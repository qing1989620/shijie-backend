"""Practice sets + attempts. Attempt submission atomically drives Module 3.

The frontend submits ONLY an Attempt; mastery update, MemoryState update and
ReviewTask scheduling all happen inside one backend transaction
(practice_service.submit_attempt) — never split across multiple API calls.
"""
import random

from fastapi import APIRouter, Depends
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.ai.memory_engine import retrievability as calc_r
from app.api.deps import get_current_user, owner_or_404
from app.core.db import get_db
from app.core.errors import AppError
from app.models import (
    Attempt,
    MemoryState,
    PracticeSet,
    PracticeSetItem,
    Question,
    QuestionKnowledgePoint,
    User,
    UserKnowledgeMastery,
    UserQuestion,
)
from app.schemas.schemas import AttemptIn, AttemptOut, PracticeSetCreateIn, PracticeSetOut

router = APIRouter(tags=["practice"])


@router.post("/practice-sets", response_model=PracticeSetOut, status_code=201, operation_id="practice_set_create")
def practice_set_create(body: PracticeSetCreateIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # candidate pool: questions related to this user (own + favorites) or global bank
    q = (
        db.query(Question)
        .outerjoin(UserQuestion, (UserQuestion.question_id == Question.id) & (UserQuestion.user_id == user.id))
        .filter(Question.deleted_at.is_(None), or_(Question.is_global.is_(True), UserQuestion.id.isnot(None)))
    )
    if body.subject:
        q = q.filter(Question.subject == body.subject)
    if body.difficulty:
        q = q.filter(Question.difficulty == body.difficulty)
    if body.favorite_only:
        q = q.filter(UserQuestion.is_favorite.is_(True))
    if body.wrong_only:
        wrong = db.query(Attempt.question_id).filter(Attempt.user_id == user.id, Attempt.is_correct.is_(False))
        q = q.filter(Question.id.in_(wrong))
    if body.knowledge_point_ids:
        q = q.join(QuestionKnowledgePoint).filter(
            QuestionKnowledgePoint.knowledge_point_id.in_(body.knowledge_point_ids)
        )
    candidates = q.distinct().all()
    if not candidates:
        raise AppError("CONFLICT", "没有符合筛选条件的题目，先收藏或导入一些题目吧。")

    if body.mode == "smart":
        # Product Heuristic weighting: mistakes, weak knowledge points, low memory retention, never practiced
        scored = []
        for cand in candidates:
            w = 1.0
            last_wrong = (
                db.query(Attempt)
                .filter(Attempt.user_id == user.id, Attempt.question_id == cand.id, Attempt.is_correct.is_(False))
                .order_by(Attempt.attempted_at.desc())
                .first()
            )
            if last_wrong:
                w += 1.5
            ms = db.query(MemoryState).filter(MemoryState.user_id == user.id, MemoryState.question_id == cand.id).first()
            if ms and ms.last_review_at:
                r = calc_r(_now_utc(), ms.last_review_at, ms.stability)
                w += 2.0 * (1 - r)
            else:
                w += 0.8  # never practiced -> moderate boost
            kp_ids = [
                row[0]
                for row in db.query(QuestionKnowledgePoint.knowledge_point_id).filter(
                    QuestionKnowledgePoint.question_id == cand.id
                )
            ]
            if kp_ids:
                weak = (
                    db.query(UserKnowledgeMastery)
                    .filter(UserKnowledgeMastery.user_id == user.id,
                            UserKnowledgeMastery.knowledge_point_id.in_(kp_ids))
                    .all()
                )
                if weak:
                    w += 2.0 * (1 - min(m.mastery for m in weak))
            k = random.random() * 0.5  # avoid same-question starvation
            scored.append((cand, w + k))
        scored.sort(key=lambda t: t[1], reverse=True)
        picked = [c for c, _ in scored[: body.count]]
    else:
        picked = random.sample(candidates, min(body.count, len(candidates)))

    ps = PracticeSet(
        user_id=user.id,
        title=body.title or ("智能练习" if body.mode == "smart" else "随机练习"),
        mode=body.mode,
        filters=body.model_dump(exclude={"title"}),
    )
    db.add(ps)
    db.flush()
    for i, cand in enumerate(picked):
        db.add(PracticeSetItem(practice_set_id=ps.id, question_id=cand.id, position=i))
    db.commit()
    return _set_out(db, user, ps)


@router.get("/practice-sets/{set_id}", response_model=PracticeSetOut, operation_id="practice_set_get")
def practice_set_get(set_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ps = owner_or_404(db.query(PracticeSet).get(set_id), user.id)
    return _set_out(db, user, ps)


def _set_out(db: Session, user: User, ps: PracticeSet) -> PracticeSetOut:
    rows = (
        db.query(PracticeSetItem, Question)
        .join(Question, Question.id == PracticeSetItem.question_id)
        .filter(PracticeSetItem.practice_set_id == ps.id)
        .order_by(PracticeSetItem.position)
        .all()
    )
    from app.schemas.schemas import PracticeSetItemOut, QuestionDetailOut

    items = []
    for item, q in rows:
        uq = db.query(UserQuestion).filter(UserQuestion.user_id == user.id, UserQuestion.question_id == q.id).first()
        detail = QuestionDetailOut.model_validate(q)
        detail.is_favorite = bool(uq and uq.is_favorite)
        detail.origin = uq.origin if uq else None
        items.append(PracticeSetItemOut(position=item.position, question=detail))
    return PracticeSetOut(
        id=ps.id, title=ps.title, mode=ps.mode, filters=ps.filters, created_at=ps.created_at, items=items
    )


def _now_utc():
    from datetime import UTC, datetime

    return datetime.now(UTC)


@router.post("/practice-sets/{set_id}/attempts", response_model=AttemptOut, status_code=201, operation_id="attempt_create")
def attempt_create(set_id: str, body: AttemptIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ps = owner_or_404(db.query(PracticeSet).get(set_id), user.id)
    q = db.query(Question).filter(Question.id == body.question_id, Question.deleted_at.is_(None)).first()
    if not q:
        raise AppError("NOT_FOUND")
    from app.services.attempt_service import submit_attempt

    attempt, memory_state = submit_attempt(db, user, body, practice_set_id=ps.id)
    return AttemptOut(
        id=attempt.id, question_id=attempt.question_id, practice_set_id=attempt.practice_set_id,
        is_correct=attempt.is_correct, score=attempt.score, attempted_at=attempt.attempted_at,
        created_memory_state=memory_state is not None,
    )


@router.post("/attempts", response_model=AttemptOut, status_code=201, operation_id="attempt_create_standalone")
def attempt_standalone(body: AttemptIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Review-flow attempts (no practice set)."""
    q = db.query(Question).filter(Question.id == body.question_id, Question.deleted_at.is_(None)).first()
    if not q:
        raise AppError("NOT_FOUND")
    from app.services.attempt_service import submit_attempt

    attempt, memory_state = submit_attempt(db, user, body, practice_set_id=None)
    return AttemptOut(
        id=attempt.id, question_id=attempt.question_id, practice_set_id=None,
        is_correct=attempt.is_correct, score=attempt.score, attempted_at=attempt.attempted_at,
        created_memory_state=memory_state is not None,
    )
