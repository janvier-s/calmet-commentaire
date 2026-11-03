#!/usr/bin/env python3
"""Side-aware crop of Good_Calmet commentary pages (local, free, native resolution).

Usage:
    uv run --with pillow --with numpy scripts/good_calmet_crop.py \
        <work_dir> <out_dir> <alignment.json> [--only pdf:page,...]

1. Side (left/right-hand page) comes from the spine shadow on the outer 4% strips.
2. Per PDF and side, the text block is the median ink extent over its commentary
   pages: the stable outer edge is kept, the width is the median plus a margin.
3. Footnote strip: x-range of the side box, y from the faint footnote rule
   (good_calmet_crop_test.ink_boxes) down to before the signature mark.
No sharpening or upscaling. Pages whose ink spills outside the box, or where no
rule is found, get flag="check" in <out_dir>/crops.json.
"""
import argparse, json, sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from good_calmet_crop_test import ink_boxes  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MAN = ROOT / "data" / "good_calmet_manifests"


def side_of(g: np.ndarray) -> str:
    w = g.shape[1]
    left, right = g[:, : int(w * .04)].mean(), g[:, -int(w * .04):].mean()
    return "R" if left < right else "L"          # spine at left = right-hand page


def extent(g: np.ndarray):
    h, w = g.shape
    m = g < np.percentile(g, 80) - 60
    m[:, : int(w * .06)] = False; m[:, int(w * .97):] = False
    m[: int(h * .02)] = False; m[int(h * .97):] = False
    cols = np.flatnonzero(m.sum(0) > h * .006); rows = np.flatnonzero(m.sum(1) > w * .01)
    if not len(cols) or not len(rows):
        return None
    return cols[0] / w, cols[-1] / w, rows[0] / h, rows[-1] / h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work", type=Path); ap.add_argument("out", type=Path); ap.add_argument("align", type=Path)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    only = set(a.only.split(",")) if a.only else None
    pages = [p for p in json.loads(a.align.read_text()) if p["type"] == "commentary"]

    files = {}
    for pdf in {p["pdf"] for p in pages}:
        m = json.loads((MAN / f"{pdf}.json").read_text())
        files[pdf] = {q["pdf_page"]: q["file"] for q in m["pages"]}

    # pass 1: side + extents for every commentary page
    info = {}
    for p in pages:
        g = np.asarray(Image.open(a.work / p["pdf"] / files[p["pdf"]][p["pdf_page"]]).convert("L"), dtype=np.int16)
        info[(p["pdf"], p["pdf_page"])] = (side_of(g), extent(g), g.shape)
    boxes = {}
    for pdf in {k[0] for k in info}:
        for sd in "LR":
            ex = np.array([v[1] for k, v in info.items() if k[0] == pdf and v[0] == sd and v[1]])
            if len(ex) < 5:
                continue
            width = float(np.median(ex[:, 1] - ex[:, 0])) + .015   # p90 is polluted by outlier pages
            top, bot = float(np.percentile(ex[:, 2], 10)), float(np.percentile(ex[:, 3], 90))
            if sd == "R":
                left = float(np.median(ex[:, 0])); right = left + width
            else:
                right = float(np.median(ex[:, 1])); left = right - width
            boxes[(pdf, sd)] = (left - .01, top - .01, right + .01, bot + .01)
    print({f"{k[0][:2]}{k[1]}": [round(x, 3) for x in v] for k, v in boxes.items()})

    out = []
    for p in pages:
        key = (p["pdf"], p["pdf_page"])
        if only and f"{p['pdf'][:2]}:{p['pdf_page']}" not in only:
            continue
        sd, ex, _ = info[key]
        if (p["pdf"], sd) not in boxes:
            continue
        im = Image.open(a.work / p["pdf"] / files[p["pdf"]][p["pdf_page"]]).convert("RGB")
        w, h = im.size
        bx = boxes[(p["pdf"], sd)]
        px = (max(0, int(bx[0] * w)), max(0, int(bx[1] * h)), min(w, int(bx[2] * w)), min(h, int(bx[3] * h)))
        stem = f"{p['pdf'][:2]}_{p['pdf_page']:04d}"
        im.crop(px).save(a.out / f"{stem}.png")
        flag = []
        if ex:
            spill = {"L": bx[0] - ex[0], "R": ex[1] - bx[2], "T": bx[1] - ex[2], "B": ex[3] - bx[3]}
            outer = "R" if sd == "R" else "L"          # margin notes sit on the outer edge
            if any(v > .005 for k, v in spill.items() if k != outer):
                flag.append("ink-outside-box")
            elif spill[outer] > .005:
                flag.append("margin-note")             # informational, outside the text column
        _, fn = ink_boxes(im)
        rec = {"pdf": p["pdf"], "pdf_page": p["pdf_page"], "stem": stem, "side": sd, "box": px,
               "source": p.get("source")}
        if fn:
            fpx = (px[0], int(fn[1]), px[2], int(min(h, fn[3])))
            im.crop(fpx).save(a.out / f"{stem}.fn.png"); rec["fn_box"] = fpx
        else:
            flag.append("no-footnote-rule")      # also true for pages that have no footnotes
        rec["flag"] = ",".join(flag)
        out.append(rec)
    (a.out / "crops.json").write_text(json.dumps(out, indent=1))
    from collections import Counter
    print(len(out), "pages;", dict(Counter(r["flag"] or "ok" for r in out)))


if __name__ == "__main__":
    main()
