"""The monthly plan and refills, paid through Cashfree: nothing is given until Cashfree itself says it is paid, a
payment counts once, it goes to the person who paid, webhooks need Cashfree's signature, and the month's videos come
back every 30 days. Cashfree is stood in for: nothing leaves this machine. Runs against the code directly with
sign-in on and its own empty data folder."""
import base64, hashlib, hmac, json, os, sys, tempfile, time
os.environ["CREATIVECUT_DATA"] = tempfile.mkdtemp(prefix="pc-bill-")
os.environ.update(DATABASE_URL="", CREATIVECUT_ACCOUNTS="1", CREATIVECUT_PUBLIC_URL="http://127.0.0.1:8765", CREATIVECUT_VERIFY_EMAIL="0",
                  CREATIVECUT_AI_KEY="", CREATIVECUT_AI_MODELS="", CREATIVECUT_FREE_VIDEOS="2", CREATIVECUT_CLIPS_PER_VIDEO="3",
                  CREATIVECUT_PLAN_PRICE_INR="499", CREATIVECUT_PLAN_VIDEOS="20", CREATIVECUT_REFILL_PRICE_INR="499",
                  CREATIVECUT_REFILL_VIDEOS="20", CREATIVECUT_PAID_REMAKES="3",
                  CREATIVECUT_CONTACT_EMAIL="help@example.com", CREATIVECUT_CONTACT_PHONE="+91 90000 00000", CREATIVECUT_CONTACT_ADDRESS="1 Test Road, Pune")
for k in ("CASHFREE_ENV", "CASHFREE_CLIENT_ID", "CASHFREE_CLIENT_SECRET", "CASHFREE_TEST_CLIENT_ID", "CASHFREE_TEST_CLIENT_SECRET"):
    os.environ.pop(k, None); os.environ.pop("CREATIVECUT_" + k, None)
sys.path.insert(0, ".")
from fastapi.testclient import TestClient
from studio import billing, config, db, plan, server
db.init()
fails = []
def check(n, got, want=True):
    ok = want(got) if callable(want) else got == want
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"   got {got!r}")); ok or fails.append(n)

BASE = "http://127.0.0.1:8765"; ORIGIN = {"Origin": BASE}
def person(email):
    c = TestClient(server.app, base_url=BASE, follow_redirects=False)
    assert c.post("/api/auth/signup", json={"email": email, "name": "P", "password": "test-pass-123"}, headers=ORIGIN).status_code == 200
    return c, c.get("/api/auth/me").json()["user"]["id"]
a, ua = person("a@example.com")
b, ub = person("b@example.com")
outside = TestClient(server.app, base_url=BASE, follow_redirects=False)      # Cashfree, or a signed-out browser

# ---- before Cashfree is set up
st = a.get("/api/status").json()["plan"]
check("a new account has its free videos", (st["limited"], st["free_left"], st["subscribed"], st["videos_left"]), (True, 2, False, 2))
check("the page is told the prices", (st["plan"], st["refill"], st["can_buy"]), ({"price": 499, "videos": 20}, {"price": 499, "videos": 20}, False))
check("subscribing without Cashfree set up says so", a.post("/api/billing/subscribe", json={"phone": "9876543210"}, headers=ORIGIN).status_code, 503)

# ---- Cashfree set up, in test mode, with the same names as Commently's settings
os.environ.update(CASHFREE_ENV="sandbox", CASHFREE_CLIENT_ID="live-id", CASHFREE_CLIENT_SECRET="live-secret",
                  CASHFREE_TEST_CLIENT_ID="test-id", CASHFREE_TEST_CLIENT_SECRET="test-secret-123")
check("test mode uses the test keys", (config.cashfree_live(), config.cashfree_keys()), (False, ("test-id", "test-secret-123")))
CF = {"subs": {}, "orders": {}, "payments": {}}
calls = []
def fake(method, path, body=None, version=billing.SUBS_VERSION):
    calls.append((method, path, body, version))
    parts = path.strip("/").split("/")
    if parts[0] == "subscriptions":
        if method == "POST" and len(parts) == 1:
            CF["subs"][body["subscription_id"]] = {"subscription_status": "INITIALIZED"}
            return {"subscription_session_id": "subs_session_" + body["subscription_id"], "subscription_status": "INITIALIZED"}
        sid = parts[1]
        if len(parts) == 3 and parts[2] == "manage":
            CF["subs"][sid]["subscription_status"] = "CANCELLED"
            return CF["subs"][sid]
        if len(parts) == 3 and parts[2] == "payments":
            return CF["payments"].get(sid, [])
        return CF["subs"][sid]
    if parts[0] == "orders":
        if method == "POST":
            CF["orders"][body["order_id"]] = {"order_status": "ACTIVE", "order_amount": body["order_amount"]}
            return {"payment_session_id": "pay_session_" + body["order_id"], "order_id": body["order_id"]}
        return CF["orders"][parts[1]]
    raise AssertionError(path)
billing._call = fake
check("the page can pay now", a.get("/api/status").json()["plan"]["can_buy"], True)

plan.add_video(ua); plan.add_video(ua)
r = a.post("/api/jobs", json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}, headers=ORIGIN)
check("after the free videos, a new video asks them to subscribe", (r.status_code, "Subscribe" in r.json()["detail"], "₹499 a month" in r.json()["detail"]), (402, True, True))
check("a refill needs a subscription first", a.post("/api/billing/refill", headers=ORIGIN).status_code, 403)
check("a bad mobile number is refused", a.post("/api/billing/subscribe", json={"phone": "12345"}, headers=ORIGIN).status_code, 400)
check("subscribing is refused from another website", a.post("/api/billing/subscribe", json={"phone": "9876543210"}, headers={"Origin": "https://evil.example"}).status_code, 403)

r = a.post("/api/billing/subscribe", json={"phone": "+91 98765 43210"}, headers=ORIGIN)
check("subscribing opens Cashfree's checkout, in test mode", (r.status_code, r.json()["mode"], r.json()["session"].startswith("subs_session_ccs_" + ua)), (200, "sandbox", True))
body = calls[-1][2]
sub_id = body["subscription_id"]
check("...₹499 every month", (body["plan_details"]["plan_amount"], body["plan_details"]["plan_interval_type"], body["plan_details"]["plan_type"]), (499, "MONTH", "PERIODIC"))
check("...UPI AutoPay or card, ₹1 check refunded", (body["authorization_details"]["payment_methods"], body["authorization_details"]["authorization_amount"], body["authorization_details"]["authorization_amount_refund"]), (["upi", "card"], 1, True))
check("...the mobile number cleaned up", body["customer_details"]["customer_phone"], "9876543210")
check("...and it comes back to us", body["subscription_meta"]["return_url"], BASE + "/billing/return")
check("nothing is given before the mandate is approved", (plan.subscribed(ua), plan.paid_left(ua)), (False, 0))

# the buyer comes back before approving: still nothing
r = outside.post("/billing/return", data={"subscription_id": sub_id}, headers={"Origin": "https://payments.cashfree.com"})
check("Cashfree's posted form back is let in", r.status_code, 303)
check("...but a subscription not approved gives nothing", (r.headers["location"], plan.subscribed(ua)), ("/app?billing=1", False))
# approved
tomorrow = time.strftime("%Y-%m-%dT%H:%M:%S+05:30", time.localtime(time.time() + 86400))
CF["subs"][sub_id] = {"subscription_status": "ACTIVE", "next_schedule_date": tomorrow}
r = outside.post("/billing/return", data={"subscription_id": sub_id, "subscription_status": "ACTIVE"}, headers={"Origin": "https://payments.cashfree.com"})
check("once Cashfree says ACTIVE, the plan starts", (r.headers["location"], plan.subscribed(ua), plan.paid_left(ua)), ("/app?billing=1", True, 20))
check("someone else's subscription id gives them nothing", (outside.post("/billing/return", data={"subscription_id": f"ccs_{ub}_1"}).headers["location"], plan.subscribed(ub)), ("/app?billing=0", False))
check("a made-up id that points outside the data folder is ignored", outside.get("/billing/return", params={"subscription_id": "ccs_../../x_1"}).headers["location"], "/app?billing=0")

st = a.get("/api/status").json()["plan"]
check("the page shows the plan", (st["subscribed"], st["videos_left"], st["month_left"], st["status"]), (True, 20, 20, "ACTIVE"))
check("subscribers get more re-makes", (st["remakes_limit"], plan.remakes_left({"remakes": 1}, server.auth.get_user(ua), ua)), (3, 2))
check("subscribing twice is refused", a.post("/api/billing/subscribe", json={"phone": "9876543210"}, headers=ORIGIN).status_code, 409)

# ---- using the month's videos, then a refill
for _ in range(20):
    plan.add_video(ua)
check("each finished video uses one of the month's", plan.paid_left(ua), 0)
r = a.post("/api/jobs", json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}, headers=ORIGIN)
check("then a new video offers a refill", (r.status_code, "refill" in r.json()["detail"]), (402, True))
r = a.post("/api/billing/refill", headers=ORIGIN)
order_id = calls[-1][2]["order_id"]
check("a refill opens Cashfree's checkout for ₹499", (r.status_code, calls[-1][2]["order_amount"], calls[-1][3]), (200, 499, billing.ORDERS_VERSION))
check("...using their mobile number", calls[-1][2]["customer_details"]["customer_phone"], "9876543210")
check("an unpaid order adds nothing", (a.get("/billing/return", params={"order_id": order_id}).status_code, plan.paid_left(ua)), (303, 0))
CF["orders"][order_id]["order_status"] = "PAID"
a.get("/billing/return", params={"order_id": order_id})
check("a paid order adds the refill", plan.paid_left(ua), 20)
a.get("/billing/return", params={"order_id": order_id})
check("coming back twice counts it once", plan.paid_left(ua), 20)
plan.add_video(ua)
check("a refill video is used after the month's", (plan.paid_left(ua), plan._read(ua)["extra"]), (19, 19))

# ---- webhooks
def hook(evt, secret="test-secret-123", stamp=None):
    raw = json.dumps(evt).encode()
    ts = stamp or str(int(time.time() * 1000))
    sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + raw, hashlib.sha256).digest()).decode()
    return outside.post("/api/billing/webhook", content=raw, headers={"x-webhook-timestamp": ts, "x-webhook-signature": sig})
next_month = time.strftime("%Y-%m-%dT%H:%M:%S+05:30", time.localtime(time.time() + 31 * 86400))
charge = {"type": "SUBSCRIPTION_PAYMENT_SUCCESS", "data": {"payment_type": "CHARGE", "cf_payment_id": "cfpay_1", "payment_amount": 499,
          "payment_initiated_date": time.strftime("%Y-%m-%dT%H:%M:%S+05:30"),
          "subscription_details": {"subscription_id": sub_id, "subscription_status": "ACTIVE", "next_schedule_date": next_month}}}
check("a webhook with a made-up signature is refused", hook(charge, secret="nope").status_code, 401)
check("an old webhook sent again is refused", hook(charge, stamp=str(int((time.time() - 3600) * 1000))).status_code, 401)
before = plan.subscription(ua)["until"]
check("a monthly charge is accepted", hook(charge).status_code, 200)
check("...and pays for about another month", plan.subscription(ua)["until"] - time.time() > 30 * 86400, True)
hook(charge)
with db.engine.connect() as c:
    n = c.execute(db.payments.select().where(db.payments.c.kind == "month")).fetchall()
check("the same charge sent twice is logged once", (len(n), n[0].amount), (1, 499))

b.post("/api/billing/subscribe", json={"phone": "9123456789"}, headers=ORIGIN)
sub_b = calls[-1][2]["subscription_id"]
act = {"type": "SUBSCRIPTION_STATUS_CHANGED", "data": {"subscription_details": {"subscription_id": sub_b, "subscription_status": "ACTIVE", "next_schedule_date": tomorrow}}}
hook(act)
check("the webhook alone starts a plan, for its own buyer", (plan.subscribed(ub), plan.subscribed(ua), plan.paid_left(ub)), (True, True, 20))
r = hook({"type": "PAYMENT_SUCCESS_WEBHOOK", "data": {"order": {"order_id": "cct_" + ub + "_123"}}})
check("a refill webhook for an order we never made adds nothing", (r.status_code, plan._read(ub).get("extra", 0)), (200, 0))

# ---- a new month, cancelling, and running out
d = plan._read(ua); d["sub"]["anchor"] = time.time() - 31 * 86400; plan._write(ua, d)
check("every 30 days the month's videos come back (refills kept)", plan.paid_left(ua), 20 + 19)
r = b.post("/api/billing/cancel", headers=ORIGIN)
check("cancelling before the first charge ends the plan at once", (r.status_code, plan.subscribed(ub)), (200, False))
check("...and the page says cancelled", r.json()["plan"]["cancelled"], True)
check("cancelling again says there is nothing to cancel", b.post("/api/billing/cancel", headers=ORIGIN).status_code, 400)
a.post("/api/billing/cancel", headers=ORIGIN)
check("cancelling after a charge keeps the paid month", (plan.subscribed(ua), plan.subscription(ua)["status"]), (True, "CANCELLED"))
d = plan._read(ua); d["sub"]["until"] = time.time() - 1; plan._write(ua, d)
check("when the paid time is over, nothing is left (refills wait)", (plan.paid_left(ua), plan._read(ua)["extra"]), (0, 19))

# ---- a charge Cashfree did not tell us about is found when the person runs out
c2, uc = person("c@example.com")
c2.post("/api/billing/subscribe", json={"phone": "9000000001"}, headers=ORIGIN)
sub_c = calls[-1][2]["subscription_id"]
CF["subs"][sub_c] = {"subscription_status": "ACTIVE", "next_schedule_date": next_month}
plan.update_sub(uc, status="ACTIVE", until=time.time() - 1, last_charge=time.time() - 40 * 86400)
CF["payments"][sub_c] = [{"payment_type": "CHARGE", "payment_status": "SUCCESS", "cf_payment_id": "cfpay_missed", "payment_amount": 499,
                          "payment_initiated_date": time.strftime("%Y-%m-%dT%H:%M:%S+05:30")}]
plan.add_video(uc); plan.add_video(uc)
check("a missed charge is found the moment it matters", (billing.maybe_refresh(uc), plan.paid_left(uc)), (True, 20))

# ---- the pages a payment provider's review looks for: public, with the price and a way to reach us
for path, words in (("/refunds", ["Refunds and Cancellations", "Cancel subscription", "₹499 a month", "₹499 for 20", "5 to 7 working days", "help@example.com"]),
                    ("/contact", ["Contact Us", "help@example.com", "+91 90000 00000", "1 Test Road, Pune", "2 working days"]),
                    ("/terms", ["Subscription, refills, payments and refunds", "/refunds"])):
    r = outside.get(path)
    check(f"{path} opens without signing in", r.status_code, 200)
    check(f"{path} says what a reviewer looks for", [w for w in words if w not in r.text], [])
    check(f"{path} has no empty placeholders", "{{" in r.text, False)
check("the front page links to all of them", [h for h in ("/terms", "/refunds", "/contact", "/privacy") if f'href="{h}"' not in outside.get("/").text], [])
check("they are in the sitemap", [h for h in ("/refunds", "/contact") if h not in outside.get("/sitemap.xml").text], [])

print("\nALL PASSED" if not fails else f"\nFAILED: {', '.join(fails)}")
db.engine.dispose()
sys.exit(1 if fails else 0)
