"""Each person has a fixed amount of space for their finished clips. When it is full, their oldest videos are
deleted to make room, newest kept, so nobody can fill the server for free.

What is never deleted here: a video still being made, a stream still being recorded, a video that has a post
waiting to go out, and the video that was just finished (that is the one the person is about to look at)."""
import os
import time

from . import config

_MB = 1_000_000
_cache: dict = {}


def limit_bytes() -> float:
    return config.MAX_USER_MB * _MB


def used(uid: str) -> int:
    """Bytes in this person's folder (videos, clips, settings), counted fresh."""
    total = 0
    for root, _dirs, files in os.walk(config.user_dir(uid)):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def _size(path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def _deletable(job) -> bool:
    from . import live
    if job.get("status") not in ("done", "error") or job["id"] in live.SESSIONS:
        return False
    for c in job.get("clips", []):
        if any(p.get("status") == "scheduled" for p in (c.get("posts") or {}).values()):
            return False
    return True


def trim(uid: str, keep=()) -> int:
    """Delete this person's oldest videos until they fit. Returns how many were deleted."""
    from . import jobs
    over = used(uid) - limit_bytes()
    if over <= 0:
        return 0
    mine = sorted((j for j in jobs.all_jobs() if j["user"] == uid and j["id"] not in keep and _deletable(j)),
                  key=lambda j: j["created"])
    gone = 0
    for j in mine:
        if over <= 0:
            break
        size = _size(j["dir"])
        if jobs.delete(j["id"]):
            over -= size
            gone += 1
    _cache.pop(uid, None)
    return gone


def info(uid: str) -> dict:
    """For the pages: space used and the limit, looked at most every 20 seconds."""
    got = _cache.get(uid)
    if not got or time.time() - got[0] > 20:
        got = _cache[uid] = (time.time(), used(uid))
    lim = limit_bytes()
    return {"used_mb": round(got[1] / _MB, 1), "limit_mb": None if lim >= 10 ** 9 else round(lim / _MB)}
