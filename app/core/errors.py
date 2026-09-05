"""Unified error model (RFC 9457 Problem Details inspired).

Frontend must branch on `code`, never on message strings.
"""
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

ERROR_CODES = {
    "VALIDATION_ERROR": 422,
    "UNAUTHORIZED": 401,
    "FORBIDDEN": 403,
    "NOT_FOUND": 404,
    "CONFLICT": 409,
    "VERSION_CONFLICT": 409,
    "PAYLOAD_TOO_LARGE": 413,
    "UNSUPPORTED_MEDIA_TYPE": 415,
    "RATE_LIMITED": 429,
    "INTERNAL_ERROR": 500,
    "BAD_REQUEST": 400,
    "AI_JOB_FAILED": 500,
}


class AppError(Exception):
    def __init__(self, code: str, detail: str = "", errors: list | None = None):
        self.code = code
        self.status = ERROR_CODES.get(code, 400)
        self.detail = detail or code
        self.errors = errors or []
        super().__init__(self.detail)


def _jsonable(value):
    """Make FastAPI validation errors JSON-safe (they may contain raw bytes input)."""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def problem_response(
    status_code: int,
    code: str,
    detail: str,
    request: Request | None = None,
    errors: list | None = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "") if request else ""
    return JSONResponse(
        status_code=status_code,
        content={
            "type": f"https://shijie.app/errors/{code.lower()}",
            "title": code.replace("_", " ").title(),
            "status": status_code,
            "code": code,
            "detail": detail,
            "request_id": request_id,
            "errors": _jsonable(errors or []),
        },
    )


def problem_response_raw(
    status_code: int,
    code: str,
    detail: str,
    errors: list | None = None,
) -> JSONResponse:
    """Middleware variant without a Request object (request_id added upstream)."""
    return problem_response(status_code, code, detail, None, errors)


def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return problem_response(422, "VALIDATION_ERROR", "Request contains invalid data", request, exc.errors())


def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return problem_response(exc.status, exc.code, exc.detail, request, exc.errors)


STATUS = status
