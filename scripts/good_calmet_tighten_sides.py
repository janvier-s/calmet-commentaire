"""Third pass on Good_Calmet crops: trim blank / scan-edge bands left and right of the text block.
Column ink profile; thin (<4 % w) edge runs isolated by a blank gap >4 % w are dropped as shadows/bleed.
Updates crops.json box (x offsets). Idempotent. usage: good_calmet_tighten_sides.py <pdf>... | --all [--dry]"""
import sys, json, numpy as np
from pathlib import Path
from PIL import Image
D = Path(__file__).resolve().parent.parent / "data" / "good_calmet"

def span(g):
    h, w = g.shape
    ink = (g < 150).sum(0) > 0.004 * h
    gap = max(3, int(.012 * w)); runs, i = [], 0
    while i < w:
        if ink[i]:
            j = i
            while j < w and (ink[j] or ink[j:j + gap].any()): j += 1
            runs.append((i, j)); i = j
        else: i += 1
    while len(runs) > 1 and runs[-1][1] - runs[-1][0] < .04 * w and runs[-1][0] - runs[-2][1] > .04 * w: runs.pop()
    while len(runs) > 1 and runs[0][1] - runs[0][0] < .04 * w and runs[1][0] - runs[0][1] > .04 * w: runs.pop(0)
    return (runs[0][0], runs[-1][1]) if runs else (0, w)

def tighten(pdf, dry=False):
    recs = json.loads((D / "crops.json").read_text()); n = 0
    for k, r in recs.items():
        if r["pdf"] != pdf: continue
        im = Image.open(D / f"{k}.png"); g = np.asarray(im.convert("L"), dtype=np.int16)
        h, w = g.shape
        l, rt = span(g)
        pad = max(6, int(.01 * w)); l, rt = max(0, l - pad), min(w, rt + pad)
        if l < .03 * w and rt > .97 * w: continue
        n += 1
        if dry: print(k.split("/")[1], f"left {l/w:.2f} right {1-rt/w:.2f}"); continue
        im.crop((l, 0, rt, h)).save(D / f"{k}.png")
        x0, y0, x1, y1 = r["box"]; r["box"] = [x0 + l, y0, x0 + rt, y1]
        r["tightened_x"] = [l, w - rt]
    if not dry: (D / "crops.json").write_text(json.dumps(recs, indent=0))
    print(pdf, n, "pages trimmed")

if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if x != "--dry"]
    pdfs = sorted({r["pdf"] for r in json.loads((D / "crops.json").read_text()).values()}) if a == ["--all"] else a
    for p in pdfs: tighten(p, "--dry" in sys.argv)
