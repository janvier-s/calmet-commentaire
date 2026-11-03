"""Kraken OCR of the Good_Calmet crops (data/good_calmet/<pdf>/page_NNNN.png, listed in crops.json), with
scan_ocr.py's model, ALTO parsing and slant step. The output has cache/ocr's format, in the crop's own
pixels, in cache/good_ocr/<pdf>/page_NNNN.json (cache/ocr is never touched).

    python3 good_calmet_kraken.py <pdf> [first-last]   OCR the pages of a PDF (or a range) not yet cached
    python3 good_calmet_kraken.py --vol 01_genese      every page of that volume's PDFs
    python3 good_calmet_kraken.py --ab [N]             A/B on N (10) Genèse pages that have a source scan:
                                                       the plain crop against it upscaled 2x, set against
                                                       the source scan's OCR and the normalized JSON
"""
import datetime
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from paths import DATA, SCRIPTS
import scan_ocr

GOOD = DATA / "good_calmet"
GOOD_OCR = SCRIPTS / "cache" / "good_ocr"
AB_OCR = SCRIPTS / "cache" / "good_ocr_ab"  # the A/B's variants: <variant>/<pdf>/page_NNNN.json
DEFAULT_VOL = "01_genese"  # a crops.json record without "vol"


def crops():
    recs = json.loads((GOOD / "crops.json").read_text(encoding="utf-8")).values()
    return [{**r, "vol": r.get("vol") or DEFAULT_VOL} for r in recs]


def crop_path(pdf, page):
    return GOOD / pdf / f"page_{page:04d}.png"


def cache_in(root):
    return lambda pdf, page: root / pdf / f"page_{page:04d}.json"


cache_path = cache_in(GOOD_OCR)


def _upscale(scans, tmp, scale):
    """The crops [(page, image)] enlarged `scale` times (Lanczos), in tmp."""
    from PIL import Image
    out = []
    for page, img in scans:
        im = Image.open(img)
        p = Path(tmp) / f"page_{page:04d}.png"
        im.resize((im.width * scale, im.height * scale), Image.LANCZOS).save(p)
        out.append((page, p))
    return out


def _downscale(f, scale):
    """The cached OCR of an upscaled crop back in the crop's pixels (the slant is the same at any size)."""
    o = json.loads(f.read_text(encoding="utf-8"))
    sc = lambda b: [round(v / scale) for v in b]
    o["size"] = sc(o["size"])
    for ln in o["lines"]:
        ln["box"] = sc(ln["box"])
        for w in ln["words"]:
            w["box"] = sc(w["box"])
    f.write_text(json.dumps(o, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def read(pdf, pages, cache=cache_path, scale=1):
    """One Kraken run over the pages of a PDF, each cached by `cache`."""
    scans = [(p, crop_path(pdf, p)) for p in pages]
    if scale == 1:
        scan_ocr.kraken(pdf, scans, cache)
        return
    with tempfile.TemporaryDirectory() as tmp:
        scan_ocr.kraken(pdf, _upscale(scans, tmp, scale), cache)
    for p in pages:
        if cache(pdf, p).exists():
            _downscale(cache(pdf, p), scale)


def run(pdf, pages, cache=cache_path, scale=1, label=None):
    """OCR the pages not yet cached, CHUNK a Kraken run (resumable), with a progress line a chunk."""
    todo = [p for p in pages if not cache(pdf, p).exists()]
    now = lambda: datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{now()}] {label or pdf}: {len(pages) - len(todo)} pages cached, {len(todo)} to OCR", flush=True)
    t0 = time.time()
    for n in range(0, len(todo), scan_ocr.CHUNK):
        chunk = todo[n:n + scan_ocr.CHUNK]
        try:
            read(pdf, chunk, cache, scale)
        except subprocess.CalledProcessError as e:  # page by page, to find the one that fails
            print(f"  p.{chunk[0]}-{chunk[-1]}: Kraken failed, page by page: {e.stderr.decode(errors='replace')[-200:]}", flush=True)
            for p in chunk:
                try:
                    read(pdf, [p], cache, scale)
                except subprocess.CalledProcessError:
                    print(f"  p.{p}: Kraken failed", flush=True)
        done, el = n + len(chunk), time.time() - t0
        left = f", ~{scan_ocr._fmt_duration(el / done * (len(todo) - done))} left" if done < len(todo) else ""
        print(f"[{now()}]   {done}/{len(todo)} (p.{chunk[-1]}) · {scan_ocr._fmt_duration(el)} elapsed{left}", flush=True)
    return len(todo)


# --- A/B ---
def _score(o, datas):
    """(words read, words the fixed alignment finds in the JSON (ok or near), words it weighs (not skip)).
    `datas`: the source page and two either side, since a crop's text may run onto them; a word is found
    if it is found in any (the alignment's words are the OCR's, in the same order, against each page)."""
    if o is None:
        return None
    runs = [scan_ocr.align(o, d, fix=True)["words"] for d in datas]
    found = [any(r[i]["s"] in ("ok", "near") for r in runs) for i in range(len(runs[0]))]
    skip = [not f and any(r[i]["s"] == "skip" for r in runs) for i, f in enumerate(found)]  # skipped where it is
    return (sum(len(ln["words"]) for ln in o["lines"]), sum(f for f, k in zip(found, skip) if not k),
            sum(not k for k in skip))


def ab(n=10):
    recs = [r for r in crops() if r["vol"] == DEFAULT_VOL and r.get("source") and not r.get("flag")]
    by_pdf = {}
    for r in recs:
        by_pdf.setdefault(r["pdf"], []).append(r)
    picked = []  # spread over the PDFs, and over each PDF's pages
    while len(picked) < n and any(by_pdf.values()):
        for pdf, rs in by_pdf.items():
            if rs and len(picked) < n:
                picked.append(rs.pop(len(rs) // 2 if len(picked) % 2 else len(rs) // 5))
    variants = {"plain": 1, "x2": 2}
    for name, scale in variants.items():
        cache = cache_in(AB_OCR / name)
        for pdf in sorted({r["pdf"] for r in picked}):
            run(pdf, sorted(r["pdf_page"] for r in picked if r["pdf"] == pdf), cache, scale, f"{name} {pdf}")
    tot = {k: [0, 0, 0] for k in ["source", *variants]}
    print(f"\n{'page':28} {'source scan':>18} " + " ".join(f"{k:>18}" for k in variants))
    for r in picked:
        src = int(r["source"].split("_")[1])
        norm = [DATA / DEFAULT_VOL / "normalized" / f"page_{s:04d}.json" for s in range(src - 2, src + 3)]
        data = [json.loads(f.read_text(encoding="utf-8")) for f in norm if f.exists()]
        cells = {"source": _score(scan_ocr.ocr(DEFAULT_VOL, src, run=False), data)}
        for name in variants:
            f = cache_in(AB_OCR / name)(r["pdf"], r["pdf_page"])
            cells[name] = _score(json.loads(f.read_text(encoding="utf-8")) if f.exists() else None, data)
        row = []
        for k, c in cells.items():
            if c:
                tot[k] = [a + b for a, b in zip(tot[k], c)]
            row.append(f"{c[0]:5d} w {c[1] / max(c[2], 1):6.1%}" if c else f"{'-':>18}")
        print(f"{r['pdf'] + ' p.' + str(r['pdf_page']) + ' ~' + str(src):28} " + " ".join(f"{x:>18}" for x in row))
    print(f"{'total':28} " + " ".join(f"{f'{t[0]:5d} w {t[1] / max(t[2], 1):6.1%}':>18}" for t in tot.values()))
    print("\nw: words read; %: of the words weighed (not skip), the share found in the normalized JSON (ok or near)\nof the source page or the two pages either side."
          "\nThe source scan holds the whole source page; a crop may hold part of it, or run onto the next.")


def main(argv):
    if not argv:
        sys.exit(__doc__)
    if argv[0] == "--ab":
        return ab(int(argv[1]) if len(argv) > 1 else 10)
    recs = crops()
    if argv[0] == "--vol":
        if len(argv) < 2:
            sys.exit(__doc__)
        jobs = {}
        for r in recs:
            if r["vol"] == argv[1]:
                jobs.setdefault(r["pdf"], []).append(r["pdf_page"])
        if not jobs:
            sys.exit(f"no crop of volume {argv[1]} in crops.json")
    else:
        pages = [r["pdf_page"] for r in recs if r["pdf"] == argv[0]]
        if not pages:
            sys.exit(f"no crop of {argv[0]} in crops.json")
        if len(argv) > 1:
            a, _, b = argv[1].partition("-")
            pages = [p for p in pages if int(a) <= p <= int(b or a)]
        jobs = {argv[0]: pages}
    t0, total = time.time(), 0
    for pdf, pages in sorted(jobs.items()):
        total += run(pdf, sorted(p for p in pages if crop_path(pdf, p).exists()))
    if total:
        took = time.time() - t0
        print(f"{total} pages OCR'd in {scan_ocr._fmt_duration(took)} ({took / total:.1f}s/page)", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
