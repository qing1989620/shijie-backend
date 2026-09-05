"""System-level entities: attachments, jobs, AI runs, RAG store, events, outbox."""
from datetime import datetime

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UTCDateTime
from app.models.base import IdMixin, TimestampMixin


class Attachment(Base, IdMixin, TimestampMixin):
    __tablename__ = "attachments"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)  # original filename (display only)
    mime_type: Mapped[str | None] = mapped_column(String(64))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    purpose: Mapped[str | None] = mapped_column(String(32))  # question_upload | lesson_audio | avatar


class AIJob(Base, IdMixin, TimestampMixin):
    __tablename__ = "ai_jobs"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    # lesson_summary | question_analysis | ocr_import | transcript_finalize | exercise_search
    status: Mapped[str] = mapped_column(String(16), default="queued", nullable=False)
    # queued | running | succeeded | failed | cancelled
    progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    stage: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict | None] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class AIRun(Base, IdMixin, TimestampMixin):
    __tablename__ = "ai_runs"

    job_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("ai_jobs.id", ondelete="SET NULL"), index=True)
    agent_name: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_version: Mapped[str | None] = mapped_column(String(32))
    prompt_version: Mapped[str | None] = mapped_column(String(32))
    provider: Mapped[str | None] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(120))
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str | None] = mapped_column(String(16))
    error_code: Mapped[str | None] = mapped_column(String(64))


class RAGDocument(Base, IdMixin, TimestampMixin):
    __tablename__ = "rag_documents"

    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)  # lesson | question | material
    source_id: Mapped[str] = mapped_column(String(36), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    subject: Mapped[str | None] = mapped_column(String(32))
    grade: Mapped[str | None] = mapped_column(String(32))
    visibility: Mapped[str] = mapped_column(String(16), default="private", nullable=False)  # private | global


class RAGChunk(Base, IdMixin, TimestampMixin):
    __tablename__ = "rag_chunks"

    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("rag_documents.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    lesson_id: Mapped[str | None] = mapped_column(String(36), index=True)
    question_id: Mapped[str | None] = mapped_column(String(36), index=True)
    knowledge_point_ids: Mapped[list | None] = mapped_column(JSON, default=list)
    embedding: Mapped[list | None] = mapped_column(JSON)  # lexical mode: None; bge mode: vector
    # production (pgvector) uses vector column; JSON keeps dev portable.

    __table_args__ = (UniqueConstraint("document_id", "chunk_index", name="uq_rag_chunk"),)


class DomainEvent(Base, IdMixin, TimestampMixin):
    """Internal product analytics + inter-module triggers."""

    __tablename__ = "domain_events"

    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str | None] = mapped_column(String(36), index=True)
    payload: Mapped[dict | None] = mapped_column(JSON)


class OutboxEvent(Base, IdMixin, TimestampMixin):
    """Transactional outbox: written in the same DB transaction as state change,
    drained by the worker to trigger async side effects (e.g. RAG indexing)."""

    __tablename__ = "outbox_events"

    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload: Mapped[dict | None] = mapped_column(JSON)
    processed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
