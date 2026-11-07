"""good_normalized: Good's text cleaned once, every automatic change a record the editor can undo.

    python3 good_normalized.py 01_genese             # (re)compute data/<vol>/good_normalized.json
    python3 good_normalized.py 01_genese --preview   # write nothing: every distinct change, word by word

Per change of good_units.json (by its id) the store keeps `src` (a hash of the text the cleaning started from:
good_italic, else good_punct, else good_modern) and `records`: [{i, before, after, rule}] from
good_clean.clean_records, plus `agent` records (good_spell_agent.py) located by their words. The decisions of
the user to take a change back are kept apart, in docs/good_merge/<vol>_normalized.json:

    {"vol": ..., "undone": {change id: [record key, ...]}}      record key = "before => after"

so a recompute never loses them, and the store itself can be rebuilt at any time. `overlay(doc, ...)` puts
`good_normalized` (the cleaned text, undone records left as they were) and `good_records` (for the list with
Undo) on the changes of a good_units document; merge_build.good_text takes `good_normalized` first.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import good_clean
from paths import DATA, DOCS


def store_path(data, vol):
    return Path(data) / vol / "good_normalized.json"


def undone_path(docs, vol):
    return Path(docs) / "good_merge" / f"{vol}_normalized.json"


def source(c):
    """The text the cleaning starts from, or None."""
    return next((c[k] for k in ("good_italic", "good_punct", "good_modern") if c.get(k) is not None), None)


def src_hash(text):
    return hashlib.md5((text or "").encode()).hexdigest()[:10]


def key(r):
    return f"{r['before']} => {r['after']}"


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def compute(doc, old=None):
    """{"changes": {id: {src, records[, agent]}}}: records for every change the cleaning alters. The agent
    records of `old` (another pass's, not recomputable) are kept while the source text is the same."""
    out = {}
    for u in doc.get("units") or []:
        for c in u.get("changes") or []:
            text = source(c)
            if not text:
                continue
            final, recs = good_clean.clean_records(text)
            keep = (old or {}).get(c["id"], {})
            agent = keep.get("agent") if keep.get("src") == src_hash(text) else None
            if recs or agent:
                out[c["id"]] = {"src": src_hash(text), "records": recs, **({"agent": agent} if agent else {})}
    return {"vol": doc.get("vol"), "changes": out}


def locate_agent(words, agent, undone=()):
    """Agent records (before, after, ctx) applied to `words` (a list) where their words are, in order; the
    ones not found are skipped. Returns (new words, [applied or not per record])."""
    out, at, found = list(words), 0, []
    for k, r in enumerate(agent):
        b = r["before"].split()
        pos = None
        for i in range(at, len(out) - len(b) + 1):
            if out[i:i + len(b)] == b and out[max(0, i - len(r.get("ctx", "").split())):i] == r.get("ctx", "").split():
                pos = i
                break
        found.append(pos is not None)
        if pos is not None and key(r) not in undone:
            out[pos:pos + len(b)] = r["after"].split()
            at = pos + len(r["after"].split())
        elif pos is not None:
            at = pos + len(b)
    return out, found


def cleaned(text, entry, undone=()):
    """(cleaned text, records for the list [{i, before, after, rule, undone}]) for a change's source text."""
    recs = entry.get("records") or []
    skip = {k for k, r in enumerate(recs) if key(r) in undone}
    out = good_clean.apply_records(text, recs, skip)
    rows = [dict(r, undone=k in skip) for k, r in enumerate(recs)]
    agent = entry.get("agent") or []
    if agent:
        words, found = locate_agent(out.split(), agent, undone)
        out = " ".join(words)
        rows += [dict(r, i=None, rule=r.get("rule", "agent"), undone=key(r) in undone, lost=not f) for r, f in zip(agent, found)]
    return out, rows


def overlay(doc, store, undone):
    """Set good_normalized / good_records on every change of `doc` the store has a current entry for.
    A change whose source text moved on since the store was computed keeps none (it reads good_text as before)."""
    ch = (store or {}).get("changes") or {}
    for u in doc.get("units") or []:
        for c in u.get("changes") or []:
            e = ch.get(c["id"])
            c.pop("good_normalized", None)
            c.pop("good_records", None)
            text = source(c)
            if not e or not text or e["src"] != src_hash(text):
                continue
            new, rows = cleaned(text, e, set((undone or {}).get(c["id"], ())))
            c["good_records"] = rows
            if new != text:
                c["good_normalized"] = new
                if c.get("good_flags"):
                    c["good_flags_normalized"] = good_clean.remap_flags(c["good_flags"], text, new)
    return doc


def save_undo(docs, vol, change_id, record_key, undo=True):
    """Take a record back (or put it again); returns the change's undone keys."""
    p = undone_path(docs, vol)
    doc = load_json(p, {"vol": vol, "undone": {}})
    ks = doc.setdefault("undone", {}).setdefault(change_id, [])
    if undo and record_key not in ks:
        ks.append(record_key)
    if not undo and record_key in ks:
        ks.remove(record_key)
    if not ks:
        doc["undone"].pop(change_id, None)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return ks


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("vol")
    ap.add_argument("--preview", action="store_true", help="write nothing: list each distinct change")
    a = ap.parse_args(argv)
    doc = load_json(Path(DATA) / a.vol / "good_units.json", None)
    if doc is None:
        sys.exit(f"{a.vol}: no good_units.json")
    p = store_path(DATA, a.vol)
    old = load_json(p, {}).get("changes")
    st = compute(doc, old)
    if a.preview:
        seen = {}
        for e in st["changes"].values():
            for r in e["records"]:
                seen.setdefault((r["rule"], r["before"], r["after"]), 0)
                seen[(r["rule"], r["before"], r["after"])] += 1
        for (rule, b, af), n in sorted(seen.items()):
            print(f"{n:4d} {rule:14s} {b}  ->  {af}")
        print(f"{len(st['changes'])} changes altered, {sum(seen.values())} word changes, {len(seen)} distinct")
        return
    p.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{a.vol}: {len(st['changes'])} changes altered -> {p}")


if __name__ == "__main__":
    main()
