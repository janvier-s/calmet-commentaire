"""good_notes.py scored against the hand-labelled reference sets (data/good_notes_gold/*.json).

    python3 good_notes_eval.py [gold file ...]     (default: every reference set)

A reference set: {vol, chapters, items: [{label: real|noise|unsure, cause: edition|normalization, kind,
page, json_mark, pdf, pdf_page, good_mark, note}], missed: [real differences not reported]}. A candidate
is an item when kind and JSON page agree and either the JSON note (its mark) or the Good note (pdf, page,
mark) is the same. Prints the real ones found, the noise still reported, and the new candidates.
"""
import json
import sys

from paths import DATA
import good_notes as gn

GOLD = DATA / "good_notes_gold"


def key(c):
    g = (c.get("good") or [{}])[0]
    return (c["kind"], c["page"], gn.mark_key(c.get("json_mark")) or None,
            (g.get("pdf"), g.get("pdf_page"), gn.mark_key(c.get("good_mark"))) if g else None)


def same(c, it):
    if c["kind"] != it["kind"] or c["page"] != it["page"]:
        return False
    jm = gn.mark_key(it.get("json_mark")) or None
    gm = (it.get("pdf"), it.get("pdf_page"), gn.mark_key(it.get("good_mark"))) if it.get("pdf") else None
    k = key(c)
    return (jm is not None and k[2] == jm) or (gm is not None and k[3] == gm)


def score(f):
    ref = json.loads(f.read_text(encoding="utf-8"))
    got, _ = gn.compare(ref["vol"], set(ref["chapters"]))
    items = [dict(g, missed=False) for g in ref["items"]] + [dict(g, label="real", missed=True) for g in ref.get("missed", [])]
    hit = [next((c for c in got if same(c, it)), None) for it in items]
    new = [c for c in got if not any(same(c, it) for it in items)]
    real = [i for i, it in enumerate(items) if it["label"] == "real"]
    found = [i for i in real if hit[i]]
    noise = [i for i, it in enumerate(items) if it["label"] == "noise" and hit[i]]
    print(f"{f.name}: real found {len(found)}/{len(real)}; noise reported {len(noise)}/"
          f"{sum(it['label'] == 'noise' for it in items)}; new {len(new)}")
    for i in real:
        if not hit[i]:
            it = items[i]
            print(f"   missed: {it['kind']} p{it['page']} {it.get('json_mark') or ''} {it.get('note', '')}")
    for i in noise:
        it = items[i]
        print(f"   noise:  {it['kind']} p{it['page']} {it.get('json_mark') or ''} {it.get('note', '')}")
    for c in new:
        g = (c.get("good") or [{}])[0]
        print(f"   new:    {c['kind']} p{c['page']} {c.get('json_mark') or ''} | JSON {(c.get('json_text') or '')[:80]!r}"
              f" | GOOD {g.get('pdf_page', '')} {c.get('good_mark') or ''} {(c.get('good_raw') or '')[:80]!r}")
    return len(found), len(real)


def main(argv):
    files = [__import__("pathlib").Path(a) for a in argv] or sorted(GOLD.glob("*.json"))
    for f in files:
        score(f)


if __name__ == "__main__":
    main(sys.argv[1:])
