"""User, auth, course/lesson domain entities (Module 1 + platform core)."""
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, UTCDateTime
from app.models.base import IdMixin, SoftDeleteMixin, TimestampMixin

# ---------------------------------------------------------------- users


class User(Base, IdMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    profile: Mapped["UserProfile | None"] = relationship(back_populates="user", uselist=False)
    preference: Mapped["UserPreference | None"] = relationship(back_populates="user", uselist=False)


class UserProfile(Base, IdMixin, TimestampMixin):
    __tablename__ = "user_profiles"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    grade: Mapped[str | None] = mapped_column(String(32))  # e.g. 初三 / 高一
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Shanghai", nullable=False)

    user: Mapped[User] = relationship(back_populates="profile")


class UserPreference(Base, IdMixin, TimestampMixin):
    __tablename__ = "user_preferences"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    daily_review_minutes: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    preferred_review_time: Mapped[str] = mapped_column(String(8), default="20:00", nullable=False)
    target_retention: Mapped[float] = mapped_column(Float, default=0.9, nullable=False)
    exam_date: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    primary_subject: Mapped[str | None] = mapped_column(String(32))

    user: Mapped[User] = relationship(back_populates="preference")


class RefreshToken(Base, IdMixin, TimestampMixin):
    """Rotating refresh tokens; revoked tokens cannot be reused."""

    __tablename__ = "refresh_tokens"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    jti: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


# ---------------------------------------------------------------- subjects / courses / lessons


class Subject(Base, IdMixin, TimestampMixin):
    __tablename__ = "subjects"

    name: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)  # 数学 / 英语 ...
    slug: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)


class Course(Base, IdMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "courses"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    subject_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("subjects.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    teacher: Mapped[str | None] = mapped_column(String(80))
    grade: Mapped[str | None] = mapped_column(String(32))
    description: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str | None] = mapped_column(String(9))

    subject_ref: Mapped["Subject | None"] = relationship()

    @property
    def subject(self) -> str | None:
        return self.subject_ref.name if self.subject_ref else None

    __table_args__ = (Index("ix_courses_user_created", "user_id", "created_at"),)


class Lesson(Base, IdMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "lessons"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("courses.id", ondelete="SET NULL"), index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(32))
    grade: Mapped[str | None] = mapped_column(String(32))
    teacher: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)  # draft/recording/processing/ready/failed/archived
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    tags: Mapped[list | None] = mapped_column(JSON, default=list)

    __table_args__ = (Index("ix_lessons_user_created", "user_id", "created_at"),)


class Recording(Base, IdMixin, TimestampMixin):
    __tablename__ = "recordings"

    lesson_id: Mapped[str] = mapped_column(String(36), ForeignKey("lessons.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(64))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="recording", nullable=False)  # recording/finalized/failed
    finalized_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class TranscriptSegment(Base, IdMixin, TimestampMixin):
    __tablename__ = "transcript_segments"

    lesson_id: Mapped[str] = mapped_column(String(36), ForeignKey("lessons.id", ondelete="CASCADE"), index=True)
    recording_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("recordings.id", ondelete="SET NULL"))
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    speaker: Mapped[str | None] = mapped_column(String(32))
    is_final: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint("lesson_id", "sequence", name="uq_segment_lesson_seq"),
        Index("ix_segments_lesson_start", "lesson_id", "start_ms"),
    )


class LessonSummary(Base, IdMixin, TimestampMixin):
    __tablename__ = "lesson_summaries"

    lesson_id: Mapped[str] = mapped_column(String(36), ForeignKey("lessons.id", ondelete="CASCADE"), unique=True)
    job_id: Mapped[str | None] = mapped_column(String(36))
    title: Mapped[str | None] = mapped_column(String(200))
    overview: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict | None] = mapped_column(JSON)  # full structured summary with source_segment_ids
    model: Mapped[str | None] = mapped_column(String(120))
    prompt_version: Mapped[str | None] = mapped_column(String(32))


class LessonKnowledgePoint(Base, IdMixin, TimestampMixin):
    __tablename__ = "lesson_knowledge_points"

    lesson_id: Mapped[str] = mapped_column(String(36), ForeignKey("lessons.id", ondelete="CASCADE"), index=True)
    knowledge_point_id: Mapped[str] = mapped_column(String(36), ForeignKey("knowledge_points.id", ondelete="CASCADE"), index=True)
    confidence: Mapped[float | None] = mapped_column(Float)
    source_segment_ids: Mapped[list | None] = mapped_column(JSON, default=list)

    __table_args__ = (UniqueConstraint("lesson_id", "knowledge_point_id", name="uq_lesson_kp"),)
