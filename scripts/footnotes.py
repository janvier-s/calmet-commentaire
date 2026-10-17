"""Footnotes: check Calmet's notes against the texts and the scans; write references out in full.

Stages (`run` does all three; every Claude answer is cached):
  1. local, free: Bible references written out with Calmet's (Vulgate) names and checked
     against the Vulgate, and against the Latin they are cited for; Hebrew checked against
     the Hebrew Bible, Greek against the Septuagint; [UNCERTAIN …], [ILLEGIBLE] and the
     references garbled by the earlier expansion ("inGenèse 50actant.") flagged.
  2. scan: Claude reads the footnote area of the scan, for the flagged Hebrew, Greek and
     uncertain notes only. Text it supplies for an uncertain or illegible place gets "*".
  3. expand: Claude writes out the other abbreviations (Fathers, commentators, classical
     authors), in batches, following footnote_glossary.txt.
Writes docs/footnotes/<volume>.json: each changed or flagged note with its current text,
the proposal, why, and flags. `apply` writes the proposals into normalized/.

Usage: uv run --no-project --with pillow python footnotes.py run <volume> [--pages 99-140] [--local]
       python3 footnotes.py apply <volume> [--pages 99-140] [--no-hold]
CLAUDE_MODEL (expand) and SCAN_MODEL (scan) choose the models (default sonnet for both) choose the models.
"""
import asyncio, hashlib, json, os, re, sys, unicodedata
from collections import Counter, defaultdict

import bible_refs as B
from paths import BOOKS, BY_VOLUME, DATA, DOCS, SCRIPTS, pages as volume_pages

OUT_DIR = DOCS / "footnotes"
CACHE = SCRIPTS / "cache" / "footnote_cache.json"
CROPS = SCRIPTS / "cache" / "footnote_crops"
GLOSSARY = (SCRIPTS / "footnote_glossary.txt").read_text(encoding="utf-8")
EXPAND_MODEL = os.environ.get("CLAUDE_MODEL", "sonnet")
SCAN_MODEL = os.environ.get("SCAN_MODEL", "sonnet")
BATCH, PARALLEL = 50, 4

HEB = re.compile(r"[א-ת][֑-״־\s'\"]*")
HEB_SEG = re.compile(r"[֑-״]+(?:[\s־]+[֑-״]+)*")
GRK_SEG = re.compile(r"[Ͱ-Ͽἀ-῿][Ͱ-Ͽἀ-῿̀-ͯ'’᾽ʼ]*"
                     r"(?:[\s,.;·:()]+[Ͱ-Ͽἀ-῿][Ͱ-Ͽἀ-῿̀-ͯ'’᾽ʼ]*)*")
UNSURE = re.compile(r"\[(?:UNCERTAIN[^\]]*|ILLEGIBLE)\]")
FRENCH_BOOKS = "|".join(sorted({re.escape(k.split(" ", 1)[-1]) for k in B.BOOK} | {"Samuel", "Chroniques"}, key=len, reverse=True))
GLUED = re.compile(rf"[a-zà-ÿ](?:{FRENCH_BOOKS})\b|\b(?:{FRENCH_BOOKS})\s?\d+(?::\d+)?[A-Za-zÀ-ÿ]")
SEE = re.compile(r"^\s*(?:Vide|Vid\.|Voi|Voyez|Voy\.)\s*", re.I)
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
            if not isinstance(fn.get("text"), str):
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

def heb_words(s):
    return [w for w in (re.sub(r"[^א-ת]", "", x) for x in re.split(r"[\s־]+", s)) if w]


def grk_words(s):
    s = B.plain(s).replace("ς", "σ")
    return [w for w in re.findall(r"[α-ω]+", s)]


def contains(seq, words):
    k = len(seq)
    return any(words[i:i + k] == seq for i in range(len(words) - k + 1))


def chapters_around(book, chap):
    """Hebrew-book chapters to look in for a Calmet chapter (psalm numbers converted)."""
    if not chap:
        return []
    if book == "Psalms":
        return [c for n in B.vulgate_to_hebrew_psalm(chap) for c in (n - 1, n, n + 1)]
    return [chap - 1, chap, chap + 1]


_HEB_ALL = {}


def heb_index():
    if not _HEB_ALL:
        for b, vs in B.hebrew().items():
            for (c, v), ws in vs.items():
                for i, w in enumerate(ws):
                    _HEB_ALL.setdefault(w, []).append((b, c, v, i))
    return _HEB_ALL


def heb_phrase_anywhere(ws):
    idx, H = heb_index(), B.hebrew()
    for b, c, v, i in idx.get(ws[0], []):
        if H[b][(c, v)][i:i + len(ws)] == ws:
            return f"{b} {c}:{v}"
    return None


def one_off(a, b):
    """One letter added, dropped or changed."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    s, l = sorted((a, b), key=len)
    return any(l[:i] + l[i + 1:] == s for i in range(len(l)))


def check_hebrew(note):
    """Each Hebrew phrase: in the verses around the one commented, or anywhere in the Bible?"""
    vul, oshb, _ = B.BOOK.get(note["vol_book"], (None, None, None))
    H = B.hebrew()
    near = [ws for (c, v), ws in H.get(oshb, {}).items() if c in chapters_around(oshb, note["chap"])] if oshb else []
    text, unsure = note["proposed"], []
    for seg in HEB_SEG.findall(text):
        ws = heb_words(seg)
        if not ws:
            continue
        if any(contains(ws, v) for v in near) or (len(ws) > 1 and heb_phrase_anywhere(ws)):
            continue
        rev = ws[::-1]
        if len(ws) > 1 and (any(contains(rev, v) for v in near) or heb_phrase_anywhere(rev)):
            fixed = " ".join(seg.split()[::-1])
            text = text.replace(seg, fixed)
            note["why"].append(f"Hebrew word order reversed: {seg} -> {fixed}")
            continue
        near_words = {w for v in near for w in v}
        slips = [w for w in ws if w not in near_words for x in near_words if len(w) >= 3 and one_off(w, x)]
        if len(ws) == 1 and ws[0] in heb_index() and not slips:
            continue  # a word that exists, cited from elsewhere
        unsure.append(seg)
    note["proposed"] = text
    if unsure:
        note["flags"].append("hebrew")
        note["scan_why"].append("Hebrew not found in the verse or anywhere in the Hebrew Bible: " + " / ".join(unsure))


_LXX_WORDS = {}


def lxx_phrase(ws, nr, chap):
    """Is the word sequence in the Septuagint chapter (±1), or in the whole Septuagint?"""
    if nr and chap:
        for (c, v), t in B.lxx(nr).items():
            if abs(c - chap) <= 1 and contains(ws, grk_words(t)):
                return True
    if not _LXX_WORDS:
        for f in (B.REFS / "lxx").glob("[0-9]*.json"):
            _LXX_WORDS[f.stem] = [grk_words(t) for t in B.lxx(int(f.stem)).values()]
    return any(contains(ws, v) for vs in _LXX_WORDS.values() for v in vs) if len(ws) >= 3 else False


def check_greek(note):
    nr = B.BOOK.get(note["vol_book"], (None, None, None))[2]
    bad = []
    for seg in GRK_SEG.findall(note["proposed"]):
        ws = grk_words(seg)
        if ws and not lxx_phrase(ws, nr, note["chap"]):
            bad.append(seg.strip()[:60])
    if bad:
        note["flags"].append("greek")
        note["scan_why"].append("Greek not found in the Septuagint (not checked against any source): " + " / ".join(bad))


def resolve_ambiguous(ref, raw_refs):
    """'1 Rois 18:38' written by the earlier expansion: Calmet's 1 Rois, or a modern 1 Kings (3 Rois)?"""
    same = [r for r in raw_refs if r.chap == ref.chap and r.verses[:1] == ref.verses[:1] and r.name in ("Rois", "Paralipomènes")]
    if same:
        return same[0].book
    return None


def render_bible(note, prev):
    """Write out a note that holds only Bible references; None if it holds anything else."""
    t = note["text"].strip()
    m = IBID.match(t)
    if m and prev:
        rest = t[m.end():]
        vm = VERSET_ONLY.match(rest)
        t = f"{prev.book} {prev.chap}. {vm.group(1)}." if vm else f"{prev.book} {rest}"
    vm = VERSET_ONLY.match(t)
    if vm and note["chap"]:
        t = f"{note['vol_book']} {note['chap']}. {vm.group(1)}."
    refs = B.find_refs(t)
    if not refs:
        return None
    raw_refs = B.find_refs(note["raw"]) if note["raw"] else []
    out, pos = [], 0
    lead = t[:refs[0].start]
    if lead.strip() and not SEE.fullmatch(lead + " ") and not SEE.match(lead):
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
            book = resolve_ambiguous(r, raw_refs)
            if not book:
                note["flags"].append("ambiguous-name")
                return None
        if r.name == "Samuel":
            note["why"].append(f"{r.src.strip()} -> {book} (Vulgate name)")
        same = i and refs[i - 1].book == r.book and not out[-1].startswith(" ; comparez")
        out.append(r.render(with_book=False) if same else f"{book} {r.render(with_book=False)}")
        pos = r.end
        s = SEQ.match(t, pos)
        if s:
            out.append(" et suivants")
            pos = s.end()
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
    """The footnote area of a page (below the rule), enlarged; cached."""
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
    top = None
    for y in range(int(h * 0.35), int(h * 0.97)):
        dark = sum(1 for x in range(x0, x1, 2) if px[x, y] < 110)
        if dark > 0.55 * (x1 - x0) / 2:
            top = y
            break
    top = top if top is not None else int(h * 0.55)
    out.parent.mkdir(parents=True, exist_ok=True)
    c = im.crop((0, max(0, top - 4), w, h))
    c = c.resize((int(c.width * 1.6), int(c.height * 1.6)), Image.LANCZOS)
    c.save(out)
    return out


SCAN_PROMPT = """You are checking the transcription of footnotes in an 18th-century French Bible commentary (Dom Calmet, 1707), against the printed page.
Read the image {image} (the footnote area of the page, enlarged). Then, for each footnote below, give its corrected text.

Rules:
- Correct only the Hebrew and the Greek, and fill in [UNCERTAIN HEBREW], [UNCERTAIN GREEK] and [ILLEGIBLE]. Change nothing else: keep the Latin and French exactly as given (spelling, abbreviations, punctuation).
- Hebrew and Greek: copy what is PRINTED, letter for letter (Greek with its accents and breathings; Hebrew with vowel points only if printed). 18th-century Greek type uses ligatures: στ (often misread as ς, σ or ι), ου (misread as ε, ω or ȣ), and others. Hebrew must be in logical (right-to-left reading) order.
- For [UNCERTAIN …]/[ILLEGIBLE]: replace the placeholder with what the page shows. If you can read it with confidence, write it plainly (no asterisk). Only where the page is not legible enough and you supply the most likely text from the context, put an asterisk right after each guessed word, e.g. "Imago, צלם* umbra". Corrections to existing Hebrew/Greek never get an asterisk.
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


def script_kept(old, new):
    """Every Hebrew and Greek passage of `new` is in `old` unchanged; one left out may only be a
    short title written out in French ("περὶ ἀρχῶν" -> "Des principes")."""
    a = HEB_SEG.findall(old) + [g.strip(" ,.;") for g in GRK_SEG.findall(old)]
    b = HEB_SEG.findall(new) + [g.strip(" ,.;") for g in GRK_SEG.findall(new)]
    if any(x not in a for x in b):
        return False
    return all(x in b or (not HEB_SEG.fullmatch(x) and len(x.split()) <= 3) for x in a)


# ---- Claude ------------------------------------------------------------------------

async def claude(prompt, model, sem, image_dir=None):
    args = ["claude", "-p", "--model", model, "--strict-mcp-config", "--disable-slash-commands"]
    args += ["--tools", "Read", "--allowedTools", "Read", "--add-dir", str(image_dir)] if image_dir else ["--tools", ""]
    async with sem:
        proc = await asyncio.create_subprocess_exec(*args, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.PIPE, cwd=str(image_dir or SCRIPTS))
        out, err = await proc.communicate(prompt.encode())
    text = out.decode().strip()
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


async def scan_stage(volume, notes, cache):
    todo = defaultdict(list)
    for n in notes:
        if {"hebrew", "greek"} & set(n["flags"]) and "uncertain" not in n["flags"] and checked(n["proposed"], cache):
            n["flags"] = [f for f in n["flags"] if f not in ("hebrew", "greek")]  # read on the scan before
            continue
        if {"hebrew", "greek", "uncertain"} & set(n["flags"]):
            n["scan_key"] = key("scan4", SCAN_MODEL, n["page"], n["proposed"], n["scan_why"])
            if n["scan_key"] not in cache:
                todo[n["page"]].append(n)
    sem = asyncio.Semaphore(PARALLEL)
    jobs = []
    for page, ns in todo.items():
        img = crop(volume, page)
        if not img:
            continue
        jobs.append((ns, claude(SCAN_PROMPT.format(image=img.name, items=scan_items(ns)), SCAN_MODEL, sem, img.parent)))
    print(f"  scan: {sum(len(v) for v in todo.values())} notes on {len(jobs)} pages to read", flush=True)
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


async def expand_stage(notes, cache):
    todo = []
    for n in notes:
        if n["done"] or not (needs_expansion(n["proposed"]) or "garbled-reference" in n["flags"]
                             or re.search(r"\b(?:Samuel|Chroniques)\b", n["proposed"])):
            continue
        n["exp_key"] = key("exp2", EXPAND_MODEL, n["proposed"], n["prev"], n["raw"] if "garbled-reference" in n["flags"] else "")
        if n["exp_key"] not in cache:
            todo.append(n)
    print(f"  expand: {len(todo)} notes to write out", flush=True)
    sem = asyncio.Semaphore(PARALLEL)
    batches = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]
    answers = await asyncio.gather(*(claude(EXPAND_PROMPT.format(glossary=GLOSSARY, items=expand_items(b)), EXPAND_MODEL, sem)
                                     for b in batches))
    for b, ans in zip(batches, answers):
        for n in b:
            if n["id"] in ans:
                cache[n["exp_key"]] = ans[n["id"]].get("text", "")
    for n in notes:
        if "exp_key" not in n:
            continue
        new = (cache.get(n["exp_key"]) or "").strip()
        if not new:
            n["flags"].append("expand-unread")
        elif not script_kept(n["proposed"], new):
            n["flags"].append("expand-changed-hebrew-or-greek")
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


def check_refs(n):
    refs = B.find_refs(n["proposed"])
    for r in refs:
        if B.exists(r) is False:
            n["flags"].append("reference-not-in-vulgate")
            n["why"].append(f"{r.render()} does not exist in the Vulgate")
    quotes = [q for q in map(latin_words, quotes_for(n)) if len(q) >= 4]
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
        n["flags"].append("reference-corrected")
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


async def run(volume, lo, hi, local_only):
    notes = load_volume(volume, lo, hi)
    print(f"{volume}: {len(notes)} footnotes", flush=True)
    local_stage(notes)
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    if not local_only:
        await scan_stage(volume, notes, cache)
        CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
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


HOLD = {"hebrew", "hebrew-recheck", "uncertain-fill-unclear", "uncertain-fill-asterisk-wrong", "greek", "uncertain", "scan-unread", "expand-unread", "expand-changed-hebrew-or-greek",
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


if __name__ == "__main__":
    cmd, volume, *rest = sys.argv[1:]
    lo, hi = page_range(rest)
    if cmd == "run":
        asyncio.run(run(volume, lo, hi, "--local" in rest))
    elif cmd == "apply":
        apply(volume, lo, hi, hold="--no-hold" not in rest)
