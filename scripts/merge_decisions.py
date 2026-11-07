"""The /merge screen's decisions, per change of a good_units.json unit, in docs/good_merge/<vol>.json.

A change is keyed by its place (change_key: id, page, path, at), since ids hash words and the same words at
several places share one. Each record keeps the texts it was made against (`hash`): a re-run that changes them
reopens the decision; one that only moves the change (`at` shifted) re-attaches it while its id is unique in
the unit. A change-less one-sided unit takes a unit decision (keep/drop) under `unit@<uid>`. `mark` (noise/real)
overrides the change's class: what needs a decision, and the gold items for good_variants.
Nothing here writes normalized.
"""
import collections
import datetime
import hashlib
import json
import os
import threading

CHOICES = {"good", "old", "both", "edit"}  # take Good / keep old / keep both / edit by hand
UNIT_CHOICES = {"keep", "drop"}
LABELS = {"noise", "real"}
ONE_SIDED = {"only_old", "only_good", "uncovered", "unaligned"}  # change-less, they need a unit decision
_lock = threading.RLock()  # mark() holds it across its write and the gold export


def path(docs, vol):
    return docs / "good_merge" / f"{vol}.json"


def change_key(c):
    return f"{c['id']}@{c.get('page')}:{c.get('path')}:{c.get('at')}"


def unit_key(uid):
    return f"unit@{uid}"


def text_hash(c):
    return hashlib.md5(json.dumps([c.get("old") or "", c.get("good_raw") or ""]).encode()).hexdigest()[:10]


def load(docs, vol):
    """{"vol", "decisions": {key: rec}}; empty when nothing was decided yet."""
    f = path(docs, vol)
    try:
        doc = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        doc = {"vol": vol, "decisions": {}}
    doc.setdefault("decisions", {})
    return doc


def _save(docs, vol, doc):
    f = path(docs, vol)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".json.tmp")
    out = {k: v for k, v in doc.items() if not k.startswith("_")}  # _by_uid: lookup's index, not saved
    tmp.write_text(json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, f)


def _update(docs, vol, uid, c, fields, unit_changes=None):
    """Set (or, None, drop) fields of the change's record; a record left with neither choice nor mark goes.
    With `unit_changes`, a re-attached record moves to the change's key; a reopened one (made against other
    texts) is dropped: what it said no longer holds, and the new fields start a fresh record."""
    with _lock:
        doc = load(docs, vol)
        key = change_key(c) if c is not None else unit_key(uid)
        rec = doc["decisions"].get(key)
        if c is not None:
            found, state = lookup(doc, uid, c, unit_changes if unit_changes is not None else [c])
            if found is not None and state in ("reattached", "reopened"):
                doc["decisions"].pop(found["key"], None)
                rec = dict(found, key=key) if state == "reattached" else None
        doc.pop("_by_uid", None)
        rec = rec or {"uid": uid, "key": key}
        if c is not None:
            rec.update(id=c["id"], page=c.get("page"), path=c.get("path"), at=c.get("at"), hash=text_hash(c),
                       old=c.get("old") or "", good_raw=c.get("good_raw") or "")
        for k, v in fields.items():
            if v is None:
                rec.pop(k, None)
            else:
                rec[k] = v
        rec["t"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        if rec.get("choice") is None and rec.get("mark") is None:
            doc["decisions"].pop(key, None)
        else:
            doc["decisions"][key] = rec
        _save(docs, vol, doc)
        return doc, rec


def decide(docs, vol, uid, c, choice, text=None, unit_changes=None):
    """The decision on change c of unit uid (c None: the unit's own keep/drop); choice None clears it."""
    if c is None and choice not in UNIT_CHOICES | {None}:
        raise ValueError(f"a unit decision is keep or drop, not {choice!r}")
    if c is not None and choice not in CHOICES | {None}:
        raise ValueError(f"a change decision is one of {sorted(CHOICES)}, not {choice!r}")
    if choice == "edit" and text is None:
        raise ValueError("edit needs the text")
    return _update(docs, vol, uid, c, {"choice": choice, "text": text if choice == "edit" else None}, unit_changes)[1]


def mark(docs, vol, uid, c, label, data=None, units_doc=None, unit_changes=None):
    """Mark change c noise or real (None clears): overrides its class. With `data` and `units_doc` (the
    volume's good_units.json), the marks go out again as a reference set (export_gold)."""
    if label not in LABELS | {None}:
        raise ValueError(f"a mark is noise or real, not {label!r}")
    with _lock:
        rec = _update(docs, vol, uid, c, {"mark": label}, unit_changes)[1]
        if data is not None and units_doc is not None:
            export_gold(docs, data, vol, units_doc)
    return rec


def export_gold(docs, data, vol, units_doc):
    """The live noise/real marks as a good_variants reference set, data/good_variants_gold/<vol>_merge.json
    (the format good_variants_eval.py scores against)."""
    doc = load(docs, vol)
    items, chapters = [], set()
    for u in units_doc.get("units") or []:
        changes = u.get("changes") or []
        found = _matches(doc, u.get("uid"), changes)
        for c in changes:
            rec, state = found.get(change_key(c), (None, "none"))
            if not rec or not rec.get("mark") or state not in ("current", "reattached"):
                continue
            try:
                chapters.add(int(u.get("chapter")))
            except (TypeError, ValueError):
                pass
            items.append({"label": rec["mark"], "page": c.get("page"), "path": c.get("path"), "at": c.get("at"),
                          "kind": c.get("kind"), "old": c.get("old") or "", "good": c.get("good_raw") or "",
                          "good_page": [[g.get("pdf"), g.get("pdf_page"), g.get("printed")] for g in c.get("good") or []],
                          "note": f"merge {u.get('uid')} {c.get('class')}"})
    f = data / "good_variants_gold" / f"{vol}_merge.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"vol": vol, "chapters": sorted(chapters), "items": items, "missed": []},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, f)
    return f


def edit_key(uid, page, path, at):
    return f"edit@{uid}:{page}:{path}:{at}"


def free_edits(doc, uid):
    """The unit's free edits, in field order."""
    return sorted((r for r in doc["decisions"].values() if r.get("kind") == "edit" and r.get("uid") == uid),
                  key=lambda r: (r.get("page"), r.get("path"), r.get("at")))


def free_edit(docs, vol, uid, page, path, at, old, text):
    """A free edit: `old` (normalized's text at `at` of the field) becomes `text`. It replaces the unit's free
    edits it overlaps on that field; `text` == `old` takes it back (None)."""
    with _lock:
        doc = load(docs, vol)
        for r in free_edits(doc, uid):
            if (r["page"], r["path"]) == (page, path) and r["at"] < at + max(len(old), 1) \
                    and at < r["at"] + max(len(r["old"]), 1):
                doc["decisions"].pop(r["key"], None)
        rec = None
        if text != old:
            key = edit_key(uid, page, path, at)
            rec = {"uid": uid, "key": key, "kind": "edit", "page": page, "path": path, "at": at, "old": old,
                   "text": text, "hash": hashlib.md5(old.encode()).hexdigest()[:10],
                   "t": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
            doc["decisions"][key] = rec
        doc.pop("_by_uid", None)
        _save(docs, vol, doc)
        return rec


def drop_edit(docs, vol, uid, key):
    """Take back the unit's free edit `key`; False when it has none such."""
    with _lock:
        doc = load(docs, vol)
        rec = doc["decisions"].get(key)
        if not rec or rec.get("kind") != "edit" or rec.get("uid") != uid:
            return False
        del doc["decisions"][key]
        _save(docs, vol, doc)
        return True


def locate_edit(rec, field_text):
    """((start, end) or None, state) of a free edit in the field's live text: current where it was made;
    reattached when its old text is now at exactly one other place; else reopened."""
    at, old = rec["at"], rec["old"]
    if field_text[at:at + len(old)] == old:
        return (at, at + len(old)), "current"
    k = field_text.find(old) if old else -1
    if k >= 0 and field_text.find(old, k + 1) < 0:
        return (k, k + len(old)), "reattached"
    return None, "reopened"


def lookup(doc, uid, c, unit_changes):
    """(record or None, state) for change c among its unit's changes: current; reattached (key gone, id unique in
    the unit, same texts); reopened (the texts it was made against changed: same key, or an orphaned record at
    the same page, path and at, since a change of texts gives good_variants a new id); none."""
    return _matches(doc, uid, unit_changes if any(change_key(x) == change_key(c) for x in unit_changes)
                    else list(unit_changes) + [c]).get(change_key(c), (None, "none"))


def _matches(doc, uid, unit_changes):
    """{change key: (record, state)} for a unit's changes; an orphaned record goes to one change at most."""
    if "_by_uid" not in doc:
        doc["_by_uid"] = {}
        for r in doc["decisions"].values():
            doc["_by_uid"].setdefault(r.get("uid"), []).append(r)
    live = {change_key(x) for x in unit_changes}
    orphans = [r for r in doc["_by_uid"].get(uid, []) if r["key"] not in live
               and not r["key"].startswith(("unit@", "edit@"))]
    ids = collections.Counter(x.get("id") for x in unit_changes)
    out, used = {}, set()
    for c in unit_changes:
        rec = doc["decisions"].get(change_key(c))
        if rec is not None:
            out[change_key(c)] = (rec, "current" if rec.get("hash") == text_hash(c) else "reopened")
            continue
        if ids[c.get("id")] == 1:
            h = text_hash(c)
            r = next((r for r in orphans if r["key"] not in used and r.get("id") == c.get("id") and r.get("hash") == h), None)
            if r is not None:
                used.add(r["key"])
                out[change_key(c)] = (r, "reattached")
    for c in unit_changes:  # then by page, offset and texts, the path ignored (a note inserted before moves its index)
        if change_key(c) in out:
            continue
        h = text_hash(c)
        r = next((r for r in orphans if r["key"] not in used and r.get("hash") == h
                  and (r.get("page"), r.get("at")) == (c.get("page"), c.get("at"))), None)
        if r is not None:
            used.add(r["key"])
            out[change_key(c)] = (r, "reattached")
    for c in unit_changes:  # then the orphans left, by place
        if change_key(c) in out:
            continue
        r = next((r for r in orphans if r["key"] not in used and (r.get("page"), r.get("path"), r.get("at"))
                  == (c.get("page"), c.get("path"), c.get("at"))), None)
        if r is not None:
            used.add(r["key"])
            out[change_key(c)] = (r, "reopened")
    return out


def needs(c, rec, state):
    """Whether change c needs a decision: not noise, unless marked real; marked noise, never."""
    m = rec.get("mark") if rec is not None and state in ("current", "reattached") else None
    if m:
        return m == "real"
    return c.get("class") != "noise"


def unit_progress(doc, u):
    """{done, decided, todo, reopened} for unit u: done when every change that needs one has a live decision."""
    uid, changes = u.get("uid"), u.get("changes") or []
    if not changes:
        if u.get("status") not in ONE_SIDED:
            return {"done": True, "decided": 0, "todo": 0, "reopened": 0}
        got = (doc["decisions"].get(unit_key(uid)) or {}).get("choice")
        return {"done": bool(got), "decided": int(bool(got)), "todo": int(not got), "reopened": 0}
    decided = todo = reopened = 0
    found = _matches(doc, uid, changes)
    for c in changes:
        rec, state = found.get(change_key(c), (None, "none"))
        if not needs(c, rec, state):
            continue
        if rec is not None and rec.get("choice") and state in ("current", "reattached"):
            decided += 1
        else:
            todo += 1
            reopened += state == "reopened" and bool(rec.get("choice"))
    return {"done": todo == 0, "decided": decided, "todo": todo, "reopened": reopened}
