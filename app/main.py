"""FastAPI application factory. Modular monolith; ASR/OCR are external runtimes."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import (
    auth,
    courses_lessons,
    exercise_search,
    jobs_meta,
    practice,
    questions,
    realtime,
    recordings_transcript,
    review,
)
from app.core.config import settings
from app.core.errors import AppError, app_error_handler, validation_error_handler
from app.observability.middleware import ErrorEnvelopeMiddleware, RequestIDMiddleware

logging.basicConfig(level=settings.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.core.db import SessionLocal
    from app.workers.runner import drain_outbox

    db = SessionLocal()
    try:
        drain_outbox(db)
    except Exception:  # pragma: no cover
        logging.getLogger("app").exception("outbox drain failed")
    finally:
        db.close()
    yield


app = FastAPI(
    title="Shijie Learning Platform API",
    version="1.0.0",
    description="课堂 → 练习 → 巩固 智能学习闭环平台后端。Contract-first; /openapi.json 是唯一机器契约。",
    openapi_url="/openapi.json",
    docs_url="/docs",
    lifespan=lifespan,
)

# NOTE: middleware added LATER wraps OUTER — CORS must be outermost so every
# response (including 4xx/5xx envelopes) carries CORS headers. Both custom
# middlewares are pure ASGI (BaseHTTPMiddleware breaks WebSocket scopes).
app.add_middleware(ErrorEnvelopeMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)


@app.get("/health", include_in_schema=False)
def health_root():
    return {"status": "ok"}


app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(auth.me_router, prefix=settings.API_V1_PREFIX)
app.include_router(courses_lessons.router, prefix=settings.API_V1_PREFIX)
app.include_router(recordings_transcript.router, prefix=settings.API_V1_PREFIX)
app.include_router(questions.router, prefix=settings.API_V1_PREFIX)
app.include_router(exercise_search.router, prefix=settings.API_V1_PREFIX)
app.include_router(practice.router, prefix=settings.API_V1_PREFIX)
app.include_router(review.router, prefix=settings.API_V1_PREFIX)
app.include_router(review.memory_router, prefix=settings.API_V1_PREFIX)
app.include_router(jobs_meta.router, prefix=settings.API_V1_PREFIX)
# WebSocket contract path is /ws/v1/... (no /api/v1 prefix, see contracts/asyncapi.yaml)
app.include_router(realtime.router, prefix=settings.API_V1_PREFIX)
app.include_router(realtime.ws_router)
