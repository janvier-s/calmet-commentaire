"""Compare sonnet's and agy's expansions of the same footnotes, straight from the cache. Read-only.

    python3 compare_expansions.py [--show N] [--out FILE]

Rebuilds, for every volume, the notes the expansion stage of footnotes.py would send (same stages,
same order, --no-scan so nothing is called), then looks up each note's answer under the sonnet key
and under the agy key (the keys answer_key() builds, one per model). Only a key the model itself
wrote counts: an agy run that reused a sonnet answer shows as "sonnet only", not "both".

Prints counts per volume and totals, then the first N differing pairs. The full list of differing
pairs goes to --out (default scripts/cache/expansion_compare.json). Never writes footnote_cache.json.
"""
import asyncio
import contextlib
import copy
import io
import json
import re
import sys
from collections import Counter

import footnotes as F

SONNET = "sonnet"
AGY = "agy:gemini-3.8-flash-low"
DEFAULT_OUT = F.SCRIPTS / "cache" / "expansion_compare.json"


def key_for(n, model):
    """The same key expand_stage/answer_key uses for this note and model."""
    raw = n["raw"] if "garbled-reference" in n["flags"] else ""
    return F.key("exp2", model, n["proposed"], n["prev"], raw)


def main(argv):
    show = int(argv[argv.index("--show") + 1]) if "--show" in argv else 5
    out = argv[argv.index("--out") + 1] if "--out" in argv else DEFAULT_OUT
    cache = json.loads(F.CACHE.read_text(encoding="utf-8"))
    lo, hi = F.page_range([])
    F.NO_CALLS = True  # nothing is called: the stages only read the cache
    totals, diffs = Counter(), []

    for vol in sorted(F.BY_VOLUME):
        if not (F.DOCS / "footnotes" / f"{vol}.json").exists():
            continue
        notes = F.load_volume(vol, lo, hi)
        with contextlib.redirect_stdout(io.StringIO()):  # the stages print their own counts
            F.local_stage(notes)
            asyncio.run(F.scan_stage(vol, notes, copy.deepcopy(cache), False))
            F.expand_local(notes)
        c = Counter()
        for n in notes:
            if n["done"] or not (F.needs_expansion(n["proposed"]) or "garbled-reference" in n["flags"]
                                 or re.search(r"\b(?:Samuel|Chroniques)\b", n["proposed"])):
                continue
            if {"scan-unread", "hebrew", "greek", "uncertain"} & set(n["flags"]):
                c["held (flags)"] += 1  # expand_stage skips these: waiting for the scan
                continue
            ks, ka = key_for(n, SONNET), key_for(n, AGY)
            hs, ha = ks in cache, ka in cache
            c["eligible"] += 1
            if hs and ha:
                c["both"] += 1
                if cache[ks].strip() == cache[ka].strip():
                    c["same"] += 1
                else:
                    c["differ"] += 1
                    diffs.append({"volume": vol, "id": n["id"], "page": n["page"], "proposed": n["proposed"],
                                  "sonnet": cache[ks], "agy": cache[ka]})
            elif hs:
                c["sonnet only"] += 1
            elif ha:
                c["agy only"] += 1
            else:
                c["neither"] += 1
        if c["eligible"]:
            print(f"{vol}: " + ", ".join(f"{k} {v}" for k, v in c.items()))
        totals += c

    print("TOTAL: " + ", ".join(f"{k} {v}" for k, v in totals.items()))
    for d in diffs[:show]:
        print(f"\n{d['volume']} {d['id']} ({d['page']})\n  proposed: {d['proposed']}\n  sonnet:   {d['sonnet']}\n  agy:      {d['agy']}")
    out_path = F.Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(diffs, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{len(diffs)} differing pairs written to {out_path}")


if __name__ == "__main__":
    main(sys.argv[1:])
