"""The plan: a few free videos to try Creative Cut, then a monthly subscription, with refills for heavy months.

    CREATIVECUT_FREE_VIDEOS      free videos a new account may clip, once (default 2; 0 = no limit for anyone)
    CREATIVECUT_CLIPS_PER_VIDEO  clips made from one video (default 3)
    CREATIVECUT_FREE_REMAKES     times one clip may be re-made on the free videos (default 1; 0 = no limit)
    CREATIVECUT_PLAN_PRICE_INR   monthly price (default 499)
    CREATIVECUT_PLAN_VIDEOS      videos every 30 days while subscribed (default 20)
    CREATIVECUT_REFILL_PRICE_INR price of a refill pack (default 499)
    CREATIVECUT_REFILL_VIDEOS    videos in a refill pack (default 20)
    CREATIVECUT_PAID_REMAKES     times one clip may be re-made while subscribed (default 3; 0 = no limit)

The subscription is paid through Cashfree (billing.py), which charges every month by UPI AutoPay or card. While it is
paid up, the person gets the plan's videos every 30 days, counted from the day it started; videos not used in those
30 days do not carry over. Refill packs are for subscribers who run out early: their videos are used after the
month's videos, never expire, and can be used only while subscribed.

Only videos that finish count: a video that fails or is cancelled uses nothing. Order of use: free, then the
month's, then refill. Admins, and the owner on a computer without sign-in, are never limited. Everything is kept in
the person's own folder (plan.json)."""
import json
import threading
import time

from . import config

_lock = threading.Lock()
DAY = 86400
PERIOD = 30 * DAY


def _file(uid):
    return config.user_dir(uid) / "plan.json"


def _read(uid) -> dict:
    try:
        d = json.loads(_file(uid).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(uid, d: dict):
    f = _file(uid)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(d), encoding="utf-8")
    tmp.replace(f)


def _int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def videos_done(uid) -> int:
    """Videos this person has ever finished (free and paid)."""
    return _int(_read(uid).get("videos"))


# ---------------------------------------------------------------- the subscription, as plan.json holds it
def _sub(d: dict) -> dict:
    s = d.get("sub")
    return s if isinstance(s, dict) else {}


def _active(d: dict) -> bool:
    """Paid up: Cashfree has it active, or the time already paid for has not run out."""
    try:
        return float(_sub(d).get("until") or 0) > time.time()
    except (TypeError, ValueError):
        return False


def _period(d: dict) -> int:
    """Which 30 days of the subscription we are in (0 for the first)."""
    try:
        return int((time.time() - float(_sub(d).get("anchor") or time.time())) // PERIOD)
    except (TypeError, ValueError):
        return 0


def _month_left(d: dict) -> int:
    if not _active(d):
        return 0
    most = _int(_sub(d).get("videos")) or config.PLAN_VIDEOS
    used = _int(d.get("used")) if _int(d.get("period")) == _period(d) else 0
    return max(0, most - used)


def _extra_left(d: dict) -> int:
    return max(0, _int(d.get("extra"))) if _active(d) else 0


def subscription(uid) -> dict:
    return dict(_sub(_read(uid)))


def subscribed(uid) -> bool:
    return _active(_read(uid))


def update_sub(uid, **fields):
    """Store what Cashfree says about this person's subscription. The 30-day count starts when it first becomes paid up."""
    with _lock:
        d = _read(uid)
        s = _sub(d)
        was = _active(d)
        s.update({k: v for k, v in fields.items() if v is not None})
        d["sub"] = s
        if _active(d) and (not was or not s.get("anchor")):
            s["anchor"] = time.time()          # a new subscription (or one started again): a fresh 30 days
            d["used"], d["period"] = 0, 0
        _write(uid, d)


def add_extra(uid, videos: int):
    """A refill pack was paid for."""
    with _lock:
        d = _read(uid)
        d["extra"] = max(0, _int(d.get("extra"))) + int(videos)
        _write(uid, d)


def free_left(uid) -> int:
    return max(0, int(config.FREE_VIDEOS) - videos_done(uid)) if config.FREE_VIDEOS < 10 ** 6 else 10 ** 6


def add_video(uid):
    """One more finished video for this person: a free one while they last, then the month's, then a refill."""
    from . import auth
    with _lock:
        d = _read(uid)
        free = _int(d.get("videos")) < int(min(config.FREE_VIDEOS, 10 ** 6))
        d["videos"] = _int(d.get("videos")) + 1
        if not free and limited(auth.get_user(uid)):
            if _month_left(d) > 0:
                p = _period(d)
                d["used"] = (_int(d.get("used")) if _int(d.get("period")) == p else 0) + 1
                d["period"] = p
            elif _extra_left(d) > 0:
                d["extra"] = _int(d.get("extra")) - 1
        _write(uid, d)


def limited(user) -> bool:
    return bool(config.ACCOUNTS) and user is not None and not getattr(user, "is_admin", False) and config.FREE_VIDEOS < 10 ** 6


def paid_left(uid) -> int:
    d = _read(uid)
    return _month_left(d) + _extra_left(d)


def videos_left(uid, user):
    """How many more videos this person may clip right now, or None when there is no limit for them."""
    if not limited(user):
        return None
    return free_left(uid) + paid_left(uid)


def remakes_left(clip, user, uid=None):
    """How many more times this clip may be re-made, or None when there is no limit for this person.
    Subscribers get CREATIVECUT_PAID_REMAKES; everyone else CREATIVECUT_FREE_REMAKES."""
    if not limited(user):
        return None
    most = config.PAID_REMAKES if uid and subscribed(uid) else config.FREE_REMAKES
    if most >= 10 ** 6:
        return None
    return max(0, int(most) - int(clip.get("remakes", 0)))


def info(uid, user) -> dict:
    """For the pages: what is left, the subscription, and the prices. The *_limit names are kept for older pages."""
    from . import billing
    lim = limited(user)
    d = _read(uid)
    s, on = _sub(d), _active(d)
    remakes = (config.PAID_REMAKES if on else config.FREE_REMAKES) if lim else 10 ** 7
    renews = None
    if on:
        renews = float(s.get("anchor") or time.time()) + (_period(d) + 1) * PERIOD     # when the month's videos come back
    return {"clips_per_video": config.CLIPS_PER_VIDEO, "videos_used": videos_done(uid),
            "limited": lim,
            "videos_left": (free_left(uid) + _month_left(d) + _extra_left(d)) if lim else None,
            "free_left": free_left(uid) if lim else None, "free_videos": int(config.FREE_VIDEOS) if lim else None,
            "subscribed": on, "status": s.get("status") or "", "month_left": _month_left(d) if lim else None,
            "extra_left": _extra_left(d) if lim else None, "extra_kept": max(0, _int(d.get("extra"))),
            "resets": renews, "until": float(s.get("until") or 0) or None,
            "cancelled": (s.get("status") or "") in billing.ENDED,
            "paid_left": (_month_left(d) + _extra_left(d)) if lim else None,
            "videos_limit": int(config.FREE_VIDEOS) if lim else None,
            "remakes_limit": int(remakes) if remakes < 10 ** 6 else None,
            "plan": {"price": config.PLAN_PRICE_INR, "videos": config.PLAN_VIDEOS},
            "refill": {"price": config.REFILL_PRICE_INR, "videos": config.REFILL_VIDEOS},
            "can_buy": lim and billing.ready(), "mode": "production" if config.cashfree_live() else "sandbox"}
