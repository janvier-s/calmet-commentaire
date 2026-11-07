"""The read-only /merge screen's server side: good_units.json turned into what the browser draws.

A unit view is two segment lists, old and Good, where every recorded change of the unit is placed (or listed
in `unplaced`), the differences good_variants dropped without a record are marked `unrecorded`, and Good's
runs that agree with old carry old's surface (punctuation, apostrophes, accents). Nothing here writes.
"""
import difflib
import json
from pathlib import Path

from paths import DOCS
import good_italics
import good_units
import merge_build
import merge_decisions
import good_variants
import scan_ocr

STATUS_ORDER = ("substantive", "only_old", "only_good", "uncovered", "unaligned", "cosmetic", "identical")
NOTES = Path(__file__).resolve().parent / "good_merge_notes.json"
_docs = {}  # good_units.json path -> ((mtime, size), parsed)


def load(data, vol, docs=None):
    """data/<vol>/good_units.json, parsed once and again whenever it, the good_normalized store or the
    undone records change (good_normalized.overlay puts the cleaned text on the changes); None if absent."""
    import good_normalized
    path = Path(data) / vol / "good_units.json"
    try:
        st = path.stat()
    except (FileNotFoundError, NotADirectoryError):
        return None
    store_p, undo_p = good_normalized.store_path(data, vol), good_normalized.undone_path(docs or DOCS, vol)
    sig = (st.st_mtime_ns, st.st_size) + tuple(
        (s.st_mtime_ns, s.st_size) if (s := (p.stat() if p.exists() else None)) else None for p in (store_p, undo_p))
    hit = _docs.get(path)
    if hit and hit[0] == sig:
        return hit[1]
    doc = json.loads(path.read_text(encoding="utf-8"))
    if store_p.exists():
        good_normalized.overlay(doc, good_normalized.load_json(store_p, {}), good_normalized.load_json(undo_p, {}).get("undone"))
    _docs[path] = (sig, doc)
    return doc


def merge_vols(data):
    return sorted(p.parent.name for p in Path(data).glob("*/good_units.json"))


def notes(vol):
    """The hand-kept data-issue notes for a volume, by status."""
    try:
        return json.loads(NOTES.read_text(encoding="utf-8")).get(vol, {})
    except FileNotFoundError:
        return {}


def field(page_data, path):
    """A text field by path ("commentary/1/french_commentary", "verses/0/french", "chapter_summary")."""
    x = page_data
    for part in path.split("/"):
        if part.isdigit():
            x = x[int(part)] if isinstance(x, list) and int(part) < len(x) else None
        else:
            x = x.get(part) if isinstance(x, dict) else None
        if x is None:
            return None
    return x if isinstance(x, str) else None


SHIFTS = (1, -1, 2, -2, 3, -3)  # an entry added or removed above a unit's on its page (a commentary inserted)


def resolve_parts(store, vol, parts, old, cache=None):
    """The unit's parts where normalized has them now: as recorded when their text still gives `old`, else
    with the list index of a page's parts shifted ("commentary/1/..." -> "commentary/2/...") when an entry
    was added or removed above them, if that gives `old` back exactly; None when neither does."""
    import itertools
    import re
    cache = {} if cache is None else cache
    texts = _part_texts(store, vol, parts, cache)
    if texts is not None and good_units._text(" ".join(texts)) == (old or ""):
        return parts
    if old is None:
        return None
    pages = sorted({p["page"] for p in parts if re.match(r"[a-z_]+/\d+/", p["path"])})
    if not pages or len(pages) > 3:
        return None

    def shifted(p, d):
        m = re.match(r"([a-z_]+)/(\d+)/(.*)", p["path"])
        if not m or not d:
            return p
        i = int(m.group(2)) + d
        return None if i < 0 else {**p, "path": f"{m.group(1)}/{i}/{m.group(3)}"}

    for ds in itertools.product((0,) + SHIFTS, repeat=len(pages)):
        if not any(ds):
            continue
        by = dict(zip(pages, ds))
        moved = [shifted(p, by.get(p["page"], 0)) for p in parts]
        if None in moved:
            continue
        t = _part_texts(store, vol, moved, cache)
        if t is not None and good_units._text(" ".join(t)) == old:
            return moved
    return None


def _part_texts(store, vol, parts, cache=None, old=None):
    """The parts' texts in normalized (None if one is missing); with the unit's `old`, read where
    resolve_parts finds them (an entry inserted above them on the page)."""
    cache = {} if cache is None else cache
    if old is not None:
        parts = resolve_parts(store, vol, parts, old, cache) or parts
    out = []
    for p in parts:
        if p["page"] not in cache:
            try:
                cache[p["page"]] = store.read(vol, p["page"])[0]
            except (FileNotFoundError, ValueError):
                cache[p["page"]] = None
        d = cache[p["page"]]
        t = field(d, p["path"]) if d is not None else None
        if t is None:
            return None
        out.append(t)
    return out


def live_old(store, vol, parts, cache=None):
    """The unit's old text as normalized has it now; None if a page or field is missing."""
    texts = _part_texts(store, vol, parts, cache)
    return None if texts is None else good_units._text(" ".join(texts))


def _stale(store, vol, u, cache=None):
    if store is None or not u.get("parts"):
        return False
    return resolve_parts(store, vol, u["parts"], u.get("old") or "", cache) is None


def rows(doc, store, decisions=None):
    """One light row per unit, in book (file) order: no texts, no boxes; with `decisions`, its `progress`."""
    vol, cache, out = doc.get("vol"), {}, []
    for i, u in enumerate(doc.get("units") or []):
        first = None
        if not u.get("lemma"):
            first = " ".join((u.get("old") or u.get("good") or "").split()[:8])
        out.append({"uid": u.get("uid"), "type": u.get("type"), "chapter": u.get("chapter"),
                    "verse": u.get("verse"), "lemma": u.get("lemma"), "first": first, "status": u.get("status"),
                    "n": sum(1 for c in u.get("changes") or [] if c.get("class") != "noise"),
                    "after": u.get("after"), "stale": _stale(store, vol, u, cache), "i": i,
                    **({"progress": merge_decisions.unit_progress(decisions, u)} if decisions is not None else {})})
    return out


def _seams(parts, texts, old):
    """[{page, at}]: where in `old` each part on a new page starts, found by its text, in order."""
    out, cur, prev = [], 0, None
    for p, t in zip(parts, texts):
        t = good_units._text(t)
        if t:
            k = old.find(t, cur)
            if k >= 0:
                if prev is not None and p["page"] != prev:
                    out.append({"page": p["page"], "at": k})
                cur = k + len(t)
        prev = p["page"]
    return out


def _insert_seams(segs, seams):
    """A seam segment before the text at each seam's offset; a plain segment is split there if need be
    (a change is never split: the seam goes before it)."""
    out, pos, todo = [], 0, list(seams)
    for s in segs:
        while todo and todo[0]["at"] < pos + len(s["t"]):
            seam = todo.pop(0)
            cut = seam["at"] - pos
            if cut > len(s["t"]) - len(s["t"].lstrip()) and s["kind"] != "change":
                out.append({**s, "t": s["t"][:cut]})
                s, pos = {**s, "t": s["t"][cut:]}, seam["at"]
            out.append({"kind": "seam", "t": "", "page": seam["page"], "k": s.get("k")})
        out.append(s)
        pos += len(s["t"])
    return out


def tokens(text):
    """(start, end, key) for each word of `text`, as scan_ocr tokenizes and keys them."""
    return [(m.start(), m.end(), scan_ocr.key(m.group())) for m in scan_ocr.OCR_TOKEN.finditer(text or "")]


def _old_tokens(text):
    """tokens(), with a word cut at a page's end ("ordinai- rement") taken as one word, as the records do."""
    out = []
    for t in tokens(text):
        if out and text[out[-1][1]:t[0]].startswith("- ") and text[out[-1][1]:t[0]].strip() == "-" \
                and text[t[0]].islower():
            s = out.pop()
            out.append((s[0], t[1], scan_ocr.key(text[s[0]:s[1]] + text[t[0]:t[1]])))
        else:
            out.append(t)
    return out


def _keys(text):
    return [k for _, _, k in tokens(text)]


def find_run(keys, needle, before, after):
    """Where `needle` (keys) starts in `keys`, the occurrence whose surroundings best match `before`/`after`.
    None if absent, or if a short (or empty) needle has no matching context at all."""
    n = len(needle)
    best, best_score = None, -1
    for i in range(len(keys) - n + 1):
        if keys[i:i + n] != needle:
            continue
        s = 0
        while s < len(before) and s < i and before[-1 - s] == keys[i - 1 - s]:
            s += 1
        p = 0
        while p < len(after) and i + n + p < len(keys) and after[p] == keys[i + n + p]:
            p += 1
        if s + p > best_score:
            best, best_score = i, s + p
    if best is None or (n < 3 and best_score == 0):
        return None
    return best


def _find(keys, needle, before, after):
    """find_run, then, failing it, find_run blind to one-letter words, with the span in `keys`' indexes:
    the records' texts keep a note call's letter ("Cicéron c parle", from ^{(c)}) that the unit's old drops.
    -> (start, end) or None."""
    i = find_run(keys, needle, before, after)
    if i is not None:
        return i, i + len(needle)
    def long(ks):
        return [k for k in ks if len(k) > 1]
    idx = [j for j, k in enumerate(keys) if len(k) > 1]
    n = long(needle)
    if not n and needle:
        return None
    i = find_run([keys[j] for j in idx], n, long(before), long(after))
    if i is None:
        return None
    if not n:  # an insert: just after the context word before it
        s = idx[i - 1] + 1 if i > 0 else 0
        return s, s
    return idx[i], idx[i + len(n) - 1] + 1


def _bounds(text, toks):
    """Cut points between tokens: punctuation glued to a word stays with it, the space before a word goes
    with that word. bounds[k] starts token k's segment; bounds[len] is the text's end."""
    out = [0]
    for k in range(1, len(toks)):
        gap = text[toks[k - 1][1]:toks[k][0]]
        sp = next((j for j, ch in enumerate(gap) if ch.isspace()), len(gap))
        out.append(toks[k - 1][1] + sp)
    out.append(len(text))
    return out


def _map_pos(blocks, i):
    """An old key index mapped onto Good through the matcher's equal blocks."""
    pos = 0
    for a, b, size in blocks:
        if a <= i < a + size:
            return b + (i - a)
        if a + size <= i:
            pos = b + size
    return pos


def _modern(raw):
    body = raw.strip()
    if not body:
        return raw
    lead = raw[:len(raw) - len(raw.lstrip())]
    return lead + (good_variants.modern(body) or body)


def _empty_note(u):
    old = good = None
    if not u.get("old"):
        what = ("Good block not aligned to a source page" if u.get("type") == "unaligned" else "Good-only text")
        old = f"{what}; follows {u.get('after')}"
    if not u.get("good"):
        good = "Source page not covered by Good" if u.get("status") == "uncovered" else "Good has no text paired here"
    return {"old": old, "good": good}


def _place(u, otoks, gtoks):
    """The changes (each with a `key` unique in the unit), in parts order then `at`, and the placed ones' spans
    {key: (old start, old end, Good start, Good end)} in token indexes."""
    okeys, gkeys = [t[2] for t in otoks], [t[2] for t in gtoks]
    blocks = difflib.SequenceMatcher(None, okeys, gkeys, autojunk=False).get_matching_blocks()
    order = {(p["page"], p["path"]): k for k, p in enumerate(u.get("parts") or [])}
    # ids hash words, not places: the same change twice shares one, so changes are keyed by their place
    keyed = [{**c, "key": merge_decisions.change_key(c)} for c in u.get("changes") or []]
    changes = sorted(keyed,
                     key=lambda c: (order.get((c.get("page"), c.get("path")), len(order)), c.get("at") or 0))
    taken, placed = [], {}
    for c in changes:
        o = _find(okeys, _keys(c.get("old")), _keys(c.get("before")), _keys(c.get("after")))
        need_g = _keys(c.get("good_raw"))
        if c.get("good_before") is None and c.get("good_after") is None and not need_g:
            g = None if o is None else (_map_pos(blocks, o[0]),) * 2
        else:
            g = _find(gkeys, need_g, _keys(c.get("good_before")), _keys(c.get("good_after")))
        if o is None or g is None:
            continue
        span = (*o, *g)
        chain = sorted(taken + [span])
        if any(b[0] < a[1] or b[2] < a[3] for a, b in zip(chain, chain[1:])):
            continue  # overlaps or crosses a change already placed
        taken.append(span)
        placed[c["key"]] = span
    return changes, placed


def segments(u):
    """The unit's two columns as segment lists (old, Good modern, Good as printed), the k-th of each standing
    against each other, with its changes in order and the placed ones' token spans."""
    old, good = u.get("old") or "", u.get("good") or ""
    otoks, gtoks = _old_tokens(old), tokens(good)
    ob, gb = _bounds(old, otoks), _bounds(good, gtoks)
    changes, placed = _place(u, otoks, gtoks)
    by_key = {c["key"]: c for c in changes}
    one_sided = not otoks or not gtoks

    osegs, gsegs, psegs = [], [], []
    counts = {"substantive": 0, "cosmetic": 0, "moved": 0, "noise": 0, "unrecorded": 0}

    def oslice(a, b):
        return old[ob[a]:ob[b]] if a < b else ""

    def gslice(a, b):
        return good[gb[a]:gb[b]] if a < b else ""

    def gap(oa, oe, ga, ge):
        if oa == oe and ga == ge:
            return
        ok, gk = [t[2] for t in otoks[oa:oe]], [t[2] for t in gtoks[ga:ge]]
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ok, gk, autojunk=False).get_opcodes():
            if op == "equal":
                t = oslice(oa + i1, oa + i2)
                osegs.append({"t": t, "kind": "same"})
                gsegs.append({"t": t, "kind": "same"})
                psegs.append({"t": gslice(ga + j1, ga + j2), "kind": "same"})
            else:
                kind = "same" if one_sided else "unrecorded"
                if not one_sided:
                    counts["unrecorded"] += 1
                raw = gslice(ga + j1, ga + j2)
                osegs.append({"t": oslice(oa + i1, oa + i2), "kind": kind})
                gsegs.append({"t": _modern(raw), "kind": kind})
                psegs.append({"t": raw, "kind": kind})

    oc = gc = 0
    for cid, (os_, oe, gs, ge) in sorted(placed.items(), key=lambda kv: kv[1]):
        gap(oc, os_, gc, gs)
        c = by_key[cid]
        cls = c.get("class")
        counts[cls] = counts.get(cls, 0) + 1
        seg = {"kind": "change", "id": cid, "cls": cls}
        modern = next((c[k] for k in ("good_normalized", "good_italic", "good_punct", "good_modern") if c.get(k) is not None), c.get("good_raw") or "")
        osegs.append({**seg, "t": oslice(os_, oe)})
        lead = " " if gs > 0 and modern else ""
        gseg = {**seg, "t": lead + modern if modern else ""}
        if c.get("good_punct") is not None and c.get("good_flags"):  # the marks to check, on the text shown
            gseg["flags"] = [dict(f, a=f["a"] + len(lead), b=f["b"] + len(lead)) for f in good_italics.shift(c.get("good_flags_normalized") or c["good_flags"], modern)]
        gsegs.append(gseg)
        psegs.append({**seg, "t": gslice(gs, ge)})
        oc, gc = oe, ge
    gap(oc, len(otoks), gc, len(gtoks))
    # text outside any token (a unit of punctuation only) still belongs to the columns
    if not otoks and old:
        osegs.append({"t": old, "kind": "same"})
    if not gtoks and good:
        psegs.append({"t": good, "kind": "same"})
        gsegs.append({"t": good, "kind": "same"})
    for segs in (osegs, gsegs, psegs):  # built side by side: the k-th of each column stand against each other
        for k, seg in enumerate(segs):
            seg["k"] = k
    if not old:
        osegs = []
    if not good:
        gsegs, psegs = [], []

    return {"old": osegs, "good": gsegs, "printed": psegs, "changes": changes, "placed": placed,
            "by_key": by_key, "counts": counts, "gtoks": gtoks}


def unit_view(doc, uid, store=None, decisions=None):
    """The unit `uid` of a good_units document, ready to draw; None if there is no such unit. With `decisions`
    (merge_decisions.load), each change carries its `decision` and the view the unit's `progress`."""
    u = next((x for x in doc.get("units") or [] if x.get("uid") == uid), None)
    if u is None:
        return None
    sg = segments(u)
    osegs, gsegs, psegs, changes, placed, by_key, counts = (
        sg[k] for k in ("old", "good", "printed", "changes", "placed", "by_key", "counts"))
    gtoks, old = sg["gtoks"], u.get("old") or ""
    stale, seams = False, []
    if store is not None and u.get("parts"):
        texts = _part_texts(store, doc.get("vol"), u["parts"], old=u.get("old"))
        stale = texts is None or good_units._text(" ".join(texts)) != old
        if texts is not None:
            seams = _seams(u["parts"], texts, old)
            osegs = _insert_seams(osegs, seams)

    merged, editable, edits, fields = [], False, [], {}
    if store is not None and u.get("parts"):
        texts = _part_texts(store, doc.get("vol"), u["parts"], old=u.get("old"))
        if texts is not None:
            fields = {f"{p['page']}:{p['path']}": merge_build.field_hash(t) for p, t in zip(u["parts"], texts)}
            dec = decisions if decisions is not None else {"decisions": {}}
            r = merge_build.unit_ops(u, texts, dec)
            edits = r["edits"]
            if r["pieces"] is not None:
                merged, editable = merge_build.merged_segments(u, texts, r, dec), True

    unit = {k: u.get(k) for k in ("uid", "type", "chapter", "verse", "lemma", "status", "parts", "good_where",
                                    "after")}
    out_changes = [{**c, "placed": c["key"] in placed, "good_at": placed[c["key"]][2] if c["key"] in placed else None}
                   for c in changes]
    extra = {}
    if decisions is not None:
        raw = u.get("changes") or []
        for c in out_changes:
            rec, state = merge_decisions.lookup(decisions, uid, c, raw)
            c["decision"] = {"choice": rec and rec.get("choice"), "text": rec and rec.get("text"),
                             "mark": rec and rec.get("mark"), "state": state}
            if state == "reopened":  # what it was decided on
                c["decision"]["was"] = {"old": rec.get("old"), "good_raw": rec.get("good_raw")}
        extra = {"progress": merge_decisions.unit_progress(decisions, u),
                 "unit_decision": (decisions["decisions"].get(merge_decisions.unit_key(uid)) or {}).get("choice")}
    return {"unit": unit, "old": osegs, "good": gsegs, "good_printed": psegs, **extra,
            "merged": merged, "editable": editable, "edits": edits, "fields": fields,
            "changes": out_changes,
            "good_tokens": len(gtoks),
            "unplaced": [c["key"] for c in changes if c["key"] not in placed],
            "counts": counts, "empty": _empty_note(u), "stale": stale, "seams": seams}


def scan_boxes(store, vol, page, path, at, n):
    """The source scan's boxes of the first n words of field `path` from offset `at` on (n 0, an insert: the
    word next to it and a `caret` [x, y, h] where Good's text would go), found through
    the page's cached OCR set against the page (never running Kraken): {"boxes", "size", "crop"}, or
    {"boxes": [], "reason"} when there is no scan, no cached OCR, or the words are not found."""
    scan = store.scan(vol, page)
    if scan is None:
        return {"boxes": [], "reason": "no scan"}
    try:
        o = scan_ocr.ocr(vol, page, run=False, scan=scan)
    except Exception:  # the cache unreadable, the slant measure failing: as good as no OCR
        o = None
    if o is None:
        return {"boxes": [], "reason": "no cached OCR"}
    data = store.read(vol, page)[0] if store.path(vol, page).exists() else {}
    res = scan_ocr.align(o, data, fix=True)
    crop = store.scan_crop(vol, page)[1]  # /scan/ shows this part of the scan, when there is a crop
    if n == 0:  # an insert: the point Good's text would go, after the word ending at `at` (else before the next)
        mine = sorted((w for w in res.get("words") or [] if w.get("path") == path and w.get("a") is not None
                       and w.get("boxes")), key=lambda w: w["a"])
        prev = [w for w in mine if w.get("b") is not None and w["b"] <= at]
        nxt = [w for w in mine if w["a"] >= at]
        if prev:
            x, y, bw, h = prev[-1]["boxes"][-1]
            cx = x + bw
            if nxt:  # midway to the next word when it is on the same line (a box can miss part of a word: &c.)
                nx, ny, _, nh = nxt[0]["boxes"][0]
                if abs(ny - y) < min(h, nh) / 2 and nx > cx:
                    cx = (cx + nx) / 2
            return {"boxes": [prev[-1]["boxes"][-1]], "caret": [cx, y, h], "size": res.get("size"), "crop": crop}
        if nxt:
            x, y, bw, h = nxt[0]["boxes"][0]
            return {"boxes": [nxt[0]["boxes"][0]], "caret": [x, y, h], "size": res.get("size"), "crop": crop}
        return {"boxes": [], "reason": "words not found"}
    words = sorted((w for w in res.get("words") or [] if w.get("path") == path and w.get("a") is not None
                    and w["a"] >= at and w.get("boxes")), key=lambda w: w["a"])[:max(n, 1)]
    if not words:
        return {"boxes": [], "reason": "words not found"}
    return {"boxes": [b for w in words for b in w["boxes"]], "size": res.get("size"), "crop": crop}
