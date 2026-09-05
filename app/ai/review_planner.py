"""Review Planner — Layer 2: "what should this user review today, and in what order?"

Product Planning Heuristic layer (NOT science): combines Memory Engine risk with
knowledge weakness, exam urgency, question importance and overdue penalties into
a priority score, then packs tasks into the user's available daily minutes.

The FSRS part lives in app/ai/memory_engine.py and is clearly labelled Memory
Model; everything here is labelled Product Heuristic and must stay swappable.
"""
from dataclasses import dataclass, field
from datetime import UTC, datetime

WEIGHTS = {
    "memory_risk": 0.40,      # 1 - retrievability
    "knowledge_weakness": 0.20,
    "exam_urgency": 0.20,
    "question_importance": 0.10,
    "overdue": 0.10,
}


@dataclass
class CandidateTask:
    question_id: str
    memory_state_id: str
    retrievability: float          # from Memory Engine
    knowledge_mastery: float       # 0..1, mean over the question's knowledge points (0.5 unknown)
    importance: float              # knowledge point importance mean (0.5 default)
    due_at: datetime
    estimated_minutes: int = 3
    stability: float = 0.5


@dataclass
class PlanContext:
    now: datetime = field(default_factory=lambda: datetime.now(UTC))
    available_minutes: int = 20
    exam_date: datetime | None = None
    max_capacity: int = 100


def _memory_risk(r: float) -> float:
    return 1.0 - r


def _exam_urgency(due_at: datetime, exam_date: datetime | None, now: datetime) -> float:
    """Product Heuristic: rises as exam approaches; 0 when no exam is set."""
    if exam_date is None:
        return 0.0
    days = max(0.0, (exam_date - now).total_seconds() / 86400.0)
    if days <= 3:
        return 1.0
    if days <= 14:
        return 0.7
    if days <= 30:
        return 0.4
    return 0.15


def _overdue_penalty(due_at: datetime, now: datetime) -> float:
    overdue_days = max(0.0, (now - due_at).total_seconds() / 86400.0)
    return min(1.0, overdue_days / 7.0)


def priority_score(task: CandidateTask, ctx: PlanContext) -> tuple[float, str]:
    risk = _memory_risk(task.retrievability)
    weakness = 1.0 - task.knowledge_mastery
    urgency = _exam_urgency(task.due_at, ctx.exam_date, ctx.now)
    overdue = _overdue_penalty(task.due_at, ctx.now)
    score = (
        WEIGHTS["memory_risk"] * risk
        + WEIGHTS["knowledge_weakness"] * weakness
        + WEIGHTS["exam_urgency"] * urgency
        + WEIGHTS["question_importance"] * task.importance
        + WEIGHTS["overdue"] * overdue
    )
    # reason string: dominant factor, for UI copy "为什么今天复习"
    factors = {
        "记忆保持率已接近遗忘阈值": risk,
        "对应知识点较薄弱": weakness,
        "考试临近": urgency,
        "任务已逾期": overdue,
    }
    reason = max(factors, key=factors.get) if max(factors.values()) > 0.15 else "按你的记忆节律安排"
    return round(score, 4), reason


def plan_today(candidates: list[CandidateTask], ctx: PlanContext) -> list[tuple[CandidateTask, float, str]]:
    """Sort candidates by priority and pack into available time (Product Heuristic)."""
    scored = sorted(
        ((c, *priority_score(c, ctx)) for c in candidates), key=lambda t: t[1], reverse=True
    )
    packed: list[tuple[CandidateTask, float, str]] = []
    used = 0
    for task, score, reason in scored:
        if len(packed) >= ctx.max_capacity:
            break
        if used + task.estimated_minutes <= ctx.available_minutes:
            packed.append((task, score, reason))
            used += task.estimated_minutes
    return packed
