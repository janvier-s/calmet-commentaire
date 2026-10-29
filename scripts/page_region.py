"""Locate the commentary band on a scan page.

The detector needs the commentary region only: the running head, the two-column
verse block above it and the footnote block below it must all stay out. Two page
layouts occur, and they differ in what the band contains:

  heading       a centred ``COMMENTAIRE.`` line opens the commentary; the band
                runs from that line's bottom to the footnote rule, and holds the
                commentary blocks only (the verse block is above the heading).

  continuation  the commentary runs on from the page before, so there is no
                heading; the band runs from below the running head to the
                footnote rule, and holds the verse block *and* the commentary.

That distinction matters when counting words against the JSON: a continuation
band must be compared with ``verses`` + ``commentary``, a heading band with
``commentary`` alone.

The footnote rule is found from the pixels, not from OCR: Tesseract does not
reliably report the rule, and when it is missed the whole footnote block leaks
into the band (+40 to +116 words a page in testing).

Pillow is needed (``uv run --no-project --with pillow python ...``). The heading
and running head are read from a Tesseract TSV; pass ``--tsv`` to reuse one, or
let the script run Tesseract (``fra`` must be installed).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

# A rule is a *contiguous* run of dark pixels, only a few rows tall. The
# contiguity is what separates it from a dense line of type: measured on these
# scans a rule gives one run of ~400 px, the darkest row of a text line gives
# ~40 px broken into 60 runs. A dark-pixel *fraction* does not separate them
# (0.54 for a rule, 0.58 for a text line).
RULE_MIN_RUN = 0.20  # of page width
RULE_MIN_Y = 0.45  # of page height; skips any rule printed under the running head
RULE_MAX_THICKNESS = 12


def load_tsv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t", quoting=csv.QUOTE_NONE))


def group_lines(rows: list[dict]) -> list[dict]:
    """Regroup Tesseract word rows into lines with their box and text."""
    lines: dict[tuple, dict] = {}
    for row in rows:
        if row.get("level") != "5" or not (row.get("text") or "").strip():
            continue
        key = (row["block_num"], row["par_num"], row["line_num"])
        line = lines.setdefault(
            key, {"words": [], "top": 10**9, "bot": 0, "left": 10**9, "right": 0}
        )
        line["words"].append(row["text"])
        line["top"] = min(line["top"], int(row["top"]))
        line["bot"] = max(line["bot"], int(row["top"]) + int(row["height"]))
        line["left"] = min(line["left"], int(row["left"]))
        line["right"] = max(line["right"], int(row["left"]) + int(row["width"]))

    out = []
    for line in lines.values():
        line["text"] = " ".join(line["words"])
        line["width"] = line["right"] - line["left"]
        line["height"] = line["bot"] - line["top"]
        out.append(line)
    return sorted(out, key=lambda ln: (ln["top"], ln["left"]))


def _squash(text: str) -> str:
    return re.sub(r"[^A-Z]", "", (text or "").upper())


def find_rules(png: Path) -> list[int]:
    """y positions of horizontal rules, found by contiguous-run projection."""
    from PIL import Image

    with Image.open(png) as im:
        im = im.convert("L")
        width, height = im.size
        data = im.tobytes()

    dark = bytes(ord("1") if v < 140 else ord("0") for v in range(256))
    needed = int(RULE_MIN_RUN * width)
    hits = []
    for y in range(int(height * RULE_MIN_Y), height):
        row = data[y * width : (y + 1) * width].translate(dark)
        longest = max((m.end() - m.start() for m in re.finditer(rb"1+", row)), default=0)
        if longest >= needed:
            hits.append(y)

    groups: list[list[int]] = []
    for y in hits:
        if groups and y - groups[-1][-1] <= 2:
            groups[-1].append(y)
        else:
            groups.append([y])
    return [g[0] for g in groups if len(g) <= RULE_MAX_THICKNESS]


def find_heading(lines: list[dict], max_width: int = 700) -> dict | None:
    """The centred ``COMMENTAIRE.`` line, if the page has one."""
    found = [
        ln
        for ln in lines
        if _squash(ln["text"]) == "COMMENTAIRE" and ln["width"] < max_width
    ]
    return found[-1] if found else None


def find_running_head(lines: list[dict], page_height: int) -> dict | None:
    """The first line, when it sits in the top band and reads as a running head."""
    for line in lines:
        if line["top"] > page_height * 0.18:
            return None
        text = line["text"]
        letters = [c for c in text if c.isalpha()]
        if not letters:
            continue
        upper = sum(1 for c in letters if c.isupper()) / len(letters)
        if upper >= 0.6:
            return line
        return None
    return None


def commentary_band(png: Path, tsv: Path | None = None, tessdata: str | None = None) -> dict:
    """Return the commentary band for one page.

    ``{"y0", "y1", "layout", "heading", "rule", "running_head"}``, or a dict with
    ``"error"`` when the page cannot be located.
    """
    png = Path(png)
    if tsv is None:
        import tempfile

        tsv = Path(tempfile.mkdtemp(prefix="page_region_")) / "page.tsv"
        cmd = ["tesseract", str(png), str(tsv.with_suffix("")), "-l", "fra", "--psm", "3", "tsv"]
        env = None
        if tessdata:
            import os

            env = {**os.environ, "TESSDATA_PREFIX": tessdata}
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
        if proc.returncode != 0:
            return {"error": f"tesseract failed: {proc.stderr.strip()[:200]}"}

    from PIL import Image

    with Image.open(png) as im:
        page_height = im.size[1]

    lines = group_lines(load_tsv(Path(tsv)))
    if not lines:
        return {"error": "no text lines found"}

    heading = find_heading(lines)
    if heading is not None:
        layout = "heading"
        y0 = heading["bot"]
    else:
        layout = "continuation"
        head = find_running_head(lines, page_height)
        if head is None:
            return {"error": "no heading and no running head"}
        y0 = head["bot"] + 8

    rules = [y for y in find_rules(png) if y > y0]
    y1 = rules[0] if rules else None
    if y1 is None:
        return {"error": "no footnote rule below the commentary", "y0": y0, "layout": layout}

    return {
        "y0": y0,
        "y1": y1,
        "layout": layout,
        "heading": heading["text"] if heading else None,
        "rule": y1,
        "running_head": None if heading else "detected",
        "tsv": str(tsv),
    }


def crop_band(png: Path, band: dict, out: Path) -> Path:
    """Write the commentary band as its own image, with a little side margin."""
    from PIL import Image

    with Image.open(png) as im:
        width, _ = im.size
        im.crop((0, band["y0"], width, band["y1"])).save(out)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("png", type=Path)
    ap.add_argument("--tsv", type=Path, help="reuse an existing Tesseract TSV")
    ap.add_argument("--tessdata", help="directory holding fra.traineddata")
    ap.add_argument("--crop", type=Path, help="write the band to this PNG")
    args = ap.parse_args(argv)

    band = commentary_band(args.png, args.tsv, args.tessdata)
    if args.crop and "error" not in band:
        crop_band(args.png, band, args.crop)
        band["crop"] = str(args.crop)
    print(json.dumps(band, ensure_ascii=False))
    return 0 if "error" not in band else 1


if __name__ == "__main__":
    sys.exit(main())
