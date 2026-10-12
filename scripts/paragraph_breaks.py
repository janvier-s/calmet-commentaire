"""Start numbered points (1°., 2°. …) on their own line, as " \\n" (space + line break).

A point gets a break when it follows the end of a sentence or clause (. ; : ? ! or a
footnote call), not inside a sentence ("il paraît 1°. que…") or after another point
("6°. 7°. et 8°."). A literal backslash-n typed in the editor becomes a real break.

Usage: python3 paragraph_breaks.py [--dry-run] [volume ...]   (default: all)
"""
import json
import re
import sys

from paths import DATA

POINT = re.compile(r"(?<=[.;:?!}])(?<![°º]\.)[  ]+(?=\d{1,2}[°º]\.?\s)")
LITERAL = re.compile(r"[  ]*\\n[  ]*\n?")
BEFORE_NL = re.compile(r"[  ]*\n")


def fix(s):
    s = LITERAL.sub(" \n", s)
    s = POINT.sub(" \n", s)
    return s


def main(argv):
    dry = "--dry-run" in argv
    vols = [a for a in argv if not a.startswith("--")] or sorted(p.name for p in DATA.iterdir() if (p / "normalized").is_dir())
    pages = points = 0
    for vol in vols:
        for path in sorted((DATA / vol / "normalized").glob("page_*.json")):
            d = json.loads(path.read_text(encoding="utf-8"))
            changed = False
            for b in d.get("commentary") or []:
                s = b.get("french_commentary")
                if isinstance(s, str) and fix(s) != s:
                    points += len(POINT.findall(s)) + len(LITERAL.findall(s))
                    b["french_commentary"], changed = fix(s), True
            if changed:
                pages += 1
                if not dry:
                    path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{points} breaks {'would be ' if dry else ''}made on {pages} pages")


if __name__ == "__main__":
    main(sys.argv[1:])
