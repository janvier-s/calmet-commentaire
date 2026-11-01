"""The red of the OCR overlay on a volume: the words on one side only, the scan's or the JSON's.

    python3 ocr_red_report.py <volume> [--fix]     the fixed alignment with --fix

Reads cache/ocr/<vol>/ and data/<vol>/normalized/ only (never runs Kraken). Prints the pages with OCR,
those with red, the red, split into the red that has a word on the other side it could pair with (a
likeness of 0.5, the word alone or joined to the one before or after) and the red that has not; then 40
of what is left (a fixed seed), each with its page, and the scan's with its height on the page.
"""
import collections
import json
import random
import sys

import scan_ocr as O
from paths import DATA


def red(vol, fix=False):
    """{"pages", "red_pages", "red", "tally": Counter, "left": [str]}."""
    pages = sorted(f for f in (O.OCR_CACHE / vol).glob("page_*.json") if (DATA / vol / "normalized" / f.name).exists())
    tally, left, per = collections.Counter(), [], []
    for f in pages:
        o = json.loads(f.read_text(encoding="utf-8"))
        if not o or not o.get("lines"):
            continue
        r = O.align(o, json.loads((DATA / vol / "normalized" / f.name).read_text(encoding="utf-8")), fix=fix)
        ws, ext = r["words"], r["extra"]
        miss = [i for i, w in enumerate(ws) if w["s"] == "missing"]
        ek = [O.key(e["t"]) for e in ext]
        per.append(len(miss) + len(ext))
        used = set()
        for i in miss:
            ks = (O.key(ws[i]["t"]), O.key(ws[i]["t"] + (ws[i + 1]["t"] if i + 1 < len(ws) else "")),
                  O.key((ws[i - 1]["t"] if i else "") + ws[i]["t"]))
            best = max(((O.similar(k, ek[j]), j) for j in range(len(ext)) for k in ks), default=(0, None))
            if best[0] >= 0.5:
                tally["could pair"] += 1
                used.add(best[1])
            else:
                tally["not (scan)"] += 1
                left.append(f"scan {ws[i]['t']!r} y={ws[i]['boxes'][0][1] / o['size'][1]:.2f}  {f.stem}")
        for j, e in enumerate(ext):
            if j in used:
                tally["could pair"] += 1
            else:
                tally["not (json)"] += 1
                left.append(f"json {e['t']!r} @{e['path']}  {f.stem}")
    return {"pages": len(per), "red_pages": sum(1 for x in per if x), "red": sum(per), "tally": tally, "left": left}


def main(argv):
    vol, fix = argv[0], "--fix" in argv
    r = red(vol, fix)
    print(f"{vol}{' --fix' if fix else ''}: pages with OCR {r['pages']}, with red {r['red_pages']}, red {r['red']}"
          f" ({r['red'] / max(1, r['red_pages']):.1f} a page with red)")
    for k in ("could pair", "not (scan)", "not (json)"):
        print(f"  {k}: {r['tally'][k]}")
    random.seed(2)
    random.shuffle(r["left"])
    print("== 40 of what is left:")
    for u in r["left"][:40]:
        print("  ", u)


if __name__ == "__main__":
    main(sys.argv[1:])
