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
        if best:
            r.update(s="match", page=best[0], path=best[1]["path"], a=best[1]["a"], b=best[1]["b"])
        else:
            r["s"] = "skip" if any(runs[p][i]["s"] == "skip" for p in runs) else "gap"
        out.append(r)
    # the footnotes' block (not compared): from the highest of the words linked to a footnote, in the
    # page's lower half, down
    h = go["size"][1]
    fy = sorted(r["boxes"][0][1] for r in out if r["s"] == "match" and r["path"].startswith("footnotes/")
                and r["boxes"][0][1] > 0.5 * h)
    linked = sorted((r["boxes"][0][1], r["path"].startswith("footnotes/")) for r in out if r["s"] == "match")
    top = next((y for y in fy if len([1 for yy, f in linked if yy >= y]) >= 3
                and sum(f for yy, f in linked if yy >= y) >= 0.8 * len([1 for yy, f in linked if yy >= y])), None)
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
    linked = {w["j"] for w in stream if w["j"] is not None}

    out, claimed = [], set()
    for gaps, after in runs_of(stream):
        before = next((stream[i] for i in range(gaps[0] - 1, -1, -1) if stream[i]["s"] == "match"), None)
        nxt = stream[after] if after is not None else None
        L, R = (before or {}).get("j"), (nxt or {}).get("j")
        if L is None and R is None:
            continue
        anchor = jt[L] if L is not None else jt[R]
        if anchor["page"] not in pages or anchor["path"].startswith("footnotes/"):
            continue
        between = list(range(L + 1, R)) if L is not None and R is not None and L < R else []
        between = [j for j in between if j not in linked]
        if L is not None and R is not None and R <= L:
            kind = "unclear"
        elif between and len(between) <= 3 * len(gaps) + 5:
            kind = "replace"
        else:
            kind, between = "insert", []
        claimed.update(between)
        ws = [stream[i] for i in gaps]
        raw = " ".join(w["t"] for w in ws)
        old = " ".join(jt[j]["t"] for j in between)
        if kind == "replace" and len(ws) <= 2 and scan_ocr.similar(" ".join(w["k"] for w in ws),
                                                                    " ".join(jt[j]["k"] for j in between)) > 0.6:
            continue  # a misreading of the same words
        content = [w for w in ws if len(w["k"]) > 2]
        if not content:
            continue
        # the third witness: the source scan's view of the anchor's page (and the next)
        sp = anchor["page"]
        held, loose = src.get(sp, (None, set()))
        loose = loose | src.get(sp + 1, (None, set()))[1] | src.get(sp - 1, (None, set()))[1]
        if kind == "replace" and held is not None and not any((jt[j]["path"], jt[j]["a"]) in held for j in between):
            origin = "normalized_differs"
        elif kind != "replace" and sum(w["k"] in loose for w in content) >= max(2, 0.6 * len(content)):
            origin = "both_scans"
        else:
            origin = "only_good"
        where = collections.OrderedDict()
        for w in ws:
            g = where.setdefault((w["pdf"], w["pdf_page"]), {
                "pdf": w["pdf"], "pdf_page": w["pdf_page"], "printed": w["printed"],
                "crop": f"data/good_calmet/{w['pdf']}/page_{w['pdf_page']:04d}.png", "boxes": []})
            g["boxes"] += w["boxes"]
        ctx_l = " ".join(t["t"] for t in jt[max(0, (L if L is not None else R) - 6):(L + 1 if L is not None else R)])
        ctx_r = " ".join(t["t"] for t in jt[(R if R is not None else L + 1):(R if R is not None else L + 1) + 6])
        rec = {"kind": kind, "origin": origin, "vol": vol, "page": anchor["page"], "path": anchor["path"],
               "at": (jt[between[0]]["a"] if between else (jt[L]["b"] if L is not None else jt[R]["a"])),
               "old": old, "good_raw": raw, "good_modern": modern(raw), "words": len(ws),
               "wc_min": round(min(w["wc"] for w in ws), 3), "before": ctx_l, "after": ctx_r,
               "good": list(where.values())}
        rec["id"] = hashlib.md5(json.dumps([vol, kind, rec["path"], [w["k"] for w in ws], old]).encode()).hexdigest()[:10]
        out.append(rec)

    # JSON words no Good word holds (3 or more in a row, in the chapter's pages, not footnotes)
    covered = {(r["page"]) for _, _, ws in labelled for r in ws if r.get("page")}
    run = []
    for j, t in enumerate(jt + [None]):
        lone = t is not None and j not in linked and j not in claimed and t["page"] in pages \
            and t["page"] in covered and not t["path"].startswith("footnotes/") and t["path"] != "book_end_marker"
        if lone and (not run or (run[-1] == j - 1 and jt[run[-1]]["path"] == t["path"])):
            run.append(j)
            continue
        if len(run) >= 3:
            held = src.get(jt[run[0]]["page"], (None, set()))[0]
            origin = "normalized_differs" if held is not None and not any((jt[k]["path"], jt[k]["a"]) in held for k in run) else "only_good"
            old = " ".join(jt[k]["t"] for k in run)
            out.append({"kind": "only_normalized", "origin": origin, "vol": vol, "page": jt[run[0]]["page"],
                        "path": jt[run[0]]["path"], "at": jt[run[0]]["a"], "old": old, "words": len(run),
                        "id": hashlib.md5(json.dumps([vol, "only_normalized", jt[run[0]]["path"], old]).encode()).hexdigest()[:10]})
        run = [j] if lone else []
    out = [r for r in out if real(r, jt, stream, lexicon(vol))]
    out.sort(key=lambda r: (r["page"], r["path"], r["at"]))
    return out


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
        pool = _pairs([t["k"] for t in jt if t["page"] in near])
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
