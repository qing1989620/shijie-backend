"""Review Planner tests (Product Heuristic layer)."""
from datetime import UTC, datetime, timedelta

from app.ai.review_planner import CandidateTask, PlanContext, plan_today, priority_score


def _cand(qid, r=0.5, due_offset_days=0, mastery=0.5, minutes=3):
    return CandidateTask(
        question_id=qid,
        memory_state_id=f"ms-{qid}",
        retrievability=r,
        knowledge_mastery=mastery,
        importance=0.5,
        due_at=datetime(2026, 1, 5, 12, 0, tzinfo=UTC) + timedelta(days=due_offset_days),
        estimated_minutes=minutes,
    )


def test_capacity_is_respected():
    ctx = PlanContext(available_minutes=20)
    cands = [_cand(f"q{i}", minutes=5) for i in range(10)]
    plan = plan_today(cands, ctx)
    assert sum(c.estimated_minutes for c, _, _ in plan) <= 20


def test_low_retrievability_gets_high_priority():
    ctx = PlanContext(available_minutes=60)
    risky = _cand("q-risky", r=0.05)
    safe = _cand("q-safe", r=0.95)
    plan = plan_today([safe, risky], ctx)
    assert plan[0][0].question_id == "q-risky"
    assert plan[0][1] > plan[1][1]


def test_overdue_penalty_applies():
    ctx = PlanContext(now=datetime(2026, 1, 5, 12, 0, tzinfo=UTC))
    overdue = _cand("q-overdue", due_offset_days=-7)
    today = _cand("q-today", due_offset_days=0)
    s_over, _ = priority_score(overdue, ctx)
    s_today, _ = priority_score(today, ctx)
    assert s_over > s_today


def test_exam_urgency_boosts_priority():
    ctx = PlanContext(now=datetime(2026, 1, 5, 12, 0, tzinfo=UTC), exam_date=datetime(2026, 1, 8, tzinfo=UTC))
    with_exam = _cand("q-exam")
    s_exam, _ = priority_score(with_exam, ctx)
    ctx2 = PlanContext(now=datetime(2026, 1, 5, 12, 0, tzinfo=UTC), exam_date=None)
    s_no, _ = priority_score(with_exam, ctx2)
    assert s_exam > s_no


def test_weak_knowledge_points_prioritized():
    ctx = PlanContext(available_minutes=60)
    weak = _cand("q-weak", mastery=0.1)
    strong = _cand("q-strong", mastery=0.95)
    plan = plan_today([strong, weak], ctx)
    assert plan[0][0].question_id == "q-weak"
