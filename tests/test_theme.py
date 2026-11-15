"""Colours live in one file, web/theme.css. Checks every page loads it, every colour name a page uses exists in it,
and no page has quietly gone back to the old brand colours. Reads files only; no server needed."""
import re, sys
from pathlib import Path
sys.path.insert(0, ".")
WEB = Path("web")
fails = []
def check(n, ok, extra=""):
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else "   " + str(extra))); ok or fails.append(n)

css = (WEB / "theme.css").read_text(encoding="utf-8")
defined = set(re.findall(r"--(c-[a-z0-9-]+)\s*:", css))
check("theme.css defines the brand colours", {"c-brand", "c-bg", "c-surface", "c-text"} <= defined)

OLD = ["#E8175D", "#FF3D7A", "#B00F45", "#1A1647", "#221C56", "#0B0A24"]     # values that now belong to theme.css only
for page in ["landing", "index", "auth", "reset", "admin", "legal"]:
    s = (WEB / f"{page}.html").read_text(encoding="utf-8")
    check(f"{page}: loads theme.css before its own styles", s.find("/assets/theme.css") != -1 and s.find("/assets/theme.css") < s.find("<style"))
    used = set(re.findall(r"var\(--(c-[a-z0-9-]+)", s))
    check(f"{page}: every colour name it uses exists", used <= defined, sorted(used - defined))
    styles = "".join(re.findall(r"<style>(.*?)</style>", s, re.S)) + "".join(re.findall(r'style="([^"]*)"', s))
    stray = [h for h in OLD if h.lower() in styles.lower()]
    check(f"{page}: no brand colour typed in by hand", not stray, stray)

js = (WEB / "hero3d.js").read_text(encoding="utf-8")
check("3D hero reads colours from the page", "getPropertyValue" in js and "0xe8175d" not in js.lower())
from studio import mailer
check("emails read theme.css", mailer.theme().get("brand") == re.search(r"--c-brand:\s*(#[0-9A-Fa-f]{6})", css).group(1))
sys.exit(1 if fails else 0)
