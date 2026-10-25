"""Proposed fixes the editor offers with Accept / Edit / Reject.

A proposal is {id, item, title, why, flags, sure, options: [{label, changes: [{vol, page, path, old,
new}]}]}: each change sets one field (path = [section, index, field]) that must still read `old`.
They come from footnotes.py's held write-outs (docs/footnotes/<vol>.json) and ref_check.py's candidates
(docs/ref_check.json), which become queue items of their own kinds, and from seam_join.py at a page
turn (review_turns.py), computed from the pages as they are now.
"""
import hashlib
import json
import re
from collections import defaultdict

from review_store import Conflict
from review_turns import TURN_KINDS, seam_proposal, turn_of

FIELD = re.compile(r"(\w+)\[(\d+)\]\.(\w+)")


def _md5(*parts):
    return hashlib.md5("\0".join(str(x) for x in parts).encode()).hexdigest()[:8]


def _read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _page_of(where):
    """'vol/page_0194' -> (vol, 194)."""
    vol, _, stem = where.partition("/")
    return vol, int(stem[5:9])


def _footnote_items(store, vol):
    report = _read_json(store.docs / "footnotes" / f"{vol}.json")
    out = []
    for n in (report or {}).get("notes") or []:
        if n.get("proposed") in (None, n.get("text")):
            continue
        page = int(n["page"][5:9])
        notes = (store._load(vol, page) or {}).get("footnotes") or []  # gone or malformed: nothing
        i = next((i for i, f in enumerate(notes)
                  if f.get("marker") == n["marker"] and f.get("text") == n["text"]), None)
        if i is None:  # written out or edited since
            continue
        iid = f"{vol}/{page:04d}/footnote_writeout/{_md5(n['marker'], n['text'])}"
        out.append({"id": iid, "book_dir": vol, "page": page, "kind": "footnote_writeout", "optional": False,
                    "msg": f"{n['marker'] or ''} {n['text'][:80]} → {n['proposed'][:80]}".strip(),
                    "where": {"section": "footnotes", "index": i, "field": "text"},
                    "proposal": {"id": iid, "item": iid, "title": "Footnote write-out", "why": n.get("why") or [],
                                 "flags": n.get("flags") or [], "sure": False,
                                 "options": [{"label": "write-out", "changes": [
                                     {"vol": vol, "page": page, "path": ["footnotes", i, "text"],
                                      "old": n["text"], "new": n["proposed"]}]}]}})
    return sorted(out, key=lambda it: it["page"])


def _ref_items(store, volumes):
    report = _read_json(store.docs / "ref_check.json")
    out = []
    for r in (report or {}).get("items") or []:
        m = FIELD.fullmatch(r.get("field") or "")
        if not r.get("candidates") or not m:
            continue
        vol, page = _page_of(r["where"])
        if vol not in volumes:
            continue
        section, i, name = m.group(1), int(m.group(2)), m.group(3)
        entries = (store._load(vol, page) or {}).get(section) or []
        old = entries[i].get(name) if i < len(entries) else None
        if not isinstance(old, str) or old.count(r["written"]) != 1:
            continue
        iid = f"{vol}/{page:04d}/ref_candidate/{_md5(r['field'], r['written'])}"
        options = [{"label": c[0], "changes": [{"vol": vol, "page": page, "path": [section, i, name], "old": old,
                                                "new": old.replace(r["written"], c[0])}]} for c in r["candidates"]]
        out.append({"id": iid, "book_dir": vol, "page": page, "kind": "ref_candidate", "optional": False,
                    "msg": f"{r['written']}: {r['kind']} — “…{(r.get('context') or '')[-80:]}”",
                    "where": {"section": section, "index": i, "field": name},
                    "proposal": {"id": iid, "item": iid, "title": f"Verse reference {r['written']}",
                                 "why": [r["kind"]], "flags": [], "sure": False, "options": options}})
    return out


def generated_items(store):
    """Queue items for the write-outs and reference candidates that still apply to the pages."""
    volumes = store.volumes()
    out = []
    for vol in volumes:
        out += _footnote_items(store, vol)
    return out + _ref_items(store, set(volumes))


def proposal_for(store, progress, item):
    """The item's proposal, or None (none, or rejected)."""
    p = item.get("proposal")
    if p is None and item["kind"] in TURN_KINDS:
        t = turn_of(store, item)
        p = t and seam_proposal(store, *t)
        if p:
            p = dict(p, item=item["id"])
    if p and progress.status("proposal:" + p["id"]) == "rejected":
        return None
    return p


def apply(store, proposal, option=0, edited=None):
    """Write one option of a proposal. Every field must still read `old`, or nothing is written."""
    changes = proposal["options"][option]["changes"]
    by_page = defaultdict(list)
    for k, c in enumerate(changes):
        by_page[(c["vol"], c["page"])].append((c, edited[k] if edited is not None else c["new"]))
    loaded = {}
    for (vol, page), cs in by_page.items():
        data, version = store.read(vol, page)
        for c, _ in cs:
            section, i, name = c["path"]
            entries = data.get(section) or []
            if i >= len(entries) or entries[i].get(name) != c["old"]:
                raise Conflict(data, version)
        loaded[(vol, page)] = (data, version)
    out = {}
    for (vol, page), cs in by_page.items():
        data, version = loaded[(vol, page)]
        for c, new in cs:
            section, i, name = c["path"]
            data[section][i][name] = new
        d, v = store.save(vol, page, data, version)
        out[page] = {"data": d, "version": v}
    return {"pages": out}
