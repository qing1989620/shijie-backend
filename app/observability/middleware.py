"""Pure-ASGI middleware (BaseHTTPMiddleware breaks WebSocket scopes).

- ErrorEnvelopeMiddleware: wraps AppError/unexpected errors into the unified
  Problem-Details envelope (http scopes only; never started twice).
- RequestIDMiddleware: per-request X-Request-ID + structured access log.
"""
import logging
import time
import uuid

from starlette.datastructures import MutableHeaders

from app.core.errors import AppError, problem_response_raw

logger = logging.getLogger("app.access")


class ErrorEnvelopeMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def send_wrapper(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except AppError as exc:
            if started:
                raise
            await problem_response_raw(exc.status, exc.code, exc.detail, exc.errors)(scope, receive, send)
        except Exception:
            if started:
                raise
            logger.exception("unhandled error")
            await problem_response_raw(500, "INTERNAL_ERROR", "Unexpected server error")(scope, receive, send)


class RequestIDMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        rid = uuid.uuid4().hex[:12]
        state = scope.setdefault("state", {})
        state["request_id"] = rid
        start = time.perf_counter()

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.append("X-Request-ID", rid)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            status = None
            try:
                path = scope["path"]
                method = scope["method"]
            except KeyError:
                path = method = "?"
            logger.info("%s %s %s %.1fms rid=%s", method, path, status, (time.perf_counter() - start) * 1000, rid)
