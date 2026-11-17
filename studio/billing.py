"""Payments with Cashfree, the same way as Commently Reviews: a monthly subscription, and one-time refill packs.

The monthly plan (Cashfree Subscriptions):
  1. The person presses Subscribe and gives their mobile number (Cashfree needs it for UPI AutoPay).
  2. We create a subscription for CREATIVECUT_PLAN_PRICE_INR a month, and Cashfree's own page sets up the mandate
     (UPI AutoPay or card, with a ₹1 check that is refunded). The first monthly charge is the next day.
  3. The plan starts as soon as the mandate is approved. Cashfree then charges every month by itself.
  4. Cashfree sends the person back to /billing/return and also tells us through the webhook. Neither is trusted
     as it stands: we always ask Cashfree for the subscription's real state before changing anything.
  5. They can cancel from Settings. What they already paid for still runs until its end.

Refill packs (Cashfree Orders), for subscribers who run out early: one-time payment, CREATIVECUT_REFILL_VIDEOS
videos for CREATIVECUT_REFILL_PRICE_INR. Counted once, when Cashfree says the order is PAID.

Settings (.env): CASHFREE_ENV (production, or anything else for the test sandbox), CASHFREE_CLIENT_ID and
CASHFREE_CLIENT_SECRET (and optionally CASHFREE_TEST_CLIENT_ID / _SECRET for the sandbox). The names may also start
with CREATIVECUT_. The secret also checks the webhook's signature. Card, UPI and bank details never reach us."""
import base64
import hashlib
import hmac
import json
import time
import traceback
import uuid
from datetime import datetime

import httpx
import sqlalchemy as sa

from . import config, ctx, db, plan

SUBS_VERSION = "2025-01-01"
ORDERS_VERSION = "2023-08-01"
GRACE = 2 * 86400            # a failed monthly charge is retried by Cashfree: the plan waits this long before it stops
MONTH = 31 * 86400
ENDED = ("CANCELLED", "CUSTOMER_CANCELLED", "EXPIRED", "COMPLETED", "LINK_EXPIRED", "CARD_EXPIRED")
SUB, ORDER = "ccs_", "cct_"   # our ids start with these, so the webhook knows what is ours


class BillingError(Exception):
    def __init__(self, msg, status=400):
        super().__init__(msg)
        self.status = status


def ready() -> bool:
    cid, secret = config.cashfree_keys()
    return bool(cid and secret)


def mode() -> str:
    return "production" if config.cashfree_live() else "sandbox"


def _base() -> str:
    return "https://api.cashfree.com/pg" if config.cashfree_live() else "https://sandbox.cashfree.com/pg"


def _call(method: str, path: str, body: dict = None, version: str = SUBS_VERSION) -> dict:
    """One call to Cashfree. Kept on its own so the tests can stand in for Cashfree."""
    cid, secret = config.cashfree_keys()
    if not cid or not secret:
        raise BillingError("Payments are not set up on this server yet.", 503)
    r = httpx.request(method, _base() + path, json=body, timeout=20, headers={
        "x-api-version": version, "x-client-id": cid, "x-client-secret": secret,
        "x-request-id": str(uuid.uuid4()), "accept": "application/json"})
    try:
        data = r.json()
    except ValueError:
        data = {}
    if r.status_code >= 300:
        print(f"Cashfree said no: {r.status_code} {data.get('code', '')} {data.get('message', '')}", flush=True)
        if r.status_code in (401, 403):        # our keys, not the buyer's fault: never show Cashfree's own words
            raise BillingError("Payments are not working for the moment. Please try again later.", 503)
        raise BillingError(data.get("message") or "The payment service said no. Please try again.", 502)
    return data


def _when(text) -> float:
    """A Cashfree date ("2026-11-18T10:00:00+05:30") as a time stamp, or 0."""
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


def _uid_from(ref: str, prefix: str):
    """The account an id of ours belongs to (ccs_<user>_<ms>), when that account exists."""
    from . import auth
    if not ref.startswith(prefix) or "_" not in ref[len(prefix):]:
        return None
    uid = ref[len(prefix):].rsplit("_", 1)[0]
    return uid if auth.get_user(uid) else None


def _phone(text) -> str:
    digits = "".join(ch for ch in str(text or "") if ch.isdigit())[-10:]
    if len(digits) != 10 or digits[0] not in "6789":
        raise BillingError("Enter a valid 10-digit Indian mobile number.")
    return digits


def _done(uid, title, body):
    try:
        from . import notices
        notices.add(uid, "account", title, body, "/app")
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    ctx.bump(uid)


# ================================================================ the monthly plan
def subscribe(user, phone) -> dict:
    """Start a subscription. Returns what the page needs to open Cashfree's checkout."""
    if not ready():
        raise BillingError("Payments are not set up on this server yet.", 503)
    s = plan.subscription(user.id)
    if plan.subscribed(user.id) and s.get("status") == "ACTIVE":
        raise BillingError("You are already subscribed.", 409)
    digits = _phone(phone)
    sub_id = f"{SUB}{user.id}_{int(time.time() * 1000)}"
    price = int(config.PLAN_PRICE_INR)
    data = _call("POST", "/subscriptions", {
        "subscription_id": sub_id,
        "customer_details": {"customer_name": (user.name or user.email.split("@")[0])[:100], "customer_email": user.email,
                             "customer_phone": digits},
        "plan_details": {"plan_name": f"Creative Cut Monthly {price}"[:40], "plan_type": "PERIODIC", "plan_amount": price,
                         "plan_max_amount": price, "plan_intervals": 1, "plan_interval_type": "MONTH", "plan_currency": "INR",
                         "plan_note": f"{config.PLAN_VIDEOS} videos a month, {config.CLIPS_PER_VIDEO} clips each"},
        # UPI AutoPay and cards only: eNACH needs a ₹0 check and days of bank approval
        "authorization_details": {"authorization_amount": 1, "authorization_amount_refund": True, "payment_methods": ["upi", "card"]},
        "subscription_meta": {"return_url": config.PUBLIC_URL + "/billing/return", "notification_channel": ["EMAIL", "SMS"]},
        # Cashfree charges UPI and cards from the next day at the earliest, and moves the date itself when it must
        "subscription_first_charge_time": datetime.fromtimestamp(time.time() + 86400).astimezone().isoformat(timespec="seconds"),
        "subscription_tags": {"user": user.id, "product": "creative_cut"},
    })
    if not data.get("subscription_session_id"):
        raise BillingError("The payment service did not open a payment page. Please try again.", 502)
    plan.update_sub(user.id, id=sub_id, status=data.get("subscription_status") or "INITIALIZED", phone=digits,
                    amount=price, videos=config.PLAN_VIDEOS)
    return {"session": data["subscription_session_id"], "mode": mode()}


def _apply(uid, status: str, next_charge=None):
    """Copy Cashfree's view of the subscription onto the person."""
    s = plan.subscription(uid)
    fields = {"status": status or s.get("status")}
    until = float(s.get("until") or 0)
    if status == "ACTIVE":
        # mandate approved: the plan runs until the next charge (and a little after, while Cashfree retries)
        nxt = _when(next_charge)
        fields["until"] = max(until, (nxt + GRACE) if nxt else time.time() + MONTH)
        fields["next"] = nxt or None
    elif status in ENDED:
        fields["ended"] = time.time()
        if not s.get("last_charge"):            # never charged: nothing paid for, so it stops now
            fields["until"] = time.time()
    plan.update_sub(uid, **fields)


def refresh(uid) -> dict:
    """Ask Cashfree for the real state of this person's subscription."""
    s = plan.subscription(uid)
    if not s.get("id"):
        return s
    data = _call("GET", "/subscriptions/" + s["id"])
    was = plan.subscribed(uid)
    _apply(uid, data.get("subscription_status"), data.get("next_schedule_date"))
    if not was and plan.subscribed(uid):
        _done(uid, "You're subscribed", f"{config.PLAN_VIDEOS} videos a month are ready for you.")
    return plan.subscription(uid)


def cancel(uid):
    s = plan.subscription(uid)
    if not s.get("id") or s.get("status") not in ("ACTIVE", "ON_HOLD", "BANK_APPROVAL_PENDING"):
        raise BillingError("There is no active subscription to cancel.")
    data = _call("POST", f"/subscriptions/{s['id']}/manage", {"subscription_id": s["id"], "action": "CANCEL"})
    _apply(uid, data.get("subscription_status") or "CANCELLED")


_tried: dict = {}


def maybe_refresh(uid) -> bool:
    """When a subscriber seems to have run out of paid time, check with Cashfree once (a charge may have been missed)."""
    s = plan.subscription(uid)
    if not s.get("id") or s.get("status") in ENDED or plan.subscribed(uid) or not ready():
        return False
    if time.time() - _tried.get(uid, 0) < 300:
        return False
    _tried[uid] = time.time()
    try:
        _charge_check(uid)
        refresh(uid)
    except (BillingError, httpx.HTTPError):
        return False
    return plan.subscribed(uid)


def _charge_check(uid):
    """Look for a monthly charge we were not told about."""
    s = plan.subscription(uid)
    data = _call("GET", f"/subscriptions/{s['id']}/payments")
    for p in data if isinstance(data, list) else []:
        if p.get("payment_type") == "CHARGE" and p.get("payment_status") == "SUCCESS":
            _charged(uid, s["id"], p)


def _charged(uid, sub_id, p: dict):
    """A monthly charge went through: one more month, logged once."""
    paid = _when(p.get("payment_initiated_date")) or time.time()
    ref = str(p.get("cf_payment_id") or p.get("payment_id") or f"{sub_id}_{int(paid)}")[:80]
    with db.engine.begin() as c:
        if c.execute(sa.select(db.payments.c.id).where(db.payments.c.id == ref)).first():
            return
        c.execute(db.payments.insert().values(id=ref, user_id=uid, kind="month", amount=int(float(p.get("payment_amount") or 0)),
                                              videos=0, status="paid", created_at=time.time(), paid_at=paid))
    s = plan.subscription(uid)
    plan.update_sub(uid, last_charge=paid, until=max(float(s.get("until") or 0), paid + MONTH + GRACE))


# ================================================================ refill packs
def refill(user) -> dict:
    if not ready():
        raise BillingError("Payments are not set up on this server yet.", 503)
    if not plan.subscribed(user.id):
        raise BillingError("Refills are for subscribers. Subscribe first: it gives you videos every month.", 403)
    order_id = f"{ORDER}{user.id}_{int(time.time() * 1000)}"
    price, videos = int(config.REFILL_PRICE_INR), int(config.REFILL_VIDEOS)
    phone = plan.subscription(user.id).get("phone") or ""
    meta = {"return_url": config.PUBLIC_URL + "/billing/return?order_id={order_id}"}
    if config.PUBLIC_URL.startswith("https://"):        # Cashfree only calls https addresses
        meta["notify_url"] = config.PUBLIC_URL + "/api/billing/webhook"
    data = _call("POST", "/orders", {
        "order_id": order_id, "order_amount": price, "order_currency": "INR",
        "customer_details": {"customer_id": user.id, "customer_name": (user.name or user.email.split("@")[0])[:100],
                             "customer_email": user.email, "customer_phone": phone if len(phone) == 10 else "9999999999"},
        "order_meta": meta, "order_note": f"Creative Cut refill: {videos} videos"[:200],
        "order_tags": {"user": user.id, "product": "creative_cut_refill"},
    }, ORDERS_VERSION)
    if not data.get("payment_session_id"):
        raise BillingError("The payment service did not open a payment page. Please try again.", 502)
    with db.engine.begin() as c:
        c.execute(db.payments.insert().values(id=order_id, user_id=user.id, kind="refill", amount=price, videos=videos,
                                              status="created", created_at=time.time()))
    return {"session": data["payment_session_id"], "mode": mode()}


def sync_order(order_id: str):
    """Ask Cashfree about a refill order. Adds its videos once, when it is PAID. Returns the buyer, or None."""
    with db.engine.connect() as c:
        row = c.execute(sa.select(db.payments).where(db.payments.c.id == order_id, db.payments.c.kind == "refill")).first()
    if not row or not row.user_id:
        return None
    if row.status == "paid":
        return row.user_id
    data = _call("GET", "/orders/" + order_id, version=ORDERS_VERSION)
    status = data.get("order_status")
    if status == "PAID" and float(data.get("order_amount") or 0) >= row.amount:
        with db.engine.begin() as c:
            won = c.execute(db.payments.update().where(db.payments.c.id == order_id, db.payments.c.status != "paid")
                            .values(status="paid", paid_at=time.time())).rowcount
            if won == 1:
                plan.add_extra(row.user_id, row.videos)     # fails: the row goes back to unpaid, so it can be tried again
        if won == 1:
            _done(row.user_id, f"{row.videos} videos added", "Your refill is ready. Thank you.")
    elif status in ("EXPIRED", "TERMINATED"):
        with db.engine.begin() as c:
            c.execute(db.payments.update().where(db.payments.c.id == order_id, db.payments.c.status == "created").values(status="failed"))
    return row.user_id


# ================================================================ Cashfree coming back to us
def came_back(params: dict):
    """The buyer's browser, sent back by Cashfree (a GET or a POSTed form). Returns the account, or None."""
    order_id = str(params.get("order_id") or "")
    if order_id.startswith(ORDER):
        return sync_order(order_id)
    sub_id = str(params.get("subscription_id") or params.get("subscriptionId") or "")
    uid = _uid_from(sub_id, SUB)
    if uid and plan.subscription(uid).get("id") == sub_id:
        refresh(uid)
        return uid
    return None


def _signed(raw: bytes, stamp: str, signature: str) -> bool:
    """Cashfree signs each webhook: base64 of HMAC-SHA256(timestamp + body) with the client secret."""
    _, secret = config.cashfree_keys()
    if not secret or not stamp or not signature:
        return False
    try:
        t = float(stamp)
    except ValueError:
        return False
    if abs(time.time() - (t / 1000 if t > 1e12 else t)) > 300:      # an old message sent again: refused
        return False
    want = base64.b64encode(hmac.new(secret.encode(), stamp.encode() + raw, hashlib.sha256).digest()).decode()
    return hmac.compare_digest(want.encode(), str(signature).encode())


def webhook(raw: bytes, stamp: str, signature: str) -> bool:
    """Cashfree telling us about a payment or a subscription. False when the signature is wrong."""
    if not _signed(raw, stamp, signature):
        return False
    try:
        evt = json.loads(raw)
        d = evt.get("data") or {}
        order_id = str((d.get("order") or {}).get("order_id") or "")
        if order_id.startswith(ORDER):
            sync_order(order_id)
            return True
        sd = d.get("subscription_details") or {}
        sub_id = str(sd.get("subscription_id") or d.get("subscription_id") or "")
        uid = _uid_from(sub_id, SUB)
        if not uid or plan.subscription(uid).get("id") != sub_id:
            return True                          # not ours, or an older subscription: nothing to do
        if evt.get("type") == "SUBSCRIPTION_PAYMENT_SUCCESS" and d.get("payment_type") == "CHARGE":
            _charged(uid, sub_id, d)
        was = plan.subscribed(uid)
        _apply(uid, sd.get("subscription_status"), sd.get("next_schedule_date"))
        if not was and plan.subscribed(uid):
            _done(uid, "You're subscribed", f"{config.PLAN_VIDEOS} videos a month are ready for you.")
    except (ValueError, TypeError, AttributeError):
        return True              # a shape we do not know: said yes so Cashfree stops sending it
    except (BillingError, httpx.HTTPError):
        traceback.print_exc()
        raise
    return True


def history(uid) -> list:
    with db.engine.connect() as c:
        return [{"t": r.paid_at, "kind": r.kind, "amount": r.amount, "videos": r.videos} for r in c.execute(
            sa.select(db.payments).where(db.payments.c.user_id == uid, db.payments.c.status == "paid")
            .order_by(db.payments.c.paid_at.desc()).limit(24))]
