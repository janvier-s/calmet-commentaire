"""Calmet's commentary: locate the pages, then sew the lemmata back together.

Copied from Lectio/build/booklet/calmet.py for the website export. Pages come
from normalized/ only: it is the definitive text, so there is no choosing
between transcriptions and no per-page overrides.
"""

import functools
import json
import re
import unicodedata
from pathlib import Path

from paths import BOOKS, VUL, load, pages as volume_pages

STRAY = re.compile(r"\^\{[^}]*\}")
# The apparatus is transcribed with Anglo chapter:verse references; the
# house style is the French comma (GUIDE.md).
CHAPTER_VERSE = re.compile(r"(\d)\s*:\s*(\d)")
ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
GREEK_FIX = {"р": "ρ", "д": "δ", "с": "ς", "е": "ε", "о": "ο", "у": "υ"}
GREEK_TABLE = str.maketrans(GREEK_FIX)


LATIN_NAMES = Path(__file__).resolve().parent / "latin_names.txt"


@functools.lru_cache(maxsize=None)
def _fold(w):
    w = w.lower().replace("æ", "ae").replace("œ", "ae")
    w = unicodedata.normalize("NFD", w).encode("ascii", "ignore").decode()
    # spellings that vary between Calmet and the Vulgate: cœli / cæli, eius / ejus, Noe / Noë
    return w.replace("oe", "ae").replace("j", "i")


@functools.lru_cache(maxsize=None)
def proper_nouns():
    """Words the Vulgate writes with a capital in most of their mid-sentence uses
    (Deus, Dominus, Abraham), keyed by their unaccented lower case."""
    caps, seen = {}, {}
    for f in VUL.glob("*.json"):
        for ch in json.loads(f.read_text(encoding="utf-8"))["chapters"]:
            for v in ch["verses"]:
                for m in re.finditer(r"(?<![.;:?!]\s)(?<!^)\b[^\W\d_]+", v["text"]):
                    k = _fold(m.group())
                    seen[k] = seen.get(k, 0) + 1
                    caps[k] = caps.get(k, 0) + m.group()[0].isupper()
    vulgate_words.cache = set(seen)
    # names Calmet spells otherwise than the Vulgate (Canaan, Sehir), added during review
    lines = LATIN_NAMES.read_text(encoding="utf-8").splitlines() if LATIN_NAMES.exists() else []
    names = {_fold(w) for line in lines if not line.startswith("#") for w in line.split()}
    vulgate_words.cache |= names
    return {k for k, n in seen.items() if caps.get(k, 0) * 2 > n} | names


def vulgate_words():
    """Every word of the Vulgate (unaccented lower case), first words of sentences aside."""
    proper_nouns()
    return vulgate_words.cache


def latin_case(s):
    """The lemma is printed in capitals: lower case, but for the Vulgate's proper nouns.
    The site sets it in small caps with a capital first letter."""
    if not s or re.search(r"[a-zæœ]", STRAY.sub("", s)):  # already in mixed case
        return s
    nouns = proper_nouns()
    return re.sub(r"[^\W\d_]+", lambda m: m.group().capitalize() if _fold(m.group()) in nouns
                  else m.group().lower(), s)


def greek_fix(s):
    """Undo Cyrillic look-alikes in the transcribed Greek.

    Cyrillic letters only occur in Greek runs, so French text is untouched.
    """
    return (s or "").translate(GREEK_TABLE)


def roman(s):
    """The chapter number from a running head like "CHAPITRE X.".

    Match the whole heading, never just its Roman letters: "COMMENTAIRE."
    reduces to CMMI, which is a perfectly good numeral and would silently
    reset the chapter on every page that carries that head.
    """
    m = re.match(r"\s*CHAPITRE\s+([IVXLCDM]+|PREMIER)\b", (s or "").upper())
    if not m:
        return None
    s = m.group(1)
    if s == "PREMIER":
        return 1
    total = prev = 0
    for ch in reversed(s):
        v = ROMAN[ch]
        total += -v if v < prev else v
        prev = max(prev, v)
    return total


@functools.lru_cache(maxsize=None)
def pages(book):
    """Every commentary page of the book, in order, tagged with its chapter.

    Calmet prints the chapter number only on the page where the chapter opens,
    so the chapter of every other page is carried forward, across volumes too
    (the Psalms are in three).
    """
    out, decisions, chapter = [], [], None
    for volume in BOOKS[book]["studium"]:
        for p in volume_pages(volume):
            stem = p.stem
            try:
                page = load(p)
            except json.JSONDecodeError:
                decisions.append(dict(page=stem, chosen="normalized", reason="malformed"))
                continue
            decisions.append(dict(page=stem, chosen="normalized"))
            ch = page.get("chapter_number") or roman(page.get("chapter_title"))
            out.append((stem, chapter, ch or chapter, page))
            if ch:
                chapter = ch
    return out, decisions


def verse_number(ref):
    """The verse a reference names: "℣. 16." -> 16, and the Roman "℣. I." -> 1,
    which Calmet uses for the first note of several books."""
    s = str(ref or "")
    m = re.search(r"(\d+)", s)
    if m:
        return int(m.group(1))
    m = re.fullmatch(r"\W*(?:℣\W*)?([IVXLC]+)\W*", s.upper())
    if not m:
        return None
    total = prev = 0
    for ch in reversed(m.group(1)):
        v = ROMAN[ch]
        total += -v if v < prev else v
        prev = max(prev, v)
    return total


def _words(s):
    return re.findall(r"[^\W\d_]+", s, re.UNICODE)


# what follows a hyphen in a compound, not the rest of a broken word
COMPOUND = re.compile(r"(?:à|dire|Christ|là|ci|même|mêmes|il|ils|elle|elles|on|vous|nous|je|tu|t|y|en)\b")


def join_seam(tail, txt, mode, stub):
    """tail and the text overleaf as one, by infer_join's mode."""
    if mode == "hyphen":
        txt = txt.split(maxsplit=1)[1] if " " in txt.strip() else ""
    if not tail.strip():
        return txt
    if mode == "mend":
        return tail.rstrip()[:-1] + " " + txt
    if mode == "splice":
        return tail.rstrip()[:-1] + txt
    if mode == "keep" or re.match(r"[,;:.!?]", txt):
        return tail.rstrip() + txt
    if mode == "refrag":
        kept = tail.rstrip()[:-1]
        return kept[:len(kept) - len(stub)].rstrip() + " " + txt
    return tail.rstrip() + " " + txt


def infer_join(prev, nxt):
    """How the fragment `nxt` attaches to the tail of `prev`.

    Calmet's text runs straight across the page turn, and the transcription
    closes each page as though it were a sentence, so the seam has to be read
    rather than assumed. Four shapes occur; see GUIDE.md.
    """
    prev, nxt = prev.rstrip(), nxt.lstrip()
    if not prev or not nxt:
        return "flow", None
    # The transcription sometimes keeps the printer's hyphen instead of
    # completing the word: "nulle compa-" then "raison entre ces deux choses".
    if prev.endswith("-"):
        # a compound broken at its own hyphen keeps it: "c'est-" / "à-dire"
        if COMPOUND.match(nxt):
            return "keep", None
        # ...unless the next page reprints the whole word ("la con-" / "concupiscence"):
        # then the fragment is dropped instead of doubled.
        frag, nw = _words(prev[:-1]), _words(nxt)
        if frag and nw and len(nw[0]) > len(frag[-1]) and nw[0].lower().startswith(frag[-1].lower()):
            return "refrag", frag[-1]
        return "splice", None
    pw, nw = _words(prev), _words(nxt)
    # the printer broke a word across the turn and both halves were completed
    # Two letters is enough ("trouvé" / "vé"): what identifies this case is
    # that the fragment repeats the tail of the word, not how long it is.
    # The whole word can repeat too ("en ce sens" / "sens dans l'ancien
    # Testament"), which is the same accident seen from the other side.
    if pw and nw and len(nw[0]) >= 2 and pw[-1].lower().endswith(nw[0].lower()):
        return "hyphen", nxt.split(maxsplit=1)[0]
    if nxt[0].islower():
        # a sentence cut in two, with a period the printer never set
        return ("mend", None) if prev.endswith(".") else ("flow", None)
    return ("para", None) if prev.endswith((".", "!", "?", "»")) else ("flow", None)


@functools.lru_cache(maxsize=None)
def apparatus(book):
    """Calmet's apparatus, keyed by page: the letters restart on every page,
    so a marker only means something together with the page it sits on.
    The whole book's, built once (notes() is called chapter by chapter)."""
    available = {}
    for stem, before, after, page in pages(book)[0]:
        for f in page.get("footnotes") or []:
            marker = re.sub(r"[^a-z]", "", str(f.get("marker") or "").lower())
            available.setdefault(
                f"{stem}-{marker}",
                _balance(CHAPTER_VERSE.sub(
                    r"\1,\2",
                    STRAY.sub("", greek_fix(str(f.get("text") or "").strip())))))
    return available


def notes(book, chapter, first, last, joins=None):
    """Calmet's lemmata for the pericope, with the page seams sewn up."""
    page_list, decisions = pages(book)

    def bind(s, pg):
        # The apparatus restarts at (a) on every page, so a marker only means
        # something together with the page it was printed on.
        # A few markers lose their closing paren in transcription (`^{(b}`),
        # so the paren is optional; otherwise they survive into the page.
        return re.sub(r"\^\{\((\w)\)?\}",
                      lambda m: f"^{{fn:{pg}-{m.group(1)}}}", s or "")

    # Every commentary block of this chapter, in reading order.
    blocks = []
    for stem, before, after, page in page_list:
        # each block carries its chapter (assign_chapters.py)
        for b in (c for c in page.get("commentary") or [] if c.get("chapter") == chapter):
            blocks.append(dict(page=stem, cid=b.get("commentary_id") or b.get("comment_id"),
                               verse=verse_number(b.get("verse_ref")),
                               latin=bind((b.get("latin_quote") or "").strip(),
                                          stem) or None,
                               lemma=(b.get("french_translation") or "").strip() or None,
                               text=(b.get("french_commentary") or "").strip()))

    out, seams, cur = [], [], None
    for b in blocks:
        # A lemma or translation the page turn cut goes on in the same field overleaf, in a block
        # with no verse of its own (seam_join.py), before the note's comment has begun.
        # A Latin lemma goes on only when the one before is still open (no full stop, no
        # translation yet): otherwise it is a second lemma of the verse (ARIARATHI. ‖ ARSACI.).
        open_latin = (not cur["french_lemma"] and cur["latin_lemma"]
                      and not re.search(r"[.!?]\W*$", STRAY.sub("", cur["latin_lemma"]))) if cur else False
        if (cur is not None and b["verse"] in (None, cur["verse"]) and cur["paragraphs"] == [""]
                and (open_latin if b["latin"] else b["lemma"])):
            if b["latin"]:
                cur["latin_lemma"] = join_seam(cur["latin_lemma"] or "", b["latin"],
                                               *infer_join(cur["latin_lemma"] or "", b["latin"]))
            if b["lemma"]:
                fr = bind(b["lemma"], b["page"])
                cur["french_lemma"] = join_seam(cur["french_lemma"] or "", fr,
                                                *infer_join(cur["french_lemma"] or "", fr))
            cur["paragraphs"] = [bind(b["text"], b["page"])]
            cur["pages"].append(b["page"])
            continue
        # The transcription often tags the top of a page with the verse it
        # continues; with no lemma of its own that is a continuation, not a new note.
        if (b["verse"] is not None and cur is not None and b["verse"] == cur["verse"]
                and not b["latin"] and not b["lemma"]):
            b = dict(b, verse=None)
        if b["verse"] is not None:
            cur = dict(verse=b["verse"], sub=False, latin_lemma=b["latin"],
                       french_lemma=bind(b["lemma"], b["page"]),
                       paragraphs=[bind(b["text"], b["page"])], pages=[b["page"]])
            out.append(cur)
        elif cur is None:
            continue                      # tail of a lemma that began earlier
        else:
            # A block with no verse_ref but its own Latin lemma is a second
            # lemma hanging under the same verse (Calmet's "In stabulum").
            if b["latin"]:
                cur = dict(verse=cur["verse"], sub=True, latin_lemma=b["latin"],
                           french_lemma=bind(b["lemma"], b["page"]),
                           paragraphs=[bind(b["text"], b["page"])], pages=[b["page"]])
                out.append(cur)
                continue
            # A lemma can open with no commentary at all, when the page
            # breaks inside Calmet's own French rendering of the Latin: the
            # word to match is then in the lemma, not in the empty paragraph.
            tail = cur["paragraphs"][-1]
            probe = tail if tail.strip() else re.sub(r"[_*]", "", cur["french_lemma"] or "")
            mode, stub = infer_join(probe, b["text"])
            key = f"{cur['pages'][-1]}>{b['page']}"
            if joins and key in joins:
                mode = joins[key]
            seams.append(dict(seam=key, verse=cur["verse"], mode=mode,
                              before=probe[-58:], after=b["text"][:58]))
            txt = bind(b["text"], b["page"])
            if mode == "para" and tail.strip():
                cur["paragraphs"].append(txt)
            else:
                cur["paragraphs"][-1] = join_seam(tail, txt, mode, stub)
            cur["pages"].append(b["page"])

    out = [n for n in out if first <= n["verse"] <= last]
    seams = [j for j in seams if first <= j["verse"] <= last]

    available = apparatus(book)

    # Number across the whole pericope, not per note: the apparatus prints
    # once under the section, so [1] must mean the same thing throughout.
    # A marker whose note is absent from the page is dropped rather than
    # printed, which would leave the reader a number pointing at nothing.
    order, missing = [], []

    def number(m):
        key = m.group(1)
        if key not in available:
            if key not in missing:
                missing.append(key)
            return ""
        if key not in order:
            order.append(key)
        return f"[{order.index(key) + 1}]"

    notes_out = [_flatten(n, number) for n in out]
    # Only the pages this pericope actually reads. `pages()` decides for the
    # whole book -- 626 of them for Matthew -- and handing all of that to the
    # review log buried each Sunday's three real problems under the other
    # ninety-odd, which is the same as reporting nothing.
    used = {pg for n in out for pg in n["pages"]}
    return dict(notes=notes_out, joins=seams,
                pages_used=sorted(used),
                footnotes=[dict(key=k, n=i + 1, text=available[k])
                           for i, k in enumerate(order)],
                decisions=[d for d in decisions if d["page"] in used],
                missing_footnotes=sorted(missing))


def _flatten(note, number):
    """One note as the booklet needs it: paragraphs joined, markers numbered.

    The apparatus markers are page-scoped keys by this point
    (`^{fn:page_0438-a}`). `number` turns each into its ordinal within the
    section, or removes it when the page carries no such note -- a number
    pointing at nothing is worse than no marker at all.
    """
    text = "\n\n".join(p for p in note["paragraphs"] if p.strip())
    text = re.sub(r"\^\{fn:([\w-]+)\}", number, text)
    lemma = re.sub(r"\^\{fn:([\w-]+)\}", number, note["french_lemma"] or "")
    latin = re.sub(r"\^\{fn:([\w-]+)\}", number, note["latin_lemma"] or "")
    # Anything still in `^{...}` is transcription noise, not an apparatus
    # marker, and would print as-is.
    text, lemma, latin = (STRAY.sub("", x) for x in (text, lemma, latin))
    # The site sets the translation in italic. Underscores left in it mark partial
    # italics (Calmet's translation, then his remark in roman) and are kept for the site.
    lemma = lemma.strip()
    return dict(verse=note["verse"], sub=note["sub"],
                latin_lemma=latin_case(latin.replace("_", "").strip()) or None,
                lemma=lemma or None,
                text=_balance(greek_fix(text)))


def _balance(text):
    """Close an italic run the page break left open.

    A lemma cut across a turn keeps its opening `_` and never sees the
    closing one ("_Un chef de la Synago-"). The template splits on the
    delimiter, so an odd count would italicise everything after it.
    """
    return text + "_" if text.count("_") % 2 else text
