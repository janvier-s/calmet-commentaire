#!/usr/bin/env python3
"""Local tesseract OCR of every text-like page in the Good_Calmet manifests.

Usage: uv run --with pillow scripts/good_calmet_ocr.py <work_dir> <manifest.json>...
Writes <work_dir>/<pdf stem>/ocr/<pdf_page>.txt (cached; free, offline).
Only used to match pages by content (see good_calmet_match.py), not as final text.
"""
import json, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TEXT_TYPES = {"commentary", "dissertation", "frontback_matter"}


def ocr(args):
    img, out = args
    if out.exists():
        return
    r = subprocess.run(["tesseract", str(img), "-", "--psm", "3", "-l", "eng"],
                       capture_output=True, text=True)
    out.write_text(r.stdout)


def main():
    work = Path(sys.argv[1])
    jobs = []
    for m in sys.argv[2:]:
        man = json.loads(Path(m).read_text())
        stem = Path(m).stem
        d = work / stem / "ocr"
        d.mkdir(parents=True, exist_ok=True)
        for p in man["pages"]:
            if p.get("type") in TEXT_TYPES:
                jobs.append((work / stem / p["file"], d / f"{p['pdf_page']}.txt"))
    print(len(jobs), "pages to OCR", flush=True)
    with ThreadPoolExecutor(6) as ex:
        for n, _ in enumerate(ex.map(ocr, jobs), 1):
            if n % 100 == 0:
                print(n, flush=True)
    print("done")


if __name__ == "__main__":
    main()
