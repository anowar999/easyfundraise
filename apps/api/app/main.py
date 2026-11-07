import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware

from .config import get_settings
from .db import SessionLocal
from .deps import client_ip
from .errors import ApiError, api_error_handler, problem, unhandled_error_handler
from .models import AuditLog
from .routers import (
    admin,
    agent,
    auth,
    billing,
    broadcasts,
    dataroom,
    funnel,
    investors,
    nav,
    notifications,
    outreach,
    seo,
    sequences,
    shortlist,
    tasks,
    team,
    workspace,
)

logging.basicConfig(level=logging.INFO)
settings = get_settings()

app = FastAPI(title="EasyFundraise API", version="0.2.0",
              docs_url=None if settings.is_prod else "/docs", openapi_url=None if settings.is_prod else "/openapi.json")


def csrf_ok(request: Request) -> bool:
    """CSRF for cookie-authenticated state changes: require a same-origin Origin/Referer when present (§19.1)."""
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return True
    origin = request.headers.get("origin") or request.headers.get("referer") or ""
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    allowed = {settings.web_origin.rstrip("/"), f"http://{host}", f"https://{host}"}
    return not origin or any(origin == a or origin.startswith(a + "/") for a in allowed)


def record_action(request: Request, status: int) -> None:
    """Every change a signed-in user makes lands in the audit log (Admin > Audit log): who, what, when, from
    where, and whether it went through. Request bodies are not stored; the key actions add their own details."""
    route = request.scope.get("route")
    try:
        with SessionLocal() as db:
            db.add(AuditLog(actor_id=request.state.user_id, action=f"{request.method} {getattr(route, 'path', '')}"[:60],
                            target=request.url.path[:500], ip=client_ip(request),
                            after={"status": status, "workspace": str(getattr(request.state, "ws_id", "") or ""),
                                   "user_agent": request.headers.get("user-agent", "")[:300]}))
            db.commit()
    except Exception:
        logging.getLogger(__name__).exception("audit write failed")


# JSON lists (search results, tracker, outreach) shrink 5-10x on the wire; tiny responses are left alone
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.middleware("http")
async def context_and_headers(request: Request, call_next):
    request.state.ref = request.headers.get("x-correlation-id", uuid.uuid4().hex[:8])[:32]
    if not csrf_ok(request):
        return problem(403, "EF-CSRF-001", "Cross-site request blocked", "", request.state.ref)
    response = await call_next(request)
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and getattr(request.state, "user_id", None):
        await run_in_threadpool(record_action, request, response.status_code)
    response.headers.setdefault("X-Correlation-Id", request.state.ref)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "DENY"
    if request.method != "GET":
        response.headers["Cache-Control"] = "no-store"
    return response


async def validation_handler(request: Request, exc: RequestValidationError):
    errs = [{"field": ".".join(str(x) for x in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
    return problem(422, "EF-VAL-000", "Invalid input", "Check the highlighted fields.", request.state.ref,
                   {"errors": errs})


app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(RequestValidationError, validation_handler)
app.add_exception_handler(Exception, unhandled_error_handler)

for r in (auth.router, workspace.router, investors.router, investors.public, funnel.router, notifications.router,
          sequences.router, admin.router, outreach.router, outreach.public, agent.router, dataroom.router,
          dataroom.public, broadcasts.router, team.router, billing.router, seo.router, shortlist.router, tasks.router,
          nav.router):
    app.include_router(r)


@app.get("/health")
def health():
    return {"ok": True, "env": settings.env}
