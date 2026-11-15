"""YouTube videos through the Apify actor: the run is started, waited for and fetched; one video is paid for once; the
token never shows up in an error; and Twitch/Kick or a missing token keep using yt-dlp. Apify is replaced by a fake,
so nothing leaves this machine and nothing is billed."""
import os, subprocess, sys, tempfile, threading
from pathlib import Path
tmp = Path(tempfile.mkdtemp(prefix="pc-apify-"))
os.environ["CREATIVECUT_DATA"] = str(tmp / "data")
os.environ.update(DATABASE_URL="", CREATIVECUT_ACCOUNTS="0", CREATIVECUT_AI_KEY="", CREATIVECUT_AI_MODELS="")
os.environ["CREATIVECUT_APIFY_TOKEN"] = ""; os.environ["CREATIVECUT_APIFY_TOKEN_FILE"] = ""      # a real token in .env must not leak into this test
sys.path.insert(0, ".")
import httpx
from studio import apify, config, media
fails = []
def check(n, got, want=True):
    ok = want(got) if callable(want) else got == want
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"   got {got!r}")); ok or fails.append(n)

YT, TW = "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "https://www.twitch.tv/videos/123456789"
TOKEN = "apify_api_SECRETSECRETSECRET1234"
check("no token: nothing goes through Apify", (apify.ready(), media.apify_on(YT)), (False, False))
(tmp / "tok.txt").write_text(TOKEN + "\n")
os.environ["CREATIVECUT_APIFY_TOKEN_FILE"] = str(tmp / "tok.txt"); config._kept.clear()
check("the token is read from its file", (apify.ready(), media.apify_on(YT)), (True, True))
check("only YouTube goes through Apify", (media.apify_on(TW), media.apify_on("https://youtube.com.evil.example/x")), (False, False))
check("the quality asked for is rounded down to one the actor has", [apify.quality_for(h) for h in (1080, 720, 600, 480, 200, "x")], ["1080", "720", "480", "480", "360", "720"])

# ---- a fake Apify
calls = {"start": 0, "bodies": [], "auth": set(), "mode": "ok", "polls": 0}
FILE = b"x" * 3000
def handler(req: httpx.Request):
    calls["auth"].add(req.headers.get("authorization"))
    path = req.url.path
    if req.method == "POST" and path.endswith("/runs"):
        calls["start"] += 1; calls["bodies"].append((req.url.params, req.read()))
        if calls["mode"] == "nocredit": return httpx.Response(402, json={})
        if calls["mode"] == "badtoken": return httpx.Response(401, json={})
        return httpx.Response(201, json={"data": {"id": "R1", "status": "READY", "defaultDatasetId": "D1"}})
    if path.endswith("/actor-runs/R1"):
        calls["polls"] += 1
        return httpx.Response(200, json={"data": {"id": "R1", "status": "SUCCEEDED" if calls["polls"] > 1 else "RUNNING", "defaultDatasetId": "D1"}})
    if path.endswith("/datasets/D1/items"):
        item = {"status": "failed"} if calls["mode"] == "failed" else {"status": "success", "title": "T", "uploader": "U", "duration": "19", "downloadUrl": "https://files.example/v.mp4?sig=1"}
        return httpx.Response(200, json=[item])
    if req.url.host == "files.example":
        return httpx.Response(200, content=FILE)
    return httpx.Response(404)
real_client = httpx.Client
httpx.Client = lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)
import time; real_sleep = time.sleep; time.sleep = lambda s: None

d = tmp / "a"; d.mkdir()
ticks = []
meta = apify.fetch(YT, d / "source.mp4", 1080, tick=lambda: ticks.append(1))
check("the file is fetched and the actor's facts come back", ((d / "source.mp4").read_bytes() == FILE, meta), (True, {"title": "T", "uploader": "U", "duration": 19.0}))
params, body = calls["bodies"][0]
check("the run is sent the link, no proxy, and a cost cap", (b'"residentialProxyMode":"disabled"' in body.replace(b" ", b""), float(params["maxTotalChargeUsd"]) > 0), (True, True))
check("the token is sent as a login header and never in the address", (calls["auth"] == {"Bearer " + TOKEN}), True)
check("waiting calls tick (so Cancel can stop it)", len(ticks) >= 1, True)
check("no half-finished file is left", list(d.glob("*.part")), [])

for mode, words in (("nocredit", "no credit"), ("badtoken", "refused our login"), ("failed", "could not download")):
    calls["mode"] = mode; calls["polls"] = 0
    try:
        apify.fetch(YT, d / "x.mp4"); msg = ""
    except apify.ApifyError as e:
        msg = str(e)
    check(f"{mode}: a plain message, and no token in it", (words in msg, TOKEN in msg), (True, False))
calls["mode"] = "ok"; calls["polls"] = 0

# ---- one video is paid for once, even when the audio and the video are asked for together
fetched = []
def fake_fetch(url, dest, height=720, tick=None):
    fetched.append((url, height))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10:duration=4",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=4", "-shortest", "-pix_fmt", "yuv420p", str(dest)], check=True)
    return {"title": "T", "uploader": "U", "duration": 4.0}
apify.fetch = fake_fetch
j = tmp / "job"; j.mkdir()
out = {}
t = [threading.Thread(target=lambda: out.__setitem__("a", media.download_audio(YT, j))), threading.Thread(target=lambda: out.__setitem__("v", media.download(YT, j, 720)))]
[x.start() for x in t]; [x.join() for x in t]
check("audio and video asked together: Apify is asked once", len(fetched), 1)
check("the video is source.mp4 and the audio is taken from it", (out["v"].name, out["a"].name, out["a"].stat().st_size > 0), ("source.mp4", "audio_src.m4a", True))

# ---- a remake cuts one stretch out of the whole video and leaves nothing else behind
clips = tmp / "clips"
piece = media.download_section(YT, clips, "c1.again", 1.0, 3.0, 720, exact=True)
info = media.probe(piece)
check("the stretch is cut exactly", abs(info["duration"] - 2.0) < 0.3, True)
check("only the piece is left in the folder", sorted(p.name for p in clips.iterdir()), ["c1.again.mp4"])

# ---- a refusal of the server's own look must not turn away links that go through Apify
media._yt_refused_until = 10 ** 12
try:
    media.check_youtube(YT); ok = True
except media.YouTubeBlocked:
    ok = False
check("YouTube refusing the server does not stop a link that goes through Apify", ok, True)
os.environ["CREATIVECUT_APIFY_TOKEN_FILE"] = ""; config._kept.clear()
try:
    media.check_youtube(YT); ok = False
except media.YouTubeBlocked:
    ok = True
check("without a token the pause still turns the link away", ok, True)
media._yt_refused_until = 0.0
os.environ["CREATIVECUT_APIFY_TOKEN_FILE"] = str(tmp / "tok.txt"); config._kept.clear()

# ---- where YouTube refuses the look at the video, the public embed information still gives the title
media._oembed = lambda u: {"title": "From embed", "uploader": "Chan", "duration": 0.0, "is_live": False, "thumbnail": "", "kind": "video"}
media._youtube_guard = lambda u: (_ for _ in ()).throw(media.YouTubeBlocked("blocked"))
check("info falls back to the embed information when yt-dlp is refused", media.info(YT)["title"], "From embed")
os.environ["CREATIVECUT_APIFY_TOKEN_FILE"] = ""; config._kept.clear()
try:
    media.info(YT); ok = False
except media.YouTubeBlocked:
    ok = True
check("without a token the refusal is passed on as before", ok, True)
sys.exit(1 if fails else 0)
