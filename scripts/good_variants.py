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

from paths import DATA, SCRIPTS
import good_calmet_kraken as gk
import scan_ocr

RANK = {"ok": 3, "near": 2}
NOTE_OPEN = re.compile(r"[(\[{]\s*[a-z]\w?\)?|[a-z][)\]]")  # (a) (b) (ch a) b]: a note's first word
# the margin's and the lemmas' references, the verses' heading: Chap. III. v. 15, ŷ. 6, COMMENTAIRE (misread)
REF_WORD = re.compile(r"(?i)chap|[vyŷ]|[ivxlc]+|\d+|comment\w*|commentalre")
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


def label(job):
    """One Good page's words, each linked (or not) to a JSON word: {t, k, wc, boxes, s, page?, path?, a?, b?}."""
    rec, cand = job
    go = json.loads(gk.cache_path(rec["pdf"], rec["pdf_page"]).read_text(encoding="utf-8"))
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
        r = {"t": w["t"], "k": scan_ocr.key(w["t"]), "wc": w["wc"], "boxes": w["boxes"]}
        li, wi = w["src"][0]
        if len(w["t"]) == 1 and re.search(r"[()]", cols["lines"][li]["words"][wi]["t"]):
            r["s"] = "skip"  # a note's mark: the later edition letters its notes otherwise
            out.append(r)
            continue
        if best:
            r.update(s="match", page=best[0], path=best[1]["path"], a=best[1]["a"], b=best[1]["b"])
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
        return p, None, set()
    res = scan_ocr.align(o, d, fix=True)
    held = {(w["path"], w["a"]) for w in res["words"] if w["s"] in RANK}
    loose = {scan_ocr.key(w["t"]) for w in res["words"] if w["s"] in ("missing", "diff")}
    return p, held, loose


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
    try:
        from clean_mechanical import fix_spelling
        from modernize_inplace import modernize_text
        return modernize_text(fix_spelling(text.replace("ſ", "s").replace("&", "et").replace("’", "'")))[0]
    except Exception:
        return None


def variants(vol, chs, workers=8):
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
        src = {p: (h, l) for p, h, l in ex.map(source_view, [(vol, p, data.get(p)) for p in range(lo, hi + 1)])}

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
            kind, j0 = "unclear", L + 1  # anchors far apart: the words between are matched elsewhere
            j1 = j0
            between = []
        else:
            kind, between = "insert", []
            j0 = j1 = L + 1 if L is not None else R
        if kind == "replace" and len(gaps) <= 2 and scan_ocr.similar(
                " ".join(stream[i]["k"] for i in gaps), " ".join(jt[j]["k"] for j in between)) > 0.6:
            continue  # a misreading of the same words
        claimed.update(between)
        pieces.append({"kind": kind, "j0": j0, "j1": j1, "g0": gaps[0], "g1": gaps[-1] + 1})

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
    for r in out:
        r.pop("_span", None)
    out.sort(key=lambda r: (r["page"], r["path"], r["at"]))
    return out


def merge(pieces, linked, reach=2, g_reach=4):
    """Pieces next to each other (no more than `reach` JSON words, `g_reach` Good words apart) made one: a
    reworded passage comes out as some JSON words alone, some Good words alone, side by side."""
    keep = [p for p in pieces if p["kind"] == "unclear"]
    rest = sorted((p for p in pieces if p["kind"] != "unclear"), key=lambda p: (p["j0"], p["j1"]))
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
    nums = [number(t["t"]) for t in olds] + [number(w["t"]) for w in ws]
    if olds and ws and all(n is not None for n in nums):
        return None  # a reference's numbers, written in figures in the JSON (4 for IV)
    if all(len(t["k"]) <= 2 for t in olds) and all(len(w["k"]) <= 2 for w in ws):
        return None  # an elision or a letter (l' for I, s'): no word changed
    sp = anchor["page"]
    held, loose = src.get(sp, (None, set()))
    loose = loose | src.get(sp + 1, (None, set()))[1] | src.get(sp - 1, (None, set()))[1]
    lone = [t for j, t in zip(range(j0, j1), olds) if j not in linked]
    content = [w for w in ws if len(w["k"]) > 2]
    if lone and held is not None and not any((t["path"], t["a"]) in held for t in lone):
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
           "words": len(ws), "old_words": len(olds), "pieces": c.get("n", 1),
           "before": " ".join(t["t"] for t in jt[max(0, j0 - 6):j0]), "after": " ".join(t["t"] for t in jt[j1:j1 + 6]),
           "good": list(where.values())}
    paths = list(dict.fromkeys(f"{t['page']}:{t['path']}" for t in olds))
    if len(paths) > 1:
        rec["spans"] = paths
    if ws:
        rec["wc_min"] = round(min(w["wc"] for w in ws), 3)
    rec["id"] = hashlib.md5(json.dumps([vol, kind, rec["path"], [w["k"] for w in ws], old]).encode()).hexdigest()[:10]
    rec["_span"] = (j0, j1)
    return rec


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


def lexicon(vol):
    """The keys of every word of the volume's normalized text."""
    if vol not in _lex:
        _lex[vol] = {t["k"] for f in (DATA / vol / "normalized").glob("page_*.json")
                     for t in scan_ocr.json_tokens(json.loads(f.read_text(encoding="utf-8")))}
    return _lex[vol]


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
    near = range(r["page"] - reach, r["page"] + reach + 1)
    old = [scan_ocr.key(t) for t in scan_ocr.TOKEN.findall(r.get("old") or "")]
    new = [scan_ocr.key(t) for t in scan_ocr.OCR_TOKEN.findall(r.get("good_raw") or "")]
    if r["kind"] == "only_normalized":
        pool = _pairs([w["k"] for w in stream if w["src_page"] in near])
        return _held(old, pool) < 0.5
    if r["kind"] == "replace" and scan_ocr.similar(" ".join(old), " ".join(new)) >= 0.75:
        return False
    if len(new) <= 2 and any(k not in lex for k in new if len(k) > 1):
        return False
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
