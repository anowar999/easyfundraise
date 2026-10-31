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
        return s.ai_model_small if task == "chat" else None  # the Raise Agent works on every plan
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


def small_json(db: Session, ws: Workspace, system: str, user: str, schema: dict, max_tokens: int = 1200) -> dict | None:
    """Cheap structured call on the small model for UI helpers (search parsing). Any plan, budget permitting."""
    if not available() or not budget_left(db, ws):
        return None
    try:
        resp = client().messages.create(
            model=get_settings().ai_model_small, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": schema}})
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
        log.warning("ai small_json failed: %s", e)
        return None
    record(db, ws, resp)
    if resp.stop_reason in ("refusal", "max_tokens"):
        return None
    try:
        return json.loads(_text(resp))
    except json.JSONDecodeError:
        return None


RESEARCH_SYSTEM = """You research one startup investor on the public web for a founder who wants to pitch them.
Search their firm's website, portfolio page, recent funding news and interviews. Report only what sources say;
leave a field empty rather than guess. No personal-life details. Return ONLY a JSON object, no prose, shaped:
{"summary": "2-3 sentences: who they are and what they back",
 "thesis": "their stated investment focus, stage and cheque size if published",
 "portfolio": [{"company": "...", "note": "what it does / round, if known"}],
 "partners": [{"name": "...", "role": "..."}],
 "recent_news": [{"title": "...", "date": "YYYY-MM or YYYY-MM-DD if known", "url": "..."}],
 "pitch_angle": "one line on what to lead with when emailing them",
 "sources": ["url", ...]}"""


def research(db: Session, ws: Workspace, who: str) -> tuple[dict | None, str]:
    """Live web research with the server-side web search tool. Returns (data or None, model)."""
    if not available() or not budget_left(db, ws):
        return None, ""
    model = get_settings().ai_model_frontier
    messages: list = [{"role": "user", "content": who}]
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 6}]
    resp = None
    try:
        for _ in range(4):  # a long server-tool turn can pause; send it back to continue
            resp = client().messages.create(model=model, max_tokens=6000, system=RESEARCH_SYSTEM, tools=tools,
                                            messages=messages, output_config={"effort": "low"})
            record(db, ws, resp)
            if resp.stop_reason != "pause_turn":
                break
            messages = [*messages, {"role": "assistant", "content": resp.content}]
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
        log.warning("ai research failed: %s", e)
        return None, ""
    if resp is None or resp.stop_reason in ("refusal", "max_tokens"):
        return None, ""
    text = _text(resp)
    start, end = text.find("{"), text.rfind("}")
    try:
        data = json.loads(text[start:end + 1]) if start >= 0 else None
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict):
        return None, ""
    found = [getattr(r, "url", "") for b in resp.content if b.type == "web_search_tool_result"
             for r in (b.content if isinstance(b.content, list) else [])]
    data["sources"] = list(dict.fromkeys([*(data.get("sources") or []), *[u for u in found if u]]))[:12]
    return data, resp.model
