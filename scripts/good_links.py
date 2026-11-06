"""Good_Calmet footnotes linked by hand to normalized footnotes (docs/good_notes_links/<vol>.json).

A link fixes what good_notes.py's pairing gets wrong, once: good_notes.py reads the links before it pairs,
takes them as fixed pairs (or fixed singles), and pairs the rest around them. The file is kept apart from
the normalized JSON:

    {"links": [{"json": {page, marker, index} | [...], "good": {pdf, pdf_page, mark[, n]} | [...],
                "kind": "same" | "merged" | "split" | "none", "by": ..., "at": ...}]}

same: one Good note, one normalized note. merged: one Good note holding several normalized notes. split:
several Good notes for one normalized note. none: the note (one side only, the other null) truly has no
counterpart, a real addition or drop. A Good note is its PDF, PDF page and mark (n, its place among the
page's notes, when two share a mark); a normalized note its page and index, its marker a check (a note
inserted before it moves its index: then the page's note with that marker, when only one has it).
"""
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from paths import DOCS

KINDS = ("same", "merged", "split", "none")


def path(vol, docs=None):
    return Path(docs or DOCS) / "good_notes_links" / f"{vol}.json"


def load(vol, docs=None):
    """The volume's links, [] when it has none."""
    f = path(vol, docs)
    try:
        return json.loads(f.read_text(encoding="utf-8")).get("links") or []
    except FileNotFoundError:
        return []


def save(vol, links, docs=None):
    f = path(vol, docs)
    f.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=f.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump({"links": links}, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    os.replace(tmp, f)


def mark_key(m):
    """A mark's letter or number, lower case: (a) a) ca) [b] -> a, b (as good_notes.mark_key)."""
    t = re.sub(r"[^\w]", "", m or "").lower()
    return t[-1:] if len(t) == 2 and t[0] in "ct" and t[1].isalpha() else t


def side(e, name):
    """One side of a link as a list ([] for a none's empty side)."""
    v = e.get(name)
    return [] if v is None else v if isinstance(v, list) else [v]


def json_id(j):
    return {"page": j["page"], "marker": j.get("marker", j.get("mark")), "index": j["index"]}


def good_id(g):
    out = {"pdf": g["pdf"], "pdf_page": g.get("pdf_page", g.get("page")), "mark": g["mark"]}
    if g.get("n") is not None:
        out["n"] = g["n"]
    return out


def same_json(a, b):
    return a["page"] == b["page"] and a["index"] == b["index"]


def same_good(a, b):
    if (a["pdf"], a["pdf_page"]) != (b["pdf"], b["pdf_page"]):
        return False
    if a.get("n") is not None and b.get("n") is not None:
        return a["n"] == b["n"]
    return mark_key(a["mark"]) == mark_key(b["mark"])


def find_json(ref, notes):
    """The index in `notes` (dicts with page, index, mark or marker) of the note a link names, or None."""
    here = [k for k, j in enumerate(notes) if j["page"] == ref["page"]]
    mk = lambda j: mark_key(j.get("marker", j.get("mark")))
    k = next((k for k in here if notes[k]["index"] == ref["index"]), None)
    if k is not None and (not ref.get("marker") or mk(notes[k]) == mark_key(ref["marker"])):
        return k
    same = [k for k in here if ref.get("marker") and mk(notes[k]) == mark_key(ref["marker"])]
    return same[0] if len(same) == 1 else None


def find_good(ref, notes):
    """The index in `notes` (dicts with pdf, page or pdf_page, mark, n) of the Good note a link names."""
    here = [k for k, g in enumerate(notes) if g["pdf"] == ref["pdf"] and g.get("pdf_page", g.get("page")) == ref["pdf_page"]]
    if ref.get("n") is not None:
        k = next((k for k in here if notes[k].get("n") == ref["n"]), None)
        if k is not None and mark_key(notes[k]["mark"]) == mark_key(ref["mark"]):
            return k
    same = [k for k in here if mark_key(notes[k]["mark"]) == mark_key(ref["mark"])]
    return same[0] if len(same) == 1 else None


def resolve(links, goods, jsons):
    """The links as indices into a chapter's notes: [(good indices, json indices, link)], each sorted; a link
    whose notes are not all among them (another chapter's, or gone) left out, and named in the second list."""
    out, stale = [], []
    for e in links:
        gs, js = side(e, "good"), side(e, "json")
        gi = [find_good(g, goods) for g in gs]
        ji = [find_json(j, jsons) for j in js]
        if None in gi or None in ji:
            if any(x is not None for x in gi + ji):
                stale.append(e)  # some of its notes here, not all: a mark or index that moved
            continue
        out.append((tuple(sorted(gi)), tuple(sorted(ji)), e))
    return out, stale


def kind_of(goods, jsons):
    if not goods or not jsons:
        return "none"
    if len(goods) == 1 and len(jsons) == 1:
        return "same"
    if len(goods) == 1:
        return "merged"
    if len(jsons) == 1:
        return "split"
    raise ValueError("several notes on both sides")


def touches(e, goods=(), jsons=()):
    return (any(same_good(a, b) for a in side(e, "good") for b in goods)
            or any(same_json(a, b) for a in side(e, "json") for b in jsons))


def link(links, goods, jsons, by="editor"):
    """The links with one added for these notes (Good ids, normalized ids; one side empty for a none): the
    links any of them was in before are dropped. Returns (links, the new link)."""
    goods, jsons = [good_id(g) for g in goods], [json_id(j) for j in jsons]
    if not goods and not jsons:
        raise ValueError("no note")
    kind = kind_of(goods, jsons)
    one = lambda xs: None if not xs else xs[0] if len(xs) == 1 else xs
    e = {"json": one(jsons), "good": one(goods), "kind": kind, "by": by,
         "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    return [x for x in links if not touches(x, goods, jsons)] + [e], e


def unlink(links, goods=(), jsons=()):
    """The links without those any of these notes is in."""
    goods, jsons = [good_id(g) for g in goods], [json_id(j) for j in jsons]
    return [x for x in links if not touches(x, goods, jsons)]
