"""The line for videos: a worker kept back for short videos, the wait estimate, and listening only to the busiest parts
of a very long video. Runs against the code directly; nothing is processed."""
import os, sys, tempfile
os.environ["CREATIVECUT_DATA"] = tempfile.mkdtemp(prefix="pc-queue-")
os.environ.update(DATABASE_URL="", CREATIVECUT_ACCOUNTS="0", CREATIVECUT_AI_KEY="", CREATIVECUT_AI_MODELS="")
sys.path.insert(0, ".")
import numpy as np
from studio import brain, config, db as database, jobs, load
database.init()
fails = []
def check(n, got, want=True):
    ok = want(got) if callable(want) else got == want
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"   got {got!r}")); ok or fails.append(n)

# ---- short or long
def job(jid, minutes, **opt):
    j = {"id": jid, "user": "u", "kind": "video", "status": "queued", "duration": minutes * 60, "options": dict(opt), "clips": []}
    jobs._jobs[jid] = j
    return j
job("short", 10); job("long", 90); job("unknown", 0); job("part", 180, range_start=0, range_end=15 * 60)
S = jobs._is_short_item
check("10 minutes is short, 90 is long", (S(("job", "short", None)), S(("job", "long", None))), (True, False))
check("a length not known yet counts as long", S(("job", "unknown", None)), False)
check("only the chosen part of a long video counts", S(("job", "part", None)), True)

# ---- the lane: 4 workers, 1 kept back, so long videos may use 3
config.JOB_WORKERS, config.JOB_SHORT_RESERVED = 4, 1
load.busy = lambda: False
q = jobs._FairQueue(); q.is_short = jobs._is_short_item
def add(user, jid):
    job(jid, 90 if jid.startswith("L") else 10)
    q.put(("job", jid, None), user=user)
for i in range(5): add(f"u{i}", f"L{i}")          # five people with long videos
add("s1", "S1")                                   # then one with a short video
started = []
def go():
    q.last_start = 0                              # skip the few seconds gap between starts
    started.append(q.get()[1])
for _ in range(3): go()
check("long videos start until they fill the workers they may have", started, ["L0", "L1", "L2"])
q.last_start = 0
check("a fourth long video is held back (one worker is kept for short ones)", q._pick() is not None and q.is_short(q.lines[q._pick()][0]), True)
go()
check("the short video takes the kept worker, ahead of waiting long ones", started[-1], "S1")
q.last_start = 0
check("with all workers busy, nothing more starts", q._room(), False)
q.done("L0"); q.done("S1")
q.last_start = 0
go()
check("when a worker frees up, the next long video starts", started[-1], "L3")

# ---- one worker only: no lane, a long video can still run
config.JOB_WORKERS = 1
q2 = jobs._FairQueue(); q2.is_short = jobs._is_short_item
q2.put(("job", "long", None), user="a")
check("with a single worker a long video still starts", q2.get()[1], "long")

# ---- wait text
jobs._took.clear()
check("the estimate is given in minutes, never exact", jobs.wait_text(3).startswith(" · about ") and jobs.wait_text(3).endswith("minutes"), True)
config.JOB_WORKERS = 4
jobs._took.extend([600.0] * 5)
check("it follows how long recent videos took", (jobs.wait_text(0), jobs.wait_text(7)), (" · about 3 minutes", " · about 20 minutes"))
check("a long wait is rounded to steps of five", jobs.wait_text(11), " · about 30 minutes")

# ---- the busiest stretches of a long video
rng = np.random.default_rng(1)
db = rng.normal(-40, 1.5, 3 * 3600).astype(np.float32)                 # three hours of ordinary level
for centre in (2000, 6000, 9000):                                      # three lively moments
    db[centre - 20: centre + 20] += 18
w = brain.busy_windows(db, 3, 240)
check("three windows are picked, each four minutes", (len(w), {round(b - a) for a, b in w}), (3, {240}))
check("each lively moment is inside a picked window", all(any(a <= c <= b for a, b in w) for c in (2000, 6000, 9000)), True)
check("no two windows overlap", all(w[i][1] <= w[j][0] or w[j][1] <= w[i][0] for i in range(len(w)) for j in range(i)), True)
many = brain.busy_windows(db, 12, 240)
check("never more than asked, never outside the video", (len(many) <= 12, all(0 <= a and b <= len(db) for a, b in many)), (True, True))
check("a short recording is just returned whole", brain.busy_windows(db[:200], 5, 240), [(0.0, 200.0)])
check("a quiet empty one gives nothing", brain.busy_windows(db[:0], 5, 240), [])

# ---- the whole pipeline on a made-up long video: only a few busy stretches are listened to, and only until there are enough clips
import time, threading
from pathlib import Path
from studio import auth, ctx, media, transcribe
config.JOB_WORKERS = 2
calls = []
def fake_transcribe(audio, on_progress=None):
    calls.append(len(audio) / 16000)
    return [{"w": "word", "s": i * 0.5, "e": i * 0.5 + 0.4} for i in range(int(len(audio) / 16000 * 2))]
def fake_find(words, db, duration, title="", uploader="", max_clips=6, min_len=15, max_len=60, log=print, niche="auto"):
    return [{"start": 5.0, "end": 35.0, "score": 80, "category": "other", "hook": "", "title": "t", "description": "", "hashtags": [], "highlight_words": [], "reason": ""}][:max_clips], {"model": "m", "tokens": 1}
def run(minutes, picky_from, clips=3, old=False):
    calls.clear()
    mins = minutes
    media.info = lambda url: {"title": "A long stream", "uploader": "u", "duration": mins * 60.0, "is_live": False, "thumbnail": "", "kind": "video"}
    def fake_audio(url, d, on_progress=None):
        f = Path(d) / "audio_src.m4a"; f.write_bytes(b"x"); return f
    media.download_audio = fake_audio
    media.download = lambda url, d, height=720, on_progress=None: (Path(d) / "source.mp4")
    media.probe = lambda p: {"width": 1280, "height": 720, "duration": mins * 60.0}
    media.extract_audio = lambda src, wav: Path(wav).write_bytes(b"x")
    rng = np.random.default_rng(3)
    def fake_load(wav):
        a = (rng.normal(0, 800, mins * 60 * 16000)).astype(np.int16)
        for c in (int(mins * 60 * f) for f in (0.2, 0.5, 0.8)):          # three loud moments
            a[(c - 30) * 16000: (c + 30) * 16000] *= 6
        return a
    media.load_audio = fake_load
    media.save_thumb = lambda *a, **k: False
    transcribe.transcribe = fake_transcribe
    jobs.brain.find_clips = fake_find
    jobs.render_one = lambda job, clip, words: clip.update(status="done")
    config.PICKY_ASR_MIN = picky_from; config.PICKY_WINDOW_S = 120
    uid = auth.local_user().id if hasattr(auth.local_user(), "id") else auth.local_user()["id"]
    with ctx.as_user(uid):
        job = jobs.create({"type": "url", "url": "https://www.twitch.tv/videos/1", "name": "x"}, {"max_clips": clips}, enqueue=False)
        if old:                                   # as after a restart: transcript so far on disk, and no note of the new way
            (Path(job["dir"]) / "words.json").write_text("[]", encoding="utf-8")
            job["resume"] = True
        tok = ctx._uid.set(uid)
        try:
            jobs._run_job(job)
        finally:
            ctx._uid.reset(tok)
    return job
j = run(90, 60)
check("a 90-minute video: busiest stretches only, and it said so", (j["status"], j.get("picky")), ("done", True))
check("...only as many stretches were listened to as it took to get 3 clips", (len(calls) <= 4, sum(calls) < 90 * 60 * 0.25), (True, True))
check("...and 3 clips were made", len(j["clips"]), 3)
j = run(90, 60, old=True)
check("a video that began before this change carries on the old way when it resumes", (j.get("picky"), j["status"]), (False, "done"))
j = run(30, 0, clips=1)
check("a shorter video is still listened to in order", (j.get("picky"), j["status"]), (False, "done"))
check("...and stops listening once there are enough clips (1 wanted: not all 3 parts)", (len(j["clips"]), len(calls) <= 2), (1, True))
j = run(30, 0, clips=3)
check("...but keeps going while clips are still missing", (len(j["clips"]), len(calls)), (3, 3))
sys.exit(1 if fails else 0)
