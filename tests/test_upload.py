"""When a link cannot be downloaded, the person uploads the video themselves: only for their own failed link, only a
real video, never bigger than the limit; the same video then starts again from the file, and the file is deleted once
its clips are cut. Runs against the code directly with sign-in on and its own empty data folder."""
import os, subprocess, sys, tempfile
from pathlib import Path
os.environ["CREATIVECUT_DATA"] = tempfile.mkdtemp(prefix="pc-up-")
os.environ.update(DATABASE_URL="", CREATIVECUT_ACCOUNTS="1", CREATIVECUT_PUBLIC_URL="http://127.0.0.1:8765", CREATIVECUT_VERIFY_EMAIL="0",
                  CREATIVECUT_AI_KEY="", CREATIVECUT_AI_MODELS="")
sys.path.insert(0, ".")
from fastapi.testclient import TestClient
from studio import config, ctx, db, jobs, server
db.init()
fails = []
def check(n, got, want=True):
    ok = want(got) if callable(want) else got == want
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"   got {got!r}")); ok or fails.append(n)

BASE = "http://127.0.0.1:8765"; ORIGIN = {"Origin": BASE}
queued = []
jobs.enqueue = lambda job: queued.append(job["id"])          # nothing is really processed here

def user(email):
    c = TestClient(server.app, base_url=BASE, follow_redirects=False)
    assert c.post("/api/auth/signup", json={"email": email, "name": "U", "password": "test-pass-123"}, headers=ORIGIN).status_code == 200
    return c, c.get("/api/auth/me").json()["user"]["id"]
a, uid = user("a@example.com")
b, _ = user("b@example.com")

def failed_job(uid, error="The video service could not download this video."):
    with ctx.as_user(uid):
        job = jobs.create({"type": "url", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "name": "x"}, {}, enqueue=False)
    job.update(status="error", error=error, title="A video")
    return job

mp4 = Path(tempfile.mkdtemp()) / "v.mp4"
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10:duration=3",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-shortest", "-pix_fmt", "yuv420p", str(mp4)], check=True)
data = mp4.read_bytes()
import urllib.parse
def piece(c, jid, body, offset, name="my video.mp4"):
    return c.post(f"/api/jobs/{jid}/upload", content=body, headers={**ORIGIN, "X-Filename": urllib.parse.quote(name), "X-Offset": str(offset)})
def finish(c, jid, name="my video.mp4"):
    return c.post(f"/api/jobs/{jid}/upload/finish", headers={**ORIGIN, "X-Filename": urllib.parse.quote(name)})
def whole(c, jid, body=data, size=2000, name="my video.mp4"):
    """What the page does: pieces in order, then finish."""
    off = 0
    while off < len(body):
        r = piece(c, jid, body[off: off + size], off, name)
        if r.status_code != 200: return r
        off = r.json()["received"]
    return finish(c, jid, name)

j = failed_job(uid)
check("someone else's video is not found", piece(b, j["id"], data[:100], 0).status_code, 404)
ok_job = failed_job(uid); ok_job["status"] = "done"
check("a video that did not fail cannot take an upload", piece(a, ok_job["id"], data[:100], 0).status_code, 400)
check("only video file types are taken", (piece(a, j["id"], data[:100], 0, "notes.txt").status_code, j["status"]), (400, "error"))

# ---- pieces
r = piece(a, j["id"], data[:2000], 0)
check("the first piece is taken and counted", (r.status_code, r.json()), (200, {"received": 2000}))
r = piece(a, j["id"], data[4000:6000], 4000)
check("a piece that skips ahead is refused, with where to carry on from", (r.status_code, r.json()["received"]), (409, 2000))
r = piece(a, j["id"], data[2000:4000], 2000)
check("the next piece carries on", r.json(), {"received": 4000})
r = piece(a, j["id"], data[2000:4000], 2000)
check("a piece sent again (after a dropped connection) replaces itself, nothing doubles", (r.json(), (Path(j["dir"]) / "upload.part").stat().st_size), ({"received": 4000}, 4000))
config.UPLOAD_CHUNK_MB = 1
check("a single piece bigger than the piece size is refused at the door", piece(a, j["id"], b"x" * (10 * 1024 * 1024), 4000).status_code, 413)
config.UPLOAD_CHUNK_MB = 40
config.MAX_UPLOAD_MB = 1
r = piece(a, j["id"], b"x" * (1024 * 1024 + 10), 0)
check("pieces that add up to more than the limit are refused and not kept", (r.status_code, (Path(j["dir"]) / "upload.part").exists()), (413, False))
config.MAX_UPLOAD_MB = 500

# ---- finishing
bad = failed_job(uid)
r = whole(a, bad["id"], body=b"this is not a video" * 200)
check("a file that is not a video is refused and not kept", (r.status_code, list(Path(bad["dir"]).glob("upload.*"))), (400, []))
r = whole(a, j["id"])
check("a real video, sent in pieces, is accepted", r.status_code, 200)
check("the same video starts again from the file", (j["status"], j["source"]["type"], Path(j["source"]["path"]).is_file(), j["error"], queued[-1] == j["id"]), ("queued", "file", True, None, True))
check("the file is whole and no piece file is left", (Path(j["source"]["path"]).read_bytes() == data, list(Path(j["dir"]).glob("upload.part"))), (True, []))
check("the link is remembered", j["source"]["from_url"].startswith("https://www.youtube.com/"), True)
check("a second upload on a video that is no longer failed is refused", piece(a, j["id"], data[:100], 0).status_code, 400)

# ---- YouTube refusing the server: the link is still accepted, already failed, so its card offers the upload
from studio import media
j["status"] = "done"                        # the earlier video is finished, so the one-at-a-time limit is free
media._yt_refused_until = 10 ** 12
media._PREVIEWS.clear()
real_info, real_oembed = media.info, media._oembed
media.info = lambda url: (_ for _ in ()).throw(media.YouTubeBlocked(media.YT_BLOCKED_VIDEO))
media._oembed = lambda url: {"title": "From embed", "uploader": "Chan", "duration": 0.0, "is_live": False, "thumbnail": "", "kind": "video"}
pv = a_prev = media.preview("https://www.youtube.com/watch?v=aaaaaaaaaaa")
check("while YouTube refuses the server, a link still gets its title for the page", pv["title"], "From embed")
r = a.post("/api/jobs", json={"url": "https://www.youtube.com/watch?v=aaaaaaaaaaa"}, headers=ORIGIN)
check("the link is accepted, as an already-failed video (not turned away)", (r.status_code, r.json().get("status")), (200, "error"))
check("...with the message that points to uploading", "upload it here" in (r.json().get("error") or ""), True)
nid = r.json()["id"]
check("...and that video can take the upload", whole(a, nid).status_code, 200)
media._yt_refused_until = 0.0
media.info, media._oembed = real_info, real_oembed

# ---- other requests are still cut off at the small size
big = a.post("/api/jobs", content=b"x" * (300 * 1024), headers={**ORIGIN, "Content-Type": "application/json"})
check("every other request is still capped at 256 KB", big.status_code, 413)

# ---- the uploaded file is deleted once the clips are cut
f = Path(j["source"]["path"]); j["source_path"] = str(f)
jobs._drop_source(j)
check("the uploaded video is deleted when the clips are made", f.exists(), False)
sys.exit(1 if fails else 0)
