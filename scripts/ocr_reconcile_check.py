"""The fixed OCR alignment checked on chosen pages: what it changes, and whether it still sees planted words.

    python ocr_reconcile_check.py <vol>:<page> ...      e.g. 07_juges:286 21a_psaumes:363

Reads cache/ocr/<vol>/ (never runs Kraken), cache/tess/<vol>/ (run tess_ocr.py first) and
data/<vol>/normalized/; writes nothing. For each page: the count of each status, plain and fixed with
Tesseract; every red (a scan word `missing`, a JSON word `extra`) the fix took away and what it paired it
to; the `both` list; the italics stretches found on each alignment; then the planted check.

The planted check, on a deep copy of the page (the seed: the page's name): two words deleted from a
verse's Latin, two from its French and two from the commentary (the first of each pair at the end of a
line on the scan, if one can be), ZZplant1 and ZZplant2 inserted, one word replaced by an unrelated real
word. Pass: a deleted word's scan box is `missing`, an inserted word is in `extra`, the replaced word's
scan box is not paired as the same word (diff, missing or both). A field the page lacks gets no plant.
Exits 1 if a planted word fails.
"""
import collections
import copy
import json
import random
import re
import sys

import scan_ocr as O
import tess_ocr
from paths import DATA

RED = ("missing",)
UNRELATED = "éléphant"  # the real word put in place of one


def load(vol, page):
    o = json.loads((O.OCR_CACHE / vol / f"page_{page:04d}.json").read_text(encoding="utf-8"))
    data = json.loads((DATA / vol / "normalized" / f"page_{page:04d}.json").read_text(encoding="utf-8"))
    return o, data, tess_ocr.read(vol, page)


def field(data, path):
    cur = data
    for p in path.split("/"):
        cur = cur[int(p)] if p.isdigit() else cur.get(p)
        if cur is None:
            return None
    return cur


def set_field(data, path, value):
    *head, last = path.split("/")
    cur = data
    for p in head:
        cur = cur[int(p)] if p.isdigit() else cur[p]
    cur[last] = value


def text_of(data, path, a, b):
    s = field(data, path)
    return s[a:b] if isinstance(s, str) else "?"


def scan_lines(o):
    """The line of each of align's scan words (index-identical to its `words`)."""
    o2 = O.split_columns(o)
    skip = O.skipped_lines(o2, True)
    return [[li for li, _ in t["src"]] for t in O.ocr_tokens(o2) if t["line"] not in skip]


def counts(res):
    c = collections.Counter(w["s"] for w in res["words"])
    c["extra"] = len(res["extra"])
    return c


# --- the report

def report(vol, page, o, data, tess, plain, fixed):
    ws0, ws1 = plain["words"], fixed["words"]
    keys = ["ok", "near", "diff", "both", "missing", "skip", "extra"]
    c0, c1 = counts(plain), counts(fixed)
    print(f"  {'':10}" + "".join(f"{k:>9}" for k in keys) + f"{'red':>9}")
    for name, c in (("plain", c0), ("fixed+tess", c1)):
        print(f"  {name:10}" + "".join(f"{c[k]:>9}" for k in keys) + f"{c['missing'] + c['extra']:>9}")
    print(f"  tesseract reading used: {fixed.get('tess')}")

    gone = []
    for i, (a, b) in enumerate(zip(ws0, ws1)):
        if a["s"] in RED and b["s"] not in RED:
            to = (f"{b.get('path')} {b.get('a')}-{b.get('b')} {text_of(data, b['path'], b['a'], b['b'])!r}"
                  if b.get("path") else "(unpaired)")
            gone.append(f"scan {a['t']!r} -> {b['s']}{' by tess' if b.get('by') == 'tess' else ''}: {to}")
    fx = {(e["path"], e["a"]) for e in fixed["extra"]}
    for e in plain["extra"]:
        if (e["path"], e["a"]) in fx:
            continue
        by = [w for w in ws1 if w.get("path") == e["path"] and w["a"] <= e["a"] < w["b"]]
        to = ", ".join(f"scan {w['t']!r} ({w['s']}{' by tess' if w.get('by') == 'tess' else ''})" for w in by) \
            or "no longer flagged (not paired)"
        gone.append(f"json {e['t']!r} @{e['path']} -> {to}")
    new = sum(1 for a, b in zip(ws0, ws1) if b["s"] in RED and a["s"] not in RED)
    px = {(e["path"], e["a"]) for e in plain["extra"]}
    new += sum(1 for e in fixed["extra"] if (e["path"], e["a"]) not in px)
    print(f"  red gone ({len(gone)}), red new ({new}):")
    for g in gone:
        print("    ", g)

    both = [w for w in ws1 if w["s"] == "both"]
    print(f"  both ({len(both)}):")
    for w in both:
        print(f"     scan {w['t']!r} tess {w.get('tt')!r} json {text_of(data, w['path'], w['a'], w['b'])!r}"
              f" @{w['path']} (was {w.get('was')})")

    i0, i1 = O.italics(o, data, ws0), O.italics(o, data, ws1)
    print(f"  italics: plain {len(i0)}, fixed+tess {len(i1)}{'' if len(i0) == len(i1) else '  (DIFFER)'}")
    return {"red": (c0["missing"] + c0["extra"], c1["missing"] + c1["extra"]), "both": len(both),
            "italics": (len(i0), len(i1))}


# --- the planted check

def candidates(o, data, res, lines, path):
    """Scan words paired `ok` to one whole word of `path`, safe from the flags that hide a missing word
    (a low confidence, the top and bottom bands, the footnotes, a numeral): [(index, at a line's end)]."""
    ws, h = res["words"], o["size"][1]
    s = field(data, path)
    fn_top = min((w["boxes"][0][1] for w in ws if (w.get("path") or "").startswith("footnotes/")), default=h)
    out = []
    for i, w in enumerate(ws):
        if w.get("path") != path or w["s"] != "ok" or w.get("by"):
            continue
        word = s[w["a"]:w["b"]]
        if not O.TOKEN.fullmatch(word) or len(O.key(word)) < 4 or O.numeral(word) or O.misread_numeral(w["t"]):
            continue
        if any(0 <= n < len(ws) and ws[n].get("path") == path and ws[n].get("a") == w["a"] for n in (i - 1, i + 1)):
            continue  # a word the scan splits in pieces
        y = w["boxes"][0][1]
        if w["wc"] < 0.6 or y < 0.1 * h or y > 0.85 * h or y >= fn_top - 20:
            continue
        end = i + 1 >= len(ws) or lines[i + 1][0] != lines[i][-1] or len(set(lines[i])) > 1
        out.append((i, end))
    return out


def plant(vol, page, o, data, fixed):
    """[(kind, path, word, scan index or None)], the planted copy."""
    rnd = random.Random(f"{vol}:{page}")
    lines = scan_lines(o)
    ws = fixed["words"]
    verses = data.get("verses") or []
    comms = data.get("commentary") or []
    targets = {"latin": [f"verses/{i}/latin" for i, v in enumerate(verses) if v.get("latin")],
               "french": [f"verses/{i}/french" for i, v in enumerate(verses) if v.get("french")],
               "commentary": [f"commentary/{i}/french_commentary" for i, c in enumerate(comms) if c.get("french_commentary")]}
    edits, plants, taken, notes = [], [], set(), []

    def far(i):
        return all(abs(i - t) >= 3 for t in taken)

    for kind, paths in targets.items():
        pool = [(p, c) for p in paths for c in candidates(o, data, fixed, lines, p)]
        if not pool:
            notes.append(f"no {kind} field with a word to delete: no plant there")
            continue
        n = 4 if kind == "commentary" and not targets["latin"] and not targets["french"] else 2
        for k in range(n):
            ends = [(p, c) for p, c in pool if c[1] and far(c[0])]
            rest = [(p, c) for p, c in pool if far(c[0])]
            choice = (ends if k == 0 and ends else rest)
            if not choice:
                notes.append(f"{kind}: only {k} word(s) could be deleted")
                break
            p, (i, end) = rnd.choice(choice)
            taken.add(i)
            s = field(data, p)
            a, b = ws[i]["a"], ws[i]["b"]
            plants.append(("delete", p, s[a:b], i, end))
            b2 = b + 1 if s[b:b + 1] == " " else b
            a2 = a - 1 if b2 == b and s[a - 1:a] == " " else a
            edits.append((p, a2, b2, ""))
        if not any(pl[0] == "delete" and pl[1] in paths and pl[4] for pl in plants):
            notes.append(f"{kind}: no deleted word at a line's end on the scan")

    # inserted: ZZplant1 in a verse (else the commentary), ZZplant2 in the commentary
    for word, where in (("ZZplant1", targets["latin"] or targets["french"] or targets["commentary"]),
                        ("ZZplant2", targets["commentary"] or targets["latin"] or targets["french"])):
        pool = [(p, c[0]) for p in where for c in candidates(o, data, fixed, lines, p) if far(c[0])]
        if not pool:
            notes.append(f"{word}: nowhere to insert it")
            continue
        p, i = rnd.choice(pool)
        taken.add(i)
        edits.append((p, ws[i]["b"], ws[i]["b"], " " + word))
        plants.append(("insert", p, word, None, False))

    # replaced: one commentary word (else a verse's) by an unrelated real word
    where = targets["commentary"] or targets["french"] or targets["latin"]
    pool = [(p, c[0]) for p in where for c in candidates(o, data, fixed, lines, p) if far(c[0])]
    if pool:
        p, i = rnd.choice(pool)
        taken.add(i)
        s = field(data, p)
        plants.append(("replace", p, f"{s[ws[i]['a']:ws[i]['b']]} -> {UNRELATED}", i, False))
        edits.append((p, ws[i]["a"], ws[i]["b"], UNRELATED))
    else:
        notes.append("nowhere to replace a word")

    planted = copy.deepcopy(data)
    for p, a, b, new in sorted(edits, key=lambda e: (e[0], -e[1])):  # the last first: the offsets hold
        s = field(planted, p)
        set_field(planted, p, s[:a] + new + s[b:])
    return plants, planted, notes


def verdict(kind, word, i, res, planted):
    if kind == "delete":
        w = res["words"][i]
        return w["s"] == "missing", (f"scan box {w['s']}" + (f" paired to {text_of(planted, w['path'], w['a'], w['b'])!r}"
                                                             f" @{w['path']} {w['a']}-{w['b']}"
                                                             f"{' by tess' if w.get('by') == 'tess' else ''}"
                                                             if w.get("path") else ""))
    if kind == "insert":
        hit = [e for e in res["extra"] if e["t"] == word]
        return bool(hit), ("in extra" if hit else "not in extra")
    w = res["words"][i]
    return w["s"] in ("diff", "missing", "both"), f"scan {w['t']!r} {w['s']}"


def planted_check(vol, page, o, data, tess, fixed):
    plants, planted, notes = plant(vol, page, o, data, fixed)
    pf = O.align(o, planted, fix=True, tess=tess)
    pp = O.align(o, planted)
    for n in notes:
        print("     note:", n)
    ok = 0
    for kind, path, word, i, end in plants:
        good, got = verdict(kind, word, i, pf, planted)
        _, got0 = verdict(kind, word, i, pp, planted)
        ok += good
        print(f"     {'PASS' if good else 'FAIL'} {kind:7} {word!r} @{path}{' (line end)' if end else ''}:"
              f" fixed+tess {got}; plain {got0}")
    return ok, len(plants)


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    fails, summary = 0, []
    for arg in argv:
        vol, page = arg.rsplit(":", 1)
        page = int(page)
        o, data, tess = load(vol, page)
        if not tess:
            print(f"{vol} p.{page}: no Tesseract reading (run tess_ocr.py {vol} {page})")
        print(f"== {vol} p.{page}")
        plain = O.align(o, data)
        fixed = O.align(o, data, fix=True, tess=tess)
        r = report(vol, page, o, data, tess, plain, fixed)
        print("  planted:")
        ok, n = planted_check(vol, page, o, data, tess, fixed)
        fails += n - ok
        summary.append(f"{vol}:{page}  red {r['red'][0]}->{r['red'][1]}  both {r['both']}"
                       f"  italics {r['italics'][0]}/{r['italics'][1]}  planted {ok}/{n}")
    print("== summary")
    for s in summary:
        print("  ", s)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
