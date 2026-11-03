#!/usr/bin/env python3
"""Margin crop of page scans: per page, the printed block (header, both columns, margin notes,
footnotes, signature and catchword) plus a small pad. Originals are never touched.

    uv run --with pillow --with numpy python margin_crop.py source <vol> [<vol> ...] | --all  [--redo]
        data/<vol>/source_images/<part>/[<section>/]page_NNNN.png -> the same path under
        data/<vol>/source_images_cropped/ (pages already cropped are kept unless --redo)
        and data/<vol>/source_images_cropped/crops.json: {"<part>/page_NNNN": {"box": [x0, y0, x1, y1],
        "size": [w, h], "flag": ...}}. The crop always contains every Kraken word of the page
        (cache/ocr/<vol>/page_NNNN.json); the Kraken cache stays in the original's coordinates,
        `ocr_on_crop()` shifts it onto the crop.
    uv run --with pillow --with numpy python margin_crop.py good <work_dir> <out_dir> <alignment.json>
        Good_Calmet commentary pages (the PDFs' pages extracted in <work_dir>/<pdf>/, see the manifests)
        -> <out_dir>/<pdf>/page_NNNN.png (the PDF's page number) and <out_dir>/crops.json:
        {"<pdf>/page_NNNN": {"source": the source_images page it matches, "box", "size", "flag"}}.
        The usual <out_dir>: data/good_calmet/.

    python margin_crop.py verify <vol> ... | --all     every Kraken word inside its page's crop?

flag "narrow": the block is narrower than the volume's 25th percentile by 4 % of the width (a column cut
off? a half-empty page, a plate) and "full" (nothing trimmed): look at those. "wide" (margin notes, specks) is informational.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import DATA, SCRIPTS  # noqa: E402

OCR_CACHE = SCRIPTS / "cache" / "ocr"
PAD = 0.012  # of the width, each side
GOOGLE = (0.65, 0.95)  # the "Digitized by Google" mark: x, y (fractions) of its corner's top left


def _runs(idx, gap):
    """Index runs (sorted ints) merged across gaps <= gap: [(first, last), ...]."""
    if not len(idx):
        return []
    cut = np.flatnonzero(np.diff(idx) > gap)
    return list(zip(idx[np.r_[0, cut + 1]], idx[np.r_[cut, len(idx) - 1]]))


def ink_mask(g, edge_x=0.01, edge_y=0.01, mask=None):
    h, w = g.shape
    paper, ink = np.percentile(g, 80), np.percentile(g, 1)
    m = g < min(paper - 60, (paper + ink) / 2)  # halfway: grey show-through on dull scans is not ink
    ex, ey = int(w * edge_x), int(h * edge_y)
    m[:, :ex] = False; m[:, w - ex:] = False
    m[:ey] = False; m[h - ey:] = False
    if mask:
        m[int(h * mask[1]):, int(w * mask[0]):] = False
    return m


def extend(m, box):
    """box widened, band by band (a line and a half high), through ink that continues the block
    outwards (a margin note in small, faint type): gaps of up to 2 % of the width, within the
    band, so dust elsewhere on the page does not count; 30 px of ink in pieces as tall as part of a
    letter at least."""
    h, w = m.shape
    x0, y0, x1, y1 = box
    gap = int(w * 0.02)
    nx0, nx1 = x0, x1
    bh = max(8, int(h * 0.025))  # about a line and a half; bands overlap by half
    for a in range(y0, y1 + 1, bh // 2):
        band = m[a:min(y1 + 1, a + bh)]
        cols = band.sum(0)
        for step, edge in ((1, x1), (-1, x0)):
            x, far, got = edge, edge, 0
            while True:
                win = range(x + step, x + step * (gap + 1), step)
                hit = [c for c in win if 0 <= c < w and cols[c]]
                if not hit:
                    break
                c = hit[0]
                piece = c  # the piece of ink starting at c, to its first blank column
                while 0 <= piece + step < w and cols[piece + step]:
                    piece += step
                lo, hi = sorted((c, piece))
                ys = np.flatnonzero(band[:, lo:hi + 1].any(1))
                if ys[-1] - ys[0] + 1 >= max(5, h * 0.004):  # as tall as part of a letter, not dust
                    got += cols[lo:hi + 1].sum()
                x = piece
                if got >= 30:  # a speck alone does not move the edge; a dot after a word does
                    far = piece
            nx1, nx0 = (max(nx1, far), nx0) if step == 1 else (nx1, min(nx0, far))
    return [int(nx0), y0, int(nx1), y1]


def text_block(g, edge_x=0.01, edge_y=0.01, mask=None):
    """[x0, y0, x1, y1] of the printed block of greyscale page g, or None.

    Ink is darker than the paper by 60+ levels. Columns with ink are merged across gaps of up
    to 4 % of the width (margin notes join the column they sit beside); the widest group is
    the block. Rows: from the first to the last ink row in those columns (specks of under
    0.1 % of the ink dropped when 5 % of the height away). edge_*: margins masked as shadow;
    mask: (x, y) fractions, the corner from there to the bottom right is masked (the
    "Digitized by Google" mark of source_images)."""
    h, w = g.shape
    m = ink_mask(g, edge_x, edge_y, mask)
    col = m.sum(0)
    ok = (col >= 12) & (col < 0.6 * h)  # a column dark from top to bottom is a shadow or a fold
    groups = _runs(np.flatnonzero(ok), int(w * 0.04))
    if not groups:
        return None
    x0, x1 = max(groups, key=lambda r: (r[1] - r[0], -abs((r[0] + r[1]) / 2 - w / 2)))
    rowink = m[:, x0:x1 + 1].sum(1)
    rows = _runs(np.flatnonzero(rowink >= max(3, 0.01 * (x1 - x0))), int(h * 0.05))  # dust: a few px a row
    mass = [rowink[r[0]:r[1] + 1].sum() for r in rows]
    # specks and dirt off on their own: under 0.1 % of the page's ink (a signature mark is ~0.3 %)
    rows = [r for r, k in zip(rows, mass) if k >= 0.001 * sum(mass)] or rows
    if not rows:
        return None
    # every group: a blank band (end of a book, a vignette below) must not cut text off
    y0, y1 = rows[0][0], rows[-1][1]
    return extend(m, [int(x0), int(y0), int(x1), int(y1)])


def pad_box(b, w, h):
    p = int(w * PAD)
    return [max(0, b[0] - p), max(0, b[1] - p), min(w, b[2] + 1 + p), min(h, b[3] + 1 + p)]


def kraken_box(vol, page):
    f = OCR_CACHE / vol / f"{page}.json"
    if not f.exists():
        return None
    o = json.loads(f.read_text())
    W, H = o["size"]
    ws = [b for ln in o["lines"] for wd in ln["words"] for b in [wd["box"]]
          if b[2] and b[3] and not (b[1] >= GOOGLE[1] * H and b[0] >= GOOGLE[0] * W)]  # its misreadings of the mark
    if not ws:
        return None
    return [min(b[0] for b in ws), min(b[1] for b in ws),
            max(b[0] + b[2] for b in ws), max(b[1] + b[3] for b in ws)]


def ocr_on_crop(vol, page, crops=None):
    """The Kraken OCR of page (e.g. "page_0103") in the cropped image's coordinates."""
    crops = crops or json.loads((DATA / vol / "source_images_cropped" / "crops.json").read_text())
    x0, y0, x1, y1 = crops[f"commentaire/{page}"]["box"]
    o = json.loads((OCR_CACHE / vol / f"{page}.json").read_text())
    sh = lambda b: [b[0] - x0, b[1] - y0, b[2], b[3]]
    return {**o, "size": [x1 - x0, y1 - y0],
            "lines": [{**ln, "box": sh(ln["box"]), "words": [{**wd, "box": sh(wd["box"])} for wd in ln["words"]]}
                      for ln in o["lines"]]}


def flag_widths(recs, key):
    """flag "narrow" where the block is 4 % of the width narrower than its group's 25th percentile
    (a column cut off?); "wide" (margin notes, specks) is only informational."""
    groups = {}
    for r in recs.values():
        if r.get("block"):
            groups.setdefault(key(r), []).append((r["block"][2] - r["block"][0]) / r["size"][0])
    med = {k: float(np.percentile(v, 25)) for k, v in groups.items()}  # pages with margin notes are wider
    for r in recs.values():
        b = r.get("block")
        if not b:
            r["flag"] = "no-ink"
        elif (b[3] - b[1]) / r["size"][1] > 0.97 or (b[2] - b[0]) / r["size"][0] > 0.97:
            r["flag"] = "full"  # nothing trimmed: a dark or dull scan
        elif (b[2] - b[0]) / r["size"][0] - med[key(r)] < -0.04:
            r["flag"] = "narrow"
        elif (b[2] - b[0]) / r["size"][0] - med[key(r)] > 0.04:
            r["flag"] = "wide"


def crop_source(vol, redo=False):
    src, dst = DATA / vol / "source_images", DATA / vol / "source_images_cropped"
    old = json.loads((dst / "crops.json").read_text()) if (dst / "crops.json").exists() else {}
    recs = {}
    for f in sorted(set(src.glob("*/**/*.png"))):  # intro/ and fin/ hold one folder a section
        rel = f.relative_to(src)
        part, k, out = rel.parts[0], str(rel.with_suffix("")), dst / rel
        if k in old and out.exists() and not redo:
            recs[k] = old[k]
            continue
        im = Image.open(f)
        g = np.asarray(im.convert("L"), dtype=np.int16)
        h, w = g.shape
        b = text_block(g, edge_x=0.005, edge_y=0.005, mask=GOOGLE)
        box = pad_box(b, w, h) if b else [0, 0, w, h]
        rec = {"part": part, "size": [w, h], "block": b, "flag": ""}
        if part == "commentaire":
            kr = kraken_box(vol, f.stem)
            if kr:  # never cut a word Kraken read
                kb = [max(0, kr[0] - 4), max(0, kr[1] - 4), min(w, kr[2] + 4), min(h, kr[3] + 4)]
                grown = [min(box[0], kb[0]), min(box[1], kb[1]), max(box[2], kb[2]), max(box[3], kb[3])]
                if grown != box:
                    rec["grown_for_kraken"] = [g_ - b_ for g_, b_ in zip(grown, box)]
                    # a word Kraken misread at the edge (a margin note): follow its ink out
                    e = extend(ink_mask(g, 0.005, 0.005, GOOGLE), [grown[0], grown[1], grown[2] - 1, grown[3] - 1])
                    grown = pad_box(e, w, h) if e[0] < grown[0] or e[2] > grown[2] - 1 else grown
                box = grown
        rec["box"] = box
        out.parent.mkdir(parents=True, exist_ok=True)
        im.crop(box).save(out)
        recs[k] = rec
    flag_widths(recs, lambda r: r["part"])
    (dst / "crops.json").write_text(json.dumps(recs, indent=0))
    return recs


def crop_good(work, out, align):
    pages = [p for p in json.loads(Path(align).read_text()) if p["type"] == "commentary"]
    man = DATA / "good_calmet_manifests"
    files = {pdf: {q["pdf_page"]: q["file"] for q in json.loads((man / f"{pdf}.json").read_text())["pages"]}
             for pdf in {p["pdf"] for p in pages}}
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    recs = {}
    for p in pages:
        im = Image.open(Path(work) / p["pdf"] / files[p["pdf"]][p["pdf_page"]]).convert("RGB")
        g = np.asarray(im.convert("L"), dtype=np.int16)
        h, w = g.shape
        b = text_block(g, edge_x=0.015, edge_y=0.01)  # a margin note can sit close to the edge; shadows go as full-height columns
        box = pad_box(b, w, h) if b else [0, 0, w, h]
        stem = f"{p['pdf']}/page_{p['pdf_page']:04d}"
        (out / p["pdf"]).mkdir(exist_ok=True)
        im.crop(box).save(out / f"{stem}.png")
        recs[stem] = {"pdf": p["pdf"], "pdf_page": p["pdf_page"], "source": p.get("source"),
                      "size": [w, h], "block": b, "box": box, "flag": ""}
    flag_widths(recs, lambda r: r["pdf"])
    (out / "crops.json").write_text(json.dumps(recs, indent=0))
    return recs


def verify(vol):
    """Kraken words of vol outside their page's crop (the mark's misreadings aside): [] if none."""
    crops = json.loads((DATA / vol / "source_images_cropped" / "crops.json").read_text())
    bad = []
    for f in sorted((OCR_CACHE / vol).glob("page_*.json")):
        c = crops.get(f"commentaire/{f.stem}")
        if not c:
            bad.append((f.stem, "no crop")); continue
        x0, y0, x1, y1 = c["box"]
        o = json.loads(f.read_text()); W, H = o["size"]
        for ln in o["lines"]:
            for wd in ln["words"]:
                b = wd["box"]
                if b[2] and b[3] and not (b[1] >= GOOGLE[1] * H and b[0] >= GOOGLE[0] * W) and \
                        (b[0] < x0 or b[1] < y0 or b[0] + b[2] > x1 or b[1] + b[3] > y1):
                    bad.append((f.stem, wd["t"]))
    return bad


def report(recs):
    from collections import Counter
    print(len(recs), "pages;", dict(Counter(r["flag"] or "ok" for r in recs.values())),
          "; grown for Kraken:", sum(1 for r in recs.values() if r.get("grown_for_kraken")))


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["good"]:
        report(crop_good(*a[1:4]))
    elif a[:1] == ["source"]:
        redo = "--redo" in a; a = [x for x in a if x != "--redo"]
        vols = sorted(d.parent.name for d in DATA.glob("*/source_images")) if a[1:] == ["--all"] else a[1:]
        for v in vols:
            print(v, end=": ", flush=True)
            report(crop_source(v, redo))
    elif a[:1] == ["verify"]:
        vols = sorted(d.parent.parent.name for d in DATA.glob("*/source_images_cropped/crops.json")) if a[1:] == ["--all"] else a[1:]
        for v in vols:
            bad = verify(v)
            print(v, "ok" if not bad else f"{len(bad)} Kraken words outside the crop: {bad[:5]}")
    else:
        print(__doc__)
