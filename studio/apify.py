"""Getting a YouTube video through an Apify actor, because YouTube often refuses downloads made straight from a server.

The actor (marielise.dev/youtube-video-downloader by default) downloads the video on Apify's side and hands back a
link to the file. We start a run, wait for it, fetch the file onto this server, and from then on the video is handled
like any other: clips are cut, then the video is deleted (jobs._drop_source). Apify charges per started minute of
video, so a limit on length and on the cost of one run is always sent with it. The token is read from
CREATIVECUT_APIFY_TOKEN or the file named by CREATIVECUT_APIFY_TOKEN_FILE and is never logged or put in an error."""
import time
from pathlib import Path

import httpx

from . import config

API = "https://api.apify.com/v2"
PER_MINUTE = 0.03          # the dearest rate (1080p), used to cap what one run may cost
QUALITIES = (360, 480, 720, 1080)


class ApifyError(RuntimeError):
    pass


def ready() -> bool:
    return bool(config.apify_token())


def quality_for(height) -> str:
    """The actor takes 360, 480, 720 or 1080: the largest of those that is not above what was asked for."""
    try:
        h = int(height)
    except (TypeError, ValueError):
        h = 720
    return str(max([q for q in QUALITIES if q <= h] or [QUALITIES[0]]))


def _headers() -> dict:
    return {"Authorization": f"Bearer {config.apify_token()}"}


def _fail(what: str, r) -> ApifyError:
    code = getattr(r, "status_code", 0)
    if code in (401, 403):
        return ApifyError("The video service refused our login. The Apify token on this server is wrong or has expired.")
    if code == 402:
        return ApifyError("The video service has no credit left. Add credit to the Apify account and try again.")
    return ApifyError(f"The video service could not {what} (error {code}). Try again in a minute.")


def fetch(url: str, dest: Path, height=720, tick=None) -> dict:
    """Download one YouTube video into the file dest. Returns what the actor knew about it (title, uploader,
    duration in seconds). tick() is called now and then; raising from it stops the wait (that is how Cancel works)."""
    if not ready():
        raise ApifyError("No Apify token is set on this server.")
    actor = config.APIFY_ACTOR.replace("/", "~")
    cap = round(config.APIFY_MAX_MIN * PER_MINUTE + 0.25, 2)           # most one run may cost, in dollars
    body = {"urls": [{"url": url}], "quality": quality_for(height), "format": "default", "residentialProxyMode": "disabled"}
    try:
        with httpx.Client(timeout=30, headers=_headers()) as c:
            r = c.post(f"{API}/acts/{actor}/runs", params={"maxTotalChargeUsd": cap, "timeout": 3600}, json=body)
            if r.status_code >= 300:
                raise _fail("start", r)
            run = r.json()["data"]
            deadline = time.time() + 3600
            while run.get("status") not in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
                if time.time() > deadline:
                    raise ApifyError("The video service took too long. Try again.")
                if tick:
                    tick()
                time.sleep(2)
                r = c.get(f"{API}/actor-runs/{run['id']}")
                if r.status_code >= 300:
                    raise _fail("report progress", r)
                run = r.json()["data"]
            r = c.get(f"{API}/datasets/{run['defaultDatasetId']}/items", params={"limit": 1})
            items = r.json() if r.status_code < 300 else []
            item = items[0] if items else {}
            if run.get("status") != "SUCCEEDED" or item.get("status") != "success" or not item.get("downloadUrl"):
                raise ApifyError("The video service could not download this video. It may be private, removed, "
                                 "age-restricted, or longer than the limit of %d minutes." % config.APIFY_MAX_MIN)
            dest.parent.mkdir(parents=True, exist_ok=True)
            part = dest.with_suffix(dest.suffix + ".part")
            with c.stream("GET", item["downloadUrl"], timeout=httpx.Timeout(30, read=120), follow_redirects=True) as s:
                if s.status_code >= 300:
                    raise _fail("send the file", s)
                n = 0
                with part.open("wb") as f:
                    for chunk in s.iter_bytes(1 << 20):
                        f.write(chunk)
                        n += 1
                        if tick and n % 4 == 0:
                            tick()
            part.replace(dest)
    except httpx.HTTPError as e:
        raise ApifyError(f"Could not reach the video service ({type(e).__name__}). Try again in a minute.") from None
    try:
        secs = float(item.get("duration") or 0)
    except (TypeError, ValueError):
        secs = 0.0
    return {"title": str(item.get("title") or ""), "uploader": str(item.get("uploader") or ""), "duration": secs}
