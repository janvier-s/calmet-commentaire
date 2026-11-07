"""The /merge screen's decisions, per change of a good_units.json unit, in docs/good_merge/<vol>.json.

A change is keyed by its place (change_key: id, page, path, at), since ids hash words and the same words at
several places share one. Each record keeps the texts it was made against (`hash`): a re-run that changes them
reopens the decision; one that only moves the change (`at` shifted) re-attaches it while its id is unique in
the unit. A change-less one-sided unit takes a unit decision (keep/drop) under `unit@<uid>`. `mark` (noise/real)
overrides the change's class: what needs a decision, and the gold items for good_variants.
Nothing here writes normalized.
"""
import datetime
import hashlib
import json
import os
import threading

CHOICES = {"good", "old", "both", "edit"}  # take Good / keep old / keep both / edit by hand
UNIT_CHOICES = {"keep", "drop"}
LABELS = {"noise", "real"}
ONE_SIDED = {"only_old", "only_good", "uncovered", "unaligned"}  # change-less, they need a unit decision
_lock = threading.Lock()


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


def _update(docs, vol, uid, c, fields):
    """Set (or, None, drop) fields of the change's record; a record left with neither choice nor mark goes."""
    with _lock:
        doc = load(docs, vol)
        doc.pop("_by_uid", None)
        key = change_key(c) if c is not None else unit_key(uid)
        rec = doc["decisions"].get(key) or {"uid": uid, "key": key}
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


def decide(docs, vol, uid, c, choice, text=None):
    """The decision on change c of unit uid (c None: the unit's own keep/drop); choice None clears it."""
    if c is None and choice not in UNIT_CHOICES | {None}:
        raise ValueError(f"a unit decision is keep or drop, not {choice!r}")
    if c is not None and choice not in CHOICES | {None}:
        raise ValueError(f"a change decision is one of {sorted(CHOICES)}, not {choice!r}")
    if choice == "edit" and not (text or "").strip():
        raise ValueError("edit needs the text")
    return _update(docs, vol, uid, c, {"choice": choice, "text": text if choice == "edit" else None})[1]


def mark(docs, vol, uid, c, label, data=None, units_doc=None):
    """Mark change c noise or real (None clears): overrides its class. With `data` and `units_doc` (the
    volume's good_units.json), the marks go out again as a reference set (export_gold)."""
    if label not in LABELS | {None}:
        raise ValueError(f"a mark is noise or real, not {label!r}")
    rec = _update(docs, vol, uid, c, {"mark": label})[1]
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
        for c in changes:
            rec, state = lookup(doc, u.get("uid"), c, changes)
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


def lookup(doc, uid, c, unit_changes):
    """(record or None, state): current, reattached (key gone, id unique in the unit, same texts),
    reopened (the texts it was made against changed), none."""
    rec = doc["decisions"].get(change_key(c))
    if rec is not None:
        return rec, "current" if rec.get("hash") == text_hash(c) else "reopened"
    if sum(1 for x in unit_changes if x.get("id") == c.get("id")) == 1:
        h = text_hash(c)
        live = {change_key(x) for x in unit_changes}
        if "_by_uid" not in doc:
            doc["_by_uid"] = {}
            for r in doc["decisions"].values():
                doc["_by_uid"].setdefault(r.get("uid"), []).append(r)
        for r in doc["_by_uid"].get(uid, []):
            if r.get("id") == c.get("id") and r.get("hash") == h and r["key"] not in live:
                return r, "reattached"
    return None, "none"


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
    for c in changes:
        rec, state = lookup(doc, uid, c, changes)
        if not needs(c, rec, state):
            continue
        if rec is not None and rec.get("choice") and state in ("current", "reattached"):
            decided += 1
        else:
            todo += 1
            reopened += state == "reopened" and bool(rec.get("choice"))
    return {"done": todo == 0, "decided": decided, "todo": todo, "reopened": reopened}
