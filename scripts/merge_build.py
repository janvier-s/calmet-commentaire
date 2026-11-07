"""The merged text: normalized + the /merge decisions + free edits, as operations on normalized's fields.

The unit view draws its left column from these operations and the page build writes data/<vol>/merged/ from
them, so the screen and the output agree. A note's marker (^{(a)}) inside a span Good replaces or cuts is kept,
so no old note is lost; markers are renumbered per page when a page's set of them changed. Nothing here writes
normalized.
"""
import copy
import re

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
    """Good's wording for take Good: punctuated, else modern, else as read."""
    return next((c[k] for k in ("good_punct", "good_modern") if c.get(k) is not None), c.get("good_raw") or "")


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
    if good and tail and good[-1].isalnum():
        good += tail.group()
    marks = [m.group() for m in CALL.finditer(old_slice) if m.group() not in good]
    return " ".join([good] + marks if good else marks)


def apply_ops(text, ops):
    """ops [{a, b, new}] (non-overlapping) applied right to left; where new text meets a word it gets one
    space, never a doubled one."""
    for op in sorted(ops, key=lambda o: (o["a"], o["b"]), reverse=True):
        left, right, new = text[:op["a"]], text[op["b"]:], (op["new"] or "").strip()
        if not new:
            if not left:
                right = right.lstrip()
            elif left[-1].isspace() and (not right or right[0].isspace() or right[0] in NO_SPACE_BEFORE):
                left = left.rstrip()
            text = left + right
            continue
        if left and not left[-1].isspace() and left[-1] not in NO_SPACE_AFTER:
            new = " " + new
        if right and not right[0].isspace() and right[0] not in NO_SPACE_BEFORE:
            new += " "
        text = left + new + right
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
