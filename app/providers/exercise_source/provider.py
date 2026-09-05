"""ExerciseSourceProvider protocol + LocalQuestionBankProvider.

强约束：本 Provider 只能 SEARCH / RETRIEVE 真实题目，绝不生成题目。
检索不到时上层必须如实显示"没有找到足够相关的练习"。
"""
from typing import Protocol

from sqlalchemy.orm import Session

from app.ai.retrievers.lexical import lexical_score
from app.models import Question


class ExerciseSourceProvider(Protocol):
    name: str

    def search(
        self,
        db: Session,
        user_id: str,
        keywords: list[str],
        subject: str | None = None,
        grade: str | None = None,
        difficulty_hint: int | None = None,
        limit: int = 12,
    ) -> list[tuple[Question, float]]: ...


class LocalQuestionBankProvider:
    """Searches (a) the seeded global bank and (b) the user's own questions.

    Scoring: lexical similarity over stem/keywords + difficulty closeness.
    License note: the seed bank under scripts/seed_questions.json is authored
    for this project (CC0), sources recorded in question_sources.
    """

    name = "local_bank"

    def search(
        self,
        db: Session,
        user_id: str,
        keywords: list[str],
        subject: str | None = None,
        grade: str | None = None,
        difficulty_hint: int | None = None,
        limit: int = 12,
    ) -> list[tuple[Question, float]]:
        query = " ".join(k for k in keywords if k)
        if not query:
            return []
        candidates = db.query(Question).filter(Question.deleted_at.is_(None)).all()
        # batch-load knowledge point names for scoring (they are the strongest signal)
        from app.models import KnowledgePoint, QuestionKnowledgePoint

        kp_rows = (
            db.query(QuestionKnowledgePoint.question_id, KnowledgePoint.name)
            .join(KnowledgePoint, KnowledgePoint.id == QuestionKnowledgePoint.knowledge_point_id)
            .all()
        )
        kp_names: dict[str, list[str]] = {}
        for qid, name in kp_rows:
            kp_names.setdefault(qid, []).append(name)
        scored: list[tuple[Question, float]] = []
        for q in candidates:
            if subject and q.subject and q.subject != subject:
                continue
            if grade and q.grade and q.grade != grade:
                continue
            if not (q.is_global or q.owner_user_id == user_id):
                continue
            names = kp_names.get(q.id, [])
            fields = [q.stem] + [o.get("text", "") if isinstance(o, dict) else str(o or "") for o in (q.options or [])]
            if q.solution:
                fields.append(q.solution)
            fields.extend(names)
            base = 0.0
            for k in keywords:
                if not k:
                    continue
                for f in fields:
                    if not f:
                        continue
                    if k in f or (f in k and len(f) >= 4):
                        base = max(base, 0.8)
                        continue
                    base = max(base, lexical_score(k, f))
            base = max(base, lexical_score(" ".join(keywords), q.stem))
            if difficulty_hint and q.difficulty:
                diff_score = 1.0 - min(abs(q.difficulty - difficulty_hint) / 4.0, 1.0)
                base = 0.7 * base + 0.3 * diff_score
            if base > 0.25:
                scored.append((q, round(base, 4)))
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored[:limit]


_exercise_source: ExerciseSourceProvider | None = None


def get_exercise_source() -> ExerciseSourceProvider:
    global _exercise_source
    if _exercise_source is None:

        # more providers (open dataset / external search) plug in here
        _exercise_source = LocalQuestionBankProvider()
    return _exercise_source
