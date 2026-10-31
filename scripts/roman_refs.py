"""Write out the Roman-numeral references chapter_refs.py and modernize_refs.py leave, in
french_commentary.

"le Psaume LXIX"                    -> "le Psaume 69"
"les Psaumes XI. XIII. et LII."     -> "les Psaumes 11, 13 et 52."
"Voyez ci-devant XVII. 6."          -> "Voyez ci-devant 17:6."      (the volume's own book)
"Comparez aussi XLIII. 20. XLVIII. 21." -> "Comparez aussi 43:20 ; 48:21."
"Voyez Isaïe XIII. XIV. et XLVII."     -> "Voyez Isaïe 13, 14 et 47."  ("Jerem. XL." -> "Jérémie 40.")
"Ézéchiel 13. et XIV."              -> "Ézéchiel 13. et 14."
"le LXIII. et le LXIV. sont"        -> "le 63. et le 64. sont"   (a chapter or psalm named alone)
"le quatrième Livre des Rois, XXIV. 14." -> "le quatrième Livre des Rois, 24:14."
"Psaume CIII. II." / "Genèse, II. II."   -> "Psaume CIII. 11." / "Genèse, II. 11." (then modernize_refs)

Every reference is checked against the Clementine Vulgate (bible_refs.exists); a list with one
reference that fails is left as it is. A verse printed "I." or "II." after a chapter is the scan's
reading of 1 and 11 (Calmet's verses are in Arabic figures): "Genèse, II. II." is the Phison,
2:11. Run after modernize_refs.py, then chapter_refs.py and modernize_refs.py again, then this
once more.

Usage: python3 roman_refs.py [--apply] [volume ...]   (dry run by default; every volume)
Changes are listed in reports/roman_refs_changes.tsv.
"""
import json, re, sys

from bible_refs import _VS, ABBR, BOOK, OT_NAME, Ref, _verses, exists, num, plain, resolve
from paths import BOOKS, BY_VOLUME, DATA, pages, volumes_of

R = r"[IVXLC]+"
R2 = r"[IVXLC]{2,}"
# "Psaume LXIX", "Psaumes XI. XIII. XXXV. et LII.": chapters alone, no verse after the last
PSALMS = re.compile(rf"(?P<w>\bPsaumes?\s+)(?P<l>{R}(?:\s*[.,]?\s*(?:et\s+)?{R})*)\b(?P<end>\.?)(?!\s*[.,]?\s*(?:\d|{R}\b))")
# chapter and verses of the volume's own book, after "ci-devant", "Voyez", ...
SAME_BOOK = re.compile(r"\b(?:ci-devant|ci-après|[Cc]omparez|[Vv]oyez)(?:\s+aussi)?\s*,?\s+$")
CHAIN = re.compile(rf"(?P<c>{R})\.\s*(?P<v>{_VS})(?P<more>(?:\s*[.,;]?\s*(?:et\s+)?{R}\.\s*{_VS})*)(?P<end>\.?)(?![\w:])")
LINK = re.compile(rf"\s*[.,;]?\s*(?:et\s+)?(?P<c>{R})\.\s*(?P<v>{_VS})")

_L = r"[A-Za-zÀ-ÿſ]"
# "Psaume CIII. II." "Genèse, II. II." "℣. II.": the verse the scan read as Roman
VERSE_I = re.compile(rf"(?P<pre>(?:(?<!{_L}){_L}{{2,}}\.?_?,?|\d\.|℣\.)\s*{R}\.\s*(?:℣\.\s*)?|℣\.\s*|\bverset\s+)(?P<v>II|I)(?=\s*[.,]|\s*$)")
NOT_BOOK = re.compile(r"(?<!\w)(?:lib|liv|livre|l|tom|tome|t|pag|p|page|Antiq|Æneid|Iliad|Odyss|Homélie|Hom|Pape|Jean|c|cap)\.?_?,?\s*$", re.I)
NUMBERED = r"(?:(?P<n>[1-4]|I{1,3}|IV)\.?\s*)?"
# a book, then chapters alone: "Isaïe XIII. XIV. et XLVII."  "4. Reg. XVIII. XIX."
BOOK_CHAPTERS = re.compile(rf"(?<!{_L}){NUMBERED}(?P<b>{_L}{{2,}})(?P<dot>\.?_?)(?P<sep>\s*,?\s+)(?P<l>{R}(?:\s*[.,]?\s*(?:et\s+)?{R})*)\b(?P<end>\.?)(?!\s*[.,]?\s*(?:\d|{R}\b|℣|§|versets?\b|ult\b|_?(?:Par|Reg|Mac|Macc|Esdr?|Cor|Tim|Thess|Petr|Joan)\b))")
# "Ézéchiel 13. et XIV."
AND_CHAPTER = re.compile(rf"(?P<pre>(?<!{_L})(?:[1-4] )?(?P<b>[A-ZÉ]{_L}+(?: des cantiques)?) \d+(?::\d+(?:(?:-|, ?)\d+)*)?\.?\s+et\s+)(?P<c>{R})\b(?=\.(?!\s*\d)|,\s*\d)")
# "le CVI. rend grâces"  "les LXXIII. LXXVIII. LXXIX. du temps"  "au XXXIV."
ARTICLE = re.compile(rf"(?P<pre>\b(?:[Ll]e|[Aa]u|[Dd]u|[Ll]es|aux)\s+)(?P<l>{R2}(?:\.\s*(?:et\s+)?{R2})*)(?P<end>\.?)(?!\s*[.,]?\s*\d)(?=[\s.,;]|$)")
# "le quatrième Livre des Rois, XXIV. 14."  "le premier des Paralipomènes, XXVII. 5."
ORDINAL = {"premier": 1, "second": 2, "troisième": 3, "quatrième": 4}
WORDS = re.compile(rf"\b(?P<o>premier|second|troisième|quatrième)\s+(?:Livre\s+)?(?:des|de|d')\s*(?P<b>Rois|Paralipomènes|Esdras|Machabées)\s*,?\s*(?:c\.\s*)?$")


def book_of(name, n=None):
    """'Reg', '4' -> '4 Rois'; 'Isaïe' -> 'Isaïe'; None if not a book."""
    full = name if name in BOOK else ABBR.get(plain(name))
    return full and resolve(full, num(n) if n else None)


def verse_one_eleven(text, out):
    def one(m):
        pre = m.group("pre")
        word = re.match(rf"{_L}{{2,}}", pre)
        if word and (NOT_BOOK.search(word.group() + ".") or not (
                book_of(word.group()) or re.fullmatch(r"(?i)psaumes?|chap\w*|suiv", word.group()))):
            return m.group(0)
        new = pre + ("11" if m.group("v") == "II" else "1")
        out.append((m.group(0), new))
        return new
    return VERSE_I.sub(one, text)


def chapter_list(words):
    """['XIII', 'et', 'XIV'] -> '13 et 14'; ['XI', 'XIII'] -> '11, 13'."""
    s = ""
    for i, w in enumerate(words):
        s += w if w == "et" else str(num(w))
        if i + 1 < len(words):
            s += " " if "et" in (w, words[i + 1]) else ", "
    return s


def book_chapters(text, out):
    def one(m):
        book = book_of(m.group("b"), m.group("n"))
        words = re.findall(rf"{R}|\bet\b", m.group("l"))
        if not book or book in ("Psaumes", "Jean") or not all(exists(Ref(0, 0, book, book, num(w), [], "")) for w in words if w != "et"):
            return m.group(0)
        written = book if m.group("b") not in BOOK or m.group("n") else m.group("b")
        new = written + (m.group("sep") if m.group("b") in BOOK and not m.group("dot") else " ") + chapter_list(words) + m.group("end")
        out.append((m.group(0), new))
        return new
    return BOOK_CHAPTERS.sub(one, text)


def and_chapter(text, out):
    def one(m):
        b = m.group("b")
        book = book_of(b) if b in BOOK else None
        book = book or (m.group("pre")[:1].isdigit() and resolve(b.split()[-1], int(m.group("pre")[0])))
        if not book or not exists(Ref(0, 0, book, book, num(m.group("c")), [], "")):
            return m.group(0)
        new = m.group("pre") + str(num(m.group("c")))
        out.append((m.group(0), new))
        return new
    return AND_CHAPTER.sub(one, text)


def article(text, book, out):
    def one(m):
        words = re.findall(rf"{R}|\bet\b", m.group("l"))
        if not all(exists(Ref(0, 0, book, book, num(w), [], "")) for w in words if w != "et"):
            return m.group(0)
        new = m.group("pre") + chapter_list(words) + m.group("end")
        out.append((m.group(0), new))
        return new
    return ARTICLE.sub(one, text)


def worded_books(text, out):
    res = []
    for m in CHAIN.finditer(text):
        w = WORDS.search(text[max(0, m.start() - 60):m.start()])
        book = w and resolve(w.group("b"), ORDINAL[w.group("o")])
        if not book:
            continue
        refs = [Ref(0, 0, book, book, num(m.group("c")), _verses(m.group("v")), "")]
        refs += [Ref(0, 0, book, book, num(k.group("c")), _verses(k.group("v")), "")
                 for k in LINK.finditer(m.group("more"))]
        if not all(r.chap and exists(r) for r in refs):
            continue
        new = " ; ".join(r.render(with_book=False) for r in refs) + m.group("end")
        res.append((m.start(), m.end(), new))
        out.append((m.group(0), new))
    for s_, e, new in reversed(res):
        text = text[:s_] + new + text[e:]
    return text


def psalms(text, out):
    def one(m):
        nums = [num(t) for t in re.findall(R, m.group("l"))]
        if any(t in ("I", "II") for t in re.findall(R, m.group("l"))) or not all(
                n and exists(Ref(0, 0, "Psaumes", "Psaumes", n, [], "")) for n in nums):
            return m.group(0)
        words = re.findall(rf"{R}|\bet\b", m.group("l"))
        s = ""
        for i, w in enumerate(words):
            s += w if w == "et" else str(num(w))
            if i + 1 < len(words) and w != "et" and words[i + 1] != "et":
                s += ", "
            elif i + 1 < len(words):
                s += " "
        new = m.group("w") + s + m.group("end")
        out.append((m.group(0), new))
        return new
    return PSALMS.sub(one, text)


def same_book(text, book, out):
    res, pos = [], 0
    for m in CHAIN.finditer(text):
        if m.start() < pos or not SAME_BOOK.search(text[max(0, m.start() - 40):m.start()]):
            continue
        refs = [Ref(0, 0, book, book, num(m.group("c")), _verses(m.group("v")), "")]
        refs += [Ref(0, 0, book, book, num(k.group("c")), _verses(k.group("v")), "")
                 for k in LINK.finditer(m.group("more"))]
        if not all(r.chap and r.verses and exists(r) for r in refs):
            continue
        new = " ; ".join(r.render(with_book=False) for r in refs) + m.group("end")
        res.append((m.start(), m.end(), new))
        out.append((m.group(0), new))
        pos = m.end()
    for s, e, new in reversed(res):
        text = text[:s] + new + text[e:]
    return text


def main(argv):
    apply = "--apply" in argv
    changes = []
    for vol in volumes_of([a for a in argv if not a.startswith("--")] or ["all"]):
        book = OT_NAME.get(BOOKS[BY_VOLUME[vol]]["vul"]) if vol in BY_VOLUME else None
        for f in pages(vol):
            d = json.loads(f.read_text(encoding="utf-8"))
            hit = False
            for c in d.get("commentary") or []:
                t = c.get("french_commentary")
                if not isinstance(t, str):
                    continue
                out = []
                t2 = verse_one_eleven(t, out)
                t2 = psalms(t2, out)
                t2 = book_chapters(t2, out)
                t2 = and_chapter(t2, out)
                t2 = worded_books(t2, out)
                if book:
                    t2 = same_book(t2, book, out)
                    t2 = article(t2, "Psaumes" if book == "Psaumes" else book, out)
                if t2 != t:
                    c["french_commentary"], hit = t2, True
                    changes += [(f"{vol}/{f.stem}", old, new) for old, new in out]
            if hit and apply:
                f.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    rep = DATA.parent / "reports"
    rep.mkdir(exist_ok=True)
    (rep / "roman_refs_changes.tsv").write_text("".join("\t".join(x).replace("\n", " ") + "\n" for x in changes),
                                                encoding="utf-8")
    print(f"{len(changes)} rewritten{'' if apply else ' (dry run)'} -> reports/roman_refs_changes.tsv")


if __name__ == "__main__":
    main(sys.argv[1:])
