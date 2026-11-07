"""The merged text: normalized + the /merge decisions + free edits, as operations on normalized's fields.

The unit view draws its left column from these operations and the page build writes data/<vol>/merged/ from
them, so the screen and the output agree. A note's marker (^{(a)}) inside a span Good replaces or cuts is kept,
so no old note is lost; markers are renumbered per page when a page's set of them changed. Nothing here writes
normalized.
"""
import copy
import hashlib
import os
import re
from pathlib import Path

from good_units import CALL

TAIL_PUNCT = re.compile(r"[^\w\s}]+$")
NO_SPACE_BEFORE = set(",.;:!?)»]")
NO_SPACE_AFTER = set("(«['’")


def text_map(texts):
    """The unit text as good_units._text(" ".join(texts)) builds it, and each of its characters' (part, offset
    in that part's field); the space joining two parts maps to (next part, -1)."""
    chars = []
    for k, t in enumerate(texts):
        if k:
            chars.append((" ", (k, -1)))
        cut = [m.span() for m in CALL.finditer(t)]
        j = 0
        for i, ch in enumerate(t):
            while j < len(cut) and cut[j][1] <= i:
                j += 1
            if j < len(cut) and cut[j][0] <= i < cut[j][1]:
                continue
            chars.append((ch, (k, i)))
    out, idx = [], []
    for ch, at in chars:
        if ch.isspace():
            if out and out[-1] != " ":
                out.append(" ")
                idx.append(at)
        else:
            out.append(ch)
            idx.append(at)
    if out and out[-1] == " ":
        out.pop()
        idx.pop()
    return "".join(out), idx


def good_text(c):
    """Good's wording for take Good: cleaned (good_normalized), else italicized, punctuated, modern, else as read."""
    return next((c[k] for k in ("good_normalized", "good_italic", "good_punct", "good_modern") if c.get(k) is not None), c.get("good_raw") or "")


def change_text(c, old_slice, choice, text):
    """What a decided change puts in place of its old slice. Take Good keeps the slice's note markers (at the
    end, or alone at a cut) and the punctuation glued to its last word when Good's wording ends without any."""
    if choice == "old":
        return old_slice
    if choice == "edit":
        return text or ""
    good = good_text(c).strip()
    if choice == "both":
        return " ".join(x for x in (old_slice.strip(), good) if x)
    bare = CALL.sub("", old_slice).rstrip()
    tail = TAIL_PUNCT.search(bare)
    marks = [m.group() for m in CALL.finditer(old_slice) if m.group() not in good]
    out = " ".join([good] + marks if good else marks)
    if good and tail and good[-1].isalnum():  # the closing mark after the kept markers, as normalized has it
        out += tail.group()
    return out


def spans(text, ops):
    """Each op's final span and text in `text`: where new text meets a word it gets one space (inside the op's
    text), never a doubled one; a cut takes the space before it along (or, at the start, the space after).
    What an op meets is what the ops before it left. -> [(a, b, new, op)] in text order."""
    out, pos, tail = [], 0, None  # tail: the result's last char before the op (None: nothing yet)
    ordered = sorted(ops, key=lambda o: (o["a"], o["b"]))
    for i, op in enumerate(ordered):
        a, b, new = op["a"], op["b"], (op["new"] or "").strip()
        stop = ordered[i + 1]["a"] if i + 1 < len(ordered) else len(text)  # never into the next op
        before = text[a - 1] if a > pos else tail
        if not new:
            if before is None or before.isspace() and a <= pos:
                while b < stop and text[b].isspace():
                    b += 1
            elif before.isspace() and (b == len(text) or text[b].isspace() or text[b] in NO_SPACE_BEFORE):
                a -= 1
                before = text[a - 1] if a > pos else tail
        else:
            if before is not None and not before.isspace() and before not in NO_SPACE_AFTER:
                new = " " + new
            if b < len(text) and not text[b].isspace() and text[b] not in NO_SPACE_BEFORE:
                new += " "
        out.append((a, b, new, op))
        tail = new[-1] if new else before
        pos = b
    return out


def apply_ops(text, ops):
    """ops [{a, b, new}] (non-overlapping) applied, spaced as spans() says."""
    for a, b, new, _ in reversed(spans(text, ops)):
        text = text[:a] + new + text[b:]
    return text


def _strings(x, skip=("footnotes",)):
    """The page's text strings outside its footnotes, in reading (key) order, with a setter for each."""
    if isinstance(x, dict):
        for k, v in x.items():
            if k in skip:
                continue
            if isinstance(v, str):
                yield v, (lambda s, d=x, k=k: d.__setitem__(k, s))
            else:
                yield from _strings(v, ())
    elif isinstance(x, list):
        for i, v in enumerate(x):
            if isinstance(v, str):
                yield v, (lambda s, d=x, i=i: d.__setitem__(i, s))
            else:
                yield from _strings(v, ())


def _markers(page):
    seen = []
    for s, _ in _strings(page):
        for m in CALL.findall(s):
            if m not in seen:
                seen.append(m)
    return seen


def renumber(page, before):
    """The merged page with its notes following their markers: when the markers in its text differ from
    normalized's (`before`), the footnotes whose marker vanished go and the rest are relabelled in reading
    order with the page's own labels. A note with no marker on the page (one continued from the page before)
    is left as it is."""
    was, now = _markers(before), _markers(page)
    if set(was) == set(now):
        return page
    out = copy.deepcopy(page)
    gone = set(was) - set(now)
    labels = iter(was)
    relabel = {m: next(labels) for m in now if m in set(was)}
    for s, put in list(_strings(out)):
        put(CALL.sub(lambda m: "^{%s}" % relabel.get(m.group(1), m.group(1)), s))
    notes = []
    for f in out.get("footnotes") or []:
        m = f.get("marker")
        if m in gone:
            continue
        notes.append(dict(f, marker=relabel.get(m, m)))
    if "footnotes" in out:
        out["footnotes"] = notes
    return out


# --- a unit's operations ---

def _token_span(field, c):
    """An unplaced change's span in its field: its old words read from `at` on (with the punctuation glued to
    the last), or None when the field no longer has them there."""
    import merge_view
    need = merge_view._keys(c.get("old"))
    at = c.get("at") or 0
    if not need:
        return (at, at) if at <= len(field) else None
    toks = [t for t in merge_view.tokens(field) if t[0] >= at][:len(need)]
    if [t[2] for t in toks] != need or toks[0][0] != at and field[at:toks[0][0]].strip():
        return None
    end = toks[-1][1]
    while end < len(field) and not field[end].isspace() and not field[end].isalnum():
        end += 1
    return toks[0][0], end


def pieces(u, texts):
    """The unit's old segments (merge_view.segments) cut on normalized's fields: [{k, kind, id, part, a, b}],
    tiling each field; None when normalized no longer reads as the unit's old text (stale)."""
    import merge_view
    old = u.get("old") or ""
    joined, idx = text_map(texts)
    if joined != old or not texts:
        return None
    sg = merge_view.segments(u)
    out, pos = [], 0
    for s in sg["old"]:
        a, b = pos, pos + len(s["t"])
        pos = b
        base = {"k": s["k"], "kind": s["kind"], "id": s.get("id")}
        if a == b:  # an insert: before the char that follows (the space before the next word)
            part, off = idx[a] if a < len(idx) else (len(texts) - 1, len(texts[-1]))
            if off < 0:
                part, off = part - 1, len(texts[part - 1])
            out.append({**base, "part": part, "a": off, "empty": True})
            continue
        cur = None
        for i in range(a, b):
            part, off = idx[i]
            if cur is None or part != cur:
                out.append({**base, "part": part, "a": max(off, 0)})
                cur = part
    for k, p in enumerate(out):  # every piece ends where the next one of its field starts, or at the field's end
        nxt = next((q for q in out[k + 1:] if q["part"] == p["part"] and not q.get("empty")), None)
        p["b"] = p["a"] if p.pop("empty", False) else (nxt["a"] if nxt else len(texts[p["part"]]))
    first = {}
    for p in out:  # a field's first piece takes what comes before it (a leading marker, spaces)
        if p["b"] > p["a"]:
            first.setdefault(p["part"], p)
    for p in first.values():
        p["a"] = 0
    return out


def unit_ops(u, texts, decisions):
    """{"ops": {(page, path): [op]}, "skipped": [{key, why}], "pieces", "edits"}: what the unit's live
    decisions and free edits do to its fields. op = {a, b, new, key, kind, choice, lead}."""
    import merge_decisions as md
    parts = u.get("parts") or []
    ps = pieces(u, texts)
    found = md._matches(decisions, u.get("uid"), u.get("changes") or [])
    taken, skipped, edits = {}, [], []

    def free(part, a, b):
        return all(o["b"] <= a or b <= o["a"] for o in taken.get(part, []))

    def add(part, op):
        taken.setdefault(part, []).append(op)

    unit_choice = (decisions["decisions"].get(md.unit_key(u.get("uid"))) or {}).get("choice")
    if unit_choice == "drop" and parts:  # the unit left out of the merge: its fields cut whole
        ops = {(p["page"], p["path"]): [{"a": 0, "b": len(texts[k]), "new": "", "key": md.unit_key(u.get("uid")),
                                         "kind": "unit", "choice": "drop", "lead": 0, "state": "current"}]
               for k, p in enumerate(parts)}
        return {"ops": ops, "skipped": [], "pieces": ps, "edits": edits}
    if unit_choice == "keep" and not parts:
        skipped.append({"key": md.unit_key(u.get("uid")), "why": "no place in normalized"})
    for r in md.free_edits(decisions, u.get("uid")):  # free edits first: they win over changes
        part = next((k for k, p in enumerate(parts) if (p["page"], p["path"]) == (r["page"], r["path"])), None)
        span, state = md.locate_edit(r, texts[part]) if part is not None else (None, "reopened")
        if span is not None and ps is not None and not any(
                p["part"] == part and p["kind"] not in ("change",) and p["a"] <= span[0] and span[1] <= p["b"]
                for p in ps):
            span, state = None, "overlap"
        if span is None:
            edits.append({"key": r["key"], "state": state, "old": r["old"], "text": r["text"],
                          "page": r["page"], "path": r["path"], "at": r["at"]})
            skipped.append({"key": r["key"], "why": state})
            continue
        add(part, {"a": span[0], "b": span[1], "new": r["text"], "key": r["key"], "kind": "edit", "choice": "edit",
                   "lead": 0, "state": state})
    by_piece = {p["id"]: p for p in ps or [] if p["kind"] == "change"}
    later = []
    for c in u.get("changes") or []:
        key = md.change_key(c)
        rec, state = found.get(key, (None, "none"))
        if rec is None or state not in ("current", "reattached") or rec.get("choice") in (None, "old"):
            continue
        p = by_piece.get(key)
        if p is None:
            later.append((c, key, rec, state))
            continue
        field = texts[p["part"]]
        lead = len(field[p["a"]:p["b"]]) - len(field[p["a"]:p["b"]].lstrip())
        a, b = p["a"] + lead, p["b"]
        if not free(p["part"], a, b):
            skipped.append({"key": key, "why": "overlap"})
            continue
        add(p["part"], {"a": a, "b": b, "new": change_text(c, field[a:b], rec["choice"], rec.get("text")),
                        "key": key, "kind": "change", "choice": rec["choice"], "lead": lead, "state": state})
    for c, key, rec, state in later:  # unplaced (or the unit stale): by the change's own place in its field
        part = next((k for k, p in enumerate(parts) if (p["page"], p["path"]) == (c.get("page"), c.get("path"))), None)
        span = _token_span(texts[part], c) if part is not None else None
        if span is None:
            skipped.append({"key": key, "why": "not found"})
            continue
        if not free(part, *span) or any(o["a"] == o["b"] == span[0] == span[1] for o in taken.get(part, [])):
            skipped.append({"key": key, "why": "overlap"})
            continue
        field = texts[part]
        add(part, {"a": span[0], "b": span[1], "new": change_text(c, field[span[0]:span[1]], rec["choice"],
                   rec.get("text")), "key": key, "kind": "change", "choice": rec["choice"], "lead": 0, "state": state})
    ops = {(parts[k]["page"], parts[k]["path"]): sorted(v, key=lambda o: (o["a"], o["b"])) for k, v in taken.items()}
    return {"ops": ops, "skipped": skipped, "pieces": ps, "edits": edits}


def merged_segments(u, texts, r, decisions):
    """The merged column: the unit's pieces with the ops applied, each {k, kind, page, path, a, b, t} (t: its
    share of the merged field text) and, for a change, {id, cls, ckind, choice, state, ghost} (ghost: shown, not
    in the text: Good's words of an undecided insert, the old words a decision cut)."""
    import merge_decisions as md
    parts, ps = u.get("parts") or [], r["pieces"]
    by_key = {md.change_key(c): c for c in u.get("changes") or []}
    found = md._matches(decisions, u.get("uid"), u.get("changes") or [])
    out, last_page = [], None
    for part, field in enumerate(texts):
        page, path = parts[part]["page"], parts[part]["path"]
        sp = spans(field, r["ops"].get((page, path), []))
        mine = [p for p in ps if p["part"] == part]
        owner = {}
        for a, b, new, op in sp:
            p = next((p for p in mine if p["kind"] == "change" and p["id"] == op["key"]), None) \
                or next((p for p in mine if p["a"] <= op["a"] < p["b"] and p["kind"] != "change"), None) \
                or next(p for p in mine if p["a"] <= op["a"] <= p["b"])
            owner[id(op)] = id(p)

        def uncovered(x, y):
            return "".join(field[i] for i in range(x, y) if not any(a <= i < b for a, b, _, _ in sp))

        for n, p in enumerate(mine):
            if last_page is not None and page != last_page:
                out.append({"kind": "seam", "t": "", "page": page, "k": p["k"]})
            elif n == 0 and part:  # the space between two fields: shown, not part of either
                out.append({"kind": "join", "t": " ", "k": p["k"]})
            last_page = page
            base = {"k": p["k"], "page": page, "path": path, "a": p["a"], "b": p["b"]}
            own = [x for x in sp if owner[id(x[3])] == id(p)]
            if p["kind"] == "change":
                c = by_key[p["id"]]
                rec, state = found.get(p["id"], (None, "none"))
                live = state in ("current", "reattached")
                seg = {**base, "kind": "change", "id": p["id"], "cls": c.get("class"), "ckind": c.get("kind"),
                       "choice": rec.get("choice") if rec and live else None, "state": state, "ghost": None}
                t, pos = "", p["a"]
                for a, b, new, op in own:  # its own op, and any unplaced one that falls inside it
                    t += uncovered(pos, a) + new
                    pos = max(pos, b)
                    if op["key"] == p["id"] and not CALL.sub("", new).strip() \
                            and CALL.sub("", field[op["a"]:op["b"]]).strip():
                        seg["ghost"] = " " + " ".join(CALL.sub("", field[op["a"]:op["b"]]).split())
                seg["t"] = t + uncovered(pos, p["b"])
                if p["a"] == p["b"] and seg["choice"] is None:
                    seg["ghost"] = " " + good_text(c).strip()
                out.append(seg)
                continue
            pos, kind = p["a"], "same" if p["kind"] == "seam" else p["kind"]
            for a, b, new, op in own:  # free edits (and unplaced changes) inside a plain piece: each part
                if pos < a:            # keeps its own span of normalized, so an edit there touches only it
                    out.append({**base, "kind": kind, "a": pos, "b": a, "t": uncovered(pos, a)})
                out.append({**base, "kind": op["kind"], "key": op["key"], "a": op["a"], "b": op["b"], "t": new,
                            "choice": op["choice"]})
                pos = max(pos, b)
            if pos < p["b"] or not own:
                out.append({**base, "kind": kind, "a": pos, "b": p["b"], "t": uncovered(pos, p["b"])})
    return out


# --- the merged pages: data/<vol>/merged/page_NNNN.json ---

def field_hash(text):
    """What the screen sends back with an edit, so a field changed since it loaded is refused."""
    return hashlib.md5((text or "").encode()).hexdigest()[:10]


def new_spans(old, new):
    """[(a, b)] in `new`: the words that are not in `old` (inserted or swapped in), whitespace left out."""
    import difflib
    import re
    ta = re.findall(r"\s+|\S+", old or "")
    tb = re.findall(r"\s+|\S+", new or "")
    out, pos = [], [0]
    for t in tb:
        pos.append(pos[-1] + len(t))
    for tag, _, _, j1, j2 in difflib.SequenceMatcher(None, ta, tb, autojunk=False).get_opcodes():
        if tag in ("insert", "replace"):
            ks = [k for k in range(j1, j2) if not tb[k].isspace()]
            if ks:
                out.append((pos[ks[0]], pos[ks[-1] + 1]))
    return out


def page_marks(old_page, new_page, path=""):
    """{field path: [(a, b)]} for every string of new_page that differs from old_page's (same shape), as new_spans."""
    out = {}
    if isinstance(new_page, dict) and isinstance(old_page, dict):
        for k, v in new_page.items():
            out.update(page_marks(old_page.get(k), v, f"{path}/{k}" if path else k))
    elif isinstance(new_page, list) and isinstance(old_page, list):
        for i, v in enumerate(new_page):
            if i < len(old_page):
                out.update(page_marks(old_page[i], v, f"{path}/{i}"))
    elif isinstance(new_page, str) and isinstance(old_page, str) and new_page != old_page:
        out[path] = new_spans(old_page, new_page)
    return out


def merged_dir(data, vol):
    return Path(data) / vol / "merged"


def unit_pages(u):
    return {p["page"] for p in u.get("parts") or []}


def _set_field(page, path, value):
    *head, last = path.split("/")
    x = page
    for part in head:
        x = x[int(part)] if part.isdigit() else x[part]
    x[int(last) if last.isdigit() else last] = value


def merged_pages(store, vol, units_doc, decisions, pages=None):
    """{page: (normalized page, merged page)} for those pages (None: every normalized page), and the report
    {"skipped": [{uid, key, why}], "reopened": n} of what could not be applied."""
    import merge_decisions as md
    import merge_view
    every = store.pages(vol)
    pages = sorted(every if pages is None else set(pages) & set(every))
    cache = {}

    def read(p):
        if p not in cache:
            try:
                cache[p] = store.read(vol, p)[0]
            except (FileNotFoundError, ValueError):
                cache[p] = None
        return cache[p]

    want = set(pages)
    ops, report = {}, {"skipped": [], "reopened": 0}
    for u in units_doc.get("units") or []:
        if not u.get("parts"):  # Good-only text: kept, it has no place in normalized yet (reported)
            if pages is None or set(pages) == set(every):
                report["skipped"] += [dict(x, uid=u["uid"]) for x in unit_ops(u, [], decisions)["skipped"]]
            continue
        if not unit_pages(u) & want:
            continue
        texts = merge_view._part_texts(store, vol, u["parts"], cache)
        if texts is None:
            continue
        r = unit_ops(u, texts, decisions)
        for (page, path), v in r["ops"].items():
            if page in want:
                ops.setdefault((page, path), []).extend(v)
        report["skipped"] += [dict(s, uid=u["uid"]) for s in r["skipped"]]
        found = md._matches(decisions, u["uid"], u.get("changes") or [])
        report["reopened"] += sum(1 for rec, state in found.values() if state == "reopened" and rec.get("choice"))
    out = {}
    for p in pages:
        before = read(p)
        if before is None:
            continue
        page = copy.deepcopy(before)
        for (pg, path), v in ops.items():
            if pg == p:
                _set_field(page, path, apply_ops(merge_view.field(before, path) or "", v))
        out[p] = (before, renumber(page, before))
    return out, report


def build_pages(store, vol, units_doc, decisions, pages=None):
    """Rebuild data/<vol>/merged/ for those pages (None: all): normalized + decisions + free edits; never writes
    normalized. -> {"written": [pages], "skipped", "reopened"}."""
    import review_store
    built, report = merged_pages(store, vol, units_doc, decisions, pages)
    folder = merged_dir(store.data, vol)
    folder.mkdir(parents=True, exist_ok=True)
    for p, (_, page) in built.items():
        f = folder / f"page_{p:04d}.json"
        tmp = f.with_name(f.name + ".tmp")
        tmp.write_text(review_store.dumps(page), encoding="utf-8")
        os.replace(tmp, f)
    return {"written": sorted(built), **report}


def narrow(field, a, b, text):
    """A free edit of field[a:b] into `text`, narrowed to the words that differ (at least one old word kept,
    so the edit has a place): -> (at, old, new)."""
    old = field[a:b]
    ow = [(m.start(), m.end(), m.group()) for m in re.finditer(r"\S+", old)]
    nw = [(m.start(), m.end(), m.group()) for m in re.finditer(r"\S+", text)]
    if not ow:
        return a, old, text
    p = 0
    while p < min(len(ow), len(nw)) and ow[p][2] == nw[p][2]:
        p += 1
    q = 0
    while q < min(len(ow), len(nw)) - p and ow[-1 - q][2] == nw[-1 - q][2]:
        q += 1
    if len(ow) - p - q == 0:  # only words added: keep the word before them (else the one after)
        if p:
            p -= 1
        else:
            q -= 1
    o0, o1 = ow[p][0], ow[len(ow) - q - 1][1]
    ns = nw[p:len(nw) - q]
    new = text[ns[0][0]:ns[-1][1]] if ns else ""
    return a + o0, old[o0:o1], new
