"""Looks at the picture of a clip, not only the sound. The AI reads words; this checks what a viewer sees.

A short, small copy of the clip is read frame by frame (two a second, tiny and grey: cheap) and three things are
measured: how much moves, how often the shot changes, and whether the first seconds have something happening.
A black screen, a frozen picture or a clip that opens still all lose points. The result is a score from 0 to 100
that is blended with the AI's own score (brain.blend), so the clips that look as good as they sound come first.

Nothing here can stop a clip from being made: if the picture cannot be read, the AI's score is used as it is."""
import subprocess

import numpy as np

from . import config

FPS = 2                 # frames looked at per second
W, H = 96, 54           # each one shrunk to this: enough to see movement and cuts, far too small to cost anything
CUT = 0.16              # average change between two frames (0 to 1) above which the shot has changed
STILL = 0.004           # below this, two frames are the same picture


def grab(path, start: float, end: float):
    """The frames of path between start and end (seconds), as an array [frames, H, W] of 0 to 1. None if unreadable."""
    dur = max(0.5, end - start)
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{max(0.0, start):.2f}", "-t", f"{dur:.2f}", "-i", str(path), "-an", "-sn",
           "-vf", f"fps={FPS},scale={W}:{H},format=gray", "-f", "rawvideo", "-"]
    try:
        raw = subprocess.run(cmd, capture_output=True, timeout=120, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    n = len(raw) // (W * H)
    if n < FPS * 2:
        return None
    return np.frombuffer(raw[: n * W * H], dtype=np.uint8).reshape(n, H, W).astype(np.float32) / 255.0


def score_frames(frames) -> dict:
    """Score the frames of one clip. Pure arithmetic, so it can be tested with made-up frames."""
    n = len(frames)
    if n < FPS * 2:
        return {}
    diff = np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2))          # change from each frame to the next
    cuts = int((diff > CUT).sum())
    seconds = n / FPS
    bright = float(frames.mean())
    still = float((diff < STILL).mean())
    motion = float(np.median(diff))
    early = diff[: FPS * 3]
    hook_motion = float(early.mean()) if len(early) else 0.0
    flags, pts = [], 55.0
    # Some movement is good. A lot of cutting is good up to a point (one change every few seconds feels alive).
    pts += min(18.0, motion * 900)
    rate = cuts / max(1.0, seconds) * 10                              # shot changes per 10 seconds
    pts += 12.0 if 1 <= rate <= 8 else 5.0 if rate > 0 else 0.0
    if hook_motion > max(motion, 0.002) * 1.15:
        pts += 10.0                                                   # opens with more happening than the rest
    if hook_motion < STILL * 1.5 and seconds > 6:
        pts -= 8.0
        flags.append("opens on a still picture")
    if bright < 0.05:
        pts -= 45.0
        flags.append("mostly black")
    if still > 0.92 and cuts == 0:
        pts -= 20.0
        flags.append("picture hardly moves")
    if rate > 14:
        pts -= 10.0
        flags.append("cuts too fast")
    return {"score": int(max(0, min(100, round(pts)))), "motion": round(motion, 4), "cuts": cuts,
            "hook_motion": round(hook_motion, 4), "flags": flags}


def profile(path, start: float, end: float):
    """The visual score of path between start and end, or None when it cannot be read or is turned off."""
    if not config.VISUAL:
        return None
    try:
        frames = grab(path, start, end)
        got = score_frames(frames) if frames is not None else {}
    except Exception:  # noqa: BLE001 - a clip is never held up by this
        return None
    return got or None
