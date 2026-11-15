"""Captions: the AI may tidy words, never change them. Real cases from clips made here: English loanwords spoken
in Hindi, a word turned into a number, words dropped, a translation passed off as a spelling, and a video with two
audio tracks whose YouTube transcript came from the wrong one. The AI is replaced, so nothing leaves this machine."""
import os, sys, tempfile
os.environ["CREATIVECUT_DATA"] = tempfile.mkdtemp(prefix="pc-cap-")
os.environ.update(DATABASE_URL="", CREATIVECUT_ACCOUNTS="0", CREATIVECUT_AI_KEY="", CREATIVECUT_AI_MODELS="")
sys.path.insert(0, ".")
from studio import brain, media
fails = []
def check(n, got, want=True):
    ok = want(got) if callable(want) else got == want
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"   got {got!r}")); ok or fails.append(n)

def fix(spoken, answer):
    """The caption fix, with the AI's answer given."""
    words = [{"w": w, "s": i * 0.5, "e": i * 0.5 + 0.4} for i, w in enumerate(spoken)]
    brain.ask_ai = lambda prompt, schema=None, purpose="": (answer, "m", 1)
    return [w["w"] for w in brain._fix_caption_words(words, "")]

check("a number word becomes digits", fix(["he", "had", "eleven", "kills"], ["He", "had", "11", "kills."]), ["He", "had", "11", "kills."])
check("an ordinary word may not become a number ('won' is not '1')", fix(["we", "won", "the", "game"], ["We", "1", "the", "game."]), ["We", "won", "the", "game."])
check("words joined into one number may disappear", fix(["twenty", "-", "five", "bucks"], ["$25", "", "", "bucks"]), ["$25", "bucks"])
check("a word the AI simply dropped stays", fix(["i", "really", "love", "this"], ["I", "", "love", "this."]), ["I", "really", "love", "this."])
check("a name is spelled right", fix(["rock", "star", "made", "this"], ["Rockstar", "", "made", "this."]), lambda w: w[0] == "Rockstar")
check("an English loanword spoken in Hindi comes out in English", fix(["कंप्लीटली", "इंपॉसिबल", "होगा"], ["completely", "impossible", "hoga"]), ["completely", "impossible", "hoga"])
check("...also short ones ('गेम्स' is games, 'वेट' is weight)", fix(["रियलिस्टिक", "वेट", "फिजिक्स", "गेम्स"], ["realistic", "weight", "physics", "games"]), ["realistic", "weight", "physics", "games"])
check("a translation is not taken for a spelling ('चूना' is not 'lime')", fix(["चूना", "लगा", "दिया"], ["lime", "laga", "diya"]), lambda w: w[0] == "चूना")
prompts = []
brain.ask_ai = lambda prompt, schema=None, purpose="": (prompts.append(prompt) or ["a", "b", "c"], "m", 1)
brain._fix_caption_words([{"w": x, "s": 0, "e": 1} for x in ("a", "b", "c")], "")
check("the AI sees each word in its sentence", "Whole text: a b c" in prompts[-1], True)
check("...and is told English loanwords in Hindi come out in English", "write those as the normal English word" in prompts[-1], True)

# ---- which YouTube transcript to borrow, when a video has more than one audio track
auto = {"bn-orig": [], "hi-orig": [], "en": [], "hi": []}
check("the video's own language wins over the first track listed", media._spoken_track({"language": "hi"}, auto), "hi-orig")
fmt = [{"language": "bn", "format_note": "Bangla, medium", "acodec": "opus"}, {"language": "hi", "format_note": "Hindi original (default), medium", "acodec": "opus"}]
check("...or the default audio track's language", media._spoken_track({"formats": fmt}, auto), "hi-orig")
check("one spoken track: that one", media._spoken_track({}, {"en-orig": []}), "en-orig")
check("several and no way to tell: none (our own transcript is used)", media._spoken_track({}, {"bn-orig": [], "hi-orig": []}), None)

print("\nALL PASSED" if not fails else f"\nFAILED: {', '.join(fails)}")
sys.exit(1 if fails else 0)
