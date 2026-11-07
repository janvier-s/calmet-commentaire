"""Second pass on Good_Calmet crops: trim blank/scan-edge bands above and below the text (thin full-width
lines or shadows separated from the body by white space). Works on the existing crops, updates crops.json box.
usage: good_calmet_tighten.py <pdf-dir-name>... | --all [--dry]"""
import sys, json, numpy as np
from pathlib import Path
from PIL import Image
D = Path(__file__).resolve().parent.parent / "data" / "good_calmet"

def band(g):
    """(top, bottom) rows of the text body: ink rows grouped, thin (<0.5 % h) groups near an edge dropped."""
    h, w = g.shape
    ink = (g < 150).sum(1) > 0.004 * w
    runs, i = [], 0
    while i < h:
        if ink[i]:
            j = i
            while j < h and (ink[j] or ink[j:j + max(3, int(.012 * h))].any()):
                j += 1
            runs.append((i, j)); i = j
        else:
            i += 1
    runs = [r for r in runs if not (r[1] - r[0] < 0.006 * h and (r[1] < .2 * h or r[0] > .8 * h))]
    # edge shadow: short run (<4 % h) hugging an edge, isolated from the body by a blank gap > 6 % h
    while len(runs) > 1 and runs[-1][1] - runs[-1][0] < .04 * h and h - runs[-1][1] < .1 * h and runs[-1][0] - runs[-2][1] > .06 * h:
        runs.pop()
    while len(runs) > 1 and runs[0][1] - runs[0][0] < .04 * h and runs[0][0] < .1 * h and runs[1][0] - runs[0][1] > .06 * h:
        runs.pop(0)
    return (runs[0][0], runs[-1][1]) if runs else (0, h)

def tighten(pdf, dry=False):
    recs = json.loads((D / "crops.json").read_text()); n = 0
    for k, r in recs.items():
        if r["pdf"] != pdf: continue
        im = Image.open(D / f"{k}.png"); g = np.asarray(im.convert("L"), dtype=np.int16)
        h, w = g.shape
        t, b = band(g)
        pad = max(4, int(.006 * h)); t, b = max(0, t - pad), min(h, b + pad)
        if t < .03 * h and b > .97 * h: continue
        n += 1
        if dry: print(k.split("/")[1], f"top {t/h:.2f} bot {1-b/h:.2f}"); continue
        im.crop((0, t, w, b)).save(D / f"{k}.png")
        x0, y0, x1, y1 = r["box"]; r["box"] = [x0, y0 + t, x1, y0 + b]
        r["tightened"] = [a + c for a, c in zip(r.get("tightened", [0, 0]), [t, h - b])]  # cumulative since the OCR
    if not dry: (D / "crops.json").write_text(json.dumps(recs, indent=0))
    print(pdf, n, "pages trimmed")

if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if x != "--dry"]
    pdfs = sorted({r["pdf"] for r in json.loads((D / "crops.json").read_text()).values()}) if a == ["--all"] else a
    for p in pdfs: tighten(p, "--dry" in sys.argv)
