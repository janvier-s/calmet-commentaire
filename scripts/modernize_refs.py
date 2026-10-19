"""Write old-style Bible references out as "Livre C:V" in french_commentary and footnotes.

"Pſal. CXXXVIII. 5. 6. 7." -> "Psaumes 138:5-7."   "3. Reg. IV. 9" -> "3 Rois 4:9"
"Jérém. xxv. 12" -> "Jérémie 25:12"            "Matthieu, XXVII. 34" -> "Matthieu 27:34"

Only references with an old tell (abbreviated or old-spelt book name, Roman chapter, "3." /
"I." before the name, "℣.") are touched; modern ones are left as they are. Every rewrite is
checked against the Clementine Vulgate (bible_refs.exists); what fails, or cannot be read with
certainty, goes to the review list instead of being changed. No model is called.

Usage: python3 modernize_refs.py [--apply] [book ...]   (default: dry run, every book)
  writes reports/modernize_refs_review.tsv (what is left to look at) and, on a dry run,
  reports/modernize_refs_changes.tsv (every planned rewrite).
"""
import json, re, sys

from bible_refs import _VS, ABBR, Ref, _verses, exists, find_refs, num, plain
from paths import DATA

FULL = re.compile(r"(?:[1-4] )?[A-ZÉ]\w+(?: des cantiques)? \d+(?::\d+(?:(?:-|, )\d+)*)?")
# a chapter with no book or "et" before it: "Genès. XXIV. 27. 49. XLVII. 29."
BARE = re.compile(rf"(?:\.\s*|\s+)(?:(?:et|&)\s+)?(?P<c>[IVXLC]+)\.\s*(?P<v>{_VS})")
ROMAN_CH = re.compile(r"\b[IVXLC]+\b|(?<![\w'’])[ivxlc]+\.")
# a book name in italics before its chapter: "_Genes._ XXI. 14." -> "Genes. XXI. 14."
DONE = re.compile(r"(?:\.\s*|\s+)(?:(?:et|&)\s+)?\d+:\d+(?:(?:-|,\s*)\d+)*")
ITALIC = re.compile(r"_((?:[1-4I]{1,3}(?:\.\s*|\s+))?([A-Za-zÀ-ÿſæœ]+)\.?)_(?=[\s.,]*(?:[IVXLCivxlc]+\b|\d))")


def unitalic(text):
    return ITALIC.sub(lambda m: m.group(1) if plain(m.group(2)) in ABBR else m.group(0), text)

# Settled by hand (reports/modernize_refs_review.tsv, 2026-10-19). A text: what the reference
# is: from the scan, or (with *, the guess convention) the verse that fits the context. None: Calmet's numbers do not match
# the Vulgate, but are written out as printed. "": not a reference, or unreadable; left alone.
MANUAL = {
    ('21a_psaumes/page_0233', 'Act. III. 29'): 'Actes 2:29*',  # David's tomb, in Peter's speech
    ('21a_psaumes/page_0687', 'Psal. x. 7. 14'): 'Psaumes 9:28, 35',  # labor (amal); Hebrew 10:7, 14
    ('02_exode/page_0573', 'Psal. 59. 5 et 59. 10'): 'Psaumes 59:5 et 59:10',
    ('10_2_rois/page_0118', '2. Reg. LII. 7'): '2 Rois 3:7',  # scan: III. 7
    ('10_2_rois/page_0262', 'I. Par. 37'): '1 Paralipomènes 11:37',  # Naarai filius Asbai
    ('11_3_rois/page_0179', '1. Par. XVIII. 27'): '1 Paralipomènes 28:17',  # scan: XXVIII. 17
    ('13_1_chroniques/page_0107', 'Psalm. 77. ℣. 51. et 104. 23. 27'): 'Psaumes 77:51 et 104:23, 27',
    ('13_1_chroniques/page_0173', '2. Reg. XXXIII. 13'): '2 Rois 23:13*',  # the three going down to David
    ('14_2_chroniques/page_0056', 'I. Par. XXXI. 3'): '2 Paralipomènes 31:3*',  # holocausts for the feasts
    ('18_judith/page_0163', 'Judith III. 35'): 'Judith 3:15',  # scan: III. 15
    ('20_job/page_0065', 'Genes. XXVI. 14. 70'): 'Genèse 26:14. 70',  # 70 = the Septuagint
    ('20_job/page_0166', 'Malach. III. 22'): 'Malachie 3:2*',  # herba fullonum, beside Jérémie 2:22
    ('21a_psaumes/page_0523', 'Hebr. x. 5. et 70'): 'Hébreux 10:5 et 70',
    ('06_josue/page_0270', 'Num. XI. 35'): 'Nombres 11:34',  # Haseroth; 11:35 is the Hebrew numbering
    ('06_josue/page_0281', 'Num. XI. 35'): 'Nombres 11:34',
    ('06_josue/page_0392', '3. Reg. xiv. 38'): '3 Rois 14:30*',  # war between Roboam and Jeroboam
    ('06_josue/page_0394', 'VIII. 13. 14'): None,
    ('07_juges/page_0048', 'XIX. 38'): None,
    ('09_1_rois/page_0097', 'Psal. CXVI. 10'): 'Psaumes 115:10',  # Credidi, propter quod (ki); Hebrew 116:10
    ('09_1_rois/page_0441', 'Esther XX. 16'): 'Esther 15:16*',  # quasi angelum Dei, beside Genèse 33:10
    ('11_3_rois/page_0413', 'Isai. XXXIX. 12'): 'Isaïe 34:12*',  # nobiles (horim)
    ('12_4_rois/page_0257', 'Isaï. IX. 30'): None,
    ('12_4_rois/page_0283', 'Ezechiel XV. 12'): None,
    ('20_job/page_0106', 'Psal. VI.15'): 'Psaumes 7:15*',  # parturiit injustitiam
    ('20_job/page_0153', 'Psal. XXVII. 16'): 'Psaumes 17:16*',  # fundamenta orbis terrarum
    ('20_job/page_0252', 'Sap. XXIII. ℣. 21'): None,
    ('20_job/page_0264', 'Psaume XXVI. 35'): 'Psaumes 36:35*',  # non est inventus locus ejus
    ('20_job/page_0335', 'Psaume xxxv. 25'): 'Psaumes 36:25',  # the verse is quoted
    ('21a_psaumes/page_0334', 'XXXI. 24. 25'): None,
    ('21a_psaumes/page_0374', '1. Reg. XXI. 46'): None,
    ('21a_psaumes/page_0638', 'Psal. X. 10'): None,
    ('21a_psaumes/page_0664', 'Psaume XLIX. 15. 24'): 'Psaumes 49:14, 23*',  # sacrificium laudis
    ('21a_psaumes/page_0678', 'Jerem. II. 51'): 'Jérémie 51:51*',  # venerunt alieni
    ('21a_psaumes/page_0798', 'Psal. LX. 29'): 'Psaumes 9:28*',  # sub lingua, beside Cantique 4:11
    ('21a_psaumes/page_0856', 'Pseaume XXXIX. 23'): 'Psaumes 39:18',  # the verse is quoted
    ('21a_psaumes/page_0878', 'Isaïe XXIII. 21'): 'Isaïe 13:21*',  # tsiyim, the people of the waters
    ('17_tobie/page_0067', 'Genes. XXXI. 11. et 63'): 'Genèse 31:11 et 13*',  # the angel: Ego sum Deus Bethel
    ('21a_psaumes/page_0855', 'Levit. II. 9. 19'): 'Lévitique 2:9, 16*',  # in memoriam (azkara)
    ('01_genese/page_0533', 'Genèse. C'): '',
    ('03_levitique/page_0122', 'deuil. 3'): '',
    ('04_nombres/page_0256', 'ici verset 12'): '',
    ('04_nombres/page_0417', 'ici, verset 21 et 31'): '',
    ('06_josue/page_0130', 'Hébreux. C'): '',
    ('06_josue/page_0287', '3. Reg. XXX.315'): '',
    ('20_job/page_0087', 'Sophi. 70'): '',
    ('21a_psaumes/page_0837', 'Cantique. C'): '',
}


def tell(src, book):
    """Why `src` is old style, or None if it is already written out."""
    s = src.strip(" .,;")
    if FULL.fullmatch(s):
        return None
    if ROMAN_CH.search(s):
        return "roman"
    if "℣" in s or re.match(r"[1-4IV]+\.\s", s):
        return "prefix"
    name = re.match(r"(?:[1-4IV]+\.?\s*)?([A-Za-zÀ-ÿſ]+)", s)
    if name and plain(name.group(1)) != plain(book.split()[-1] if book[0].isdigit() else book.split()[0]):
        return "abbr"
    return None


def risky(src, text, start, end):
    """Readings find_refs gets wrong: "deuil" (deu + il), "Lévitique 1, 2" (chapters or 1:2?)."""
    m = re.match(r"\s*(?:[1-4IV]+\.?\s*)?[A-Za-zÀ-ÿſ]+", src)  # None: a continuation (", XXI. 3.")
    after = src[m.end():m.end() + 1] if m else " "
    if not after or after not in " .,":  # "deuil" = deu + il, "exil", "collet"
        return "no break after name"
    if end < len(text) and text[end].isalpha():  # "Genèse. C|et"
        return "runs into a word"
    if start and text[start - 1].isalpha():
        return "inside a word"
    if not ROMAN_CH.search(src) and ":" not in src and re.search(r"\d+\s*,\s*\d+", src):
        return "C, V or two chapters?"
    return None


def refs(text):
    """find_refs, plus the bare chapters it leaves after a reference."""
    out = []
    for r in find_refs(text):
        out.append(r)
        end = r.end
        while True:
            k = BARE.match(text, end)
            if k and num(k.group("c")):
                out.append(Ref(k.start(), k.end(), r.book, r.name, num(k.group("c")), _verses(k.group("v")), k.group(0)))
            elif not (k := DONE.match(text, end)):  # "33:10." already written out: go on past it
                break
            end = k.end()
    return out


def rewrite(text, where, review, changes):
    out, pos = [], 0
    text = unitalic(text)
    for r in refs(text):
        if r.start < pos:
            continue
        why = tell(r.src, r.book)
        if not why or " " in r.book and text[:r.start].endswith(r.book.rsplit(" ", 1)[0] + " "):
            continue  # modern already, or the tail of "Cantique des cantiques 5:1"
        lead = len(r.src) - len(r.src.lstrip(" .,;&et"))  # continuation: keep its separator
        src = r.src[lead:]
        new = r.render(with_book=not lead)
        bad = risky(r.src, text, r.start, r.end)
        if new == src.rstrip(" ."):
            continue
        key = (where[0], " ".join(src.strip(" .,;").split()))
        if MANUAL.get(key) == "":
            continue
        if key in MANUAL:
            new, bad = MANUAL[key] or new, None
        elif not bad and exists(r) is False:
            if not BARE.fullmatch(r.src):  # in a list after a good reference: Calmet's misprint

                bad = "not in the Vulgate"
        if bad == "no break after name":  # a word, not a reference
            continue
        if bad:
            review.append((*where, bad, src, new, text[max(0, r.start - 40):r.end + 20]))
            continue
        trail = src[len(src.rstrip(" .")):]  # "IV. 9." -> keep the final full stop
        sep = r.src[:lead]
        sep = " ; " if ";" in sep else ", " if "," in sep else " et " if "et" in sep or "&" in sep else ". "
        if not lead and re.search(r"\b(?:le|du|au)\s+$", text[:r.start]):
            new = new.replace("Psaumes ", "Psaume ", 1)  # "le Psaume 36:25"
        out.append((r.start, r.end, (sep if lead else "") + new + ("." if trail.strip() else "")))
        changes.append((*where, src, new))
        pos = r.end
    for s, e, new in reversed(out):
        text = text[:s] + new + text[e:]
    return text


def main(argv):
    apply = "--apply" in argv
    books = [a for a in argv if not a.startswith("--")]
    review, changes, touched = [], [], 0
    for f in sorted(DATA.glob("*/normalized/page_*.json")):
        book = f.parent.parent.name
        if books and book not in books:
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        before = json.dumps(d, ensure_ascii=False)
        for c in d.get("commentary") or []:
            if isinstance(c.get("french_commentary"), str):
                c["french_commentary"] = rewrite(c["french_commentary"], (f"{book}/{f.stem}", "c"), review, changes)
        for n in d.get("footnotes") or []:
            if isinstance(n, dict) and isinstance(n.get("text"), str):
                n["text"] = rewrite(n["text"], (f"{book}/{f.stem}", n.get("marker", "f")), review, changes)
        if json.dumps(d, ensure_ascii=False) != before:
            touched += 1
            if apply:
                f.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    rep = DATA.parent / "reports"
    rep.mkdir(exist_ok=True)
    (rep / "modernize_refs_review.tsv").write_text(
        "".join("\t".join(map(str, x)).replace("\n", " ") + "\n" for x in review), encoding="utf-8")
    if not apply:
        (rep / "modernize_refs_changes.tsv").write_text(
            "".join("\t".join(x) + "\n" for x in changes), encoding="utf-8")
    print(f"{len(changes)} rewritten in {touched} pages{'' if apply else ' (dry run)'}; "
          f"{len(review)} to review -> reports/modernize_refs_review.tsv")


if __name__ == "__main__":
    main(sys.argv[1:])
