"""The read-only /merge screen's server side: good_units.json turned into what the browser draws.

A unit view is two segment lists, old and Good, where every recorded change of the unit is placed (or listed
in `unplaced`), the differences good_variants dropped without a record are marked `unrecorded`, and Good's
runs that agree with old carry old's surface (punctuation, apostrophes, accents). Nothing here writes.
"""
import difflib

import good_variants
import scan_ocr


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
    seen, keyed = {}, []
    for c in u.get("changes") or []:  # ids hash words, not places: the same change twice shares one
        seen[c["id"]] = seen.get(c["id"], 0) + 1
        keyed.append({**c, "key": c["id"] if seen[c["id"]] == 1 else f"{c['id']}~{seen[c['id']]}"})
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


def unit_view(doc, uid, store=None):
    """The unit `uid` of a good_units document, ready to draw; None if there is no such unit."""
    u = next((x for x in doc.get("units") or [] if x.get("uid") == uid), None)
    if u is None:
        return None
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
        modern = c.get("good_modern") if c.get("good_modern") is not None else c.get("good_raw") or ""
        osegs.append({**seg, "t": oslice(os_, oe)})
        gsegs.append({**seg, "t": ((" " if gs > 0 else "") + modern) if modern else ""})
        psegs.append({**seg, "t": gslice(gs, ge)})
        oc, gc = oe, ge
    gap(oc, len(otoks), gc, len(gtoks))
    # text outside any token (a unit of punctuation only) still belongs to the columns
    if not otoks and old:
        osegs.append({"t": old, "kind": "same"})
    if not gtoks and good:
        psegs.append({"t": good, "kind": "same"})
        gsegs.append({"t": good, "kind": "same"})
    if not old:
        osegs = []
    if not good:
        gsegs, psegs = [], []

    unit = {k: u.get(k) for k in ("uid", "type", "chapter", "verse", "lemma", "status", "parts", "good_where",
                                    "after")}
    return {"unit": unit, "old": osegs, "good": gsegs, "good_printed": psegs,
            "changes": [{**c, "placed": c["key"] in placed} for c in changes],
            "unplaced": [c["key"] for c in changes if c["key"] not in placed],
            "counts": counts, "empty": _empty_note(u), "stale": False, "seams": []}
