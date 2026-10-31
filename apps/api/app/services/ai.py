"""§9 / §13 AI layer: one place that talks to Claude.

- Model routing by tier (COST-01): `template` tiers never call a model; `template+small` uses the small model;
  `frontier*` tiers use the frontier model for drafting, briefs and chat, and the small model for classification.
- Every call is optional: if the API key is missing, the budget is spent, or the model declines, callers get None
  and fall back to the deterministic engine. The product keeps working without AI.
- Structured JSON outputs, capped max_tokens, automatic prompt caching, per-workspace monthly token budget
  (COST-03), server-side refusal fallback on the frontier model.
"""

import json
import logging
import os
from datetime import UTC, datetime

import anthropic
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Workspace
from .entitlements import limit, tier, usage

log = logging.getLogger("easyfundraise.ai")
_client: anthropic.Anthropic | None = None

SAFETY = (
    "You work for a startup founder inside EasyFundraise. Rules that override everything else: "
    "never invent investors, deals, portfolio companies, quotes, metrics or dates; use only the facts provided; "
    "when a fact is missing, leave it out; never include personal-life details about investors; "
    "keep the founder's voice: short, specific, confident, no hype, no emoji."
)


def available() -> bool:
    s = get_settings()
    return s.ai_enabled and bool(s.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key or None, max_retries=2, timeout=120)
    return _client


def model_for(db: Session, ws: Workspace, task: str) -> str | None:
    """task: draft | brief | chat | classify | profile | polish. None = use the template engine."""
    if not available():
        return None
    engine = str(tier(db, ws).features.get("ai_engine", "template"))
    s = get_settings()
    if engine == "template":
        return None
    if engine.startswith("frontier") and task in ("draft", "brief", "chat", "profile"):
        return s.ai_model_frontier
    return s.ai_model_small


def budget_left(db: Session, ws: Workspace) -> bool:
    cap = limit(db, ws, "ai_tokens_month")
    return cap is None or usage(db, ws, "ai_tokens", datetime.now(UTC).strftime("%Y-%m")) < cap


def record(db: Session, ws: Workspace, resp) -> None:
    from .entitlements import consume

    u = getattr(resp, "usage", None)
    if u is None:
        return
    n = (u.input_tokens or 0) + (u.output_tokens or 0) + (getattr(u, "cache_creation_input_tokens", 0) or 0)
    consume(db, ws, "ai_tokens", datetime.now(UTC).strftime("%Y-%m"), None, n)


def _params(model: str, effort: str) -> dict:
    p: dict = {"model": model, "output_config": {"effort": effort}}
    if model == get_settings().ai_model_frontier:
        p.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")
    return p


def _text(resp) -> str:
    return "".join(b.text for b in resp.content if b.type == "text")


def json_call(db: Session, ws: Workspace, task: str, system: str, user: str, schema: dict,
              max_tokens: int = 4000, effort: str = "medium") -> tuple[dict | None, str]:
    """Returns (parsed JSON or None, engine label). Never raises for model-side problems."""
    model = model_for(db, ws, task)
    if model is None or not budget_left(db, ws):
        return None, "template"
    p = _params(model, effort)
    p["output_config"]["format"] = {"type": "json_schema", "schema": schema}
    try:
        resp = client().beta.messages.create(
            max_tokens=max_tokens, cache_control={"type": "ephemeral"},
            system=f"{SAFETY}\n\n{system}", messages=[{"role": "user", "content": user}], **p)
    except anthropic.APIStatusError as e:
        log.warning("ai %s failed: %s %s", task, e.status_code, getattr(e, "message", ""))
        return None, "template"
    except anthropic.APIConnectionError:
        log.warning("ai %s: connection error", task)
        return None, "template"
    record(db, ws, resp)
    if resp.stop_reason in ("refusal", "max_tokens"):
        log.info("ai %s stopped: %s", task, resp.stop_reason)
        return None, "template"
    try:
        return json.loads(_text(resp)), resp.model
    except json.JSONDecodeError:
        return None, "template"


def tool_turn(db: Session, ws: Workspace, system: str, messages: list, tools: list, max_tokens: int = 8000):
    """One Messages call for the agent chat loop (AGT-05). Returns the response or None."""
    model = model_for(db, ws, "chat")
    if model is None or not budget_left(db, ws):
        return None
    try:
        resp = client().beta.messages.create(max_tokens=max_tokens, cache_control={"type": "ephemeral"},
                                             system=f"{SAFETY}\n\n{system}", messages=messages, tools=tools,
                                             **_params(model, "medium"))
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
        log.warning("ai chat failed: %s", e)
        return None
    record(db, ws, resp)
    return resp
