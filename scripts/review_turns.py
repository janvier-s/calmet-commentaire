"""The page turn an issue belongs to: the foot of page A, the head of page B, the text as calmet.py
joins it, and the fix seam_join.py would make there (computed from the pages as they are now)."""
import hashlib
import json
import re

from calmet import infer_join, join_seam

# where the audit puts a page-turn issue: on the page before the turn, or on the page after it
FOOT_KINDS = frozenset({"hyphen_cut", "italic_seam", "period_seam"})
HEAD_KINDS = frozenset({"possible_gap", "seam_artifact", "seam_missing", "seam_repeat", "seam_unclear"})
TURN_KINDS = FOOT_KINDS | HEAD_KINDS


def turn_of(store, item):
    """(vol, a, b) for a page-turn issue, else None."""
    vol, page, kind = item["book_dir"], item["page"], item["kind"]
    if kind not in TURN_KINDS or vol not in store.volumes():
        return None
    pages = store.pages(vol)
    if kind in FOOT_KINDS:
        later = [p for p in pages if p > page]
        if page not in pages or not later:
            return None
        where = item.get("where")
        if kind == "hyphen_cut" and where:  # a cut followed by another note on the same page
            n = len(store.read(vol, page)[0].get("commentary") or [])
            if where.get("index") != n - 1:
                return None
        return vol, page, later[0]
    m = re.search(r"/(\d{4})$", item["id"]) if kind.startswith("seam_") and kind != "seam_artifact" else None
    if m and int(m.group(1)) in pages:  # seam_check names the page before
        return vol, int(m.group(1)), page
    earlier = [p for p in pages if p < page]
    return (vol, earlier[-1], page) if earlier else None


def _first(block, names):
    return next((block.get(k) for k in names if (block.get(k) or "").strip()), None)


def join_preview(la, fb):
    """How the last block of A and the first of B read joined, as on the site."""
    tail = _first(la, ("french_commentary", "french_translation", "latin_quote"))
    head = _first(fb, ("latin_quote", "french_translation", "french_commentary"))
    if not tail or not head:
        return None
    mode, stub = infer_join(tail, head)
    return {"tail": tail, "head": head, "mode": mode, "joined": join_seam(tail[-200:], head[:200], mode, stub)}


def _side(store, vol, page, last):
    if page not in store.pages(vol):
        return None
    data, version = store.read(vol, page)
    verses, notes = data.get("verses") or [], data.get("commentary") or []
    pick = (lambda xs: len(xs) - 1 if xs else None) if last else (lambda xs: 0 if xs else None)
    return {"page": page, "data": data, "version": version, "scan": store.scan(vol, page) is not None,
            "verse": pick(verses), "note": pick(notes)}


def _verse_french(store, vol, block):
    ch, v = block.get("chapter"), re.match(r"\d+", str(block.get("verse_ref") or ""))
    if not isinstance(ch, int) or not v:
        return ""
    p = store.locate(vol, ch, int(v.group()))
    if p is None:
        return ""
    for x in store.read(vol, p)[0].get("verses") or []:
        if (x.get("chapter"), x.get("verse_number")) == (ch, int(v.group())):
            return x.get("french") or ""
    return ""


def seam_proposal(store, vol, a, b, sa=None, sb=None):
    """seam_join.py's fix for this turn, as a proposal; None when it has none."""
    import seam_join
    sa = sa or _side(store, vol, a, True)
    sb = sb or _side(store, vol, b, False)
    if not sa or not sb or sa["note"] is None or sb["note"] is None:
        return None
    la, fb = sa["data"]["commentary"][sa["note"]], sb["data"]["commentary"][0]
    pa, pb = store.path(vol, a), store.path(vol, b)
    fix = seam_join.plan(vol, pa, pb, la, fb, _verse_french(store, vol, la)) or seam_join.plan_repeat(vol, pa, pb, la, fb)
    if not fix or not fix.get("set"):
        return None
    changes = []
    for k, new in fix["set"].items():
        side, block, page, i = (sa, la, a, sa["note"]) if k[0] == "a" else (sb, fb, b, 0)
        old = block.get(k[2:])
        if new != old:
            changes.append({"vol": vol, "page": page, "path": ["commentary", i, k[2:]], "old": old, "new": new})
    if not changes:
        return None
    digest = hashlib.md5(json.dumps(fix["set"], ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:8]
    return {"id": f"seam/{vol}/{a:04d}>{b:04d}/{digest}", "item": None, "title": fix["how"], "why": [],
            "flags": [], "sure": bool(fix["sure"]), "options": [{"label": fix["how"], "changes": changes}]}


def turn(store, vol, a, b):
    """Both sides of the turn a > b, the joined text and the proposal."""
    sa, sb = _side(store, vol, a, True), _side(store, vol, b, False)
    join = None
    if sa and sb and sa["note"] is not None and sb["note"] is not None:
        join = join_preview(sa["data"]["commentary"][sa["note"]], sb["data"]["commentary"][0])
    return {"vol": vol, "a": sa, "b": sb, "join": join, "proposal": seam_proposal(store, vol, a, b, sa, sb)}
