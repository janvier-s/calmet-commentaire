"""Footnotes pasted at the end of a comment, as lines "(a) …", moved into the page's footnotes.

  python3 pasted_footnotes.py <volume|book|all> ... [--apply]

Only on pages that have no footnotes of their own (Jérémie mostly): the lines stay on their page.
"""
import json
import re
import sys

from paths import pages, volumes_of

TAIL = re.compile(r"(?:\n\s*\([a-z]\)\s+[^\n]*)+\s*$")
LINE = re.compile(r"^\s*\(([a-z])\)\s+(.*\S)\s*$")


def main(argv):
    apply = "--apply" in argv
    vols = volumes_of([a for a in argv if not a.startswith("--")])
    if not vols:
        sys.exit(__doc__)
    done = 0
    for vol in vols:
        for p in pages(vol):
            raw = p.read_text(encoding="utf-8")
            d = json.loads(raw)
            if d.get("footnotes"):
                continue
            notes = []
            for b in d.get("commentary") or []:
                t = b.get("french_commentary") or ""
                m = TAIL.search(t)
                if not m:
                    continue
                notes += [LINE.match(x).groups() for x in m.group().split("\n") if x.strip()]
                b["french_commentary"] = t[:m.start()].rstrip()
            if not notes:
                continue
            notes.sort()
            print(f"{vol}/{p.stem}: " + ", ".join(f"({k}) {v[:40]}" for k, v in notes))
            done += 1
            if apply:
                d["footnotes"] = [{"marker": f"({k})", "text": v} for k, v in notes]
                p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + ("\n" if raw.endswith("\n") else ""),
                             encoding="utf-8")
    print(f"{done} pages" + (" written" if apply else ""))


if __name__ == "__main__":
    main(sys.argv[1:])
