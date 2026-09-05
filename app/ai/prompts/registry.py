"""Prompt registry — every AI capability has a named, versioned prompt.

Never scatter prompts inside services. Each entry: name, version, system text,
output schema. MockLLM handlers are keyed by prompt version.
"""
from pydantic import BaseModel, Field

# ------------------------------------------------------------------ schemas


class SummaryTopic(BaseModel):
    topic: str
    summary: str
    source_segment_ids: list[str] = []
    timestamp_range: list[int] = []


class KeyConcept(BaseModel):
    concept: str
    definition: str


class LessonSummaryResult(BaseModel):
    title: str
    overview: str
    topics: list[SummaryTopic]
    key_concepts: list[KeyConcept] = []
    definitions: list[KeyConcept] = []
    formulas: list[KeyConcept] = []
    teacher_emphasis: list[str] = []
    examples: list[str] = []
    common_mistakes: list[str] = []
    knowledge_points: list[str] = []
    review_focus: list[str] = []
    uncertain: bool = False


class ExerciseQueryRewrite(BaseModel):
    keywords: list[str]
    subject: str | None = None
    grade: str | None = None
    difficulty_hint: int | None = None
    rationale: str = ""


class TreeNode(BaseModel):
    name: str
    role: str = Field(pattern="^(prerequisite|core|method|extension)$")
    level: int = 1
    description: str = ""
    importance: float = 0.5
    confidence: float = 0.6
    children: list["TreeNode"] = []


class QuestionAnalysisResult(BaseModel):
    root: TreeNode
    summary: str = ""
    mastery_signals: list[str] = []


TreeNode.model_rebuild()


class SearchQuery(BaseModel):
    keywords: list[str] = []
    subject: str | None = None
    grade: str | None = None
    difficulty_hint: int | None = None


# ------------------------------------------------------------------ prompts

LESSON_SUMMARY_V1 = {
    "name": "lesson_summary_v1",
    "version": "v1",
    "system": (
        "你是课堂笔记助手。只根据给定的课堂转写内容总结，禁止编造老师没有讲过的内容。"
        "无法确定的内容输出 uncertain=true。严格输出 JSON，结构符合 LessonSummaryResult schema。"
        "关键结论必须携带 source_segment_ids 与 timestamp_range，让用户能跳回课堂原位置。"
    ),
    "output_schema": LessonSummaryResult,
}

EXERCISE_QUERY_REWRITE_V1 = {
    "name": "exercise_query_rewrite_v1",
    "version": "v1",
    "system": (
        "你是检索查询构造器。根据课堂知识点构造题目检索关键词。"
        "严格输出 JSON，结构符合 ExerciseQueryRewrite schema。"
    ),
    "output_schema": ExerciseQueryRewrite,
}

QUESTION_ANALYSIS_V1 = {
    "name": "question_analysis_v1",
    "version": "v1",
    "system": (
        "你是题目知识点分析器。将题目解剖为 知识点树（core/prerequisite/method/extension）。"
        "知识点名称必须使用提供的规范知识点词表（canonical names），不得自造新名称。"
        "严格输出 JSON，结构符合 QuestionAnalysisResult schema。"
    ),
    "output_schema": QuestionAnalysisResult,
}

PROMPTS = {p["version"]: p for p in [LESSON_SUMMARY_V1, EXERCISE_QUERY_REWRITE_V1, QUESTION_ANALYSIS_V1]}
