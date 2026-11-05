"""good_variants.py scored against the hand-labelled reference sets (data/good_variants_gold/*.json).

    python3 good_variants_eval.py [gold file ...]     (default: every reference set)

A reference set: {vol, chapters, items: [{label: real|noise|unsure, page, path, at, kind, old, good, note}],
missed: [real differences the script did not report, found by reading]}. A candidate is the same as an
item on the same page when their words overlap (old and Good words, spelling-blind). Prints, per set: the
real ones found (of the real items and the missed), the noise still reported, and the new candidates (not
in the set: to label, then add).
"""
import json
import sys

from paths import DATA
import good_variants as gv
import scan_ocr

GOLD = DATA / "good_variants_gold"


def words(*texts):
    return {scan_ocr.key(t) for x in texts for t in scan_ocr.OCR_TOKEN.findall(x or "") if len(t) > 1}


def same(c, g):
    if c["page"] != g["page"]:
        return False
    a, b = words(c.get("old"), c.get("good_raw")), words(g.get("old"), g.get("good"))
    if not a or not b:
        return c["path"] == g["path"] and abs(c["at"] - g.get("at", -999)) <= 20
    return len(a & b) >= 0.5 * min(len(a), len(b))


def score(f):
    ref = json.loads(f.read_text(encoding="utf-8"))
    got = gv.variants(ref["vol"], set(ref["chapters"]))
    items = [dict(g, missed=False) for g in ref["items"]] + [dict(g, label="real", missed=True) for g in ref.get("missed", [])]
    # an item is found when some candidate is the same (a merged candidate may hold several items)
    hit = [next((c for c in got if same(c, g)), None) for g in items]
    new = [c for c in got if not any(same(c, g) for g in items)]
    real = [i for i, g in enumerate(items) if g["label"] == "real"]
    print(f"\n== {f.name}: {len(got)} candidates")
    print(f"   real found   {sum(hit[i] is not None for i in real)}/{len(real)}"
          f"  (of the {sum(items[i]['missed'] for i in real)} once missed: {sum(hit[i] is not None for i in real if items[i]['missed'])})")
    noise = [i for i, g in enumerate(items) if g["label"] == "noise"]
    print(f"   noise left   {sum(hit[i] is not None for i in noise)}/{len(noise)}")
    print(f"   unsure       {sum(hit[i] is not None for i, g in enumerate(items) if g['label'] == 'unsure')}")
    print(f"   new          {len(new)}")
    for tier in ("high", "low"):
        cs = [c for c in got if c.get("confidence", "high") == tier]
        lab = [next((g["label"] for g in items if same(c, g)), "new") for c in cs]
        print(f"   {tier:5} {len(cs):4} candidates: " + ", ".join(f"{k} {lab.count(k)}" for k in ("real", "noise", "unsure", "new")))
    for i in real:
        if hit[i] is None:
            g = items[i]
            print(f"   - lost real  p{g['page']} {g['kind']}: [{g['old'][:50]}] -> [{g['good'][:60]}]  {g.get('note', '')}")
    for i in noise:
        if hit[i] is not None:
            g = items[i]
            print(f"   - noise      p{g['page']}: [{g['old'][:40]}] -> [{g['good'][:50]}]  {g['note']}")
    for c in new:
        print(f"   - new        p{c['page']} {c['kind']}: [{c['old'][:50]}] -> [{(c.get('good_raw') or '')[:60]}]")


if __name__ == "__main__":
    for f in [__import__("pathlib").Path(a) for a in sys.argv[1:]] or sorted(GOLD.glob("*.json")):
        score(f)
