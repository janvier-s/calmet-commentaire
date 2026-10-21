"""Bible references in Calmet's footnotes: parse, write out in full, check.

Names are Calmet's (the Vulgate's): 1-4 Rois, 1-2 Paralipomènes, Ecclésiastique, 1-2
Machabées; psalms in Vulgate numbering. A reference is written "Livre C:V" ("Psaumes 103:5",
"Genèse 1:16-17", "Isaïe 24:18, 21"), several separated by " ; ".

Also gives the texts to check against: the Clementine Vulgate (paths.VUL), the Hebrew
(Open Scriptures, cache/refs/hebrew_oshb.json) and the Septuagint (getbible, cache/refs/lxx/).
"""
import json, re, unicodedata
from functools import lru_cache

from paths import SCRIPTS, VUL

REFS = SCRIPTS / "cache" / "refs"

# canonical name, Vulgate file, Hebrew book (OSHB), LXX book number, abbreviations
# (lower case, no accents, no ſ, no full stop). A number before the name is read separately.
_TABLE = [
    ("Genèse", "genesis", "Genesis", 1, "gen genes genese genesis genef gn"),
    ("Exode", "exodus", "Exodus", 2, "ex exod exode exo"),
    ("Lévitique", "leviticus", "Leviticus", 3, "lev levit levitique laevit laevitique"),
    ("Nombres", "numbers", "Numbers", 4, "num numer nombres nomb"),
    ("Deutéronome", "deuteronomy", "Deuteronomy", 5, "deut deuter deuteronome deu dt"),
    ("Josué", "josue", "Joshua", 6, "jos josue josuae iosuae iosue"),
    ("Juges", "judges", "Judges", 7, "judic juges judicum iudic iudicum"),
    ("Ruth", "ruth", "Ruth", 8, "ruth"),
    ("Rois", None, None, None, "reg regum rois"),                 # numbered 1-4
    ("Paralipomènes", None, None, None, "par paral paralip paralipom paralipomenes"),
    ("Esdras", None, None, None, "esdr esd esdras"),                # 1-2
    ("Néhémie", "2-esdras", "Nehemiah", 16, "nehem neh nehemie"),
    ("Tobie", "tobias", None, 69, "tob tobie tobiae"),
    ("Judith", "judith", None, 70, "judith judit"),
    ("Esther", "esther", "Esther", 17, "esth esther"),
    ("Job", "job", "Job", 18, "job iob"),
    ("Psaumes", "psalms", "Psalms", 19, "ps psal psalm pseaume psaume psaumes pf pfal"),
    ("Proverbes", "proverbs", "Proverbs", 20, "prov proverb proverbes"),
    ("Ecclésiaste", "ecclesiastes", "Ecclesiastes", 21, "eccle eccles ecclesiaste eccl ecclef"),
    ("Cantique des cantiques", "canticle-of-canticles", "Song of Solomon", 22, "cant cantic cantique cantiques"),
    ("Sagesse", "wisdom", None, 73, "sap sagesse"),
    ("Ecclésiastique", "ecclesiasticus", None, 74, "eccli ecclesiastique ecclesiastici"),
    ("Isaïe", "isaie", "Isaiah", 23, "is isa isai isaie esai ysai ysaie"),
    ("Jérémie", "jeremie", "Jeremiah", 24, "jer jerem jeremie ier ierem ieremie"),
    ("Lamentations", "lamentations", "Lamentations", 25, "thren lament lamentations"),
    ("Baruch", "baruch", None, 75, "bar baruc baruch"),
    ("Ézéchiel", "ezechiel", "Ezekiel", 26, "ez ezech ezechiel exech"),
    ("Daniel", "daniel", "Daniel", 27, "dan daniel"),
    ("Osée", "osee", "Hosea", 28, "os osee"),
    ("Joël", "joel", "Joel", 29, "joel"),
    ("Amos", "amos", "Amos", 30, "amos"),
    ("Abdias", "abdias", "Obadiah", 31, "abd abdias"),
    ("Jonas", "jonas", "Jonah", 32, "jon jonas"),
    ("Michée", "micheas", "Micah", 33, "mich michee"),
    ("Nahum", "nahum", "Nahum", 34, "nah nahum"),
    ("Habacuc", "habacuc", "Habakkuk", 35, "hab habac abac habacuc"),
    ("Sophonie", "sophonias", "Zephaniah", 36, "soph sophon sophonie"),
    ("Aggée", "aggeus", "Haggai", 37, "agg aggee"),
    ("Zacharie", "zacharias", "Zechariah", 38, "zach zachar zacharie"),
    ("Malachie", "malachie", "Malachi", 39, "mal malach malac malachie"),
    ("Machabées", None, None, None, "macc maccab mach machab machabees maccabees"),  # 1-2
    ("Matthieu", "matthew", None, None, "matt matth mat matthieu"),
    ("Marc", "mark", None, None, "marc"),
    ("Luc", "luke", None, None, "luc"),
    ("Jean", "john", None, None, "joan johan joann jean"),          # with a number: the epistles
    ("Actes", "acts", None, None, "act actes"),
    ("Romains", "romans", None, None, "rom romains"),
    ("Corinthiens", None, None, None, "cor corinth corinthiens"),
    ("Galates", "galatians", None, None, "gal galat galates"),
    ("Éphésiens", "ephesians", None, None, "eph ephes ephef ephesiens"),
    ("Philippiens", "philippians", None, None, "philip philipp philippiens"),
    ("Colossiens", "colossians", None, None, "col coloss colloss colossiens coloff"),
    ("Thessaloniciens", None, None, None, "thess thessal thessaloniciens"),
    ("Timothée", None, None, None, "tim timot timoth timothee"),
    ("Tite", "titus", None, None, "tit tite"),
    ("Philémon", "philemon", None, None, "philem philemon"),
    ("Hébreux", "hebrews", None, None, "hebr heb hebreux"),
    ("Jacques", "james", None, None, "jac jacob jacobi jacques"),
    ("Pierre", None, None, None, "pet petr petri pierre"),
    ("Jude", "jude", None, None, "jude judae"),
    ("Apocalypse", "apocalypse", None, None, "apoc apocal apocalyps apocalypse"),
    # the earlier expansion's modern names: Samuel = Rois 1-2, Chroniques = Paralipomènes
    ("Samuel", None, None, None, "samuel sam"),
    ("Chroniques", None, None, None, "chroniques chron"),
    ("Siracide", "ecclesiasticus", None, 74, "siracide sir"),
]
NUMBERED = {  # name -> {n: (canonical, vul, oshb, lxx)}
    "Rois": {1: ("1 Rois", "1-kings", "I Samuel", 9), 2: ("2 Rois", "2-kings", "II Samuel", 10),
             3: ("3 Rois", "3-kings", "I Kings", 11), 4: ("4 Rois", "4-kings", "II Kings", 12)},
    "Samuel": {1: ("1 Rois", "1-kings", "I Samuel", 9), 2: ("2 Rois", "2-kings", "II Samuel", 10)},
    "Paralipomènes": {1: ("1 Paralipomènes", "1-paralipomenon", "I Chronicles", 13),
                      2: ("2 Paralipomènes", "2-paralipomenon", "II Chronicles", 14)},
    "Chroniques": {1: ("1 Paralipomènes", "1-paralipomenon", "I Chronicles", 13),
                   2: ("2 Paralipomènes", "2-paralipomenon", "II Chronicles", 14)},
    "Esdras": {1: ("1 Esdras", "1-esdras", "Ezra", 15), 2: ("2 Esdras", "2-esdras", "Nehemiah", 16)},
    "Machabées": {1: ("1 Machabées", "1-machabees", None, 80), 2: ("2 Machabées", "2-machabees", None, 81)},
    "Corinthiens": {1: ("1 Corinthiens", "1-corinthians", None, None), 2: ("2 Corinthiens", "2-corinthians", None, None)},
    "Thessaloniciens": {1: ("1 Thessaloniciens", "1-thessalonians", None, None),
                        2: ("2 Thessaloniciens", "2-thessalonians", None, None)},
    "Timothée": {1: ("1 Timothée", "1-timothy", None, None), 2: ("2 Timothée", "2-timothy", None, None)},
    "Pierre": {1: ("1 Pierre", "1-peter", None, None), 2: ("2 Pierre", "2-peter", None, None)},
    "Jean": {1: ("1 Jean", "1-john", None, None), 2: ("2 Jean", "2-john", None, None), 3: ("3 Jean", "3-john", None, None)},
}
# Names that are ambiguous once the earlier expansion has run: "1 Rois" may be Calmet's
# 1 Rois or a modern 1 Kings (= 3 Rois). The raw page decides (see footnotes.py).
AMBIGUOUS = {"Rois", "Chroniques"}

BOOK = {}       # canonical (with number) -> (vul, oshb, lxx)
ABBR = {}       # abbreviation -> name in _TABLE
for name, vul, oshb, lxx, abbrs in _TABLE:
    for a in abbrs.split():
        ABBR[a] = name
    if vul:
        BOOK[name] = (vul, oshb, lxx)
for n in NUMBERED.values():
    for canon, vul, oshb, lxx in n.values():
        BOOK[canon] = (vul, oshb, lxx)
BOOK["Siracide"] = BOOK["Ecclésiastique"]
OT_NAME = {v[0]: k for k, v in BOOK.items() if k not in ("Siracide", "Néhémie")}  # vul file -> name

ROMAN = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100}


def plain(s):
    """lower case, no accents, ſ -> s."""
    s = unicodedata.normalize("NFD", s.replace("ſ", "s").replace("æ", "ae").replace("œ", "oe"))
    return "".join(ch for ch in s if not unicodedata.combining(ch)).lower()


def num(tok):
    """'CIII' / 'ciii' / '103' -> 103; None if not a number."""
    if tok.isdigit():
        return int(tok)
    t = tok.lower()
    if not t or any(ch not in ROMAN for ch in t):
        return None
    total = prev = 0
    for ch in reversed(t):
        v = ROMAN[ch]
        total += -v if v < prev else v
        prev = max(prev, v)
    return total


def resolve(name, n):
    """('Rois', 3) -> '3 Rois'; ('Genèse', None) -> 'Genèse'; None if impossible."""
    if name == "Jean" and n is None:  # the Gospel; with a number, the epistles
        return "Jean"
    if name in NUMBERED:
        if n is None:
            return None
        hit = NUMBERED[name].get(n)
        return hit[0] if hit else None
    if n is not None:
        return None
    return "Ecclésiastique" if name == "Siracide" else name


# ---- parsing ---------------------------------------------------------------------

_W = r"[A-Za-zÀ-ÿſæœÆŒ]"
_NUMPFX = r"(?:(?P<n>[1-4]|I{1,3}|IV)(?:\s*\.\s*|\s+)(?:Livre\s+des?\s+)?)"
# lower-case Roman chapters ("Luc. i. 79.", "Jerem. v. 22.") but not "l." (livre), "c." (chapitre)
_CH = r"(?:[IVXLC]+|(?![lcd]\b)[ivxlc]+|\d{1,3})"
# verses: "1. 4. 5"  "16. & 17"  "21, 22, 23"  "22-23"; a number is not a verse when a chapter
# follows it ("95:10") or, for 1-4, a book name ("31. 1 Rois")
_VN = r"(?:[1-4](?!\d|\s*:|\s*\.?\s*(?!et\b)[A-Za-zÀ-ÿſ]{2,}\.?\s*(?:[IVXLC]+\b|\d))|(?:[1-9]\d{1,2}|[05-9])(?!\d|\s*:))"
_VS = rf"\d{{1,3}}(?!\d|\s*:)(?:\s*\.?\s*(?:,|-|&|et|\.)\s*{_VN})*"
# chapter then verse(s): "XVI. 1. 4. 5."  "16:1, 4, 5"  "XXXIX. ℣. 3."  "1. 2."  "9:7-8"
_CV = (rf"(?P<c>{_CH})\s*(?:[.,:]\s*|\s+)(?:(?:℣|v|verset|vers)\.?\s*)?"
       rf"(?P<v>{_VS})")
REF = re.compile(
    rf"(?<!{_W})(?:{_NUMPFX})?(?P<b>{_W}{{1,15}})\s*\.?\s*,?\s*(?:{_CV}|(?P<conly>{_CH})(?=\s*\.?\s*(?:$|[;&]|et\b)))",
)
CONT = re.compile(rf"\s*\.?\s*(?:,|;|&|et)\s*(?:(?:℣|v|verset)\.?\s*(?P<vo>{_VS})|{_CV})\.?")


def _verses(s):
    """'1. 4. 5' -> [1, 4, 5]; '22-23' -> [22, 23]."""
    out, prev_dash = [], False
    for tok in re.findall(r"\d+|-", s):
        if tok == "-":
            prev_dash = True
            continue
        v = int(tok)
        if prev_dash and out:
            out.extend(range(out[-1] + 1, v + 1))
        else:
            out.append(v)
        prev_dash = False
    return out


def fmt_verses(vs):
    """[1, 4, 5] -> '1, 4-5'."""
    vs = sorted(dict.fromkeys(vs))
    parts, i = [], 0
    while i < len(vs):
        j = i
        while j + 1 < len(vs) and vs[j + 1] == vs[j] + 1:
            j += 1
        parts.append(str(vs[i]) if i == j else f"{vs[i]}-{vs[j]}")
        i = j + 1
    return ", ".join(parts)


class Ref:
    __slots__ = ("start", "end", "book", "name", "chap", "verses", "src")

    def __init__(self, start, end, book, name, chap, verses, src):
        self.start, self.end, self.book, self.name = start, end, book, name
        self.chap, self.verses, self.src = chap, verses, src

    def render(self, with_book=True):
        cv = f"{self.chap}:{fmt_verses(self.verses)}" if self.verses else f"{self.chap}"
        return f"{self.book} {cv}" if with_book else cv

    def __repr__(self):
        return f"<{self.render()} {self.src!r}>"


def find_refs(text):
    """Every Bible reference in `text`, in order. A reference without a book after '&'/'et'
    belongs to the book before it ("Pſ. CIII. 5. & XCV. 10.")."""
    out, pos = [], 0
    for m in REF.finditer(text):
        if m.start() < pos:
            continue
        name = ABBR.get(plain(m.group("b")))
        if not name:
            continue
        n = num(m.group("n")) if m.group("n") else None
        book = resolve(name, n)
        if not book:
            continue
        if m.group("conly"):
            c = num(m.group("conly"))
            if not c:
                continue
            out.append(Ref(m.start(), m.end(), book, name, c, [], m.group(0)))
            pos = m.end()
            continue
        c = num(m.group("c"))
        if not c:
            continue
        ref = Ref(m.start(), m.end(), book, name, c, _verses(m.group("v")), m.group(0))
        out.append(ref)
        pos = m.end()
        while True:  # "& XCV. 10."  ", 9:7-8"  "et ℣. 3."
            k = CONT.match(text, pos)
            if not k:
                break
            if k.group("vo"):
                ref.verses += _verses(k.group("vo"))
                ref.end = k.end()
            else:
                c2 = num(k.group("c"))
                if not c2:
                    break
                out.append(Ref(k.start(), k.end(), book, name, c2, _verses(k.group("v")), k.group(0)))
            pos = k.end()
    return out


# ---- the texts -------------------------------------------------------------------

@lru_cache(None)
def vulgate(vul):
    """{(chapter, verse): text} of one Vulgate book."""
    d = json.loads((VUL / f"{vul}.json").read_text(encoding="utf-8"))
    return {(c["chapter"], v["verse"]): v["text"] for c in d["chapters"] for v in c["verses"]}


def clementine(ref, v):
    """Our Vulgate text numbers Psalm 115 from 1; the Clementine (Calmet's) from 10, following on Psalm 114."""
    return v - 9 if ref.book == "Psaumes" and ref.chap == 115 and v >= 10 else v


def exists(ref):
    vul = BOOK.get(ref.book, (None,))[0]
    if not vul:
        return None
    vg = vulgate(vul)
    if not ref.verses:
        return any(c == ref.chap for c, _ in vg)
    return all((ref.chap, clementine(ref, v)) in vg for v in ref.verses)


def vulgate_text(ref):
    vul = BOOK.get(ref.book, (None,))[0]
    if not vul:
        return ""
    vg = vulgate(vul)
    return " ".join(vg.get((ref.chap, clementine(ref, v)), "") for v in ref.verses)


@lru_cache(None)
def hebrew():
    """{book: {(c, v): [words]}}; prefixes joined ('ב/ראשית' -> 'בראשית')."""
    d = json.loads((REFS / "hebrew_oshb.json").read_text(encoding="utf-8"))
    return {b: {(ci + 1, vi + 1): [w[0].replace("/", "") for w in verse]
                for ci, ch in enumerate(chs) for vi, verse in enumerate(ch)} for b, chs in d.items()}


@lru_cache(None)
def lxx(nr):
    """{(c, v): text} of one Septuagint book (getbible numbering)."""
    p = REFS / "lxx" / f"{nr}.json"
    if not p.exists():
        return {}
    d = json.loads(p.read_text(encoding="utf-8"))
    return {(c["chapter"], v["verse"]): v["text"] for c in d["chapters"] for v in c["verses"]}


def vulgate_to_hebrew_psalm(n):
    """Vulgate psalm number -> Hebrew psalm numbers it overlaps."""
    if n <= 8 or n >= 148:
        return [n]
    if n == 9:
        return [9, 10]
    if 10 <= n <= 112:
        return [n + 1]
    if n == 113:
        return [114, 115]
    if n in (114, 115):
        return [116]
    if 116 <= n <= 145:
        return [n + 1]
    return [147]  # 146, 147
