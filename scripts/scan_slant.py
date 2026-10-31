"""The slant of every word the OCR read, in degrees (italics lean 12-20, roman 0 or less), written into
the OCR cache as "sl" on each String. Run by scan_ocr.py with the Kraken venv's Python (numpy, Pillow):

    .kraken-venv/bin/python scan_slant.py SCAN CACHE [SCAN CACHE ...]

The slant is the shear that makes the word's ink stand most upright: the columns of its sheared ink
are then the sharpest."""
import json
import sys

import numpy as np
from PIL import Image

ANGLES = np.radians(np.arange(-6, 26, 1.0))
TAN = np.tan(ANGLES)


def slant(img, box):
    x, y, w, h = box
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
            for w in ln["words"]:
                w["sl"] = slant(img, w["box"])
        o["slant"] = 1
        with open(cache, "w", encoding="utf-8") as f:
            json.dump(o, f, ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    main(sys.argv[1:])
