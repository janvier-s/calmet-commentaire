"""Insert the Psalms verses missing from the transcription, with their Latin from the Vulgate.

For each verse psalms_check.py reports missing, a verse is inserted after the verse
before it, with:
  - latin: the Vulgate text (Calmet's Latin is nearly the same; check against the scan)
  - french: "" (to type from the scan)
  - annotations: a note saying the Latin came from the Vulgate
  - verse_number: the gap left in Calmet's numbering (e.g. 1, 2, 4 -> 3)
Where Calmet's numbers leave no gap, nothing is inserted and the verse is listed instead.

Usage: python3 fill_psalm_verses.py [--dry-run] [volume]   (default 21a_psaumes)
"""
import json
import re
import sys

import psalms_check as P
from paths import DATA

NOTE = ("Latin from the Vulgate (verse missing from the transcription): check it against the scan, "
        "keep only the part Calmet prints under this number, and type his French")


def main(argv):
    dry = "--dry-run" in argv
    vol = next((a for a in argv if not a.startswith("--")), "21a_psaumes")
    rows, issues = P.check(vol)
    missing = []
    for i in issues:
        if i["kind"] == "missing":
            ps, v = map(int, re.match(r"Ps (\d+):(\d+)", i["msg"]).groups())
            missing.append((ps, v))
    pages, inserted, skipped = {}, [], []
    # insert from the last so earlier insertions don't shift the indexes still to use
    plan = []
    # missing verses that fall in the same gap between two transcribed verses
    groups = {}
    for ps, v in missing:
        rs = [r for r in rows if r["psalm"] == ps and isinstance(r["number"], int)]
        before = [r for r in rs if r["vulgate"] and r["vulgate"] < v]
        # a transcribed verse holding part of verse v (Calmet split it) comes after the missing part
        after = [r for r in rs if r["vulgate"] and r["vulgate"] >= v]
        prev, nxt = (before[-1] if before else None), (after[0] if after else None)
        key = (ps, id(prev), id(nxt))
        groups.setdefault(key, dict(ps=ps, prev=prev, nxt=nxt, verses=[]))["verses"].append(v)
    for g in groups.values():
        ps, prev, nxt, vs = g["ps"], g["prev"], g["nxt"], sorted(g["verses"])
        if prev and nxt:
            first, room = prev["number"] + 1, nxt["number"] - prev["number"] - 1
        elif prev:
            first, room = prev["number"] + 1, len(vs)  # the end of the psalm
        elif nxt:
            first, room = max(nxt["number"] - len(vs), 1), nxt["number"] - 1
        else:
            first, room = 1, 0
        if room >= len(vs):
            numbered = [(first + k, [v]) for k, v in enumerate(vs)]
        elif room == 1:
            numbered = [(first, vs)]  # Calmet prints them as one verse
        else:
            skipped += [(ps, v, prev and prev["number"], nxt and nxt["number"]) for v in vs]
            continue
        anchor = prev or nxt
        index = anchor["index"] + (1 if prev else 0)
        for k, (number, group) in enumerate(numbered):
            plan.append((anchor["page"], index, k, ps, group, number))
    # several missing verses after the same anchor go in Vulgate order
    # from the end of each page backwards, so earlier insertions don't shift later indexes
    for page, index, k, ps, group, number in sorted(plan, key=lambda t: (t[0], t[1], t[2]), reverse=True):
        path = DATA / vol / "normalized" / f"page_{page:04d}.json"
        d = pages.setdefault(path, json.loads(path.read_text(encoding="utf-8")))
        d["verses"].insert(index, {"verse_number": number, "latin": " ".join(P.VULGATE_TEXT[ps][v] for v in group),
                                   "french": "", "annotations": NOTE})
        inserted.append((ps, group, number, page))
    for ps, group, number, page in sorted(inserted):
        print(f"Ps {ps}:{'-'.join(map(str, group))} (Vulgate) -> verse {number} on page {page}")
    for ps, v, a, b in skipped:
        print(f"NOT inserted: Ps {ps}:{v} (Vulgate): Calmet's numbers go {a} -> {b} with no gap; check the scan")
    if not dry:
        for path, d in pages.items():
            path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{sum(len(g) for _, g, _, _ in inserted)} Vulgate verses as {len(inserted)} verses {'would be ' if dry else ''}inserted on {len(pages)} pages, {len(skipped)} left for you")


if __name__ == "__main__":
    main(sys.argv[1:])
