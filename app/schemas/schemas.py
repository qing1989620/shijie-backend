"""Pydantic request/response schemas (API contract source of truth)."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# ---------------------------------------------------------------- shared


class CursorPage(BaseModel):
    items: list[Any]
    next_cursor: str | None = None
    has_more: bool = False



class Option(BaseModel):
    key: str
    text: str


# ---------------------------------------------------------------- auth


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=80)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenPairOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshIn(BaseModel):
    refresh_token: str


class LogoutIn(BaseModel):
    refresh_token: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    display_name: str
    created_at: datetime


class UpdateMeIn(BaseModel):
    display_name: str | None = None
    grade: str | None = None
    timezone: str | None = None


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


# ---------------------------------------------------------------- courses


class CourseIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    subject: str | None = None
    teacher: str | None = None
    grade: str | None = None
    description: str | None = None
    color: str | None = None


class CourseOut(CourseIn):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime


# ---------------------------------------------------------------- lessons


class LessonIn(BaseModel):
    course_id: str | None = None
    title: str = Field(min_length=1, max_length=200)
    subject: str | None = None
    grade: str | None = None
    teacher: str | None = None
    tags: list[str] = []


class LessonPatchIn(BaseModel):
    title: str | None = None
    status: str | None = None
    tags: list[str] | None = None


class LessonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    course_id: str | None
    title: str
    subject: str | None
    grade: str | None
    teacher: str | None
    status: str
    started_at: datetime | None
    ended_at: datetime | None
    tags: list[str] | None
    created_at: datetime


class RecordingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    lesson_id: str
    status: str
    mime_type: str | None
    size_bytes: int | None
    duration_ms: int | None
    created_at: datetime


class TranscriptSegmentPatch(BaseModel):
    text: str | None = None
    version: int  # optimistic concurrency


class TranscriptSegmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    sequence: int
    start_ms: int
    end_ms: int | None
    text: str
    confidence: float | None
    is_final: bool
    version: int


class TranscriptOut(BaseModel):
    lesson_id: str
    status: str
    items: list[TranscriptSegmentOut]


class SummaryOut(BaseModel):
    lesson_id: str
    title: str | None
    overview: str | None
    payload: dict | None
    job_id: str | None


# ---------------------------------------------------------------- questions


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    subject: str | None
    grade: str | None
    question_type: str
    stem: str
    options: list[Option] | None = None
    answer: str | None
    solution: str | None
    difficulty: int
    content_hash: str
    created_at: datetime


class QuestionDetailOut(QuestionOut):
    is_favorite: bool = False
    origin: str | None = None
    analysis_summary: str | None = None


class ImportQuestionIn(BaseModel):
    subject: str | None = None
    grade: str | None = None
    question_type: str = "single_choice"
    stem: str = Field(min_length=1)
    options: list[Option] = []
    answer: str | None = None
    solution: str | None = None
    difficulty: int = Field(default=3, ge=1, le=5)
    origin: str = "upload"  # upload | lesson | specialized_search | favorite
    lesson_id: str | None = None
    source_name: str | None = None


class QuestionListOut(BaseModel):
    items: list[QuestionDetailOut]
    next_cursor: str | None = None
    has_more: bool = False


class OcrPreviewOut(BaseModel):
    attachment_id: str
    text: str
    blocks: list[dict]
    needs_review: bool
    notice: str | None = None


# ---------------------------------------------------------------- knowledge


class TreeNodeOut(BaseModel):
    id: str | None = None
    knowledge_point_id: str | None = None
    name: str
    role: str
    level: int = 1
    description: str = ""
    importance: float = 0.5
    confidence: float = 0.6
    mastery_estimate: float | None = None
    children: list["TreeNodeOut"] = []


TreeNodeOut.model_rebuild()


class KnowledgeTreeOut(BaseModel):
    question_id: str
    summary: str | None
    tree: TreeNodeOut | None


class KnowledgePointOut(BaseModel):
    id: str
    name: str
    subject: str | None = None
    description: str | None = None
    mastery: float | None = None
    mastery_status: str | None = None
    question_count: int | None = None


class KnowledgePointDetailOut(KnowledgePointOut):
    note: str | None = None


# ---------------------------------------------------------------- exercise search


class ExerciseSearchOut(BaseModel):
    id: str
    scope: str
    lesson_id: str | None
    knowledge_point_id: str | None
    status: str
    explanation: str | None
    created_at: datetime


class ExerciseSearchResultOut(BaseModel):
    question: QuestionOut
    score: float
    band: str | None
    relevance_reason: str | None


class ExerciseSearchDetailOut(ExerciseSearchOut):
    results: list[ExerciseSearchResultOut] = []


# ---------------------------------------------------------------- practice


class PracticeSetCreateIn(BaseModel):
    mode: str = "random"  # random | smart
    count: int = Field(default=5, ge=1, le=50)
    subject: str | None = None
    knowledge_point_ids: list[str] = []
    difficulty: int | None = None
    wrong_only: bool = False
    favorite_only: bool = False
    title: str | None = None


class PracticeSetItemOut(BaseModel):
    position: int
    question: QuestionDetailOut


class PracticeSetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    mode: str
    filters: dict | None
    created_at: datetime
    items: list[PracticeSetItemOut] = []


class AttemptIn(BaseModel):
    question_id: str
    answer: str | None = None
    is_correct: bool | None = None
    score: float | None = None
    duration_ms: int | None = None
    confidence: int | None = Field(default=None, ge=1, le=5)
    hint_count: int = 0
    answer_change_count: int = 0
    grading_source: str | None = None  # objective|self|ai_assisted
    review_task_id: str | None = None


class AttemptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    question_id: str
    practice_set_id: str | None
    is_correct: bool | None
    score: float | None
    attempted_at: datetime
    created_memory_state: bool = False


# ---------------------------------------------------------------- review


class ReviewProfileIn(BaseModel):
    grade: str | None = None
    primary_subject: str | None = None
    daily_minutes: int = Field(default=20, ge=5, le=240)
    preferred_time: str | None = None
    target_retention: float = Field(default=0.9, ge=0.7, le=0.98)
    exam_date: datetime | None = None
    density_preference: str | None = None


class ReviewProfileOut(ReviewProfileIn):
    model_config = ConfigDict(from_attributes=True)

    onboarded: bool
    user_id: str


class ReviewTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    question_id: str
    status: str
    due_at: datetime
    priority_score: float
    reason: str | None
    estimated_minutes: int
    scheduled_date: str


class ReviewTaskDetailOut(ReviewTaskOut):
    question: QuestionOut | None = None
    retrievability: float | None = None
    last_rating: int | None = None


class ReviewCalendarDay(BaseModel):
    date: str
    count: int
    items: list[ReviewTaskOut] = []


class MemoryStateOut(BaseModel):
    question_id: str
    difficulty: float
    stability: float
    retrievability: float | None
    last_review_at: datetime | None
    next_review_at: datetime | None
    review_count: int
    lapse_count: int
    scheduler_version: str


class MemoryForecastOut(BaseModel):
    question_id: str
    points: list[dict]


class ReviewCompleteIn(BaseModel):
    attempt: AttemptIn | None = None  # answering inside review flow


# ---------------------------------------------------------------- jobs


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_type: str
    status: str
    progress: float
    stage: str | None
    result: dict | None
    error_code: str | None
    error_message: str | None
    created_at: datetime


# ---------------------------------------------------------------- meta


class MetaVersionOut(BaseModel):
    api_version: str = "1"
    contract_version: str = "1.0.0"
    app_env: str


class HealthOut(BaseModel):
    status: str
    database: bool


class ReadyOut(BaseModel):
    ready: bool
    checks: dict[str, bool]


class LessonPageOut(CursorPage):
    items: list[LessonOut] = []


class CoursePageOut(CursorPage):
    items: list[CourseOut] = []


class JobCreatedOut(BaseModel):
    job_id: str
