"""Unified question bank: list / import / favorite / OCR upload / analysis / knowledge tree."""
import hashlib
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.core.errors import AppError
from app.models import (
    AIJob,
    DomainEvent,
    KnowledgePoint,
    Question,
    QuestionAnalysis,
    QuestionKnowledgePoint,
    QuestionSource,
    User,
    UserQuestion,
)
from app.providers.ocr.provider import get_ocr_provider
from app.providers.storage.provider import get_storage
from app.schemas.schemas import (
    ImportQuestionIn,
    JobCreatedOut,
    KnowledgePointDetailOut,
    KnowledgePointOut,
    OcrPreviewOut,
    QuestionDetailOut,
    QuestionListOut,
)
from app.workers.runner import run_job_async

router = APIRouter(tags=["questions"])


def _content_hash(stem: str, options: list | None) -> str:
    normalized = "".join((stem or "").split()).lower()
    opts = "".join(sorted((o.get("text", "") if isinstance(o, dict) else str(o) or "") for o in (options or [])))
    return hashlib.sha256((normalized + opts).encode()).hexdigest()


def _detail(db: Session, q: Question, user: User) -> QuestionDetailOut:
    uq = db.query(UserQuestion).filter(UserQuestion.user_id == user.id, UserQuestion.question_id == q.id).first()
    analysis = db.query(QuestionAnalysis).filter(QuestionAnalysis.question_id == q.id).first()
    out = QuestionDetailOut.model_validate(q)
    out.is_favorite = bool(uq and uq.is_favorite)
    out.origin = uq.origin if uq else None
    out.analysis_summary = analysis.tree_payload.get("summary") if analysis and analysis.tree_payload else None
    return out


@router.get("/questions", response_model=QuestionListOut, operation_id="questions_list")
def questions_list(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    subject: str | None = None,
    favorites_only: bool = False,
    wrong_only: bool = False,
    search: str | None = None,
    limit: int = Query(default=20, le=100),
    cursor: int = 0,
):
    """Paginated personal question view: my questions + my relations to bank questions."""
    base = (
        db.query(Question, UserQuestion)
        .join(UserQuestion, UserQuestion.question_id == Question.id)
        .filter(UserQuestion.user_id == user.id, Question.deleted_at.is_(None))
    )
    if subject:
        base = base.filter(Question.subject == subject)
    if favorites_only:
        base = base.filter(UserQuestion.is_favorite.is_(True))
    if wrong_only:
        from app.models import Attempt

        wrong_qids = (
            db.query(Attempt.question_id)
            .filter(Attempt.user_id == user.id, Attempt.is_correct.is_(False))
            .distinct()
            .subquery()
        )
        base = base.filter(Question.id.in_(wrong_qids))
    if search:
        like = f"%{search}%"
        base = base.filter(Question.stem.like(like))
    rows = base.order_by(UserQuestion.added_at.desc()).offset(cursor).limit(limit + 1).all()
    has_more = len(rows) > limit
    items = [_detail(db, q, user) for q, uq in rows[:limit]]
    next_cursor = cursor + limit if has_more else None
    return QuestionListOut(items=items, next_cursor=str(next_cursor) if next_cursor else None, has_more=has_more)


@router.post("/questions/import", response_model=QuestionDetailOut, status_code=201, operation_id="question_import")
def question_import(body: ImportQuestionIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Manual/text import with confirmation (OCR flow calls this after user correction)."""
    h = _content_hash(body.stem, body.options)
    existing = db.query(Question).filter(Question.content_hash == h, Question.deleted_at.is_(None)).first()
    if existing:
        uq = db.query(UserQuestion).filter(UserQuestion.user_id == user.id, UserQuestion.question_id == existing.id).first()
        if not uq:
            db.add(UserQuestion(user_id=user.id, question_id=existing.id, origin=body.origin,
                                lesson_id=body.lesson_id, added_at=datetime.now(UTC)))
            db.commit()
        return _detail(db, existing, user)
    src = None
    if body.source_name:
        src = QuestionSource(source_type="upload", source_name=body.source_name, retrieved_at=datetime.now(UTC))
        db.add(src)
        db.flush()
    q = Question(
        subject=body.subject,
        grade=body.grade,
        question_type=body.question_type,
        stem=body.stem,
        options=[o.model_dump() for o in body.options],
        answer=body.answer,
        solution=body.solution,
        difficulty=body.difficulty,
        source_id=src.id if src else None,
        content_hash=h,
        owner_user_id=user.id,
    )
    db.add(q)
    db.flush()
    db.add(UserQuestion(user_id=user.id, question_id=q.id, origin=body.origin, lesson_id=body.lesson_id,
                        added_at=datetime.now(UTC)))
    db.add(DomainEvent(event_type="question_uploaded", user_id=user.id, payload={"question_id": q.id}))
    db.commit()
    return _detail(db, q, user)


ALLOWED_IMAGE = {"png", "jpg", "jpeg", "webp", "pdf"}


@router.post("/questions/ocr", response_model=OcrPreviewOut, status_code=202, operation_id="question_ocr_preview")
async def question_ocr(
    file: UploadFile,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Upload -> OCR draft -> preview. Nothing is saved as a Question until user confirms."""
    ext = (file.filename or "img.png").rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_IMAGE:
        raise AppError("UNSUPPORTED_MEDIA_TYPE", f"unsupported file .{ext}")
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise AppError("PAYLOAD_TOO_LARGE", "file exceeds 20MB")
    ocr = get_ocr_provider()
    result = ocr.recognize(__import__("io").BytesIO(data), file.content_type or "", file.filename or "")
    storage = get_storage()
    key = storage.random_key("uploads", ext)
    storage.put(key, __import__("io").BytesIO(data), file.content_type)
    from app.models import Attachment

    att = Attachment(
        user_id=user.id, storage_key=key, display_name=file.filename or "upload",
        mime_type=file.content_type, size_bytes=len(data), purpose="question_upload",
    )
    db.add(att)
    db.flush()
    return OcrPreviewOut(
        attachment_id=att.id, text=result.get("text", ""), blocks=result.get("blocks", []),
        needs_review=result.get("needs_review", True), notice=result.get("notice"),
    )


@router.post("/questions/{question_id}/favorite", response_model=QuestionDetailOut, operation_id="question_favorite")
def question_favorite(
    question_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    lesson_id: str | None = None,
):
    """Favorite -> UserQuestion row -> visible in Module 2 immediately. Idempotent."""
    q = db.query(Question).filter(Question.id == question_id, Question.deleted_at.is_(None)).first()
    if not q:
        raise AppError("NOT_FOUND")
    uq = db.query(UserQuestion).filter(UserQuestion.user_id == user.id, UserQuestion.question_id == q.id).first()
    if uq:
        uq.is_favorite = True
        uq.origin = uq.origin or "favorite"
    else:
        uq = UserQuestion(user_id=user.id, question_id=q.id, is_favorite=True, origin="favorite",
                          lesson_id=lesson_id, added_at=datetime.now(UTC))
        db.add(uq)
    db.add(DomainEvent(event_type="question_favorited", user_id=user.id, payload={"question_id": q.id}))
    db.commit()
    return _detail(db, q, user)


@router.delete("/questions/{question_id}/favorite", response_model=QuestionDetailOut, operation_id="question_unfavorite")
def question_unfavorite(question_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Question).get(question_id)
    if not q:
        raise AppError("NOT_FOUND")
    uq = db.query(UserQuestion).filter(UserQuestion.user_id == user.id, UserQuestion.question_id == q.id).first()
    if uq:
        uq.is_favorite = False
        db.commit()
    return _detail(db, q, user)


@router.delete("/questions/{question_id}", status_code=204, operation_id="question_delete")
def question_delete(question_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Question).get(question_id)
    if q is None:
        raise AppError("NOT_FOUND")
    uq = db.query(UserQuestion).filter(UserQuestion.user_id == user.id, UserQuestion.question_id == q.id).first()
    if not uq:
        raise AppError("FORBIDDEN", "not your question")
    from datetime import datetime as dt

    q.deleted_at = dt.now(UTC)
    db.delete(uq)
    db.commit()
    return None


@router.get("/questions/{question_id}", response_model=QuestionDetailOut, operation_id="question_get")
def question_get(question_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Question).filter(Question.id == question_id, Question.deleted_at.is_(None)).first()
    if not q:
        raise AppError("NOT_FOUND")
    if not q.is_global and q.owner_user_id != user.id:
        # visible only if related to the user (favorite/uploaded)
        if not db.query(UserQuestion).filter(UserQuestion.user_id == user.id, UserQuestion.question_id == q.id).first():
            raise AppError("FORBIDDEN", "no access to this question")
    return _detail(db, q, user)


@router.post("/questions/{question_id}/analysis-jobs", response_model=JobCreatedOut, status_code=202, operation_id="analysis_job_create")
def analysis_job_create(question_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Question).filter(Question.id == question_id, Question.deleted_at.is_(None)).first()
    if not q:
        raise AppError("NOT_FOUND")
    job = AIJob(user_id=user.id, job_type="question_analysis", status="queued", payload={"question_id": q.id})
    db.add(job)
    db.commit()
    run_job_async(job.id)
    return JobCreatedOut(job_id=job.id)


@router.get("/questions/{question_id}/knowledge-tree", response_model=dict, operation_id="knowledge_tree_get")
def knowledge_tree_get(question_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Question).get(question_id)
    if not q:
        raise AppError("NOT_FOUND")
    analysis = db.query(QuestionAnalysis).filter(QuestionAnalysis.question_id == q.id).first()
    if not analysis or not analysis.tree_payload:
        raise AppError("NOT_FOUND", "analysis not ready")
    payload = analysis.tree_payload

    def enrich(node: dict) -> dict:
        kp = (
            db.query(KnowledgePoint)
            .filter(KnowledgePoint.name == node.get("name"))
            .first()
        )
        out = dict(node)
        out["knowledge_point_id"] = kp.id if kp else None
        out["children"] = [enrich(c) for c in node.get("children", [])]
        return out

    tree = enrich(payload["root"])
    # attach mastery estimates for the user
    from app.models import UserKnowledgeMastery

    def attach_mastery(node: dict) -> dict:
        node = dict(node)
        node["mastery_estimate"] = None
        if node.get("knowledge_point_id"):
            m = (
                db.query(UserKnowledgeMastery)
                .filter(UserKnowledgeMastery.user_id == user.id,
                        UserKnowledgeMastery.knowledge_point_id == node["knowledge_point_id"])
                .first()
            )
            if m:
                node["mastery_estimate"] = round(m.mastery, 3)
        node["children"] = [attach_mastery(c) for c in node.get("children", [])]
        return node

    tree = attach_mastery(tree)
    return {"question_id": q.id, "summary": payload.get("summary"), "tree": tree}


@router.get("/knowledge-points", response_model=list[KnowledgePointOut], operation_id="knowledge_points_list")
def knowledge_points_list(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """User's knowledge points with mastery estimates (weak ones first)."""
    from app.models import UserKnowledgeMastery

    kps = db.query(KnowledgePoint).all()
    masteries = {m.knowledge_point_id: m for m in db.query(UserKnowledgeMastery).filter(UserKnowledgeMastery.user_id == user.id)}
    counts = dict(
        db.query(QuestionKnowledgePoint.knowledge_point_id, func.count())
        .join(Question)
        .filter(Question.deleted_at.is_(None))
        .group_by(QuestionKnowledgePoint.knowledge_point_id)
        .all()
    )
    out: list[KnowledgePointOut] = []
    for kp in kps:
        m = masteries.get(kp.id)
        out.append(KnowledgePointOut(
            id=kp.id, name=kp.name, subject=kp.subject, description=kp.description,
            mastery=round(m.mastery, 3) if m else None,
            mastery_status=m.status if m else "unknown",
            question_count=counts.get(kp.id, 0),
        ))
    out.sort(key=lambda x: (x.mastery if x.mastery is not None else 2.0))
    return out


@router.get("/knowledge-points/{kp_id}", response_model=KnowledgePointDetailOut, operation_id="knowledge_point_get")
def knowledge_point_get(kp_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    kp = db.query(KnowledgePoint).get(kp_id)
    if not kp:
        raise AppError("NOT_FOUND")
    from app.models import UserKnowledgeMastery

    m = db.query(UserKnowledgeMastery).filter(
        UserKnowledgeMastery.user_id == user.id, UserKnowledgeMastery.knowledge_point_id == kp.id
    ).first()
    return KnowledgePointDetailOut(
        id=kp.id, name=kp.name, subject=kp.subject, description=kp.description,
        mastery=round(m.mastery, 3) if m else None,
        mastery_status=m.status if m else "unknown",
        note="掌握度是系统根据学习行为的估算，不是精确测量。",
    )
