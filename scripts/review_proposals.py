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


def _footnote_items(store, vol, pages=None):
    report = _read_json(store.docs / "footnotes" / f"{vol}.json")
    out = []
    for n in (report or {}).get("notes") or []:
        if n.get("proposed") in (None, n.get("text")):
            continue
        page = int(n["page"][5:9])
        if pages is not None and page not in pages:
            continue
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


def _ref_items(store, volumes, pages=None):
    report = _read_json(store.docs / "ref_check.json")
    out = []
    for r in (report or {}).get("items") or []:
        m = FIELD.fullmatch(r.get("field") or "")
        if not r.get("candidates") or not m:
            continue
        vol, page = _page_of(r["where"])
        if vol not in volumes or (pages is not None and page not in pages):
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


def _gap_items(store, volumes, pages=None):
    """Words the scan has and the field lacks (docs/ocr_gaps.json, ocr_gaps.py), while the field still
    reads as it did around the place."""
    import scan_ocr
    report = _read_json(store.docs / "ocr_gaps.json")
    out = []
    for g in (report or {}).get("gaps") or []:
        if g["vol"] not in volumes or (pages is not None and g["page"] not in pages):
            continue
        path = g["path"].split("/")
        o = store._load(g["vol"], g["page"]) or {}
        for k in path:
            o = (o[int(k)] if int(k) < len(o) else None) if isinstance(o, list) and k.isdigit() else (o or {}).get(k)
        if not isinstance(o, str):
            continue
        pos = g["pos"] if o[:g["pos"]].endswith(g["before"]) and o[g["pos"]:].startswith(g["after"]) else None
        if pos is None and o.count(g["before"] + g["after"]) == 1:
            pos = o.index(g["before"] + g["after"]) + len(g["before"])
        if pos is None or g["text"] in o:  # the field changed there, or the words are in
            continue
        vol, page = g["vol"], g["page"]
        iid = f"{vol}/{page:04d}/ocr_gap/{_md5(g['path'], g['before'], g['ocr'])}"
        where = {"section": path[0], "index": int(path[1]), "field": path[2]} if len(path) == 3 else \
            {"section": "heading", "index": 0, "field": path[0]}
        change = {"vol": vol, "page": page, "path": [path[0], int(path[1]), path[2]] if len(path) == 3 else path,
                  "old": o, "new": scan_ocr.insert(o, pos, g["text"])}
        if g.get("note"):  # a whole note: a block to add by hand
            out.append({"id": iid, "book_dir": vol, "page": page, "kind": "ocr_gap", "optional": False,
                        "msg": f"A whole note missing? The scan has, after “…{g['before'][-40:]}”: “{g['ocr']}”",
                        "where": where})
            continue
        out.append({"id": iid, "book_dir": vol, "page": page, "kind": "ocr_gap", "optional": False,
                    "msg": f"The scan has “{g['ocr']}” after “…{g['before'][-40:]}”", "where": where,
                    "proposal": {"id": iid, "item": iid, "title": "Words missing (from the scan's OCR)",
                                 "why": ["Kraken reads these words on the scan; the text lacks them"],
                                 "flags": [], "sure": False, "options": [{"label": "put them in", "changes": [change]}]}})
    return out


def _italic_items(store, volumes, pages=None):
    """Words the scan prints in italics and the field in roman, or the other way (docs/ocr_gaps.json),
    while the field still reads so there."""
    from page_text import italic_runs, toggle_italics
    report = _read_json(store.docs / "ocr_gaps.json")
    out = []
    for r in (report or {}).get("italics") or []:
        if r["vol"] not in volumes or (pages is not None and r["page"] not in pages):
            continue
        path = r["path"].split("/")
        o = store._load(r["vol"], r["page"]) or {}
        for k in path:
            o = (o[int(k)] if int(k) < len(o) else None) if isinstance(o, list) and k.isdigit() else (o or {}).get(k)
        if not isinstance(o, str):
            continue
        a = r["a"] if o[r["a"]:r["b"]] == r["old"] and o[:r["a"]].endswith(r["before"]) else None
        if a is None and o.count(r["before"] + r["old"] + r["after"]) == 1:
            a = o.index(r["before"] + r["old"] + r["after"]) + len(r["before"])
        if a is None:  # the field changed there
            continue
        b = a + len(r["old"])
        italic = {i for x, y in italic_runs(o)[0] for i in range(x, y)}
        letters = [i for i in range(a, b) if o[i].isalnum()]
        if all((i in italic) == (r["to"] == "italic") for i in letters):  # done already
            continue
        t = toggle_italics(o, a, b) if r["to"] == "roman" or not all(i in italic for i in letters) else None
        if not t or t[0] == o:
            continue
        vol, page = r["vol"], r["page"]
        iid = f"{vol}/{page:04d}/ocr_italic/{_md5(r['path'], r['before'], r['old'])}"
        where = {"section": path[0], "index": int(path[1]), "field": path[2]} if len(path) == 3 else \
            {"section": "heading", "index": 0, "field": path[0]}
        change = {"vol": vol, "page": page, "path": [path[0], int(path[1]), path[2]] if len(path) == 3 else path,
                  "old": o, "new": t[0]}
        word = r["old"].replace("_", "").rstrip(" \t;:?!.,")
        said = "in italics; the text has it in roman" if r["to"] == "italic" else "in roman; the text has it in italics"
        out.append({"id": iid, "book_dir": vol, "page": page, "kind": "ocr_italic", "optional": False,
                    "msg": f"The scan prints “{word}” {said}", "where": where,
                    "proposal": {"id": iid, "item": iid, "title": "Italics as on the scan", "word": word,
                                 "why": [f"The words lean {r['slant']}° on the scan" if r["to"] == "italic"
                                         else f"The words stand upright on the scan ({r['slant']}°)"],
                                 "flags": [], "sure": False,
                                 "options": [{"label": "italicize" if r["to"] == "italic" else "make roman",
                                              "changes": [change]}]}})
    return out


GENERATED_KINDS = ("footnote_writeout", "ref_candidate", "ocr_gap", "ocr_italic")


def generated_items(store, volumes=None, pages=None):
    """Queue items for the write-outs, reference candidates and OCR gaps and italics that still apply."""
    volumes = list(volumes if volumes is not None else store.volumes())
    pset = set(pages) if pages is not None else None
    out = []
    for vol in volumes:
        out += _footnote_items(store, vol, pset)
    vset = set(volumes)
    return out + _ref_items(store, vset, pset) + _gap_items(store, vset, pset) + _italic_items(store, vset, pset)


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
            if len(c["path"]) == 1:  # a heading field
                if data.get(c["path"][0]) != c["old"]:
                    raise Conflict(data, version)
                continue
            section, i, name = c["path"]
            entries = data.get(section) or []
            if i >= len(entries) or entries[i].get(name) != c["old"]:
                raise Conflict(data, version)
        loaded[(vol, page)] = (data, version)
    out = {}
    for (vol, page), cs in by_page.items():
        data, version = loaded[(vol, page)]
        for c, new in cs:
            if len(c["path"]) == 1:
                data[c["path"][0]] = new
                continue
            section, i, name = c["path"]
            data[section][i][name] = new
        d, v = store.save(vol, page, data, version)
        out[page] = {"data": d, "version": v}
    return {"pages": out}
