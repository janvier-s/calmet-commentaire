"""Words the scan has and the JSON lacks, and words the scan prints in italics and the JSON in roman (or
the other way), from the cached Kraken OCR (scan_ocr.py): docs/ocr_gaps.json, which the review editor
shows as issues "WORDS MISSING (SCAN)", "ITALICS (SCAN)", "WORD DIFFERS (SCAN)" and "NOT ON SCAN",
each with its change. Italics logged as false positives in NOTES.md are left out; words missing and not
on the scan in the verses' Latin and margin are left out (nearly all misreads).

    python3 ocr_gaps.py [volume ...]     (default: every volume with OCR cached)

Only pages already read by Kraken are looked at; run it again after more are read (it is quick).
"""
import datetime
import json
import os
import re
import sys
import time

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


def page_report(vol, page, data=None):
    """The page's gaps, italics, words that differ, words the scan lacks; `data`: the page's text, else the
    one in data/."""
    global FP
    FP = FP or italic_false_positives()
    o = scan_ocr.ocr(vol, page, run=False)
    path = DATA / vol / "normalized" / f"page_{page:04d}.json"
    if not o or (data is None and not path.exists()):
        return [], [], [], []
    data = data if data is not None else json.loads(path.read_text(encoding="utf-8"))
    al = scan_ocr.align(o, data)
    res = al["words"]
    fx = scan_ocr.align(o, data, fix=True)  # every list from the fixed alignment (same words, same indexes): the plain one pairs across the verses' columns
    at = dict(vol=vol, page=page)
    word = lambda r: r["old"].replace("_", "").rstrip(" \t;:?!.,").strip().lower()
    its = [r for r in scan_ocr.italics(o, data, fx["words"]) if (vol, page, word(r)) not in FP[0] and word(r) not in FP[1]]
    def box(r):
        i, j = r["words"] if "words" in r else (r["word"], r["word"])
        return scan_ocr.scan_box(o["size"], res, i, j)
    scope = lambda r: not scan_ocr.OUT_OF_SCOPE.fullmatch(r["path"])  # not the verses' Latin and margin
    return ([dict(g, **at, box=box(g)) for g in scan_ocr.gaps(o, data, fx["words"]) if scope(g)],
            [dict({k: v for k, v in r.items() if k != "new"}, **at, box=box(r)) for r in its],
            [dict(r, **at, box=box(r)) for r in scan_ocr.differs(o, data, fx["words"])],
            [dict(r, **at, box=box(r)) for r in scan_ocr.unscanned(o, data, fx) if scope(r)])


def _write(report, out):
    for v in out.values():
        v.sort(key=lambda g: (g["vol"], g["page"], g["words"][0] if "words" in g else g.get("word", g.get("a", 0))))
    tmp = report.with_name(report.name + ".tmp")
    tmp.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(report)


def update_page(report, vol, page, data):
    """The page's entries of `report` (an ocr_gaps.json) made again from `data` (the text just saved), the
    others kept: the issues follow the edits without a run over the volume. False: no OCR for the page."""
    if scan_ocr.ocr(vol, page, run=False) is None:
        return False
    old = json.loads(report.read_text(encoding="utf-8")) if report.exists() else {}
    found = page_report(vol, page, data)
    _write(report, {k: [g for g in old.get(k) or [] if (g["vol"], g["page"]) != (vol, page)] + found[n]
                    for n, k in enumerate(KINDS)})
    return True


def main(argv):
    vols = argv or sorted(p.name for p in scan_ocr.OCR_CACHE.iterdir() if p.is_dir())
    old = json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.exists() else {}
    out = {k: [g for g in old.get(k) or [] if g["vol"] not in vols] for k in KINDS}
    for vol in vols:
        t0 = time.time()
        pages = sorted(int(p.stem[5:]) for p in (scan_ocr.OCR_CACHE / vol).glob("page_*.json"))
        found = [page_report(vol, p) for p in pages]
        got = {k: [g for f in found for g in f[n]] for n, k in enumerate(KINDS)}
        dur = scan_ocr._fmt_duration(time.time() - t0)
        now_time = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[{now_time}] {vol}: {len(pages)} pages analyzed in {dur}, " + ", ".join(f"{len(v)} {k} on {len({g['page'] for g in v})} pages" for k, v in got.items()), flush=True)
        for k in KINDS:
            out[k] += got[k]
    _write(REPORT, out)


if __name__ == "__main__":
    main(sys.argv[1:])
