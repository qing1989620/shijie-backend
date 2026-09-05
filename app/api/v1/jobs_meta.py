"""Jobs API + health + meta version."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, owner_or_404
from app.core.config import settings
from app.core.db import get_db
from app.models import AIJob, User
from app.schemas.schemas import HealthOut, JobOut, MetaVersionOut, ReadyOut

router = APIRouter(tags=["jobs", "meta"])


@router.get("/jobs/{job_id}", response_model=JobOut, operation_id="job_get")
def job_get(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = owner_or_404(db.query(AIJob).get(job_id), user.id)
    return job


@router.get("/jobs/{job_id}/events", operation_id="job_events_sse")
def job_events(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """SSE progress stream — frontend renders stage copy, never polls blindly."""
    import asyncio
    import json

    from fastapi.responses import StreamingResponse

    async def stream():
        last = None
        for _ in range(600):  # max ~5min
            job = db.query(AIJob).get(job_id)
            if job is None:
                break
            state = {"status": job.status, "progress": job.progress, "stage": job.stage}
            if state != last:
                yield f"data: {json.dumps(state, ensure_ascii=False)}\n\n"
                last = state
            if job.status in {"succeeded", "failed", "cancelled"}:
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.get("/meta/version", response_model=MetaVersionOut, operation_id="meta_version")
def meta_version():
    return MetaVersionOut(api_version="1", contract_version="1.0.0", app_env=settings.APP_ENV)


@router.get("/health", response_model=HealthOut, operation_id="health")
def health(db: Session = Depends(get_db)):
    ok = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        ok = False
    return HealthOut(status="ok" if ok else "degraded", database=ok)


@router.get("/ready", response_model=ReadyOut, operation_id="ready")
def ready(db: Session = Depends(get_db)):
    checks = {"database": False}
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        pass
    return ReadyOut(ready=all(checks.values()), checks=checks)
