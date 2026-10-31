"""§6 billing with Stripe Checkout + Customer Portal; the webhook is the source of truth for the plan."""

import hashlib
import hmac
import json
import logging
import time
import uuid
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import Ctx, ctx
from ..errors import ApiError
from ..models import AuditLog, Notification, Subscription, Tier, Workspace, WorkspaceMember

router = APIRouter(prefix="/billing", tags=["billing"])
log = logging.getLogger("easyfundraise.billing")
STRIPE = "https://api.stripe.com/v1"


def _stripe(path: str, data: dict) -> dict:
    key = get_settings().stripe_secret_key
    if not key:
        raise ApiError(503, "EF-BILL-001", "Billing is not configured yet")
    r = httpx.post(f"{STRIPE}{path}", data=data, auth=(key, ""), timeout=20)
    if r.status_code >= 400:
        log.warning("stripe %s: %s", path, r.text[:300])
        raise ApiError(502, "EF-BILL-002", "Payment provider error", "Please try again in a minute.")
    return r.json()


@router.get("")
def billing(c: Ctx = Depends(ctx)):
    sub = c.db.get(Subscription, c.ws_id)
    tiers = c.db.scalars(select(Tier).where(Tier.visible).order_by(Tier.sort)).all()
    return {"enabled": bool(get_settings().stripe_secret_key), "current": c.workspace.tier_code,
            "subscription": {"status": sub.status, "interval": sub.interval, "tier": sub.tier_code,
                             "current_period_end": sub.current_period_end} if sub and sub.stripe_subscription_id else None,
            "tiers": [{"code": t.code, "name": t.name, "price_monthly": t.price_monthly, "price_annual": t.price_annual,
                       "purchasable": bool(t.stripe_price_monthly or t.stripe_price_annual), "limits": t.limits,
                       "features": t.features} for t in tiers if t.code != "trial"]}


class CheckoutIn(BaseModel):
    tier: str = Field(max_length=32)
    interval: str = Field("month", pattern="^(month|year)$")


@router.post("/checkout")
def checkout(body: CheckoutIn, c: Ctx = Depends(ctx)):
    if c.role != "owner":
        raise ApiError(403, "EF-AUTH-021", "Only the workspace owner can change the plan")
    t = c.db.get(Tier, body.tier)
    price = (t.stripe_price_annual if body.interval == "year" else t.stripe_price_monthly) if t else ""
    if not price:
        raise ApiError(422, "EF-BILL-003", "That plan can't be bought online yet")
    sub = c.db.get(Subscription, c.ws_id)
    origin = get_settings().web_origin
    data = {"mode": "subscription", "line_items[0][price]": price, "line_items[0][quantity]": "1",
            "success_url": f"{origin}/app/settings?billing=success", "cancel_url": f"{origin}/app/settings?billing=cancel",
            "client_reference_id": str(c.ws_id), "metadata[workspace_id]": str(c.ws_id), "metadata[tier]": t.code,
            "subscription_data[metadata][workspace_id]": str(c.ws_id), "subscription_data[metadata][tier]": t.code,
            "allow_promotion_codes": "true"}
    if sub and sub.stripe_customer_id:
        data["customer"] = sub.stripe_customer_id
    else:
        data["customer_email"] = c.user.email
    return {"url": _stripe("/checkout/sessions", data)["url"]}


@router.post("/portal")
def portal(c: Ctx = Depends(ctx)):
    sub = c.db.get(Subscription, c.ws_id)
    if not sub or not sub.stripe_customer_id:
        raise ApiError(409, "EF-BILL-004", "No subscription yet")
    return {"url": _stripe("/billing_portal/sessions", {"customer": sub.stripe_customer_id,
                                                         "return_url": f"{get_settings().web_origin}/app/settings"})["url"]}


def verify(payload: bytes, header: str, secret: str, tolerance: int = 300) -> bool:
    pairs = [p.split("=", 1) for p in header.split(",") if "=" in p]
    t = next((v for k, v in pairs if k == "t"), "")
    sig = [v for k, v in pairs if k == "v1"]
    if not t.isdigit() or abs(time.time() - int(t)) > tolerance:
        return False
    expected = hmac.new(secret.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, s) for s in sig)


def _apply_sub(db: Session, obj: dict) -> None:
    ws_id = (obj.get("metadata") or {}).get("workspace_id")
    sub = db.scalar(select(Subscription).where(or_(Subscription.stripe_subscription_id == obj["id"],
                                                   Subscription.workspace_id == uuid.UUID(ws_id) if ws_id else False)))
    if sub is None:
        if not ws_id:
            return
        sub = Subscription(workspace_id=uuid.UUID(ws_id))
        db.add(sub)
    item = ((obj.get("items") or {}).get("data") or [{}])[0]
    price = (item.get("price") or {}).get("id", "")
    t = db.scalar(select(Tier).where(or_(Tier.stripe_price_monthly == price, Tier.stripe_price_annual == price))) if price else None
    sub.stripe_subscription_id, sub.stripe_customer_id = obj["id"], obj.get("customer") or sub.stripe_customer_id
    sub.status = obj.get("status", "")
    sub.interval = ((item.get("price") or {}).get("recurring") or {}).get("interval", sub.interval)
    end = obj.get("current_period_end") or item.get("current_period_end")
    sub.current_period_end = datetime.fromtimestamp(end, UTC) if end else None
    if t:
        sub.tier_code = t.code
    ws = db.get(Workspace, sub.workspace_id)
    before = ws.tier_code
    if sub.status in ("active", "trialing", "past_due") and sub.tier_code:
        ws.tier_code = sub.tier_code
    elif sub.status in ("canceled", "unpaid", "incomplete_expired"):
        ws.tier_code, ws.trial_ends_at = "trial", datetime.now(UTC)  # back to a read-only expired trial
    if ws.tier_code != before:
        db.add(AuditLog(action="billing.tier", target=str(ws.id), before={"tier": before}, after={"tier": ws.tier_code}))


@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    secret = get_settings().stripe_webhook_secret
    payload = await request.body()
    if not secret or not verify(payload, request.headers.get("stripe-signature", ""), secret):
        raise ApiError(400, "EF-BILL-010", "Invalid signature")
    ev = json.loads(payload)
    obj = ev.get("data", {}).get("object", {})
    kind = ev.get("type", "")
    if kind == "checkout.session.completed" and obj.get("client_reference_id"):
        ws_id = uuid.UUID(obj["client_reference_id"])
        sub = db.get(Subscription, ws_id) or Subscription(workspace_id=ws_id)
        sub.stripe_customer_id = obj.get("customer") or sub.stripe_customer_id
        sub.stripe_subscription_id = obj.get("subscription") or sub.stripe_subscription_id
        sub.tier_code = (obj.get("metadata") or {}).get("tier", sub.tier_code)
        db.merge(sub)
    elif kind.startswith("customer.subscription."):
        _apply_sub(db, obj)
    elif kind == "invoice.payment_failed":
        sub = db.scalar(select(Subscription).where(Subscription.stripe_customer_id == obj.get("customer", "")))
        if sub:
            owner = db.scalar(select(WorkspaceMember.user_id).where(WorkspaceMember.workspace_id == sub.workspace_id,
                                                                    WorkspaceMember.role == "owner"))
            if owner:
                db.add(Notification(workspace_id=sub.workspace_id, user_id=owner, kind="billing",
                                    title="Payment failed", body="Update your card to keep your plan.", link="/app/settings"))
    db.commit()
    return {"received": True}
