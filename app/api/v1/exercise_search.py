"""Exercise search endpoints (lesson scope & knowledge-point scope).

Agent pipeline: understand KP -> rewrite query -> search provider -> rerank ->
persist ExerciseSearch + Results. Retrieval only — never generation.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.ai.agents.agents import ExerciseRetrievalAgentBase
from app.api.deps import get_current_user, owner_or_404
from app.core.db import get_db
from app.core.errors import AppError
from app.models import (
    DomainEvent,
    ExerciseSearch,
    ExerciseSearchResult,
    KnowledgePoint,
    Lesson,
    LessonKnowledgePoint,
    LessonSummary,
    Question,
    User,
)
from app.providers.exercise_source.provider import get_exercise_source
from app.schemas.schemas import ExerciseSearchDetailOut, ExerciseSearchResultOut

router = APIRouter(tags=["exercise-search"])


def _run_search(
    db: Session,
    user: User,
    *,
    scope: str,
    lesson: Lesson | None = None,
    kp: KnowledgePoint | None = None,
    difficulty_hint: int | None = None,
) -> ExerciseSearch:
    agent = ExerciseRetrievalAgentBase()
    # 1) gather knowledge points
    names: list[str] = []
    subject = grade = None
    if scope == "lesson" and lesson:
        subject, grade = lesson.subject, lesson.grade
        summary = db.query(LessonSummary).filter(LessonSummary.lesson_id == lesson.id).first()
        if summary and summary.payload:
            names = list(summary.payload.get("knowledge_points") or [])[:6]
        if not names:
            rows = (
                db.query(LessonKnowledgePoint, KnowledgePoint)
                .join(KnowledgePoint, KnowledgePoint.id == LessonKnowledgePoint.knowledge_point_id)
                .filter(LessonKnowledgePoint.lesson_id == lesson.id)
                .all()
            )
            names = [k.name for _, k in rows]
    elif scope == "knowledge_point" and kp:
        names = [kp.name]
        subject = kp.subject
    if not names:
        raise AppError("CONFLICT", "没有可用于检索的知识点（请先生成课堂总结）")

    # 2) query rewrite (agent, allowlisted)
    rewrite = agent.rewrite_query(db, knowledge_points=names, subject=subject, grade=grade,
                                  difficulty_hint=difficulty_hint)
    # 3) retrieval (tool: search_question_bank)
    provider = get_exercise_source()
    hits = provider.search(
        db, user.id, keywords=rewrite.keywords or names, subject=rewrite.subject,
        grade=rewrite.grade, difficulty_hint=rewrite.difficulty_hint or difficulty_hint, limit=12,
    )
    # 4) persist search + results
    search = ExerciseSearch(
        user_id=user.id, scope=scope,
        lesson_id=lesson.id if lesson else None,
        knowledge_point_id=kp.id if kp else None,
        query_payload=rewrite.model_dump(),
        status="succeeded" if hits else "succeeded_empty",
        agent=agent.agent,
        explanation=(
            f"围绕知识点「{'、'.join(names[:3])}」检索到 {len(hits)} 道相关练习。"
            if hits else "没有找到足够相关的练习。你可以稍后重试，或先收藏更多题目扩充题库。"
        ),
    )
    db.add(search)
    db.flush()
    for _rank, (q, score) in enumerate(hits):
        band = "basic" if q.difficulty <= 2 else ("advanced" if q.difficulty >= 4 else "same_level")
        reason = f"涉及知识点「{'、'.join(names[:2])}」，与本次课堂内容直接相关。" if scope == "lesson" else \
                 f"围绕「{kp.name}」的典型题目，难度{'较低' if band == 'basic' else ('较高' if band == 'advanced' else '相当')}。"
        db.add(ExerciseSearchResult(search_id=search.id, question_id=q.id, score=score, band=band,
                                    relevance_reason=reason))
    db.add(DomainEvent(
        event_type="exercise_search_completed", user_id=user.id,
        payload={"search_id": search.id, "hits": len(hits)}))
    db.commit()
    return search


@router.post("/lessons/{lesson_id}/exercise-searches", response_model=ExerciseSearchDetailOut, status_code=201,
             operation_id="lesson_exercise_search_create")
def lesson_exercise_search(lesson_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    lesson = owner_or_404(db.query(Lesson).filter(Lesson.id == lesson_id, Lesson.deleted_at.is_(None)).first(), user.id)
    search = _run_search(db, user, scope="lesson", lesson=lesson)
    return search_detail(db, user, search.id)


@router.post("/knowledge-points/{kp_id}/exercise-searches", response_model=ExerciseSearchDetailOut, status_code=201,
             operation_id="kp_exercise_search_create")
def kp_exercise_search(kp_id: str, difficulty: int | None = None, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    kp = db.query(KnowledgePoint).get(kp_id)
    if not kp:
        raise AppError("NOT_FOUND")
    search = _run_search(db, user, scope="knowledge_point", kp=kp, difficulty_hint=difficulty)
    return search_detail(db, user, search.id)


@router.get("/exercise-searches/{search_id}", response_model=ExerciseSearchDetailOut, operation_id="exercise_search_get")
def exercise_search_get(search_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return search_detail(db, user, search_id)


def search_detail(db: Session, user: User, search_id: str) -> ExerciseSearchDetailOut:
    search = owner_or_404(db.query(ExerciseSearch).get(search_id), user.id)
    rows = (
        db.query(ExerciseSearchResult, Question)
        .join(Question, Question.id == ExerciseSearchResult.question_id)
        .filter(ExerciseSearchResult.search_id == search.id, Question.deleted_at.is_(None))
        .order_by(ExerciseSearchResult.score.desc())
        .all()
    )
    from app.schemas.schemas import QuestionOut

    results = [
        ExerciseSearchResultOut(
            question=QuestionOut.model_validate(q), score=r.score, band=r.band, relevance_reason=r.relevance_reason
        )
        for r, q in rows
    ]
    return ExerciseSearchDetailOut(
        id=search.id, scope=search.scope, lesson_id=search.lesson_id,
        knowledge_point_id=search.knowledge_point_id, status=search.status,
        explanation=search.explanation, created_at=search.created_at, results=results,
    )
