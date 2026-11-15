"""The morning tidy-up of unfinished uploads: old partial files go, fresh ones (an upload happening now) and real files
stay, and it fires at 6 o'clock India time."""
import os, sys, tempfile, time
from datetime import datetime
from pathlib import Path
os.environ["CREATIVECUT_DATA"] = tempfile.mkdtemp(prefix="pc-clean-")
sys.path.insert(0, ".")
from studio import cleanup, config
fails = []
def check(n, got, want=True):
    ok = want(got) if callable(want) else got == want
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"   got {got!r}")); ok or fails.append(n)

d = Path(config.USERS_DIR) / "u_1" / "jobs" / "j1"; d.mkdir(parents=True)
old, new, keep = d / "upload.part", Path(config.USERS_DIR) / "u_1" / "jobs" / "j2" / "upload.part", d / "upload.mp4"
new.parent.mkdir(parents=True)
for f in (old, new, keep): f.write_bytes(b"x" * 10)
t = time.time() - 5 * 3600
os.utime(old, (t, t))
check("one abandoned upload is removed", cleanup.sweep(), 1)
check("the old one is gone; one being uploaded now and a finished upload stay", (old.exists(), new.exists(), keep.exists()), (False, True, True))
check("nothing left to remove the second time", cleanup.sweep(), 0)
ist = cleanup.IST
check("before 6 in the morning it runs the same day", cleanup.next_run(datetime(2026, 11, 15, 3, 0, tzinfo=ist), 6), datetime(2026, 11, 15, 6, 0, tzinfo=ist))
check("after 6 it runs the next morning", cleanup.next_run(datetime(2026, 11, 15, 7, 0, tzinfo=ist), 6), datetime(2026, 11, 16, 6, 0, tzinfo=ist))
check("exactly at 6 it waits for the next day", cleanup.next_run(datetime(2026, 11, 15, 6, 0, tzinfo=ist), 6), datetime(2026, 11, 16, 6, 0, tzinfo=ist))
sys.exit(1 if fails else 0)
