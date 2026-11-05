"""The footnotes of the Good_Calmet edition (cache/good_ocr) set against the normalized JSON's.

    python3 good_notes.py <vol> <chapter>[-<chapter>] [--out FILE] [--hg FILE]
    python3 good_notes.py --page <pdf> <pdf_page>      the notes read on one Good page (a check)

The JSON writes its references out ("Saint Augustin, De la Genèse à la lettre, livre 11, chapitre 39"),
the scans abbreviate them ("S. Aug. de Genes. ad litt. l. XI. c. 39."): notes are compared by their
numbers (arabic or roman, in order) and by their words of four letters or more, not word by word.

Each Good page's note block (from the first line in its lower part that opens with a note's mark, in
two columns, left then right; the catchword and the signature left out) is cut into notes at the marks.
The notes of a chapter, Good's and the JSON's, each in page order, are paired by a monotone alignment
on their likeness. Kinds:
  note_added      a Good note no JSON note pairs with
  note_dropped    a JSON note no Good note pairs with
  refs_changed    a pair whose numbers differ (a reference changed)
  text_changed    a pair of prose notes (8+ long words each) sharing under half their long words
  script_changed  a pair where one note has Hebrew or Greek and the other has none
Hebrew and Greek: Kraken reads Latin letters only, so on Good they come out as non-words. Every JSON
note with Hebrew or Greek, when paired, gives the Good note's boxes (--hg FILE): where a Hebrew or Greek
reading of the cleaner Good scan should look.
"""
import collections
import difflib
import hashlib
import json
import re
import sys
import unicodedata

from paths import DATA
import good_calmet_kraken as gk
import bible_refs
import good_variants as gv
import good_notes_read as gr
import scan_ocr

MARK = re.compile(r"[(\[{C]\s*[a-zA-Z]{1,2}\s*[)\]}]?|[a-z][)\]]|\d\d?\)")  # (a) (b) Ce) (ch b] 66): a note's mark
HEBREW = re.compile(r"[֐-׿]")
GREEK = re.compile(r"[Ͱ-Ͽἀ-῿]")
SIGNATURE = re.compile(r"[A-Z]{1,3}\.?\s*[ijv]{1,4}\.?|[A-Z]\s*\d")  # the gathering's signature: M.iij


def plain(t):
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if c.isalnum())


def page_notes(pdf, page, o=None):
    """A Good page's notes in reading order: [{mark, words: [{t, box}], col}]; [] when it has none.
    `o`: another page's OCR (the source scan's) read the same way."""
    if o is None:
        o = json.loads(gk.cache_path(pdf, page).read_text(encoding="utf-8"))
    w, h = o["size"]
    lines = [ln for ln in o["lines"] if ln["words"]]
    top = next((ln["box"][1] for ln in sorted(lines, key=lambda l: l["box"][1])
                if ln["box"][1] > 0.6 * h and MARK.fullmatch(ln["words"][0]["t"].strip(".,"))), None)
    if top is None:
        return []
    block = [ln for ln in lines if ln["box"][1] >= top - 5]
    last_y = max(ln["box"][1] for ln in block)
    keep = []
    for ln in block:
        text = " ".join(x["t"] for x in ln["words"])
        if ln["box"][1] >= last_y - 5 and len(ln["words"]) == 1 and ln["box"][0] > 0.55 * w:
            continue  # the catchword
        if SIGNATURE.fullmatch(text.strip()):
            continue
        keep.append(ln)
    mid = w / 2 - 20
    cols = [sorted((ln for ln in keep if (ln["box"][0] >= mid) == right), key=lambda l: l["box"][1]) for right in (False, True)]
    notes = []
    for ci, col in enumerate(cols):
        for ln in col:
            for wi, x in enumerate(ln["words"]):
                if (wi == 0 or re.fullmatch(r"[(t]?[(\[][a-zA-Z0-9][)\]]|t?e\)", x["t"])) and MARK.fullmatch(x["t"].strip(".,")) \
                        or (wi > 0 and re.fullmatch(r"\(\d\)", x["t"])):  # (3) (8): a mark misread, mid-line
                    notes.append({"mark": x["t"], "words": [], "col": ci, "page": page, "pdf": pdf})
                elif notes:
                    notes[-1]["words"].append({"t": x["t"], "box": x["box"]})
    for n in notes:  # a word cut at a line's end joined to the next (Ja¬ cob)
        ws, out = n["words"], []
        for x in ws:
            if out and out[-1]["t"].endswith(("¬", "-")) and not out[-1].get("joined"):
                out[-1] = {"t": out[-1]["t"].rstrip("¬-") + x["t"], "box": out[-1]["box"], "joined": True,
                           "boxes": [out[-1]["box"], x["box"]]}
            else:
                out.append(x)
        n["words"] = out
        n["text"] = " ".join(x["t"] for x in out)
    return notes


def mark_key(m):
    """A mark's letter or number, lower case: (a) a) ca) [b] -> a, b; Kraken's c( or t( prefix dropped."""
    t = re.sub(r"[^\w]", "", m or "").lower()
    return t[-1:] if len(t) == 2 and t[0] in "ct" and t[1].isalpha() else t


def agy_notes(pdf, page, o=None):
    """A Good page's notes as Flash read them (good_notes_read.py's cache), each given the boxes of the
    Kraken note with its mark (in order), else the crop's whole block; None when the page is not read."""
    d = gr.cached(pdf, page)
    if d is None:
        return None
    o = o or gr.kraken_ocr(pdf, page)
    ks = page_notes(pdf, page, o) if o else []
    used, out = set(), []
    w = h = None
    for i, a in enumerate(d["notes"]):
        k = next((j for j, kn in enumerate(ks) if j not in used and mark_key(kn["mark"]) == mark_key(a["mark"])), None)
        if k is None and len(ks) == len(d["notes"]) and i not in used:
            k = i  # same count, marks misread: by order
        if k is not None:
            used.add(k)
            words, col, from_ = ks[k]["words"], ks[k]["col"], "kraken"
        else:
            if w is None:
                w, h = o["size"] if o else (0, 0)
            words, col, from_ = [{"t": "", "box": [0, d["top"], w, h - d["top"]]}], None, "block"
        out.append({"mark": f"({a['mark']})", "text": a["text"], "words": words, "col": col, "page": page, "pdf": pdf,
                    "agy": True, "box_from": from_})
    return out


AFTER_ABBR = re.compile(r"(?:^|[\s(])(?:l|lib|liv|livre|c|cap|ser|serm|hom|homil|tom|t|quæst|quaest|q|part|n|num|v|vers|p|pag|"
                        r"dist|epist|ep|tract|sect|art|cant|psal|ps|et|&)\.?,?\s*$", re.I)  # where a lowercase roman number may stand


def numbers(text):
    """The numbers in order, arabic or roman; a roman number misread with 1 for I (111, 1v, x1) set right."""
    toks = []
    for m in re.finditer(r"[^\W_]+", text):
        t = m.group()
        if not re.fullmatch(r"[0-9IVXLCivxlc]+", t):
            continue
        if not re.search(r"\d", t) and not t.isupper() and not AFTER_ABBR.search(text[:m.start()]):
            continue  # a lowercase roman number only after an abbreviation (lib. v., l. xi): not "ci", "vi"
        if t == "111":
            t = "I" * len(t)  # l. 111. : III
        elif re.search(r"\d", t) and re.fullmatch(r"[\dIil]+", t) and sum(c.isdigit() for c in t) >= len(t) / 2:
            t = re.sub(r"[Iil]", "1", t)  # I7, 1I44: an arabic number, its 1 read as I
        elif re.search(r"\d", t) and re.search(r"[IVXLCivxlc]", t):
            t = t.replace("1", "I")  # 1v, x1: a roman one, its I read as 1
        toks.append(t)
    out = []
    for t in toks:
        n = gv.number(t)
        if n is not None:
            out.append(n)
    return out


def long_words(text, lex=None):
    """Its words of four letters or more, spelling-blind, in Latin letters (on Good: real words only)."""
    ks = [scan_ocr.key(t) for t in scan_ocr.TOKEN.findall(text) if not (HEBREW.search(t) or GREEK.search(t))]
    return {k for k in ks if len(k) >= 4 and (lex is None or k in lex)}


def script(text):
    return {"hebrew": bool(HEBREW.search(text)), "greek": bool(GREEK.search(text))}


STOP = {"dans", "sur", "les", "des", "une", "par", "pour", "avec", "contre", "contra", "voyez", "vid", "lib",
        "livre", "liv", "chapitre", "cap", "page", "pag", "verset", "vers", "saint", "sanct", "apud", "idem", "ibid"}


def readings(text):
    """Each number of a Good note with the values a misreading may hide: 11 or I1 for II, X1 for XI, l for 1."""
    out = []
    for m in re.finditer(r"[^\W_]+", text):
        t = m.group()
        if not re.fullmatch(r"[0-9IVXLCivxlc]+", t):
            continue
        if not re.search(r"\d", t) and not t.isupper() and not AFTER_ABBR.search(text[:m.start()]):
            continue
        vals = set()
        for u in {t, t.replace("1", "I"), re.sub(r"[Iil]", "1", t)}:
            n = gv.number(u)
            if n is not None:
                vals.add(n)
        if vals:
            out.append(vals)
    return out


def same_numbers(good_text, json_nums):
    """Whether the JSON's numbers are, in order, among the Good note's readings (extra Good numbers, an
    edition's year, allowed)."""
    rs = readings(good_text) if isinstance(good_text, str) else good_text  # [{n}] lists: read exactly
    i = 0
    for n in json_nums:
        while i < len(rs) and n not in rs[i]:
            i += 1
        if i == len(rs):
            return False
        i += 1
    return True


def covered(rs, nums):
    """Whether every one of a note's readings (in order) is one of these numbers: Good adds none."""
    i = 0
    for r in rs:
        while i < len(nums) and nums[i] not in r:
            i += 1
        if i == len(nums):
            return False
        i += 1
    return True


ALIAS = {"hieron": "jerome", "hieronym": "jerome", "hieronymus": "jerome", "quaest": "questions", "quæst": "questions",
         "quaestiones": "questions", "hebr": "hebraiques", "targ": "targum", "aqu": "aquila", "sym": "symmaque",
         "symm": "symmaque", "theod": "theodotion", "chald": "chaldeen", "syr": "syriaque", "vulg": "vulgate"}


def abbr_words(text, lex=None):
    """Its words in Latin letters, unaccented, three letters or more, not the commonest (to match by start)."""
    ws = [plain(t) for t in re.findall(r"[^\W\d_]+", text) if not (HEBREW.search(t) or GREEK.search(t))]
    ws = [ALIAS.get(w, w) for w in ws if len(w) >= 3 and w not in STOP]
    try:  # a Bible reference's book, whatever its spelling (Judic., Juges): its canonical name
        ws += [plain(r.book) for r in bible_refs.find_refs(text)]
    except Exception:
        pass
    if re.search(r"(?:^|[\s(])70\s*\.", text):
        ws.append("septante")  # the Septuagint, as the scans cite it
    return ws


def _abbr_share(gw, jw):
    """The share of the shorter list's words the other holds, one word the start of the other (Fag. for
    Fagius, Hesiod. for Hésiode)."""
    if not gw or not jw:
        return None
    short, long_ = (gw, jw) if len(gw) <= len(jw) else (jw, gw)
    def same(x, y):  # one the start of the other, or a long start in common (Celsum, Celse)
        n = next((i for i, (a, b) in enumerate(zip(x, y)) if a != b), min(len(x), len(y)))
        return (x == y or (min(len(x), len(y)) >= 3 and n == min(len(x), len(y))) or n >= 4
                or (min(len(x), len(y)) >= 5 and difflib.SequenceMatcher(None, x, y).ratio() >= 0.8))  # Capell., Cappel.
    hit = sum(any(same(x, y) for y in long_) for x in short)
    return hit / len(short)


def junk_share(g, lex):
    if g.get("agy"):
        return 0.0  # Flash writes Hebrew and Greek in their letters: no junk to read them by
    ws = [x["t"] for x in g["words"] if plain(x["t"])]
    if not ws:
        return 0.0
    bad = sum(1 for t in ws if (GREEK.search(t) or (scan_ocr.key(t) not in lex and gv.number(t.strip(".,")) is None)))
    return bad / len(ws)


def likeness(g, j):
    """0..1: how far a Good note and a JSON note are the same note: their numbers (the references), their
    words matched by their start (the scans abbreviate), a Hebrew or Greek note against a note of
    non-words (Kraken reads Latin letters only), and the same mark on the same page."""
    gn, jn = g["nums"], j["nums"]
    num = 2 * len(collections.Counter(gn) & collections.Counter(jn)) / (len(gn) + len(jn)) if gn and jn else None
    wd = _abbr_share(g["aw"], j["aw"])
    if num is not None:
        score = 0.6 * num + 0.4 * (wd or 0)
    elif wd is not None:
        score = wd * (0.8 if (gn or jn) else 1.0)
    else:
        score = 0.0
    if g.get("agy"):
        gs, js = g["script"], j["script"]
        if (gs["hebrew"] and js["hebrew"]) or (gs["greek"] and js["greek"]):
            score = max(score, 0.5 if not j["aw"] else score + 0.2)
    elif (j["script"]["hebrew"] or j["script"]["greek"]) and g["junk"] >= 0.4:
        score = max(score, 0.5 if not j["aw"] else score + 0.2)
    if mark_key(g["mark"]) == mark_key(j["mark"]) and g["src_page"] == j["page"]:
        score += 0.15
    return min(score, 1.0)


def joined(a, b, good):
    """Two consecutive notes as one (a note Good merged, or split)."""
    text = a["text"] + " " + b["text"]
    out = dict(a, text=text, nums=a["nums"] + b["nums"], aw=a["aw"] + b["aw"], parts=[a, b], script=script(text))
    if "lw" in a and "lw" in b:
        out["lw"] = a["lw"] | b["lw"]
    if good:
        out["words"] = a["words"] + b["words"]
        out["junk"] = (a.get("junk", 0) + b.get("junk", 0)) / 2
    return out


def pair(goods, jsons, least=0.34, part=0.4):
    """The monotone alignment of the two lists most alike in all: [(g, j, likeness)], g and j an index,
    None, or a pair of consecutive indices (a Good note that holds two JSON notes, or two Good notes one
    JSON note: allowed when the two as one are liker than either alone, each alike in part)."""
    n, m = len(goods), len(jsons)
    sim = [[likeness(g, j) for j in jsons] for g in goods]
    best = [[0.0] * (m + 1) for _ in range(n + 1)]
    move = [[None] * (m + 1) for _ in range(n + 1)]
    merged = {}
    for i in range(n + 1):
        for k in range(m + 1):
            if i == 0 and k == 0:
                continue
            opts = []
            if i and k and sim[i - 1][k - 1] >= least:
                opts.append((best[i - 1][k - 1] + sim[i - 1][k - 1], "pair"))
            if i and k >= 2 and sim[i - 1][k - 1] >= part and sim[i - 1][k - 2] >= part:
                s2 = likeness(goods[i - 1], joined(jsons[k - 2], jsons[k - 1], False))
                if s2 >= least and s2 > max(sim[i - 1][k - 1], sim[i - 1][k - 2]) + 0.15:
                    merged[(i, k, "jj")] = s2
                    opts.append((best[i - 1][k - 2] + 1.5 * s2, "jj"))
            if i >= 2 and k and sim[i - 1][k - 1] >= part and sim[i - 2][k - 1] >= part:
                s2 = likeness(joined(goods[i - 2], goods[i - 1], True), jsons[k - 1])
                if s2 >= least and s2 > max(sim[i - 1][k - 1], sim[i - 2][k - 1]) + 0.15:
                    merged[(i, k, "gg")] = s2
                    opts.append((best[i - 2][k - 1] + 1.5 * s2, "gg"))
            if i:
                opts.append((best[i - 1][k], "good"))
            if k:
                opts.append((best[i][k - 1], "json"))
            best[i][k], move[i][k] = max(opts)
    out, i, k = [], n, m
    while i or k:
        mv = move[i][k]
        if mv == "pair":
            out.append((i - 1, k - 1, sim[i - 1][k - 1])); i -= 1; k -= 1
        elif mv == "jj":
            out.append((i - 1, (k - 2, k - 1), merged[(i, k, "jj")])); i -= 1; k -= 2
        elif mv == "gg":
            out.append(((i - 2, i - 1), k - 1, merged[(i, k, "gg")])); i -= 2; k -= 1
        elif mv == "good":
            out.append((i - 1, None, None)); i -= 1
        else:
            out.append((None, k - 1, None)); k -= 1
    return out[::-1], sim


def pick(xs, ix, good):
    if ix is None:
        return None
    if isinstance(ix, tuple):
        return joined(xs[ix[0]], xs[ix[1]], good)
    return xs[ix]


def json_notes(vol, pages):
    out = []
    for p in pages:
        d = gv.norm(vol, p)
        for i, fn in enumerate((d or {}).get("footnotes") or []):
            text = fn.get("text") or ""
            out.append({"page": p, "index": i, "path": f"footnotes/{i}/text", "mark": fn.get("marker"), "text": text,
                        "nums": numbers(text), "lw": long_words(text), "aw": abbr_words(text), "script": script(text)})
    return out


def compare(vol, chs):
    pages = gv.chapter_pages(vol, chs)
    lex = gv.lexicon()
    recs = sorted((r for r in gk.crops() if r["vol"] == vol and r.get("source")
                   and pages[0] <= int(r["source"][5:]) <= pages[-1]
                   and gk.cache_path(r["pdf"], r["pdf_page"]).exists()), key=lambda r: (r["pdf"], r["pdf_page"]))
    goods = []
    read = 0
    for r in recs:
        ns = agy_notes(r["pdf"], r["pdf_page"])
        read += ns is not None
        for n in ns if ns is not None else page_notes(r["pdf"], r["pdf_page"]):
            n.update(src_page=int(r["source"][5:]), nums=numbers(n["text"]), lw=long_words(n["text"], lex),
                     aw=abbr_words(n["text"]), printed=gv.printed_page(r["pdf"], r["pdf_page"]), script=script(n["text"]))
            n["junk"] = junk_share(n, lex)
            goods.append(n)
    jsons = json_notes(vol, pages)
    # the source scan's notes, page by page, paired with the JSON's of that page: the third witness
    for p in pages:
        o = scan_ocr.ocr(vol, p, run=False)
        js = [j for j in jsons if j["page"] == p]
        if o is None or not js:
            continue
        ss = agy_notes(gr.src(vol), p, o)
        if ss is None:
            ss = page_notes(vol, p, o)
        for n in ss:
            n.update(src_page=p, nums=numbers(n["text"]), aw=abbr_words(n["text"]))
            n["junk"] = junk_share(n, lex)
        sp, ssim = pair(ss, js)
        for si, ji, _ in sp:
            if isinstance(ji, tuple) or isinstance(si, tuple):
                continue
            if si is not None and ji is not None:
                js[ji]["source_text"] = ss[si]["text"]
    print(f"  {read}/{len(recs)} Good pages read by Flash, the rest by Kraken", file=sys.stderr)
    pairs, sim = pair(goods, jsons)
    out, hg = [], []

    def where(g):
        return {"pdf": g["pdf"], "pdf_page": g["page"], "printed": g["printed"],
                "crop": f"data/good_calmet/{g['pdf']}/page_{g['page']:04d}.png",
                "boxes": [b for x in g["words"] for b in x.get("boxes", [x["box"]])],
                "reader": "flash" if g.get("agy") else "kraken", "box_from": g.get("box_from", "kraken")}

    def rec(kind, g=None, j=None, **kw):
        r = {"kind": kind, "vol": vol, "page": j["page"] if j else g["src_page"],
             "path": j["path"] if j else None, "json_mark": j["mark"] if j else None,
             "json_text": j["text"] if j else None, "good_mark": g["mark"] if g else None,
             "good_raw": g["text"] if g else None, "good": [where(g)] if g else [], **kw}
        r["id"] = hashlib.md5(json.dumps([vol, kind, r["page"], r["json_text"], r["good_raw"]]).encode()).hexdigest()[:10]
        out.append(r)

    for gi, ji, s in pairs:
        g, j = pick(goods, gi, True), pick(jsons, ji, False)
        if isinstance(gi, tuple) or isinstance(ji, tuple):
            rec("note_split" if isinstance(gi, tuple) else "notes_merged", g, j, likeness=round(s, 2),
                json_parts=[x["text"] for x in j.get("parts", [j])], good_parts=[x["text"] for x in g.get("parts", [g])])
        if j and (j["script"]["hebrew"] or j["script"]["greek"]) and g:
            hg.append({"vol": vol, "page": j["page"], "path": j["path"], "json_text": j["text"],
                       "script": [s for s, v in j["script"].items() if v], "good_raw": g["text"], **where(g)})
        if g and not j:
            if len(g["text"]) >= 3:
                rec("note_added", g)
        elif j and not g:
            rec("note_dropped", j=j)
        else:
            gr_ = readings(g["text"])  # Flash, like Kraken, reads II as 11: an I/1 swap is no difference
            if (g["nums"] or j["nums"]) and (not same_numbers(gr_, j["nums"])
                                             or (g.get("agy") and not covered(gr_, j["nums"]))):
                st = j.get("source_text")
                if st is None:
                    origin = "no_source"
                elif same_numbers(st, j["nums"]):
                    origin = "only_good"  # the source scan reads the JSON's numbers: the edition (or a misreading on Good)
                elif same_numbers(st, numbers(g["text"])) or same_numbers(g["text"], numbers(st)):
                    origin = "both_scans"  # both scans read alike, the JSON otherwise: the JSON's slip
                else:
                    origin = "unsure"
                rel = "good_extra" if same_numbers(gr_, j["nums"]) else "differ"  # Good adds numbers / they differ
                rec("refs_changed", g, j, likeness=round(s, 2), json_nums=j["nums"], good_nums=g["nums"],
                    origin=origin, source_raw=st, numbers=rel)
            elif len(j["lw"]) >= 8 and len(g["lw"]) >= 8 and len(g["lw"] & j["lw"]) < 0.5 * min(len(g["lw"]), len(j["lw"])):
                rec("text_changed", g, j, likeness=round(s, 2))
            if g.get("agy"):
                gs, js = g["script"], j["script"]
                if gs != js:
                    rec("script_changed", g, j, good_script=[k for k, v in gs.items() if v],
                        json_script=[k for k, v in js.items() if v])
                continue
            junk = sum(1 for x in g["words"] if plain(x["t"]) and scan_ocr.key(x["t"]) not in lex
                       and gv.number(x["t"].strip(".,")) is None and len(plain(x["t"])) >= 3)
            if not (j["script"]["hebrew"] or j["script"]["greek"]) and junk >= 3 and junk >= 0.4 * len(g["words"]):
                rec("script_changed", g, j, note="Good has a run of non-words (Hebrew or Greek?), the JSON none")
    return out, hg


def main(argv):
    if not argv:
        sys.exit(__doc__)
    if argv[0] == "--page":
        for n in page_notes(argv[1], int(argv[2])):
            print(f"{n['mark']:>5} [col {n['col']}] {n['text']}")
        return
    vol, spec = argv[0], argv[1]
    a, _, b = spec.partition("-")
    chs = set(range(int(a), int(b or a) + 1))
    out, hg = compare(vol, chs)
    if "--read-sources" in argv:  # the source scan's notes read by Flash too, where a difference was found
        import asyncio
        want = sorted({r["page"] for r in out if r["kind"] in ("refs_changed", "text_changed", "note_added", "note_dropped")
                       and not gr.cached(gr.src(vol), r["page"])})
        print(f"  reading {len(want)} source pages with Flash", file=sys.stderr)
        asyncio.run(gr.run([(gr.src(vol), p) for p in want], 6, 4, False))
        out, hg = compare(vol, chs)
    for flag, data in (("--out", out), ("--hg", hg)):
        if flag in argv:
            with open(argv[argv.index(flag) + 1], "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=1)
    print(f"{vol} ch. {spec}: {len(out)} note differences {dict(collections.Counter(r['kind'] for r in out))}; "
          f"{len(hg)} Hebrew/Greek notes located on Good")
    for r in out:
        g = r["good"][0] if r["good"] else {}
        print(f"\n[{r['id']}] {r['kind']} p{r['page']} {r.get('json_mark') or ''}  Good {g.get('pdf', '')} p.{g.get('pdf_page', '')} (printed {g.get('printed', '')})")
        if r["json_text"]:
            print(f"   JSON: {r['json_text'][:200]}")
        if r["good_raw"]:
            print(f"   GOOD: {r['good_mark']} {r['good_raw'][:200]}")


if __name__ == "__main__":
    main(sys.argv[1:])
