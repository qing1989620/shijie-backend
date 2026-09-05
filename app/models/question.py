"""Knowledge points, unified Question, user-question relations, analysis artifacts."""
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UTCDateTime
from app.models.base import IdMixin, SoftDeleteMixin, TimestampMixin

# ---------------------------------------------------------------- knowledge points


class KnowledgePoint(Base, IdMixin, TimestampMixin):
    """Canonical knowledge node. Aliases map surface forms onto it."""

    __tablename__ = "knowledge_points"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True, nullable=False)
    subject: Mapped[str | None] = mapped_column(String(32), index=True)
    grade: Mapped[str | None] = mapped_column(String(32))
    description: Mapped[str | None] = mapped_column(Text)
    parent_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("knowledge_points.id", ondelete="SET NULL"))
    importance: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)  # 0..1 taxonomy weight


class KnowledgePointAlias(Base, IdMixin, TimestampMixin):
    __tablename__ = "knowledge_point_aliases"

    knowledge_point_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_points.id", ondelete="CASCADE"), index=True
    )
    alias: Mapped[str] = mapped_column(String(160), nullable=False)

    __table_args__ = (UniqueConstraint("alias", name="uq_kp_alias"),)


# ---------------------------------------------------------------- questions


class QuestionSource(Base, IdMixin, TimestampMixin):
    __tablename__ = "question_sources"

    source_type: Mapped[str] = mapped_column(String(32), nullable=False)  # local_bank | upload | lesson | external
    source_name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(500))
    license: Mapped[str | None] = mapped_column(String(120))
    retrieved_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    original_id: Mapped[str | None] = mapped_column(String(160))


class Question(Base, IdMixin, TimestampMixin, SoftDeleteMixin):
    """Unified question entity — shared by lesson favorites, uploads, and bank retrieval."""

    __tablename__ = "questions"

    subject: Mapped[str | None] = mapped_column(String(32), index=True)
    grade: Mapped[str | None] = mapped_column(String(32))
    question_type: Mapped[str] = mapped_column(String(24), default="single_choice", nullable=False)
    # single_choice | multi_choice | fill_blank | true_false | subjective
    stem: Mapped[str] = mapped_column(Text, nullable=False)  # Markdown + LaTeX
    options: Mapped[list | None] = mapped_column(JSON, default=list)  # [{key, text}]
    answer: Mapped[str | None] = mapped_column(Text)  # may be empty for subjective
    solution: Mapped[str | None] = mapped_column(Text)
    difficulty: Mapped[int] = mapped_column(Integer, default=3, nullable=False)  # 1..5
    source_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("question_sources.id", ondelete="SET NULL"))
    content_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    is_global: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # bank questions visible to all
    owner_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)

    __table_args__ = (Index("ix_questions_subject_diff", "subject", "difficulty"),)


class UserQuestion(Base, IdMixin, TimestampMixin):
    """The user<->question relation: favorites, uploads, personal metadata.

    Modules reference Question through this table — never copies of content.
    """

    __tablename__ = "user_questions"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[str] = mapped_column(String(36), ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    origin: Mapped[str] = mapped_column(String(24), default="favorite", nullable=False)
    # favorite | upload | lesson | specialized_search | practice
    lesson_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("lessons.id", ondelete="SET NULL"), index=True)
    note: Mapped[str | None] = mapped_column(Text)
    added_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "question_id", name="uq_user_question"),
        Index("ix_uq_user_added", "user_id", "added_at"),
    )


class QuestionAnalysis(Base, IdMixin, TimestampMixin):
    __tablename__ = "question_analyses"

    question_id: Mapped[str] = mapped_column(String(36), ForeignKey("questions.id", ondelete="CASCADE"), unique=True)
    job_id: Mapped[str | None] = mapped_column(String(36))
    tree_payload: Mapped[dict | None] = mapped_column(JSON)  # validated KnowledgeTree
    model: Mapped[str | None] = mapped_column(String(120))
    prompt_version: Mapped[str | None] = mapped_column(String(32))


class KnowledgeTreeSnapshot(Base, IdMixin, TimestampMixin):
    """Immutable snapshot of a question's knowledge tree (history preserved)."""

    __tablename__ = "knowledge_tree_snapshots"

    question_id: Mapped[str] = mapped_column(String(36), ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    analysis_id: Mapped[str] = mapped_column(String(36), ForeignKey("question_analyses.id", ondelete="CASCADE"))
    tree_payload: Mapped[dict | None] = mapped_column(JSON)


class QuestionKnowledgePoint(Base, IdMixin, TimestampMixin):
    __tablename__ = "question_knowledge_points"

    question_id: Mapped[str] = mapped_column(String(36), ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    knowledge_point_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_points.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16), default="core", nullable=False)  # prerequisite|core|method|extension
    confidence: Mapped[float | None] = mapped_column(Float)

    __table_args__ = (UniqueConstraint("question_id", "knowledge_point_id", name="uq_question_kp"),)


# ---------------------------------------------------------------- search


class ExerciseSearch(Base, IdMixin, TimestampMixin):
    __tablename__ = "exercise_searches"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)  # lesson | knowledge_point
    lesson_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("lessons.id", ondelete="SET NULL"))
    knowledge_point_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("knowledge_points.id", ondelete="SET NULL"))
    query_payload: Mapped[dict | None] = mapped_column(JSON)  # structured ExerciseSearchQuery
    status: Mapped[str] = mapped_column(String(16), default="queued", nullable=False)  # queued/running/succeeded/failed
    agent: Mapped[str | None] = mapped_column(String(64))
    explanation: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(64))


class ExerciseSearchResult(Base, IdMixin, TimestampMixin):
    __tablename__ = "exercise_search_results"

    search_id: Mapped[str] = mapped_column(String(36), ForeignKey("exercise_searches.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[str] = mapped_column(String(36), ForeignKey("questions.id", ondelete="CASCADE"))
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    relevance_reason: Mapped[str | None] = mapped_column(Text)  # short AI explanation: why relevant
    band: Mapped[str | None] = mapped_column(String(16))  # basic | same_level | advanced

    __table_args__ = (Index("ix_esr_search_score", "search_id", "score"),)
