#!/usr/bin/env python3
"""Check the privacy notice is the same everywhere it appears:
  * docs/PRIVACY.md's code block must equal PRIVACY_TEXT in bin/mohaa_launcher.py;
  * every left-hand text in _PRIVACY_SWAPS (bin/mohaa_map_launcher.py) must occur in
    PRIVACY_TEXT, or the Map Viewer silently shows the Model Viewer's wording.
--write regenerates the code block in docs/PRIVACY.md from PRIVACY_TEXT.
Needs tkinter (the launcher modules import it). Exit 0 = in sync."""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "bin"))
import mohaa_launcher as ML       # noqa: E402
import mohaa_map_launcher as MM   # noqa: E402

MD = os.path.join(ROOT, "docs", "PRIVACY.md")
BLOCK = re.compile(r"```\n(.*?)```", re.S)


def main(argv):
    """Compare (or with --write, regenerate); print the result; return the exit code."""
    text = open(MD, encoding="utf-8").read()
    m = BLOCK.search(text)
    if not m:
        print("no code block in docs/PRIVACY.md")
        return 1
    if "--write" in argv:
        new = text[:m.start(1)] + ML.PRIVACY_TEXT + text[m.end(1):]
        import mohaa_common as MC
        MC.atomic_write_text(MD, new, newline="\n")
        print("docs/PRIVACY.md regenerated from PRIVACY_TEXT")
        text, m = new, BLOCK.search(new)
    bad = 0
    if m.group(1) != ML.PRIVACY_TEXT:
        print("docs/PRIVACY.md differs from PRIVACY_TEXT (run with --write)")
        bad = 1
    missing = [a for a, _b in MM._PRIVACY_SWAPS if a not in ML.PRIVACY_TEXT]
    for a in missing:
        print("_PRIVACY_SWAPS text not found in PRIVACY_TEXT: %r" % a[:70])
    if not bad and not missing:
        print("OK: PRIVACY.md, PRIVACY_TEXT and all %d _PRIVACY_SWAPS agree" % len(MM._PRIVACY_SWAPS))
    return 1 if (bad or missing) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
