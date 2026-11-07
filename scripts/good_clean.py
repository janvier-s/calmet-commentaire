"""Good's text cleaned the way `normalized` was: the same rules, run on text that already carries its _italics_.

    good_clean(text)            -> the cleaned text
    clean_records(text)         -> (cleaned, records): records = [{i, before, after, rule}], one per changed
                                   run of words (i = index of the first word of `before` in text.split())
    apply_records(text, recs, undone=())  -> text with every record applied but the undone ones
    remap_flags(flags, a, b)    -> flags' offsets (into text a without underscores) moved to text b's

The pipeline is modernize_inplace.modernize_page's, field by field: Latin spans (marked _..._) and the halves of
words broken at a page turn stay as printed (clean_mechanical.keep_printed); then spaced letters, spelling,
modernization (modernize_text, shared with normalized), old forms hunspell knows (scan_ocr.modern_words), and
the typography of fix_typography (& c. -> etc., long s), and last the OCR garble of good_spell. One rule set for both layers: a new rule added to those
tables reaches Good's text on the next `good_normalize.py` run.
"""
import difflib
import re

import clean_mechanical
import fix_typography
import modernize_inplace
import good_spell
import scan_ocr


def _mod(t):
    return modernize_inplace.modernize_text(t)[0]


def _typography(t):
    return fix_typography.fix(t.replace("’", "'"))


# (rule name, function on the text). keep_printed holds Latin spans out of the rules that touch words.
STAGES = [
    ("typography", _typography),
    ("spaced-letters", clean_mechanical.fix_spaced_letters),
    ("spelling", lambda t: clean_mechanical.keep_printed(clean_mechanical.fix_spelling, t)),
    ("modernize", lambda t: clean_mechanical.keep_printed(_mod, t)),
    ("old-forms", lambda t: clean_mechanical.keep_printed(scan_ocr.modern_words, t)),
    ("ocr-spelling", lambda t: clean_mechanical.keep_printed(good_spell.fix, t)),  # OCR garble: good_spell.py
]


def _run(text):
    """(final text, [(rule, text after it)])"""
    outs = []
    for rule, fn in STAGES:
        new = fn(text)
        if new != text:
            outs.append((rule, new))
            text = new
    return text, outs


def good_clean(text):
    return _run(text)[0] if text else text


def _ops(a, b):
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return [o for o in sm.get_opcodes() if o[0] != "equal"]


def clean_records(text):
    """The cleaned text and its changes as records, each labelled with the stage(s) that made it."""
    if not text:
        return text, []
    final, outs = _run(text)
    if final == text:
        return text, []
    src, dst = text.split(), final.split()
    stage_after = []  # per stage, the words it newly produced
    prev = src
    for rule, t in outs:
        cur = t.split()
        stage_after.append((rule, {w for tag, i1, i2, j1, j2 in _ops(prev, cur) for w in cur[j1:j2]}))
        prev = cur
    recs = []

    def add(i1, i2, j1, j2):
        after = dst[j1:j2]
        rules = [r for r, ws in stage_after if ws & set(after)] or [r for r, _ in outs]
        recs.append({"i": i1, "before": " ".join(src[i1:i2]), "after": " ".join(after), "rule": "+".join(dict.fromkeys(rules))})
    for tag, i1, i2, j1, j2 in _ops(src, dst):
        if i2 - i1 == j2 - j1:  # word for word: one record each, so each can be undone alone
            for k in range(i2 - i1):
                if src[i1 + k] != dst[j1 + k]:
                    add(i1 + k, i1 + k + 1, j1 + k, j1 + k + 1)
        else:
            add(i1, i2, j1, j2)
    return final, recs


def apply_records(text, recs, undone=()):
    """`text` with the records applied except those whose index in recs is in `undone`."""
    words = text.split()
    out, at = [], 0
    for k, r in enumerate(recs):
        n = len(r["before"].split())
        out += words[at:r["i"]]
        out += r["before"].split() if k in undone else r["after"].split()
        at = r["i"] + n
    out += words[at:]
    return " ".join(out)


def remap_flags(flags, a, b):
    """flags (offsets into `a` without its underscores) moved to the same places in `b` without its underscores."""
    if not flags or a == b:
        return flags
    pa, pb = a.replace("_", ""), b.replace("_", "")
    sm = difflib.SequenceMatcher(None, pa, pb, autojunk=False)
    blocks = sm.get_matching_blocks()

    def at(k):
        for i, j, n in blocks:
            if i <= k < i + n:
                return j + (k - i)
            if i > k:
                return j
        return len(pb)
    return [dict(f, a=at(f["a"]), b=max(at(f["a"]), at(f["b"] - 1) + 1 if f["b"] > f["a"] else at(f["b"]))) for f in flags]
