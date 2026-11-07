"""Rule-based spelling of Good's OCR garble: a word hunspell does not know, mended only when one repair is sure.

    fix(text) -> text      (a stage of good_clean: Latin spans stay as printed, names and Latin words are never touched)

For a lowercase word hunspell flags (not a name of spellcheck_names.txt, not a word of the Vulgate):
  accent    one hunspell suggestion differs only by accents        (tres -> très, chatiment -> châtiment)
  -èrent    -erent where the -èrent form is known                  (avancerent -> avancèrent)
  slip      one letter missing, extra, or misread (f/s, m/n, e/c, u/n, v/u, i/l, a/o), hunspell's first
            suggestion, and a word the corpus already uses (spellcheck.french_words)
and a doubled function word (de de, la la). Nothing else is guessed: the agent pass (good_spell_agent.py) lists
real-word and context errors for review, and unknown words stay as printed.
"""
import re

import spellcheck
from calmet import _fold, vulgate_words

WORD = re.compile(r"(?<![^\W_])[a-zà-ÿœ][^\W_]*(?![^\W_])")
KEEP = {"posson"}  # old words hunspell does not know and a slip would change (a measure of capacity)
CONFUSED = {frozenset(p) for p in ("fs", "mn", "ec", "un", "vu", "il", "ao", "lt")}
DOUBLED = {"de", "du", "la", "le", "les", "des", "et", "à", "en", "un", "une", "que", "qui", "ou", "au", "aux", "se", "ne", "par", "pour", "dans", "sur", "est", "ce", "cette", "ses", "son", "sa", "mais", "avec"}
_known = {}   # word -> hunspell's suggestions, or None when it is a French word


def warm(ws):
    """Ask hunspell about the words not asked yet (one call for all)."""
    import contextlib
    import io
    todo = sorted({w for w in ws if w not in _known})
    if todo:
        with contextlib.redirect_stdout(io.StringIO()):
            bad = spellcheck.check(todo)
        for w in todo:
            _known[w] = bad.get(w)


def _slip(a, b):
    """True when b is a with one letter missing, extra, or one of the CONFUSED pairs."""
    if len(a) == len(b):
        d = [i for i in range(len(a)) if a[i] != b[i]]
        return len(d) == 1 and frozenset((a[d[0]], b[d[0]])) in CONFUSED
    s, l = sorted((a, b), key=len)
    if len(l) - len(s) != 1:
        return False
    i = 0
    while i < len(s) and s[i] == l[i]:
        i += 1
    return s[i:] == l[i + 1:]


def repair(w, names=None, lexicon=None, vul=None, after=False):
    """The mended form of the lowercase word w, or None. `after`: w follows an apostrophe (l'lusieurs: a
    lost capital, not a slip), where only accents and -èrent are mended."""
    names = spellcheck.known_names() if names is None else names
    lexicon = spellcheck.french_words() if lexicon is None else lexicon
    vul = vulgate_words() if vul is None else vul
    warm([w])
    sugg = _known.get(w)
    if sugg is None or w in names or w in KEEP or _fold(w) in vul or len(w) < 4:
        return None
    if w.endswith("erent") and len(w) > 6:
        v = w[:-5] + "èrent"
        warm([v])
        if _known.get(v) is None:
            return v
    cands = [x.strip() for x in sugg.split(",")]
    cands = [x for x in cands if x and x == x.lower() and re.fullmatch(r"[a-zà-ÿœ]+", x)]
    acc = [x for x in cands if _fold(x) == _fold(w)]
    if len(acc) == 1 and not (re.search("[ïëü]", w) and re.search("[àâéèêîôûù]", w)):  # envoïé is envoyé, not envoie
        return acc[0]
    if len(w) >= 6 and cands and not after:
        first = cands[0]
        if first in lexicon and _slip(_fold(w), _fold(first)) and first[:-1] != w and w[:-1] != first and sugg.split(",")[0].strip() == first:
            return first
    return None


def fix(text):
    if not text:
        return text
    names, lexicon, vul = spellcheck.known_names(), spellcheck.french_words(), vulgate_words()
    warm(WORD.findall(re.sub(r"_[^_\n]+_", " ", text)))

    def one(m, part):
        w = m.group()
        r = repair(w, names, lexicon, vul, after=m.start() > 0 and part[m.start() - 1] in "'’")
        return r if r else w
    # words between underscores are italic (Latin, a quoted word): left as printed
    out = "".join(p if p.startswith("_") and p.endswith("_") and len(p) > 1 else WORD.sub(lambda m: one(m, p), p)
                  for p in re.split(r"(_[^_\n]+_)", text))
    return re.sub(r"(?<![^\W_])([^\W_]+) \1(?![^\W_])", lambda m: m.group(1) if m.group(1).lower() in DOUBLED else m.group(), out)
