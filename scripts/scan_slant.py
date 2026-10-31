"""The slant of every word the OCR read, in degrees (italics lean 12-20, roman 0 or less), written into
the OCR cache as "sl" on each String. Run by scan_ocr.py with the Kraken venv's Python (numpy, Pillow):

    .kraken-venv/bin/python scan_slant.py SCAN CACHE [SCAN CACHE ...]

The slant is the shear that makes the word's ink stand most upright: the columns of its sheared ink
are then the sharpest."""
import json
import sys

import numpy as np
from PIL import Image

VERSION = 2  # the measure's version, in the cache (scan_ocr.SLANT): 2, the box widened to the ink, accents left out
ANGLES = np.radians(np.arange(-6, 26, 1.0))
TAN = np.tan(ANGLES)


def snap(img, box):
    """The box widened to the ends of the word's ink: Kraken's boxes clip the overhang of italic letters,
    and a straight cut through slanted strokes reads as upright ("avec" -4 instead of 15). The box's
    rows cut into ink clusters at the gaps between words; the clusters the box touches widen it, by a
    third of its height at most each side (the overhang of a 20° slant)."""
    x, y, w, h = box
    pad = h // 3
    x0, x1 = max(0, x - pad), min(img.shape[1], x + w + pad)
    c = img[y:y + h, x0:x1]
    if c.size == 0 or w < 6 or h < 6:
        return box
    ink = np.nonzero((c < (float(c.min()) + float(c.max())) / 2).sum(axis=0))[0]
    if not len(ink):
        return box
    gap = max(4, h // 6)
    a, b = x - x0, x - x0 + w
    lo = hi = None
    for r0, r1 in zip(np.r_[ink[0], ink[1:][np.diff(ink) > gap]], np.r_[ink[:-1][np.diff(ink) > gap], ink[-1]] + 1):
        if r1 > a and r0 < b:  # touches the box
            lo = r0 if lo is None else lo
            hi = r1
    if lo is None:
        return box
    lo, hi = min(lo, a), max(hi, b)
    return [x0 + int(lo), y, int(hi - lo), h]


ACCENTS = set("áàâäéèêëíìîïóòôöúùûüÁÀÂÉÈÊÔ^")


def slant(img, box, text=""):
    """`text`: the word as read; an accented word is measured below its accents (slanted strokes of their own)."""
    box = snap(img, box)
    x, y, w, h = box
    if ACCENTS & set(text):
        y, h = y + h * 3 // 10, h - h * 3 // 10
    if w < 6 or h < 6:
        return None
    c = img[y:y + h, max(0, x - 2):x + w + 2]
    if c.size == 0:
        return None
    ink = c < (float(c.min()) + float(c.max())) / 2
    ys, xs = np.nonzero(ink)
    if len(xs) < 30:
        return None
    yc = ys - ys.mean()
    best, at = -1.0, 0
    for i, t in enumerate(TAN):
        xp = np.round(xs + yc * t).astype(int)
        s = float((np.bincount(xp - xp.min()).astype(float) ** 2).sum())
        if s > best:
            best, at = s, i
    return round(float(np.degrees(ANGLES[at])))


def main(argv):
    for scan, cache in zip(argv[::2], argv[1::2]):
        img = np.asarray(Image.open(scan).convert("L"), dtype=np.float32)
        with open(cache, encoding="utf-8") as f:
            o = json.load(f)
        for ln in o["lines"]:
            ws = ln["words"]
            for n, w in enumerate(ws):
                box = w["box"]
                if w["box"][2] < 6 and "&" in w["t"] and 0 < n < len(ws) - 1:  # Kraken boxes an & as a point: it lies between its neighbours
                    x = ws[n - 1]["box"][0] + ws[n - 1]["box"][2]
                    box = [x, box[1], ws[n + 1]["box"][0] - x, box[3]]
                w["sl"] = slant(img, box, w["t"])
        o["slant"] = VERSION
        with open(cache, "w", encoding="utf-8") as f:
            json.dump(o, f, ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    main(sys.argv[1:])
