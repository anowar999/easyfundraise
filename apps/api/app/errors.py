"""RFC 9457 problem+json errors with stable codes (§18.1), and capture into the Error Center (§18.3)."""

import hashlib
import logging
import traceback
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse

from .config import get_settings
from .db import SessionLocal

log = logging.getLogger("easyfundraise")


class ApiError(Exception):
    def __init__(self, status: int, code: str, title: str, detail: str = "", extra: dict | None = None):
        self.status, self.code, self.title, self.detail, self.extra = status, code, title, detail, extra or {}


def problem(status: int, code: str, title: str, detail: str, ref: str, extra: dict | None = None) -> JSONResponse:
    body = {"type": f"https://easyfundraise.com/errors/{code}", "title": title, "status": status,
            "detail": detail, "code": code, "ref": ref, **(extra or {})}
    return JSONResponse(body, status_code=status, media_type="application/problem+json",
                        headers={"X-Correlation-Id": ref})


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return problem(exc.status, exc.code, exc.title, exc.detail, _ref(request), exc.extra)


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    ref = _ref(request)
    log.exception("unhandled error ref=%s", ref)
    try:
        record_error(exc, request.url.path, getattr(request.state, "user_email", None))
    except Exception:  # never let error capture mask the original error
        log.exception("failed to record error")
    return problem(500, "EF-SYS-001", "Something went wrong", "An unexpected error occurred.", ref)


def _ref(request: Request) -> str:
    return getattr(request.state, "ref", None) or uuid.uuid4().hex[:8]


def record_error(exc: Exception, path: str, user_email: str | None) -> None:
    from .models import EngTask, ErrorRecord

    frames = traceback.extract_tb(exc.__traceback__)
    top = frames[-1] if frames else None
    key = f"{type(exc).__name__}:{top.filename if top else ''}:{top.name if top else ''}:{path}"
    fp = hashlib.sha256(key.encode()).hexdigest()[:32]
    stack = "".join(traceback.format_exception(exc))[-8000:]
    with SessionLocal() as db:
        rec = db.get(ErrorRecord, fp)
        if rec is None:
            rec = ErrorRecord(fingerprint=fp, error_type=type(exc).__name__, message=str(exc)[:2000], path=path,
                              stack=stack, env=get_settings().env, users_affected=[])
            db.add(rec)
        else:
            rec.count += 1
            rec.message = str(exc)[:2000]
            rec.last_seen = _now()
        if user_email and user_email not in rec.users_affected:
            rec.users_affected = [*rec.users_affected, user_email]
        # Rules engine: >=3 affected users -> auto-create a bug task (§18.3)
        if rec.task_id is None and len(rec.users_affected) >= 3:
            task = EngTask(type="bug", title=f"[auto] {rec.error_type} at {path}", description=rec.message,
                           source="error", severity="medium", state="Approved")
            db.add(task)
            db.flush()
            rec.task_id, rec.status = task.id, "task_created"
        db.commit()


def _now():
    from datetime import UTC, datetime

    return datetime.now(UTC)


def not_found(what: str = "Resource") -> ApiError:
    return ApiError(404, "EF-NF-001", f"{what} not found")
