"""Recording upload / finalize, transcript read & edit, summary jobs."""
import io
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, owner_or_404
from app.core.db import get_db
from app.core.errors import AppError
from app.models import (
    AIJob,
    DomainEvent,
    Lesson,
    LessonSummary,
    OutboxEvent,
    Recording,
    TranscriptSegment,
    User,
)
from app.providers.storage.provider import get_storage
from app.schemas.schemas import (
    JobCreatedOut,
    RecordingOut,
    SummaryOut,
    TranscriptOut,
    TranscriptSegmentOut,
)

router = APIRouter(tags=["recordings", "transcript", "summary"])

ALLOWED_AUDIO = {"webm", "mp3", "wav", "m4a", "ogg", "aac", "mp4"}
MAX_AUDIO_BYTES = 200 * 1024 * 1024


def _lesson(db: Session, lesson_id: str, user: User) -> Lesson:
    return owner_or_404(
        db.query(Lesson).filter(Lesson.id == lesson_id, Lesson.deleted_at.is_(None)).first(), user.id
    )


@router.post("/lessons/{lesson_id}/recordings", response_model=RecordingOut, status_code=201, operation_id="recordings_create")
async def recordings_create(
    lesson_id: str,
    file: UploadFile,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    lesson = _lesson(db, lesson_id, user)
    ext = (file.filename or "audio.webm").rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_AUDIO:
        raise AppError("UNSUPPORTED_MEDIA_TYPE", f"unsupported audio extension .{ext}")
    storage = get_storage()
    data = await file.read()
    if len(data) > MAX_AUDIO_BYTES:
        raise AppError("PAYLOAD_TOO_LARGE", "audio file exceeds 200MB")
    key = storage.random_key(f"lessons/{lesson_id}", ext)
    storage.put(key, io.BytesIO(data), file.content_type)
    rec = Recording(
        lesson_id=lesson.id,
        user_id=user.id,
        storage_key=key,
        mime_type=file.content_type,
        size_bytes=len(data),
        status="recording",
    )
    lesson.status = "recording"
    lesson.started_at = lesson.started_at or datetime.now(UTC)
    db.add(rec)
    db.commit()
    return rec


@router.post("/recordings/{recording_id}/finalize", response_model=RecordingOut, operation_id="recording_finalize")
def recording_finalize(recording_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rec = owner_or_404(db.query(Recording).get(recording_id), user.id)
    if rec.status == "finalized":
        return rec
    rec.status = "finalized"
    rec.finalized_at = datetime.now(UTC)
    lesson = _lesson(db, rec.lesson_id, user)
    # final transcription pass over the complete audio (ASR provider), replaces stream transcript
    from app.providers.asr.provider import get_asr_provider

    asr = get_asr_provider()
    with open(get_storage().get_path(rec.storage_key), "rb") as fh:
        result = asr.transcribe(fh)
    db.query(TranscriptSegment).filter(
        TranscriptSegment.lesson_id == rec.lesson_id, TranscriptSegment.is_final.is_(False)
    ).delete()
    seq = db.query(TranscriptSegment).filter(TranscriptSegment.lesson_id == rec.lesson_id).count()
    for seg in result.get("segments", []):
        seq += 1
        db.add(
            TranscriptSegment(
                lesson_id=rec.lesson_id,
                recording_id=rec.id,
                sequence=seq,
                start_ms=seg.get("start_ms", 0),
                end_ms=seg.get("end_ms"),
                text=seg.get("text", ""),
                confidence=seg.get("confidence"),
                is_final=True,
            )
        )
    lesson.status = "ready"
    lesson.ended_at = lesson.ended_at or datetime.now(UTC)
    db.add(DomainEvent(event_type="recording_completed", user_id=user.id, payload={"lesson_id": lesson.id}))
    # outbox: RAG indexing of the transcript happens async
    db.add(OutboxEvent(event_type="transcript_ready", payload={"lesson_id": lesson.id, "user_id": user.id}))
    db.commit()
    return rec


@router.get("/lessons/{lesson_id}/transcript", response_model=TranscriptOut, operation_id="transcript_get")
def transcript_get(
    lesson_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(default=500, le=1000),
):
    lesson = _lesson(db, lesson_id, user)
    segs = (
        db.query(TranscriptSegment)
        .filter(TranscriptSegment.lesson_id == lesson.id)
        .order_by(TranscriptSegment.sequence)
        .limit(limit)
        .all()
    )
    from app.schemas.schemas import TranscriptSegmentOut

    return TranscriptOut(
        lesson_id=lesson.id,
        status=lesson.status,
        items=[TranscriptSegmentOut.model_validate(s) for s in segs],
    )


@router.patch("/transcript-segments/{segment_id}", response_model=TranscriptSegmentOut, operation_id="transcript_segment_update")
def transcript_segment_update(
    segment_id: str,
    body: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Edit one segment with optimistic concurrency (version). 409 on stale version."""
    seg = db.query(TranscriptSegment).get(segment_id)
    if seg is None:
        raise AppError("NOT_FOUND")
    _lesson(db, seg.lesson_id, user)
    text = body.get("text")
    version = body.get("version")
    if version is None or int(version) != seg.version:
        raise AppError("VERSION_CONFLICT", "segment was modified by another client")
    if text is None or not str(text).strip():
        raise AppError("VALIDATION_ERROR", "text required")
    seg.text = str(text)
    seg.version += 1
    db.commit()
    from app.schemas.schemas import TranscriptSegmentOut

    return TranscriptSegmentOut.model_validate(seg)


@router.post("/lessons/{lesson_id}/summary-jobs", response_model=JobCreatedOut, status_code=202, operation_id="summary_job_create")
def summary_job_create(lesson_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    lesson = _lesson(db, lesson_id, user)
    seg_count = db.query(TranscriptSegment).filter(TranscriptSegment.lesson_id == lesson.id).count()
    if seg_count == 0:
        raise AppError("CONFLICT", "lesson has no transcript to summarize")
    job = AIJob(user_id=user.id, job_type="lesson_summary", status="queued", payload={"lesson_id": lesson.id})
    lesson.status = "processing"
    db.add(job)
    db.commit()
    from app.workers.runner import run_job_async

    run_job_async(job.id)
    return JobCreatedOut(job_id=job.id)


@router.get("/lessons/{lesson_id}/summary", response_model=SummaryOut, operation_id="lesson_summary_get")
def lesson_summary_get(lesson_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    lesson = _lesson(db, lesson_id, user)
    summary = db.query(LessonSummary).filter(LessonSummary.lesson_id == lesson.id).first()
    if not summary:
        raise AppError("NOT_FOUND", "summary not generated yet")
    return SummaryOut(
        lesson_id=lesson.id,
        title=summary.title,
        overview=summary.overview,
        payload=summary.payload,
        job_id=summary.job_id,
    )
