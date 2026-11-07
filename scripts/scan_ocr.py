"""Kraken OCR of the scans, for the review editor's overlay only (never a source of text).

    python3 scan_ocr.py <volume> [first-last]     OCR every page of a volume (or a range) not yet cached

`ocr(vol, page)` runs Kraken (CATMuS-Print Large, about 12 s a page) and caches the words with their
boxes, and their slant (scan_slant.py: italics), in cache/ocr/<vol>/page_NNNN.json; `align(ocr, data)` sets each OCR word against the page's
JSON fields: the same word (old spelling allowed), a different one, or missing from the JSON.
"""
import datetime
import difflib
import functools
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

from paths import DATA, SCRIPTS, STUDIUM

OCR_CACHE = SCRIPTS / "cache" / "ocr"
KRAKEN = Path(os.environ.get("CALMET_KRAKEN") or STUDIUM / ".kraken-venv" / "bin" / "kraken")
MODEL = Path(os.environ.get("CALMET_KRAKEN_MODEL") or Path.home() / "Library" / "Application Support" / "htrmopo"
             / "d96caf7a-122e-5576-ab2b-a246c4e64221" / "catmus-print-fondue-large.mlmodel")
VENV_PYTHON = KRAKEN.parent / "python"  # numpy and Pillow, for the slant


def scan_path(vol, page):
    return DATA / vol / "source_images" / "commentaire" / f"page_{page:04d}.png"


SLANT = 2  # scan_slant.VERSION: a cache measured before is measured again


def cache_path(vol, page):
    return OCR_CACHE / vol / f"page_{page:04d}.json"


# --- OCR ---
def parse_alto(xml):
    """ALTO → {"size": [w, h], "lines": [{"box": [x, y, w, h], "words": [{"t", "box", "wc"}]}]}."""
    root = ET.fromstring(xml)
    ns = root.tag.split("}")[0] + "}" if root.tag.startswith("{") else ""
    box = lambda e: [int(float(e.get(k))) for k in ("HPOS", "VPOS", "WIDTH", "HEIGHT")]
    page = root.find(f".//{ns}Page")
    lines = [{"box": box(ln), "words": [{"t": unicodedata.normalize("NFC", s.get("CONTENT")), "box": box(s), "wc": round(float(s.get("WC") or 0), 3)}
                                        for s in ln.iter(f"{ns}String") if s.get("HPOS")]}  # a word without a box: dropped
             for ln in root.iter(f"{ns}TextLine") if ln.get("HPOS")]
    return {"size": [int(page.get("WIDTH")), int(page.get("HEIGHT"))], "lines": [ln for ln in lines if ln["words"]]}


_running = {}
_running_lock = threading.Lock()


def ocr(vol, page, run=True, scan=None):
    """The page's OCR, from the cache; else, with `run`, Kraken's (cached). None: no scan, or not run.
    `scan`: the image, if not the one in data/."""
    out, scan = cache_path(vol, page), Path(scan or scan_path(vol, page))
    if out.exists():
        o = json.loads(out.read_text(encoding="utf-8"))
        if o.get("slant", 0) < SLANT and scan.exists() and slants(vol, [(page, scan)]):  # read before the slant was measured
            o = json.loads(out.read_text(encoding="utf-8"))
        return o
    if not run or not scan.exists():
        return None
    with _running_lock:  # one Kraken per page at a time: a second request waits for the first
        lock = _running.setdefault((vol, page), threading.Lock())
    with lock:
        if out.exists():
            return json.loads(out.read_text(encoding="utf-8"))
        kraken(vol, [(page, scan)])
        return json.loads(out.read_text(encoding="utf-8"))


def kraken(vol, scans, cache=cache_path):
    """Read [(page, image)] in one Kraken run (the model loads once) and cache each page. On this Mac
    8 threads and 64 lines a pass halve the time (about 12 s a page); two runs side by side are slower.
    `cache(vol, page)`: where a page's OCR goes (good_calmet_kraken.py: cache/good_ocr)."""
    with tempfile.TemporaryDirectory() as tmp:
        pairs = [a for page, scan in scans for a in ("-i", str(scan), str(Path(tmp) / f"{page}.xml"))]
        subprocess.run([str(KRAKEN), "-a", "-d", "mps", "--threads", "8", *pairs, "segment", "-bl",
                        "ocr", "-B", "64", "-m", str(MODEL)], check=True, capture_output=True)
        cache_alto(vol, scans, lambda page: Path(tmp) / f"{page}.xml", cache)


def cache_alto(vol, scans, alto, cache=cache_path):
    """Cache the ALTO `alto(page)` of each of [(page, image)], then measure its slant."""
    for page, _ in scans:
        out = cache(vol, page)
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = parse_alto(alto(page).read_bytes())
        except (OSError, ET.ParseError, TypeError, ValueError) as e:
            print(f"  {vol} p.{page}: no OCR ({type(e).__name__}: {e})", flush=True)
            continue
        out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    slants(vol, [(page, scan) for page, scan in scans if cache(vol, page).exists()], cache)


_no_slant = []  # the venv's Python failed once: not tried again


def slants(vol, scans, cache=cache_path):
    """Measure the slant of every word of the cached pages [(page, image)]. False if it could not."""
    if _no_slant or not scans:
        return False
    try:
        subprocess.run([str(VENV_PYTHON), str(SCRIPTS / "scan_slant.py"),
                        *(a for page, scan in scans for a in (str(scan), str(cache(vol, page))))],
                       check=True, capture_output=True)
        return True
    except (OSError, subprocess.CalledProcessError) as e:
        _no_slant.append(e)
        print(f"  {vol}: no slant ({getattr(e, 'stderr', b'') and e.stderr.decode(errors='replace')[-200:] or e})", flush=True)
        return False

# --- alignment ---
TOKEN = re.compile(r"[^\W_]+(?:-[^\W_]+)*")
OCR_TOKEN = re.compile(r"&|[^\W_]+(?:-[^\W_]+)*")  # & is "et"
ABBREV = {"s": "saint", "ste": "sainte", "st": "saint", "tems": "temps", "longtems": "longtemps",
          "entr": "entre", "contr": "contre", "chap": "chapitre"}  # entr'eux: entre eux
SPELLING = SCRIPTS / "ocr_spelling.txt"  # "old modern" a line: what the scan prints and the text has


@functools.cache
def key(t):
    """A word's spelling-blind key: no accents or case; ſ, &, y, j, v, oi as in the modernized text; the
    pairs of ocr_spelling.txt (loix: lois, Caldéen: Chaldéen, Iraël: Israël)."""
    k = _key(t)
    return _keymap().get(k, k)


@functools.cache
def _keymap():
    out = {}
    for ln in (SPELLING.read_text(encoding="utf-8").splitlines() if SPELLING.exists() else []):
        old, _, new = ln.split("#")[0].strip().partition(" ")
        if old and new.strip():
            out[_key(old)] = _key(new.strip())
    return out


@functools.cache
def modern_key(t):
    """The key of the scan's words once modernized as the text was (avoit: avait, soixante & dix)."""
    from clean_mechanical import fix_spelling
    from modernize_inplace import modernize_text
    m = modernize_text(fix_spelling(t.replace("ſ", "s").replace("&", "et").replace("’", "'")))[0]
    return "".join(key(w) for w in TOKEN.findall(m))


@functools.cache
def _key(t):
    t = re.sub(r"\btems\b", "temps", t.lower())  # même-tems
    t = unicodedata.normalize("NFKD", t.replace("ſ", "s").replace("æ", "e").replace("œ", "e"))  # æ, œ mixed up
    t = "".join(c for c in t if c.isalnum())
    t = t.replace("y", "i").replace("j", "i").replace("v", "u").replace("oi", "ai")
    t = re.sub(r"([ae])nts$", r"\1ns", re.sub(r"ez$", "es", t))  # enfans, alliez: enfants, alliés
    return ABBREV.get(t, "et" if t == "" else t)


MARGIN_YEAR = re.compile(r"(?:An[.-]?)?\d{3,4}[.,]?|An\.?")  # An.2585. An-2917,
ROMAN_NUMERAL = re.compile(r"(?=[IVXLCDM])M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})")


def numeral(t):
    """A number: digits, or a roman numeral (the JSON has them in arabic: Juges XVII. 4 is 17:4) -- an
    OCR l for I allowed (XIl)."""
    return t.isdigit() or bool(ROMAN_NUMERAL.fullmatch(t.replace("l", "I") if len(t) > 2 else t))


def ocr_tokens(o):
    """The OCR's words in reading order as tokens: a String may hold several ("21.Et"), a word cut at
    the line's end (¬) is joined to the next line's first. Each: {t, k, boxes, wc, line}."""
    out, carry, held = [], None, []
    mid, lines = gutter(o), o["lines"]
    side = [ln["box"][0] > mid for ln in lines]
    carry_to = None  # where a cut word goes on: the next line of its column (verses: a French line, then a Latin one)
    for li, ln in enumerate(lines):
        ws = ln["words"]
        body = len(ws)  # the margin's year ends a line (An.2585.): after the word cut at the end of the line
        while body and MARGIN_YEAR.fullmatch(ws[body - 1]["t"]):
            body -= 1
        for wi, w in enumerate(ws):
            text, (x, y, bw, bh) = unicodedata.normalize("NFC", w["t"]), w["box"]
            n = max(1, len(text))
            year = re.fullmatch(r"(.+?)-?An\.?-?\d{3,4}\.?", text)  # ren-An.2784: the year is glued to a cut word
            body_text = year.group(1) + "-" if year else text
            ms = list(OCR_TOKEN.finditer(body_text))
            for m, pt in zip(ms, _surfaces(body_text, [m.span() for m in ms])):
                a, b = m.span()
                tok = {"t": m.group(), "boxes": [[x + round(bw * a / n), y, max(1, round(bw * (b - a) / n)), bh]],
                       "wc": w["wc"], "line": li, "src": [[li, wi]], "pt": pt}
                if wi >= body and body and ws[body - 1]["t"].endswith(("¬", "-")):
                    held.append(tok)  # the year goes on after the word it interrupts
                    continue
                if carry and li == carry_to:  # the first word after a cut
                    carry["t"] += tok["t"]
                    carry["pt"] = carry["pt"].rstrip("-¬") + tok["pt"]
                    carry["boxes"] += tok["boxes"]
                    carry["src"] += tok["src"]
                    carry["wc"] = min(carry["wc"], tok["wc"])
                    tok, carry = carry, None
                    out.append(tok)
                    out.extend(held)
                    held = []
                    continue
                out.append(tok)
            if (wi == body - 1 or year) and (year or text.endswith(("¬", "-"))) and out and out[-1]["line"] == li:
                carry = out.pop()
                carry_to = next((k for k in range(li + 1, min(li + 9, len(lines))) if side[k] == side[li]), li + 1)
    out.extend(held)
    if carry:
        out.append(carry)
    for t in out:
        t["k"] = key(t["t"])
    return out


OPENING = "(«[{“‘¿¡"


def _surfaces(text, spans):
    """Each token's printed surface in a String: its letters and the marks touching them (l’|Homme.,
    21.|Et, (Gen.): an apostrophe and closing marks go with the word before, opening marks with the word after."""
    if not spans:
        return []
    cuts = [0]
    for (_, b), (a, _) in zip(spans, spans[1:]):
        gap = text[b:a]
        k = len(gap)
        while k and gap[k - 1] in OPENING:
            k -= 1
        cuts.append(b + k)
    cuts.append(len(text))
    return [text[cuts[i]:cuts[i + 1]] for i in range(len(spans))]


@functools.lru_cache(maxsize=1 << 14)  # good_variants.record asks a third of its texts again (via printed())
def modern(text):
    """The modernized text (as normalized is), or None when the modernization fails."""
    try:
        from clean_mechanical import fix_spelling
        from modernize_inplace import modernize_text
        import fix_typography  # the typography rules normalized has (long s, & c., et c., monnaie, &)
        text = fix_typography.fix(text.replace("’", "'"))
        return modern_words(modernize_text(fix_spelling(text))[0])
    except Exception:
        return None


OLD_FORMS = [("oi", "ai"), ("oî", "aî"), ("ans", "ants"), ("ens", "ents")]  # avoit, paroît, enfans, présens


def modern_words(text, known=None):
    """Old spellings the modernization left (confondoient, connoissance, enfans) as the modern word normalized
    uses: one OLD_FORMS change, and only to a word French knows (spellcheck.bare_french_words) when the word
    itself is unknown. Nothing else is guessed: names (Esau, Cain), Latin (Deus) and verbs (multipliez) stay."""
    import spellcheck
    known = spellcheck.bare_french_words() if known is None else known
    if not known:
        return text

    def one(m):
        w = m.group()
        wl = w.lower()
        if wl in known or len(w) < 4 or wl in PRINTED_ABBREV:  # Matth. is not Math.
            return w
        found = set()
        for old, new in OLD_FORMS:
            i = wl.find(old)
            while i >= 0:
                v = wl[:i] + new + wl[i + len(old):]
                if v in known:
                    found.add(v)
                i = wl.find(old, i + 1)
            if not found and wl.count(old) > 1 and old in ("oi", "oî"):  # connoissoit: every oi is an ai
                v = wl.replace(old, new)
                if v in known:
                    found.add(v)
        if len(found) != 1:
            return w
        v = found.pop()
        return v.upper() if w.isupper() else v[0].upper() + v[1:] if w[0].isupper() else v
    # the imparfait and conditionnel in -oit/-oient hunspell does not know, whose -ait/-aient form it does
    # (the word list above only holds words the text has): tendoit, possedoient, connoissoit
    cands = {}
    for m in re.finditer(r"[^\W\d_]+", text):
        w = m.group()
        wl = w.lower()
        if len(w) >= 5 and wl not in known and re.search(r"o[iî]t$|o[iî]ent$", wl):
            cands[w] = wl.replace("oî", "aî").replace("oi", "ai")
    if cands:
        bad = spellcheck.check(sorted(set(cands) | set(c.lower() for c in cands.values())))
        ok = {w for w, v in cands.items() if w.lower() in bad and v not in bad}
    else:
        ok = set()

    def two(m):
        w = m.group()
        if w not in ok:
            return one(m)
        v = cands[w]
        return v.upper() if w.isupper() else v[0].upper() + v[1:] if w[0].isupper() else v
    return re.sub(r"[^\W\d_]+", two, text)


# words a stop may close without ending the sentence: Saint, chapters, books of the Bible, sources
PRINTED_ABBREV = set("""s st ste ch chap cap liv lib art comm vers tom pag ibid etc cf voy ant antiq hist epist
ep serm quaest hom sup inf gen exod exo levit lev num deut jos judic jud reg paral esdr tob judith esth job psal
ps prov eccl eccle cant sap eccli isai is jerem jer baruc bar ezech dan ose osee joel abd jon mich nah habac soph
agg zach malach mal mach matth matt marc luc joan act rom cor galat gal ephes eph philip phil coloss col thess tim
tit philem hebr heb jac petr pet joann apoc""".split())
MARK = re.compile(r"[.,;:!?]")
WC_LOW = 0.6  # a mark from a word Kraken read below this is to check


def printed(words, closes=False, latin=False):
    """The words' printed surfaces (`pt`, else `t`) as modern text: {text, flags}. Flags point at marks to check
    against the scan, as offsets into text: {a, b, why}; why: stop_lower (a stop, then a lowercase word),
    inner (a mark inside a word), doubled (two marks), low_conf (a mark Kraken read unsure), no_end (`closes`:
    the text should end a sentence and has no mark). `latin`: not modernized, only ſ and ’ made plain."""
    raw = ""
    for w in words:
        p = w.get("pt") or w.get("t") or ""
        raw = raw + p if not raw or raw.endswith(("’", "'")) else raw + " " + p
    text = (raw.replace("ſ", "s").replace("’", "'") if latin else modern(raw)) if raw else ""
    if text is None:
        text = raw
    return {"text": text, "flags": flags_of(text, [w.get("wc", 1) for w in words for _ in MARK.findall(w.get("pt") or "")], closes)}


def flags_of(text, marks_wc=None, closes=False):
    """printed()'s flags on a modern text; `marks_wc`: the confidence of each printed mark, in order."""
    flags = []
    for m in re.finditer(r"(\S*?)\.(\s+)(?=[^\W\d_])", text):
        nxt = text[m.end()]
        word = re.sub(r"[^\w]", "", m.group(1).split(".")[-1]).lower()
        if nxt.islower() and len(word) > 2 and word not in PRINTED_ABBREV:
            a = m.start() + len(m.group(1))
            flags.append({"a": a, "b": a + 1, "why": "stop_lower"})
    for m in re.finditer(r"(?<=[^\W\d_])[.,;:](?=[^\W\d_])", text):
        if not (text[m.start() - 1].isupper() and text[m.end()].isupper()):
            flags.append({"a": m.start(), "b": m.end(), "why": "inner"})
    for m in re.finditer(r"[.,;:]{2,}", text):
        if m.group() != "...":
            flags.append({"a": m.start(), "b": m.end(), "why": "doubled"})
    # the k-th mark of the text is the k-th printed one, when the modernization kept their number
    marks_raw = marks_wc or []
    marks = list(MARK.finditer(text))
    if marks_wc and len(marks) == len(marks_raw):
        taken = {f["a"] for f in flags}
        for m, wc in zip(marks, marks_raw):
            if wc < WC_LOW and m.start() not in taken:
                flags.append({"a": m.start(), "b": m.end(), "why": "low_conf"})
    if closes and text and not re.search(r"[.?!:;][»)\]]*\s*$", text):
        flags.append({"a": len(text), "b": len(text), "why": "no_end"})
    return sorted(flags, key=lambda f: f["a"])


HEAD_FIELDS = ["book_title", "chapter_title", "chapter_summary", "chapter_argument", "chapter_intro"]
TEXT_FIELDS = {"verses": ["annotations", "latin"], "verses_fr": ["french"],  # the year is in the left margin
               "commentary": ["latin_quote", "french_translation", "french_commentary"], "footnotes": ["marker", "text"]}
MARKUP = re.compile(r"\^\{|\}")


def json_tokens(data):
    """The page's words in the scan's order: the notes on the chapter before (a chapter opens), headings,
    the verses' Latin column then their French, the commentary, the footnotes. Each: {t, k, path, a, b} (a, b: offsets in the field's string)."""
    notes = data.get("commentary") or []
    # on a page where a chapter opens, the notes on the chapter before are printed above its title
    opening = data.get("chapter_title") and (data.get("verses") or [{}])[0].get("chapter")
    before = 0
    while opening and before < len(notes) and notes[before].get("chapter") not in (None, opening):
        before += 1
    fields = [(f"commentary/{i}/{f}", notes[i].get(f)) for i in range(before) for f in TEXT_FIELDS["commentary"]]
    fields += [(f, data.get(f)) for f in HEAD_FIELDS]
    for sec in ("verses", "verses_fr", "commentary", "footnotes"):
        src = "verses" if sec == "verses_fr" else sec
        for i, blk in enumerate(data.get(src) or []):
            if sec == "commentary" and i < before:
                continue
            for f in TEXT_FIELDS[sec]:
                fields.append((f"{src}/{i}/{f}", blk.get(f)))
    fields.append(("book_end_marker", data.get("book_end_marker")))
    out = []
    for path, s in fields:
        if not isinstance(s, str):
            continue
        for m in TOKEN.finditer(MARKUP.sub(lambda m: " " * len(m.group()), s)):
            out.append({"t": m.group(), "k": key(m.group()), "path": path, "a": m.start(), "b": m.end()})
    return out


@functools.lru_cache(maxsize=1 << 20)  # _pair asks the same pairs again: a Good page against 5 pages
def similar(a, b):
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


CONFUSED = [set("tlrfsi"), set("ceo"), set("nu")]  # letters Kraken mistakes for each other in this type


@functools.cache
def slip(o, j):
    """Two keys that differ only as Kraken's slips or old spelling do: a doubled letter (jetter, AAn), or
    one letter for a look-alike (salte, traduite)."""
    def look_alike(o, j):
        diff = [(x, y) for x, y in zip(o, j) if x != y]
        return len(o) == len(j) and len(diff) == 1 and any(set(diff[0]) <= g for g in CONFUSED)
    single = lambda t: re.sub(r"(.)\1+", r"\1", t).rstrip("s")  # Hipocrates: Hippocrate
    return single(o) == single(j) or look_alike(o, j) or look_alike(single(o), single(j))


NUMBER_WORDS = {"un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix", "onze", "douze",
                "treize", "quatorze", "quinze", "seize", "uingt", "uingts", "trente", "quarante", "cinquante",
                "saixante", "cent", "cents", "mille"}  # keys


def _number(ocr_toks):
    """A number the scan prints with & (soixante & dix-sept): its key without the et, else None."""
    words = [t for t in ocr_toks if t["t"] not in ("&", "et")]
    if len(words) < 2 or len(words) == len(ocr_toks):  # et dix for dix: the et may be a real word missing
        return None
    if not all(_key(x) in NUMBER_WORDS for t in words for x in t["t"].split("-")):
        return None
    return "".join(_key(t["t"]) for t in words)


def _joined_same(ocr_toks, json_toks, k, jk):
    """Words joined on one side or the other that make the same word: the same key, a slip, quæ read qua,
    the same once modernized, or a number printed with & (soixante & dix: soixante-dix)."""
    ae = "".join(_key(t["t"].replace("æ", "a").replace("Æ", "A")) for t in json_toks)
    return (k == jk or slip(k, jk) or ae == k
            or modern_key(" ".join(t["t"] for t in ocr_toks)) in (jk, jk.replace("-", ""))
            or _number(ocr_toks) == jk)


def _pair(ocr_run, json_run, allow=None, least=0.5, skip_least=None):
    """Inside a stretch the two disagree on: [(ocr indexes, json index or None, json count, status)].
    `allow(ocr word, json word, exact)`: False keeps the two apart (`exact`: their keys, joined, the same);
    with it (the fixed alignment), words are joined only when they make the same word or a likelier one
    than any of them alone; `least`: the likeness a pair needs; `skip_least`: the likeness a pair needs
    that passes over JSON words left unpaired (they stay red), but for the same word."""
    out, j = [], 0
    i = 0
    while i < len(ocr_run):
        best = None
        for jj in range(j, min(len(json_run), j + 3)):
            for take, jtake in ((1, 1), (2, 1), (1, 2), (1, 3)) + (((3, 1),) if allow else ()):  # 2:1, 1:2, 1:3 (tout-à-fait), a space lost or added; 3:1 (soixante & dix)
                if i + take > len(ocr_run) or jj + jtake > len(json_run):
                    continue
                if (take > 1 or jtake > 1) and not all(t["k"] for t in ocr_run[i:i + take] + json_run[jj:jj + jtake]):
                    continue  # a piece with no key ("" + sedenti is sedenti): no join
                k = "".join(t["k"] for t in ocr_run[i:i + take])
                jk = "".join(t["k"] for t in json_run[jj:jj + jtake])
                r = similar(k, jk) - 0.05 * (jj - j) - 0.02 * (take + jtake - 2)
                if r < least or best is not None and r <= best[0]:
                    continue  # it could not be kept (the tests below only refuse): spared them
                if allow and not allow(ocr_run[i], json_run[jj], k == jk):
                    continue
                same = _joined_same(ocr_run[i:i + take], json_run[jj:jj + jtake], k, jk)
                if take == 3 and not same:
                    continue  # three of the scan's words: only when they make the word
                if allow and (take > 1 or jtake > 1) and not same and similar(k, jk) <= max(
                        similar(x, y) for x in ([t["k"] for t in ocr_run[i:i + take]] if take > 1 else [k])
                        for y in ([t["k"] for t in json_run[jj:jj + jtake]] if jtake > 1 else [jk])):
                    continue  # deux colomnes: colonnes (colomnes alone is likelier); répom dent: répondent joins
                if skip_least is not None and jj > j and not same and similar(k, jk) < skip_least:
                    continue  # nostrum: not past "in" to a nostram further on (a slip-equal one, nostrums, still pairs: a known limit)
                best = (r, jj, take, jtake, k, jk)
        if best and best[0] >= least:
            r, jj, take, jtake, k, jk = best
            ae = "".join(_key(t["t"].replace("æ", "a").replace("Æ", "A")) for t in json_run[jj:jj + jtake])  # quæ read qua
            if k != jk and (ae == k or modern_key(" ".join(t["t"] for t in ocr_run[i:i + take])) in (jk, jk.replace("-", ""))
                            or _number(ocr_run[i:i + take]) == jk):
                k = jk
            status = ("ok" if k == jk or (slip(k, jk) and (take == jtake == 1 or take == 1 and "-" in ocr_run[i]["t"]))  # a lost space is the OCR's; même-tems: même temps
                      else "near" if r >= 0.8 and take == jtake == 1 else "diff")
            out.append((list(range(i, i + take)), jj, jtake, status))
            i, j = i + take, jj + jtake
        else:
            out.append(([i], None, 0, "missing"))
            i += 1
    return out


HEADER = re.compile(r"COMMENTAIRE|LITTERAL|^SUR\b|CHAP")  # capitals: a body line may open with "sur"


def misread_head(text):
    """A running head (or the "COMMENTAIRE.") misread, in capitals: S'UR LES, SURLESIUGES, COMME NTAIRE
    LITTERAI., COMMENTAIRF. (Juges); a lemma in capitals is not one (FERTE SENTENTIAM)."""
    caps = re.sub(r"[^A-Z]", "", text)
    letters = sum(c.isalpha() for c in text)
    return bool(caps) and len(caps) >= 0.8 * letters and (caps.startswith("SURLES") or any(
        similar(re.sub(r"[^A-Z]", "", w), h) >= 0.8 for w in text.split() for h in ("COMMENTAIRE", "LITTERAL")))


def skipped_lines(o, fix=False):
    """Lines no field holds: the running header (in the top band, but for the year in the margin) and the
    "COMMENTAIRE." between the verses and the commentary. `fix`: their misreadings too, in the top tenth."""
    h = o["size"][1]
    out = set()
    for li, ln in enumerate(o["lines"]):
        text = " ".join(w["t"] for w in ln["words"])
        top = ln["box"][1] < 0.075 * h
        if (top and (HEADER.search(text) or re.fullmatch(r"[\dIVXLC.\s]+", text))) or re.fullmatch(r"COMMENTAIRE\.?", text.strip()):
            out.add(li)
        elif fix and ln["box"][1] < 0.10 * h and misread_head(text):
            out.add(li)
    return out


MISREAD_NUMERAL = re.compile(r"[IVXLCDMivxlcdm0-9]{1,6}\.?")


def misread_numeral(t):
    """A roman numeral misread: a digit among its letters (L2, I0), or capitals and small letters mixed
    (xII, viII) -- not as a word is (Il, Civil); a word of those letters alone stays one (dixi, dic, vix, mi)."""
    if not MISREAD_NUMERAL.fullmatch(t):
        return False
    letters = [c for c in t if c.isalpha()]
    title = t[0].isupper() and t[1:].rstrip(".").islower()
    return bool(letters) and (any(c.isdigit() for c in t) or (not title and any(c.isupper() for c in letters)
                                                               and any(c.islower() for c in letters)))


def split_columns(o):
    """A line Kraken read across the gutter (a verse's Latin and French on one line) cut in two, the
    right part put before the right column's next line, so the reading goes column by column."""
    lines = [dict(ln, words=list(ln["words"])) for ln in o["lines"]]
    mid, gut = o["size"][0] * 0.45, gutter(o)
    head = min((ln["box"][1] for ln in lines if re.sub(r"[^A-Z]", "", "".join(w["t"] for w in ln["words"]).upper())
                == "COMMENTAIRE" and ln["box"][1] > 0.1 * o["size"][1]), default=0)  # the verses end there
    right_ys = [ln["box"][1] for ln in lines if ln["box"][0] > gut and ln["box"][1] < head]  # the French column's lines
    i = 0
    while i < len(lines):
        ws, h = lines[i]["words"], lines[i]["box"][3]
        cut = next((k for k in range(1, len(ws)) if ws[k]["box"][0] > mid
                    and ws[k]["box"][0] - (ws[k - 1]["box"][0] + ws[k - 1]["box"][2]) > max(60, 2 * h)), None)
        y = lines[i]["box"][1]
        if cut is None and y < head and lines[i]["box"][0] < gut and any(0 < abs(r - y) < 2.5 * h for r in right_ys) \
                and any(c.islower() for w in ws for c in w["t"]):
            # no gap, the French column beside: the gutter's rule read as a letter (mani-i re) or glued in a
            # word (addu-[mandérent): cut at it
            ws = lines[i]["words"] = [x for w in ws for x in _at_rule(w, gut)]
            cut = next((k for k in range(1, len(ws)) if ws[k]["box"][0] > gut and ws[k - 1]["box"][0] < gut), None)
        if cut is not None:
            left, right = ws[:cut], ws[cut:]
            span = lambda w: [w[0]["box"][0], min(x["box"][1] for x in w),
                              w[-1]["box"][0] + w[-1]["box"][2] - w[0]["box"][0], h]
            lines[i] = dict(lines[i], words=left, box=span(left))
            piece = dict(lines[i], words=right, box=span(right))
            py = piece["box"][1]  # among the right column's lines by height: two lines cut, their pieces in order
            col = min(mid, gut)
            at = next((k for k in range(i + 1, len(lines)) if lines[k]["box"][0] > col and lines[k]["box"][1] > py), i + 1)
            lines.insert(at, piece)
        i += 1
    return dict(o, lines=lines)


RULE = re.compile(r"(?<=-)[\[\]|¡Il](?=\W*$|[^\W\d_])|[\[\]|¡]")  # the gutter's rule in a word: addu-[mandérent, fecerún-I


def _at_rule(w, gut):
    """A word across the gutter cut at the rule read in it (dropped), when the rule falls by the gutter."""
    t, (x, y, bw, bh) = w["t"], w["box"]
    if not (x < gut < x + bw):
        return [w]
    n = max(1, len(t))
    for m in RULE.finditer(t):
        at = x + bw * m.start() / n
        if abs(at - (gut + 15)) < 60:
            a, b = t[:m.start()], t[m.end():]
            xb = round(x + bw * m.end() / n)
            return [dict(w, t=a, box=[x, y, max(1, round(bw * m.start() / n)), bh])] * bool(a) + \
                [dict(w, t=b, box=[xb, y, max(1, x + bw - xb), bh])] * bool(b)
    return [w]


def gutter(o):
    """Where the right column starts: 30 px before the middle start of the lines begun between 0.3 and 0.7
    of the width (the page sits further left or right on the scan); else 0.45 of the width."""
    w = o["size"][0]
    starts = sorted(ln["box"][0] for ln in o["lines"] if 0.3 * w < ln["box"][0] < 0.7 * w)
    return (starts[(len(starts) - 1) // 2] + starts[len(starts) // 2]) / 2 - 30 if starts else 0.45 * w


def _allow(o):
    """The pairs the fixed alignment refuses, `o` the columns split: but for the same word, a word of the
    right column with a verse's Latin, of the left with its French; a verse number with a word (a number,
    a range 51-52, the same numeral XC, a slip II for Il allowed). The right column: from 30 px before the middle start of the lines begun
    between 0.3 and 0.7 of the width (the page sits further left or right on the scan); else 0.45."""
    mid = gutter(o)

    def allow(ot, jt, exact=False):
        right, path = ot["boxes"][0][0] >= mid, jt["path"]
        if not exact and path.startswith("verses/") and (path.endswith("/latin") and right or path.endswith("/french") and not right):
            return False
        return not numeral(ot["t"]) or exact or any(c.isdigit() for c in jt["t"]) or slip(ot["k"], jt["k"])
    return allow


def _repair_leftovers(res, ot, jt, link, allow, key_of=lambda t: t["k"], least=0.5, skip_least=0.9):
    """The scan's words still unpaired, paired again with the JSON's words still unpaired in the field of
    one of the words linked either side of them, between the nearest scan words linked in that field (a
    misread the stretches cut apart: inimi-I eus, répom dent; soptem between a French line and a Latin
    one). `key_of`: the scan word's key (another reading of it: Tesseract's); `skip_least`: the likeness a pair needs that passes over unpaired JSON words (else the same word)."""
    first = {(t["path"], t["a"]): j for j, t in enumerate(jt)}

    def linked(r):  # the JSON's words a scan word is linked to (the last may be in the next field)
        j = first[r["path"], r["a"]]
        return range(j, next(k for k in range(j, len(jt)) if jt[k]["b"] == r["b"]) + 1)
    used = {j for r in res if "path" in r for j in linked(r)}
    keyed = lambda t: dict(t, k=key_of(t))
    i = 0
    while i < len(res):
        if "path" in res[i]:
            i += 1
            continue
        e = i
        while e < len(res) and "path" not in res[e]:
            e += 1
        sides = [n for n in (i - 1, e) if 0 <= n < len(res)]
        for path in dict.fromkeys(res[n]["path"] for n in sides):
            # the neighbours in this field: on a verse page the scan goes a French line, a Latin line, so
            # the words either side of a misread are often one in each field
            before = next((n for n in range(i - 1, -1, -1) if res[n].get("path") == path), None)
            after = next((n for n in range(e, len(res)) if res[n].get("path") == path), None)
            lo = max(linked(res[before])) if before is not None else -1
            hi = min(linked(res[after])) if after is not None else len(jt)
            run = [n for n in range(i, e) if "path" not in res[n] and key_of(ot[n]) is not None]  # None: no reading
            cand = [j for j in range(lo + 1, hi) if j not in used and jt[j]["path"] == path]
            if not run or not cand:
                continue
            for idx, j, n, status in _pair([keyed(ot[x]) for x in run], [jt[x] for x in cand], allow, least, skip_least):
                if run[idx[-1]] - run[idx[0]] != len(idx) - 1:
                    continue  # a join over a scan word left out (no reading): not made, it stays red
                for x in idx:  # a join only over the JSON's words next to each other (link takes those between)
                    if j is not None and cand[j + n - 1] == cand[j] + n - 1:
                        link(run[x], cand[j], status, n)
                        used.update(cand[j:j + n])
        i = e


OUT_OF_SCOPE = re.compile(r"verses/\d+/(?:latin|annotations)")  # the verses' Latin and margin: no red there
LEMMA_MARK = 3  # the longest a lemma's verse number reads (ỳ. 19.: Y19, VA7, IJ)
LATIN_QUOTE = re.compile(r"commentary/\d+/latin_quote")
NOTE_READ = re.compile(r"(?:[(\[][a-zàâèéòó][a-zjlY0-9ꝯ]?[)\]]?|[(\[]?[A-Za-z0-9]?[a-zàâèéòó][)\]])[il]?[.,:;]*")  # a note's mark misread: Ce) Id) (eY (sj 1b) (fe),


def _out_of_scope(o, res):
    """Red only where the reviewer looks, the commentary and the verses' French: a scan word left unpaired
    between words of the verses, in the Latin column (left of the gutter) or between Latin or margin words
    only, is skipped; so is a short word or one with a digit read just before a lemma (its verse number)."""
    mid = gutter(o)
    prev, nxt, last = [None] * len(res), [None] * len(res), None
    for i, r in enumerate(res):
        prev[i], last = last, (i if "path" in r else last)
    last = None
    for i in range(len(res) - 1, -1, -1):
        nxt[i], last = last, (i if "path" in res[i] else last)
    for i, r in enumerate(res):
        if r["s"] != "missing":
            continue
        near = [res[n]["path"] for n in (prev[i], nxt[i]) if n is not None]
        if near and all(p.startswith("verses/") for p in near) and (
                all(OUT_OF_SCOPE.fullmatch(p) for p in near) or r["boxes"][0][0] < mid):
            r["s"] = "skip"
        elif (nxt[i] is not None and nxt[i] - i <= 2 and LATIN_QUOTE.fullmatch(res[nxt[i]]["path"])
              and res[nxt[i]]["a"] == 0 and (len(r["t"]) <= LEMMA_MARK or any(c.isdigit() for c in r["t"]))):
            r["s"] = "skip"


def _note_marks(o, data, res):
    """A note's mark the scan misreads, "(e)" as "Ce)": not red, not a different word. Paired to the
    text's note letter it is the same; else (unpaired, or paired to a word) it is left out."""
    text = dict(_fields(data))
    for r in res:
        if r["s"] not in ("missing", "diff", "near", "both") or len(r["src"]) != 1:
            continue
        li, wi = r["src"][0]
        if not NOTE_READ.fullmatch(o["lines"][li]["words"][wi]["t"]):
            continue
        f = text.get(r.get("path")) or ""
        r["s"] = "ok" if "a" in r and f[max(0, r["a"] - 3):r["a"]].endswith("{(") else "skip"


def align(o, data, fix=False, tess=None):
    """The OCR set against the JSON: {"size", "words": [{t, boxes, s, path?, a?, b?}], "extra": [{t, path,
    a, b}]}. A word's `s`: ok (the same word, old spelling allowed), near (nearly), diff (a different
    word), missing (not in the JSON), skip (the running header, an unsure reading, a footnote: they are
    expanded, so they differ by design). `extra`: the JSON's words the scan does not have (but for the
    footnotes'), with what they are written in. `fix`: the fixed alignment (the verses' columns kept apart,
    the verse numbers out of the words, the words left unpaired paired again, no red in the verses' Latin
    and margin nor for a lemma's verse number); `tess`: Tesseract's reading of the page (tess_ocr.read),
    with `fix`: the words still unpaired paired by it (`by`: tess), a paired
    word both OCRs read against the JSON `both` (`was`: its status before), `tt` its reading under each
    paired word, and `tess`: whether there was one."""
    o = split_columns(o)
    skip = skipped_lines(o, fix)
    ot = [t for t in ocr_tokens(o) if t["line"] not in skip]
    jt = json_tokens(data)
    res = [dict(t=t["t"], pt=t["pt"], boxes=t["boxes"], s="missing", src=t["src"], wc=t["wc"]) for t in ot]

    allow = _allow(o) if fix else None
    used, at = set(), {}  # at: a JSON word's index -> the scan's word linked to it

    def link(i, j, status, n=1):
        res[i].update(s=status, path=jt[j]["path"], a=jt[j]["a"], b=jt[j + n - 1]["b"])
        used.update(range(j, j + n))
        at.update((x, i) for x in range(j, j + n))

    sm = difflib.SequenceMatcher(None, [t["k"] for t in ot], [t["k"] for t in jt], autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for d in range(i2 - i1):
                link(i1 + d, j1 + d, "ok")
        elif op == "replace":
            for idx, j, n, status in _pair(ot[i1:i2], jt[j1:j2], allow):
                for i in idx:
                    if j is not None:
                        link(i1 + i, j1 + j, status, n)
    # what is left on both sides, the same words in another order (the margin's years): linked too
    for _ in range(4):  # again while it finds some: a pass keeps only blocks that do not cross
        rest = [i for i, r in enumerate(res) if "path" not in r]
        free = [j for j in range(len(jt)) if j not in used]
        sm = difflib.SequenceMatcher(None, [ot[i]["k"] for i in rest], [jt[j]["k"] for j in free], autojunk=False)
        found = 0
        for a, b, n in sm.get_matching_blocks():
            if n >= 2 or (n == 1 and len(ot[rest[a]]["k"]) >= 4):
                for d in range(n):
                    if not allow or allow(ot[rest[a + d]], jt[free[b + d]], True):
                        link(rest[a + d], free[b + d], "ok")
                        found += 1
        if not found:
            break
    tess = fix and tess and tess["words"] and tess
    if fix:
        _repair_leftovers(res, ot, jt, link, allow)
    if tess:
        from tess_ocr import under
        read = [under(tess, t["boxes"]) for t in ot]

        def by_tess(i, j, status, n=1):
            link(i, j, status, n)
            res[i]["by"] = "tess"
        tk = {id(t): key(r) if any(c.isalnum() for c in r) else None  # nothing beneath (or only a dash): no key, left out
              for t, r in zip(ot, read)}
        _repair_leftovers(res, ot, jt, by_tess, allow, lambda t: tk[id(t)], 0.7)
    # a body word paired with a footnote's (a "dans" of the text with the note's first word) is a wrong pairing: the
    # notes are a block of consecutive words at the page's foot, so a footnote word alone, well above, is unlinked
    in_fn = [(r.get("path") or "").startswith("footnotes/") for r in res]
    block = [i for i in range(len(res)) if in_fn[i] and ((i > 0 and in_fn[i - 1]) or (i + 1 < len(res) and in_fn[i + 1]))]
    if block:
        top = min(res[i]["boxes"][0][1] for i in block)
        for i, r in enumerate(res):
            if in_fn[i] and i not in block and r["boxes"][0][1] < top - 0.1 * o["size"][1]:  # well above: a body line, not a note line misread
                for j in [j for j, n in at.items() if n == i]:
                    del at[j]
                    used.discard(j)
                for k in ("path", "a", "b"):
                    r.pop(k, None)
                r["s"] = "missing"
    # around the footnotes (expanded by design), the unmatched are not flagged; nor are unsure readings
    near_path = [None] * len(res)
    last = None
    for i, r in enumerate(res):
        last = r.get("path", last)
        near_path[i] = last
    for i in range(len(res) - 1, -1, -1):
        nxt = res[i].get("path") or (near_path[i + 1] if i + 1 < len(res) else None)
        near_path[i] = near_path[i] or nxt
    for r, t, p in zip(res, ot, near_path):
        if r["s"] in ("missing", "diff", "near") and (
                t["wc"] < 0.6 or (p or "").startswith("footnotes/") or (r.get("path") or "").startswith("footnotes/")):
            r["s"] = "skip" if r["s"] == "missing" else "ok"
        if r["s"] == "missing" and (numeral(t["t"]) or len(t["t"]) <= 1 or MARGIN_YEAR.fullmatch(t["t"])):  # a verse number (roman too), a stray letter, the margin's year
            r["s"] = "skip"
        if fix and r["s"] == "missing" and misread_numeral(t["t"]):  # xII, L2
            r["s"] = "skip"
    # nor the top and bottom bands (a header misread, the catchword), nor what is below the first footnote
    h = o["size"][1]
    fn_top = min((r["boxes"][0][1] for r in res if (r.get("path") or "").startswith("footnotes/")), default=h)
    for r in res:
        y = r["boxes"][0][1]
        if r["s"] == "missing" and (y < 0.075 * h or y > 0.88 * h or y >= fn_top - 5):
            r["s"] = "skip"
        sl = word_slant(o, r)
        if sl is not None:
            r["sl"] = round(sl)
    if fix:
        _out_of_scope(o, res)
        _note_marks(o, data, res)
    extra = [dict(t=t["t"], path=t["path"], a=t["a"], b=t["b"]) for j, t in enumerate(jt)
             if j not in used and not t["path"].startswith("footnotes/") and len(t["t"]) > 1 and not t["t"].isdigit()
             and not (fix and OUT_OF_SCOPE.fullmatch(t["path"]))]
    if tess:
        _both(res, ot, jt, read)
    out = {"size": o["size"], "words": res, "extra": extra, "unscanned": _unscanned(jt, at, res)}
    if fix:
        out.update(fix=fix, tess=bool(tess))
    return out


def _both(res, ot, jt, read):
    """`tt` on every paired word; `both` on those Tesseract reads as Kraken does (the same key or modern
    key), against the JSON's word, but for numbers and the pieces of a word split (its key under 60% of
    the JSON's, or a scan word beside it linked to the same JSON words)."""
    first = {(t["path"], t["a"]): j for j, t in enumerate(jt)}
    span = lambda r: (r.get("path"), r.get("a"), r.get("b"))
    for i, (r, t, tt) in enumerate(zip(res, ot, read)):
        if "path" not in r:
            continue
        r["tt"] = tt
        j = first[r["path"], r["a"]]
        jk = "".join(x["k"] for x in jt[j:next(k for k in range(j, len(jt)) if jt[k]["b"] == r["b"]) + 1])
        piece = any(0 <= n < len(res) and span(res[n]) == span(r) for n in (i - 1, i + 1))
        if (r["s"] in ("diff", "near") and tt and (key(tt) == t["k"] or modern_key(tt) == modern_key(t["t"]))
                and t["k"] != jk and not numeral(t["t"]) and len(t["k"]) >= 0.6 * len(jk) and not piece):
            r.update(was=r["s"], s="both")


def _unscanned(jt, at, res, least=3):
    """Runs of the JSON's words the scan does not have, read where the scan was read: `least` words or
    more (of two letters or more), with linked words both sides, one in the same field, and few of the scan's
    words between those two, a third of theirs or less (else the scan has words there, misread: Orda concubinc). Each: {path, a, b}."""
    used = at
    out, j = [], 0
    while j < len(jt):
        if j in used:
            j += 1
            continue
        k = j
        while k + 1 < len(jt) and k + 1 not in used and jt[k + 1]["path"] == jt[j]["path"]:
            k += 1
        path = jt[j]["path"]
        words = [t for t in jt[j:k + 1] if len(t["t"]) > 1 and not t["t"].isdigit()]
        sides = [jt[n]["path"] for n in (j - 1, k + 1) if 0 <= n < len(jt) and n in used]
        between = res[at[j - 1] + 1:at[k + 1]] if len(sides) == 2 and at[j - 1] < at[k + 1] else None
        if (len(words) >= least and between is not None and path in sides and not path.startswith("footnotes/")
                and 3 * sum("path" not in r and len(r["t"]) > 1 and not numeral(r["t"]) for r in between) <= len(words)):
            out.append(dict(path=path, a=jt[j]["a"], b=jt[k]["b"], words=[at[j - 1], at[k + 1]]))
        j = k + 1
    # the page's end: the text runs on past the scan's last words (a stray word linked further on let by)
    body = [n for n, t in enumerate(jt) if not t["path"].startswith("footnotes/") and t["path"] != "book_end_marker"]
    if body:
        last = body[-1]
        j, strays = last, 0
        while j > 0 and jt[j - 1]["path"] == jt[last]["path"] and (j - 1 not in at or strays < 1 and len(jt[j - 1]["t"]) <= 4):
            strays += j - 1 in at
            j -= 1
        words = [t for t in jt[j:last + 1] if len(t["t"]) > 1 and not t["t"].isdigit()]
        if len(words) >= least and j - 1 in at and not any(r.get("a") == jt[j]["a"] and r.get("path") == jt[j]["path"] for r in out):
            after = [r for r in res[at[j - 1] + 1:] if not (r.get("path") or "").startswith("footnotes/") and r["s"] != "skip"]
            if 3 * sum("path" not in r and len(r["t"]) > 1 for r in after) <= len(words):
                out.append(dict(path=jt[j]["path"], a=jt[j]["a"], b=jt[last]["b"], end=True, words=[at[j - 1], at[j - 1]]))
    return out


def scan_box(size, res, i, j):
    """Where res[i..j] is on the scan, for a crop of it: {size, boxes (a box a line)}."""
    out = []
    for x, y, w, h in (b for r in res[i:j + 1] for b in r["boxes"]):
        last = out[-1] if out else None
        if last and x >= last[0] and abs((y + h / 2) - (last[1] + last[3] / 2)) < max(h, last[3]) * 0.8:
            x2, y2 = max(last[0] + last[2], x + w), max(last[1] + last[3], y + h)
            last[1] = min(last[1], y)
            last[2], last[3] = x2 - last[0], y2 - last[1]
        else:
            out.append([x, y, w, h])
    return {"size": size, "boxes": out}


def gaps(o, data, res=None, least=3):
    """Runs of words the scan has and the JSON lacks: `least` words or more, or two with eight letters
    or more (one word alone is mostly the modernization's), read with confidence. Each: {path, pos, ocr,
    text, before, after, words: [first, last], note?}: `note` when it opens with a lemma (a whole note
    missing); `text` (the scan's words in modern spelling) goes in at `pos` of field `path`
    (after the word before the run, or before the word after it when the run opens a field); `before`
    and `after`: the field's text around `pos`, to find the place again once the field has changed."""
    from clean_mechanical import fix_spelling
    from modernize_inplace import modernize_text
    o = split_columns(o)
    res = res or align(o, data)["words"]
    fields = {path: s for path, s in _fields(data)}
    out, i = [], 0
    while i < len(res):
        if res[i]["s"] != "missing":
            i += 1
            continue
        j = i
        while j + 1 < len(res) and res[j + 1]["s"] in ("missing", "skip") and "path" not in res[j + 1]:
            j += 1
        while res[j]["s"] == "skip":
            j -= 1
        # an elision opening the word after the run (dans l'Assyrie) goes in with it: it is skipped as a stray letter
        if (j + 2 < len(res) and res[j + 1]["s"] == "skip" and "path" not in res[j + 1] and len(res[j + 1]["t"]) == 1
                and res[j + 1]["t"].isalpha() and res[j + 2].get("path") and res[j + 1]["src"][0][0] == res[j]["src"][0][0]):
            j += 1
        run = [w for w in res[i:j + 1] if w["s"] == "missing"]
        sure = sum(w["wc"] for w in run) / len(run) >= 0.9  # gibberish (an ornament, Greek) reads unsure
        if sure and (len(run) >= least or (len(run) == 2 and sum(len(w["t"]) for w in run) >= 8)):
            # A B X A' B' with A' B' paired to the JSON (Votre père. Quam ... à votre père, the JSON having Votre père once):
            # the same alignment the other way, and the better one: X A' B' goes in after the JSON's words, A B are not missing
            k = 0
            while (i + k < j and j + 1 + k < len(res) and res[i + k]["s"] == "missing" and res[j + 1 + k]["s"] == "ok"
                   and res[j + 1 + k].get("path") and key(res[i + k]["t"]) == key(res[j + 1 + k]["t"])):
                k += 1
            if k and sum(len(w["t"]) for w in res[i:i + k]) >= 6 and not (res[j + k]["path"].startswith("footnotes/")):
                last = res[j + k]
                s_ = fields.get(last["path"]) or ""
                pos = last["b"]
                while pos < len(s_) and s_[pos] in ",.;:!?)»_}":
                    pos += 1
                g = {"path": last["path"], "pos": pos, "before": s_[max(0, pos - 30):pos], "after": s_[pos:pos + 30]}
                i, j, k = i + k, j + k, 0
                run = [w for w in res[i:j + 1] if w["s"] == "missing" or w is res[j]]
                if not any(w["s"] == "missing" for w in res[i:j + 1]):
                    g = None
            else:
                g = _place(res, i, j, fields)
            if g:
                ocr = _raw(o, res[i:j + 1])
                if j + 1 < len(res) and res[j + 1]["src"] == res[j]["src"] and res[j + 1].get("path"):  # l'|Assyrie: one scan word
                    ocr = ocr[:max(ocr.rfind("’"), ocr.rfind("'")) + 1]  # only up to the apostrophe, the word after is in the JSON
                text = modernize_text(fix_spelling(ocr.replace("ſ", "s").replace("&", "et").replace("’", "'")))[0]
                if REF_ONLY.fullmatch(ocr) or re.sub(r"[^A-Z]", "", ocr.upper()) == "COMMENTAIRE":  # a reference, written
                    i = j + 1  # out in the JSON (Judic. XVII. 4.: Juges 17:4); the heading misread (C.OM MENT.AIRE.)
                    continue
                note = bool(LEMMA.match(ocr))  # a whole note: a block of its own, not words in a field
                out.append(dict(g, ocr=ocr, text=text, flags=flags_of(text), words=[i, j], **({"note": True} if note else {})))
        i = j + 1
    return out


FRENCH_FIELDS = {"french_commentary", "french", "french_translation", "chapter_intro", "chapter_argument",
                 "chapter_summary", "chapter_title"}


def unscanned(o, data, al=None):
    """The JSON's runs of words the scan lacks (align's `unscanned`), with what they are written in: each
    {path, a, b, old, before, after}."""
    al = al or align(o, data)
    fields = dict(_fields(data))
    out = []
    for r in al["unscanned"]:
        s = fields[r["path"]]
        out.append(dict(r, old=s[r["a"]:r["b"]], before=s[max(0, r["a"] - 30):r["a"]], after=s[r["b"]:r["b"] + 30]))
    return out


def differs(o, data, res=None):
    """Words the scan prints, read with confidence, where the French text has another word, and the scan's
    word (modernized) is French where the text's is not, or both are (une for un, dessous for dessus).
    Not: a shorter or longer form of the same word (Exod., qu'), nor an a the scan has for u or o (an, lai,
    san: Kraken's). Each: {path, a, b, old, new, ocr, word (in res), known (the text's word is French),
    before, after, both (Tesseract reads it as Kraken does: the strongest)}."""
    from clean_mechanical import fix_spelling
    from modernize_inplace import modernize_text
    from spellcheck import check
    o = split_columns(o)
    res = res or align(o, data)["words"]
    fields = dict(_fields(data))
    cands = []
    for i, w in enumerate(res):
        path = w.get("path")
        if w["s"] not in ("diff", "near", "both") or w["wc"] < 0.95 or not path or path.rsplit("/", 1)[-1] not in FRENCH_FIELDS:
            continue
        if any(res[n].get("path") == path and res[n].get("a") == w["a"] for n in (i - 1, i + 1) if 0 <= n < len(res)):
            continue  # two of the scan's words for one of the text's
        s = fields[path]
        if s[max(0, w["a"] - 3):w["a"]].endswith("{("):
            continue  # a note's letter ^{(e)}, read with the word next to it (Ce)
        old = s[w["a"]:w["b"]]
        new = modernize_text(fix_spelling(_raw(o, [w]).replace("ſ", "s").replace("’", "'")))[0]
        toks = TOKEN.findall(new) or [""]
        el = re.search(r"(\w+)['’]$", s[max(0, w["a"] - 8):w["a"]])
        if len(toks) > 1 and el and toks[0].lower() == el.group(1).lower():
            toks = toks[1:]  # the scan's qu'Henoc for the text's qu'|Hénoch: the word, not the qu
        new = toks[0]
        lo, ln = old.lower(), new.lower()
        if len(new) < 2 or " " in old or key(new) == key(old) or lo.startswith(ln) or ln.startswith(lo):
            continue
        if w["src"][0][1] == 0 and lo.endswith(ln):
            continue  # a line's first word, the end of the text's word: the cut word's half (Taber-|nacle), the hyphen lost
        d = [(x, y) for x, y in zip(ln, lo) if x != y]
        if len(ln) == len(lo) and len(d) == 1 and d[0][0] == "a":
            continue
        cands.append(dict(path=path, a=w["a"], b=w["b"], old=old, new=new, ocr=w["t"], word=i,
                          before=s[max(0, w["a"] - 30):w["a"]], after=s[w["b"]:w["b"] + 30],
                          **({"both": True} if w["s"] == "both" else {})))
    unknown = check(sorted({c["old"] for c in cands} | {c["new"] for c in cands})) if cands else {}
    out = []
    for c in cands:
        if c["new"] not in unknown:
            out.append(dict(c, known=c["old"] not in unknown))
    return out


# --- italics ---
ITALIC_CHECKED = {"french_commentary", "french", "chapter_intro", "chapter_argument"}  # the rest: italic, or caps, by
# style; the footnotes are written out (their italic book names dropped)
LEANING = set("vwxyzkAVWXYZK")  # letters whose strokes lean in roman too: a word mostly of them is not told
SHORT_ITALIC, SHORT_ROMAN = 12, 2  # a word of one or two letters (à, La, ne, ô) votes only this clearly
ITALIC_AT, ROMAN_AT = 9, 4  # a word's slant, in degrees: italic from 9, roman to 4 (between: not told)


def word_slant(o, w):
    """The slant of a word as measured on the scan (o: split_columns'), or None (unmeasured, too small)."""
    sl = [o["lines"][li]["words"][wi].get("sl") for li, wi in w["src"]]
    sl = [x for x in sl if x is not None]
    return sum(sl) / len(sl) if sl else None


REF_AFTER = re.compile(r"\.?\s+\d+:\d+")  # Psaumes 118:17
NOTE_MARK = re.compile(r"\^\{[^}]*\}")  # ^{(f)}
ELIDED = re.compile(r"(?:^|(?<=[^\w_]))(\w{1,2})['’]$")  # d', l', qu' just before a word
NAME_ELISION = re.compile(r"(?:[a-zà-ÿ]|qu|jusqu|lorsqu|puisqu|quoiqu)['’]_?(?=[A-ZÀ-ÖØ-Þ])")  # d'Achad, l'Égypte, qu'Arphaxad: the elision before a name
SPLIT_ELISION = re.compile(r"(?<![\w_])_(\w{1,2})_(['’])_(?=\w)")  # _d_'_Achat_


def mark_json_italics(res, data):
    """Sets `it` on each word of `res` the JSON has in italics (all its letters inside _marks_), for the
    scan's wavy underline: what is italic already, so what the scan has in italics besides shows."""
    from page_text import italic_runs
    fields = dict(_fields(data))
    marks = {path: {i for a, b in italic_runs(s)[0] for i in range(a, b)} for path, s in fields.items() if isinstance(s, str)}
    for w in res:
        path = w.get("path")
        m = marks.get(path) if path else None
        if not m:
            continue
        f = fields[path]
        letters = [i for i in range(w["a"], min(w["b"], len(f))) if f[i].isalnum()]
        if letters and all(i in m for i in letters):
            w["it"] = True
    return res


def italics(o, data, res=None):
    """Stretches the scan prints in italics and the JSON in roman, or the other way. Each: {path, a, b,
    to: "italic" | "roman", words: [first, last] (in `res`), slant, old, before, after, new}: `old` is
    the field's a..b, `before` and `after` its text around (to find the place again), `new` the field
    with a..b toggled. Words of three letters or more vote; a lone word must lean clearly (12 or more,
    or 2 or less); a word two fifths of letters that lean anyway (voyez) has no vote."""
    from page_text import ROMAN_TRAILING, TRAILING_PUNCT, italic_runs, toggle_italics
    o = split_columns(o)
    res = res or align(o, data)["words"]
    fields = dict(_fields(data))
    marks = {path: {i for a, b in italic_runs(s)[0] for i in range(a, b)} for path, s in fields.items()}
    mid = gutter(o)

    def across(w):
        """A verse's word read in the other column (the Latin's Israël, italic, paired with the French's
        Israël, the same word): its slant is the other column's, it neither votes nor is taken in."""
        path = w.get("path") or ""
        if not path.startswith("verses/") or not w["src"]:
            return False
        li, wi = w["src"][0]
        right = o["lines"][li]["words"][wi]["box"][0] >= mid
        return path.endswith("/french") and not right or path.endswith("/latin") and right

    votes = []  # (index in res, the scan's italic?, the JSON's italic?, slant)
    for i, w in enumerate(res):
        path = w.get("path")
        if not path or w["s"] == "skip" or path.rsplit("/", 1)[-1] not in ITALIC_CHECKED or across(w):
            continue
        if any(re.fullmatch(r"\(\w\)\W*", o["lines"][li]["words"][wi]["t"]) for li, wi in w["src"]):
            continue  # a note's letter
        f = fields[path]
        if numeral(w["t"]) and not any(c.isalpha() for c in f[w["a"]:w["b"]]):
            continue  # 17, XVII (as after a ℣, or by a lemma); not Il read II
        src = "".join(o["lines"][li]["words"][wi]["t"] for li, wi in w["src"])
        if "&" in src:
            continue  # the & leans in roman too (&, &c.)
        if f[max(0, w["a"] - 3):w["a"]].endswith("{(") or f[w["a"]:w["b"]].isdigit() or REF_AFTER.match(f, w["b"]):
            continue  # a note's letter ^{(d)}; a number (70 for LXX); a book before its chapter:verse (Psal. for Psaumes)
        if len({i in marks[path] for i in range(w["a"], min(w["b"], len(f))) if f[i].isalnum()}) > 1:
            continue  # the text has both under one scan word already
        if re.match(re.escape(w["t"]) + "['’]", src):  # d'Achat: one slant for both pieces
            j = w["b"]
            while j < len(f) and f[j] in "'’_":
                j += 1
            if j < len(f) and (j in marks[path]) != (w["a"] in marks[path]):
                continue  # d'_Achat_: the text has the elided d roman, the name italic
        t = w["t"]
        if "'" in src or "’" in src:  # qu' il: the pieces of one word vote as that word, its letters (s'y leans as y)
            t = re.sub(r"\W", "", src)
            if len(t) < 4:
                continue  # n'a, s'en: the apostrophe's own slant outweighs so few letters
        sl = word_slant(o, w)
        if sl is None or ROMAN_AT < sl < ITALIC_AT or (len(t) < 3 and SHORT_ROMAN < sl < SHORT_ITALIC) or 5 * sum(c in LEANING for c in t) >= 2 * len(t):
            continue
        votes.append((i, sl >= ITALIC_AT, w["a"] in marks[path], sl))
    voters = {v[0] for v in votes}

    def widen(n, step, scan, js):
        """The stretch's edge moved over up to two words that did not vote (short, or not clear enough) but
        that the scan measures the stretch's way and the text has as the rest of it (La terre de Sual)."""
        path = res[n]["path"]
        for _ in range(2):
            m = n + step
            if not 0 <= m < len(res) or m in voters:
                break
            w = res[m]
            if w.get("path") != path or w["s"] == "skip" or (w["a"] in marks[path]) != js or across(w):
                break
            f = fields[path]
            if numeral(w["t"]) and not any(c.isalpha() for c in f[w["a"]:w["b"]]):
                break  # a number; not Il read II
            if f[max(0, w["a"] - 3):w["a"]].endswith("{(") or f[w["a"]:w["b"]].isdigit() or "^{" in f[min(w["a"], f.rfind(" ", 0, w["a"]) + 1):w["b"]]:
                break  # a note's mark ^{(f)}, a number: never taken in
            if step > 0 and "&" in "".join(o["lines"][li]["words"][wi]["t"] for li, wi in w["src"]):
                break  # an & after the stretch: it leans in roman too (Ciel & puis)
            sl = word_slant(o, w)  # an & before it, leaning its way, is taken in (& ce vestibule)
            if sl is None or not (sl >= ITALIC_AT if scan else sl <= ROMAN_AT):
                break
            n = m
        return n

    def lead_in(n):
        """A stretch to italics opening a sentence takes in a word of one or two letters just before it that
        the scan does not measure roman (A quoi peut-on, the A unmeasured; on _vit paraître_ at 8 degrees):
        too short to vote, and the stretch's first word as a rule. One measured roman stays out: mostly it is
        (Le _core_ contenait, Un _cœur mauvais_, 17. Et _on y voyait_). An & comes in by `widen`, leaning."""
        m = n - 1
        if m < 0:
            return n
        w, path = res[m], res[n]["path"]
        if w.get("path") != path or w["s"] == "skip" or w["a"] in marks[path] or across(w):
            return n
        f = fields[path]
        word = f[w["a"]:w["b"]]
        src = "".join(o["lines"][li]["words"][wi]["t"] for li, wi in w["src"])
        sl = word_slant(o, w)
        if "&" in src or not (word.isalpha() and len(word) <= 2) or (sl is not None and sl <= ROMAN_AT):
            return n
        before = f[:w["a"]].replace("_", "").rstrip()
        if NOTE_MARK.search(f, w["a"], res[n]["a"]) or "^{" in before[-6:]:
            return n
        if before and before[-1] not in ".:;?!)" :
            return n
        return m

    out, k = [], 0
    while k < len(votes):
        i, scan, js, _ = votes[k]
        if scan == js:
            k += 1
            continue
        m = k
        while m + 1 < len(votes) and votes[m + 1][1:3] == (scan, js) and res[votes[m + 1][0]]["path"] == res[i]["path"]:
            m += 1
        run = votes[k:m + 1]
        mean = sum(v[3] for v in run) / len(run)
        flank = [votes[n] for n in (k - 1, m + 1) if 0 <= n < len(votes) and res[votes[n][0]]["path"] == res[i]["path"] and votes[n][2] == js]
        t = res[i]["t"]
        w0 = res[i]
        before0 = fields[w0["path"]][:w0["a"]].replace("_", "").rstrip() if w0.get("path") else ""
        # a short name in the middle of a sentence, leaning clearly (engendra Sem, Cham; de Sur): not a ses, a Les or an en
        name = len(run) == 1 and t[:1].isupper() and mean >= 12 and bool(before0) and before0[-1] not in ".?!"
        lone = len(run) == 1 and scan and (mean < 14 or 5 * sum(c in LEANING for c in t) > len(t)  # leaning letters (voyage.)
                                           or (len(re.sub(r"\W", "", t)) <= 3 and not name))  # ses (ſ leans), Les, en, ô: 8 in 12 roman on the scan
        # montagne, sur le bord: a few words the scan measures roman with the text's own style (italic) round them
        ringed = not scan and len(run) <= 3 and flank and all(v[1] == js for v in flank) and (len(flank) == 2 or len(run) == 1)
        # one italic word, an "&", one italic word (Gad & Méni): each is a lone word's reading, the "&" never leans like the rest
        pair = (scan and mean < 17 and len(run) in (2, 3) and run[-1][0] - run[0][0] == 2
                and res[run[0][0] + 1]["t"].lower() in ("&", "et"))
        if lone or ringed or pair:
            k = m + 1
            continue
        if len(run) > 1 or mean >= 12 or mean <= 2:
            lo, hi = widen(run[0][0], -1, scan, js), widen(run[-1][0], 1, scan, js)
            if scan:
                lo = lead_in(lo)
            first, last = res[lo], res[hi]
            s = fields[first["path"]]
            a, b = first["a"], last["b"]
            m_el = ELIDED.search(s, 0, a) if a >= 2 and s[a - 1] in "'’" else None
            if m_el and all((i in marks[first["path"]]) == js for i in range(m_el.start(1), a - 1)):
                a = m_el.start(1)  # d'Achat: the elision with the word (_d'Achat_, the text's way)
            if scan:  # but a d' or l' opening the stretch before a name stays roman: d'_Achad_, l'_Égypte_
                m_nm = NAME_ELISION.match(s, a, b)
                if m_nm:
                    a = m_nm.end()
            pm = (TRAILING_PUNCT if scan else ROMAN_TRAILING).match(s, b)
            if pm and (scan or pm.end() - 1 in marks[first["path"]]):
                b = pm.end()
            # a note's mark inside the stretch stays out of the italics (the text's way: vestiges_^{(f)} _du pays_),
            # and so does a word that did not vote but the scan measures roman (Le conseil, ou le secret)
            gaps = [(mk.start(), mk.end()) for mk in NOTE_MARK.finditer(s, a, b)]
            if scan:
                for n in range(lo + 1, hi):
                    w = res[n]
                    if n not in voters and w.get("path") == first["path"] and w["s"] != "skip":
                        sl = word_slant(o, w)
                        if sl is not None and sl <= ROMAN_AT:
                            gaps.append((w["a"], w["b"]))
            segs, pos = [], a
            for ga, gb in sorted(gaps):
                if ga >= pos:
                    segs.append((pos, ga))
                    pos = gb
            segs.append((pos, b))
            t = s
            for sa, sb in reversed(segs):  # the last first: the offsets before it hold
                if any(c.isalnum() for c in s[sa:sb]):
                    t = (toggle_italics(t, sa, sb) or (t,))[0]
            if t != s:
                new = SPLIT_ELISION.sub(r"_\1\2", t)  # _d_'_Achat_: _d'Achat_
                out.append(dict(path=first["path"], a=a, b=b, to="italic" if scan else "roman",
                                words=[lo, hi], slant=round(mean), old=s[a:b],
                                before=s[max(0, a - 30):a], after=s[b:b + 30], new=new))
        k = m + 1
    out += bracket_italics(res, fields)
    return out


BRACKET_OPENS = re.compile(r"\[\s*$")  # an italic stretch that ends with the bracket: _Elle se couvrit, [_elle se déguisa
BRACKET_CLOSES = re.compile(r"[,;.:!?]*\]")  # one that opens with it: reconnue_,] et elle


def bracket_italics(res, fields):
    """A bracket (and the punctuation before a closing one) caught inside an italic stretch: the scan has the
    brackets roman, whatever their words are, so the marks are misplaced round them. One row for each, to roman."""
    from page_text import italic_runs, toggle_italics
    out = []
    for path, s in fields.items():
        if not isinstance(s, str) or path.rsplit("/", 1)[-1] not in ITALIC_CHECKED or "[" not in s and "]" not in s:
            continue
        at = [n for n, w in enumerate(res) if w.get("path") == path]
        if not at:
            continue
        for ra, rb in italic_runs(s)[0]:
            text = s[ra:rb]
            spans = []
            m = BRACKET_OPENS.search(text)
            if m and any(c.isalnum() for c in text[:m.start()]):
                spans.append((ra + m.start(), ra + m.start() + 1))
            m = BRACKET_CLOSES.match(text)
            if m and any(c.isalnum() for c in text[m.end():]):
                spans.append((ra, ra + m.end()))
            for a, b in spans:
                t = toggle_italics(s, a, b)
                if not t or t[0] == s:
                    continue
                n = max((n for n in at if res[n]["a"] <= a), default=at[0])
                out.append(dict(path=path, a=a, b=b, to="roman", words=[n, n], slant=0, old=s[a:b],
                                before=s[max(0, a - 30):a], after=s[b:b + 30], new=t[0]))
    return out


REF_ONLY = re.compile(r"\W*(?:\d\.?\s*)?[A-ZÉ][a-zé]+\.?(?:\s+(?:[IVXLC]+|\d+)[.,:]?)+\W*")
LEMMA = re.compile(r"\W*[\dIl]*\W*[A-ZÆŒ]{2,}[\s.,]+[A-ZÆŒ]{2,}")


def _fields(data):
    seen = set()
    for t in json_tokens(data):
        seen.add(t["path"])
    for path in seen:
        o = data
        for k in path.split("/"):
            o = o[int(k)] if isinstance(o, list) else o.get(k)
        yield path, o


def _raw(o, words):
    """The scan's text of these words, punctuation kept, a word cut at the line's end joined."""
    seen, parts = set(), []
    for w in words:
        for li, wi in w["src"]:
            if (li, wi) not in seen:
                seen.add((li, wi))
                parts.append(o["lines"][li]["words"][wi]["t"])
    text = ""
    for p in parts:
        text = text[:-1] + p if text.endswith(("¬", "-")) and text else (text + " " + p if text else p)
    return text


def _place(res, i, j, fields):
    """Where the run res[i..j] goes: after the linked word before it, else before the linked word after."""
    prev = next((w for w in reversed(res[:i]) if "path" in w), None)
    nxt = next((w for w in res[j + 1:] if "path" in w), None)
    if prev:
        path, pos = prev["path"], prev["b"]
        s = fields.get(path) or ""
        while pos < len(s) and s[pos] in ",.;:!?)»_}":  # the word's own punctuation stays with it
            pos += 1
    elif nxt:
        path, pos = nxt["path"], nxt["a"]
        s = fields.get(path) or ""
    else:
        return None
    if path.startswith("footnotes/"):
        return None
    return {"path": path, "pos": pos, "before": s[max(0, pos - 30):pos], "after": s[pos:pos + 30]}


def insert(s, pos, text):
    """`text` put into `s` at `pos`, one space each side where words meet."""
    left, right = s[:pos], s[pos:]
    if text.endswith(("'", "’")) and right.startswith(" "):  # l' | Assyrie: the elision joins the word after
        right = right[1:]
    if left and not left.endswith((" ", "\n")):
        text = " " + text
    if right and not right.startswith((" ", "\n")) and right[0] not in ",.;:!?)" and not text.endswith(("'", "’")):
        text = text + " "
    return left + text + right


CHUNK = 10  # pages a Kraken run: the model loads once, and an interrupted run loses little


def _fmt_duration(seconds):
    seconds = int(round(seconds))
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}h{m:02d}m{s:02d}s"
    elif m > 0:
        return f"{m}m{s:02d}s"
    else:
        return f"{s}s"


def main(argv):
    if not argv:
        sys.exit(__doc__)
    vol = argv[0]
    pages = sorted(int(p.stem.split("_")[1]) for p in (DATA / vol / "source_images" / "commentaire").glob("page_*.png"))
    if len(argv) > 1:
        a, _, b = argv[1].partition("-")
        pages = [p for p in pages if int(a) <= p <= int(b or a)]
    todo = [p for p in pages if not cache_path(vol, p).exists()]
    t0 = time.time()
    total_pages = len(pages)
    cached_count = total_pages - len(todo)
    total_todo = len(todo)
    now_str = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{now_str}] {vol}: {cached_count} pages cached, {total_todo} to OCR", flush=True)
    unslanted = [p for p in pages if p not in todo and f'"slant":{SLANT}' not in cache_path(vol, p).read_text(encoding="utf-8")[-20:]]
    for n in range(0, len(unslanted), 50):  # read before the slant was measured
        slants(vol, [(p, scan_path(vol, p)) for p in unslanted[n:n + 50]])
    if unslanted:
        print(f"  slant measured on {len(unslanted)} pages read before", flush=True)
    for n in range(0, total_todo, CHUNK):
        chunk = todo[n:n + CHUNK]
        chunk_t0 = time.time()
        try:
            kraken(vol, [(p, scan_path(vol, p)) for p in chunk])
        except subprocess.CalledProcessError as e:  # page by page, to find the one that fails
            print(f"  p.{chunk[0]}-{chunk[-1]}: Kraken failed, page by page: {e.stderr.decode(errors='replace')[-200:]}", flush=True)
            for p in chunk:
                try:
                    kraken(vol, [(p, scan_path(vol, p))])
                except subprocess.CalledProcessError:
                    print(f"  p.{p}: Kraken failed", flush=True)
        chunk_took = time.time() - chunk_t0
        done = min(n + CHUNK, total_todo)
        current_page_count = cached_count + done
        pct = (current_page_count / total_pages) * 100 if total_pages else 100.0
        now_time = datetime.datetime.now().strftime("%H:%M:%S")
        elapsed = time.time() - t0
        if done > 0 and done < total_todo:
            sec_per_item = elapsed / done
            remaining = sec_per_item * (total_todo - done)
            time_info = f"took {_fmt_duration(chunk_took)} ({_fmt_duration(elapsed)} elapsed, ~{_fmt_duration(remaining)} left)"
        else:
            time_info = f"took {_fmt_duration(chunk_took)} ({_fmt_duration(elapsed)} elapsed)"
        print(f"[{now_time}]   {current_page_count:3d}/{total_pages} ({pct:5.1f}%) (p.{chunk[-1]}) · {time_info}", flush=True)

    if total_todo:
        total_time = time.time() - t0
        sec_per_page = total_time / total_todo
        now_time = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[{now_time}] {vol}: {total_todo} pages OCR'd in {_fmt_duration(total_time)} ({sec_per_page:.1f}s/page)", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
