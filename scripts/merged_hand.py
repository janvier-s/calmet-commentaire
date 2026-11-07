"""Hand edits of the merged text: docs/good_merge/<vol>.hand.json.

merged/ is derived (normalized + /merge decisions + free edits, merge_build.build_pages) and rebuilt whenever
those change, so text typed in the Merged view is kept apart, one record per field:

    {"page", "path", "text": the field as typed (None: no hand edit, the built text shows),
     "base": field_hash of the built text it was typed on, "built": that built text,
     "conflict": None | {"why": "changed" | "gone", "built": the built text now, "t"},
     "versions": [{"text", "base", "built", "t"}, ...]: every earlier state, oldest first}

Every rebuild lays the hand text over the built field (overlay). When the built field is no longer the one the
edit was typed on (normalized, Good or a decision changed underneath) the hand text still wins and the field is
flagged (conflict) until the user keeps theirs or takes the rebuilt text (resolve). Nothing is ever thrown away:
each change pushes the previous state on `versions`, and restore() brings any of them back (pushing the current
one in turn).
"""
import datetime
import json
import os
import threading
from pathlib import Path

import merge_build
import merge_view

_lock = threading.RLock()


def path(docs, vol):
    return Path(docs) / "good_merge" / f"{vol}.hand.json"


def key(page, field_path):
    return f"{int(page)}:{field_path}"


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def load(docs, vol):
    f = path(docs, vol)
    if not f.exists():
        return {"vol": vol, "fields": {}}
    return json.loads(f.read_text(encoding="utf-8"))


def _save(docs, vol, doc):
    f = path(docs, vol)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_name(f.name + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, f)


def page_records(doc, page):
    return [r for r in doc["fields"].values() if r["page"] == int(page)]


def _state(rec):
    return {k: rec.get(k) for k in ("text", "base", "built")} | {"t": rec.get("t")}


def _record(doc, page, field_path):
    k = key(page, field_path)
    if k not in doc["fields"]:
        doc["fields"][k] = {"page": int(page), "path": field_path, "text": None, "base": None, "built": None,
                            "conflict": None, "t": None, "versions": []}
    return doc["fields"][k]


def _set(rec, text, built):
    """rec takes `text` typed on `built` (the field as built now); the previous state goes on versions."""
    rec["versions"].append(_state(rec))
    if text == built:
        rec.update(text=None, base=None, built=None)
    else:
        rec.update(text=text, base=merge_build.field_hash(built), built=built)
    rec.update(conflict=None, t=_now())


def edit(docs, vol, page, field_path, built, text):
    """The field typed as `text` over `built` (what the build gives it now). Typing it back to `built` takes the
    hand edit away (kept in versions). A flagged field stays flagged (on the built text it was typed on) until
    resolve(): typing in it is not a look at what changed underneath. -> the record."""
    with _lock:
        doc = load(docs, vol)
        rec = _record(doc, page, field_path)
        if rec.get("conflict") and rec.get("text") is not None and text != built:
            rec["versions"].append(_state(rec))
            rec.update(text=text, t=_now())
        else:
            _set(rec, text, built)
        _save(docs, vol, doc)
        return rec


def resolve(docs, vol, page, field_path, choice, built):
    """A flagged field: "mine" keeps the hand text (now based on `built`), "theirs" takes `built`."""
    if choice not in ("mine", "theirs"):
        raise ValueError(f"choice must be mine or theirs, not {choice!r}")
    with _lock:
        doc = load(docs, vol)
        rec = doc["fields"].get(key(page, field_path))
        if rec is None or rec.get("text") is None:
            raise KeyError(key(page, field_path))
        _set(rec, rec["text"] if choice == "mine" else built, built)
        _save(docs, vol, doc)
        return rec


def restore(docs, vol, page, field_path, index=-1):
    """Version `index` (default the last: undo) becomes the field's state; the current one goes on versions,
    so a restore is undone the same way. The next build flags it if the built text moved since."""
    with _lock:
        doc = load(docs, vol)
        rec = doc["fields"].get(key(page, field_path))
        if rec is None or not rec["versions"]:
            raise KeyError(key(page, field_path))
        old = rec["versions"][index]
        rec["versions"].append(_state(rec))
        rec.update(text=old["text"], base=old["base"], built=old["built"], conflict=None, t=_now())
        _save(docs, vol, doc)
        return rec


def overlay(doc, page, data):
    """Lay the page's hand edits over its built page `data` (changed in place); flag (rec["conflict"]) the ones
    whose built field moved or went. -> ([conflict report], whether any record changed)."""
    out, changed = [], False
    for rec in page_records(doc, page):
        if rec.get("text") is None:
            continue
        built = merge_view.field(data, rec["path"])
        if built is None:
            why = "gone"
        elif merge_build.field_hash(built) != rec["base"]:
            why = "changed"
        else:
            why = None
        if built is not None:
            merge_build._set_field(data, rec["path"], rec["text"])
        old = rec.get("conflict")
        if why is None:
            if old is not None:
                rec["conflict"], changed = None, True
            continue
        if not old or old.get("why") != why or old.get("built") != built:
            rec["conflict"], changed = {"why": why, "built": built, "t": _now()}, True
        out.append({"page": rec["page"], "path": rec["path"], "why": why, "built": built, "was": rec["built"],
                    "text": rec["text"]})
    return out, changed


def conflicts(doc):
    """Every flagged field of the volume."""
    return [{"page": r["page"], "path": r["path"], "why": r["conflict"]["why"], "built": r["conflict"]["built"],
             "was": r["built"], "text": r["text"]}
            for r in sorted(doc["fields"].values(), key=lambda r: (r["page"], r["path"]))
            if r.get("conflict") and r.get("text") is not None]


def apply_pages(docs, vol, built):
    """overlay() over {page: built page} (changed in place), the flags saved. -> [conflict report]."""
    with _lock:
        doc = load(docs, vol)
        out, changed = [], False
        for p, data in built.items():
            c, ch = overlay(doc, p, data)
            out += c
            changed |= ch
        if changed:
            _save(docs, vol, doc)
        return out
