"""Attempt submission — the transactional bridge between Module 2 and Module 3.

One call, one transaction:
    Attempt -> grading -> UserKnowledgeMastery update -> MemoryState (FSRS)
            -> ReviewTask create/reschedule -> DomainEvent
"""
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.ai.memory_engine import MemoryEngine, MemorySnapshot
from app.core.errors import AppError
from app.models import (
    Attempt,
    DomainEvent,
    MemoryState,
    Question,
    QuestionKnowledgePoint,
    ReviewProfile,
    ReviewTask,
    User,
    UserKnowledgeMastery,
)
from app.models import (
    ReviewTask as RT,
)
from app.schemas.schemas import AttemptIn


def _grade_objective(q: Question, answer: str | None) -> bool | None:
    """Deterministic grading for objective types; None when not gradeable."""
    if answer is None or q.answer is None:
        return None
    if q.question_type in {"single_choice", "true_false"}:
        return answer.strip().lower() == q.answer.strip().lower()
    if q.question_type == "fill_blank":
        norm = lambda s: "".join(s.split()).lower()
        return norm(answer) == norm(q.answer)
    return None  # subjective -> caller/self/ai grading


def _update_mastery(db: Session, user_id: str, question: Question, correct: bool | None, now: datetime):
    kp_rows = db.query(QuestionKnowledgePoint).filter(QuestionKnowledgePoint.question_id == question.id).all()
    for row in kp_rows:
        m = (
            db.query(UserKnowledgeMastery)
            .filter(UserKnowledgeMastery.user_id == user_id, UserKnowledgeMastery.knowledge_point_id == row.knowledge_point_id)
            .first()
        )
        if m is None:
            m = UserKnowledgeMastery(user_id=user_id, knowledge_point_id=row.knowledge_point_id, mastery=0.5, status="unknown")
            db.add(m)
            db.flush()
        m.attempt_count += 1
        m.correct_count += 1 if correct else 0
        m.last_attempt_at = now
        # Product Heuristic estimate: exponential moving average on correctness (0/1),
        # unknown correctness nudges toward neutral.
        signal = {True: 1.0, False: 0.0, None: 0.5}[correct]
        m.mastery = round(max(0.0, min(1.0, 0.7 * m.mastery + 0.3 * signal)), 4)
        if m.mastery >= 0.85:
            m.status = "mastered"
        elif m.mastery < 0.4:
            m.status = "weak"
        else:
            m.status = "developing"


def _get_profile(db: Session, user_id: str) -> ReviewProfile:
    p = db.query(ReviewProfile).filter(ReviewProfile.user_id == user_id).first()
    if p is None:
        p = ReviewProfile(user_id=user_id)
        db.add(p)
        db.flush()
    return p


def submit_attempt(db: Session, user: User, body: AttemptIn, practice_set_id: str | None) -> tuple[Attempt, MemoryState | None]:
    now = datetime.now(UTC)
    question = db.query(Question).get(body.question_id)
    is_correct = body.is_correct
    grading_source = body.grading_source
    if is_correct is None and body.answer is not None:
        auto = _grade_objective(question, body.answer)
        if auto is not None:
            is_correct = auto
            grading_source = grading_source or "objective"
    if is_correct is None:
        # cannot fake correctness for subjective questions without self grading
        raise AppError("VALIDATION_ERROR", "主观题需要自评 is_correct（grading_source=self）或提交可判定的客观答案")

    attempt = Attempt(
        user_id=user.id,
        question_id=question.id,
        practice_set_id=practice_set_id,
        answer=body.answer,
        is_correct=is_correct,
        score=body.score,
        duration_ms=body.duration_ms,
        confidence=body.confidence,
        hint_count=body.hint_count,
        answer_change_count=body.answer_change_count,
        grading_source=grading_source or "objective",
        attempted_at=now,
    )
    db.add(attempt)
    db.flush()

    # 1) mastery update
    _update_mastery(db, user.id, question, is_correct, now)

    # 2) memory engine update (per user+question state, independent of others)
    profile = _get_profile(db, user.id)
    engine = MemoryEngine(target_retention=profile.target_retention)
    ms = (
        db.query(MemoryState)
        .filter(MemoryState.user_id == user.id, MemoryState.question_id == question.id)
        .first()
    )
    snapshot = MemorySnapshot(
        difficulty=ms.difficulty if ms else 5.0,
        stability=ms.stability if ms else 0.5,
        last_review_at=ms.last_review_at if ms else None,
        review_count=ms.review_count if ms else 0,
        lapse_count=ms.lapse_count if ms else 0,
    )
    rating = engine.map_rating(
        is_correct=is_correct,
        duration_ms=body.duration_ms,
        hint_count=body.hint_count,
        confidence=body.confidence,
        answer_change_count=body.answer_change_count,
    )
    outcome = engine.update(snapshot, rating, now=now)
    if ms is None:
        ms = MemoryState(user_id=user.id, question_id=question.id)
        db.add(ms)
    ms.difficulty = outcome.snapshot.difficulty
    ms.stability = outcome.snapshot.stability
    ms.retrievability = outcome.retrievability
    ms.last_review_at = outcome.snapshot.last_review_at
    ms.next_review_at = outcome.next_due_at
    ms.review_count = outcome.snapshot.review_count
    ms.lapse_count = outcome.snapshot.lapse_count
    ms.last_rating = outcome.rating
    ms.scheduler_version = outcome.snapshot.scheduler_version
    db.flush()

    # 3) review task: create first task or reschedule existing future one
    existing_task = (
        db.query(RT)
        .filter(RT.user_id == user.id, RT.question_id == question.id, RT.status.in_(["scheduled", "due", "snoozed"]))
        .order_by(RT.due_at.desc())
        .first()
    )
    if existing_task:
        existing_task.status = "scheduled"
        existing_task.due_at = outcome.next_due_at
        existing_task.memory_state_id = ms.id
        existing_task.reason = f"完成练习后按你的记忆节律重新安排（下次预计保持率约 {int(engine.target_retention*100)}%）"
        existing_task.scheduled_date = (outcome.next_due_at + timedelta(hours=8)).date().isoformat()
    else:
        # Product Planning Heuristic: a lapsed new question gets a same-day learning
        # review (~15 min), the FSRS interval then governs from that first review.
        first_due = now + timedelta(minutes=15) if outcome.rating == 1 else outcome.next_due_at
        task = ReviewTask(
            user_id=user.id,
            question_id=question.id,
            memory_state_id=ms.id,
            status="scheduled",
            due_at=first_due,
            priority_score=0.5,
            reason="第一次复习已安排：趁记忆还新鲜，今天稍后再做一次",
            estimated_minutes=3,
            scheduled_date=(first_due + timedelta(hours=8)).date().isoformat(),
        )
        db.add(task)

    db.add(DomainEvent(event_type="practice_completed", user_id=user.id,
                       payload={"question_id": question.id, "is_correct": is_correct, "rating": outcome.rating}))
    db.commit()
    return attempt, ms
