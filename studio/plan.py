"""The free plan: how many videos one account may turn into clips, and how many clips one video gives.

    CREATIVECUT_FREE_VIDEOS      videos a free account may clip in all (default 5; 0 = no limit)
    CREATIVECUT_CLIPS_PER_VIDEO  clips made from one video (default 3)
    CREATIVECUT_FREE_REMAKES     times one clip may be re-made after changes (default 1; 0 = no limit)

Only videos that finish count: a video that fails or is cancelled does not use up the allowance. Admins, and
the owner on a computer without sign-in, are never limited. The count is kept in the person's own folder."""
import json
import threading

from . import config

_lock = threading.Lock()


def _file(uid):
    return config.user_dir(uid) / "plan.json"


def videos_done(uid) -> int:
    try:
        return int(json.loads(_file(uid).read_text(encoding="utf-8")).get("videos", 0))
    except (OSError, ValueError, AttributeError):
        return 0


def add_video(uid):
    """One more finished video for this person."""
    with _lock:
        n = videos_done(uid) + 1
        f = _file(uid)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"videos": n}), encoding="utf-8")


def limited(user) -> bool:
    return bool(config.ACCOUNTS) and not getattr(user, "is_admin", False) and config.FREE_VIDEOS < 10 ** 6


def videos_left(uid, user):
    """How many more videos this person may clip, or None when there is no limit for them."""
    if not limited(user):
        return None
    return max(0, int(config.FREE_VIDEOS) - videos_done(uid))


def remakes_left(clip, user):
    """How many more times this clip may be re-made, or None when there is no limit for this person."""
    if not limited(user) or config.FREE_REMAKES >= 10 ** 6:
        return None
    return max(0, int(config.FREE_REMAKES) - int(clip.get("remakes", 0)))


def info(uid, user) -> dict:
    """For the pages: the clips per video, the free videos used and allowed, and the re-makes allowed per clip
    (None when unlimited)."""
    return {"clips_per_video": config.CLIPS_PER_VIDEO, "videos_used": videos_done(uid),
            "videos_limit": int(config.FREE_VIDEOS) if limited(user) else None,
            "remakes_limit": int(config.FREE_REMAKES) if limited(user) and config.FREE_REMAKES < 10 ** 6 else None}
