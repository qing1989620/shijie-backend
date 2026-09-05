"""Job execution — dev-mode worker.

Runs AI jobs in a background thread with its own DB session (production swaps in
Dramatiq/Celery workers calling the same `execute_job` functions; see
docs/adr/ADR-008-Background-Jobs.md). Job progress/stage is persisted so the
frontend can render "排队中 → 解析题目 → 识别知识点 → 生成知识结构 → 完成".
"""
import threading
import traceback
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models import (
    AIJob,
    DomainEvent,
    KnowledgePoint,
    KnowledgeTreeSnapshot,
    Lesson,
    LessonKnowledgePoint,
    LessonSummary,
    OutboxEvent,
    Question,
    QuestionAnalysis,
    QuestionKnowledgePoint,
    RAGChunk,
    RAGDocument,
    TranscriptSegment,
)


def _set(job: AIJob, status: str | None = None, progress: float | None = None, stage: str | None = None):
    if status:
        job.status = status
    if progress is not None:
        job.progress = progress
    if stage is not None:
        job.stage = stage


def execute_job(db: Session, job_id: str) -> None:
    job = db.query(AIJob).get(job_id)
    if job is None:
        return
    _set(job, status="running", progress=0.05, stage="开始处理")
    job.started_at = datetime.now(UTC)
    db.commit()
    try:
        if job.job_type == "lesson_summary":
            _run_lesson_summary(db, job)
        elif job.job_type == "question_analysis":
            _run_question_analysis(db, job)
        elif job.job_type == "rag_indexing":
            _run_rag_indexing(db, job)
        else:
            raise ValueError(f"unknown job type {job.job_type}")
        _set(job, status="succeeded", progress=1.0, stage="完成")
        job.finished_at = datetime.now(UTC)
        db.commit()
    except Exception as exc:
        db.rollback()
        job = db.query(AIJob).get(job_id)
        _set(job, status="failed", stage="失败")
        job.error_code = type(exc).__name__
        job.error_message = str(exc)[:500]
        job.finished_at = datetime.now(UTC)
        db.commit()


def _run_lesson_summary(db: Session, job: AIJob):
    lesson_id = job.payload["lesson_id"]
    lesson = db.query(Lesson).get(lesson_id)
    segments = (
        db.query(TranscriptSegment)
        .filter(TranscriptSegment.lesson_id == lesson_id)
        .order_by(TranscriptSegment.sequence)
        .all()
    )
    _set(job, progress=0.2, stage="整理转写片段")
    db.commit()
    from app.ai.agents.agents import LessonSummaryAgent, canonicalize_kp

    agent = LessonSummaryAgent()
    result, meta = agent.run(
        db,
        segment_ids=[s.id for s in segments],
        segments=[s.text for s in segments],
        timestamps=[s.start_ms for s in segments],
        subject=lesson.subject,
        job_id=job.id,
    )
    _set(job, progress=0.6, stage="生成课堂总结")
    db.commit()
    summary = db.query(LessonSummary).filter(LessonSummary.lesson_id == lesson_id).first()
    if not summary:
        summary = LessonSummary(lesson_id=lesson_id)
        db.add(summary)
    summary.job_id = job.id
    summary.title = result.title
    summary.overview = result.overview
    summary.payload = result.model_dump(mode="json")
    summary.model = meta.get("model")
    summary.prompt_version = "v1"
    # knowledge points from summary -> canonical entities + lesson links
    linked_kp_ids: set[str] = set()
    first_topic_ids = result.model_dump(mode="json").get("topics", [{}])[0].get("source_segment_ids", [])
    for kp_name in result.knowledge_points[:8]:
        kp = canonicalize_kp(db, kp_name, lesson.subject)
        if kp.id in linked_kp_ids:
            continue
        exists = (
            db.query(LessonKnowledgePoint)
            .filter(LessonKnowledgePoint.lesson_id == lesson_id, LessonKnowledgePoint.knowledge_point_id == kp.id)
            .first()
        )
        if not exists:
            db.add(LessonKnowledgePoint(lesson_id=lesson_id, knowledge_point_id=kp.id, confidence=0.6,
                                        source_segment_ids=first_topic_ids))
            linked_kp_ids.add(kp.id)
            db.flush()  # autoflush=False: keep in-transaction existence checks accurate
    lesson.status = "ready"
    db.add(DomainEvent(event_type="summary_generated", user_id=job.user_id, payload={"lesson_id": lesson_id}))
    db.add(OutboxEvent(event_type="index_lesson", payload={"lesson_id": lesson_id, "user_id": job.user_id}))


def _run_question_analysis(db: Session, job: AIJob):
    question_id = job.payload["question_id"]
    question = db.query(Question).get(question_id)
    _set(job, progress=0.25, stage="解析题目")
    db.commit()
    from app.ai.agents.agents import QuestionAnalysisAgent, canonicalize_kp

    # seed candidates from existing knowledge point vocabulary (canonical names only)
    names = [k.name for k in db.query(KnowledgePoint).limit(40).all()]
    agent = QuestionAnalysisAgent()
    result, meta = agent.run(db, stem=question.stem, canonical_names=names, job_id=job.id)
    _set(job, progress=0.65, stage="识别知识点")
    db.commit()

    # flatten tree -> canonical KnowledgePoints + relations
    def walk(node, out):
        out.append(node)
        for c in node.children:
            walk(c, out)

    nodes = []
    walk(result.root, nodes)
    kp_map = {}
    for node in nodes:
        kp = canonicalize_kp(db, node.name, question.subject)
        kp_map[node.name] = (kp, node)
    analysis = db.query(QuestionAnalysis).filter(QuestionAnalysis.question_id == question_id).first()
    if not analysis:
        analysis = QuestionAnalysis(question_id=question_id)
        db.add(analysis)
    analysis.job_id = job.id
    analysis.tree_payload = result.model_dump(mode="json")
    analysis.model = meta.get("model")
    analysis.prompt_version = "v1"
    db.flush()
    db.add(KnowledgeTreeSnapshot(question_id=question_id, analysis_id=analysis.id,
                                 tree_payload=result.model_dump(mode="json")))
    for (kp, node) in kp_map.values():
        exists = (
            db.query(QuestionKnowledgePoint)
            .filter(QuestionKnowledgePoint.question_id == question_id, QuestionKnowledgePoint.knowledge_point_id == kp.id)
            .first()
        )
        if not exists:
            db.add(QuestionKnowledgePoint(question_id=question_id, knowledge_point_id=kp.id,
                                          role=node.role, confidence=node.confidence))
    _set(job, progress=0.9, stage="生成知识结构")
    db.add(DomainEvent(event_type="question_analyzed", user_id=job.user_id, payload={"question_id": question_id}))
    db.add(OutboxEvent(event_type="index_question", payload={"question_id": question_id}))


def _run_rag_indexing(db: Session, job: AIJob):
    """Index lesson transcript / question into RAG chunks (lexical mode: no vectors)."""
    payload = job.payload or {}
    lesson_id = payload.get("lesson_id")
    if lesson_id:
        doc = db.query(RAGDocument).filter(RAGDocument.source_type == "lesson", RAGDocument.source_id == lesson_id).first()
        if not doc:
            lesson = db.query(Lesson).get(lesson_id)
            doc = RAGDocument(user_id=payload.get("user_id"), source_type="lesson", source_id=lesson_id,
                              title=lesson.title, subject=lesson.subject, grade=lesson.grade, visibility="private")
            db.add(doc)
            db.flush()
        segs = db.query(TranscriptSegment).filter(TranscriptSegment.lesson_id == lesson_id).order_by(TranscriptSegment.sequence).all()
        chunk_size = 6
        for i in range(0, len(segs), chunk_size):
            part = segs[i : i + chunk_size]
            content = "\n".join(f"[{s.start_ms//1000}s] {s.text}" for s in part)
            exists = db.query(RAGChunk).filter(RAGChunk.document_id == doc.id, RAGChunk.chunk_index == i // chunk_size).first()
            if not exists:
                db.add(RAGChunk(document_id=doc.id, chunk_index=i // chunk_size, content=content,
                                lesson_id=lesson_id))
    _set(job, progress=0.8, stage="建立检索索引")


def run_job_async(job_id: str) -> None:
    """Spawn a daemon worker thread (dev worker). Production: queue enqueue."""

    def _runner():
        db = SessionLocal()
        try:
            execute_job(db, job_id)
        except Exception:
            traceback.print_exc()
        finally:
            db.close()

    threading.Thread(target=_runner, daemon=True).start()


def drain_outbox(db: Session) -> int:
    """Process pending outbox events (called by worker loop / startup)."""
    events = db.query(OutboxEvent).filter(OutboxEvent.processed_at.is_(None)).limit(50).all()
    for ev in events:
        if ev.event_type in {"transcript_ready", "index_lesson"}:
            lesson_id = (ev.payload or {}).get("lesson_id")
            if lesson_id:
                job = AIJob(user_id=(ev.payload or {}).get("user_id"), job_type="rag_indexing",
                            status="queued", payload={"lesson_id": lesson_id, **(ev.payload or {})})
                db.add(job)
                db.flush()
                execute_job(db, job.id)
        elif ev.event_type == "index_question":
            pass  # question indexing joins lesson indexing for now
        ev.processed_at = datetime.now(UTC)
    db.commit()
    return len(events)
