"""A tidy-up that runs every morning (India time, 6 o'clock by default): it deletes the unfinished uploads that were
started and never completed (upload.part, see server.upload_piece). A person who closes the page half-way through
sending a video leaves such a file behind; it would sit in their space until they deleted the video. Only files not
touched for a few hours go, so an upload that is happening right now is never cut off.

It runs inside the server (no separate cron job to set up). Set CREATIVECUT_CLEANUP_HOUR_IST (0 to 23), or -1 to turn it
off. If the server was off at that hour, the tidy-up happens when it next starts, because it also runs once at start."""
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config

log = logging.getLogger("creativecut.cleanup")
IST = timezone(timedelta(hours=5, minutes=30))
STALE = 3 * 3600          # an upload not touched for this long (seconds) was abandoned


def sweep(now=None) -> int:
    """Delete abandoned partial uploads everywhere. Returns how many were removed."""
    now = now or time.time()
    gone = 0
    for f in Path(config.USERS_DIR).glob("*/**/upload.part"):
        try:
            if now - f.stat().st_mtime > STALE:
                f.unlink()
                gone += 1
        except OSError:
            continue
    if gone:
        log.info("removed %d unfinished upload(s)", gone)
    return gone


def next_run(after: datetime, hour: int) -> datetime:
    """The next time it is `hour` o'clock in India after the moment given."""
    t = after.astimezone(IST).replace(hour=hour, minute=0, second=0, microsecond=0)
    return t if t > after else t + timedelta(days=1)


def start():
    hour = config.CLEANUP_HOUR_IST
    if hour < 0:
        return

    def loop():
        try:
            sweep()                                       # once at start: it may have been off at the usual hour
        except Exception:  # noqa: BLE001
            log.exception("tidy-up failed")
        while True:
            at = next_run(datetime.now(IST), hour)
            time.sleep(max(1.0, (at - datetime.now(IST)).total_seconds()))
            try:
                sweep()
            except Exception:  # noqa: BLE001
                log.exception("tidy-up failed")
            time.sleep(60)                                # never run twice for the same minute

    threading.Thread(target=loop, daemon=True, name="cleanup").start()
