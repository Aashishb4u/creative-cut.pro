"""A download can never fill the server: it is stopped past a size limit, or when the disk is nearly full, and a
Cancel still works through the same check. No network; the hook is called directly."""
import os, sys, tempfile, collections
from pathlib import Path
os.environ["CREATIVECUT_DATA"] = tempfile.mkdtemp(prefix="pc-guard-")
sys.path.insert(0, ".")
from studio import config, media
fails = []
def check(n, got, want=True):
    ok = want(got) if callable(want) else got == want
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"   got {got!r}")); ok or fails.append(n)

folder = tempfile.mkdtemp()
config.MAX_DOWNLOAD_GB, config.MIN_FREE_DISK_GB = 8, 0.0
seen = []
hook = media._size_guard(folder, lambda d: seen.append(1))
hook({"status": "downloading", "downloaded_bytes": 3 * 10 ** 9})
check("a download under the limit goes on, and the caller's own check still runs", seen, [1])

def raises(fn, exc):
    try:
        fn(); return False
    except exc:
        return True
check("past the size limit it is stopped, with a plain message", raises(lambda: hook({"downloaded_bytes": 9 * 10 ** 9}), media.TooBig), True)
try:
    hook({"downloaded_bytes": 9 * 10 ** 9})
except media.TooBig as e:
    check("...and the message says what to do", "shorter" in str(e), True)
config.MAX_DOWNLOAD_GB = 0
check("a limit of 0 means no size limit", raises(lambda: media._size_guard(folder)({"downloaded_bytes": 10 ** 12}), media.TooBig), False)
config.MAX_DOWNLOAD_GB = 8

# the disk nearly full
real = media.shutil.disk_usage
media.shutil.disk_usage = lambda p: collections.namedtuple("u", "total used free")(100 * 10 ** 9, 99 * 10 ** 9, 1 * 10 ** 9)
config.MIN_FREE_DISK_GB = 3.0
check("with the disk nearly full the download is stopped", raises(lambda: media._size_guard(folder)({"downloaded_bytes": 1}), media.TooBig), True)
media.shutil.disk_usage = lambda p: collections.namedtuple("u", "total used free")(100 * 10 ** 9, 50 * 10 ** 9, 50 * 10 ** 9)
check("with plenty of room it carries on", raises(lambda: media._size_guard(folder)({"downloaded_bytes": 1}), media.TooBig), False)
media.shutil.disk_usage = real

# Cancel still stops it
class Stop(Exception): pass
def cancel(d): raise Stop()
check("a cancel raised by the caller still stops the download", raises(lambda: media._size_guard(folder, cancel)({"downloaded_bytes": 1}), Stop), True)
sys.exit(1 if fails else 0)
