"""Review module: profile (onboarding), today's tasks, calendar, complete/skip/snooze,
memory state & forecast. The planner runs per request over due+upcoming tasks."""
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.ai.memory_engine import MemoryEngine, MemorySnapshot
from app.ai.memory_engine import retrievability as calc_r
from app.ai.review_planner import CandidateTask, PlanContext, plan_today
from app.api.deps import get_current_user, owner_or_404
from app.core.db import get_db
from app.core.errors import AppError
from app.models import (
    DomainEvent,
    MemoryState,
    Question,
    QuestionKnowledgePoint,
    ReviewLog,
    ReviewProfile,
    ReviewTask,
    User,
    UserKnowledgeMastery,
)
from app.schemas.schemas import (
    AttemptIn,
    MemoryForecastOut,
    MemoryStateOut,
    ReviewCalendarDay,
    ReviewProfileIn,
    ReviewProfileOut,
    ReviewTaskDetailOut,
    ReviewTaskOut,
)
from app.services import attempt_service

router = APIRouter(prefix="/review", tags=["review"])
# memory-state endpoints live at the contract path /questions/{id}/... (no /review prefix)
memory_router = APIRouter(tags=["memory"])

USER_TZ_OFFSET_HOURS = 8  # Asia/Shanghai; profile.timezone honored in production deployment


def _local_date(dt: datetime) -> date:
    return (dt + timedelta(hours=USER_TZ_OFFSET_HOURS)).date()


# ---------------------------------------------------------------- profile


@router.get("/profile", response_model=ReviewProfileOut, operation_id="review_profile_get")
def profile_get(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.query(ReviewProfile).filter(ReviewProfile.user_id == user.id).first()
    if not p:
        p = ReviewProfile(user_id=user.id)
        db.add(p)
        db.commit()
    return p


@router.put("/profile", response_model=ReviewProfileOut, operation_id="review_profile_update")
def profile_update(body: ReviewProfileIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.query(ReviewProfile).filter(ReviewProfile.user_id == user.id).first()
    if not p:
        p = ReviewProfile(user_id=user.id)
        db.add(p)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    p.onboarded = True
    db.commit()
    return p


# ---------------------------------------------------------------- tasks


def _retrievability_of(db: Session, user_id: str, question_id: str, now: datetime) -> tuple[float, MemoryState | None]:
    ms = db.query(MemoryState).filter(MemoryState.user_id == user_id, MemoryState.question_id == question_id).first()
    if not ms or not ms.last_review_at:
        return 0.0, ms
    return calc_r(now, ms.last_review_at, ms.stability), ms


def _weakness_of(db: Session, user_id: str, question_id: str) -> float:
    kp_rows = db.query(QuestionKnowledgePoint).filter(QuestionKnowledgePoint.question_id == question_id).all()
    if not kp_rows:
        return 0.5
    vals = []
    for row in kp_rows:
        m = db.query(UserKnowledgeMastery).filter(
            UserKnowledgeMastery.user_id == user_id, UserKnowledgeMastery.knowledge_point_id == row.knowledge_point_id
        ).first()
        vals.append(m.mastery if m else 0.5)
    return sum(vals) / len(vals)


@router.get("/tasks", response_model=list[ReviewTaskDetailOut], operation_id="review_tasks_today")
def review_tasks(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    day: str | None = Query(default=None, description="YYYY-MM-DD; default today (user-local)"),
    limit: int = Query(default=50, le=200),
):
    now = datetime.now(UTC)
    profile = db.query(ReviewProfile).filter(ReviewProfile.user_id == user.id).first()
    target_day = date.fromisoformat(day) if day else _local_date(now)

    # candidate tasks: due/overdue/scheduled for this day + snoozed overdue ones
    day_start = datetime.combine(target_day, datetime.min.time()) - timedelta(hours=USER_TZ_OFFSET_HOURS)
    day_end = day_start + timedelta(days=1)
    rows = (
        db.query(ReviewTask)
        .filter(
            ReviewTask.user_id == user.id,
            ReviewTask.status.in_(["scheduled", "due", "snoozed"]),
            ReviewTask.due_at < day_end,
        )
        .order_by(ReviewTask.due_at)
        .limit(300)
        .all()
    )
    # planner (Product Heuristic) — pack into available minutes, sort by priority
    candidates = []
    for t in rows:
        r, ms = _retrievability_of(db, user.id, t.question_id, now)
        weakness = 1.0 - _weakness_of(db, user.id, t.question_id)
        candidates.append(CandidateTask(
            question_id=t.question_id,
            memory_state_id=t.memory_state_id,
            retrievability=r,
            knowledge_mastery=1 - weakness,
            importance=0.5,
            due_at=t.due_at,
            estimated_minutes=t.estimated_minutes,
            stability=ms.stability if ms else 0.5,
        ))
    ctx = PlanContext(
        now=now,
        available_minutes=profile.daily_minutes if profile else 20,
        exam_date=profile.exam_date if profile else None,
    )
    planned = {c.question_id: (score, reason) for c, score, reason in plan_today(candidates, ctx)}
    # base reason from task if planner didn't include it
    out = []
    for t in rows[:limit]:
        score, reason = planned.get(t.question_id, (t.priority_score, t.reason))
        r, ms = _retrievability_of(db, user.id, t.question_id, now)
        q = db.query(Question).filter(Question.id == t.question_id, Question.deleted_at.is_(None)).first()
        out.append(ReviewTaskDetailOut(
            id=t.id, question_id=t.question_id, status=t.status, due_at=t.due_at,
            priority_score=score, reason=t.reason or reason, estimated_minutes=t.estimated_minutes,
            scheduled_date=t.scheduled_date, question=q,
            retrievability=round(r, 3) if t.status != "completed" else None,
            last_rating=ms.last_rating if ms else None,
        ))
    out.sort(key=lambda x: x.priority_score, reverse=True)
    return out


@router.get("/calendar", response_model=list[ReviewCalendarDay], operation_id="review_calendar")
def review_calendar(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    days: int = Query(default=30, le=62),
):
    now = datetime.now(UTC)
    start = (_local_date(now) - timedelta(days=7))
    start_utc = datetime.combine(start, datetime.min.time()) - timedelta(hours=USER_TZ_OFFSET_HOURS)
    rows = (
        db.query(ReviewTask)
        .filter(ReviewTask.user_id == user.id, ReviewTask.status.in_(["scheduled", "due", "snoozed"]),
                ReviewTask.due_at >= start_utc)
        .order_by(ReviewTask.due_at)
        .limit(600)
        .all()
    )
    by_day: dict[str, list[ReviewTask]] = {}
    for t in rows:
        d = _local_date(t.due_at).isoformat()
        by_day.setdefault(d, []).append(t)
    out = []
    for i in range(days):
        d = (start + timedelta(days=i)).isoformat()
        tasks = by_day.get(d, [])
        out.append(ReviewCalendarDay(date=d, count=len(tasks), items=[ReviewTaskOut.model_validate(t) for t in tasks[:8]]))
    return out


@router.get("/tasks/{task_id}", response_model=ReviewTaskDetailOut, operation_id="review_task_get")
def review_task_get(task_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    t = owner_or_404(db.query(ReviewTask).get(task_id), user.id)
    r, ms = _retrievability_of(db, user.id, t.question_id, datetime.now(UTC))
    q = db.query(Question).filter(Question.id == t.question_id).first()
    return ReviewTaskDetailOut(
        id=t.id, question_id=t.question_id, status=t.status, due_at=t.due_at,
        priority_score=t.priority_score, reason=t.reason, estimated_minutes=t.estimated_minutes,
        scheduled_date=t.scheduled_date, question=q, retrievability=round(r, 3),
        last_rating=ms.last_rating if ms else None,
    )


@router.post("/tasks/{task_id}/complete", response_model=dict, operation_id="review_task_complete")
def review_task_complete(task_id: str, body: AttemptIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Complete review with an attempt -> ReviewLog + MemoryState update + next task."""
    t = owner_or_404(db.query(ReviewTask).get(task_id), user.id)
    if t.status == "completed":
        raise AppError("CONFLICT", "task already completed")
    t.status = "completed"  # close the old task BEFORE submitting, so submit_attempt schedules the next one
    t.completed_at = datetime.now(UTC)
    db.commit()
    attempt, ms = attempt_service.submit_attempt(db, user, body, practice_set_id=None)
    attempt.review_task_id = t.id
    db.add(ReviewLog(
        user_id=user.id, review_task_id=t.id, question_id=t.question_id, action="complete",
        rating=ms.last_rating if ms else None, attempt_id=attempt.id,
        elapsed_ms=body.duration_ms, scheduler_version=ms.scheduler_version if ms else None,
    ))
    db.add(DomainEvent(event_type="review_completed", user_id=user.id, payload={"task_id": t.id}))
    db.commit()
    # next review task was created/rescheduled by submit_attempt
    next_task = (
        db.query(ReviewTask)
        .filter(ReviewTask.user_id == user.id, ReviewTask.question_id == t.question_id,
                ReviewTask.status.in_(["scheduled", "due"]))
        .order_by(ReviewTask.due_at)
        .first()
    )
    return {"ok": True, "attempt_id": attempt.id,
            "next_review_at": str(next_task.due_at) if next_task else None}


@router.post("/tasks/{task_id}/skip", response_model=dict, operation_id="review_task_skip")
def review_task_skip(task_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Skip != correct. Memory state untouched; planner reschedules later today/tomorrow."""
    t = owner_or_404(db.query(ReviewTask).get(task_id), user.id)
    if t.status == "completed":
        raise AppError("CONFLICT", "task already completed")
    t.status = "skipped"
    now = datetime.now(UTC)
    new_task = ReviewTask(
        user_id=user.id, question_id=t.question_id, memory_state_id=t.memory_state_id,
        status="scheduled", due_at=now + timedelta(days=1), priority_score=t.priority_score * 0.9,
        reason="你跳过了上次复习，我们把它安排在今天之后", estimated_minutes=t.estimated_minutes,
        scheduled_date=_local_date(now + timedelta(days=1)).isoformat(),
    )
    db.add(new_task)
    db.add(ReviewLog(user_id=user.id, review_task_id=t.id, question_id=t.question_id, action="skip"))
    db.commit()
    return {"ok": True, "rescheduled_to": str(new_task.due_at)}


@router.post("/tasks/{task_id}/snooze", response_model=dict, operation_id="review_task_snooze")
def review_task_snooze(task_id: str, hours: int = Query(default=8, le=72), db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    t = owner_or_404(db.query(ReviewTask).get(task_id), user.id)
    t.status = "snoozed"
    t.due_at = datetime.now(UTC) + timedelta(hours=hours)
    t.scheduled_date = _local_date(t.due_at).isoformat()
    db.add(ReviewLog(user_id=user.id, review_task_id=t.id, question_id=t.question_id, action="snooze"))
    db.commit()
    return {"ok": True, "due_at": str(t.due_at)}


@router.post("/tasks/{task_id}/mastered", response_model=dict, operation_id="review_task_mastered")
def review_task_mastered(task_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """'已掌握' suspends the question (lower frequency), never deletes — restorable."""
    t = owner_or_404(db.query(ReviewTask).get(task_id), user.id)
    t.status = "cancelled"
    ms = db.query(MemoryState).filter(MemoryState.user_id == user.id, MemoryState.question_id == t.question_id).first()
    if ms:
        ms.suspended = True
        ms.stability = max(ms.stability, 120.0)  # long interval, not deletion
        ms.next_review_at = datetime.now(UTC) + timedelta(days=120)
    db.add(ReviewLog(user_id=user.id, review_task_id=t.id, question_id=t.question_id, action="complete", rating=4))
    return {"ok": True, "note": "已降低复习频率（未删除），可在题目详情恢复。"}


# ---------------------------------------------------------------- memory state


@memory_router.get("/questions/{question_id}/memory-state", response_model=MemoryStateOut, operation_id="memory_state_get")
def memory_state_get(question_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ms = db.query(MemoryState).filter(MemoryState.user_id == user.id, MemoryState.question_id == question_id).first()
    if not ms:
        raise AppError("NOT_FOUND", "还没有该题的记忆状态（先完成一次作答）")
    r = calc_r(datetime.now(UTC), ms.last_review_at, ms.stability) if ms.last_review_at else None
    return MemoryStateOut(
        question_id=ms.question_id, difficulty=round(ms.difficulty, 3), stability=round(ms.stability, 3),
        retrievability=round(r, 4) if r is not None else None, last_review_at=ms.last_review_at,
        next_review_at=ms.next_review_at, review_count=ms.review_count, lapse_count=ms.lapse_count,
        scheduler_version=ms.scheduler_version,
    )


@memory_router.get("/questions/{question_id}/memory-forecast", response_model=MemoryForecastOut, operation_id="memory_forecast_get")
def memory_forecast_get(question_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ms = db.query(MemoryState).filter(MemoryState.user_id == user.id, MemoryState.question_id == question_id).first()
    if not ms:
        raise AppError("NOT_FOUND", "还没有该题的记忆状态")
    engine = MemoryEngine()
    snapshot = MemorySnapshot(difficulty=ms.difficulty, stability=ms.stability,
                              last_review_at=ms.last_review_at, review_count=ms.review_count)
    return MemoryForecastOut(question_id=question_id, points=engine.forecast(snapshot))
