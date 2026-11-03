#!/usr/bin/env python3
"""Contact sheets of the Good_Calmet crops flagged "narrow" or "full", for a quick eyeball.

    uv run --with pillow python scripts/good_calmet_sheets.py [out_dir]   (default data/good_calmet_review/)

6 crops a sheet (3 x 2), each labelled <pdf>/page_NNNN (flag, source page); sheets sorted by PDF and page.
"""
import json, sys
from pathlib import Path
from PIL import Image, ImageDraw

D = Path(__file__).resolve().parent.parent / "data"
out = Path(sys.argv[1]) if len(sys.argv) > 1 else D / "good_calmet_review"
out.mkdir(parents=True, exist_ok=True)
for f in out.glob("sheet_*.png"):
    f.unlink()
crops = json.loads((D / "good_calmet" / "crops.json").read_text())
keys = sorted(k for k, v in crops.items() if v["flag"] in ("narrow", "full"))
W, H, PER = 560, 780, 6
for n in range(0, len(keys), PER):
    sheet = Image.new("RGB", (3 * W, 2 * (H + 22)), "white")
    d = ImageDraw.Draw(sheet)
    for i, k in enumerate(keys[n:n + PER]):
        im = Image.open(D / "good_calmet" / f"{k}.png").convert("RGB")
        im.thumbnail((W - 6, H - 6))
        x, y = (i % 3) * W, (i // 3) * (H + 22)
        sheet.paste(im, (x + 3, y + 22))
        v = crops[k]
        d.text((x + 4, y + 4), f"{k}  [{v['flag']}]  -> {v.get('vol') or '01_genese'} {v.get('source')}", fill="black")
    sheet.save(out / f"sheet_{n // PER + 1:03d}.png")
print(len(keys), "crops,", -(-len(keys) // PER), "sheets in", out)
