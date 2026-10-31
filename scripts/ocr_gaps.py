"""Words the scan has and the JSON lacks, and words the scan prints in italics and the JSON in roman (or
the other way), from the cached Kraken OCR (scan_ocr.py): docs/ocr_gaps.json, which the review editor
shows as issues "WORDS MISSING (SCAN)" and "ITALICS (SCAN)", each with its change.

    python3 ocr_gaps.py [volume ...]     (default: every volume with OCR cached)

Only pages already read by Kraken are looked at; run it again after more are read (it is quick).
"""
import json
import sys

import scan_ocr
from paths import DATA, DOCS

REPORT = DOCS / "ocr_gaps.json"


def page_report(vol, page):
    """The page's gaps and italics."""
    o = scan_ocr.ocr(vol, page, run=False)
    path = DATA / vol / "normalized" / f"page_{page:04d}.json"
    if not o or not path.exists():
        return [], []
    data = json.loads(path.read_text(encoding="utf-8"))
    res = scan_ocr.align(o, data)["words"]
    at = dict(vol=vol, page=page)
    return ([dict(g, **at) for g in scan_ocr.gaps(o, data, res)],
            [dict({k: v for k, v in r.items() if k != "new"}, **at) for r in scan_ocr.italics(o, data, res)])


def main(argv):
    vols = argv or sorted(p.name for p in scan_ocr.OCR_CACHE.iterdir() if p.is_dir())
    old = json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.exists() else {}
    out = {k: [g for g in old.get(k) or [] if g["vol"] not in vols] for k in ("gaps", "italics")}
    for vol in vols:
        pages = sorted(int(p.stem[5:]) for p in (scan_ocr.OCR_CACHE / vol).glob("page_*.json"))
        found = [page_report(vol, p) for p in pages]
        gaps, its = [g for f in found for g in f[0]], [r for f in found for r in f[1]]
        print(f"{vol}: {len(pages)} pages read, {len(gaps)} gaps on {len({g['page'] for g in gaps})} pages, "
              f"{len(its)} italics to check on {len({r['page'] for r in its})}")
        out["gaps"] += gaps
        out["italics"] += its
    for v in out.values():
        v.sort(key=lambda g: (g["vol"], g["page"], g["words"][0]))
    REPORT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
