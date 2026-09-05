"""Practice sets, attempts, and the Module-3 memory system tables."""
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
from app.models.base import IdMixin, TimestampMixin, utcnow

# ---------------------------------------------------------------- practice


class PracticeSet(Base, IdMixin, TimestampMixin):
    __tablename__ = "practice_sets"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), default="random", nullable=False)  # random | smart
    filters: Mapped[dict | None] = mapped_column(JSON)  # subject/kp/difficulty/wrong_only...
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class PracticeSetItem(Base, IdMixin, TimestampMixin):
    """Frozen ordering — refreshing the page must not reshuffle questions."""

    __tablename__ = "practice_set_items"

    practice_set_id: Mapped[str] = mapped_column(String(36), ForeignKey("practice_sets.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[str] = mapped_column(String(36), ForeignKey("questions.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (UniqueConstraint("practice_set_id", "position", name="uq_ps_item_pos"),)


class Attempt(Base, IdMixin, TimestampMixin):
    __tablename__ = "attempts"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[str] = mapped_column(String(36), ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    practice_set_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("practice_sets.id", ondelete="SET NULL"))
    review_task_id: Mapped[str | None] = mapped_column(String(36), index=True)
    answer: Mapped[str | None] = mapped_column(Text)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    score: Mapped[float | None] = mapped_column(Float)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[int | None] = mapped_column(Integer)  # 1..5
    hint_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    answer_change_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    grading_source: Mapped[str | None] = mapped_column(String(16))  # objective | self | ai_assisted
    attempted_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)

    __table_args__ = (Index("ix_attempts_user_time", "user_id", "attempted_at"),)


# ---------------------------------------------------------------- mastery


class UserKnowledgeMastery(Base, IdMixin, TimestampMixin):
    __tablename__ = "user_knowledge_mastery"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    knowledge_point_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_points.id", ondelete="CASCADE"), index=True
    )
    mastery: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)  # 0..1 estimate
    status: Mapped[str] = mapped_column(String(16), default="unknown", nullable=False)  # unknown/weak/developing/mastered
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    correct_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    __table_args__ = (UniqueConstraint("user_id", "knowledge_point_id", name="uq_user_kp_mastery"),)


# ---------------------------------------------------------------- module 3: memory system


class ReviewProfile(Base, IdMixin, TimestampMixin):
    """Cold-start onboarding answers + planner preferences (a prior, not a law)."""

    __tablename__ = "review_profiles"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    onboarded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    grade: Mapped[str | None] = mapped_column(String(32))
    primary_subject: Mapped[str | None] = mapped_column(String(32))
    daily_minutes: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    preferred_time: Mapped[str | None] = mapped_column(String(8))  # "20:00"
    target_retention: Mapped[float] = mapped_column(Float, default=0.9, nullable=False)
    exam_date: Mapped[datetime | None] = mapped_column(UTCDateTime())
    density_preference: Mapped[str | None] = mapped_column(String(16))  # little_often | focused
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Shanghai", nullable=False)


class MemoryState(Base, IdMixin, TimestampMixin):
    """Per (user, question) memory state — the heart of Module 3."""

    __tablename__ = "memory_states"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[str] = mapped_column(String(36), ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    difficulty: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)  # FSRS D 1..10
    stability: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)  # FSRS S (days)
    retrievability: Mapped[float | None] = mapped_column(Float)  # last computed R
    last_review_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    next_review_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), index=True)
    review_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lapse_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_rating: Mapped[int | None] = mapped_column(Integer)  # 1..4 internal Again/Hard/Good/Easy
    suspended: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # "mastered" suspension
    scheduler_version: Mapped[str] = mapped_column(String(64), default="fsrs45-baseline", nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "question_id", name="uq_memory_state"),
        Index("ix_ms_user_due", "user_id", "next_review_at"),
    )


class ReviewTask(Base, IdMixin, TimestampMixin):
    __tablename__ = "review_tasks"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[str] = mapped_column(String(36), ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    memory_state_id: Mapped[str] = mapped_column(String(36), ForeignKey("memory_states.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16), default="scheduled", nullable=False)
    # scheduled | due | completed | snoozed | skipped | cancelled
    due_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    priority_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(200))  # why today (UI copy)
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    scheduled_date: Mapped[str] = mapped_column(String(10), nullable=False, index=True)  # user-local YYYY-MM-DD
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    __table_args__ = (Index("ix_rt_user_status_due", "user_id", "status", "due_at"),)


class ReviewLog(Base, IdMixin, TimestampMixin):
    __tablename__ = "review_logs"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    review_task_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("review_tasks.id", ondelete="SET NULL"))
    question_id: Mapped[str] = mapped_column(String(36), ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(16), nullable=False)  # complete | skip | snooze | reschedule
    rating: Mapped[int | None] = mapped_column(Integer)  # 1..4
    attempt_id: Mapped[str | None] = mapped_column(String(36))
    elapsed_ms: Mapped[int | None] = mapped_column(Integer)
    reviewed_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    scheduler_version: Mapped[str | None] = mapped_column(String(64))
