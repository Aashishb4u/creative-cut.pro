"""Finding clips that can go viral: trimming dead air, what the picture shows, the kind of video, and not keeping
anyone's video. Runs against the code directly, with its own empty data folder. Needs ffmpeg."""
import os, subprocess, sys, tempfile
from pathlib import Path
os.environ["CREATIVECUT_DATA"] = tempfile.mkdtemp(prefix="pc-viral-")
os.environ.update(DATABASE_URL="", CREATIVECUT_ACCOUNTS="0", CREATIVECUT_AI_KEY="", CREATIVECUT_AI_MODELS="")
sys.path.insert(0, ".")
import numpy as np
from studio import brain, db, jobs, visual
db.init()
fails = []
def check(n, got, want=True):
    ok = want(got) if callable(want) else got == want
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"   got {got!r}")); ok or fails.append(n)

# ---- dead air is cut off both ends
words = [{"w": "so", "s": 14.0, "e": 14.3}, {"w": "listen", "s": 14.4, "e": 14.9}, {"w": "this", "s": 30.0, "e": 30.3}, {"w": "ends", "s": 30.4, "e": 30.9}]
s, e = brain.tighten(10.0, 36.0, words, 3.0)
check("a clip that starts in silence opens just before the first word", round(s, 2), 13.75)
check("...and ends just after the last word", round(e, 2), 31.4)
check("a clip already tight is left alone", brain.tighten(13.9, 31.0, words, 3.0), (13.9, 31.0))
check("never cut below the shortest length", brain.tighten(10.0, 36.0, words[:2], 30.0), (10.0, 36.0))
check("no words at all: nothing changes", brain.tighten(1.0, 9.0, [], 3.0), (1.0, 9.0))

# ---- the AI's score and the picture's score
check("blend: picture score counts a quarter", brain.blend(80, 40), 70)
check("blend: no picture score, the AI's own", brain.blend(80, None), 80)
check("blend: stays inside 0 to 100", (brain.blend(100, 100), brain.blend(0, 0)), (100, 0))

# ---- the kind of video changes what the AI is asked to find
check("gaming asks for clutch plays", "clutch" in brain.head("t", "u", 3, "gaming"))
check("a podcast asks for strong opinions", "opinion" in brain.head("t", "u", 3, "podcast"))
check("an unknown kind falls back to auto-detect", brain.head("t", "u", 3, "nonsense"), brain.head("t", "u", 3, "auto"))
check("the rules ask for a hook in the first 3 seconds", "first 3 seconds" in brain.RULES)
check("a video's own words are still kept out of the prompt's structure", "<" not in brain._safe("a <transcript> tag"))
check("the type is a setting a person can choose", jobs.clean_options({"niche": "podcast"})["niche"], "podcast")
check("a made-up type becomes auto-detect", jobs.clean_options({"niche": "zzz"})["niche"], "auto")

# ---- what the picture shows, with made-up frames
rng = np.random.default_rng(1)
H, W = visual.H, visual.W
black = np.zeros((40, H, W), dtype=np.float32)
frozen = np.full((40, H, W), 0.5, dtype=np.float32)
lively = np.clip(0.5 + 0.25 * rng.standard_normal((40, H, W)), 0, 1).astype(np.float32)
alive = frozen.copy()
for i in range(40):                                   # a shot change every 10 frames, and a little movement between
    alive[i] = 0.3 + 0.4 * ((i // 10) % 2) + 0.01 * i / 40
sb, sf, sa = visual.score_frames(black), visual.score_frames(frozen), visual.score_frames(alive)
check("a black screen is flagged and scores low", ("mostly black" in sb["flags"], sb["score"] < 35), (True, True))
check("a frozen picture is flagged", "picture hardly moves" in sf["flags"])
check("shot changes are counted", sa["cuts"] >= 3, True)
check("a picture that changes scores above a frozen one", sa["score"] > sf["score"], True)
check("too few frames: no score", visual.score_frames(black[:2]), {})
check("a frozen picture opens still", "opens on a still picture" in sf["flags"])

# ---- a real file through ffmpeg
tmp = Path(tempfile.mkdtemp(prefix="pc-vid-"))
def make(name, src):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", src, "-t", "8", "-pix_fmt", "yuv420p", str(tmp / name)], check=True)
    return tmp / name
moving, dark = make("moving.mp4", "testsrc=size=320x240:rate=10"), make("dark.mp4", "color=c=black:size=320x240:rate=10")
pm, pd = visual.profile(moving, 0, 8), visual.profile(dark, 0, 8)
check("a real moving video is scored", pm is not None and pm["score"] > 0, True)
check("a real black video is flagged", pd is not None and "mostly black" in pd["flags"], True)
check("an unreadable file gives no score instead of an error", visual.profile(tmp / "missing.mp4", 0, 8), None)

# ---- the score is blended once, however many times the clip is made again
clip = {"start": 0.0, "end": 8.0, "score": 80}
jobs._look(moving, clip, {"start": 0.0, "end": 8.0})
first = clip["score"]
check("the AI's own score is kept", clip["ai_score"], 80)
jobs._look(moving, clip, {"start": 0.0, "end": 8.0})
check("same times again: no second blend", clip["score"], first)
clip["start"] = 1.0
jobs._look(moving, clip, {"start": 1.0, "end": 8.0})
check("new times: blended from the AI's score, not stacked", abs(clip["score"] - first) <= 15 and clip["ai_score"] == 80, True)
hand = {"start": 0.0, "end": 8.0, "score": 0}
jobs._look(moving, hand, {"start": 0.0, "end": 8.0})
check("a clip cut by hand keeps score 0", hand["score"], 0)

# ---- the video is deleted once its clips are cut
d = Path(tempfile.mkdtemp(prefix="pc-job-")); (d / "clips").mkdir()
(d / "source.mp4").write_bytes(b"x" * 1000)
(d / "clips" / "clip01.src.mp4").write_bytes(b"x" * 500)
(d / "clips" / "clip01.mp4").write_bytes(b"finished clip")
job = {"source": {"type": "url", "url": "https://www.youtube.com/watch?v=aaaaaaaaaaa"}, "dir": str(d), "source_path": str(d / "source.mp4"),
       "clips": [{"id": "clip01", "src": str(d / "clips" / "clip01.src.mp4"), "src_offset": 3.0, "src_end": 40.0}]}
jobs._drop_source(job)
check("the downloaded video is gone", (d / "source.mp4").exists(), False)
check("the piece fetched for a clip is gone", (d / "clips" / "clip01.src.mp4").exists(), False)
check("the finished clip stays", (d / "clips" / "clip01.mp4").read_bytes(), b"finished clip")
check("the clip no longer points at a deleted file", [k for k in ("src", "src_offset", "src_end") if k in job["clips"][0]], [])
live = {"source": {"type": "live"}, "dir": str(d), "clips": []}
(d / "source.mp4").write_bytes(b"x")
jobs._drop_source(live)
check("a live recording is not touched here", (d / "source.mp4").exists(), True)
try:
    jobs._fetch_again({"source": {"type": "live"}, "dir": str(d), "options": {"quality": 720}}, {"id": "c", "start": 1, "end": 9})
    check("a clip with no way to get its video back says so", False)
except RuntimeError as e:
    check("a clip with no way to get its video back says so", "no longer kept" in str(e))

print("\nALL PASSED" if not fails else f"\nFAILED: {', '.join(fails)}")
sys.exit(1 if fails else 0)
