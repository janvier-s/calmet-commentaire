"""Italics for Good's words, from the slant measured on the Good scan (scan_ocr.ITALIC_AT / ROMAN_AT).

    runs(ws)                       -> [[first, last]]: the runs of Good words (indexes in ws) printed in italics
    apply(final, raw, runs)        -> `final` (raw as modernized and punctuated) with _italics_ marked
    shift(flags, text)             -> flags' offsets (into text without its underscores) moved into `text`

A word leans italic from ITALIC_AT degrees and roman up to ROMAN_AT; in between, or unmeasured, it takes
its neighbours' reading when both agree. A lone one- or two-letter word (de, et, a) is never an italic run.
"""
import difflib
import re

ITALIC_AT, ROMAN_AT = 9, 4  # scan_ocr's


def _flags(ws):
    s = [w.get("sl") for w in ws]
    f = [True if x is not None and x >= ITALIC_AT else False if x is not None and x <= ROMAN_AT else None for x in s]
    for i, v in enumerate(f):
        if v is None:
            prev = next((f[j] for j in range(i - 1, -1, -1) if f[j] is not None), False)
            nxt = next((f[j] for j in range(i + 1, len(f)) if f[j] is not None), False)
            f[i] = prev and nxt
    return f


def runs(ws):
    f = _flags(ws)
    out, i = [], 0
    while i < len(f):
        if not f[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(f) and f[j + 1]:
            j += 1
        letters = sum(len(re.sub(r"\W", "", ws[k]["t"])) for k in range(i, j + 1))
        if not (j == i and letters <= 2):
            out.append([i, j])
        i = j + 1
    return out


def _key(t):
    return re.sub(r"\W", "", t.lower())


EDGE = re.compile(r"^([^\w]*)(.*?)([^\w]*)$", re.S)


def apply(final, raw, runs_):
    """`final` with the words that stand for raw's italic words between underscores (punctuation outside)."""
    if not runs_ or not final:
        return final
    rt, ft = raw.split(), final.split()
    it = [False] * len(rt)
    for a, b in runs_:
        for k in range(a, min(b + 1, len(rt))):
            it[k] = True
    out = [False] * len(ft)
    sm = difflib.SequenceMatcher(None, [_key(t) for t in rt], [_key(t) for t in ft], autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                out[j1 + k] = it[i1 + k]
        elif tag == "replace" and i2 > i1 and all(it[i1:i2]):
            for k in range(j1, j2):
                out[k] = True
    res, i = [], 0
    while i < len(ft):
        if not out[i]:
            res.append(ft[i])
            i += 1
            continue
        j = i
        while j + 1 < len(ft) and out[j + 1]:
            j += 1
        words = ft[i:j + 1]
        lead, _, _ = EDGE.match(words[0]).groups()
        _, _, tail = EDGE.match(words[-1]).groups()
        core = " ".join(words)
        core = core[len(lead):len(core) - len(tail) if tail else len(core)]
        if re.search(r"\w", core):
            res.append(f"{lead}_{core}_{tail}")
        else:
            res.append(" ".join(words))
        i = j + 1
    return " ".join(res)


def shift(flags, text):
    """flags ([{a, b, ...}] offsets into the text as it is without underscores) moved into `text` with them."""
    if not flags or "_" not in text:
        return flags
    plain = [i for i, ch in enumerate(text) if ch != "_"]

    def at(k):
        return plain[k] if k < len(plain) else len(text)
    return [dict(f, a=at(f["a"]), b=at(f["b"] - 1) + 1 if f["b"] > f["a"] else at(f["b"])) for f in flags]
