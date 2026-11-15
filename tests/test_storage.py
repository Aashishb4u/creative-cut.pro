"""Each person has a fixed space. When it is full the oldest videos are deleted, newest kept, and nothing that is
still being made or has a post waiting. Runs against the code directly, with its own empty data folder."""
import os, sys, tempfile, time
from pathlib import Path
os.environ["CREATIVECUT_DATA"] = tempfile.mkdtemp(prefix="pc-sto-")
os.environ.update(DATABASE_URL="", CREATIVECUT_ACCOUNTS="0", CREATIVECUT_AI_KEY="", CREATIVECUT_AI_MODELS="")
sys.path.insert(0, ".")
from studio import auth, config, ctx, db, jobs, storage
db.init()
fails = []
def check(n, got, want=True):
    ok = want(got) if callable(want) else got == want
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"   got {got!r}")); ok or fails.append(n)

u, _ = auth._create("a@example.com", "A", password_hash="x")
v, _ = auth._create("b@example.com", "B", password_hash="x")
check("100 MB is the default", config.MAX_USER_MB, 100)
config.MAX_USER_MB = 1.0                     # one megabyte for the test

def fake_job(uid, name, mb, age, status="done", posts=None):
    d = config.user_dir(uid) / "jobs" / name
    (d / "clips").mkdir(parents=True, exist_ok=True)
    (d / "clips" / "clip01.mp4").write_bytes(b"x" * int(mb * 1_000_000))
    j = {"id": name, "user": uid, "kind": "video", "dir": str(d), "created": time.time() - age, "status": status,
         "clips": [{"id": "clip01", "status": "done", "posts": posts or {}}], "source": {"type": "url"}}
    jobs._jobs[name] = j
    jobs._by_user.setdefault(uid, {})[name] = j
    return j

old1, old2, mid, new = (fake_job(u.id, "j-old1", 0.4, 400), fake_job(u.id, "j-old2", 0.4, 300),
                        fake_job(u.id, "j-mid", 0.4, 200), fake_job(u.id, "j-new", 0.4, 10))
other = fake_job(v.id, "j-other", 0.9, 999)
used = storage.used(u.id)
check("space used is counted", 1_500_000 < used < 1_700_000, True)
check("the page is told used and limit", storage.info(u.id)["limit_mb"], 1)
gone = storage.trim(u.id, keep={"j-new"})
check("over the limit: the oldest are deleted until it fits", (gone, sorted(jobs._by_user[u.id])), (2, ["j-mid", "j-new"]))
check("their files are gone", (Path(old1["dir"]).exists(), Path(old2["dir"]).exists()), (False, False))
check("the newest is kept", Path(new["dir"]).exists(), True)
check("it now fits", storage.used(u.id) <= storage.limit_bytes(), True)
check("another person's videos are never touched", (Path(other["dir"]).exists(), "j-other" in jobs._by_user[v.id]), (True, True))
check("nothing to do when it already fits", storage.trim(u.id), 0)

# what must never be deleted
a = fake_job(u.id, "j-run", 0.6, 500, status="running")
b = fake_job(u.id, "j-post", 0.6, 450, posts={"p1": {"status": "scheduled"}})
c = fake_job(u.id, "j-fin", 0.6, 420)
gone = storage.trim(u.id, keep={"j-new"})
check("a video still being made is kept", Path(a["dir"]).exists(), True)
check("a video with a post waiting is kept", Path(b["dir"]).exists(), True)
check("an ordinary old video goes", Path(c["dir"]).exists(), False)
check("when everything left is protected, it stops instead of failing", storage.trim(u.id, keep={"j-new"}) >= 0, True)

# a newest video that alone is over the limit is still kept
config.MAX_USER_MB = 0.2
storage.trim(u.id, keep={"j-new"})
check("the video just finished is never deleted, even when it alone is too big", Path(new["dir"]).exists(), True)
config.MAX_USER_MB = 10 ** 7
check("no limit set: nothing is deleted", storage.trim(u.id), 0)
check("and the page is told there is no limit", storage.info(u.id)["limit_mb"], None)

print("\nALL PASSED" if not fails else f"\nFAILED: {', '.join(fails)}")
db.engine.dispose()
sys.exit(1 if fails else 0)
