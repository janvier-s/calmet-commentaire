"""Writing Calmet's citations out in French without Claude (footnotes.py, before the expand stage).

Reads a note made of citations only, such as "Aug. l. XXII. contra Faust. cap. 84. Theodoret.
quaest. 96. in Genes.", into authors, works and places (livre, chapitre, homélie...) using
footnote_glossary.txt, and writes it the way the earlier Claude expansion did:
"Saint Augustin, Contre Fauste, livre 22, chapitre 84 ; Théodoret, Question 96 sur la Genèse."
A quotation before the citations ("Spiritus quem ... etc. Plin. l. 2 c. 5.") is kept as is.
Anything it does not know (a word, an abbreviation, a construction) and expand() returns None:
the note goes to Claude.

  python3 footnote_expand.py test    the notes of Genesis 99-141 written out before, compared
"""
import re
import sys

import bible_refs as B
from paths import SCRIPTS

GLOSSARY = (SCRIPTS / "footnote_glossary.txt").read_text(encoding="utf-8")

# places in a work: abbreviation -> (French, plural, title: capitalised when it opens the citation)
PLACES = {}
for abbrs, fr, plural, title in [
    ("l lib liv livr", "livre", "livres", False),
    ("c cap ch chap capit", "chapitre", "chapitres", False),
    ("hom homil homel", "homélie", "homélies", True),
    ("ep epist epistol", "lettre", "lettres", True),
    ("serm ser sermo", "sermon", "sermons", True),
    ("orat", "discours", "discours", True),
    ("q qu quaest quaestion quest", "question", "questions", True),
    ("interrog", "question", "questions", True),
    ("tract", "traité", "traités", True),
    ("catech", "catéchèse", "catéchèses", True),
    ("art artic", "article", "articles", False),
    ("p pag", "page", "pages", False),
    ("n", "numéro", "numéros", False),  # not "num.": the Book of Numbers
    ("col", "colonne", "colonnes", False),
    ("tom", "tome", "tomes", False),
    ("part", "partie", "parties", False),
    ("sect", "section", "sections", False),
    ("not", "note", "notes", False),
    ("dist", "distinction", "distinctions", False),
    ("ode od", "ode", "odes", True),
    ("satyr sat", "satire", "satires", False),
    ("epigr", "épigramme", "épigrammes", True),
    ("eclog", "églogue", "églogues", True),
    ("haeres haer", "hérésie", "hérésies", False),
]:
    for a in abbrs.split():
        PLACES[a] = (fr, plural, title)
HIGH = {"livre", "tome", "partie"}  # "l. 5 de Civit.": a livre before a work belongs to it

# the article before a Bible book after "in" ("in Genes." = sur la Genèse)
ARTICLE = {"Genèse": "la ", "Exode": "l'", "Lévitique": "le ", "Nombres": "les ", "Deutéronome": "le ",
           "Juges": "les ", "Rois": "les ", "Paralipomènes": "les ", "Psaumes": "les ", "Proverbes": "les ",
           "Ecclésiaste": "l'", "Cantique des cantiques": "le ", "Sagesse": "la ", "Ecclésiastique": "l'",
           "Lamentations": "les ", "Actes": "les ", "Apocalypse": "l'", "Matthieu": "saint ", "Marc": "saint ",
           "Luc": "saint ", "Jean": "saint ", "Josué": "", "Ruth": "", "Job": "", "Tobie": "", "Judith": "",
           "Esther": "", "Isaïe": "", "Jérémie": "", "Ézéchiel": "", "Daniel": "", "Osée": "", "Joël": "",
           "Amos": "", "Jonas": "", "Michée": "", "Baruch": "", "Habacuc": "", "Zacharie": "", "Malachie": ""}
EPISTLE = {"Romains": "l'Épître aux Romains", "Galates": "l'Épître aux Galates", "Éphésiens": "l'Épître aux Éphésiens",
           "Hébreux": "l'Épître aux Hébreux", "Colossiens": "l'Épître aux Colossiens", "Philippiens": "l'Épître aux Philippiens",
           "Tite": "l'Épître à Tite", "Philémon": "l'Épître à Philémon"}

# words standing alone
WORDS = {"passim": "passim", "hic": "sur ce passage", "init": "au commencement", "initio": "au commencement",
         "ibid": "au même endroit", "ibidem": "au même endroit", "fin": "à la fin", "sub fin": "vers la fin",
         "in fin": "à la fin", "in hunc locum": "sur ce passage", "in loc": "sur ce passage", "in h l": "sur ce passage",
         "in princip": "au commencement", "in principio": "au commencement", "et seq": "et suivants", "et sequ": "et suivants",
         "et sq": "et suivants", "seq": "et suivants", "sequ": "et suivants", "et seqq": "et suivants",
         "seqq": "et suivants", "si lubet": "si l'on veut", "nov edit": "nouvelle édition", "loco citato": "à l'endroit cité",
         "loc cit": "à l'endroit cité", "in hebraeo": "dans l'Hébreu", "in hebr": "dans l'Hébreu",
         "in hebraeo textu": "dans le texte hébreu", "in graeco": "dans le Grec", "loco cit": "à l'endroit cité", "ad finem": "à la fin", "in fine": "à la fin"}
CITIES = {"basil": "Bâle", "cantabrig": "Cambridge", "genev": "Genève", "paris": "Paris", "rom": "Rome", "lugd": "Lyon",
          "lugdun": "Lyon", "colon": "Cologne", "amstel": "Amsterdam", "amstelod": "Amsterdam", "francof": "Francfort",
          "oxon": "Oxford", "lips": "Leipzig", "venet": "Venise", "antverp": "Anvers", "lond": "Londres"}
SEE = {"vid", "vide", "videsis", "voyez", "voy", "voi", "voiez", "voir", "cf", "conf", "confer"}
OTHERS = {"et alii": "et d'autres", "et alios": "et d'autres", "et al": "et d'autres", "alii": "et d'autres",
          "et caeteri": "et d'autres", "et caet": "et d'autres", "et plerique": "et la plupart",
          "et plures alii": "et plusieurs autres", "et alii plures": "et plusieurs autres"}
NOT_AUTHORS = {"Hebr", "Heb", "70", "LXX", "Theod", "Greg", "Justin", "Jer", "Cyrill", "Bibliot", "Bibl"}
CLASSICAL_WORKS = {"Antiquités judaïques", "Guerre des Juifs", "Contre Apion", "Énéide", "Géorgiques", "Églogues", "Iliade",
                   "Odyssée", "Métamorphoses", "Fastes", "Cyropédie"}  # in the glossary's classical authors
NOT_PREFIX = {"philosoph", "philosophi", "philosophia", "hebraeor", "hebraeo", "hebraeorum", "hebraei", "hebraice", "origenian", "iustinian", "basilid", "ambrosiast", "augustal", "hieronymian", "plinian", "ciceronian"}


def key(s):
    """'Hexaëmer.' -> 'hexaemer': lower case, no accents, no full stop."""
    if not isinstance(s, str):
        return ""
    return B.plain(s).rstrip(".").replace("j", "i")


def entries():
    """The glossary's 'abbreviation = French' entries, by section; an abbreviation with two readings
    ('or', or a note in brackets naming where it applies) is left out."""
    section, out = None, []
    for line in GLOSSARY.splitlines():
        if line.startswith("## "):
            section = line[3:].strip().split()[0].lower()
            continue
        if line.startswith("#") or "=" not in line:
            continue
        for left, right in re.findall(r"(\S.*?)\s=\s(.*?)(?=\s{3,}\S[^=]*?\s=\s|$)", line.strip()):
            if " or" in right or "(or" in right:
                continue
            right = re.sub(r"\s*\([^)]*\)", "", right).strip()
            for a in left.split(" / "):
                a = a.strip()
                opt = re.fullmatch(r"(.*?)\s*\((\w+)\)", a)  # "de Civit. (Dei)": with or without
                if opt:
                    out += [(section, opt.group(1), right), (section, f"{opt.group(1)} {opt.group(2)}", right)]
                elif "(" not in a:
                    out.append((section, a, right))
    return out


PHRASES = {}  # tuple of keys -> (kind, French)
DOTTED = set()  # words the glossary gives abbreviated ("Strom."): "Stromat." is the same
NOT_NAMES = {key(a) for a in NOT_AUTHORS}
for section, abbr, fr in entries():
    words = tuple(key(w) for w in re.findall(r"[^\s.]+\.?", abbr))
    DOTTED.update(key(w) for w in re.findall(r"[^\s.]+\.", abbr))
    if section == "words" or not words:
        continue
    if section == "works":
        kind = "in" if words[0] == "in" else "work"
    elif section in ("fathers", "commentators", "classical", "versions", "more"):
        if abbr.rstrip(".") in NOT_AUTHORS:
            continue
        kind = "work" if fr in CLASSICAL_WORKS else "author"
    else:
        kind = "work" if section == "titles" else "author"
    if words not in PHRASES:
        PHRASES[words] = (kind, fr)
        name = tuple(key(w) for w in fr.removeprefix("saint ").split())  # the name written out ("Bonfrère.")
        if kind == "author" and len(fr.split()) <= 4 and not (len(name) == 1 and name[0] in NOT_NAMES):
            PHRASES.setdefault(tuple(key(w) for w in fr.removeprefix("saint ").split()), (kind, fr))
PHRASES.update({
    ("cyrill",): ("author", "saint Cyrille d'Alexandrie"), ("cyrill", "alex"): ("author", "saint Cyrille d'Alexandrie"),
    ("cyrill", "ieros"): ("author", "saint Cyrille de Jérusalem"), ("cyrill", "hierosol"): ("author", "saint Cyrille de Jérusalem"),
    ("diodor",): ("author", "Diodore de Sicile"), ("diod",): ("author", "Diodore de Sicile"),
    ("diodor", "sicul"): ("author", "Diodore de Sicile"), ("diod", "sicul"): ("author", "Diodore de Sicile"),
    ("diod", "de", "sicile"): ("author", "Diodore de Sicile"), ("diodor", "tars"): ("author", "Diodore de Tarse"),
    ("idem",): ("author", "le même"), ("id",): ("author", "le même"),
    # never a Bible reference here (bible_refs reads "Hebr. 5. 4." first): the Hebrew text
    ("hebr",): ("author", "l'Hébreu"), ("heb",): ("author", "l'Hébreu"), ("hebraei",): ("author", "les Hébreux"),
    ("hebr", "recent"): ("author", "les Hébreux modernes"), ("rab", "salom"): ("author", "Rabbi Salomon"),
    ("rabb", "salom"): ("author", "Rabbi Salomon"), ("rabbi", "salom"): ("author", "Rabbi Salomon"),
    ("antiq", "vulg"): ("author", "l'ancienne Vulgate"), ("antiqua", "vulg"): ("author", "l'ancienne Vulgate"), ("greg", "mag"): ("author", "saint Grégoire le Grand"),
})
MAXLEN = max(map(len, PHRASES))
SAINT = re.compile(r"^(?:saint|s|d|sanct|b|beat)$")

TOKEN = re.compile(r"[A-Za-zÀ-ÿæœÆŒſ'’]+\.?|\d+(?::\d+)?\.?|[,;:]|\S")
ROMAN_UP = re.compile(r"[IVXLC]+")
ROMAN_LOW = re.compile(r"[ivxlc]{2,}|[ivx]")


def number(tok):
    t = tok.rstrip(".")
    if re.fullmatch(r"\d+", t):
        return int(t)
    if ROMAN_UP.fullmatch(t) or ROMAN_LOW.fullmatch(t):
        return B.num(t)
    return None


class Unknown(Exception):
    pass


def real_ref(r):
    """'Malv.' (Malvenda) is read by bible_refs as Mal. V.: the book's letters must be an abbreviation."""
    m = re.match(r"\W*(?:(?:[1-4]|I{1,3}|IV)[\s.,]+)?([A-Za-zÀ-ÿſæœÆŒ]+)", r.src)
    # and a book is written with a capital, its chapter exists ("num. 196" is numéro 196)
    return bool(m) and m.group(1)[0].isupper() and B.ABBR.get(B.plain(m.group(1))) is not None \
        and B.exists(r) is not False


def words_of(text):
    """[(start, end, token)], a Bible reference as one token ('bible', rendered)."""
    refs = {r.start: r for r in B.find_refs(text) if real_ref(r)}
    out, pos = [], 0
    for m in TOKEN.finditer(text):
        if m.start() < pos:
            continue
        r = refs.get(m.start())
        if r:
            out.append((r.start, r.end, ("bible", r)))
            pos = r.end
            continue
        out.append((m.start(), m.end(), m.group()))
        pos = m.end()
    return out


def lookup(toks, i):
    """The longest glossary phrase at toks[i]: (kind, French, tokens used)."""
    ks = []
    for t in toks[i:i + MAXLEN]:
        if not isinstance(t, str) or not re.match(r"[A-Za-zÀ-ÿæœÆŒſ]", t):
            break
        ks.append(key(t))
    for n in range(len(ks), 0, -1):
        hit = PHRASES.get(tuple(ks[:n])) or PHRASES.get(tuple(k.replace("f", "s") for k in ks[:n]))
        if hit:
            return hit + (n,)
    # "Stromat." = "Strom.", "contra Celsum" = "contra Cels.": each word the glossary's, written longer
    best = None
    for p, hit in PHRASES.items():
        if len(p) <= len(ks) and (best is None or len(p) > best[2]) and all(
                k == w or (len(w) >= 4 and k.startswith(w) and len(k) - len(w) <= 4 and k not in NOT_PREFIX
                           and w in DOTTED and (n or toks[i].endswith(".")))
                for n, (k, w) in enumerate(zip(ks, p))) and any(k != w for k, w in zip(ks, p)):
            best = hit + (len(p),)
    return best


_LATIN = set()
LATIN_STOP = {"et", "c", "l", "lib", "cap", "apud", "in", "ad", "ex", "de", "contra", "adversus", "advers", "cum", "vide", "vid"}


def latin(w):
    """A whole Latin word (it is in the Vulgate), not an abbreviation."""
    if not _LATIN:
        for name, (vul, _, _) in B.BOOK.items():
            for t in B.vulgate(vul).values():
                _LATIN.update(re.findall(r"[a-z]+", B.plain(t).replace("j", "i")))
    return key(w) in _LATIN


def latin_title(toks, i):
    """'de Carne Christi' -> ('De carne Christi', tokens used): a Latin title of whole words."""
    ws, j = [], i + 1
    while j < len(toks) and isinstance(toks[j], str) and re.fullmatch(r"[A-Za-zæœÆŒ]+\.?", toks[j]) \
            and key(toks[j]) not in LATIN_STOP and latin(toks[j]) and not PLACES.get(key(toks[j])):
        if toks[j].endswith(".") and j + 1 < len(toks):  # "de animal. part.": cut short, not a title
            return None
        ws.append(toks[j].rstrip("."))
        j += 1
    if not ws:
        return None
    return " ".join(["De"] + [w if w[0].isupper() else w for w in ws]), j - i


def numbers(toks, i):
    """'84. 85. 86.' / '10 et 34' / '1, 2, 3' -> ([84, 85, 86], ', ' or ' et ', tokens used)."""
    ns, seps, j, roman = [], [], i, None
    while j < len(toks):
        n = number(toks[j]) if isinstance(toks[j], str) else None
        if n is None or roman is not None and (roman != (not toks[j][0].isdigit()) or len(toks[j].rstrip(".")) == 1
                                               and toks[j][0].islower()):
            break  # "Chap. VI. 1.", "Satyr. 3. v. 78.": a Roman and an Arabic number are not one list
        roman = not toks[j][0].isdigit()
        ns.append(n)
        j += 1
        k = j
        if k < len(toks) and toks[k] in (",", "et", "&"):
            k += 1
        if k < len(toks) and isinstance(toks[k], str) and number(toks[k]) is not None \
                and not (k + 1 < len(toks) and (toks[k + 1] == ":" or isinstance(toks[k + 1], str)
                                                and toks[k + 1].endswith(".") and key(toks[k + 1]) in PLACES)):
            if roman != (not toks[k][0].isdigit()):
                break
            seps.append(" et " if toks[j] in ("et", "&") else ", " if toks[j] == "," else ".")
            j = k
            continue
        break
    sep = " et " if seps and seps[-1] == " et " else "." if seps and set(seps) == {"."} else ", "
    return ns, sep, j - i


class Parser:
    """parse() under way: the tokens, the one reached (i) and the citations read so far. Each step
    reads the token at i, or the few starting there, and moves i past them; it returns False when
    the token is not its kind."""

    def __init__(self, text):
        self.toks = [t for _, _, t in words_of(text)]
        self.cites, self.cur, self.lead, self.i = [], None, "", 0
        self.pending = None  # a number before its place ("1. part.")
        self.hit = None  # the glossary phrase at i (lookup)

    def new(self, author=None, how=" ; "):
        self.cur = dict(lead=how, author=author, groups=[[]])
        self.cites.append(self.cur)

    def item(self, kind, val):
        if self.cur is None:
            self.new()
        self.cur["groups"][-1].append((kind, val))

    def at(self, j):
        """The key of token j, "" past the end or for a Bible reference."""
        return key(self.toks[j]) if j < len(self.toks) and isinstance(self.toks[j], str) else ""

    def number_at(self, j):
        return j < len(self.toks) and isinstance(self.toks[j], str) and number(self.toks[j]) is not None

    def bible(self, t, k):
        if not isinstance(t, tuple):
            return False
        r, cur = t[1], self.cur
        if cur and cur["groups"][-1] and cur["groups"][-1][-1] == ("in", None):
            cur["groups"][-1].pop()
            book = r.book
            if r.name == "Psaumes":
                self.item("in", f"sur le Psaume {r.render(with_book=False)}")
            else:
                self.item("in", f"sur {ARTICLE.get(book, '')}{book} {r.render(with_book=False)}")
        else:
            if not (cur and cur["author"] is None and not any(cur["groups"])):
                self.new(None, " ; " if self.cites else "")
            self.cur["author"] = r.render()
        self.i += 1
        return True

    def punctuation(self, t, k):
        if t in (",", ";", ":"):
            self.i += 1
            return True
        if t in ("etc.", "etc", "&c."):
            self.item("word", "etc.")
            self.i += 1
            return True
        return False

    def ita(self, t, k):
        """"Ita Cornel." = Ainsi Cornelius a Lapide; "Ita et" = de même."""
        if k != "ita":
            return False
        same = self.at(self.i + 1) == "et"
        if self.cites:
            self.new(None, " ; de même " if same else " ; ainsi ")
        else:
            self.lead = "De même " if same else "Ainsi "
        self.i += 2 if same else 1
        return True

    def see(self, t, k):
        if k not in SEE:
            return False
        toks, i = self.toks, self.i
        j = i + 1 + (i + 1 < len(toks) and toks[i + 1] == ",")
        if j + 1 < len(toks) and key(toks[j]) == "si" and key(toks[j + 1]) in ("lubet", "placet", "libet"):
            if self.cites:
                self.new(None, ". Voyez, si l'on veut, ")
            else:
                self.lead = "Voyez, si l'on veut, "
            self.i = j + 2 + (j + 2 < len(toks) and toks[j + 2] == ",")
            return True
        also = i + 1 < len(toks) and key(toks[i + 1]) in ("et", "etiam", "aussi")
        if self.cites:
            self.new(None, ". Voyez aussi " if also else ". Voyez ")
        else:
            self.lead = "Voyez aussi " if also else "Voyez "
        self.i += 2 if also else 1
        return True

    def phrase(self, t, k):
        """"et alii", "passim", "hic"...: OTHERS opens a citation, WORDS goes in the current one."""
        joined = " ".join(key(x) for x in self.toks[self.i:self.i + 4] if isinstance(x, str)) + " "
        hit = next((o for o in sorted(OTHERS, key=len, reverse=True) if joined.startswith(o + " ")), None)
        if hit:
            self.new(OTHERS[hit], " ; ")
            self.i += len(hit.split())
            return True
        hit = next((w for w in sorted(WORDS, key=len, reverse=True) if joined.startswith(w + " ")), None)
        if hit:
            self.item("word", WORDS[hit])
            self.i += len(hit.split())
            return True
        return False

    def link(self, t, k):
        """"apud", "ex", "et apud", "et vid.", "et": how the next citation follows."""
        toks, i = self.toks, self.i
        if k in ("apud", "dans"):
            self.new(None, ", dans ")
            self.i += 1
        elif k in ("ex", "d'apres"):
            self.new(None, ", d'après ")
            self.i += 1
        elif k not in ("et", "&") or i + 1 >= len(toks):
            return False
        elif self.at(i + 1) in ("apud", "dans"):
            self.new(None, ", et dans ")
            self.i += 2
        elif self.at(i + 1) in SEE:
            self.new(None, " ; et voyez ")
            self.i += 2
        else:
            nxt = lookup(toks, i + 1)
            if nxt and nxt[0] == "author" or SAINT.match(self.at(i + 1)) or isinstance(toks[i + 1], tuple):
                self.new(None, " ; et ")
            elif self.cur and self.cur["groups"][-1]:
                self.cur["groups"].append([])
            self.i += 1
        return True

    def saint(self, t, k):
        """"S. Aug.": the author says it."""
        if SAINT.match(k) and self.i + 1 < len(self.toks) and (lookup(self.toks, self.i + 1) or (None,))[0] == "author":
            self.i += 1
            return True
        return False

    def in_book(self, t, k):
        """"in Genes." = sur la Genèse; "homil. 3 in Hexaëmer." = Homélie 3 sur l'Hexaméron."""
        toks, i = self.toks, self.i
        if k != "in" or i + 1 >= len(toks):
            return False
        nb = toks[i + 1]
        if isinstance(nb, tuple):
            self.item("in", None)
            self.i += 1
            return True
        pk = B.plain(nb).rstrip(".")
        name = B.ABBR.get(pk) or next((v for a, v in B.ABBR.items() if len(a) >= 4 and pk.startswith(a)
                                       and len(pk) - len(a) <= 3), None)
        if name and (lookup(toks, i) or (None,))[:1] != ("in",):
            if name in EPISTLE:
                self.item("in", f"sur {EPISTLE[name]}")
            elif name in ARTICLE:
                self.item("in", f"sur {ARTICLE[name]}{name}")
            else:
                raise Unknown(f"in {nb}")
            self.i += 2
            return True
        hit = lookup(toks, i + 1)
        if hit and hit[0] == "work":  # alone, Hexaméron
            self.item("in-work", hit[1])
            self.i += 1 + hit[2]
            return True
        return False

    def place_at(self, t, k):
        """The place (livre, chapitre...) token i names, if it is one: (French, plural, title)."""
        toks, i = self.toks, self.i
        if t == "§":
            return ("§", "§", False)
        if self.hit and self.hit[2] >= 2 and self.hit[0] != "author":
            return None
        place = PLACES.get(k) if t.endswith(".") or k in ("ode",) or self.number_at(i + 1) else None
        if k in ("verset", "vers", "v") and i + 1 < len(toks) and isinstance(toks[i + 1], str) \
                and toks[i + 1][:1].isdigit() and self.cur and self.cur["author"] and not re.search(r"\d", self.cur["author"]) \
                and any(k2 in ("place", "work") for k2, _ in self.cur["groups"][-1]):
            place = ("vers", "vers", False)  # "Ovid. Metam. lib. 8. verset 749." = vers 749
        # "Jun. Pag. Mont.": a capitalised name the glossary knows is the author, not "page"
        if place and t[0].isupper() and (self.hit or (None,))[0] == "author" and not self.number_at(i + 1):
            place = None
        return place

    def place(self, t, k):
        """"l. 4.", "cap. 21. & 22.", "hom. 3": a place in the work, with its numbers."""
        if not isinstance(t, str):
            return False
        self.hit = lookup(self.toks, self.i)
        place = self.place_at(t, k)
        if t == "§":
            t = "§."
            if self.i + 1 < len(self.toks) and self.toks[self.i + 1] == ".":
                self.i += 1
        if not place or k in ("c", "l", "p", "n", "q") and not t.endswith("."):
            return False
        toks, i = self.toks, self.i
        if k in ("c", "l") and self.at(i + 1) in ("ult", "ultim"):
            self.item("place", ("dernier " + place[0], True))
            self.i += 2
            return True
        m = re.fullmatch(r"(\d+):(\d+)\.?", toks[i + 1]) if i + 1 < len(toks) and isinstance(toks[i + 1], str) else None
        if m and place[0] == "livre":  # "Plin. l. 7:12" = livre 7, chapitre 12
            self.item("place", (f"livre {m.group(1)}", False))
            self.item("place", (f"chapitre {m.group(2)}", False))
            self.i += 2
            return True
        ns, sep, used = numbers(toks, i + 1)
        if self.pending is not None:
            if ns:
                raise Unknown(str(self.pending))  # "Plin. 13. cap. 3.": a number left over
            ns, sep, used = [self.pending], ", ", 0
        self.pending = None
        if not ns and place[0] == "livre" and self.at(i + 1) in ("de", "contra", "adversus", "advers", "in"):
            self.i += 1  # "lib. de Baptismo" = De baptismo
            return True
        if not ns:
            raise Unknown(t)
        word = place[1] if len(ns) > 1 else place[0]
        if sep == "." and place[0] == "livre" and len(ns) == 2:  # "Plin. lib. 6. 28." = livre 6, chapitre 28
            self.item("place", (f"livre {ns[0]}", False))
            ns, word = ns[1:], "chapitre"
        elif sep == "." and place[0] == "livre":
            raise Unknown(t)
        sep = ", " if sep == "." else sep
        ns = list(map(str, ns))  # "cap. 21. & 22." -> "chapitres 21 et 22"; "1. 2. 3." -> "1, 2 et 3"
        self.item("place", (f"{word} {', '.join(ns[:-1]) + ' et ' + ns[-1] if len(ns) > 1 else ''.join(ns)}", place[2]))
        self.i += 1 + used
        return True

    def after_reference(self, t, k):
        """Another chapter of the book just cited, with no book: "Gen. 3:4 ; 5:6", "Osee IV. 15. et X. 5."."""
        toks, i, cites = self.toks, self.i, self.cites
        if not isinstance(t, str) or not cites or any(cites[-1]["groups"]):
            return False
        author = cites[-1]["author"] or ""
        m = re.fullmatch(r"(\d+):(\d+)\.?", t)
        if m and re.search(r"\d:\d", author):
            vs, j = [int(m.group(2))], i + 1
            while j + 1 < len(toks) and toks[j] in (",", "et") and isinstance(toks[j + 1], str) \
                    and re.fullmatch(r"\d+\.?", toks[j + 1]) and not (j + 2 < len(toks) and isinstance(toks[j + 2], str)
                                                                    and re.fullmatch(r"\d+:\d+\.?", toks[j + 2])):
                vs.append(int(toks[j + 1].rstrip(".")))
                j += 2
            self.new(f"{m.group(1)}:{B.fmt_verses(vs)}", " ; ")
            self.i = j
            return True
        n = number(t)
        if n is not None and not t[0].isdigit() and re.search(r"\d:\d|\D \d+$", author) \
                and i + 1 < len(toks) and isinstance(toks[i + 1], str) \
                and toks[i + 1][:1].isdigit() and not toks[i + 1].endswith(":"):
            vs, sep, used = numbers(toks, i + 1)  # chapter 10 of the same book
            self.new(f"{n}:{B.fmt_verses(vs)}", " ; ")
            self.i += 1 + used
            return True
        return False

    def bare_number(self, t, k):
        """A number before its place ("1. part."), or after a work ("Strom. 5." = Stromates 5)."""
        n = number(t) if isinstance(t, str) else None
        if n is None:
            return False
        toks, i = self.toks, self.i
        if i + 1 < len(toks) and PLACES.get(self.at(i + 1)):
            self.pending = n
            self.i += 1
            return True
        g = self.cur["groups"][-1] if self.cur else []
        if not (g and g[-1][0] == "work"):
            raise Unknown(t)
        ns, sep, used = numbers(toks, i)
        g[-1] = ("work", f"{g[-1][1]} {(', ' if sep == '.' else sep).join(map(str, ns))}")
        self.i += used
        if self.number_at(self.i):
            raise Unknown(toks[self.i])  # "Æneid. VII. V. 176.", "Antiq. xx. 5.": what is which?
        return True

    def glossary(self, t, k):
        """An author, a work or "in ..." from the glossary, or a Latin title ("de Carne Christi")."""
        hit = self.hit
        if k == "de" and not hit:
            lt = latin_title(self.toks, self.i)
            if lt:
                hit = ("work",) + lt
        if not hit:
            return False
        kind, fr, used = hit
        cur = self.cur
        if kind == "author":
            if cur and cur["author"] is None and not any(cur["groups"]):  # after "apud", "vid.", "et"
                cur["author"] = fr
            else:
                self.new(fr, " ; " if self.cites else "")
        elif kind == "in":
            self.item("in", fr)
        else:
            g = cur["groups"][-1] if cur else []
            if any(x[0] == "work" for x in g):  # a second work: "l. 4 Confess. c. 3. lib. 5 de Civit."
                moved = []
                while g and g[-1][0] == "place" and g[-1][1][0].split()[0] in HIGH:
                    moved.insert(0, g.pop())
                cur["groups"].append(moved)
                cur.setdefault("split", set()).add(len(cur["groups"]) - 1)
            self.item("work", fr)
        self.i += used
        return True

    def edition(self, t, k):
        """"edit. Paris. 1675." = édition de Paris 1675."""
        toks, i, cur = self.toks, self.i, self.cur
        if k in ("edit", "edition") and self.at(i + 1) in CITIES:
            self.item("word", f"édition de {CITIES[self.at(i + 1)]}")
            self.i += 2
            return True
        if isinstance(t, str) and re.fullmatch(r"\d{4}\.?", t) and cur and cur["groups"][-1] \
                and "édition" in str(cur["groups"][-1][-1]):
            self.item("word", t.rstrip("."))
            self.i += 1
            return True
        return False

    STEPS = (bible, punctuation, ita, see, phrase, link, saint, in_book, place, after_reference, bare_number,
             glossary, edition)

    def step(self):
        t = self.toks[self.i]
        k = key(t) if isinstance(t, str) else ""
        self.hit = None
        if not any(s(self, t, k) for s in self.STEPS):
            raise Unknown(t if isinstance(t, str) else t[1].src)


def parse(text):
    """Citations: [{'lead': '', 'author': str|None, 'groups': [[('work'|'place'|'in'|'word', str)]]}]."""
    p = Parser(text)
    while p.i < len(p.toks):
        p.step()
    if p.pending is not None:
        raise Unknown(str(p.pending))
    return p.lead, p.cites


TITLES = {fr for fr, plural, title in PLACES.values() if title} | {plural for fr, plural, title in PLACES.values() if title}


def render_group(g):
    works = [v for k, v in g if k == "work"]
    ins = [v for k, v in g if k == "in" and v]
    places = [v for k, v in g if k == "place"]
    words = [v for k, v in g if k == "word"]
    if any(k == "in" and not v for k, v in g):
        raise Unknown("in")
    parts = []
    titled = [p for p in places if p[1] and not p[0].startswith("dernier")]
    in_works = [v for k, v in g if k == "in-work"]
    if (ins or in_works) and len(titled) == 1 and not works:  # "homil. 1. in Genes." = Homélie 1 sur la Genèse
        places.remove(titled[0])
        w = ins.pop(0) if ins else in_works.pop(0)
        if not w.startswith("sur "):
            w = "sur l'" + w if w[0] in "AEIOUÉH" else "sur " + w[0].lower() + w[1:]
        parts.append(f"{titled[0][0]} {w}")
    lead = places.pop(0)[0] if places and g[0][0] == "place" and g[0][1][1] and places[0] is g[0][1] else None
    if lead:  # "Orat. II. de Pascha" = Discours 2, De Pascha
        parts.append(lead)
    parts += works + in_works + ins
    if "au même endroit" in words:  # "Id. ibid. c. 1." = Le même, au même endroit, chapitre 1
        words.remove("au même endroit")
        parts.append("au même endroit")
    for p, title in places:
        parts.append(p)
    if parts and parts[0].split()[0] in TITLES:  # a homily, a letter... opening its group: "Homélie 1"
        parts[0] = parts[0][0].upper() + parts[0][1:]
    out = ", ".join(parts)
    for w in words:
        out += (" " if out and w == "et suivants" else ", " if out else "") + w
    return out


TITLES_CAP = {t[0].upper() + t[1:] for t in TITLES}
DEFAULT_WORK = {"Pline": "Histoire naturelle"}  # "Plin. l. 2 c. 5." = Pline, Histoire naturelle, livre 2, chapitre 5


def render(lead, cites):
    out = lead
    bare = all(not any(g for g in c["groups"] if any(k != "word" for k, _ in g)) for c in cites)
    for n, c in enumerate(cites):
        g0 = c["groups"][0]
        if c["author"] in DEFAULT_WORK and g0 and not any(k in ("work", "in") for k, _ in g0) and g0[0][0] == "place":
            g0.insert(0, ("work", DEFAULT_WORK[c["author"]]))
        body = []
        for gi, g in enumerate(c["groups"]):
            s = render_group(g)
            if s:
                if gi in c.get("split", ()):
                    joint = "; "
                else:  # "et homil. 1." = " ; et Homélie 1", "et l. 12 Confess." = ", et Confessions"
                    joint = "; et " if s.split()[0] in TITLES_CAP else "et "
                body.append((joint if body else "") + s)
        text = ", ".join(body).replace(", ; ", " ; ")
        head = c["author"] or ""
        if not head and not text:
            continue
        sep = c["lead"] if n else c["lead"].lstrip(",; ")
        if head == "saint Cyrille d'Alexandrie" and "atéchèse" in text:
            head = "saint Cyrille de Jérusalem"
        if head and text == "etc.":
            piece = f"{head} etc." if re.search(r"\d:\d", head) else f"{head} ; etc." if bare and n else f"{head}, etc."
        elif head and text:
            piece = f"{head} {text}" if text.startswith("et suivants") else f"{head}, {text}"
        else:
            piece = head or text
        out += sep + piece
    out = re.sub(r"\s+", " ", out).strip()
    if not out:
        return None
    out = out[0].upper() + out[1:]
    return out if out.endswith((".", "?", "!")) else out + "."


ABBR_LEFT = re.compile(r"(?<![\w])([A-Za-zÀ-ÿæœÆŒſ]{1,14})\.(?=[\s,;:)]|$)")


def expand(text, abbrev):
    """The note written out, or None. `abbrev`: the set of known abbreviations (footnotes.ABBREV);
    a quotation before the citations may not contain any."""
    t = text.strip()
    if "[" in t or "(" in t or "\n" in t.strip():
        return None
    # "_" is the scan's italics: dropped in the citations, kept in a quotation
    try:
        return render(*parse(t.replace("_", "")))
    except (Unknown, IndexError, KeyError, TypeError):
        pass
    # a quotation, then the citations: try each sentence end, the longest citation first
    for m in re.finditer(r"[.!?;]_?\s+(?=_?[A-ZÀ-Ý])|etc\.\s+|\s---?\s+", t):
        head, tail = t[:m.end()].rstrip(), t[m.end():].replace("_", "")
        if head.count("_") % 2:
            continue
        if any(B.plain(w) in abbrev and w.lower() != "etc" for w in ABBR_LEFT.findall(head)) or B.find_refs(head):
            continue
        if re.search(r"\b[IVXLC]{2,}\.\s*\d", head):  # "Pseaumes_ LXVI. 2.": references left in it
            continue
        # a citation, not a quotation: "Ita Hugues à Saint Victor.", "... Ita 70.", "_Vide Genes._ XX. I."
        if re.search(r"\b(?:Ita|Vid|Vide|Apud|LXX|Sept|Vulg|Hebr)\b|\b70\.", head):
            continue
        if not re.search(r"[א-תͰ-Ͽἀ-῿]", head) and len(re.findall(r"\b[a-zà-ÿæœ]{2,}\b", head)) < 3:
            continue
        if len(head.split()) < 4 and not re.search(r"[א-תͰ-Ͽἀ-῿]", head):  # "Ludov. de Dieu.": not a quotation
            continue
        last = head.split()[-1]
        if re.fullmatch(r"[A-ZÀ-Ý][a-zà-ÿæœ]+\.", last) and not latin(last):  # "... Scoliast.": a name cut short
            continue
        if not re.match(r"(?:Vid|Vide|Voyez|Apud|S\.|Saint|D\.)?\s*[A-ZÀ-Ý]", tail):
            continue
        try:
            lead, cites = parse(tail)
        except (Unknown, IndexError, KeyError, TypeError):
            continue
        if not cites or cites[0]["author"] is None and lead != "Voyez ":
            continue
        out = render(lead, cites)
        if out:
            return f"{head} {out}"
    return None


WRITTEN_OUT = "37eaf90ac"  # the commit with Genesis 99-141's notes written out by Claude


def test():
    """Compare with the notes of Genesis 99-141 that Claude wrote out (git: before and after)."""
    import json, subprocess
    import footnotes as F
    from paths import DATA

    def at(rev, f):  # "./": the path from data/, wherever the repository's root is
        return json.loads(subprocess.run(["git", "show", f"{rev}:./{f}"], capture_output=True, text=True, cwd=DATA).stdout)
    same = diff = none = 0
    for p in range(99, 142):
        f = f"01_genese/normalized/page_{p:04d}.json"
        old, new = at(f"{WRITTEN_OUT}~1", f), at(WRITTEN_OUT, f)
        before = {n["marker"]: n["text"] for n in old.get("footnotes") or []}
        for n in new.get("footnotes") or []:
            o = before.get(n["marker"])
            if not o or o == n["text"] or not F.needs_expansion(o) or re.search(r"[א-תͰ-Ͽἀ-῿]", o):
                continue
            got = expand(o, F.ABBREV)
            want = re.sub(r" ;\n", " ; ", n["text"])
            if got is None:
                none += 1
                try:
                    parse(o)
                    why = "?"
                except Exception as e:
                    why = repr(e)
                print(f"--  {o[:110]}\n    ({why})")
            elif got == want:
                same += 1
            else:
                diff += 1
                print(f"≠   {o[:110]}\n    got:  {got[:160]}\n    want: {want[:160]}")
    print(f"same {same}, different {diff}, left to Claude {none}")


if __name__ == "__main__":
    if sys.argv[1:] == ["test"]:
        test()
    else:
        print(expand(" ".join(sys.argv[1:]), __import__("footnotes").ABBREV))
