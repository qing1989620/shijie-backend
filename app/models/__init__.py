"""Import all models so Base.metadata sees every table."""
from app.core.db import Base
from app.models.base import IdMixin, SoftDeleteMixin, TimestampMixin  # noqa: F401
from app.models.lesson import (  # noqa: F401
    Course,
    Lesson,
    LessonKnowledgePoint,
    LessonSummary,
    Recording,
    RefreshToken,
    Subject,
    TranscriptSegment,
    User,
    UserPreference,
    UserProfile,
)
from app.models.practice import (  # noqa: F401
    Attempt,
    MemoryState,
    PracticeSet,
    PracticeSetItem,
    ReviewLog,
    ReviewProfile,
    ReviewTask,
    UserKnowledgeMastery,
)
from app.models.question import (  # noqa: F401
    ExerciseSearch,
    ExerciseSearchResult,
    KnowledgePoint,
    KnowledgePointAlias,
    KnowledgeTreeSnapshot,
    Question,
    QuestionAnalysis,
    QuestionKnowledgePoint,
    QuestionSource,
    UserQuestion,
)
from app.models.system import (  # noqa: F401
    AIJob,
    AIRun,
    Attachment,
    DomainEvent,
    OutboxEvent,
    RAGChunk,
    RAGDocument,
)

__all__ = ["Base"]
