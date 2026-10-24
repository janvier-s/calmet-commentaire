"""Greek spelling of the footnotes, without Claude: each word checked against an Ancient Greek
dictionary (hunspell-grc, himeros.eu, 760,000 accented forms; cache/refs/grc_hunspell) and the
Septuagint; the ligatures the transcription misreads set right when one reading is a word:
  ου read as ε, ω, υ or ῦ (τῦ, ἀυτῦ, Θεῦ, μυ), or written ȣ, ẽ; στ read as ς (ἔςαι);
  καὶ read as κὶ; a breathing on the first letter of a diphthong (ἀυτὸς for αὐτὸς); ᾶ for οῦ;
  ὐκ for οὐκ. Words transcribed with no accent at all get the Septuagint's usual form (και -> καὶ),
  a tilde its circumflex, an apostrophe after a capital its breathing (Ε'ν -> Ἐν). Proper nouns,
  unaccented in the Septuagint text, are compared without accents. Letters in their variant
  shapes (ϱ ϰ ϐ ϑ ϕ ϖ ϲ) made the usual ones. Last, the dictionary's own suggestions: the same
  letters accented otherwise (ἀριθμους -> ἀριθμούς), or one letter changed, when it has only one.
A word with no reading in the dictionary is left as it is, for the scan.
"""
import atexit
import json
import os
import re
import select
import subprocess
import sys
import time
import unicodedata
from collections import Counter, defaultdict

import bible_refs as B
from paths import SCRIPTS

DICT = SCRIPTS / "cache" / "refs" / "grc_hunspell" / "usr" / "share" / "hunspell" / "grc"
BREATHING = "̓̔"
ACUTE, GRAVE = "́", "̀"
_VALID = {}
ALSO = {"ἀναμέσον", "Μωσῆς", "Μωσῆ", "Μωσῇ", "Μωσῆν", "Μωσέως"}  # spellings of Calmet's time the dictionary lacks


# the dictionary writes the acute as oxia (ό U+1F79), the text as tonos (ό U+03CC): NFC makes oxia tonos
OXIA = str.maketrans("άέήίόύώΐΰΆΈΉΊΌΎΏ", "\u1f71\u1f73\u1f75\u1f77\u1f79\u1f7b\u1f7d\u1fd3\u1fe3\u1fbb\u1fc9\u1fcb\u1fdb\u1ff9\u1feb\u1ffb")


def nfd(w):
    return unicodedata.normalize("NFD", w)


def nfc(w):
    return unicodedata.normalize("NFC", w)


ASKED_FILE = SCRIPTS / "cache" / "refs" / "grc_hunspell_asked.json"
_HUNSPELL = []
_ASKED = json.loads(ASKED_FILE.read_text(encoding="utf-8")) if ASKED_FILE.exists() else {}
_ASKED_DIRTY = False
_SAVED_AT = time.monotonic()


def save_asked():
    global _ASKED_DIRTY, _SAVED_AT
    if _ASKED_DIRTY:
        ASKED_FILE.write_text(json.dumps(_ASKED, ensure_ascii=False), encoding="utf-8")
        _ASKED_DIRTY = False
    _SAVED_AT = time.monotonic()


atexit.register(save_asked)


TIMEOUT = 5  # seconds for one word: a real word takes milliseconds; on some misread ones
             # hunspell's suggestion search runs for minutes


def _read_until(p, end):
    """hunspell's output up to `end`, or None if it has not come within TIMEOUT."""
    buf, deadline = b"", time.monotonic() + TIMEOUT
    while not buf.endswith(end):
        left = deadline - time.monotonic()
        if left <= 0 or not select.select([p.stdout], [], [], left)[0]:
            return None
        chunk = os.read(p.stdout.fileno(), 65536)
        if not chunk:
            return None
        buf += chunk
    return buf.decode("utf-8")


def ask(w):
    """hunspell's answer for one word (pipe mode; one process kept for the run): '*' or '+ …' a word,
    '& … : suggestions', '#' none. A word hunspell cannot answer within TIMEOUT counts as '#'
    (unknown, no suggestion: left for the scan), and hunspell is started again for the next."""
    if w not in _ASKED:
        if not _HUNSPELL:
            p = subprocess.Popen(["hunspell", "-d", str(DICT), "-a"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
            _read_until(p, b"\n")  # the banner
            _HUNSPELL.append(p)
        p = _HUNSPELL[0]
        p.stdin.write(("^" + w.translate(OXIA) + "\n").encode("utf-8"))
        p.stdin.flush()
        out = _read_until(p, b"\n\n")
        if out is None:
            print(f"  hunspell gave no answer for {w} in {TIMEOUT} s: left for the scan", file=sys.stderr, flush=True)
            p.kill()
            _HUNSPELL.clear()
            lines = ["# timeout"]
        else:
            lines = [l.strip() for l in out.splitlines() if l.strip()]
        _ASKED[w] = lines
        global _ASKED_DIRTY
        _ASKED_DIRTY = True
        if time.monotonic() - _SAVED_AT > 60:  # every minute too, so a run stopped midway keeps its answers
            save_asked()
    return _ASKED[w]


def check(words):
    """The words the dictionary has (as printed, or with a final acute made grave, or in lower case)."""
    for w in words:
        if w not in _VALID:
            _VALID[w] = any(all(x[:1] in "*+-" for x in ask(re.sub(r"[᾽’'ʼ]$", "", v)) or ["#"]) for v in sorted(forms(w)))  # sorted: the same forms asked every run, so the cache answers
    return {w for w in words if _VALID.get(w)}


def suggestions(words):
    """{word: the dictionary's suggestions}."""
    res = {}
    for w in set(words):
        for line in ask(w):
            if line.startswith("&"):
                res.setdefault(w, []).extend(nfc(x) for x in line.split(": ", 1)[1].split(", "))
    return res


def distance(a, b):
    """Letters added, dropped or changed between two words, accents aside."""
    a, b = plain(a), plain(b)
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def one_of(cands):
    """The one word among `cands`, a final grave or acute aside; None if there are several."""
    keys = {nfd(c).replace(GRAVE, ACUTE) for c in cands}
    return sorted(cands)[0] if len(keys) == 1 else None


def letter_marks(w):
    """The accents on each letter (breathings aside)."""
    out = []
    for c in nfd(w):
        if unicodedata.combining(c):
            if out and c not in BREATHING:
                out[-1].add(c)
        else:
            out.append(set())
    return out


def completed(w, cands):
    """Among words with the same letters as `w`: the one that keeps every accent printed and adds
    the fewest (a breathing missing or wrong counts nothing), then the Septuagint's. None if two are as good."""
    mine = letter_marks(w)
    scored = []
    for c in cands:
        theirs = letter_marks(c)
        if len(theirs) == len(mine) and all(a <= b for a, b in zip(mine, theirs)):
            same_breathing = [x for x in nfd(c) if x in BREATHING] == [x for x in nfd(w) if x in BREATHING]
            usual = -lxx_forms().get(plain(c), Counter()).get(nfc(nfd(c.lower()).replace(GRAVE, ACUTE)), 0)
            scored.append((sum(len(b - a) for a, b in zip(mine, theirs)), not same_breathing, usual, c))
    scored.sort()  # last, the form the Septuagint uses most (Ἐὰν, not Ἑὰν)
    if not scored or len(scored) > 1 and scored[0][:3] == scored[1][:3]:
        return None
    return scored[0][3]


def forms(w):
    low = w[:1].lower() + w[1:]
    out = {w, low}
    for x in (w, low):
        d = nfd(x)
        out |= {nfc(d.replace(ACUTE, GRAVE)), nfc(d.replace(GRAVE, ACUTE))}
    return out


_LXX = {}


def lxx_forms():
    """plain word -> Counter of its forms in the Septuagint (lower case)."""
    if not _LXX:
        forms = defaultdict(Counter)
        for f in (B.REFS / "lxx").glob("[0-9]*.json"):
            for t in B.lxx(int(f.stem)).values():
                for w in re.findall(r"[^\W\d_]+", t):
                    forms[B.plain(w).replace("ς", "σ")][w.lower()] += 1
        _LXX.update(forms)
    return _LXX


def plain(w):
    return B.plain(w).replace("ς", "σ")


VARIANTS = str.maketrans("ϱϰϐϑϕϖϲ", "ρκβθφπσ")


def tidy(w):
    """The transcription's stand-ins: a tilde for the circumflex, an apostrophe after a capital vowel
    for its breathing, letters in their variant shapes."""
    w = nfc(nfd(w.translate(VARIANTS)).replace("\u0303", "\u0342"))
    m = re.match(r"([ΑΕΗΙΟΥΩ])['’᾿]", w)
    if m:
        w = nfc(m.group(1) + ("\u0314" if m.group(1) == "Υ" else "\u0313")) + w[2:]
    return w


def accented(w):
    """A word transcribed with no accent or breathing: the Septuagint's usual form of it, if one is."""
    if any(unicodedata.combining(c) for c in nfd(w)):
        return None
    forms = lxx_forms().get(plain(w))
    if not forms:
        return None
    best, n = forms.most_common(1)[0]
    if n < 0.75 * sum(forms.values()) or not any(unicodedata.combining(c) for c in nfd(best)):
        return None
    return best[0].upper() + best[1:] if w[0].isupper() else best


def proper_noun(w):
    """A capitalised word the Septuagint has, compared without accents (names are unaccented there)."""
    return w[:1].isupper() and plain(w) in lxx_forms() and not any(
        unicodedata.combining(c) for f in lxx_forms()[plain(w)] for c in nfd(f))


def breathing_moved(w):
    """ἀυτῦ -> αὐτῦ: the breathing belongs on the second letter of a diphthong."""
    d = nfd(w)
    m = re.match(rf"([αεοΑΕΟ])([{BREATHING}])([\u0342\u0345]*)([ιυ])", d)  # ἄυλος, accented, is a word
    if not m:
        return None
    return nfc(m.group(1) + m.group(3).replace(ACUTE, "").replace(GRAVE, "") + m.group(4) + m.group(2)
               + "".join(c for c in m.group(3) if c in ACUTE + GRAVE + "͂") + d[m.end():])


def one_step(w):
    """Readings of `w` with one ligature set right."""
    out = set()
    w2 = w.replace("ȣ", "ου").replace("ẽ", "οῦ")
    if w2 != w:
        out.add(w2)
    if w in ("κὶ", "κὴ", "Κὶ", "Κὴ"):
        out.add("Καὶ" if w[0] == "Κ" else "καὶ")
    d = nfd(w)
    if d[:1] in ("υ", "Υ") and d[1:2] in BREATHING:  # ὐκ -> οὐκ
        out.add(nfc(("Ο" if d[0] == "Υ" else "ο") + "υ" + d[1:]))
    b = breathing_moved(w)
    if b:
        out.add(b)
    for i, ch in enumerate(w):
        if ch == "ς" and i < len(w) - 1 and w[i + 1].isalpha():
            out.add(w[:i] + "στ" + w[i + 1:])
        base = nfd(ch)
        letter, marks = base[0], base[1:]
        prev = w[i - 1] if i else ""
        if letter == "α" and "\u0342" in marks and i:  # ἐμᾶ -> ἐμοῦ
            out.add(w[:i] + nfc("ου" + marks) + w[i + 1:])
        if (letter in "εω" and i) or (letter == "υ" and prev and (nfd(prev)[0] not in "αεηοωυι" or "\u0342" in marks)):
            out.add(w[:i] + nfc("ο" + "υ" + marks) + w[i + 1:])
    return out


def readings(w):
    """Readings of `w` with up to two ligatures set right."""
    first = one_step(w)
    return first | {r2 for r in first for r2 in one_step(r)}


def ou_dropped(w):
    """τῦ -> τοῦ, Θεῦ -> Θεοῦ: the ου ligature read as υ."""
    out = set()
    for i, ch in enumerate(w):
        if nfd(ch)[0] == "υ" and i:
            out.add(w[:i] + nfc("ου" + nfd(ch)[1:]) + w[i + 1:])
    return out


def fix(tokens, in_septuagint=lambda w: False):
    """{token: corrected} for the misread words with exactly one reading in the dictionary
    or the Septuagint, and the words with none."""
    fixed, unknown = {}, []
    words = []
    for t in tokens:
        if not re.search(r"[α-ωΑ-Ωἀ-῿ẽȣ]", t):
            continue
        w = tidy(t)
        a = accented(w)
        if a or w != t:
            fixed[t] = a or w
        words.append(a or w)
    good = check(words) | {w for w in words if in_septuagint(w) or proper_noun(w) or w in ALSO}
    origin = {v: k for k, v in fixed.items()}
    for w in words:
        t = origin.get(w, w)
        if len(re.sub(r"[^α-ωΑ-Ωἀ-῿]", "", nfd(w))) < 2:
            if w not in good:
                unknown.append(t)  # a letter alone: nothing to read it by
            continue
        if w in good and w not in ("κὶ", "κὴ", "Κὶ", "Κὴ"):
            lxx = [r for r in ou_dropped(w) if in_septuagint(r)]
            if len(lxx) == 1 and not in_septuagint(w):  # Θεῦ: a form the dictionary has, but Calmet's Θεοῦ misread
                fixed[t] = lxx[0]
            continue
        cands = sorted(readings(w))
        ok = check(cands) | {c for c in cands if in_septuagint(c)}
        if len(ok) == 1:
            fixed[t] = ok.pop()
        elif ok and len({nfd(c).replace(GRAVE, ACUTE) for c in ok}) == 1:
            fixed[t] = sorted(ok)[0]  # the same word with a final grave or acute
        else:
            unknown.append(t)
    if unknown:  # the dictionary's suggestions: same letters accented otherwise, else one letter changed
        sug = suggestions([origin_inv(t, fixed) for t in unknown])
        for t in list(unknown):
            w = origin_inv(t, fixed)
            if len(plain(w)) < 3:
                continue
            ss = [x for x in sug.get(w, []) if " " not in x and x[:1].isupper() == w[:1].isupper()
                  and nfd(x[-1])[0] in "αεηιουωνρςξψ"]  # a Greek word ends so (ὀρθωθέντ is no word)
            pick = completed(w, [x for x in ss if plain(x) == plain(w)]) or one_of([x for x in ss if distance(x, w) == 1])
            if pick:
                fixed[t] = pick
                unknown.remove(t)
    return fixed, unknown


def origin_inv(t, fixed):
    """The token as tidied before the dictionary saw it."""
    return fixed.get(t, tidy(t))
