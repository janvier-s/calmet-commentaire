"""Words the scan has and the JSON lacks, and words the scan prints in italics and the JSON in roman (or
the other way), from the cached Kraken OCR (scan_ocr.py): docs/ocr_gaps.json, which the review editor
shows as issues "WORDS MISSING (SCAN)", "ITALICS (SCAN)", "WORD DIFFERS (SCAN)" and "NOT ON SCAN",
each with its change. Italics logged as false positives in NOTES.md are left out.

    python3 ocr_gaps.py [volume ...]     (default: every volume with OCR cached)

Only pages already read by Kraken are looked at; run it again after more are read (it is quick).
"""
import json
import os
import re
import sys

import scan_ocr
from pathlib import Path

from paths import DATA, DOCS, STUDIUM

REPORT = DOCS / "ocr_gaps.json"


KINDS = ("gaps", "italics", "differs", "unscanned")
NOTES = Path(os.environ.get("CALMET_NOTES") or STUDIUM.parent / "NOTES.md")


def italic_false_positives():
    """NOTES.md's FALSE POSITIVE ITALICS ("word (vol p.N)" a line): {(vol, page, word)}, and the words
    logged on two pages or more, no longer flagged anywhere."""
    text = NOTES.read_text(encoding="utf-8") if NOTES.exists() else ""
    sec = text.split("## FALSE POSITIVE ITALICS", 1)[1].split("\n## ", 1)[0] if "## FALSE POSITIVE ITALICS" in text else ""
    seen = {(m[2], int(m[3]), m[1].strip().lower()) for m in re.finditer(r"^[-*\s]*(.+?) \((\S+) p\.(\d+)\)", sec, re.M)}
    pages = {}
    for vol, page, w in seen:
        pages.setdefault(w, set()).add((vol, page))
    return seen, {w for w, ps in pages.items() if len(ps) >= 2}


FP = None


def page_report(vol, page):
    """The page's gaps, italics, words that differ, words the scan lacks."""
    global FP
    FP = FP or italic_false_positives()
    o = scan_ocr.ocr(vol, page, run=False)
    path = DATA / vol / "normalized" / f"page_{page:04d}.json"
    if not o or not path.exists():
        return [], [], [], []
    data = json.loads(path.read_text(encoding="utf-8"))
    al = scan_ocr.align(o, data)
    res = al["words"]
    at = dict(vol=vol, page=page)
    word = lambda r: r["old"].replace("_", "").rstrip(" \t;:?!.,").strip().lower()
    its = [r for r in scan_ocr.italics(o, data, res) if (vol, page, word(r)) not in FP[0] and word(r) not in FP[1]]
    def box(r):
        i, j = r["words"] if "words" in r else (r["word"], r["word"])
        return scan_ocr.scan_box(o["size"], res, i, j)
    return ([dict(g, **at, box=box(g)) for g in scan_ocr.gaps(o, data, res)],
            [dict({k: v for k, v in r.items() if k != "new"}, **at, box=box(r)) for r in its],
            [dict(r, **at, box=box(r)) for r in scan_ocr.differs(o, data, res)],
            [dict(r, **at, box=box(r)) for r in scan_ocr.unscanned(o, data, al)])


def main(argv):
    vols = argv or sorted(p.name for p in scan_ocr.OCR_CACHE.iterdir() if p.is_dir())
    old = json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.exists() else {}
    out = {k: [g for g in old.get(k) or [] if g["vol"] not in vols] for k in KINDS}
    for vol in vols:
        pages = sorted(int(p.stem[5:]) for p in (scan_ocr.OCR_CACHE / vol).glob("page_*.json"))
        found = [page_report(vol, p) for p in pages]
        got = {k: [g for f in found for g in f[n]] for n, k in enumerate(KINDS)}
        print(f"{vol}: {len(pages)} pages read, " + ", ".join(f"{len(v)} {k} on {len({g['page'] for g in v})} pages" for k, v in got.items()))
        for k in KINDS:
            out[k] += got[k]
    for v in out.values():
        v.sort(key=lambda g: (g["vol"], g["page"], g["words"][0] if "words" in g else g.get("word", g.get("a", 0))))
    REPORT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
