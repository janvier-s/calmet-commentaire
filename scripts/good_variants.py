"""Where the Good_Calmet edition (a later printing: cache/good_ocr, good_calmet_kraken.py) differs from the
normalized JSON, with the source scan's OCR (cache/ocr) as a third witness.

    python3 good_variants.py <vol> <chapter>[-<chapter>] [--out FILE]

Each Good word is set against the normalized pages near its matched source page (scan_ocr.align, fixed),
keeping the link that agrees with its line. The words no page holds make runs (a short matched word
between two unmatched ones does not cut a run), each anchored between the matched words on either side:
  insert            Good words where the JSON has none
  replace           Good words where the JSON has other words (old: the JSON's)
  only_normalized   JSON words (3+) no Good word is linked to, not part of a replace
  unclear           the anchors are out of order (a moved block, a page-break mix-up)
  moved             8+ words one text lacks here but holds elsewhere in the run (4-grams, half or more)
`origin`: only_good (the source scan agrees with the JSON: the edition differs), both_scans (the source
scan has the Good words too: the JSON dropped them), normalized_differs (neither scan has the JSON's words).
Each record names where to find it in Good_Calmet: `good`: [{pdf, pdf_page, printed, crop, boxes}]
(boxes in the crop's pixels). Footnotes are not compared (expanded in the JSON by design), nor the verses'
Latin column (the fixed alignment leaves its misreads out).
"""
import collections
import concurrent.futures
import hashlib
import json
import re
import sys
import unicodedata

from paths import DATA, SCRIPTS
import good_calmet_kraken as gk
import good_italics
import scan_ocr

RANK = {"ok": 3, "near": 2}
NOTE_OPEN = re.compile(r"[(\[{]\s*[a-z]\w?\)?|[a-z][)\]]")  # (a) (b) (ch a) b]: a note's first word
# the margin's and the lemmas' references, the verses' heading: Chap. III. v. 15, ŷ. 6, COMMENTAIRE (misread)
REF_WORD = re.compile(r"(?i)chap|[vyŷ]|[ivxlc]+|\d+|comment\w*|commentalre")
# the margin's chronology and the chapters' headings: "An. du M. 2315", "A. N. du Monde 1, avant J. C. 4000,
# avant l'Ere vulgaire 4004", "CHAPITRE XXXVII"
CHRONO = {"an", "ans", "ars", "au", "du", "m", "me", "monde", "avant", "j", "c", "l", "ere", "vulgaire",
          "chapitre", "chap", "commentaire", "n", "a"}
STRONG = {"an", "ans", "ars", "monde", "avant", "vulgaire", "chapitre", "chap", "commentaire"}
# the scan's short book names in references, against the text's full ones (others match by their start)
BOOK = {"reg": "rois", "paral": "chroniques", "esdr": "esdras", "pseaume": "psaume", "ps": "psaume",
        "psal": "psaume", "joan": "jean", "johan": "jean", "matth": "matthieu", "act": "actes", "apoc": "apocalypse",
        "apocal": "apocalypse", "eccli": "ecclesiastique", "eccl": "ecclesiaste", "cant": "cantique",
        "deut": "deuteronome", "num": "nombres", "levit": "levitique", "exod": "exode", "genes": "genese"}
ROMAN = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}


def number(t):
    """A word's value as a number, arabic or roman (IV, xxxiv), else None."""
    t = t.lower().strip(".")
    if t.isdigit():
        return int(t)
    if t and all(c in ROMAN for c in t):
        n = 0
        for a, b in zip(t, t[1:] + " "):
            n += -ROMAN[a] if b != " " and ROMAN[a] < ROMAN[b] else ROMAN[a]
        return n
    return None
SHORT = 3  # a matched word this short between unmatched ones is taken as a chance pairing


def norm(vol, p):
    f = DATA / vol / "normalized" / f"page_{p:04d}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def chapter_pages(vol, chs):
    out = []
    for f in sorted((DATA / vol / "normalized").glob("page_*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        got = {b.get("chapter") for sec in ("verses", "commentary") for b in d.get(sec) or []} | {d.get("chapter_number")}
        if got & chs:
            out.append(int(f.stem[5:]))
    return out


def _header_number(pdf, page):
    f = gk.cache_path(pdf, page)
    if not f.exists():
        return None
    o = json.loads(f.read_text(encoding="utf-8"))
    h = o["size"][1]
    nums = [w["t"].strip(".") for ln in o["lines"] if ln["box"][1] < 0.075 * h for w in ln["words"]]
    nums = [n for n in nums if n.isdigit() and len(n) <= 4]
    return int(nums[-1]) if nums else None


_printed = {}


def printed_page(pdf, page, reach=6):
    """The page's printed number: the offset (printed - the page's rank among the PDF's text pages, the
    plates and blanks between them unnumbered) most of its neighbours' headers give (a header misreads);
    None when fewer than 3 agree."""
    if pdf not in _printed:
        text = sorted(int(f.stem[5:]) for f in gk.cache_path(pdf, 1).parent.glob("page_*.json"))
        nums = [_header_number(pdf, q) for q in text]
        _printed[pdf] = {}
        for i, q in enumerate(text):
            offs = collections.Counter(nums[k] - k for k in range(max(0, i - reach), min(len(text), i + reach + 1))
                                       if nums[k] is not None)
            best = offs.most_common(1)
            _printed[pdf][q] = i + best[0][0] if best and best[0][1] >= 3 else None
    return _printed[pdf].get(page)


def in_order(stream, near=4):
    """Matches out of the JSON's order (the longest increasing run of JSON positions keeps the rest), or
    alone (no matched neighbour within `near` JSON words), made gaps: a new passage's common words paired
    with the same words elsewhere."""
    for sec in ("lat", "fr", "body"):
        _in_order(stream, [i for i, w in enumerate(stream) if w["s"] == "match" and section(w["path"]) == sec], near)


STRAY_MAX = 8  # matches: a longer run into another field is a real passage of it (a page's notes, a verse)


def strays(stream, near=4):
    """Matches into another field between two body matches on one Good page whose JSON words are neighbours
    (`near`), STRAY_MAX of them at most, made gaps: the JSON has nothing between those words, so Good's own
    passage there was paired, word by word, with a verse's or a note's same words (Genèse 1:1, "la Terre.
    Mais ces explications... la langue Hebraïque"). A run mostly linked is kept: a verse Good sets between two
    lines of the commentary ("Et du soir & du matin se fit le", 1:23), and so is one holding RUN_MIN matches
    in a row in the JSON's order: the French column Kraken read between the Latin's words, line by line
    ("Lors Dina fille de Lia", 34:1)."""
    body = [i for i, w in enumerate(stream) if w["s"] == "match" and section(w["path"]) == "body"]
    for a, b in zip(body, body[1:]):
        if stream[a].get("pdf_page") != stream[b].get("pdf_page") or not 0 < stream[b]["j"] - stream[a]["j"] <= near:
            continue
        other = [i for i in range(a + 1, b) if stream[i]["s"] == "match"]
        if 0 < len(other) <= STRAY_MAX and len(other) < 0.5 * (b - a - 1) and not _has_run(stream, other):
            for i in other:
                stream[i]["s"] = "gap"


RUN_MIN = 3


def _has_run(stream, idx):
    """RUN_MIN of the matches `idx` in a row: each a word or two after the last, its JSON word just after."""
    n = 1
    for p, q in zip(idx, idx[1:]):
        n = n + 1 if q - p <= 2 and 0 <= stream[q]["j"] - stream[p]["j"] <= 2 else 1
        if n >= RUN_MIN:
            return True
    return False


def section(path):
    """The stream a field is read in: the verses' Latin column, their French one, the rest of the text
    (headings and commentary); the scan and the JSON order each the same way, but not across them."""
    if path.startswith("verses/"):
        return "fr" if path.endswith("/french") else "lat"
    return "fn" if path.startswith("footnotes/") else "body"


def _in_order(stream, idx, near):
    tails, prev, tail_at = [], [None] * len(idx), []
    import bisect
    for n, i in enumerate(idx):
        j = stream[i]["j"]
        k = bisect.bisect_left(tails, j)
        if k == len(tails):
            tails.append(j); tail_at.append(n)
        else:
            tails[k] = j; tail_at[k] = n
        prev[n] = tail_at[k - 1] if k else None
    keep, n = set(), tail_at[-1] if tail_at else None
    while n is not None:
        keep.add(idx[n]); n = prev[n]
    for i in idx:
        if i not in keep:
            stream[i]["s"] = "gap"
    idx = [i for i in idx if i in keep]
    for n, i in enumerate(idx):
        j = stream[i]["j"]
        nb = [stream[idx[m]]["j"] for m in (n - 1, n + 1) if 0 <= m < len(idx)]
        if not any(abs(j - x) <= near for x in nb):
            stream[i]["s"] = "gap"


def margin_words(lines, size):
    """(line, word) indexes of the words in Good's margins (the chronology "Monde I. avant J.C. 4000", the
    references): a narrow line standing at or beyond the body column's right edge (or wholly left of its left
    edge), or a word of a body line set out past it ("tems Acos avant": Kraken runs the margin into the line).
    The column's edges are the median ends and the 20th-percentile starts of the lines half the page wide."""
    wide = [ln["box"] for ln in lines if ln["box"][2] >= 0.5 * size[0]]
    if len(wide) < 3:
        return set()
    right = sorted(b[0] + b[2] for b in wide)[len(wide) // 2]
    left = sorted(b[0] for b in wide)[len(wide) // 5]
    out = set()
    for li, ln in enumerate(lines):
        x, _, w, _ = ln["box"]
        narrow = w < 0.25 * size[0]
        for wi, wd in enumerate(ln["words"]):
            x0, x1 = wd["box"][0], wd["box"][0] + wd["box"][2]
            if narrow and (x >= right - 10 or x + w <= left + 4) or x0 > right + 4 or x1 < left - 4:
                out.add((li, wi))
    return out


def without_margin(o):
    """The page's OCR with its margin words left out (and the lines left empty), the cache untouched."""
    drop = margin_words(o["lines"], o["size"])
    lines = []
    for li, ln in enumerate(o["lines"]):
        ws = [w for wi, w in enumerate(ln["words"]) if (li, wi) not in drop]
        if ws:
            lines.append(dict(ln, words=ws) if len(ws) < len(ln["words"]) else ln)
    return dict(o, lines=lines)


def label(job):
    """One Good page's words, each linked (or not) to a JSON word: {t, k, wc, boxes, s, page?, path?, a?, b?}."""
    rec, cand = job
    go = without_margin(json.loads(gk.cache_path(rec["pdf"], rec["pdf_page"]).read_text(encoding="utf-8")))
    runs = {p: scan_ocr.align(go, d, fix=True)["words"] for p, d in cand}
    if not runs:
        return rec, None, []
    words = next(iter(runs.values()))
    cols = scan_ocr.split_columns(go)  # the lines align() read, which the words' `src` index
    # the page each line agrees with most
    votes = collections.defaultdict(collections.Counter)
    for p, ws in runs.items():
        for i, w in enumerate(ws):
            if w["s"] in RANK:
                votes[w["src"][0][0]][p] += 1
    out = []
    for i, w in enumerate(words):
        line = w["src"][0][0]
        order = [p for p, _ in votes[line].most_common()] + [p for p in runs if p not in votes[line]]
        best = next(((p, runs[p][i]) for p in order if runs[p][i]["s"] in RANK), None)
        r = {"t": w["t"], "pt": w.get("pt") or w["t"], "k": scan_ocr.key(w["t"]), "wc": w["wc"], "boxes": w["boxes"]}
        sl = scan_ocr.word_slant(cols, w)
        if sl is not None:
            r["sl"] = round(sl, 1)  # degrees: italic from ITALIC_AT
        li, wi = w["src"][0]
        if len(w["t"]) == 1 and re.search(r"[()]", cols["lines"][li]["words"][wi]["t"]):
            r["s"] = "skip"  # a note's mark: the later edition letters its notes otherwise
            out.append(r)
            continue
        if best:
            r.update(s="match", page=best[0], path=best[1]["path"], a=best[1]["a"], b=best[1]["b"],
                     near=best[1]["s"] == "near")
        else:
            # align()'s own skips (a band by the notes, the page's foot) would hide a changed passage: only
            # an unsure reading is left out here (the notes' block and the header are, below and before)
            r["s"] = "skip" if w["wc"] < 0.5 else "gap"
        out.append(r)
    # the footnotes' block (not compared): from the highest of the words linked to a footnote, in the
    # page's lower half, down
    h = go["size"][1]
    fy = sorted(r["boxes"][0][1] for r in out if r["s"] == "match" and r["path"].startswith("footnotes/")
                and r["boxes"][0][1] > 0.5 * h)
    linked = sorted((r["boxes"][0][1], r["path"].startswith("footnotes/")) for r in out if r["s"] == "match")
    top = next((y for y in fy if len([1 for yy, f in linked if yy >= y]) >= 3
                and sum(f for yy, f in linked if yy >= y) >= 0.8 * len([1 for yy, f in linked if yy >= y])), None)
    # or from the first line in the lower part that opens with a note's mark, "(a)"
    marked = [ln["box"][1] for ln in go["lines"] if ln["box"][1] > 0.6 * h and ln["words"]
              and NOTE_OPEN.match(ln["words"][0]["t"])]
    if marked:
        top = min(top, marked[0] + 5) if top is not None else min(marked) + 5
    if top is not None:
        top -= 5
        for r in out:
            if r["boxes"][0][1] >= top:
                r["s"] = "skip"
    return rec, None, out


def source_view(job):
    """The source scan's OCR of a page against its JSON: the JSON words it holds, its unmatched words' keys."""
    vol, p, d = job
    o = scan_ocr.ocr(vol, p, run=False)
    if o is None or d is None:
        return p, None, set(), {}
    res = scan_ocr.align(o, d, fix=True)
    held = {(w["path"], w["a"]) for w in res["words"] if w["s"] in RANK}
    loose = {scan_ocr.key(w["t"]) for w in res["words"] if w["s"] in ("missing", "diff")}
    exact = {(w["path"], w["a"]): None for w in res["words"] if w["s"] == "ok"}
    exact.update({(w["path"], w["a"]): w["t"] for w in res["words"] if w["s"] == "near"})
    return p, held, loose, exact  # exact: the JSON words the scan reads the same (None), or nearly (its reading)


def runs_of(stream):
    """Maximal runs of gap words; skip words neither cut nor join; a short matched word between gaps joins."""
    idx = [i for i, w in enumerate(stream) if w["s"] != "skip"]
    out, cur, pend = [], [], []
    for i in idx:
        w = stream[i]
        if w["s"] == "gap":
            cur += pend + [i]
            pend = []
        elif cur and len(w["t"]) <= SHORT and len(pend) < 2:
            pend.append(i)
        else:
            if cur:
                out.append((cur, pend[0] if pend else i))
            cur, pend = [], []
    if cur:
        out.append((cur, None))
    return out  # (gap word indexes, index of the matched word after or None)


def modern(text):
    return scan_ocr.modern(text)


def _punct(ws):
    """The Good words as modern text with their printed punctuation, and the marks to check (scan_ocr.printed)."""
    if not ws:
        return {"good_punct": None, "good_flags": []}
    r = scan_ocr.printed(ws)
    return {"good_punct": r["text"], "good_flags": r["flags"]}


def align(vol, chs, workers=8):
    """The chapters' alignment: the JSON's words (`jt`), the Good words in Good's order linked to them
    (`stream`), the pages, their JSON (`data`), the source scans' views (`src`, `src_ok`), the linked JSON words."""
    pages = chapter_pages(vol, chs)
    if not pages:
        sys.exit(f"{vol}: no page holds chapter(s) {sorted(chs)}")
    lo, hi = pages[0] - 2, pages[-1] + 2
    data = {p: norm(vol, p) for p in range(lo - 2, hi + 3)}
    data = {p: d for p, d in data.items() if d}
    recs = sorted((r for r in gk.crops() if r["vol"] == vol and r.get("source")
                   and pages[0] - 1 <= int(r["source"][5:]) <= pages[-1] + 1
                   and gk.cache_path(r["pdf"], r["pdf_page"]).exists()), key=lambda r: (r["pdf"], r["pdf_page"]))
    jobs = []
    for r in recs:
        s = int(r["source"][5:])
        jobs.append((r, [(p, data[p]) for p in range(s - 2, s + 3) if p in data]))
    with concurrent.futures.ProcessPoolExecutor(workers) as ex:
        labelled = list(ex.map(label, jobs))
        views = list(ex.map(source_view, [(vol, p, data.get(p)) for p in range(lo, hi + 1)]))
    src = {p: (h, l) for p, h, l, _ in views}
    src_ok = {p: e for p, _, _, e in views}

    # the JSON's words in order, and the Good words in order with where they come from
    jt, at = [], {}
    for p in range(lo, hi + 1):
        if p in data:
            for t in scan_ocr.json_tokens(data[p]):
                at[(p, t["path"], t["a"])] = len(jt)
                jt.append(dict(t, page=p))
    join_seams(jt, data)
    stream = []
    for rec, printed, ws in labelled:
        for w in ws:
            w.update(pdf=rec["pdf"], pdf_page=rec["pdf_page"], printed=printed_page(rec["pdf"], rec["pdf_page"]),
                     src_page=int(rec["source"][5:]))
            w["j"] = at.get((w.get("page"), w.get("path"), w.get("a"))) if w["s"] == "match" else None
            if w["s"] == "match" and w["j"] is None:
                w["s"] = "skip"  # linked to a page outside the stream
            stream.append(w)
    in_order(stream)
    strays(stream)
    for w in stream:
        if w["s"] == "gap":
            w["j"] = None
    relink_seams(stream, jt)
    linked = {w["j"] for w in stream if w["j"] is not None}
    for j, t in enumerate(jt):  # the JSON's note marks, ^{(a)}: left out as on the scan
        f = field_text(data[t["page"]], t["path"]) if t["page"] in data else None
        if f and len(t["t"]) == 1 and f[max(0, t["a"] - 1):t["a"]] == "(":
            linked.add(j)
    linked |= {j for j, t in enumerate(jt) if t.get("seamed")}
    return {"vol": vol, "pages": pages, "data": data, "jt": jt, "stream": stream, "labelled": labelled,
            "src": src, "src_ok": src_ok, "linked": linked}


def unclear_anchor(stream, gaps, after, jt, reach=8):
    """The JSON index an `unclear` Good-only run goes before. Its nearest matched neighbour can be a short
    phrase matched far off (Good's "le Ciel & la Terre" in a note, linked to the verse's), so the run goes to the
    field (page, path) most of its `reach` matched neighbours on each side hold: after the last of them before
    the run, else before the first after it."""
    before = [stream[i]["j"] for i in range(gaps[0] - 1, -1, -1) if stream[i]["s"] == "match"][:reach]
    nxt = [stream[i]["j"] for i in range(after, len(stream)) if stream[i]["s"] == "match"][:reach] \
        if after is not None else []
    field = lambda j: (jt[j]["page"], jt[j]["path"])
    votes = collections.Counter(field(j) for j in before + nxt)
    if not votes:
        return None
    best = votes.most_common(1)[0][0]
    j = next((j for j in before if field(j) == best), None)
    if j is not None:
        return j + 1
    return next(j for j in nxt if field(j) == best)


def variants(vol, chs, workers=8, ctx=None):
    ctx = ctx or align(vol, chs, workers)
    pages, data, jt, stream = ctx["pages"], ctx["data"], ctx["jt"], ctx["stream"]
    labelled, src, src_ok, linked = ctx["labelled"], ctx["src"], ctx["src_ok"], ctx["linked"]

    pieces, claimed = [], set()
    for gaps, after in runs_of(stream):
        before = next((stream[i] for i in range(gaps[0] - 1, -1, -1) if stream[i]["s"] == "match"), None)
        nxt = stream[after] if after is not None else None
        L, R = (before or {}).get("j"), (nxt or {}).get("j")
        if L is None and R is None:
            continue
        between = list(range(L + 1, R)) if L is not None and R is not None and L < R else []
        between = [j for j in between if j not in linked]
        if L is not None and R is not None and R <= L:
            kind, j0 = "unclear", L + 1
            j1 = j0
        elif between and R - L - 1 <= 3 * len(gaps) + 5:
            kind, j0, j1 = "replace", between[0], between[-1] + 1
        elif L is not None and R is not None and R - L - 1 > 50:
            kind, j0 = "unclear", unclear_anchor(stream, gaps, after, jt)  # anchors far apart: the words
            j1 = j0  # between are matched elsewhere
            between = []
        else:
            kind, between = "insert", []
            j0 = j1 = L + 1 if L is not None else R
        if kind == "replace" and len(gaps) <= 2 and scan_ocr.similar(
                " ".join(stream[i]["k"] for i in gaps), " ".join(jt[j]["k"] for j in between)) > 0.6:
            held = src_ok.get(jt[between[0]]["page"]) or {}
            if not held or any(held.get((jt[j]["path"], jt[j]["a"]), 1) is None for j in between):
                continue  # a misreading of the same words (unless the source scan reads otherwise too)
        claimed.update(between)
        pieces.append({"kind": kind, "j0": j0, "j1": j1, "g0": gaps[0], "g1": gaps[-1] + 1})

    # a word both scans read alike, nearly the JSON's but not it (once modernized): the JSON's own slip
    for i, w in enumerate(stream):
        if not w.get("near") or w["j"] is None:
            continue
        t = jt[w["j"]]
        sw = (src_ok.get(t["page"]) or {}).get((t["path"], t["a"]))
        lig = lambda x: x.replace("æ", "ae").replace("Æ", "Ae").replace("œ", "oe").replace("Œ", "Oe")
        if sw and scan_ocr.key(sw) == w["k"] and w["k"] in lexicon() \
                and scan_ocr.modern_key(lig(w["t"])) != scan_ocr.key(lig(t["t"])):  # (écheoir: old spelling)
            pieces.append({"kind": "replace", "j0": w["j"], "j1": w["j"] + 1, "g0": i, "g1": i + 1, "agree": True})

    # JSON words no Good word holds (in the chapter's pages, not footnotes)
    covered = {(r["page"]) for _, _, ws in labelled for r in ws if r.get("page")}
    run = []
    for j, t in enumerate(jt + [None]):
        lone = t is not None and j not in linked and j not in claimed and t["page"] in pages \
            and t["page"] in covered and not t["path"].startswith("footnotes/") and t["path"] != "book_end_marker"
        if lone and (not run or (run[-1] == j - 1 and jt[run[-1]]["path"] == t["path"])):
            run.append(j)
            continue
        if run:
            pieces.append({"kind": "only_normalized", "j0": run[0], "j1": run[-1] + 1, "g0": None, "g1": None})
        run = [j] if lone else []

    out = []
    for c in merge(pieces, linked):
        rec = record(c, vol, jt, stream, src, pages, linked)
        if rec:
            out.append(rec)
    out = [r for r in out if real(r, jt, stream, lexicon(vol))]
    # a passage of 8 words or more the other text holds elsewhere (beyond the pages near by): moved
    g4 = _grams([w["k"] for w in stream if w["s"] != "skip"])
    j4 = _grams([t["k"] for t in jt])
    for r in out:
        if r["kind"] == "only_normalized" and r["old_words"] >= 8:
            k = [scan_ocr.key(t) for t in scan_ocr.TOKEN.findall(r["old"])]
            if _share(k, g4) >= 0.5:
                r["kind"] = "moved"
        elif r["kind"] in ("insert", "unclear") and r["words"] >= 8:
            k = [scan_ocr.key(t) for t in scan_ocr.OCR_TOKEN.findall(r["good_raw"])]
            if _share(k, j4) >= 0.5:
                r["kind"] = "moved"
    for r in out:
        r.pop("_span", None)
        # low: a word or two read out of order, mostly a page's or column's edge (3 real in 20 on Genèse 3, 49)
        r["confidence"] = "low" if r["kind"] == "unclear" and r["words"] <= 2 else "high"
    out.sort(key=lambda r: (r["page"], r["path"], r["at"]))
    return out


def merge(pieces, linked, reach=2, g_reach=4):
    """Pieces next to each other (no more than `reach` JSON words, `g_reach` Good words apart) made one: a
    reworded passage comes out as some JSON words alone, some Good words alone, side by side."""
    keep = [p for p in pieces if p["kind"] == "unclear" or p.get("agree")]
    rest = sorted((p for p in pieces if p["kind"] != "unclear" and not p.get("agree")), key=lambda p: (p["j0"], p["j1"]))
    cur = None
    for p in rest:
        a, b = (cur["j0"], max(cur["j1"], p["j1"])) if cur else (0, 0)
        if cur is not None and p["j0"] - cur["j1"] <= reach and (
                p["g0"] is None or cur["g1"] is None or p["g0"] - cur["g1"] <= g_reach) \
                and sum(j not in linked for j in range(a, b)) >= 0.5 * (b - a):
            cur["j1"] = max(cur["j1"], p["j1"])
            if p["g0"] is not None:
                cur["g0"] = p["g0"] if cur["g0"] is None else min(cur["g0"], p["g0"])
                cur["g1"] = p["g1"] if cur["g1"] is None else max(cur["g1"], p["g1"])
            cur["n"] += 1
            continue
        if cur:
            keep.append(cur)
        cur = dict(p, n=1)
    if cur:
        keep.append(cur)
    return keep


def record(c, vol, jt, stream, src, pages, linked):
    """A merged piece as a candidate (None when out of the chapter, in the footnotes, or too slight)."""
    j0, j1 = c["j0"], c["j1"]
    ws = [w for w in stream[c["g0"]:c["g1"]] if w["s"] != "skip"] if c["g0"] is not None else []
    for i in range(len(ws) - 2, 0, -1):  # the margin's year heading, "An. du M." (Ars du M)
        if i + 1 < len(ws) and ws[i]["t"] == "du" and ws[i + 1]["t"][:1] == "M" and len(ws[i + 1]["t"]) <= 2 \
                and re.fullmatch(r"A\w{0,2}", ws[i - 1]["t"]):
            del ws[i - 1:i + 2]
    while ws and REF_WORD.fullmatch(ws[-1]["t"]):  # "… expressément. V. 9.": the next lemma's reference
        ws.pop()
    while ws and REF_WORD.fullmatch(ws[0]["t"]):
        ws.pop(0)
    olds = jt[j0:j1]
    if c["kind"] == "unclear":
        kind = "unclear"
    elif ws and olds:
        kind = "replace"
    elif ws:
        kind = "insert"
    else:
        kind = "only_normalized"
    anchor = olds[0] if olds else (jt[j0 - 1] if j0 > 0 else jt[j0]) if j0 < len(jt) or j0 > 0 else None
    if anchor is None or anchor["page"] not in pages or anchor["path"].startswith("footnotes/"):
        return None
    if kind == "only_normalized" and len(olds) < 3:
        return None
    if ws and not olds and not any(len(w["k"]) > 2 for w in ws):
        return None
    if not ws and c["g0"] is not None and not olds:
        return None
    if c["g0"] is not None and not ws and kind != "only_normalized":
        return None
    if ws and all(w["k"] in CHRONO or number(w["t"]) is not None for w in ws) and any(
            w["k"] in STRONG or number(w["t"]) is not None for w in ws):
        return None  # the margin's chronology, a chapter's heading
    if olds and ws and same_reference([t["t"] for t in olds], [w["t"] for w in ws]):
        return None  # a reference written otherwise (4 Reg. XIX. 37 for 4 Rois 19:37)
    on, gn = [number(t["t"]) for t in olds], [number(w["t"]) for w in ws]
    if olds and ws and on == gn and None not in on:
        return None  # a reference's numbers, written in figures in the JSON (4 for IV): the same numbers
    if anchor["path"].startswith("verses/") and anchor["path"].endswith(("/latin", "/annotations")):
        return None  # the verses' Latin column: not compared (its misreads outnumber its changes)
    if olds and len(ws) == 1 and len(ws[0]["k"]) <= 1 and ws[0]["t"] not in ("à", "a", "y", "ô", "o"):
        return None  # a lone letter for words (an italic misread)
    if all(len(t["k"]) <= 2 for t in olds) and all(len(w["k"]) <= 2 for w in ws):
        return None  # an elision or a letter (l' for I, s'): no word changed
    sp = anchor["page"]
    held, loose = src.get(sp, (None, set()))
    loose = loose | src.get(sp + 1, (None, set()))[1] | src.get(sp - 1, (None, set()))[1]
    lone = [t for j, t in zip(range(j0, j1), olds) if j not in linked]
    content = [w for w in ws if len(w["k"]) > 2]
    if c.get("agree"):
        origin = "both_scans"  # both scans read the Good word: the JSON's is a slip
    elif lone and held is not None and not any((t["path"], t["a"]) in held for t in lone):
        origin = "normalized_differs"
    elif not olds and content and sum(w["k"] in loose for w in content) >= max(2, 0.6 * len(content)):
        origin = "both_scans"
    else:
        origin = "only_good"
    where = collections.OrderedDict()
    for w in ws:
        g = where.setdefault((w["pdf"], w["pdf_page"]), {
            "pdf": w["pdf"], "pdf_page": w["pdf_page"], "printed": w["printed"],
            "crop": f"data/good_calmet/{w['pdf']}/page_{w['pdf_page']:04d}.png", "boxes": []})
        g["boxes"] += w["boxes"]
    raw = " ".join(w["t"] for w in ws)
    old = " ".join(t["t"] for t in olds)
    if olds:
        at = olds[0]["a"]
    else:
        at = jt[j0 - 1]["b"] if j0 > 0 and jt[j0 - 1] is anchor else anchor["a"]
    rec = {"kind": kind, "origin": origin, "vol": vol, "page": anchor["page"], "path": anchor["path"], "at": at,
           "old": old, "good_raw": raw, "good_modern": modern(raw) if raw else None,
           **_punct(ws),
           "words": len(ws), "old_words": len(olds), "pieces": c.get("n", 1),
           "before": " ".join(t["t"] for t in jt[max(0, j0 - 8):j0]), "after": " ".join(t["t"] for t in jt[j1:j1 + 8]),
           "good": list(where.values())}
    it = good_italics.runs(ws)
    if it:  # the words printed in italics, as _marks_ in the text Good's wording is taken as
        final = next((rec[k] for k in ("good_punct", "good_modern") if rec.get(k) is not None), raw)
        marked = good_italics.apply(final, raw, it)
        if marked != final:
            rec["good_italic"] = marked
    paths = list(dict.fromkeys(f"{t['page']}:{t['path']}" for t in olds))
    if len(paths) > 1:
        rec["spans"] = paths
    if ws and len(ws) <= 2 and not olds:
        # the same words just across the JSON's page turn (its notes between): a page's edge read twice
        body = [t["k"] for t in jt[max(0, j0 - 30):j0] if not t["path"].startswith("footnotes/")][-4:] + \
               [t["k"] for t in jt[j0:j0 + 30] if not t["path"].startswith("footnotes/")][:4]
        if all(w["k"] in body for w in ws):
            return None
    if ws and len(ws) <= 2:
        g0, g1 = stream.index(ws[0]), stream.index(ws[-1]) + 1
        near_j = {t["k"] for t in jt[max(0, j0 - 2):j1 + 2]}
        nb = [w["k"] for w in stream[max(0, g0 - 1):g0]] + [""], [w["k"] for w in stream[g1:g1 + 1]] + [""]
        mid = "".join(w["k"] for w in ws)
        lex = lexicon(vol)
        if any(k in near_j for k in (nb[0][0] + mid, mid + nb[1][0], nb[0][0] + mid + nb[1][0])) or any(
                len(t) >= 3 and t != mid and t not in lex and (mid.startswith(t) or mid.endswith(t)) for t in near_j) \
                or (mid not in lex and any(len(mid) >= 2 and t != mid and t.startswith(mid) for t in near_j)):
            rec["split"] = True  # a word cut at a line's end (ani|maux) or the JSON's at a page turn (Créa|teur)
    if ws:
        rec["wc_min"] = round(min(w["wc"] for w in ws), 3)
        g0, g1 = stream.index(ws[0]), stream.index(ws[-1]) + 1
        rec["good_before"] = " ".join(w["t"] for w in stream[max(0, g0 - 10):g0] if w["s"] != "skip")
        rec["good_after"] = " ".join(w["t"] for w in stream[g1:g1 + 10] if w["s"] != "skip")
    rec["id"] = hashlib.md5(json.dumps([vol, kind, rec["path"], [w["k"] for w in ws], old]).encode()).hexdigest()[:10]
    rec["_span"] = (j0, j1)
    if c.get("agree"):
        rec["agree"] = True
    return rec


def same_reference(old, new):
    """Whether two runs are the same references written otherwise: the same numbers in order, and each
    other word the same book (one name the start of the other, or a known short name) or "et"."""
    num = lambda ws: [n for n in map(number, ws) if n is not None]
    if not num(old) or num(old) != num(new):
        return False
    plain = lambda w: "".join(c for c in unicodedata.normalize("NFD", w.lower()) if c.isalpha())
    words = lambda ws: [plain(w) for w in ws if number(w) is None and plain(w) not in ("et", "")]
    a, b = words(old), words(new)
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        x, y = BOOK.get(x, x), BOOK.get(y, y)
        if not (x == y or (min(len(x), len(y)) >= 3 and (x.startswith(y) or y.startswith(x)))):
            return False
    return True


def field_text(d, path):
    x = d
    for part in path.split("/"):
        x = x[int(part)] if part.isdigit() else (x or {}).get(part)
        if x is None:
            return None
    return x if isinstance(x, str) else None


def join_seams(jt, data):
    """A word the JSON cuts at a page turn (préam- | bulle) made one token, kept at the first page; the
    second half is marked `seamed`."""
    last = {}
    for i, t in enumerate(jt):
        if not t["path"].startswith("footnotes/") and t["path"] != "book_end_marker":
            last[t["page"]] = i
    firsts = {}
    for i, t in enumerate(jt):
        if t["page"] not in firsts and t["a"] == 0 and not t["path"].startswith(("footnotes/", "verses/")):
            firsts[t["page"]] = i
    for p, i in last.items():
        k = firsts.get(p + 1)
        f = field_text(data[p], jt[i]["path"]) or ""
        if k is None or not f.rstrip().endswith("-") or not jt[k]["t"][:1].islower():
            continue
        jt[i] = dict(jt[i], t=jt[i]["t"] + jt[k]["t"], k=scan_ocr.key(jt[i]["t"] + jt[k]["t"]), seam=k)
        jt[k] = dict(jt[k], seamed=True)


def relink_seams(stream, jt, near=6):
    """A Good word left unmatched that is a joined seam word, between matches close to it, linked to it."""
    seams = {t["k"]: j for j, t in enumerate(jt) if "seam" in t}
    ms = [i for i, w in enumerate(stream) if w["s"] == "match"]
    for i, w in enumerate(stream):
        j = seams.get(w["k"]) if w["s"] == "gap" else None
        if j is None:
            continue
        nb = [stream[m]["j"] for m in ms if abs(m - i) <= 3]
        if any(abs(x - j) <= near for x in nb):
            w.update(s="match", j=j)


_lex = {}


LEXICON = SCRIPTS / "cache" / "good_variants_lexicon.json"


def lexicon(vol=None):
    """The keys of the words of the normalized text, all volumes, met 3 times or more (cached in LEXICON;
    delete it to remake)."""
    if "all" not in _lex:
        if LEXICON.exists():
            _lex["all"] = set(json.loads(LEXICON.read_text(encoding="utf-8")))
        else:
            n = collections.Counter(t["k"] for f in DATA.glob("*/normalized/page_*.json")
                                    for t in scan_ocr.json_tokens(json.loads(f.read_text(encoding="utf-8"))))
            _lex["all"] = {k for k, c in n.items() if c >= 3}  # a word cut at a page turn (roient) is rare
            LEXICON.write_text(json.dumps(sorted(_lex["all"]), ensure_ascii=False), encoding="utf-8")
    return _lex["all"]


def _grams(keys, n=4):
    return set(zip(*(keys[i:] for i in range(n))))


def _share(keys, grams, n=4):
    """The share of a run's word 4-grams found in `grams`."""
    g = list(zip(*(keys[i:] for i in range(n))))
    return sum(x in grams for x in g) / len(g) if g else 0


def _pairs(keys):
    return {(a, b) for a, b in zip(keys, keys[1:])}


def _held(keys, pool):
    """The share of a run's word pairs found in `pool` (word pairs)."""
    p = _pairs(keys)
    return len(p & pool) / len(p) if p else 0


def real(r, jt, stream, lex, reach=2):
    """A candidate is kept when its words are not found near by on the other side (a block read in another
    order, a page's edge, a pairing gone astray), a replace is not the same words misread, and a run of one
    or two words holds only real words (not a piece of a word cut at the line's end, a header's "Chap")."""
    if r.get("agree"):
        return True
    near = range(r["page"] - reach, r["page"] + reach + 1)
    old = [scan_ocr.key(t) for t in scan_ocr.TOKEN.findall(r.get("old") or "")]
    new = [scan_ocr.key(t) for t in scan_ocr.OCR_TOKEN.findall(r.get("good_raw") or "")]
    if r["kind"] == "only_normalized":
        pool = _pairs([w["k"] for w in stream if w["src_page"] in near])
        return _held(old, pool) < 0.5
    if r["kind"] == "replace" and scan_ocr.similar(" ".join(old), " ".join(new)) >= 0.75:
        return False
    if r["kind"] == "unclear" and len(new) <= 2 and any(k not in lex for k in new if len(k) > 1):
        return False  # a piece of a word cut at a column's or page's end, a header, read out of order
    if len(new) <= 2 and r.get("split"):
        return False
    if len(new) <= 2 and any(k not in lex and (r.get("wc_min", 1) < 0.8 or r["kind"] == "replace") for k in new if len(k) > 1):
        return False  # a misreading (fodueut for fondant), or an unsure reading
    if len(new) >= 3 and sum(k in lex for k in new if len(k) > 2) < 0.5 * max(1, sum(len(k) > 2 for k in new)):
        return False  # mostly not words: a note's or a margin's text read into the body
    if len(new) >= 3:
        a, b = r.get("_span", (0, 0))
        pool = _pairs([t["k"] for j, t in enumerate(jt) if t["page"] in near and not a <= j < b])
        return _held(new, pool) < 0.5
    return True


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)
    vol, spec = argv[0], argv[1]
    a, _, b = spec.partition("-")
    chs = set(range(int(a), int(b or a) + 1))
    res = variants(vol, chs)
    if "--out" in argv:
        f = argv[argv.index("--out") + 1]
        with open(f, "w", encoding="utf-8") as fh:
            json.dump(res, fh, ensure_ascii=False, indent=1)
    print(f"{vol} ch. {spec}: {len(res)} candidates  " + str(dict(collections.Counter((r['kind'], r['origin']) for r in res))))
    for r in res:
        g = r.get("good") or []
        loc = "; ".join(f"{x['pdf']} p.{x['pdf_page']} (printed {x['printed']})" for x in g)
        print(f"\n[{r['id']}] {r['kind']}/{r['origin']}  page {r['page']} {r['path']}@{r['at']}  {r['words']} w  {loc}")
        if r.get("before") is not None:
            print(f"   …{r['before']} ‖ {r['after']}…")
        if r.get("old"):
            print(f"   JSON: {r['old'][:300]}")
        if r.get("good_raw"):
            print(f"   GOOD: {r['good_raw'][:300]}")


if __name__ == "__main__":
    main(sys.argv[1:])
