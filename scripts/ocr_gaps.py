"""Words the scan has and the JSON lacks, from the cached Kraken OCR (scan_ocr.py): docs/ocr_gaps.json,
which the review editor shows as issues "WORDS MISSING (SCAN)", each with the words to put in.

    python3 ocr_gaps.py [volume ...]     (default: every volume with OCR cached)

Only pages already read by Kraken are looked at; run it again after more are read (it is quick).
"""
import json
import sys

import scan_ocr
from paths import DATA, DOCS

REPORT = DOCS / "ocr_gaps.json"


def page_gaps(vol, page):
    o = scan_ocr.ocr(vol, page, run=False)
    path = DATA / vol / "normalized" / f"page_{page:04d}.json"
    if not o or not path.exists():
        return []
    return [dict(g, vol=vol, page=page) for g in scan_ocr.gaps(o, json.loads(path.read_text(encoding="utf-8")))]


def main(argv):
    vols = argv or sorted(p.name for p in scan_ocr.OCR_CACHE.iterdir() if p.is_dir())
    old = json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.exists() else {"gaps": []}
    gaps = [g for g in old["gaps"] if g["vol"] not in vols]
    for vol in vols:
        pages = sorted(int(p.stem[5:]) for p in (scan_ocr.OCR_CACHE / vol).glob("page_*.json"))
        found = [g for p in pages for g in page_gaps(vol, p)]
        print(f"{vol}: {len(pages)} pages read, {len(found)} gaps on {len({g['page'] for g in found})} pages")
        gaps += found
    gaps.sort(key=lambda g: (g["vol"], g["page"], g["words"][0]))
    REPORT.write_text(json.dumps({"gaps": gaps}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
