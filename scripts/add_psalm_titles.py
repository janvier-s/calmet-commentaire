"""Insert the Psalm titles missing from the transcription as verse 0, with the Vulgate Latin.

Calmet prints the title unnumbered (verse 0) above verse 1. For each psalm given, a
verse 0 is inserted before the psalm's first transcribed verse:
  - latin: the Vulgate title (check against the scan)
  - french: "" (to type from the scan)
  - annotations: a note saying the Latin came from the Vulgate
Where the Vulgate's verse 1 also holds the first line and Calmet's verse 1 is missing
(Ps 12, 14, 34), that line is inserted as verse 1 too. Where the title runs over Vulgate
verses 1-2 (Ps 51, 53), both make the title. Psalms that already have a verse 0 are left alone.

Usage: python3 add_psalm_titles.py [--dry-run] PSALM ...   (volume 21a_psaumes)
"""
import json
import sys

import psalms_check as P
from paths import DATA

VOLUME = "21a_psaumes"
NOTE = ("Latin from the Vulgate (title missing from the transcription): check it against the scan, "
        "keep only what Calmet prints, and type his French")
# where the Vulgate title ends inside verse 1, the first line (Calmet's verse 1) starts with:
FIRST_LINE = {12: "Usquequo", 14: "Domine, quis", 34: "Judica", 65: "Jubilate"}
TWO_VERSE_TITLE = {51, 53}


def main(argv):
    dry = "--dry-run" in argv
    psalms = [int(a) for a in argv if not a.startswith("--")]
    rows, _ = P.check(VOLUME)
    pages = {}
    for ps in sorted(psalms, reverse=True):  # last first, so indexes on a shared page stay right
        rs = [r for r in rows if r["psalm"] == ps]
        if any(r["number"] == 0 for r in rs):
            print(f"Ps {ps}: already has a verse 0, skipped")
            continue
        first = rs[0]
        v1 = P.VULGATE_TEXT[ps][1]
        new = []
        if ps in FIRST_LINE:
            cut = v1.index(FIRST_LINE[ps])
            title, line = v1[:cut].strip(), v1[cut:].strip()
            new.append(title)
            if first["number"] != 1:  # Calmet's verse 1 is missing too
                new.append(line)
        else:
            new.append(v1 + (" " + P.VULGATE_TEXT[ps][2] if ps in TWO_VERSE_TITLE else ""))
        path = DATA / VOLUME / "normalized" / f"page_{first['page']:04d}.json"
        d = pages.setdefault(path, json.loads(path.read_text(encoding="utf-8")))
        for n, latin in reversed(list(enumerate(new))):
            d["verses"].insert(first["index"], {"verse_number": n, "latin": latin, "french": "", "annotations": NOTE})
            print(f"Ps {ps}: verse {n} on page {first['page']}: {latin}")
    if not dry:
        for path, d in pages.items():
            path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(pages)} pages {'would be ' if dry else ''}changed")


if __name__ == "__main__":
    main(sys.argv[1:])
