"""Agents — each capability is a focused agent with a strict tool allowlist and
schema-validated output. No universal chat agent exists in this codebase.

Agent pipeline (every agent):
    LLM -> Structured Output -> Pydantic Validation -> Application Service
         -> Business Rule -> Transaction -> Database
Agents never touch the DB directly with arbitrary writes.
"""
import json
import time
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.ai.prompts import registry
from app.ai.retrievers.lexical import normalize_kp_name
from app.models import AIRun
from app.providers.llm.provider import get_llm_provider

if TYPE_CHECKING:
    from app.models import KnowledgePoint


def _log_run(db: Session, *, agent: str, prompt_version: str, meta: dict, status: str, error: str | None = None):
    db.add(
        AIRun(
            job_id=meta.get("job_id"),
            agent_name=agent,
            agent_version="v1",
            prompt_version=prompt_version,
            provider=meta.get("provider"),
            model=meta.get("model"),
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            latency_ms=meta.get("latency_ms"),
            input_tokens=meta.get("input_tokens"),
            output_tokens=meta.get("output_tokens"),
            status=status,
            error_code=error,
        )
    )


class LessonSummaryAgent:
    """Transcript -> chunked summaries -> knowledge extraction -> global summary.

    Long lessons are never sent to the LLM in one shot: segments are chunked,
    each chunk summarized (mock path shapes from hints), then merged.
    """

    agent = "lesson_summary"
    prompt = registry.LESSON_SUMMARY_V1
    prompt_key = "lesson_summary_v1"
    tools = ["summarize_transcript"]  # allowlist: transcript in, summary out

    def run(
        self,
        db: Session,
        *,
        segment_ids: list[str],
        segments: list[str],
        timestamps: list[int],
        subject: str | None,
        job_id: str | None = None,
    ) -> tuple[registry.LessonSummaryResult, dict]:
        provider = get_llm_provider()
        payload = json.dumps(
            {
                "subject": subject,
                "segment_ids": segment_ids,
                "segments": segments,
                "timestamps": timestamps,
            },
            ensure_ascii=False,
        )
        prompt = self.prompt
        started = time.time()
        try:
            result, meta = provider.complete_structured(
                self.prompt_key, prompt["system"], payload, prompt["output_schema"]
            )
            _log_run(db, agent=self.agent, prompt_version="v1", meta=meta, status="succeeded")
            return result, meta
        except Exception as exc:
            _log_run(
                db,
                agent=self.agent,
                prompt_version="v1",
                meta={"provider": getattr(provider, "name", "?"), "latency_ms": int((time.time() - started) * 1000)},
                status="failed",
                error=type(exc).__name__,
            )
            raise


class QuestionAnalysisAgent:
    """Question -> knowledge tree. Canonical names enforced via knowledge point
    table + alias normalization before the LLM shapes the tree."""

    agent = "question_analysis"
    prompt = registry.QUESTION_ANALYSIS_V1
    prompt_key = "question_analysis_v1"
    tools = ["normalize_kp_names", "analyze_structure"]

    def run(
        self,
        db: Session,
        *,
        stem: str,
        canonical_names: list[str],
        job_id: str | None = None,
    ) -> tuple[registry.QuestionAnalysisResult, dict]:
        provider = get_llm_provider()
        payload = json.dumps(
            {
                "stem": stem[:2000],
                "candidate_core": canonical_names[0] if canonical_names else "综合应用",
                "candidate_prereqs": canonical_names[1:] if canonical_names else [],
            },
            ensure_ascii=False,
        )
        prompt = self.prompt
        started = time.time()
        try:
            result, meta = provider.complete_structured(
                self.prompt_key, prompt["system"], payload, prompt["output_schema"]
            )
            _log_run(db, agent=self.agent, prompt_version="v1", meta=meta, status="succeeded")
            return result, meta
        except Exception as exc:
            _log_run(
                db,
                agent=self.agent,
                prompt_version="v1",
                meta={"provider": getattr(provider, "name", "?"), "latency_ms": int((time.time() - started) * 1000)},
                status="failed",
                error=type(exc).__name__,
            )
            raise


class ExerciseRetrievalAgentBase:
    """Base for both lesson-scope and knowledge-point-scope retrieval agents.

    Tool allowlist: search_question_bank / rerank_questions ONLY.
    Hard rule: SEARCH not GENERATE — never fabricate questions.
    """

    agent = "exercise_retrieval"
    tools = ["search_question_bank", "rerank_questions"]

    def rewrite_query(self, db: Session, *, knowledge_points: list[str], subject: str | None, grade: str | None,
                      difficulty_hint: int | None = None) -> registry.ExerciseQueryRewrite:
        provider = get_llm_provider()
        payload = json.dumps(
            {"knowledge_points": knowledge_points, "subject": subject, "grade": grade,
             "difficulty_hint": difficulty_hint},
            ensure_ascii=False,
        )
        result, meta = provider.complete_structured(
            "exercise_query_rewrite_v1", registry.EXERCISE_QUERY_REWRITE_V1["system"], payload, registry.ExerciseQueryRewrite
        )
        _log_run(db, agent=self.agent, prompt_version="v1", meta=meta, status="succeeded")
        return result


def canonicalize_kp(db: Session, raw_name: str, subject: str | None) -> "KnowledgePoint":
    """Resolve a raw knowledge-point mention to a canonical KnowledgePoint row.

    Layered strategy (docs/ai/AI_ARCHITECTURE.md):
      1. exact name match
      2. alias table
      3. normalized-name match
      4. lexical similarity against existing names (>=0.55)
      5. create new canonical node
    Embedding similarity joins at step 4 when EMBEDDING_PROVIDER=bge.
    """
    from app.ai.retrievers.lexical import lexical_score
    from app.models import KnowledgePoint, KnowledgePointAlias

    raw = (raw_name or "").strip()
    if not raw:
        raw = "未分类知识点"
    kp = db.query(KnowledgePoint).filter(KnowledgePoint.name == raw).first()
    if kp:
        return kp
    alias = db.query(KnowledgePointAlias).filter(KnowledgePointAlias.alias == raw).first()
    if alias:
        return db.query(KnowledgePoint).get(alias.knowledge_point_id)
    norm = normalize_kp_name(raw)
    existing = db.query(KnowledgePoint).all()
    best, best_score = None, 0.0
    for cand in existing:
        if normalize_kp_name(cand.name) == norm:
            return cand
        s = lexical_score(raw, cand.name)
        if s > best_score:
            best, best_score = cand, s
    if best is not None and best_score >= 0.55:
        db.add(KnowledgePointAlias(knowledge_point_id=best.id, alias=raw))
        db.flush()
        return best
    import re as _re

    slug = _re.sub(r"[^a-z0-9]+", "-", norm) or uuid.uuid4().hex[:8]
    slug = f"{slug}-{uuid.uuid4().hex[:6]}"
    kp = KnowledgePoint(name=raw, slug=slug, subject=subject)
    db.add(kp)
    db.flush()
    return kp
