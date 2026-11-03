#!/usr/bin/env python3
"""Crop test on ~20 Genèse pages: Jev Box vs plain ink-bounds crop.

Usage:
    set -a; . ./.env; set +a
    uv run --with requests --with pillow --with numpy scripts/good_calmet_crop_test.py \
        <work_dir> <out_dir> <sample.json> [--cap-usd 0.05]

For each sample page writes native-resolution crops (no sharpen, no upscale):
  <out>/<stem>.full.png    ink-bounds crop of the text area (local, free)
  <out>/<stem>.jev_fn.png  Jev footnote-strip box
  <out>/<stem>.ink_fn.png  footnote strip from the ink-detected rule
  <out>/<stem>.src_fn.png  same strip of the existing source_images page (baseline)
then OCRs each strip (tesseract eng, psm 6) and scores word recall against the
existing footnote text for that source page (docs/footnotes/<book>.json).
Jev answers are cached in <out>/jev_cache.json.
"""
import argparse, base64, difflib, io, json, os, re, subprocess, sys, unicodedata, uuid
from pathlib import Path

import numpy as np
import requests
from PIL import Image

API = "https://api.typesafe.ai/v1/systemone"
PRICE = 0.042 / 1e6
ROOT = Path(__file__).resolve().parent.parent
Q = {
    "text": {"type": "box", "instructions":
             "Locate the main text block of the printed page `page`: body paragraphs only, "
             "excluding the running header line, the footnote band and the signature mark."},
    "footnotes": {"type": "box", "instructions":
                  "Locate the footnote band of the printed page `page`: the small-print notes "
                  "below the horizontal rule at the bottom, excluding the signature mark below them."},
}


def ink_mask(im: Image.Image) -> np.ndarray:
    a = np.asarray(im.convert("L"), dtype=np.int16)
    return a < np.percentile(a, 80) - 60


def ink_boxes(im: Image.Image):
    """(text bbox, footnote-strip bbox or None) in pixels from projections + footnote rule."""
    m = ink_mask(im)
    h, w = m.shape
    m[:, : int(w * .03)] = False; m[:, int(w * .985):] = False       # spine / edge shadows
    m[: int(h * .01)] = False; m[int(h * .99):] = False
    # footnote rule: thin, faint, long horizontal line in the lower half. Use a looser
    # darkness threshold than the text mask and require quiet rows just above it.
    g = np.asarray(im.convert("L"), dtype=np.int16)
    faint = g < np.median(g) - 18
    faint[:, : int(w * .03)] = False; faint[:, int(w * .985):] = False
    frac = faint.sum(1) / w
    rule = None
    for y in range(int(h * .5), int(h * .95)):
        if frac[y] > .3 and frac[max(0, y - 8):y - 2].max(initial=0) < .1:
            rule = y; break
    rows = np.flatnonzero(m.sum(1) > w * .004)
    cols = np.flatnonzero(m.sum(0) > h * .004)
    if not len(rows) or not len(cols):
        return None, None
    pad = 12
    text = (max(0, cols[0] - pad), max(0, rows[0] - pad), min(w, cols[-1] + pad), min(h, rows[-1] + pad))
    fn = None
    if rule:
        below = np.flatnonzero(m[rule + 4:].sum(1) > w * .004) + rule + 4
        # drop the signature mark: stop at the largest vertical gap after the rule
        end = below[-1]
        gaps = np.diff(below)
        if len(gaps) and gaps.max() > h * .012:
            end = below[int(np.argmax(gaps))]
        fn = (text[0], max(0, rule - 4), text[2], min(h, end + pad))
    return text, fn


def jev_boxes(path: Path, key: str, cache: dict, spent: list, cap: float):
    if path.name in cache:
        return cache[path.name]
    if spent[0] > cap:
        return None
    im = Image.open(path).convert("RGB"); im.thumbnail((768, 768))
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=85); ref = str(uuid.uuid4())
    body = {"model": "jev-latest", "state": {"page": ref},
            "assets": {ref: {"type": "image", "format": "jpg",
                             "data_base64": base64.b64encode(buf.getvalue()).decode()}},
            "questions": Q}
    r = requests.post(API, json=body, timeout=120, headers={
        "Authorization": "Bearer " + key, "TypeSafe-Danger-Zone-Images": "true"})
    if r.status_code != 200:
        return {"error": r.status_code}
    j = r.json(); spent[0] += j["usage"]["input_tokens"] * PRICE
    res = {k: {**v["box"], "conf": v["confidence"]} for k, v in j["answers"].items() if v.get("box")}
    cache[path.name] = res
    return res


def frac_box(b, w, h, pad=0.006):
    return (max(0, int((b["left"] - pad) * w)), max(0, int((b["top"] - pad) * h)),
            min(w, int((b["right"] + pad) * w)), min(h, int((b["bottom"] + pad) * h)))


def norm_words(s: str):
    s = unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()
    s = s.replace("s", "s")
    return re.findall(r"[a-z]{3,}", s.replace("ſ", "s"))


def ocr(img: Image.Image) -> str:
    tmp = Path(os.environ.get("TMPDIR", "/tmp")) / f"gc_{uuid.uuid4().hex}.png"
    img.save(tmp)
    t = subprocess.run(["tesseract", str(tmp), "-", "--psm", "6", "-l", "eng"],
                       capture_output=True, text=True).stdout
    tmp.unlink(missing_ok=True)
    return t


def recall(ocr_text: str, truth: str) -> float:
    """Fraction of ground-truth words (len>=3) found in the OCR (fuzzy, accent-blind)."""
    tw, ow = norm_words(truth), set(norm_words(ocr_text))
    if not tw:
        return float("nan")
    hit = 0
    for w in tw:
        if w in ow or difflib.get_close_matches(w, ow, 1, 0.8):
            hit += 1
    return hit / len(tw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work", type=Path); ap.add_argument("out", type=Path); ap.add_argument("sample", type=Path)
    ap.add_argument("--cap-usd", type=float, default=0.05)
    a = ap.parse_args()
    key = os.environ["TYPESAFE_API_KEY"]
    a.out.mkdir(parents=True, exist_ok=True)
    cpath = a.out / "jev_cache.json"
    cache = json.loads(cpath.read_text()) if cpath.exists() else {}
    truth: dict[str, str] = {}
    for f in (ROOT / "data/01_genese/raw_json/commentaire").glob("page_*.json"):
        try:
            fns = json.loads(f.read_text(), strict=False).get("footnotes") or []
        except ValueError:
            continue    # a few raw files are malformed; no ground truth for those pages
        truth[f.stem] = " ".join(n.get("text") or "" for n in fns)
    spent = [0.0]
    rows = []
    for s in json.loads(a.sample.read_text()):
        src = a.work / s["pdf"] / s["file"]
        im = Image.open(src).convert("RGB")
        w, h = im.size
        stem = f"{s['pdf'][:2]}_{s['file'][:-4]}"
        text_box, ink_fn = ink_boxes(im)
        if text_box:
            im.crop(text_box).save(a.out / f"{stem}.full.png")
        jb = jev_boxes(src, key, cache, spent, a.cap_usd)
        rec = {"page": stem, "source": s["source"], "truth_words": len(norm_words(truth.get(s["source"], "")))}
        t = truth.get(s["source"], "")
        if ink_fn:
            c = im.crop(ink_fn); c.save(a.out / f"{stem}.ink_fn.png")
            rec["ink_fn"] = round(recall(ocr(c), t), 3); rec["ink_fn_px"] = c.size
        if jb and "footnotes" in jb:
            c = im.crop(frac_box(jb["footnotes"], w, h)); c.save(a.out / f"{stem}.jev_fn.png")
            rec["jev_fn"] = round(recall(ocr(c), t), 3); rec["jev_fn_px"] = c.size
            rec["jev_conf"] = round(jb["footnotes"]["conf"] or 0, 2)
        sp = ROOT / "data/01_genese/source_images/commentaire" / f"{s['source']}.png"
        if sp.exists():
            sim = Image.open(sp).convert("RGB")
            _, sfn = ink_boxes(sim)
            if sfn:
                c = sim.crop(sfn); c.save(a.out / f"{stem}.src_fn.png")
                rec["src_fn"] = round(recall(ocr(c), t), 3)
        rows.append(rec); print(rec, flush=True)
    cpath.write_text(json.dumps(cache, indent=1))
    (a.out / "results.json").write_text(json.dumps(rows, indent=1))
    for k in ("ink_fn", "jev_fn", "src_fn"):
        v = [r[k] for r in rows if k in r and r[k] == r[k]]
        print(k, "n=%d mean recall=%.3f" % (len(v), sum(v) / max(1, len(v))))
    print(f"jev spend this run ${spent[0]:.5f}")


if __name__ == "__main__":
    main()
