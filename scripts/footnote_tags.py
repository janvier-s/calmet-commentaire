"""Footnote tags: what each footnote holds (Hebrew, a Father, a Bible verse …), to review them by kind.

Each footnote gets `"tags": [...]` in normalized/, and `"titles": [{"fr", "original"}]` for the works
it names (calmet.py exports only the text, so both stay out of the site; the editor shows them
only with "Tags" on).
  1. rules, free:
     hebrew, greek, uncertain    from the text
     verse                       the Bible references ("Chapitre 36." too: the volume's own book)
     fathers, rabbis, versions, classical, commentators
                                 the names in footnote_glossary.txt and footnote_names.txt, the
                                 works in footnote_names.txt; "Le même", "Ibid." take the author
                                 tags of the note before
     title                       a work of footnote_names.txt (its original title in "titles")
     latin                       a word of the Vulgate that is not French (two if capitalized)
     versions                    also "70." (the Septuagint)
     abbrev                      an abbreviation not written out (lib., cap., Chrysost.)
     old-ref                     a Bible reference not modernized (Marc. XV. 21.)
     bad-ref                     a Bible reference to a verse the Vulgate does not have
     ibid                        "Ibid.", "Le même", "Au même endroit"
  2. model: the notes the rules leave unclear (prose that may explain, a name no list knows)
     are asked in batches, agy first, then Haiku for what agy does not answer. Answers are
     cached by the note's text (cache/footnote_tags_cache.json).
The tagger's own result is kept in docs/footnotes/tags_auto.json: on a new run, the tags added
or taken away by hand in the editor since are kept as they are.

footnote_names.txt (`names` builds it, then read and correct it by hand; lines already in it are
never changed): the works and authors the footnotes name in French, found in the notes, each
asked of Haiku with the note as Calmet printed it (raw_json) beside its written-out form:
    title: La Cité de Dieu = De civitate Dei | Augustin | fathers
    author: Ferrand | commentators
    other: Alius
"  # CHECK: …" at the end of a line marks something to look at (`names` sets it; ignored when read).

Usage: python3 footnote_tags.py run <volume|book|all> ... [--local] [--model agy|haiku|both]
       python3 footnote_tags.py names            (all volumes)
       python3 footnote_tags.py stats <volume|book|all> ...
AGY_MODEL picks agy's model, as for footnotes.py.
"""
import asyncio, json, re, sys
from collections import Counter, defaultdict

import bible_refs as B
import footnotes as F
from calmet import _fold, vulgate_words
from paths import DOCS, HUNSPELL_CACHE, SCRIPTS, pages, volumes_of

AUTHORS = ("fathers", "rabbis", "versions", "classical", "commentators")
TAGS = ("hebrew", "greek", "verse", *AUTHORS, "title", "latin", "explanation",
        "abbrev", "old-ref", "bad-ref", "ibid", "uncertain")
CACHE = SCRIPTS / "cache" / "footnote_tags_cache.json"
NAMES_FILE = SCRIPTS / "footnote_names.txt"
AUTO = DOCS / "footnotes" / "tags_auto.json"
BATCH, PARALLEL = 100, 4
F.BACKEND = "claude"  # F.claude() is Haiku here; agy is called by name

# ---- the names ---------------------------------------------------------------------

# glossary section -> tag; Josèphe and Philon count as Jewish sources, with the rabbis
SECTIONS = {"Fathers and church writers": "fathers", "Commentators": "commentators", "Classical authors": "classical"}
VERSIONS = {"Hébreu", "Septante", "Symmaque", "Aquila", "Théodotion", "Syriaque", "Arabe", "Chaldéen", "Samaritain",
            "Vulgate", "Grec", "Hexaples", "Psautier", "Complute", "Targum", "Onkelos", "Jonathan",
            "paraphrase chaldaïque", "Bible de Zurich"}
RABBIS = {"rabbins", "Rabbi", "Kimhi", "Maïmonide", "Aben Ezra", "Talmud", "Josèphe", "Philon", "Jarchi"}
MOVE = {"Josèphe": "rabbis", "Philon": "rabbis"}
# one name for several people: not enough alone to say which kind of author
AMBIGUOUS = {"Joseph", "Denys", "Hugues", "Jean", "Pierre", "Paul", "Grégoire", "Cyrille", "Justin", "Théodore", "Marc"}
# abbreviations too short or too common to name an author alone
DROP = {"Justin", "Joseph", "Jer", "Est", "Theod", "Mont", "Mas", "Stat", "Fast", "Mart", "Clar", "Leo", "Muis",
        "Fag", "Vat", "Jun", "Pag", "Tir", "Lap", "Pisc", "Plut", "Diod", "Herod", "Arist", "Curt", "Liv", "Amm",
        "Sanct", "Mais", "Malu", "Jans", "Caj", "Abul", "Will", "Phil", "Iun", "Epiph", "Clem", "Amb", "Greg",
        "Antiq", "Georg", "Eclog", "Iliad", "Odyss", "Metam", "Strom", "Moral", "Confess", "Retract", "Annal"}


def read_names():
    """footnote_names.txt: ({French title: (original, author, tag)}, {author: tag}, {other})."""
    titles, authors, other = {}, {}, set()
    if NAMES_FILE.exists():
        for line in NAMES_FILE.read_text(encoding="utf-8").splitlines():
            line = line.split("  # ")[0]  # "  # CHECK: …": a note for the reader
            kind, _, rest = line.partition(":")
            rest = rest.strip()
            if kind == "title" and "=" in rest:
                fr, _, r = rest.partition("=")
                original, author, tag = ([x.strip() for x in r.split("|")] + ["", ""])[:3]
                tag = MOVE.get(author, tag)
                titles[fr.strip()] = (original, author, tag if tag in AUTHORS else "")
            elif kind == "author":
                name, _, tag = rest.partition("|")
                name = name.strip()
                if name in AMBIGUOUS or B.plain(name) in {B.plain(k.split(" ", 1)[-1]) for k in B.BOOK}:
                    continue  # Marc, Jérémie: a Bible book first
                authors[name] = MOVE.get(name, tag.strip()) if tag.strip() in AUTHORS else ""
            elif kind == "other":
                other.add(rest)
    return titles, authors, other


TITLES, LISTED, OTHER = read_names()


def alternation(names):
    return re.compile(r"(?<![\wÀ-ÿ])(?:" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + r")(?![\wÀ-ÿ])")


GLOSSARY_TAG = {}  # name -> tag, from the glossary alone (names() fills it)


def names():
    """tag -> regex of the names (written out, and abbreviated) for it."""
    out = {t: set() for t in AUTHORS}
    tag = None
    for line in F.GLOSSARY.splitlines():
        if line.startswith("## "):
            head = line[3:]
            tag = next((t for s, t in SECTIONS.items() if head.startswith(s)),
                       "more" if head.startswith(("More", "Versions")) else None)
            continue
        if not tag:
            continue
        for left, right in re.findall(r"(?:^|\s{2,})([^=]+?)\s=\s(.+?)(?=\s{2,}|$)", line):
            full = re.sub(r"^(?:saint|le|la|les|l')\s*", "", right.strip()).split(" (")[0].strip()
            t = MOVE.get(full) or tag
            if t == "more":  # the mixed sections: sort by the written-out name (footnote_names.txt does the rest)
                t = ("fathers" if right.startswith("saint") else "rabbis" if any(r in right for r in RABBIS)
                     else "versions" if any(v in right for v in VERSIONS) else LISTED.get(full) or None)
            if t:
                out[t].add(full)
                out[t] |= {a.strip().rstrip(".") for a in left.split(" / ")
                           if len(a.strip().rstrip(".")) >= 4 and a.strip().rstrip(".") not in DROP}
    out["rabbis"] |= RABBIS
    out["versions"] |= VERSIONS - {"Grec", "Hébreu"} | {"l'Hébreu", "le Grec", "LXX", "les Septante"}
    for t, ns in out.items():
        for n in ns:
            GLOSSARY_TAG.setdefault(n, t)
    for name, t in LISTED.items():
        if t:
            out[t].add(name)
    for t in out:  # a work title only names its author through footnote_names.txt
        out[t] = {n for n in out[t] if not re.fullmatch(r"(?:de|in|contra|adv)\b.*", n)}
    return {t: alternation(ns) for t, ns in out.items() if ns}


NAMES = names()
TITLE_RX = alternation(TITLES) if TITLES else None
HEB = re.compile(r"[א-ת]")
GRK = re.compile(r"[Ͱ-Ͽἀ-῿]")
GUESSED = re.compile(r"[\wÀ-ÿ]\*")
IBID = re.compile(r"^\s*(?:Ibid|Ibidem|Idem|Id\.|Au même endroit|Le même|La même|Les mêmes)\b", re.I)
HOMILY = re.compile(r"\bHomélies?\s+\d+(?:\s+et\s+\d+)?\s+sur\b")
BARE_CV = re.compile(r"(?<![\d:])\d{1,3}:\d{1,3}(?![\d:])")
SEPTUAGINT = re.compile(r"(?:^|(?<=[\s;,(]))(?:Les\s+|les\s+)?70\b\.?(?!\s*[:\d])")
CHAPTER = re.compile(r"^\s*(?:Voyez\s+(?:le\s+)?)?(?:chapitre|chap\.)\s*\d+", re.I)
FULL_BOOKS = {B.plain(k.split(" ", 1)[-1]) for k in B.BOOK} | {"psaume"}
NAME_WORDS = {B.plain(w) for rx in NAMES.values() for w in re.findall(r"[\wÀ-ÿ]+", rx.pattern) if len(w) > 3}
ABBR_WORD = re.compile(r"(?<![\w])([A-Za-zÀ-ÿæœÆŒſ]{1,14})\.(?=[\s,;:)]|$)")
WORD = re.compile(r"[A-Za-zÀ-ÿæœÆŒſ]{3,}")


def french():
    """The words hunspell took for French (spellcheck.py's cache), lower case."""
    try:
        cached = json.loads(HUNSPELL_CACHE.read_text(encoding="utf-8"))["words"]
    except (OSError, ValueError, KeyError):
        return frozenset()
    return frozenset(w.lower() for w, sugg in cached.items() if sugg is None)


FRENCH = french()
VULGATE = vulgate_words()


def latin_words(t):
    return [w for w in WORD.findall(t) if w.lower() not in FRENCH and _fold(w) in VULGATE]


def old_ref(t, r):
    """Roman numerals, a long s, or the book under another name than the French one."""
    s = t[r.start:r.end]
    bk = re.match(r"\D*", s).group().strip(" .;,&")
    return bool(re.search(r"\b[IVXLC]+\b|ſ", s) or (bk and B.plain(bk) not in FULL_BOOKS
                                                       and not B.plain(r.book).startswith(B.plain(bk))))


def abbreviations(t):
    return [w for w in ABBR_WORD.findall(t) if (p := B.plain(w)) in F.ABBREV and p not in FULL_BOOKS | NAME_WORDS
            and w.lower() not in FRENCH and p != "etc"]


def local_tags(t):
    """(tags, titles found, whether the model has anything to add)."""
    tags = set()
    if HEB.search(t):
        tags.add("hebrew")
    if GRK.search(t):
        tags.add("greek")
    if F.UNSURE.search(t) or GUESSED.search(t):
        tags.add("uncertain")
    refs = B.find_refs(t)
    if refs or CHAPTER.match(t) or BARE_CV.search(t):
        tags.add("verse")
    if any(old_ref(t, r) for r in refs):
        tags.add("old-ref")
    if any(B.exists(r) is False for r in refs):
        tags.add("bad-ref")
    if HOMILY.search(t):  # "Homélie 31 sur la Genèse": a Father's homilies on a book
        tags.add("fathers")
    if IBID.match(t):
        tags.add("ibid")
    if abbreviations(t):
        tags.add("abbrev")
    rest = t
    for r in reversed(refs):
        rest = rest[:r.start] + " " + rest[r.end:]
    for tag, rx in NAMES.items():
        if rx.search(rest):
            tags.add(tag)
        rest = rx.sub(" ", rest)
    titles = []
    if TITLE_RX:
        for m in TITLE_RX.finditer(rest):
            original, _, tag = TITLES[m.group()]
            tags.add("title")
            if tag:
                tags.add(tag)
            if original and {"fr": m.group(), "original": original} not in titles:
                titles.append({"fr": m.group(), "original": original})
        rest = TITLE_RX.sub(" ", rest)
    if SEPTUAGINT.search(rest):
        tags.add("versions")
        rest = SEPTUAGINT.sub(" ", rest)
    lat = [w for w in latin_words(rest) if w.lower() not in CITING]
    if len(lat) >= 2 or any(w[0].islower() for w in lat):  # one capitalized word may be a name (Tryphon)
        tags.add("latin")
    # what is left once references, names, titles and Latin are out: prose (an explanation?)
    # or a capitalized word no list knows (an author?) is for the model
    lat = {w.lower() for w in lat}
    rest = re.sub(r"[א-ת֑-״־Ͱ-Ͽἀ-῿̀-ͯ'’᾽ʼ]+|\d+", " ", F.UNSURE.sub(" ", rest))
    left = [w for w in WORD.findall(rest) if w.lower() not in lat and w.lower() not in CITING and B.plain(w) not in F.ABBREV]
    unknown = [w for w in left if w[0].isupper() and w not in OTHER]
    prose = [w for w in left if not w[0].isupper()]
    return tags, titles, bool(unknown) or len(prose) >= 4


# the words of a written-out citation: nothing for the model in them
CITING = set("""livre livres chapitre chapitres page pages tome tomes partie section question questions lettre lettres
homélie homélies sermon sermons discours vers verset versets numéro colonne article note notes édition nouvelle
commencement fin vers passim passage sur dans voyez voir aussi ailleurs suivants suivant même endroit cité plus haut
bas les des une pour par avec chez selon comme etc saint saints sainte pères père ancienne anciens autres quelques
qui que est sont ont dit après avant ainsi encore également surtout entre leur leurs ses son sur ceux celui
apud vide ibid idem""".split())


def ordered(tags):
    return [t for t in TAGS if t in tags]


# ---- the model ---------------------------------------------------------------------

PROMPT = """Tag each footnote of Dom Calmet's Bible commentary (French, 18th century; some notes still
in Calmet's Latin abbreviations) with every tag that fits, from this list only:
  verse        cites a Bible verse or chapter
  fathers      cites a Church Father or church writer (Augustin, Jérôme, Chrysostome, Origène, Eusèbe, Bède, Thomas …)
  rabbis       cites a Jewish source: the rabbis, Talmud, Targum, Kimhi, Rabbi Salomon, Aben Ezra, Maïmonide, Josèphe, Philon
  versions     cites an ancient version or edition: l'Hébreu, les Septante, Symmaque, Aquila, Théodotion, le Syriaque, le Chaldéen, la Vulgate, the Psalters
  classical    cites a pagan Greek or Latin author (Pline, Hérodote, Strabon, Homère, Virgile, Platon, Cicéron …)
  commentators cites a commentator or scholar after the Fathers (Lyre, Grotius, Vatable, Bochart, Cornelius a Lapide, Estius, Tostat …)
  latin        holds a Latin quotation or Latin words (not a bare Latin abbreviation like "lib." or "cap.")
  explanation  explains, translates or comments in sentences, rather than only giving references
  hebrew, greek, uncertain: leave these out (they are found without you)
A note can have several tags, or none ("Ibid.", "Idem."). Answer with only a JSON array, one object per note:
[{{"id": "n1", "tags": ["fathers", "verse"]}}, …]

Notes:
{items}"""
ASKED = {"verse", "fathers", "rabbis", "versions", "classical", "commentators", "latin", "explanation"}


def save_cache(cache):
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")


async def batches(todo, prompt_of, read, cache, who, size=BATCH):
    """Ask agy or Haiku `todo` in batches; read(item, answer) puts each answer in the cache."""
    sem = asyncio.Semaphore(PARALLEL)
    groups = [todo[i:i + size] for i in range(0, len(todo), size)]
    print(f"  {who}: {len(todo)} in {len(groups)} batches", flush=True)

    async def one(group):
        prompt = prompt_of(group)
        got = await (F.agy(prompt, sem) if who == "agy" else F.claude(prompt, "haiku", sem))
        for i, x in enumerate(group):
            r = got.get(f"n{i}")
            if isinstance(r, dict):
                read(x, r)

    done = 0
    for coro in asyncio.as_completed([one(g) for g in groups]):
        await coro
        done += 1
        if done % 10 == 0 or done == len(groups):
            save_cache(cache)
            print(f"    {done}/{len(groups)} batches", flush=True)


def ask_tags(texts, cache, who):
    todo = [t for t in texts if F.key("tags", t) not in cache]
    if not todo:
        return

    def prompt_of(group):
        return PROMPT.format(items="\n".join(json.dumps({"id": f"n{i}", "text": t}, ensure_ascii=False)
                                             for i, t in enumerate(group)))

    def read(t, r):
        if isinstance(r.get("tags"), list):
            cache[F.key("tags", t)] = {"tags": ordered(set(map(str, r["tags"])) & ASKED), "by": who}

    asyncio.run(batches(todo, prompt_of, read, cache, who))


# ---- tagging -----------------------------------------------------------------------

def merge(now, last_auto, auto):
    """The tags to write: the tagger's new ones, with what was added or taken away by hand since
    its last run (`now` against `last_auto`; no last run on record: `now` was all the tagger's)."""
    if now is None:
        return ordered(auto)
    before = set(now if last_auto is None else last_auto)
    added, removed = set(now) - before, before - set(now)
    return ordered((set(auto) | added) - removed)


def footnotes_of(volumes):
    """(volume, path, page, footnote) for every footnote with text, in reading order."""
    for v in volumes:
        for p in pages(v):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            for fn in d.get("footnotes") or []:
                if isinstance(fn, dict) and isinstance(fn.get("text"), str) and fn["text"].strip():
                    yield v, p, d, fn


def where(v, p, fn):
    return f"{v}/{p.stem}/{fn.get('marker')}"


def run(volumes, local_only, model):
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    auto = json.loads(AUTO.read_text(encoding="utf-8")) if AUTO.exists() else {}
    F.NO_CALLS = local_only
    found = {}
    for *_, fn in footnotes_of(volumes):
        t = fn["text"].strip()
        if t not in found:
            found[t] = local_tags(t)
    ask = [t for t, (*_, unclear) in found.items() if unclear]
    print(f"{len(found)} different texts, {len(ask)} for the model", flush=True)
    if not local_only:
        for who in (["agy", "haiku"] if model == "both" else [model]):
            F.LIMIT_HIT = False  # agy out of quota says nothing of Haiku's
            ask_tags(ask, cache, who)
        save_cache(cache)
    by_page, unanswered, hand = {}, 0, 0
    prev = set()
    for v, p, d, fn in footnotes_of(volumes):
        t = fn["text"].strip()
        tags, titles, unclear = found[t]
        tags = set(tags)
        a = cache.get(F.key("tags", t))
        if a:
            tags |= set(a["tags"])
        elif unclear:
            unanswered += 1
        if "ibid" in tags and not tags & set(AUTHORS):  # "Le même": the author of the note before
            tags |= prev & set(AUTHORS)
        prev = tags
        k = where(v, p, fn)
        new = merge(fn.get("tags"), auto.get(k), tags)
        hand += new != ordered(tags)
        auto[k] = ordered(tags)
        if fn.get("tags") != new or fn.get("titles", []) != titles:
            fn["tags"] = new
            if titles:
                fn["titles"] = titles
            else:
                fn.pop("titles", None)
            by_page[p] = d
    for p, d in by_page.items():
        raw = p.read_text(encoding="utf-8")
        p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + ("\n" if raw.endswith("\n") else ""), encoding="utf-8")
    AUTO.write_text(json.dumps(auto, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(by_page)} pages written; {hand} notes keep tags changed by hand; {unanswered} notes the model did not answer"
          + (" (--local)" if local_only else " (run again)" if unanswered else ""))


# ---- footnote_names.txt ------------------------------------------------------------

LOCATOR = re.compile(r"(?i)^(?:livres?|chapitres?|pages?|tomes?|partie|section|questions?|lettres?|homélies?|sermons?|discours"
                     r"|vers|versets?|numéro|colonne|article|notes?|édition|au commencement|à la fin|vers la fin|passim"
                     r"|sur ce passage|etc|et|ou|voyez|voir|dans|au même endroit|le même|ibid|idem|et suivants|ailleurs)\b")
TITLE_SLOT = r",\s*(?:livres?|chapitres?|partie|tome|pages?|questions?|lettres?|homélies?|discours|sermons?|section)\b"


def candidates(volumes):
    """French segments that may be a work or an author: {segment: (count, [(Calmet's note, the note now)])}."""
    count, ex, slot = Counter(), defaultdict(list), set()
    for v in volumes:
        for n in F.load_volume(v, 0, 9999):
            t = n["text"]
            for seg in re.split(r"\s*[,;:\n]\s*|\.\s+(?=[A-ZÀ-Ý])", t):
                seg = re.sub(r"^(?:(?:et|Voyez|Voir|voyez|aussi|dans|Dans|sur|Sur)\s+)+", "", seg.strip(" .*_()"))
                if not (4 <= len(seg) <= 70) or len(seg.split()) > 9 or re.search(r"\d|[א-תͰ-Ͽἀ-῿]", seg) or LOCATOR.match(seg):
                    continue
                if not re.match(r"(?:[A-ZÀ-Ý]|De |Du |Des |D'|L'|La |Le |Les |Contre )", seg) or B.find_refs(seg):
                    continue
                if any(rx.fullmatch(re.sub(r"^[Ss]aint\s+", "", seg)) for rx in NAMES.values()):
                    continue
                count[seg] += 1
                if re.search(re.escape(seg) + TITLE_SLOT, t):
                    slot.add(seg)
                if len(ex[seg]) < 2 and n["raw"]:
                    ex[seg].append((n["raw"][:200], t[:200]))
    return {s: (c, ex[s]) for s, c in count.items() if (c >= 2 or s in slot) and ex[s]}


NAMES_PROMPT = """Footnotes of Dom Calmet's Bible commentary (1707-1716) were written out from his Latin
abbreviations into French. For each French segment below, the notes it comes from are given as
Calmet printed them ("calmet") and as written out now ("now"). Say what the segment is:
  "title"   the title of a work, translated into French: give "original", its full title in the
            original language as catalogues and editions cite it (Latin, or the usual Latin title of a
            Greek work; never abbreviated: "De civitate Dei", "Praeparatio evangelica",
            "De animalibus sacris" (Hierozoicon)), "author" (in French: "Augustin", "Eusèbe de Césarée",
            "Bochart"), and "tag": one of fathers, rabbis, versions, classical, commentators.
            Read the title Calmet abbreviated in "calmet"; if you cannot tell the original, give "original": "".
  "author"  a person's or a version's name: give "tag" (as above).
  "other"   anything else (Latin words, a place, a phrase, a misreading).
Answer with only a JSON array, one object per segment:
[{{"id": "n1", "kind": "title", "original": "De civitate Dei", "author": "Augustin", "tag": "fathers"}},
 {{"id": "n2", "kind": "author", "tag": "commentators"}}, {{"id": "n3", "kind": "other"}}]

Segments:
{items}"""


def checks(kind, name, author, tag, original):
    """What to look at in a footnote_names.txt line ("  # CHECK: …")."""
    why = []
    if kind == "title" and not original:
        why.append("no original title")
    who = re.sub(r"^[Ss]aint\s+", "", author if kind == "title" else name)
    if who in MOVE and tag != MOVE[who]:
        why.append(f"{who} counts as {MOVE[who]} here, not {tag or 'no tag'}")
    elif who in GLOSSARY_TAG and tag and GLOSSARY_TAG[who] != tag:
        why.append(f"the glossary has {who} under {GLOSSARY_TAG[who]}, not {tag}")
    if kind == "author" and (name in AMBIGUOUS or B.plain(name) in FULL_BOOKS):
        why.append("ambiguous name (several people, or a Bible book): left out of the rules")
    if kind in ("title", "author") and not tag:
        why.append("no tag")
    return "  # CHECK: " + "; ".join(why) if why else ""


def build_names():
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    known = set(TITLES) | set(LISTED) | OTHER
    cand = {s: x for s, x in candidates(volumes_of(["all"])).items() if s not in known}
    todo = [s for s in cand if F.key("name", s) not in cache]
    print(f"{len(cand)} segments not in footnote_names.txt yet, {len(todo)} to ask", flush=True)

    def prompt_of(group):
        return NAMES_PROMPT.format(items="\n".join(json.dumps(
            {"id": f"n{i}", "segment": s, "notes": [{"calmet": a, "now": b} for a, b in cand[s][1]]}, ensure_ascii=False)
            for i, s in enumerate(group)))

    def read(s, r):
        if r.get("kind") in ("title", "author", "other"):
            cache[F.key("name", s)] = {k: str(r.get(k) or "") for k in ("kind", "original", "author", "tag")}

    if todo:
        asyncio.run(batches(todo, prompt_of, read, cache, "haiku", size=40))
        save_cache(cache)
    lines = NAMES_FILE.read_text(encoding="utf-8").splitlines() if NAMES_FILE.exists() else [
        "# Works and authors named in the footnotes (footnote_tags.py names; correct by hand: lines here are kept).",
        "# title: French title = original title | author | tag      author: name | tag      other: not a name"]
    new = []
    for s in sorted(cand, key=lambda s: -cand[s][0]):
        a = cache.get(F.key("name", s))
        if not a:
            continue
        tag = a["tag"] if a["tag"] in AUTHORS else ""
        new.append(f"title: {s} = {a['original']} | {a['author']} | {tag}" + checks("title", s, a["author"], tag, a["original"])
                   if a["kind"] == "title" else f"author: {s} | {tag}" + checks("author", s, "", tag, "")
                   if a["kind"] == "author" else f"other: {s}")
    order = {"title": 0, "author": 1, "other": 2}
    new.sort(key=lambda l: order[l.split(":")[0]])
    NAMES_FILE.write_text("\n".join(lines + new) + "\n", encoding="utf-8")
    print(f"footnote_names.txt: {len(new)} lines added ({Counter(l.split(':')[0] for l in new)})")


def stats(volumes):
    c, n, none = Counter(), 0, 0
    for *_, fn in footnotes_of(volumes):
        n += 1
        if "tags" not in fn:
            none += 1
        c.update(fn.get("tags") or [])
    print(f"{n} footnotes, {none} not tagged yet")
    for t in TAGS:
        print(f"  {t:13} {c[t]}")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("run", "stats", "names") or sys.argv[1] != "names" and len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd, *rest = sys.argv[1:]
    if cmd == "names":
        build_names()
        sys.exit()
    vols = volumes_of([a for a in rest if not a.startswith("--") and a not in ("agy", "haiku", "both")])
    if cmd == "stats":
        stats(vols)
    else:
        m = next((rest[i + 1] for i, a in enumerate(rest) if a == "--model" and i + 1 < len(rest)), "both")
        run(vols, "--local" in rest, m)
