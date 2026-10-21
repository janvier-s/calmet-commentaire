"""Write out chapter references that name no book, in french_commentary.

"au chap. XVIII. 12. il"           -> "au chapitre 18:12 il"
"Voyez le chap. II. ℣. I."         -> "Voyez le chapitre 2:1."
"ci-devant chap. XV. ℣. 42. XIX. 7."  -> "ci-devant chapitre 15:42 ; 19:7."
"Chap. VIII. IX. X. XI."           -> "chapitres 8-11"
No book is guessed. Right after a book name or abbreviation ("sur les Nombres, chap. XXXIII. 25.",
"Deut. ch. I. ℣. 4.") only the chapter word goes, and modernize_refs.py, run next, writes the
reference out ("Nombres 33:25", "Deutéronome 1:4") with its Vulgate check. Rois, Paralipomènes, Esdras, Machabées... alone (bible_refs.NUMBERED) stay "chapitre" too (which one?). Chapter lists must go up (XXV. I. is left alone). A dot after the numbers is kept before a capital or at the end, dropped
before a lowercase word. Changed French is added to the LLM cache.

Usage: python3 chapter_refs.py [--apply] [volume ...]   (dry run by default; every volume)
Changes are listed in reports/chapter_refs_changes.tsv.
"""
import hashlib
import json
import re
import sys

from bible_refs import ABBR, NUMBERED, fmt_verses, plain
from paths import DATA, LLM_CACHE, pages

ROMAN = r"\b(?=[IVXLC])C{0,3}(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})(?<=[IVXLC])\b(?!['’])"
VERSE = r"(?:\d+(?:-\d+)?|(?<=℣\. )" + ROMAN + ")"
SEP = r"\.?\s*(?:(?:et|&)\s+)?"
REF = re.compile(
    rf"(?P<sep>,?\s*)\b(?P<w>[Cc]hap(?:itre)?s?\.?|[Cc]h\.)\s*(?P<c>{ROMAN}(?:{SEP}{ROMAN})*)"
    rf"(?:\.?,?\s*(?:℣\.\s*)?(?P<v>{VERSE}(?:{SEP}{VERSE})*))?"
    rf"(?P<more>(?:\.?,?\s*(?:(?:et|&)\s+)?{ROMAN}\.?,?\s*(?:℣\.\s*)?{VERSE}(?:{SEP}{VERSE})*)*)(?P<dot>\.)?(?=(?P<next>\s*\S?))")
BOOK_BEFORE = re.compile(r"(?<!\w)([A-ZÉ][A-Za-zÀ-ÿ]{2,})$|(?<!\w)([A-Za-zÀ-ÿ]{2,})\.\s*$")
NAMES = {plain(n) for n in ABBR.values() if n not in NUMBERED} | {k for k, n in ABBR.items() if n not in NUMBERED and len(k) > 3}
VAL = dict(I=1, V=5, X=10, L=50, C=100)


def roman(r):
    n = 0
    for a, b in zip(r, r[1:] + " "):
        n += -VAL[a] if VAL.get(b, 0) > VAL[a] else VAL[a]
    return n


def numbers(s):
    out = []
    for x in re.findall(r"[IVXLC]+|\d+(?:-\d+)?", s):
        a, _, b = x.partition("-")
        a = int(a) if a.isdigit() else roman(a)
        out += range(a, int(b) + 1) if b else [a]
    return out


def write(m, text):
    ch = numbers(m["c"])
    if not ch or max(ch) > 150 or any(a >= b for a, b in zip(ch, ch[1:])):
        return m.group()  # "Chap. XXV. I." : a verse or a pronoun, not two chapters; left alone
    before = text[:m.start()]
    book = BOOK_BEFORE.search(before)
    if book and (plain(book[1]) in NAMES if book[1] else plain(book[2]) in ABBR):
        # "Nombres, chap. XXXIII. 25." -> "Nombres XXXIII. 25.": modernize_refs.py writes it out
        # (number before Rois/Paralipomènes, Vulgate check, chains of chapters)
        return " " + text[m.end("w"):m.end()].lstrip()
    word = "chapitres" if len(ch) > 1 else "chapitre"
    if not before.strip() or re.search(r"[.!?]\s*$", before):
        word = word.capitalize()
    out = m["sep"] + word + " " + " et ".join(fmt_verses(ch).rsplit(", ", 1))  # runs stay "8-11"
    if m["v"] and len(ch) == 1:
        out += ":" + fmt_verses(numbers(m["v"]))
    elif m["v"]:
        return m.group()
    for k in re.finditer(rf"(?P<et>\s(?:et|&)\s+)?(?P<c>{ROMAN})\.?,?\s*(?:℣\.\s*)?(?P<v>{VERSE}(?:{SEP}{VERSE})*)", m["more"]):
        out += (" et " if k["et"] else " ; ") + f"{roman(k['c'])}:{fmt_verses(numbers(k['v']))}"
    if m["dot"] and not m["next"].strip()[:1].islower():
        out += "."
    return out


def fix(s, log, where):
    def rep(m):
        new = write(m, s)
        if new != m.group():
            log.append(f"{where}\t{m.group()!r}\t{new!r}\t{s[max(0, m.start() - 30):m.end() + 15]!r}")
        return new
    return REF.sub(rep, s)


def walk(o, key, cache, log, where):
    if isinstance(o, dict):
        return {k: walk(v, k, cache, log, where) for k, v in o.items()}
    if isinstance(o, list):
        return [walk(v, key, cache, log, where) for v in o]
    if isinstance(o, str) and key == "french_commentary":
        new = fix(o, log, where)
        if new != o:
            cache[hashlib.md5(new.encode()).hexdigest()] = new
        return new
    return o


def main(argv):
    apply = "--apply" in argv
    vols = [a for a in argv if not a.startswith("--")] or sorted(p.parent.name for p in DATA.glob("*/normalized"))
    cache = json.loads(LLM_CACHE.read_text(encoding="utf-8")) if LLM_CACHE.exists() else {}
    log, npages = [], 0
    for vol in vols:
        for p in pages(vol):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            new = walk(d, None, cache, log, f"{vol}/{p.stem}")
            if new != d:
                npages += 1
                if apply:
                    p.write_text(json.dumps(new, ensure_ascii=False, indent=2), encoding="utf-8")
    if apply:
        LLM_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    out = DATA.parent / "reports" / "chapter_refs_changes.tsv"
    out.write_text("page\tbefore\tafter\tcontext\n" + "\n".join(log), encoding="utf-8")
    print(f"{len(log)} references on {npages} pages", "" if apply else "(dry run)", f"\nlisted in {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
