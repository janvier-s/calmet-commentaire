#!/usr/bin/env python3
"""Sort the pages of one Good_Calmet PDF by type (blank/plate/map/commentary/...).

Usage:
    set -a; . ./.env; set +a          # TYPESAFE_API_KEY
    uv run --with requests --with pillow --with numpy --with scipy \
        scripts/good_calmet_sort.py <pdf> <work_dir> [--cap-usd 0.50]

Writes <manifest_dir>/<pdf stem>.json (page type, confidence, header OCR,
size) and keeps extracted page JPEGs in <work_dir>/<pdf stem>/ for the later
crop step. Jev answers are cached in the manifest, so reruns never pay twice.
Alignment to source_images numbering is a separate step (good_calmet_align.py).
"""
import argparse, base64, io, json, os, re, subprocess, sys, time, uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import requests
from PIL import Image

API = "https://api.typesafe.ai/v1/systemone"
PRICE_PER_TOKEN = 0.042 / 1e6
MIN_SIDE = 280           # Jev rejects images smaller than this
BLANK_INK = 0.004        # ink fraction below which a page is blank without asking Jev
MANIFEST_DIR = Path(__file__).resolve().parent.parent / "data" / "good_calmet_manifests"

QUESTION = {"page_type": {
    "type": "choice",
    "instructions": "What kind of page of a printed 18th-century book is `page`?",
    "criteria": {
        "commentary": "A page of the verse-by-verse commentary: running header like COMMENTAIRE LITTERAL or SUR LA GENESE, Latin verse text with French commentary, often a footnote band at the bottom",
        "dissertation": "A page of a dissertation, preface or introductory essay (header like DISSERTATION or PREFACE), running prose, possibly footnotes",
        "frontback_matter": "Title page, dedication, approbation, privilege, table of contents or errata with sparse or list-like lines",
        "plate": "An engraved illustration, plate, frontispiece or ornamental image taking up most of the page",
        "map": "A map or fold-out chart",
        "blank": "An empty page, possibly with faint show-through",
    }}}


def extract(pdf: Path, out: Path) -> dict[int, Path]:
    """Extract embedded JPEGs untouched; return {pdf_page: largest jpg}."""
    out.mkdir(parents=True, exist_ok=True)
    if not any(out.glob("*.jpg")):
        subprocess.run(["pdfimages", "-j", "-p", str(pdf), str(out / "p")], check=True)
    best: dict[int, Path] = {}
    for f in out.glob("p-*.jpg"):
        page = int(f.name.split("-")[1])
        if page not in best or f.stat().st_size > best[page].stat().st_size:
            best[page] = f
    return best


def page_stats(path: Path) -> dict:
    im = Image.open(path).convert("L")
    a = np.asarray(im)
    ink = a < np.percentile(a, 80) - 60
    return {"w": im.width, "h": im.height, "ink": round(float(ink.mean()), 4)}


def header_ocr(path: Path) -> str:
    """First header line via tesseract (eng only installed): number + running title."""
    im = Image.open(path).convert("L")
    w, h = im.size
    tmp = path.with_suffix(".hdr.png")
    im.crop((0, int(h * .03), w, int(h * .12))).save(tmp)
    t = subprocess.run(["tesseract", str(tmp), "-", "--psm", "6"],
                       capture_output=True, text=True).stdout
    tmp.unlink(missing_ok=True)
    for line in t.split("\n"):
        if re.search(r"[A-Za-z]{4,}", line):
            return line.strip()[:60]
    return ""


def ask_jev(path: Path, key: str, spent: list) -> dict:
    im = Image.open(path).convert("RGB")
    im.thumbnail((768, 768))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    ref = str(uuid.uuid4())
    body = {"model": "jev-latest", "state": {"page": ref},
            "assets": {ref: {"type": "image", "format": "jpg",
                             "data_base64": base64.b64encode(buf.getvalue()).decode()}},
            "questions": QUESTION}
    r = None
    for attempt in range(5):
        try:
            r = requests.post(API, json=body, timeout=120, headers={
                "Authorization": "Bearer " + key, "TypeSafe-Danger-Zone-Images": "true"})
        except requests.exceptions.RequestException:
            time.sleep(2 ** attempt)
            continue
        if r.status_code in (429, 529):
            time.sleep(2 ** attempt)
            continue
        break
    if r is None or r.status_code != 200:
        return {"error": getattr(r, "status_code", "net")}
    j = r.json()
    a = j["answers"]["page_type"]
    spent[0] += j["usage"]["input_tokens"] * PRICE_PER_TOKEN
    return {"type": a["choice"], "conf": round(a["confidence"] or 0, 3), "src": "jev"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("work", type=Path)
    ap.add_argument("--cap-usd", type=float, default=0.50)
    args = ap.parse_args()
    key = os.environ["TYPESAFE_API_KEY"]

    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    mpath = MANIFEST_DIR / (args.pdf.stem + ".json")
    old = json.loads(mpath.read_text()) if mpath.exists() else {}
    pages_old = {p["pdf_page"]: p for p in old.get("pages", [])}

    files = extract(args.pdf, args.work / args.pdf.stem)
    spent = [0.0]
    pages = {}

    def job(pg):
        f = files[pg]
        prev = pages_old.get(pg)
        if prev and "type" in prev:
            return pg, prev
        rec = {"pdf_page": pg, "file": f.name, **page_stats(f)}
        if min(rec["w"], rec["h"]) < MIN_SIDE or rec["ink"] < BLANK_INK:
            rec.update(type="blank", conf=1.0, src="ink")
        elif spent[0] > args.cap_usd:
            rec["error"] = "cap"
        else:
            res = ask_jev(f, key, spent)
            rec.update(res)
            if rec.get("type") in ("commentary", "dissertation", "frontback_matter"):
                rec["header"] = header_ocr(f)
        return pg, rec

    with ThreadPoolExecutor(4) as ex:
        for pg, rec in ex.map(job, sorted(files)):
            pages[pg] = rec
    out = {"pdf": args.pdf.name, "n_pdf_pages": len(files),
           "pages": [pages[p] for p in sorted(pages)]}
    mpath.write_text(json.dumps(out, indent=1))
    errs = sum(1 for p in pages.values() if "error" in p)
    from collections import Counter
    print(args.pdf.name, dict(Counter(p.get("type", "ERR") for p in pages.values())),
          f"errors={errs} spent=${spent[0]:.4f}")


if __name__ == "__main__":
    main()
