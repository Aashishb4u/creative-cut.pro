"""The free plan and the video flow around it: clips per video, free videos per account, one video at a time,
cancelling, the hook when there is no AI, and what counts against a person's space. Runs against the code
directly with sign-in on, with its own empty data folder and no network."""
import os, sys, tempfile, time
from pathlib import Path
os.environ["CREATIVECUT_DATA"] = tempfile.mkdtemp(prefix="pc-plan-")
os.environ.update(DATABASE_URL="", CREATIVECUT_ACCOUNTS="1", CREATIVECUT_PUBLIC_URL="http://127.0.0.1:8765", CREATIVECUT_VERIFY_EMAIL="0",
                  CREATIVECUT_AI_KEY="", CREATIVECUT_AI_MODELS="", CREATIVECUT_FREE_VIDEOS="2", CREATIVECUT_CLIPS_PER_VIDEO="3")
for k in ("CREATIVECUT_MAX_JOBS_PER_USER",):
    os.environ.pop(k, None)
sys.path.insert(0, ".")
import numpy as np
from fastapi.testclient import TestClient
from studio import auth, brain, config, ctx, db, jobs, plan, server, storage
db.init()
fails = []
def check(n, got, want=True):
    ok = want(got) if callable(want) else got == want
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"   got {got!r}")); ok or fails.append(n)

BASE = "http://127.0.0.1:8765"; ORIGIN = {"Origin": BASE}
c = TestClient(server.app, base_url=BASE, follow_redirects=False)
assert c.post("/api/auth/signup", json={"email": "f@example.com", "name": "Free", "password": "test-pass-123"}, headers=ORIGIN).status_code == 200
uid = c.get("/api/auth/me").json()["user"]["id"]

# ---- the two settings
check("clips per video comes from the setting", (config.CLIPS_PER_VIDEO, jobs.DEFAULTS["max_clips"]), (3, 3))
check("asking for more clips than that is held to it", jobs.clean_options({"max_clips": 20})["max_clips"], 3)
st = c.get("/api/status").json()["plan"]
check("the page is told the plan", (st["clips_per_video"], st["videos_limit"], st["videos_used"]), (3, 2, 0))
check("one video at a time", config.MAX_ACTIVE_JOBS_PER_USER, 1)

# ---- free videos per account: only finished videos count
plan.add_video(uid); plan.add_video(uid)
r = c.post("/api/jobs", json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}, headers=ORIGIN)
check("after the free videos, a new one is refused with the paid-plan message", (r.status_code, "paid plan" in r.json()["detail"]), (402, True))
admin = auth.get_user(uid); admin_like = type("U", (), {"is_admin": True})()
check("an admin is never limited", plan.videos_left(uid, admin_like), None)
check("with no limit set, nobody is limited", (setattr(config, "FREE_VIDEOS", 10 ** 7) or plan.videos_left(uid, admin)), None)
config.FREE_VIDEOS = 2

# ---- cancelling
with ctx.as_user(uid):
    job = jobs.create({"type": "url", "url": "https://www.youtube.com/watch?v=aaaaaaaaaaa", "name": "x"}, {}, enqueue=False)
    check("a video waiting counts as in progress", jobs.busy_count(), 1)
    r = c.post("/api/jobs", json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}, headers=ORIGIN)
    plan_ok = True
    check("a second video is refused while one is being made", r.status_code in (402, 429), True)
    check("cancel stops it", jobs.cancel(job["id"]), True)
    check("its slot is free at once", (jobs.busy_count(), jobs.get(job["id"])["status"]), (0, "cancelled"))
    check("a cancelled video cannot be cancelled again", jobs.cancel(job["id"]), False)
    try:
        jobs._set(job, progress=0.5)
        check("work on a cancelled video stops at its next step", False)
    except jobs.Cancelled:
        check("work on a cancelled video stops at its next step", True)
    clip = {"id": "clip01", "status": "queued"}
    jobs.render_one(job, clip, [])
    check("its waiting clips are not made", clip["status"], "error")
r = c.post("/api/jobs/nope12345678/cancel", headers=ORIGIN)
check("cancelling something that does not exist", r.status_code, 404)

# ---- re-making a clip after changes: once for a free account
admin_like = type("U", (), {"is_admin": True})()
check("a new clip has its free re-make", plan.remakes_left({}, admin), 1)
check("after one re-make there are none left", plan.remakes_left({"remakes": 1}, admin), 0)
check("an admin is never limited on re-makes", plan.remakes_left({"remakes": 9}, admin_like), None)
check("the page is told how many re-makes", c.get("/api/status").json()["plan"]["remakes_limit"], 1)
with ctx.as_user(uid):
    j2 = jobs.create({"type": "url", "url": "https://www.youtube.com/watch?v=bbbbbbbbbbb", "name": "y"}, {}, enqueue=False)
    j2.update(status="done", duration=100, width=1280, height=720)
    (Path(j2["dir"]) / "words.json").write_text("[]")
    j2["clips"] = [{"id": "clip01", "status": "done", "start": 10.0, "end": 30.0, "style": "bounce", "layout": "blur", "hook": "", "title": "t", "description": "", "score": 50}]
    jobs.save(j2)
r = c.post(f"/api/jobs/{j2['id']}/clips/clip01/render", json={"title": "New title"}, headers=ORIGIN)
check("the first re-make is accepted", r.status_code, 200)
clip = j2["clips"][0]        # the same dict the server changed
check("...and counted", (clip["remakes"], clip.get("pending_remake")), (1, True))
clip["status"] = "done"
r = c.post(f"/api/jobs/{j2['id']}/clips/clip01/render", json={"title": "Again"}, headers=ORIGIN)
check("a second re-make is refused with the paid-plan message", (r.status_code, "paid plan" in r.json()["detail"]), (402, True))
clip["status"] = "error"; clip["remakes"] = 1
with ctx.as_user(uid):
    jobs.render_one(j2, clip, [])
check("a re-make that fails gives the free one back", clip["remakes"], 0)

# ---- the hook when there is no AI: the clip's own words, never a fixed phrase
words = [{"w": w, "s": 10 + i * 0.5, "e": 10.4 + i * 0.5} for i, w in enumerate("you will not believe what happened next".split())]
picks = brain.fallback_by_loudness(np.array([0.0] * 9 + [9.0] + [0.0] * 30), words, 1, 30, 40.0)
check("no AI: no hook is drawn on the clip", picks[0]["hook"], "")
check("...and the title says where the moment is", picks[0]["title"], lambda t: t.startswith("Moment at "))

# ---- space: the download a video is working on does not count, the clips do
d = config.user_dir(uid) / "jobs" / "j1" / "clips"; d.mkdir(parents=True)
(d.parent / "source.mp4").write_bytes(b"x" * 3_000_000)
(d.parent / "audio_src.m4a").write_bytes(b"x" * 500_000)
(d / "clip01.mp4").write_bytes(b"x" * 1_000_000)
check("only the finished clip counts against the space", 900_000 < storage.used(uid) < 1_200_000, True)

print("\nALL PASSED" if not fails else f"\nFAILED: {', '.join(fails)}")
db.engine.dispose()
sys.exit(1 if fails else 0)
