"""Bring your own key: every person has their own AI service, model and key, kept apart from everyone else's.
Runs with sign-in on, with its own empty data folder and the network replaced."""
import json, os, sys, tempfile, shutil
os.environ["CREATIVECUT_DATA"] = tempfile.mkdtemp(prefix="pc-aiu-")
os.environ.update(DATABASE_URL="", CREATIVECUT_ACCOUNTS="1", CREATIVECUT_PUBLIC_URL="http://127.0.0.1:8765", CREATIVECUT_VERIFY_EMAIL="0",
                  CREATIVECUT_AI_PROVIDER="gemini", CREATIVECUT_AI_MODELS="server-model", CREATIVECUT_AI_KEY="server-key-1234567890",
                  CREATIVECUT_AI_KEY_FILE="", CREATIVECUT_AI_BASE_URL="")
os.environ.pop("CREATIVECUT_SHARED_AI", None)
sys.path.insert(0, ".")
from fastapi.testclient import TestClient
from studio import ai, auth, config, ctx, db, server
db.init()
fails = []
BASE = "http://127.0.0.1:8765"; ORIGIN = {"Origin": BASE}
def check(n, got, want=True):
    ok = want(got) if callable(want) else got == want
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"   got {got!r}")); ok or fails.append(n)

def person(email):
    c = TestClient(server.app, base_url=BASE, follow_redirects=False)
    r = c.post("/api/auth/signup", json={"email": email, "name": email.split("@")[0], "password": "test-pass-123"}, headers=ORIGIN)
    assert r.status_code == 200, r.text
    return c
A, B = person("ann@example.com"), person("bob@example.com")
KA, KB = "ann-key-abcdefgh12345678", "bob-key-zyxwvuts87654321"

check("sign-in site: the owner's key is not shared by default", config.SHARED_AI, False)
check("a new person has no AI until they add a key", (A.get("/api/ai").json()["ready"], A.get("/api/status").json()["ai"]["ready"]), (False, False))
check("any signed-in person (not only an admin) can open the AI settings", A.get("/api/ai").status_code, 200)
check("a signed-out visitor cannot", TestClient(server.app, base_url=BASE, follow_redirects=False).get("/api/ai").status_code, 401)
check("the suggested models are listed for each service", [p["suggested"][:1] for p in A.get("/api/ai").json()["providers"][:2]], [["gemini-2.5-flash"], ["gpt-4o-mini"]])

r = A.put("/api/ai", json={"provider": "gemini", "models": "gemini-2.5-pro", "key": KA}, headers=ORIGIN)
check("Ann saves Gemini with the Pro model and her key", (r.status_code, r.json()["ready"], r.json()["models"], r.json()["key_hint"]), (200, True, ["gemini-2.5-pro"], "5678"))
r = B.put("/api/ai", json={"provider": "openai", "models": "gpt-4o-mini", "key": KB}, headers=ORIGIN)
check("Bob saves OpenAI with his key", (r.status_code, r.json()["provider"], r.json()["ready"]), (200, "openai", True))
check("Ann still sees her own settings, not Bob's", (A.get("/api/ai").json()["provider"], A.get("/api/ai").json()["models"]), ("gemini", ["gemini-2.5-pro"]))
check("neither key is ever sent to a page", KA in A.get("/api/ai").text or KB in A.get("/api/ai").text or KA in B.get("/api/ai").text or KB in B.get("/api/ai").text, False)
check("each key sits in its own person's folder", sorted(json.loads(f.read_text())["key"] for f in config.USERS_DIR.glob("*/ai.json")), sorted([KA, KB]))
uids = {n: c.get("/api/auth/me").json()["user"]["id"] for n, c in (("a", A), ("b", B))}
with ctx.as_user(uids["a"]):
    seen_a = (ai.key(), ai.models(), ai.provider(), ai.ready())
with ctx.as_user(uids["b"]):
    seen_b = (ai.key(), ai.models(), ai.provider(), ai.ready())
check("work done for Ann uses Ann's key and model", seen_a, (KA, ["gemini-2.5-pro"], "gemini", True))
check("work done for Bob uses Bob's key and model", seen_b, (KB, ["gpt-4o-mini"], "openai", True))

C = person("cy@example.com")
check("a third person with no key gets no AI, never Ann's or Bob's or the server's", (C.get("/api/status").json()["ai"]["ready"], C.get("/api/ai").json()["source"]), (False, "none"))
with ctx.as_user(C.get("/api/auth/me").json()["user"]["id"]):
    check("...and the AI key in use is empty", ai.key(), "")

# the test and the model list use the caller's own key
seen = []
class Reply:
    def __init__(self, s, d): self.status_code, self._d, self.text = s, d, json.dumps(d)
    def json(self): return self._d
def fake_post(url, json=None, headers=None, timeout=None):
    seen.append((url, headers or {}))
    return Reply(200, {"candidates": [{"content": {"parts": [{"text": '["ok"]'}]}}], "usageMetadata": {"promptTokenCount": 1, "totalTokenCount": 2}})
ai.httpx.post = fake_post
check("Ann's test goes to Gemini with Ann's key", (A.post("/api/ai/test", headers=ORIGIN).status_code, seen[-1][1].get("x-goog-api-key")), (200, KA))
def fake_openai(url, json=None, headers=None, timeout=None):
    seen.append((url, headers or {}))
    return Reply(200, {"choices": [{"message": {"content": '{"items": ["ok"]}'}}], "usage": {"prompt_tokens": 1, "completion_tokens": 1}})
ai.httpx.post = fake_openai
check("Bob's test goes to OpenAI with Bob's key", (B.post("/api/ai/test", headers=ORIGIN).status_code, "openai" in seen[-1][0], seen[-1][1].get("Authorization")), (200, True, "Bearer " + KB))
check("a person with no key cannot run the test", C.post("/api/ai/test", headers=ORIGIN).status_code, 400)
check("another website cannot change a key", A.put("/api/ai", json={"provider": "gemini", "models": "m", "key": KA}, headers={"Origin": "https://evil.example"}).status_code, 403)

# removing a key
r = A.delete("/api/ai", headers=ORIGIN)
check("Ann removes her key: she has no AI again, Bob is untouched", (r.json()["ready"], B.get("/api/ai").json()["ready"]), (False, True))

# sharing the server's key is an explicit choice
config.SHARED_AI = True
with ctx.as_user(C.get("/api/auth/me").json()["user"]["id"]):
    check("with CREATIVECUT_SHARED_AI=1 a person without a key uses the server's", (ai.key(), ai.models(), ai.ready()), ("server-key-1234567890", ["server-model"], True))
with ctx.as_user(uids["b"]):
    check("...but a person's own key still wins", ai.key(), KB)
config.SHARED_AI = False

print("\nALL PASSED" if not fails else f"\nFAILED: {', '.join(fails)}")
db.engine.dispose(); shutil.rmtree(os.environ["CREATIVECUT_DATA"], ignore_errors=True)
sys.exit(1 if fails else 0)
