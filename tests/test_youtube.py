"""Getting past YouTube refusing the server: the cookies file, the proxy, and a newer yt-dlp. Nothing leaves this
machine: pip and YouTube are replaced. Runs against the code directly, with its own empty data folder."""
import os, sys, tempfile
from pathlib import Path
tmp = Path(tempfile.mkdtemp(prefix="pc-yt-"))
os.environ["CREATIVECUT_DATA"] = str(tmp / "data")
os.environ.update(DATABASE_URL="", CREATIVECUT_ACCOUNTS="0", CREATIVECUT_AI_KEY="", CREATIVECUT_AI_MODELS="",
                  CREATIVECUT_YT_COOKIES=str(tmp / "cookies.txt"), CREATIVECUT_YT_PROXY="http://u:p@proxy.example:8080",
                  CREATIVECUT_YTDLP_UPDATE_HOURS="24")
(tmp / "cookies.txt").write_text("# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t2000000000\tSID\tabc\n")
sys.path.insert(0, ".")
from studio import config, media, ytupdate
fails = []
def check(n, got, want=True):
    ok = want(got) if callable(want) else got == want
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"   got {got!r}")); ok or fails.append(n)

YT, TW = "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "https://www.twitch.tv/videos/123456789"

# ---- cookies and proxy are for YouTube only
with media.ytdl_extra(YT) as e:
    copy = Path(e["cookiefile"])
    check("YouTube gets the cookies and the proxy", (copy.is_file(), e["proxy"]), (True, "http://u:p@proxy.example:8080"))
    check("the cookies are a private copy, never the original file", str(copy) != config.YT_COOKIES and copy.read_text() == Path(config.YT_COOKIES).read_text())
check("the copy is deleted afterwards", copy.exists(), False)
check("the original cookies file is untouched", Path(config.YT_COOKIES).is_file(), True)
with media.ytdl_extra(TW) as e:
    check("Twitch gets neither", e, {})
with media.ytdl_extra("https://youtube.com.evil.example/x") as e:
    check("a look-alike host gets neither", e, {})
os.environ["CREATIVECUT_YT_PROXY"] = ""; config._kept.clear()
with media.ytdl_extra(YT) as e:
    check("no proxy set: only the cookies", sorted(e), ["cookiefile"])
os.environ["CREATIVECUT_YT_PROXY"] = "http://u:p@proxy.example:8080"; config._kept.clear()
config.YT_COOKIES = str(tmp / "missing.txt")
with media.ytdl_extra(YT) as e:
    check("a cookies file that is not there is ignored, not an error", sorted(e), ["proxy"])
config.YT_COOKIES = str(tmp / "cookies.txt")

# ---- they reach yt-dlp, and only inside the guard
with media._youtube_guard(YT):
    y = media._ydl({})
    check("yt-dlp is given the cookies file and the proxy for a YouTube link", (y.params.get("cookiefile", "").endswith(".txt"), y.params.get("proxy")), (True, "http://u:p@proxy.example:8080"))
    seen = y.params["cookiefile"]
check("...and the private copy is gone once the download is over", Path(seen).exists(), False)
check("outside the guard yt-dlp gets neither", ("cookiefile" in media._ydl({}).params, "proxy" in media._ydl({}).params), (False, False))
with media._youtube_guard(TW):
    check("a Twitch link gets neither", ("cookiefile" in media._ydl({}).params, "proxy" in media._ydl({}).params), (False, False))

# ---- a refusal asks for a newer yt-dlp
asked = []
ytupdate.update = lambda: asked.append(1) or "x"
import threading, time
ytupdate._state.update(last=0.0, soon=0.0)
try:
    with media._youtube_guard(YT):
        raise RuntimeError("Sign in to confirm you're not a bot")
except media.YouTubeBlocked:
    pass
time.sleep(0.3)
check("YouTube refusing the server triggers a look for a newer yt-dlp", len(asked), 1)
media._yt_refused_until = 0.0
try:
    with media._youtube_guard(YT):
        raise RuntimeError("Sign in to confirm you're not a bot")
except media.YouTubeBlocked:
    pass
time.sleep(0.3)
check("...but not again straight away", len(asked), 1)
media._yt_refused_until = 0.0

# ---- the update itself, with pip replaced
import importlib
importlib.reload(ytupdate)
real_run = ytupdate.subprocess.run
def fake_pip(version, ok=True):
    def run(cmd, **kw):
        target = Path(cmd[cmd.index("--target") + 1])
        class R: pass
        r = R(); r.returncode = 0 if ok else 1; r.stdout = ""; r.stderr = "" if ok else "no network"
        if ok:
            (target / "yt_dlp").mkdir(parents=True)
            (target / "yt_dlp" / "version.py").write_text(f"__version__ = '{version}'\n")
            (target / "yt_dlp" / "__init__.py").write_text("")
        return r
    return run
have = ytupdate.current()
check("the installed yt-dlp has a version", bool(have), True)
ytupdate.subprocess.run = fake_pip("2099.01.01")
out = ytupdate.update()
check("a newer yt-dlp is fetched and used", (out.startswith("updated"), ytupdate._version_in(ytupdate.target())), (True, "2099.01.01"))
check("it comes first on the path, so it wins", sys.path[0], str(ytupdate.target()))
check("the loaded yt-dlp was dropped so the next download uses the new one", any(n.startswith("yt_dlp") for n in sys.modules), False)
ytupdate.subprocess.run = fake_pip("2099.01.01")
check("the same version again: nothing changes", ytupdate.update().startswith("already newest"), True)
ytupdate.subprocess.run = fake_pip("2000.01.01")
check("an older one is never installed", ytupdate.update().startswith("already newest"), True)
ytupdate.subprocess.run = fake_pip("", ok=False)
out = ytupdate.update()
check("no network or no pip: carries on with what is installed, with the reason", out.startswith("could not fetch") and "no network" in out, True)
check("...and the working copy is still there", ytupdate._version_in(ytupdate.target()), "2099.01.01")
check("no leftovers from the failed try", ytupdate.target().with_name("ytdlp.new").exists(), False)
check("it is a setting a person can turn off", (config.YTDLP_UPDATE_HOURS, ytupdate.status()["auto"]), (24.0, True))

print("\nALL PASSED" if not fails else f"\nFAILED: {', '.join(fails)}")
sys.exit(1 if fails else 0)
