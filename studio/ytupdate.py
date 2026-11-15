"""Keeping yt-dlp up to date. YouTube changes often and an old yt-dlp stops working, so every day (and soon after
YouTube refuses a download) a newer yt-dlp is fetched into the data folder and used from then on, with no
restart and no new image. The copy that came with the install is only the starting point.

    CREATIVECUT_YTDLP_UPDATE_HOURS   how often to look (default 24; 0 = never)"""
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import config

_lock = threading.Lock()
_state = {"last": 0.0, "result": "", "soon": 0.0}


def target() -> Path:
    return config.DATA_DIR / "ytdlp"


def use_updated():
    """Put the downloaded copy first, so it wins over the one that came with the install. Called before yt-dlp is
    first imported, and again after an update."""
    t = str(target())
    if target().is_dir() and t not in sys.path[:1]:
        if t in sys.path:
            sys.path.remove(t)
        sys.path.insert(0, t)


def _version_in(folder: Path) -> str:
    try:
        m = re.search(r"__version__\s*=\s*['\"]([^'\"]+)", (folder / "yt_dlp" / "version.py").read_text(encoding="utf-8"))
        return m.group(1) if m else ""
    except OSError:
        return ""


def _key(v: str):
    return tuple(int(x) for x in re.findall(r"\d+", v))


def current() -> str:
    """The yt-dlp version in use."""
    try:
        import yt_dlp.version as v
        return v.__version__
    except Exception:  # noqa: BLE001
        return ""


def _forget_loaded():
    """Drop the loaded yt-dlp so the next download imports the new one. Downloads already running keep the old one."""
    for name in [n for n in sys.modules if n == "yt_dlp" or n.startswith("yt_dlp.")]:
        del sys.modules[name]


def update() -> str:
    """Fetch the newest yt-dlp. Returns what happened, in a few words; never raises."""
    with _lock:
        _state["last"] = time.time()
        new = target().with_name("ytdlp.new")
        try:
            shutil.rmtree(new, ignore_errors=True)
            p = subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "--quiet", "--disable-pip-version-check",
                                "--no-deps", "--target", str(new), "yt-dlp"], capture_output=True, text=True, timeout=300)
            if p.returncode != 0:
                _state["result"] = "could not fetch: " + (p.stderr or p.stdout).strip()[-160:]
                return _state["result"]
            got, have = _version_in(new), (_version_in(target()) or current())
            if not got:
                _state["result"] = "the download had no yt-dlp in it"
            elif have and _key(got) <= _key(have):
                _state["result"] = f"already newest ({have})"
            else:
                old = target().with_name("ytdlp.old")
                shutil.rmtree(old, ignore_errors=True)
                if target().exists():
                    target().rename(old)
                new.rename(target())
                shutil.rmtree(old, ignore_errors=True)
                use_updated()
                _forget_loaded()
                _state["result"] = f"updated {have or '?'} to {got}"
                print(f"[Creative Cut] yt-dlp {_state['result']}", flush=True)
        except Exception as e:  # noqa: BLE001 - offline, no pip, read-only folder: carry on with what is installed
            _state["result"] = "could not update: " + str(e)[-160:]
        finally:
            shutil.rmtree(new, ignore_errors=True)
        return _state["result"]


def soon():
    """YouTube just refused a download: look for a newer yt-dlp in the background (at most every few hours)."""
    if config.YTDLP_UPDATE_HOURS <= 0 or time.time() - _state["last"] < 6 * 3600 or time.time() - _state["soon"] < 600:
        return
    _state["soon"] = time.time()
    threading.Thread(target=update, daemon=True).start()


def start():
    """The daily look. The first one is a minute after the server starts."""
    if config.YTDLP_UPDATE_HOURS <= 0:
        return

    def loop():
        time.sleep(60)
        while True:
            update()
            time.sleep(max(1.0, config.YTDLP_UPDATE_HOURS) * 3600)

    threading.Thread(target=loop, daemon=True, name="ytdlp-update").start()


def status() -> dict:
    return {"version": current(), "last_check": _state["last"] or None, "result": _state["result"],
            "auto": config.YTDLP_UPDATE_HOURS > 0}
