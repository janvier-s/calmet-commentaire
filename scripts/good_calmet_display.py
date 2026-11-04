"""The Good_Calmet crops with their contrast raised, for the review editor only (Kraken reads the plain
crops): data/good_calmet_display/<pdf>/page_NNNN.png, same size, no pixel moved (the OCR boxes hold).

    python3 good_calmet_display.py <pdf> [first-last]   the display copies of a PDF's crops not yet made
    python3 good_calmet_display.py --vol 01_genese      every PDF of that volume
    python3 good_calmet_display.py --all                every crop in crops.json
    python3 good_calmet_display.py ... --force          made again (after a change to the curve)

The curve, per page (its paper and ink vary): the darkest LO % of the pixels to black, the lightest
(100 - HI) % to white, a gamma GAMMA that darkens the strokes' edges, then a knee that sends to white
whatever is lighter than KNEE[1] (show-through and paper grain, the gamma darkened them too) with a
smooth ramp from KNEE[0], so the letters' edges stay soft. Chosen on contact sheets (variant F).
"""
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from PIL import Image

from paths import DATA
from good_calmet_kraken import crops, crop_path

DISPLAY = DATA / "good_calmet_display"
LO, HI, GAMMA, KNEE = 5, 60, 1.8, (0.45, 0.65)


def display_path(pdf, page):
    return DISPLAY / pdf / f"page_{page:04d}.png"


def _percentile(hist, q):
    """The grey level below which q % of the pixels lie."""
    n, acc = sum(hist) * q / 100, 0
    for v, c in enumerate(hist):
        acc += c
        if acc >= n:
            return v
    return 255


# optimize=True cost ~10x the time for ~2 % smaller files; level 6 is the speed/size sweet spot.
SAVE = {"compress_level": 6}


def curve(lo, hi):
    lut = []
    k0, k1 = KNEE
    for v in range(256):
        x = min(max((v - lo) / max(hi - lo, 1), 0.0), 1.0) ** GAMMA
        t = min(max((x - k0) / (k1 - k0), 0.0), 1.0)
        t = t * t * (3 - 2 * t)
        lut.append(round((x * (1 - t) + t) * 255))
    return lut


def make(src, out):
    im = Image.open(src).convert("L")
    h = im.histogram()
    out.parent.mkdir(parents=True, exist_ok=True)
    im.point(curve(_percentile(h, LO), _percentile(h, HI))).save(out, **SAVE)


def _job(job):
    make(*job)


def main(argv):
    force = "--force" in argv
    argv = [a for a in argv if a != "--force"]
    if not argv or (argv[0] == "--vol" and len(argv) < 2):
        sys.exit(__doc__)
    recs = crops()
    if argv[0] == "--all":
        jobs = [(r["pdf"], r["pdf_page"]) for r in recs]
    elif argv[0] == "--vol":
        jobs = [(r["pdf"], r["pdf_page"]) for r in recs if r["vol"] == argv[1]]
    else:
        jobs = [(r["pdf"], r["pdf_page"]) for r in recs if r["pdf"] == argv[0]]
        if len(argv) > 1:
            a, _, b = argv[1].partition("-")
            jobs = [(pdf, p) for pdf, p in jobs if int(a) <= p <= int(b or a)]
    if not jobs:
        sys.exit(f"no crop of {argv[-1]} in crops.json")
    todo = []
    for pdf, p in sorted(set(jobs)):
        src, out = crop_path(pdf, p), display_path(pdf, p)
        if src.exists() and (force or not out.exists()):
            todo.append((src, out))
    with ProcessPoolExecutor(os.cpu_count()) as ex:
        for i, _ in enumerate(ex.map(_job, todo, chunksize=16), 1):
            if i % 500 == 0:
                print(f"  {i}/{len(todo)}", flush=True)
    print(f"{len(todo)} display copies made, {len(set(jobs)) - len(todo)} already there or without a crop")


if __name__ == "__main__":
    main(sys.argv[1:])
