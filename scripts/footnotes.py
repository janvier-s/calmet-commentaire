"""Footnotes: check Calmet's notes against the texts and the scans; write references out in full.

Stages (`run` does all three; every Claude answer is cached):
  1. local, free: Bible references written out with Calmet's (Vulgate) names and checked
     against the Vulgate, and against the Latin they are cited for; Hebrew checked against
     the Hebrew Bible, Greek against the Septuagint, allowing for misread type (letters set
     right from the Bible); [UNCERTAIN …], [ILLEGIBLE] and the
     references garbled by the earlier expansion ("inGenèse 50actant.") flagged.
  2. scan: Claude reads the footnote area of the scan, for the flagged Hebrew, Greek and
     uncertain notes only. Text it supplies for an uncertain or illegible place gets "*".
  2b. context (--context): what stays doubtful (Hebrew and Greek not found, [UNCERTAIN …],
     references that do not exist or are ambiguous) set right by Claude from the passage the
     note is called from, text only, the answer only the edits; guessed text gets "*".
  3. expand: footnote_expand.py writes out, without Claude, the notes made of citations the
     glossary knows; Claude writes out the rest (Fathers, commentators, classical authors),
     in batches, following footnote_glossary.txt. With --local, only footnote_expand.py.
Writes docs/footnotes/<volume>.json: each changed or flagged note with its current text,
the proposal, why, and flags. `apply` writes the proposals into normalized/.

Usage: uv run --no-project --with pillow python footnotes.py run <volume|book|all> ... [--pages 99-140] [--local | --no-scan] [--uncertain-only] [--context] [--apply]
       python3 footnotes.py apply <volume|book|all> ... [--pages 99-140] [--no-hold]
       python3 footnotes.py held      (every note still held, all volumes: docs/footnotes/held.json)
Several volumes run one after another in one process (the Bible indexes are built once).
run --apply writes each volume's proposals in as soon as it is done, flagged notes held.
CLAUDE_MODEL (expand) and SCAN_MODEL (scan) choose the models (default sonnet for both).
FOOTNOTE_BACKEND=agy sends the text-only calls (expand, --context) to agy instead of Claude Code
(AGY_MODEL picks its model, e.g. gemini-3.8-flash-medium; default: agy's own); the scan stays with Claude.
Answers Claude already gave for the same notes are used as they are, not asked again.
"""
import asyncio, difflib, hashlib, json, os, re, sys, tempfile, unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from functools import lru_cache

import bible_refs as B
import footnote_spell
from paths import BOOKS, BY_VOLUME, DATA, DOCS, SCRIPTS, pages as volume_pages, volumes_of

OUT_DIR = DOCS / "footnotes"
CACHE = SCRIPTS / "cache" / "footnote_cache.json"
CROPS = SCRIPTS / "cache" / "footnote_crops2"
GLOSSARY = (SCRIPTS / "footnote_glossary.txt").read_text(encoding="utf-8")
BACKEND = os.environ.get("FOOTNOTE_BACKEND", "claude")
AGY_MODEL = os.environ.get("AGY_MODEL", "")
CLAUDE_EXPAND = os.environ.get("CLAUDE_MODEL", "sonnet")
# the model's name goes into the cache keys: agy's answers are kept apart from Claude's
EXPAND_MODEL = f"agy:{AGY_MODEL or 'default'}" if BACKEND == "agy" else CLAUDE_EXPAND
SCAN_MODEL = os.environ.get("SCAN_MODEL", "sonnet")
BATCH, PARALLEL = 50, 4

HEB = re.compile(r"[א-ת][֑-״־\s'\"]*")
HEB_SEG = re.compile(r"[֑-״]+(?:[\s־]+[֑-״]+)*")
GRK_SEG = re.compile(r"[Ͱ-Ͽἀ-῿][Ͱ-Ͽἀ-῿̀-ͯ'’᾽ʼ]*"
                     r"(?:[\s,.;·:()]+[Ͱ-Ͽἀ-῿][Ͱ-Ͽἀ-῿̀-ͯ'’᾽ʼ]*)*")
UNSURE = re.compile(r"\[(?:UNCERTAIN[^\]]*|ILLEGIBLE)\]")
FRENCH_BOOKS = "|".join(sorted({re.escape(k.split(" ", 1)[-1]) for k in B.BOOK} | {"Samuel", "Chroniques"}, key=len, reverse=True))
GLUED = re.compile(rf"[a-zà-ÿ](?:{FRENCH_BOOKS})\b|\b(?:{FRENCH_BOOKS})\s?\d+(?::\d+)?[A-Za-zÀ-ÿ]")
SEE = re.compile(r"^\s*(?:Vide|Vid\.|Voir|Voi|Voyez|Voy\.)\s*", re.I)
SEQ = re.compile(r"^\s*\.?\s*(?:&|et)\s*(?:seq|sequ|sq|suiv)\w*\.?", re.I)
COMPARE = re.compile(r"^\s*\.?\s*(?:comparé à|comparez|conf\.?|cf\.?)\s*", re.I)
GAP = re.compile(r"^[\s.,;:&]*(?:et\s*)?[\s.,;:&]*$")
IBID = re.compile(r"^\s*(?:Ibid|Idem|Id)\.?\s*,?\s*")
VERSET_ONLY = re.compile(r"^\s*(?:℣|v|verset|vers)\.?\s*(\d{1,3}(?:\s*(?:\.|,|-|&|et)\s*\d{1,3})*)\.?\s*$", re.I)


def abbreviations():
    """Every abbreviation the glossary or the Bible table knows (plain, without the full stop)."""
    out = set(B.ABBR) | {"l", "c", "q", "qu", "ep", "hom", "homil", "lib", "cap", "ch", "chap", "n", "p", "pag",
                         "art", "edit", "not", "serm", "orat", "tract", "epist", "quaest", "quaest", "init",
                         "vid", "ibid", "id", "seq", "sequ", "sq"}
    for line in GLOSSARY.splitlines():
        for left in re.findall(r"(?:^|\s{2,})([^=]+?)\s=", line):
            for a in left.split(" / "):
                for w in re.findall(r"([A-Za-zÀ-ÿæœÆŒ]+)\.", a):
                    out.add(B.plain(w))
    return out


ABBREV = abbreviations()


def needs_expansion(t):
    return any(B.plain(w) in ABBREV for w in re.findall(r"(?<![\w])([A-Za-zÀ-ÿæœÆŒſ]{1,14})\.(?=[\s,;:)]|$)", t))


def marker_key(m):
    return re.sub(r"[^a-z0-9*†]", "", str(m).lower())


# ---- reading the volume ----------------------------------------------------------

def load_volume(volume, lo, hi):
    """Every footnote of the volume in [lo, hi] with where it is called from."""
    book_key = BY_VOLUME[volume]
    vol_book = B.OT_NAME.get(BOOKS[book_key]["vul"]) or BOOKS[book_key]["fr"]
    notes = []
    for p in volume_pages(volume):
        n = int(p.stem[5:9])
        if not lo <= n <= hi:
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        rp = DATA / volume / "raw_json" / "commentaire" / p.name
        raw = {}
        try:
            rd = json.loads(rp.read_text(encoding="utf-8"))
            for rn in (rd.get("footnotes") or []) if isinstance(rd, dict) else []:
                if isinstance(rn, dict) and isinstance(rn.get("text"), str):
                    raw.setdefault(marker_key(rn.get("marker")), rn["text"])
        except (OSError, json.JSONDecodeError):
            pass
        blocks = []  # (text, chapter, verse)
        for c in d.get("commentary") or []:
            t = " | ".join((c.get(k) or "") for k in ("latin_quote", "french_translation", "french_commentary"))
            v = re.match(r"\d+", str(c.get("verse_ref") or ""))
            blocks.append((t, c.get("chapter") or d.get("chapter_number"), int(v.group()) if v else None))
        for v in d.get("verses") or []:
            if isinstance(v.get("annotations"), str):
                blocks.append((v["annotations"], v.get("chapter"), v.get("verse_number")))
        for fn in d.get("footnotes") or []:
            if not isinstance(fn.get("text"), str) or "marker" not in fn:
                continue
            call = "^{" + str(fn["marker"]) + "}"
            chap = verse = None
            before = after = ""
            for t, c, vn in blocks:
                i = t.find(call)
                if i >= 0:
                    chap, verse = c, vn
                    before, after = t[max(0, i - 300):i], t[i + len(call):i + len(call) + 120]
                    break
            notes.append(dict(id=f"{p.stem[5:9]}{fn['marker']}", page=p.stem, marker=fn["marker"],
                              chap=chap or d.get("chapter_number"), verse=verse, before=before, after=after,
                              text=fn["text"], raw=raw.get(marker_key(fn["marker"]), ""),
                              vol_book=vol_book, why=[], flags=[]))
    return notes


# ---- stage 1: local ------------------------------------------------------------

def chapters_around(book, chap):
    """Hebrew-book chapters to look in for a Calmet chapter (psalm numbers converted)."""
    if not chap:
        return []
    if book == "Psalms":
        return [c for n in B.vulgate_to_hebrew_psalm(chap) for c in (n - 1, n, n + 1)]
    return [chap - 1, chap, chap + 1]


HEB_POINTS = re.compile(r"[֑-ׇ]")
HEB_ALIKE = str.maketrans("דחכזןךםףץ", "רהבווכמפצ")  # letters small type confuses (ר/ד, ה/ח, ב/כ, ו/ז/ן); final forms


@lru_cache(None)
def heb_skel(w):
    """A Hebrew word with the letters small type confuses made one, and without ו/י (spelled full or not)."""
    return re.sub("[וי]", "", re.sub(r"[^א-ת]", "", w).translate(HEB_ALIKE))


@lru_cache(None)
def grk_skel(w):
    """A Greek word without accents, with the ligatures the transcription misreads made one (ου read ε or ω, στ read σ)."""
    w = B.plain(unicodedata.normalize("NFD", w.replace("ẽ", "ου")).replace("\u0345", "ι")).replace("ς", "σ").replace("ȣ", "ου").replace("στ", "σ")
    return re.sub(r"[^α-ω]", "", w.replace("ου", "ε").replace("ω", "ε"))


# Greek runs, with the ου ligature as the transcription writes it (ẽ, ȣ)
GRK_RUN = re.compile(r"[Ͱ-Ͽἀ-῿ẽȣ][Ͱ-Ͽἀ-῿ẽȣ̀-ͯ'’᾽ʼ]*(?:[\s,.;·:()]+[Ͱ-Ͽἀ-῿ẽȣ][Ͱ-Ͽἀ-῿ẽȣ̀-ͯ'’᾽ʼ]*)*")
LXX_NAME = {nr: name for name, (_, _, nr) in B.BOOK.items() if nr}
_STREAMS = {}


def stream(kind):
    """The whole Hebrew Bible or Septuagint as one word list: (words, skeletons, (book, c, v) of each, skeleton -> positions)."""
    if kind not in _STREAMS:
        words, where = [], []
        if kind == "hebrew":
            for b, vs in B.hebrew().items():
                for (c, v), ws in sorted(vs.items()):
                    words += ws
                    where += [(b, c, v)] * len(ws)
        else:
            for f in sorted((B.REFS / "lxx").glob("[0-9]*.json"), key=lambda f: int(f.stem)):
                for (c, v), t in sorted(B.lxx(int(f.stem)).items()):
                    ws = re.findall(r"[^\W\d_]+(?:[᾽’'][^\W\d_]*)?", t)
                    words += ws
                    where += [(int(f.stem), c, v)] * len(ws)
        skel = heb_skel if kind == "hebrew" else grk_skel
        sk = [skel(w) for w in words]
        index = defaultdict(list)
        for i, s in enumerate(sk):
            index[s].append(i)
        plain = {heb_skel(w) if kind == "hebrew" else B.plain(w).replace("ς", "σ") for w in words}
        _STREAMS[kind] = (words, sk, where, index, plain)
    return _STREAMS[kind]


def find_in_bible(tokens, kind, book, chaps):
    """The passage of the Hebrew Bible / Septuagint the words quote, allowing for misread letters.
    Returns (pairs (token index, Bible position), where) or None. Near the verse commented (book,
    chapters `chaps`): two words are enough; elsewhere, three. Three words in four must match."""
    words, sk, where, index, _ = stream(kind)
    skel = heb_skel if kind == "hebrew" else grk_skel
    ts = [skel(t) for t in tokens]
    k = len(ts)
    if k < 2:
        return None
    rare = sorted((i for i in range(k) if ts[i] and len(index.get(ts[i], [])) > 0), key=lambda i: len(index[ts[i]]))[:3]
    want = Counter(ts)
    best = None
    for i in rare:
        for p in index[ts[i]][:2000]:
            start = p - i
            window = sk[max(0, start - 2):start + k + 2]
            near = where[p][0] == book and where[p][1] in chaps
            # the words window and tokens share bound the pairs difflib can find: skip the
            # windows that could not pass, or not beat the best so far
            most = sum((Counter(window) & want).values())
            if most < (2 if near else 3) or most < -(-3 * k // 4) or (best and (most, near) <= best[0]):
                continue
            sm = difflib.SequenceMatcher(None, ts, window, autojunk=False)
            pairs = [(b.a + j, max(0, start - 2) + b.b + j) for b in sm.get_matching_blocks() for j in range(b.size)]
            if len(pairs) < (2 if near else 3) or len(pairs) < -(-3 * k // 4):
                continue
            score = (len(pairs), near)
            if not best or score > best[0]:
                best = (score, pairs, where[p])
    return (best[1], best[2]) if best else None


CONFUSED = [set("רד"), set("הח"), set("בכ"), set("וזן"), set("ןנ"), set("מם"), set("ךכ"), set("ףפ"), set("ץצ")]


def heb_misread(old, ref):
    """`old` is `ref` with one letter small type confuses (beyond ו/י spelled full or not)."""
    a, b = re.sub("[וי]", "", old), re.sub("[וי]", "", ref)
    diffs = [(x, y) for x, y in zip(a, b) if x != y]
    return len(a) == len(b) and len(diffs) == 1 and any({*diffs[0]} <= c for c in CONFUSED)


def marks(w):
    """The accents and breathings of a Greek word."""
    return [c for c in unicodedata.normalize("NFD", w) if unicodedata.combining(c)]


def known(token, kind):
    _, _, _, _, plain = stream(kind)
    return (heb_skel(token) if kind == "hebrew" else B.plain(token).replace("ς", "σ")) in plain


def heb_variant(a, b):
    """Only ו and י differ: the same word spelled full or not, left as Calmet prints it."""
    return re.sub("[וי]", "", a) == re.sub("[וי]", "", b)


def verify(seg, kind, book, chaps):
    """Check one Hebrew or Greek phrase against the Bible. Returns (ok, corrected phrase, notes on what changed)."""
    parts = re.split(r"([\s־,.;:·]+)", seg)
    idx = [i for i, p in enumerate(parts) if p and not re.fullmatch(r"[\s־,.;:·]+", p)]
    tokens = [parts[i] for i in idx]
    if kind == "hebrew":
        tokens = [re.sub(r"[^א-ת֑-ׇ]", "", t) for t in tokens]
    if len(tokens) == 1:  # a word alone: spell() checks it
        return False, seg, []
    found = find_in_bible(tokens, kind, book, chaps)
    if not found and kind == "hebrew":  # Hebrew transcribed in visual order
        rev = find_in_bible(tokens[::-1], kind, book, chaps)
        if rev:
            words = [parts[i] for i in idx][::-1]
            for i, w in zip(idx, words):
                parts[i] = w
            seg2 = "".join(parts)
            ok, fixed, changes = verify(seg2, kind, book, chaps)
            return ok, fixed, [f"word order reversed: {seg} -> {seg2}"] + changes
    if not found:
        return False, seg, []
    pairs, (b, c, v) = found
    words = stream(kind)[0]
    matched = {a for a, _ in pairs}
    if not all(known(tokens[i], kind) for i in range(len(tokens)) if i not in matched):
        return False, seg, []
    changes = []
    for a, p in pairs:
        old, ref = parts[idx[a]], words[p]
        if kind == "hebrew":
            bare = re.sub(r"[^א-ת]", "", old)
            if HEB_POINTS.search(old) or bare == ref or heb_variant(bare, ref):
                continue
            if not heb_misread(bare, ref):
                return False, seg, []  # not a slip of the type: the scan decides
            new = re.sub(r"[א-ת]+", ref, old, count=1)
        else:
            same_letters = B.plain(old).replace("ς", "σ") == B.plain(ref).replace("ς", "σ")
            if old == ref or not marks(ref) or (same_letters and marks(old) and
                                               [m for m in marks(old) if m in "\u0313\u0314"] == [m for m in marks(ref) if m in "\u0313\u0314"]):
                continue  # proper nouns are unaccented in the Septuagint text; accents placed otherwise are Calmet's
            new = ref[0].upper() + ref[1:] if old[:1].isupper() else ref
            if new == old:
                continue
        parts[idx[a]] = new
        changes.append(f"{old} -> {new}")
    label = f"the Hebrew Bible, {b} {c}:{v}" if kind == "hebrew" else f"the Septuagint, {LXX_NAME.get(b, b)} {c}:{v}"
    return True, "".join(parts), [f"checked against {label}" + (": " + ", ".join(changes) if changes else "")]


def check_script(note, kind):
    """Each Hebrew (or Greek) phrase: in the Hebrew Bible (or the Septuagint), allowing for misread type?
    Misread letters are set right from the Bible; what cannot be found waits for the scan."""
    vul, oshb, nr = B.BOOK.get(note["vol_book"], (None, None, None))
    if kind == "hebrew":
        book, chaps, segs = oshb, set(chapters_around(oshb, note["chap"])) if oshb else set(), HEB_SEG.findall(note["proposed"])
    else:
        book, chaps = nr, {note["chap"] - 1, note["chap"], note["chap"] + 1} if note["chap"] else set()
        segs = [g.strip(" ,.;:") for g in GRK_RUN.findall(note["proposed"])]
    text, unsure = note["proposed"], []
    for seg in segs:
        if not seg.strip():
            continue
        ok, fixed, why = verify(seg.replace("ẽ", "ου"), kind, book, chaps) if kind == "greek" else verify(seg, kind, book, chaps)
        if not ok:  # not from the Bible: a Father, a classical author, a version; checked word by word
            ok, fixed, why, unknown = spell(seg, kind)
            if unknown:
                unsure.append(" ".join(unknown)[:80])
        if fixed != seg:
            text = text.replace(seg, fixed, 1)
        note["why"] += [("Hebrew " if kind == "hebrew" else "Greek ") + w for w in why]
    note["proposed"] = text
    if unsure:
        note["flags"].append(kind)
        source = "the Hebrew Bible" if kind == "hebrew" else "the Septuagint or the Greek dictionary"
        note["scan_why"].append(f"{'Hebrew' if kind == 'hebrew' else 'Greek'} words not found in {source}: " + " / ".join(unsure))


_HEB_WORDS, _LXX_FORMS = set(), set()
FINAL = dict(zip("כמנפצ", "ךםןףץ"))


def hebrew_words():
    """The Hebrew Bible's words, the Targums' (Sefaria) and Strong's lexicon forms, consonants only."""
    if not _HEB_WORDS:
        _HEB_WORDS.update(w for vs in B.hebrew().values() for ws in vs.values() for w in ws)

        def walk(x):
            if isinstance(x, str):
                _HEB_WORDS.update(re.sub(r"[^א-ת]", "", y) for y in re.split(r"[\s־]+", re.sub(r"<[^>]+>", "", x)))
            elif isinstance(x, list):
                for y in x:
                    walk(y)
        for f in (B.REFS / "targum").glob("*.json"):
            walk(json.loads(f.read_text(encoding="utf-8"))["text"])
        lex = (B.REFS / "strongs" / "StrongHebrewG.xml").read_text(encoding="utf-8")
        _HEB_WORDS.update(re.sub(r"[^א-ת]", "", w) for m in re.findall(r'lemma="([^"]*)"', lex) for w in m.split())
        _HEB_WORDS.discard("")
        _HEB_WORDS.add("ייי")  # the divine name as Calmet and the rabbis abbreviate it
    return _HEB_WORDS


# two letters at least: with one (ה ו י ם…) almost any misreading would pass for a word
SUFFIXES = sorted("ים ות נו כם הם הן יו יה יך ינו יכם יהם יהן ותיו ותיהם ותי ותם ותינו תי".split(), key=len, reverse=True)
FINAL_OF = dict(zip("כמנפצ", "ךםןףץ"))


def hebrew_word(w):
    """A word of the Bible, the Targums or the lexicon, as written, or after its prefixes (ו ה ב כ ל מ ש),
    or its suffixes (plural, possessive; two letters at least) with a stem of three letters at least."""
    words = hebrew_words()
    stems = {w} | {w[k:] for k in range(1, 4) if len(w) - k >= 2 and all(c in "והבכלמש" for c in w[:k])}
    if stems & words:
        return True
    for st in stems:
        for suf in SUFFIXES:
            if st.endswith(suf) and len(st) - len(suf) >= 3:
                base = st[:-len(suf)]
                if base in words or base[:-1] + FINAL_OF.get(base[-1], base[-1]) in words or base + "ה" in words:
                    return True
    return False


def lxx_form(w):
    """A Greek word as the Septuagint would have it: lower case, a final grave made acute."""
    return unicodedata.normalize("NFC", unicodedata.normalize("NFD", w.lower()).replace("\u0300", "\u0301"))


def in_septuagint(w):
    """The word, accents and breathings as printed, is in the Septuagint."""
    if not _LXX_FORMS:
        _LXX_FORMS.update(lxx_form(x) for x in stream("greek")[0])
    return lxx_form(re.sub(r"[᾽’'ʼ]$", "", w)) in _LXX_FORMS


def spell(seg, kind):
    """A phrase not from the Bible: is each word a word? Greek: the dictionary and the Septuagint,
    misread ligatures set right (footnote_spell.py). Hebrew: hebrew_word(); a letter that should
    be final set right.
    Returns (ok, phrase, notes on what changed, words not found)."""
    parts = re.split(r"([\s־,.;:·()]+)", seg)
    if kind == "hebrew":
        why = []
        for i, p in enumerate(parts):
            w = re.sub(r"[^א-ת]", "", p)
            if w and not hebrew_word(w) and w[-1] in FINAL and hebrew_word(w[:-1] + FINAL[w[-1]]):
                parts[i] = p[::-1].replace(w[-1], FINAL[w[-1]], 1)[::-1]  # תקפ -> תקף
                why.append(f"{p} -> {parts[i]}")
        unknown = [p for p in parts if re.search(r"[א-ת]", p) and not hebrew_word(re.sub(r"[^א-ת]", "", p))]
        if unknown:
            return False, "".join(parts), [], unknown
        return True, "".join(parts), ["words found in the Hebrew Bible, the Targums or Strong's lexicon"
                                      + (": final letter " + ", ".join(why) if why else "")], []
    fixed, unknown = footnote_spell.fix(parts, in_septuagint)
    new = "".join(fixed.get(p, p) for p in parts)
    why = ["spelling checked against a Greek dictionary" + (": " + ", ".join(f"{a} -> {b}" for a, b in fixed.items()) if fixed else "")]
    return not unknown, new, why if not unknown or fixed else [], unknown


def check_hebrew(note):
    check_script(note, "hebrew")


def check_greek(note):
    check_script(note, "greek")


def resolve_ambiguous(ref, raw_refs, note=None, from_volume=False):
    """'1 Rois 18:38' written by the earlier expansion: Calmet's 1 Rois, or a modern 1 Kings (3 Rois)?
    The raw page; else, for a bare verse, the volume's own book; else the one reading where the
    verse exists; else the one whose Vulgate text is the Latin quoted with the note."""
    same = [r for r in raw_refs if r.chap == ref.chap and r.verses[:1] == ref.verses[:1] and r.name in ("Rois", "Paralipomènes")]
    if same:
        return same[0].book
    if from_volume:
        return ref.book
    m = re.match(r"([12]) Rois$", ref.book)
    if not m or note is None:
        return None
    other = f"{int(m.group(1)) + 2} Rois"
    cands = []
    for book in (ref.book, other):
        r = B.Ref(ref.start, ref.end, book, ref.name, ref.chap, ref.verses, ref.src)
        if B.exists(r):
            cands.append(r)
    if len(cands) == 1:
        return cands[0].book
    quotes = [q for q in map(latin_words, quotes_for(note) + re.findall(r"_([^_]{12,})_", note["text"])) if len(q) >= 3]
    scores = {r.book: max((len(q & latin_words(B.vulgate_text(r))) / len(q) for q in quotes), default=0) for r in cands}
    good = [b for b, sc in scores.items() if sc >= 0.5]
    return good[0] if len(good) == 1 else None


def render_bible(note, prev):
    """Write out a note that holds only Bible references; None if it holds anything else."""
    t = note["text"].strip()
    m = IBID.match(t)
    if m and prev:
        rest = t[m.end():]
        vm = VERSET_ONLY.match(rest)
        t = f"{prev.book} {prev.chap}. {vm.group(1)}." if vm else f"{prev.book} {rest}"
    vm = VERSET_ONLY.match(t)
    from_volume = bool(vm and note["chap"])
    if from_volume:
        t = f"{note['vol_book']} {note['chap']}. {vm.group(1)}."
    refs = B.find_refs(t)
    if not refs:
        return None
    raw_refs = B.find_refs(note["raw"]) if note["raw"] else []
    out, pos = [], 0
    lead = t[:refs[0].start]
    if lead.strip() and not SEE.fullmatch(lead):  # "Voyez Grotius sur …": not references alone
        return None
    see = bool(SEE.match(lead))
    for i, r in enumerate(refs):
        gap = t[pos:r.start] if i else ""
        if i:
            if COMPARE.match(gap):
                sep = " ; comparez "
            elif GAP.match(gap):
                sep = " ; "
            else:
                return None
            out.append(sep)
        book = r.book
        if r.name in B.AMBIGUOUS and "Reg" not in r.src and "Par" not in r.src:
            book = resolve_ambiguous(r, raw_refs, note, from_volume)
            if not book:
                note["flags"].append("ambiguous-name")
                return None
        if r.name == "Samuel":
            note["why"].append(f"{r.src.strip()} -> {book} (Vulgate name)")
        same = i and refs[i - 1].book == r.book and not out[-1].startswith(" ; comparez")
        out.append(r.render(with_book=False) if same else f"{book} {r.render(with_book=False)}")
        pos = r.end
        s = SEQ.match(t[pos:])  # "^" only matches at the start of the string
        if s:
            out.append(" et suivants")
            pos += s.end()
    tail = t[pos:]
    if not re.fullmatch(r"[\s.,;:]*(?:etc\.?)?[\s.]*", tail):
        return None
    text = ("Voyez " if see else "") + "".join(out) + (" etc." if "etc" in tail else ".")
    return text, refs[-1]


def local_stage(notes):
    prev = None
    for n in notes:
        n["proposed"], n["scan_why"] = n["text"], []
        if GLUED.search(n["text"]):
            n["flags"].append("garbled-reference")
        if UNSURE.search(n["text"]):
            n["flags"].append("uncertain")
            n["scan_why"].append("contains " + ", ".join(UNSURE.findall(n["text"])))
        r = None if "garbled-reference" in n["flags"] else render_bible(n, prev)
        if r:
            n["proposed"], prev = r
            n["done"] = True
        else:
            refs = B.find_refs(n["text"])
            prev = refs[-1] if refs else prev
            n["done"] = False
        n["prev"] = prev.render() if prev else ""
        if re.search(r"[א-ת]", n["proposed"]):
            check_hebrew(n)
        if re.search(r"[Ͱ-Ͽἀ-῿]", n["proposed"]):
            check_greek(n)


# ---- stage 2: the scans --------------------------------------------------------

def crop(volume, page):
    """The footnote area of a page: from the lowest rule to the last line of print; cached."""
    from PIL import Image
    out = CROPS / volume / f"{page}.png"
    if out.exists():
        return out
    src = DATA / volume / "source_images" / "commentaire" / f"{page}.png"
    if not src.exists():
        return None
    im = Image.open(src).convert("L")
    w, h = im.size
    px = im.load()
    x0, x1 = int(w * 0.12), int(w * 0.88)

    def dark(y):
        return sum(1 for x in range(x0, x1, 2) if px[x, y] < 110)

    # the lowest rule: a heading or a band of type higher up can look like one
    top = next((y for y in range(int(h * 0.97), int(h * 0.35), -1) if dark(y) > 0.55 * (x1 - x0) / 2), int(h * 0.55))
    bottom = next((y for y in range(h - 1, top, -1) if dark(y) > 3), h - 1)
    y0, y1 = max(0, top - 4), min(h, bottom + 12)
    cols = [x for x in range(w) if sum(1 for y in range(y0, y1, 2) if px[x, y] < 110) > 1]
    c = im.crop((max(0, cols[0] - 10), y0, min(w, cols[-1] + 10), y1) if cols else (0, y0, w, y1))
    scale = min(2.0, 1560 / c.width)  # as large as Claude reads it (about 1568 px across)
    if scale > 1.05:
        c = c.resize((int(c.width * scale), int(c.height * scale)), Image.LANCZOS)
    out.parent.mkdir(parents=True, exist_ok=True)
    c.save(out)
    return out


SCAN_PROMPT = """You are checking the transcription of footnotes in an 18th-century French Bible commentary (Dom Calmet, 1707), against the printed page.
Read the images {images} (the footnote area of each page; note 0101(a) is on page_0101.png). Then, for each footnote below, give its corrected text.

Rules:
- Correct only the Hebrew and the Greek, and fill in [UNCERTAIN HEBREW], [UNCERTAIN GREEK] and [ILLEGIBLE]. Change nothing else: keep the Latin and French exactly as given (spelling, abbreviations, punctuation).
- Hebrew and Greek: copy what is PRINTED, letter for letter (Greek with its accents and breathings; Hebrew with vowel points only if printed). 18th-century Greek type uses ligatures: στ (often misread as ς, σ or ι), ου (misread as ε, ω or ȣ), and others. Hebrew must be in logical (right-to-left reading) order.
- For [UNCERTAIN …]/[ILLEGIBLE]: replace the placeholder with what the page shows. If you can read it with confidence, write it plainly (no asterisk). Only where the page is not legible enough and you supply the most likely text from the context, put an asterisk right after each guessed word, e.g. "Imago, צלם* umbra". Never leave a placeholder: where the page cannot be read at all, write what Calmet most likely printed, from the passage the note is called from, the verse, and the usual form of such citations, with the asterisk. Corrections to existing Hebrew/Greek never get an asterisk.
- List every placeholder you filled in "fills", in order: {{"text": "<what replaced it, with its asterisk if guessed>", "read": true if read on the page with confidence, false if guessed}}.
- Small Hebrew type is easily misread (ו/ן/ז/י, ר/ד, ה/ח, ב/כ). Where the print is unclear and the REFERENCE has the word, write the reference's spelling: Calmet quotes the Hebrew of the verse commented as it stands.
- The reference text (Septuagint or Hebrew Bible) is given as a hint when the note quotes the verse commented; Calmet may quote another version (Aquila, Symmachus) or another passage, so the page wins.
- If a note is right, return its text unchanged.

Output ONLY a JSON array: [{{"id": "<id>", "text": "<corrected note>", "what": "<max 15 words: what you changed, or 'ok'>", "fills": [...]}}]

NOTES:
{items}"""


def scan_items(notes):
    out = []
    for n in notes:
        hint = ""
        vul, oshb, nr = B.BOOK.get(n["vol_book"], (None, None, None))
        if n["chap"] and n["verse"]:
            if "greek" in n["flags"] and nr:
                hint = B.lxx(nr).get((n["chap"], n["verse"]), "")
            elif ("hebrew" in n["flags"] or "uncertain" in n["flags"]) and oshb:
                ch = chapters_around(oshb, n["chap"])
                hint = " ".join(B.hebrew()[oshb].get((ch[1] if len(ch) > 1 else n["chap"], n["verse"]), []))
        ctx = (n["before"][-160:] + " ^{" + n["marker"] + "} " + n["after"][:60]).replace("\n", " ")
        out.append(f'id {n["id"]}\nTEXT: {n["proposed"]}\nWHY CHECKED: {"; ".join(n["scan_why"])}\n'
                   f'CALLED FROM: …{ctx}…' + (f"\nREFERENCE ({n['vol_book']} {n['chap']}:{n['verse']}): {hint}" if hint else ""))
    return "\n\n".join(out)


# ---- stage 3: writing abbreviations out ----------------------------------------

EXPAND_PROMPT = """You are editing the footnotes of an 18th-century French Bible commentary (Dom Calmet) for a modern edition.
Write out every abbreviated reference in full, in French. Keep everything else exactly as it is.

Rules:
- Bible references: Calmet's (Vulgate) book names: 1-4 Rois (1. Reg. = 1 Rois, 3. Reg. = 3 Rois), 1-2 Paralipomènes, 1-2 Esdras, Néhémie, Tobie, Ecclésiastique (Eccli.), Ecclésiaste (Eccle.), Cantique des cantiques, Sagesse, 1-2 Machabées, Psaumes (Vulgate numbering, unchanged). Written "Livre C:V" with arabic numbers ("Psal. CIII. 5." = "Psaumes 103:5"; "Prov. VIII. 22. 23." = "Proverbes 8:22-23"); several separated by " ; ". "Ibid. 26:15" = the book of the reference before it (PREVIOUS), written out. "℣. 17." alone = verse 17 of the chapter commented (CHAPTER).
- Earlier software wrote some references with modern names: "1 Samuel" = 1 Rois, "2 Samuel" = 2 Rois, "Chroniques" = Paralipomènes. When RAW is given it is the original printed note: use it to repair a garbled reference ("inGenèse 50actant." was "in Geneſ. Lactant.": a Roman-numeral misreading) and to tell 1 Rois from 3 Rois.
- Fathers, commentators, ancient versions, classical authors and their works: written out in French following the GLOSSARY ("Aug. l. 22. contra Faust. c. 10." = "saint Augustin, Contre Fauste, livre 22, chapitre 10"). Separate authors with " ; ". A work with no usual French title keeps its Latin title, written out.
- Do NOT translate quotations (Latin, Greek, Hebrew, poetry). Do NOT change any Hebrew or Greek character. Keep line breaks (\\n). Keep asterisks.
- If nothing is abbreviated, return the text unchanged.

Examples:
"Origen. homil. 1. in Genes. Basil. homil. 1. in Hexaëmer. Nazianz. Orat. 38. et 42." -> "Origène, Homélie 1 sur la Genèse ; saint Basile, Homélie 1 sur l'Hexaméron ; saint Grégoire de Nazianze, Discours 38 et 42."
"Thales apud Laërtium et Aristotel. l. 1 Metaphysic." -> "Thalès, dans Diogène Laërce ; et Aristote, Métaphysique, livre 1."
"Aqu. Κένωμα καὶ οὐδέν." -> "Aquila : κένωμα καὶ οὐδέν."
"Spiritus quem Graeci … consertum, etc. Plin. l. 2 c. 5." -> "Spiritus quem Graeci … consertum, etc. Pline, Histoire naturelle, livre 2, chapitre 5."
"Voi Deutéronome 32:11. Fag. Grot. et alii." -> "Voyez Deutéronome 32:11. Fagius ; Grotius ; et d'autres."

GLOSSARY:
{glossary}

Output ONLY a JSON array: [{{"id": "<id>", "text": "<note written out>"}}]

NOTES:
{items}"""


def glossary_for(notes):
    """The glossary lines a batch needs: the "Words" section, and every entry one of whose
    abbreviations begins with a word found in the notes (the whole glossary is ~3x a batch)."""
    import footnote_expand as X
    words = {X.key(w) for n in notes for w in re.findall(r"[A-Za-zÀ-ÿæœÆŒſ]+", n["proposed"] + " " + n.get("raw", ""))}
    words |= {w.replace("f", "s") for w in words}
    keep, section = [], None
    for line in GLOSSARY.splitlines():
        if line.startswith("## "):
            section = line
            keep.append(line)
        elif section and section.startswith("## Words"):
            keep.append(line)
    for sec, abbr, fr in X.entries():
        if sec == "words":
            continue
        firsts = [X.key(re.findall(r"[^\s.]+", a)[0]) for a in abbr.split(" / ") if a.strip()]
        if any(f in words or any(w.startswith(f) and len(f) >= 4 for w in words) for f in firsts):
            keep.append(f"{abbr} = {fr}")
    return "\n".join(l for i, l in enumerate(keep) if not (l.startswith("## ") and (i + 1 == len(keep) or keep[i + 1].startswith("## "))))


def expand_items(notes):
    out = []
    for n in notes:
        s = f'id {n["id"]}\nTEXT: {n["proposed"]}'
        if n["prev"]:
            s += f'\nPREVIOUS: {n["prev"]}'
        if re.search(r"(?:℣|verset)\s*\.?\s*\d", n["proposed"]):
            s += f'\nCHAPTER: {n["vol_book"]} {n["chap"]}'
        if "garbled-reference" in n["flags"] or re.search(r"\b(?:Samuel|Rois|Chroniques)\b", n["proposed"]):
            s += f'\nRAW: {n["raw"]}'
        out.append(s)
    return "\n\n".join(out)


def expand_local(notes):
    """Notes made of citations the glossary knows: written out by footnote_expand.py, no Claude."""
    import footnote_expand
    done = 0
    for n in notes:
        if n["done"] or "garbled-reference" in n["flags"] or not needs_expansion(n["proposed"]) \
                or re.search(r"\b(?:Samuel|Rois|Chroniques)\b", n["proposed"]):
            continue
        new = footnote_expand.expand(n["proposed"], ABBREV)
        if new and script_kept(n["proposed"], new):
            n["proposed"], n["done"] = new, True
            n["why"].append("abbreviations written out (footnote_expand.py)")
            done += 1
    print(f"  expand locally: {done} notes written out", flush=True)


def script_kept(old, new):
    """Every Hebrew and Greek passage of `new` is in `old` unchanged; one left out may only be a
    short title written out in French ("περὶ ἀρχῶν" -> "Des principes")."""
    a = HEB_SEG.findall(old) + [g.strip(" ,.;") for g in GRK_SEG.findall(old)]
    b = HEB_SEG.findall(new) + [g.strip(" ,.;") for g in GRK_SEG.findall(new)]
    if any(x not in a for x in b):
        return False
    return all(x in b or (not HEB_SEG.fullmatch(x) and len(x.split()) <= 3) for x in a)


def numbers(t):
    """The numbers a text holds, arabic or Roman (XXXII., cxiii)."""
    out = {int(x) for x in re.findall(r"\d+", t or "")}
    out |= {v for w in re.findall(r"\b[IVXLCivxlc]+\b", t or "") if (v := B.num(w))}
    return out


def numbers_kept(old, new, n):
    """Every number of the written-out note was in the note already (arabic or Roman), in the
    reference before it (Ibid.), in the printed note, or is the chapter commented (℣. 17. alone);
    a book's number before its name (1 Esdras) aside. A model that changes Josué 13:27 to 12:27,
    or adds a reference of its own, is caught here."""
    allowed = numbers(old) | numbers(n.get("prev")) | numbers(n.get("raw")) | {n.get("chap") or 0}
    book_no = {m.start() for m in re.finditer(r"\b[1-4](?= [A-ZÉ])", new)}
    return all(int(m.group()) in allowed or m.start() in book_no for m in re.finditer(r"\d+", new))


# ---- Claude ------------------------------------------------------------------------

USAGE = SCRIPTS / "cache" / "usage.log"
LIMIT_HIT = False  # set once Claude answers "session limit": no more calls this run
NO_CALLS = False   # --local


def answer_key(tag, *parts):
    """The cache key for this question; an answer Claude or agy's default model already gave to it counts too."""
    keys = [key(tag, m, *parts) for m in dict.fromkeys([EXPAND_MODEL, CLAUDE_EXPAND, "agy:default"])]
    return keys, keys[0]


AGY_PLAIN = "Answer directly, with text only: do not use any tool, do not run commands, do not read or write files.\n\n"


async def agy(prompt, sem):
    """claude() for the text-only calls, through agy (FOOTNOTE_BACKEND=agy). agy is an agent: some
    models reach for a tool (a shell command, which print mode refuses, leaving no answer), so it is
    told to answer in text and runs in an empty folder."""
    global LIMIT_HIT
    empty = Path(tempfile.gettempdir()) / "footnotes_agy"
    empty.mkdir(exist_ok=True)
    args = ["agy", "-p", AGY_PLAIN + prompt, "--print-timeout", "600s", "--disable-slash-commands", "--output-format", "json"]
    args += ["--model", AGY_MODEL] if AGY_MODEL else []
    async with sem:
        if LIMIT_HIT or NO_CALLS:
            return {}
        proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                                                    cwd=str(empty))
        try:  # agy does not always keep to --print-timeout
            out, err = await asyncio.wait_for(proc.communicate(), 660)
        except asyncio.TimeoutError:
            proc.kill()
            out, err = b"", b"timed out"
    try:
        d = json.loads(out.decode())
    except json.JSONDecodeError:
        d = {"status": "ERROR", "response": (err or out).decode()[:300]}
    text = str(d.get("response") or "")
    u = d.get("usage") or {}
    with USAGE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(dict(model=EXPAND_MODEL, image=False, cost=None, input_tokens=u.get("input_tokens", 0),
                                output_tokens=u.get("output_tokens", 0))) + "\n")
    if d.get("status") != "SUCCESS":
        if re.search(r"quota|limit|exhausted|429", text + err.decode(), re.I):
            if not LIMIT_HIT:
                print(f"  agy: {text[:100]}: no more calls this run; answers so far are cached", file=sys.stderr, flush=True)
            LIMIT_HIT = True
        else:
            print("  agy call failed:", text[:200], file=sys.stderr)
        return {}
    m = re.search(r"\[\s*\{.*\}\s*\]", text, re.S)
    try:
        return {str(r["id"]).removeprefix("id ").strip(): r for r in json.loads(m.group())}
    except Exception:
        print("  agy call failed:", text[:200], file=sys.stderr)
        return {}


async def claude(prompt, model, sem, image_dir=None):
    if BACKEND == "agy" and not image_dir:
        return await agy(prompt, sem)
    global LIMIT_HIT
    # --safe-mode: no CLAUDE.md, plugins, hooks or skills loaded into each call (half the overhead)
    args = ["claude", "-p", "--model", model, "--strict-mcp-config", "--disable-slash-commands",
            "--safe-mode", "--no-session-persistence", "--output-format", "json"]
    args += ["--tools", "Read", "--allowedTools", "Read", "--add-dir", str(image_dir)] if image_dir else ["--tools", ""]
    async with sem:
        if LIMIT_HIT or NO_CALLS:
            return {}
        proc = await asyncio.create_subprocess_exec(*args, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.PIPE, cwd=str(image_dir or SCRIPTS))
        out, err = await proc.communicate(prompt.encode())
    text = out.decode().strip()
    try:  # --output-format json: the answer, and what it cost (cache/usage.log)
        d = json.loads(text)
        text = str(d.get("result") or "")
        u = d.get("usage") or {}
        with USAGE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(dict(model=model, image=bool(image_dir), cost=d.get("total_cost_usd"),
                                    **{k: u.get(k, 0) for k in ("input_tokens", "cache_creation_input_tokens",
                                                                "cache_read_input_tokens", "output_tokens")})) + "\n")
    except (json.JSONDecodeError, AttributeError):
        pass
    if re.search(r"hit your (?:session |usage |weekly )?limit", text, re.I):
        if not LIMIT_HIT:
            print(f"  {text[:100]}: no more calls this run; answers so far are cached", file=sys.stderr, flush=True)
        LIMIT_HIT = True
        return {}
    m = re.search(r"\[\s*\{.*\}\s*\]", text, re.S)
    try:
        return {str(r["id"]).removeprefix("id ").strip(): r for r in json.loads(m.group())}
    except Exception:
        print("  call failed:", (err or out).decode()[:200], file=sys.stderr)
        return {}


def key(*parts):
    return hashlib.md5("\x00".join(map(str, parts)).encode()).hexdigest()


def check_fills(n, fills):
    """Read with confidence: no asterisk; guessed: an asterisk on each word. Held when the
    answer does not say which, or the asterisks do not match."""
    if len(fills) != len(UNSURE.findall(n["text"])):
        n["flags"].append("uncertain-fill-unclear")
        return
    for f in fills:
        t, read = str(f.get("text", "")), f.get("read")
        if read is True and "*" in t or read is False and not t.rstrip(".,;").endswith("*"):
            n["flags"].append("uncertain-fill-asterisk-wrong")
        if read is False:
            n["why"].append(f"guessed from context: {t}")
        elif read is True:
            n["why"].append(f"read on the scan: {t}")


def script_segments(t):
    return HEB_SEG.findall(t) + [g.strip(" ,.;") for g in GRK_SEG.findall(t)]


def checked(t, cache):
    """All the Hebrew and Greek of `t` has been read on the scan already (in an earlier run)."""
    segs = script_segments(t)
    return bool(segs) and all(cache.get(key("checked", s)) for s in segs)


PAGES_PER_CALL = 5  # one call reads several pages: the cost of a call is mostly its fixed part


async def scan_stage(volume, notes, cache, uncertain_only=False):
    todo = defaultdict(list)
    for n in notes:
        if not {"hebrew", "greek", "uncertain"} & set(n["flags"]):
            continue
        n["scan_key"] = key("scan4", SCAN_MODEL, n["page"], n["proposed"], n["scan_why"])
        if n["scan_key"] in cache:  # this note's own reading wins: it holds the corrections
            continue
        if "uncertain" not in n["flags"] and checked(n["proposed"], cache):
            n["flags"] = [f for f in n["flags"] if f not in ("hebrew", "greek")]  # read on the scan before
            del n["scan_key"]
            continue
        if uncertain_only and "uncertain" not in n["flags"]:
            continue  # --uncertain-only: Hebrew and Greek not found in the Bible wait
        todo[n["page"]].append(n)
    sem = asyncio.Semaphore(PARALLEL)
    jobs = []
    pages = [(p, ns, None if NO_CALLS else crop(volume, p)) for p, ns in todo.items()]
    pages = [x for x in pages if x[2]]
    for i in range(0, len(pages), PAGES_PER_CALL):
        group = pages[i:i + PAGES_PER_CALL]
        ns = [n for _, g, _ in group for n in g]
        images = ", ".join(img.name for _, _, img in group)
        jobs.append((ns, claude(SCAN_PROMPT.format(images=images, items=scan_items(ns)), SCAN_MODEL, sem, group[0][2].parent)))
    print(f"  scan: {sum(len(v) for v in todo.values())} notes on {len(todo)} pages to read"
          + (" (--local: left unread)" if NO_CALLS else ""), flush=True)
    for ns, ans in zip([j[0] for j in jobs], await asyncio.gather(*(j[1] for j in jobs))):
        for n in ns:
            if n["id"] in ans:
                a = ans[n["id"]]
                cache[n["scan_key"]] = {"text": a.get("text", ""), "what": a.get("what", ""), "fills": a.get("fills") or []}
    for n in notes:
        hit = cache.get(n.get("scan_key", ""))
        if not hit:
            if n.get("scan_key"):
                n["flags"].append("scan-unread")
            continue
        new = hit["text"].strip()
        for seg in script_segments(new):
            cache[key("checked", seg)] = True
        if new and new != n["proposed"]:
            if "*" in new and "uncertain" not in n["flags"] and "*" not in n["proposed"]:
                n["flags"].append("asterisk-outside-uncertain")
            n["why"].append(f"scan: {hit['what']}")
            n["proposed"] = new
        if "uncertain" in n["flags"]:
            check_fills(n, hit.get("fills") or [])
        if not UNSURE.search(n["proposed"]):
            had_hebrew = "hebrew" in n["flags"]
            n["flags"] = [f for f in n["flags"] if f not in ("hebrew", "greek", "uncertain")] + ["scanned"]
            if had_hebrew and new != n["text"]:  # the scan confirmed the print as is: trusted
                n["scan_why"] = []
                check_hebrew(n)
                if "hebrew" in n["flags"]:
                    n["flags"][n["flags"].index("hebrew")] = "hebrew-recheck"


# ---- stage 2b: context, without the scan ----------------------------------------

CONTEXT_PROMPT = """You are correcting the transcription of footnotes in an 18th-century French Bible commentary (Dom Calmet, 1707). There is no image: work from the passage the note is called from, the note itself, the Bible text given, and what you know of the authors Calmet cites (Fathers, rabbis, classical authors, the versions: Septuagint, Aquila, Symmachus, Theodotion, the Chaldee paraphrase).

Each note below has a PROBLEM found by an automatic check. For each, give the smallest edits that set it right:
- A misprinted Greek or Hebrew word whose intended form is clear (a misread letter, accent or ligature; a word of a passage you recognise): correct it, "guessed": false.
- [UNCERTAIN …] or [ILLEGIBLE], or a word that cannot be read and that you reconstruct from the context: replace it with the most likely text, "guessed": true. If you cannot say what it was, leave it.
- A Bible reference whose verse does not exist, or "1 Rois"/"2 Rois" that may mean Calmet's 1-2 Rois (1-2 Samuel) or the modern 1-2 Kings (= 3-4 Rois): decide from the passage and the Latin; an edit that changes a number you cannot confirm is "guessed": true.
- A word the check did not know but that is right (a rare form, a proper name, an Aramaic word, Calmet's spelling, a reading of another edition than the Septuagint text you know): no edit, and say so. Do not bring Calmet's text into line with the Septuagint or the Hebrew where his form is a real word.
Do not touch anything else: no modernising, no expanding abbreviations, no translating.

Output ONLY a JSON array, one object per note:
[{{"id": "<id>", "edits": [{{"from": "<exact text in the note>", "to": "<replacement>", "guessed": true|false}}], "resolved": true|false, "why": "<max 5 words>"}}]
"resolved": true only if after your edits nothing in the note is doubtful; false if something must wait for the printed page. Never delete an [UNCERTAIN …] or [ILLEGIBLE]: replace it with text, or leave it.

NOTES:
{items}"""

CONTEXT_FLAGS = {"hebrew", "greek", "uncertain", "ambiguous-name"}


def bad_refs(n):
    return [r for r in B.find_refs(n["proposed"]) if B.exists(r) is False]


def context_items(notes):
    out = []
    for n in notes:
        problems = list(n["scan_why"])
        hints = []
        vul, oshb, nr = B.BOOK.get(n["vol_book"], (None, None, None))
        if n["chap"] and n["verse"]:
            if vul:
                hints.append(f"VULGATE {n['vol_book']} {n['chap']}:{n['verse']}: " + B.vulgate(vul).get((n["chap"], n["verse"]), ""))
            if "greek" in n["flags"] and nr:
                hints.append("SEPTUAGINT: " + B.lxx(nr).get((n["chap"], n["verse"]), ""))
            if "hebrew" in n["flags"] and oshb:
                ch = chapters_around(oshb, n["chap"])
                hints.append("HEBREW: " + " ".join(B.hebrew()[oshb].get((ch[1] if len(ch) > 1 else n["chap"], n["verse"]), [])))
        if "ambiguous-name" in n["flags"]:
            problems.append("'Rois' reference: Calmet's numbering (1-2 Rois = 1-2 Samuel) or the modern one (1-2 Kings = 3-4 Rois)?")
            for r in B.find_refs(n["proposed"]):
                m = re.match(r"([12]) Rois$", r.book)
                if m:
                    for book in (r.book, f"{int(m.group(1)) + 2} Rois"):
                        x = B.Ref(r.start, r.end, book, r.name, r.chap, r.verses, r.src)
                        if B.exists(x):
                            hints.append(f"{x.render()}: {B.vulgate_text(x)[:200]}")
        for r in bad_refs(n):
            vg = B.vulgate(B.BOOK[r.book][0])
            problems.append(f"{r.render()} does not exist (the chapter has {max((v for c, v in vg if c == r.chap), default=0)} verses)")
        ctx = (n["before"][-220:] + " ^{" + n["marker"] + "} " + n["after"][:80]).replace("\n", " ")
        out.append(f'id {n["id"]}\nNOTE: {n["proposed"]}\nPROBLEM: {"; ".join(problems)}\nCALLED FROM: …{ctx}…'
                   + "".join("\n" + h for h in hints if h.strip()))
    return "\n\n".join(out)


def starred(t, src=""):
    """An asterisk after each word of guessed text (before its punctuation); not on the words
    already printed in `src`, the text it replaces."""
    kept = set(src.split())
    return re.sub(r"(\S*?[^\s.,;:!?»)\]])([.,;:!?»)\]]*)(?=\s|$)",
                  lambda m: m.group(0) if m.group(0) in kept or m.group(1) in kept else m.group(1) + "*" + m.group(2), t.replace("*", ""))


CONTEXT_BATCH = 75


async def context_stage(notes, cache):
    """The held notes (Hebrew and Greek not found, [UNCERTAIN …], references that do not exist or
    are ambiguous) set right from the context, without the scan; text only, a batch of notes a call,
    the answer only the edits. Guessed text gets "*"; what Claude cannot settle stays held."""
    todo = []
    for n in notes:
        if not (CONTEXT_FLAGS & set(n["flags"]) or bad_refs(n)):
            continue
        keys, n["ctx_key"] = answer_key("ctx1", n["proposed"], n["scan_why"], n["flags"], n["before"][-220:])
        n["ctx_key"] = next((k for k in keys if k in cache), n["ctx_key"])
        if n["ctx_key"] not in cache:
            todo.append(n)
    print(f"  context: {len(todo)} notes for {EXPAND_MODEL} to settle from the context" + (" (--local: left)" if NO_CALLS else ""), flush=True)
    sem = asyncio.Semaphore(PARALLEL)
    batches = [todo[i:i + CONTEXT_BATCH] for i in range(0, len(todo), CONTEXT_BATCH)]
    answers = await asyncio.gather(*(claude(CONTEXT_PROMPT.format(items=context_items(b)), EXPAND_MODEL, sem) for b in batches))
    for b, ans in zip(batches, answers):
        for n in b:
            if n["id"] in ans:
                a = ans[n["id"]]
                cache[n["ctx_key"]] = {"edits": a.get("edits") or [], "resolved": bool(a.get("resolved")), "why": a.get("why", "")}
    for n in notes:
        hit = cache.get(n.get("ctx_key", ""))
        if not hit:
            continue
        text, done = n["proposed"], []
        for e in hit["edits"]:
            src, to = str(e.get("from", "")), str(e.get("to", ""))
            if not src or src not in text or (UNSURE.search(src) and not to.strip()):
                hit = dict(hit, resolved=False)  # an edit that does not fit the note, or drops a placeholder: held
                continue
            to = starred(to, src) if e.get("guessed") else to.replace("*", "")
            text = text.replace(src, to, 1)
            done.append(f"{src} -> {to}")
        n["proposed"] = text
        n["why"].append(f"context: {hit['why']}" + (": " + ", ".join(done) if done else ""))
        if hit["resolved"] and not UNSURE.search(text):
            n["flags"] = [f for f in n["flags"] if f not in CONTEXT_FLAGS | {"scan-unread"}] + ["context"]


def tidy_expansion(old, new):
    """A list of authors written out one per line goes back on one line; a note that began with a
    capital keeps it ("Ambr." → "saint Ambroise" → "Saint Ambroise")."""
    if new and "\n" not in old:
        new = re.sub(r"\s*\n\s*", " ", new)
    if new[:1].islower() and old[:1].isupper():
        new = new[0].upper() + new[1:]
    return new


def script_chars(s):
    return len(re.findall(r"[Ͱ-Ͽἀ-῿֐-׿]", s))


async def expand_stage(notes, cache):
    todo = []
    for n in notes:
        if n["done"] or not (needs_expansion(n["proposed"]) or "garbled-reference" in n["flags"]
                             or re.search(r"\b(?:Samuel|Chroniques)\b", n["proposed"])):
            continue
        if {"scan-unread", "hebrew", "greek", "uncertain"} & set(n["flags"]):
            continue  # waiting for its scan: held at apply anyway, and the scan may change the text
        keys, n["exp_key"] = answer_key("exp2", n["proposed"], n["prev"], n["raw"] if "garbled-reference" in n["flags"] else "")
        n["exp_key"] = next((k for k in keys if k in cache), n["exp_key"])
        if n["exp_key"] not in cache:
            todo.append(n)
    print(f"  expand: {len(todo)} notes for {EXPAND_MODEL} to write out" + (" (--local: left as they are)" if NO_CALLS else ""), flush=True)
    sem = asyncio.Semaphore(PARALLEL)
    batches = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]
    answers = await asyncio.gather(*(claude(EXPAND_PROMPT.format(glossary=glossary_for(b), items=expand_items(b)), EXPAND_MODEL, sem)
                                     for b in batches))
    for b, ans in zip(batches, answers):
        for n in b:
            if n["id"] in ans:
                cache[n["exp_key"]] = ans[n["id"]].get("text", "")
    for n in notes:
        if "exp_key" not in n:
            continue
        new = tidy_expansion(n["proposed"], (cache.get(n["exp_key"]) or "").strip())
        if not new:
            n["flags"].append("expand-unread")
        elif not script_kept(n["proposed"], new) or script_chars(new) < script_chars(n["proposed"]) - 2:
            n["flags"].append("expand-changed-hebrew-or-greek")  # a Greek or Hebrew title translated away, too
        elif new.count("_") != n["proposed"].count("_"):
            n["flags"].append("expand-changed-italics")  # italics dropped or moved: held, the note as it was
            n["why"].append(f"written out, but the italics changed: {new[:200]}")
        elif not numbers_kept(n["proposed"], new, n):
            n["flags"].append("expand-changed-numbers")  # a number from nowhere: held, the note as it was
            n["why"].append(f"written out, but a number changed or added: {new[:200]}")
        elif new != n["proposed"]:
            n["proposed"] = new
            n["why"].append("abbreviations written out")


# ---- checks on the result -----------------------------------------------------------

LATIN_STOP = set("quia enim autem super eius ejus eorum illis illi ille haec hoc quod quae quam sicut omnes omnia omnis "
                 "tuum tuus tua suum suus sua meus mea meum nostra nobis vobis ipse ipsa ipsum erat erit sunt esse "
                 "dominus domini domino deus dei deum deo".split())


def latin_words(s):
    s = B.plain(s).replace("j", "i").replace("v", "u")
    return {w for w in re.findall(r"[a-z]{4,}", s) if w not in LATIN_STOP}


_VG_INDEX = {}


def vulgate_index():
    if not _VG_INDEX:
        for name, (vul, _, _) in B.BOOK.items():
            if name in ("Siracide",) or not vul or vul in {v[0] for v in _VG_INDEX.values()}:
                continue
            for (c, v), t in B.vulgate(vul).items():
                _VG_INDEX[(name, c, v)] = (vul, latin_words(t))
    return _VG_INDEX


def quotes_for(n):
    """The Latin a reference may be cited for: italics ending just before the call, or
    starting just after it (Calmet puts the call on either side)."""
    out = []
    m = re.search(r"_([^_]{12,})_[\s.,;:]{0,3}$", n["before"])
    if m:
        out.append(m.group(1))
    m = re.match(r"[\s.,;:]{0,3}_([^_]{12,})_", n["after"])
    if m:
        out.append(m.group(1))
    return out


DIGITS = {"1": "74", "7": "1", "3": "8", "8": "3", "5": "6", "6": "5", "0": "9", "9": "0", "4": "1"}


def misread(r):
    """The references `r` may be, misread: a Roman chapter one, four, five or ten off (XXII/XXIII, IV/VI,
    XV/XX), a verse with one digit taken for another (1/7, 3/8, 5/6, 0/9)."""
    chaps = {r.chap + d for d in (-10, -5, -4, -1, 1, 4, 5, 10)} | {r.chap}
    out = []
    for c in sorted(chaps):
        verse_sets = [r.verses] if c != r.chap else []
        for i, v in enumerate(r.verses):
            sv = str(v)
            for j, ch in enumerate(sv):
                for alt in DIGITS.get(ch, ""):
                    nv = int(sv[:j] + alt + sv[j + 1:] or 0)
                    if nv:
                        verse_sets.append(r.verses[:i] + [nv] + r.verses[i + 1:])
        out += [B.Ref(r.start, r.end, r.book, r.name, c, vs, r.src) for vs in verse_sets]
    return [x for x in out if x.chap > 0 and B.exists(x)]


def check_refs(n):
    refs = B.find_refs(n["proposed"])
    quotes = [q for q in map(latin_words, quotes_for(n) + re.findall(r"_([^_]{12,})_", n["text"])) if len(q) >= 4]
    for r in refs:
        if B.exists(r) is False:
            fits = [x for x in misread(r) if quotes and max(len(q & latin_words(B.vulgate_text(x))) / len(q) for q in quotes) >= 0.5]
            if len(fits) == 1:  # the Latin quoted says which verse it is
                n["why"].append(f"{r.render()} does not exist; the Latin quoted is {fits[0].render()}")
                n["proposed"] = n["proposed"][:r.start] + n["proposed"][r.start:r.end].replace(
                    r.render(with_book=False), fits[0].render(with_book=False), 1) + n["proposed"][r.end:]
                n["flags"].append("reference-corrected")
                return
            n["flags"].append("reference-not-in-vulgate")
            n["why"].append(f"{r.render()} does not exist in the Vulgate")
    if not quotes or not refs:
        return
    score = lambda q, ws: len(q & ws) / len(q)
    if any(score(q, latin_words(B.vulgate_text(r))) >= 0.4 for q in quotes for r in refs if B.exists(r)):
        return
    q = quotes[0] if len(quotes) == 1 else max(quotes, key=len)
    (name, c, v), (_, ws) = max(vulgate_index().items(), key=lambda kv: score(q, kv[1][1]))
    if score(q, ws) < 0.6:
        return
    found = f"{name} {c}:{v}"
    r = refs[0]
    # corrected only when it is surely the same reference misprinted: one reference, same
    # book, and not the next verse (Calmet often cites where a quotation begins)
    if len(refs) == 1 and r.book == name and not (r.chap == c and r.verses and abs(r.verses[0] - v) <= 1):
        n["why"].append(f"{r.render()} -> {found}: the Latin quoted («{' '.join(sorted(q))[:60]}») is {found}")
        n["proposed"] = n["proposed"][:r.start] + found + n["proposed"][r.end:]
        n["flags"] = [f for f in n["flags"] if f != "reference-not-in-vulgate"] + ["reference-corrected"]
    elif not (r.book == name and r.chap == c):
        n["flags"].append("reference-mismatch")
        n["why"].append(f"the Latin next to the call is {found}, not {', '.join(x.render() for x in refs)}")


LATIN_ONLY = set("est quod qui quem quae quam cum sunt enim sed nisi ut autem ejus eius non erat sicut quia ita nec atque".split())


def break_list(t):
    """A list of three or more references, with no quotation in it: one per line."""
    parts = re.split(r" ;\s+", t)
    # every item after the first starts like a reference: an author ("Origène", "saint Basile")
    # or a book; a lower-case start is a quotation going on, a number a same-book verse
    if not all(re.match(r"(?:saint|sainte|et)?\s*[A-ZÀ-ÝŒ]", x) for x in parts[1:]):
        return t
    if (len(parts) < 3 or HEB_SEG.search(t) or GRK_SEG.search(t) or "\n" in t.replace(" ;\n", "")
            or any(w in LATIN_ONLY for w in re.findall(r"[a-zæœ]+", t))):
        return t
    return " ;\n".join(parts)


# ---- commands -------------------------------------------------------------------------

def page_range(argv):
    m = next((a for a in argv if re.fullmatch(r"\d+-\d+", a)), None)
    return tuple(map(int, m.split("-"))) if m else (0, 99999)


async def run(volume, lo, hi, local_only, scan=True, uncertain_only=False, context=False):
    notes = load_volume(volume, lo, hi)
    print(f"{volume}: {len(notes)} footnotes", flush=True)
    local_stage(notes)
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    global NO_CALLS
    # --local: only Claude's answers already cached, no new call; --no-scan: the same, for the scans only
    NO_CALLS = local_only or not scan
    await scan_stage(volume, notes, cache, uncertain_only)
    NO_CALLS = local_only
    if context and not LIMIT_HIT:
        await context_stage(notes, cache)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    expand_local(notes)  # after the scan: its cache keys are made from the text before
    if not LIMIT_HIT:
        await expand_stage(notes, cache)
        CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    for n in notes:
        check_refs(n)
        n["proposed"] = break_list(re.sub(r"[ \t]+", " ", n["proposed"]).strip())
    keep = [{k: n[k] for k in ("id", "page", "marker", "text", "proposed", "why", "flags")}
            for n in notes if n["proposed"] != n["text"] or n["flags"]]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{volume}.json"
    summary = dict(notes=len(notes), changed=sum(n["proposed"] != n["text"] for n in notes),
                   flags=dict(Counter(f for n in notes for f in n["flags"])))
    if out.exists():  # a run over some pages keeps what earlier runs found on the others
        older = [n for n in json.loads(out.read_text(encoding="utf-8"))["notes"] if not lo <= int(n["page"][5:9]) <= hi]
        keep = sorted(older + keep, key=lambda n: n["page"])
    out.write_text(json.dumps(dict(summary=summary, notes=keep), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  {summary}\nwrote {out}")


HOLD = {"hebrew", "hebrew-recheck", "uncertain-fill-unclear", "uncertain-fill-asterisk-wrong", "greek", "uncertain", "scan-unread", "expand-unread", "expand-changed-hebrew-or-greek", "expand-changed-numbers", "expand-changed-italics",
        "asterisk-outside-uncertain", "ambiguous-name", "reference-not-in-vulgate", "reference-mismatch"}


def apply(volume, lo, hi, hold=True):
    """Write the proposals into normalized/. Notes whose flags need a look are left (listed),
    unless hold is False (--no-hold)."""
    data = json.loads((OUT_DIR / f"{volume}.json").read_text(encoding="utf-8"))
    by_page = defaultdict(dict)
    held = []
    for n in data["notes"]:
        if not lo <= int(n["page"][5:9]) <= hi or n["proposed"] == n["text"]:
            continue
        if hold and HOLD & set(n["flags"]):
            held.append(n["id"])
            continue
        by_page[n["page"]][n["marker"]] = n
    changed = 0
    for page, ns in sorted(by_page.items()):
        p = DATA / volume / "normalized" / f"{page}.json"
        raw = p.read_text(encoding="utf-8")
        d = json.loads(raw)
        for fn in d.get("footnotes") or []:
            n = ns.get(fn["marker"])
            if n and fn["text"] == n["text"]:
                fn["text"] = n["proposed"]
                changed += 1
        p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + ("\n" if raw.endswith("\n") else ""), encoding="utf-8")
    print(f"{volume}: {changed} notes written; {len(held)} held for review: {' '.join(held)}")


def held():
    """Every note still held, from all the reports, in one list: docs/footnotes/held.json, by volume
    and page, with why (the flags) and the text as it stands. What the scans are for."""
    out, counts = [], Counter()
    for f in sorted(OUT_DIR.glob("[0-9]*.json")):
        for n in json.loads(f.read_text(encoding="utf-8"))["notes"]:
            h = sorted(HOLD & set(n["flags"]))
            if h:
                out.append(dict(volume=f.stem, page=n["page"], marker=n["marker"], flags=h, text=n["proposed"]))
                counts[f.stem] += 1
    (OUT_DIR / "held.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    flags = Counter(x for n in out for x in n["flags"] if x != "scan-unread")
    print(f"{len(out)} notes held on {len({(n['volume'], n['page']) for n in out})} pages -> {OUT_DIR / 'held.json'}")
    print("  by volume:", dict(counts))
    print("  by flag:", dict(flags.most_common()))


if __name__ == "__main__":
    if sys.argv[1:] == ["held"]:
        held()
        sys.exit()
    cmd, *rest = sys.argv[1:]
    lo, hi = page_range(rest)
    volumes = volumes_of([a for a in rest if not a.startswith("--") and not re.fullmatch(r"\d+-\d+", a)])
    for i, volume in enumerate(volumes, 1):
        if len(volumes) > 1:
            print(f"[{i}/{len(volumes)}]", end=" ", flush=True)
        if cmd == "run":
            asyncio.run(run(volume, lo, hi, "--local" in rest, scan="--no-scan" not in rest, uncertain_only="--uncertain-only" in rest,
                            context="--context" in rest))
            if "--apply" in rest:
                apply(volume, lo, hi, hold=True)
        elif cmd == "apply":
            apply(volume, lo, hi, hold="--no-hold" not in rest)
