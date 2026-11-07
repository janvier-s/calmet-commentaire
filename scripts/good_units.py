"""The units the two editions are compared by (a note with its lemma, a verse's French, a chapter's title,
summary or introduction), the Good_Calmet text on each, their changes and a status.

Good's OCR is not cut into units on its own: good_variants.align links each Good word to a word of the
normalized JSON, and a Good word goes to the unit that holds its linked word.

    python3 good_units.py <vol> <chapter>[-<chapter>] [--out FILE]    (default: data/<vol>/good_units.json,
                                                                       its other chapters' units kept)
"""
import collections
import re

from continuations import continues

HEADS = {"chapter_title": "title", "chapter_summary": "summary", "chapter_argument": "summary", "chapter_intro": "intro"}
NOTE_FIELDS = ("latin_quote", "french_translation", "french_commentary")
CALL = re.compile(r"\^\{([^}]*)\}")


def type_of(path):
    if path.startswith("commentary/"):
        return "commentary"
    if path.startswith("verses/"):
        return "verse"
    return HEADS.get(path)


def _text(s):
    return " ".join(CALL.sub("", s).split())


def _notes(page, data, texts):
    marks = {m for t in texts for m in CALL.findall(t)}
    return [{"page": page, "path": f"footnotes/{k}"} for k, f in enumerate(data.get("footnotes") or [])
            if f.get("marker") in marks]


def old_units(data):
    """The units of the pages `data` ({page: page JSON}), in reading order (a note over a page turn is one unit)."""
    units, count, last = [], collections.Counter(), None

    def add(typ, chapter, verse, page, parts, lemma=None):
        key = (typ, str(chapter), str(verse))  # verse_ref is an int on some pages, a string on others
        u = {"uid": f"{typ}:{chapter}:{verse}:{count[key]}", "type": typ, "chapter": chapter, "verse": verse,
             "lemma": lemma, "parts": [{"page": page, "path": p} for p, _ in parts], "_texts": [t for _, t in parts]}
        count[key] += 1
        units.append(u)
        return u

    for p in sorted(data):
        d = data[p]
        notes = d.get("commentary") or []
        opening = d.get("chapter_title") and (d.get("verses") or [{}])[0].get("chapter")
        before = 0
        while opening and before < len(notes) and notes[before].get("chapter") not in (None, opening):
            before += 1
        chapter = d.get("chapter_number") or (d.get("verses") or [{}])[0].get("chapter")

        def note(i, blk):
            nonlocal last
            parts = [(f"commentary/{i}/{f}", blk[f]) for f in NOTE_FIELDS if isinstance(blk.get(f), str) and blk[f].strip()]
            if last is not None and continues(last["_texts"][-1] if last["_texts"] else "", blk):
                last["parts"] += [{"page": p, "path": path} for path, _ in parts]
                last["_texts"] += [t for _, t in parts]
                last.setdefault("_pages", set()).add(p)
                return
            first = blk.get("latin_quote") or " ".join((blk.get("french_translation") or blk.get("french_commentary") or "").split()[:8])
            last = add("commentary", blk.get("chapter"), blk.get("verse_ref"), p, parts, lemma=first.strip() or None)

        for i in range(before):
            note(i, notes[i])
        for f, typ in HEADS.items():
            if isinstance(d.get(f), str) and d[f].strip():
                add(typ, chapter, None, p, [(f, d[f])])
        for i, v in enumerate(d.get("verses") or []):
            if isinstance(v.get("french"), str) and v["french"].strip():
                add("verse", v.get("chapter"), v.get("verse_number"), p, [(f"verses/{i}/french", v["french"])])
        for i in range(before, len(notes)):
            note(i, notes[i])

    for u in units:
        texts = u.pop("_texts")
        u.pop("_pages", None)
        u["old"] = _text(" ".join(texts))
        u["notes"] = []
        for part, t in zip(u["parts"], texts):
            for n in _notes(part["page"], data[part["page"]], [t]):
                if n not in u["notes"]:
                    u["notes"].append(n)
    return units


def unit_index(units):
    """(page, path) -> the uid of the unit holding that field."""
    return {(p["page"], p["path"]): u["uid"] for u in units for p in u["parts"]}


def _number(t):
    t = t.strip(".,;:")
    if t.isdigit():
        return int(t)
    import good_variants
    return good_variants.number(t)


def lemma_start(words):
    """Where a lemma only Good has opens in `words` (texts): a verse mark (ŷ. 7., V. 7) then, within 2
    words, two words in capitals. (index, verse) or None."""
    for i in range(len(words) - 1):
        if words[i].strip(".").lower() not in ("v", "y", "ŷ") or _number(words[i + 1]) is None:
            continue
        rest = [w.strip(".,;:") for w in words[i + 2:i + 5]]
        if any(a.isupper() and b.isupper() and len(a) >= 2 and len(b) >= 2 for a, b in zip(rest, rest[1:])):
            return i, _number(words[i + 1])
    return None


def _where(ws):
    where = collections.OrderedDict()
    for w in ws:
        g = where.setdefault((w["pdf"], w["pdf_page"]), {
            "pdf": w["pdf"], "pdf_page": w["pdf_page"], "printed": w.get("printed"),
            "crop": f"data/good_calmet/{w['pdf']}/page_{w['pdf_page']:04d}.png", "boxes": []})
        g["boxes"] += w["boxes"]
    return list(where.values())


def _fill(u, ws):
    u["good"] = " ".join(w["t"] for w in ws)
    u["good_where"] = _where(ws)
    u["good_words"] = len(ws)


HEAD_SIM = 0.6
HEAD_MIN = 3  # words: "Chapitre II." alone is too slight to look for
SHORT_UNIT = 60  # words: a longer unit with no linked word is left alone
HEADING_WORD = re.compile(r"(?i)chap\w*|[ivxlc]+|\d+")


def _head_window(run, heads, got):
    """A short unit no Good word is linked to (`heads`: page -> units), not found yet, read in `run`
    (unlinked words) on its page or one either side: (uid, start, end) of its words ("CHAPITRE III"
    before a heading included), or None."""
    import scan_ocr
    pages = {w.get("src_page") for w in run} - {None}
    cands = [u for p in pages for q in (p - 1, p, p + 1) for u in heads.get(q, []) if not got.get(u["uid"])]
    keys = [scan_ocr.key(w["t"]) for w in run]
    best = None
    for u in cands:
        target = " ".join(scan_ocr.key(t) for t in scan_ocr.OCR_TOKEN.findall(u["old"]))
        n = len(target.split())
        if n < HEAD_MIN:
            continue
        for s in range(0, max(1, len(run) - n + 1)):
            sim = scan_ocr.similar(" ".join(keys[s:s + n]), target)
            if sim >= HEAD_SIM and (best is None or sim > best[0]):
                best = (sim, u["uid"], s, min(len(run), s + n))
    if not best:
        return None
    _, uid, s, e = best
    while s > 0 and HEADING_WORD.fullmatch(run[s - 1]["t"].strip(".")):
        s -= 1
    return uid, s, e


LONG_RUN = 40  # unlinked words: a run this long the old text holds elsewhere is not given to a neighbour
COVER_SHARE = 0.3


def covered_pages(ctx):
    """The source pages a share (COVER_SHARE) of whose words some Good word is linked to: a page with a Good
    scan but no link, or a few stray ones, was not aligned (its units are `uncovered`, not `only_old`)."""
    jt = ctx["jt"]
    linked = {w["j"] for w in ctx["stream"] if w.get("j") is not None and w["s"] != "skip"}
    total, held = collections.Counter(), collections.Counter()
    for j, t in enumerate(jt):
        if not t["path"].startswith("footnotes/"):
            total[t["page"]] += 1
            held[t["page"]] += j in linked
    return {p for p in total if held[p] >= COVER_SHARE * total[p] and held[p]}


STRAY_PAGES = 2
STRAY = 4  # linked words: a group this short, linked to another unit than the same one on both sides, is a mislink


def _mend_strays(owner, ws, jt):
    """The aligner sometimes links a word or two ("& la") to a similar place far off, inside a stretch of
    Good text linked to one unit. Such a short group of words (at most STRAY, the unlinked words between
    them aside) whose unit differs from the one the words before and after it are linked to (the same on
    both sides) and whose words are linked more than a page away from the Good word's own page (STRAY_PAGES)
    goes to that unit: the Good words then stay with the text around them. Edits `owner`."""
    groups = []  # [owner, [indexes]] of the linked words, in order
    for i, o in enumerate(owner):
        if o is None:
            continue
        if groups and groups[-1][0] == o:
            groups[-1][1].append(i)
        else:
            groups.append([o, [i]])
    for k in range(1, len(groups) - 1):
        o, ix = groups[k]
        prev, nxt = groups[k - 1][0], groups[k + 1][0]
        far = all(ws[i].get("src_page") is not None and ws[i].get("j") is not None
                  and abs(jt[ws[i]["j"]]["page"] - ws[i]["src_page"]) >= STRAY_PAGES for i in ix)
        if len(ix) <= STRAY and far and prev == nxt != o:
            for i in ix:
                owner[i] = prev
            groups[k][0] = prev


VERSE_FOUND = 0.5  # a verse with fewer Good words than this share of its own is looked for in all of Good's text
VERSE_VOTES = 0.5  # the share of a verse's word pairs a stretch of Good's words must hold to be taken for it
QUOTE = 0.4  # a stretch linked, for more than this share, to notes is a note quoting the verse, not the verse


def _find_verses(units, ws, owner, got):
    """Good prints a verse's French inline, before its commentary, where the old edition has it at the top
    of an earlier page (up to a dozen pages off), so the aligner's window (a few pages round the one Good's
    page matches) never holds it, and Kraken reads it between the commentary's lines. A verse unit left with
    little Good text is looked for in the whole of Good's words, by the word pairs it shares with a stretch of
    them: the words found go to it, from whichever unit had them (`got`, edited)."""
    by_uid = {u["uid"]: u for u in units}
    pairs = collections.defaultdict(list)
    keys = [scan_ocr_key(w["t"]) for w in ws]
    for p, ab in enumerate(zip(keys, keys[1:])):
        pairs[ab].append(p)
    taken = set()  # words given to a verse here
    for u in units:
        if u["type"] != "verse":
            continue
        ok = _keys(u["old"])
        n = len(ok)
        if n < 6 or len(got.get(u["uid"], [])) >= VERSE_FOUND * n:
            continue
        votes = collections.Counter()
        for i, ab in enumerate(zip(ok, ok[1:])):
            for p in pairs.get(ab, ()):
                votes[p - i] += 1
        best = max(votes, key=lambda st: sum(votes.get(st + d, 0) for d in range(-3, 4)), default=None)
        if best is None:
            continue
        hits = sorted(p for i, ab in enumerate(zip(ok, ok[1:])) for p in pairs.get(ab, ())
                      if best - 3 <= p - i <= best + 3)
        if len(set(hits)) < VERSE_VOTES * (n - 1):
            continue
        a, b = max(0, min(hits)), min(len(ws), max(hits) + 2)
        span = range(a, b)
        if any(i in taken for i in span):
            continue
        mine = [i for i in span if owner[i] is None or by_uid[owner[i]]["type"] == "verse"]
        if len(span) - len(mine) > QUOTE * len(span):
            continue  # linked to notes for the most part: a note quoting the verse
        moved = {id(ws[i]) for i in mine}
        for uid in list(got):
            got[uid] = [w for w in got[uid] if id(w) not in moved]
        # what the verse already held stays (the unlinked words after it): the unit before gets nothing back
        have = {id(w) for w in got.get(u["uid"], [])} | moved
        got[u["uid"]] = [w for w in ws if id(w) in have]
        taken |= set(span)


DISPLACED_RUN = 30  # words: an unlinked run this long, on either side, may be a passage the editions order differently
DISPLACED_BLOCK = 6  # words in a row two such runs share to be linked


def relink_displaced(ctx):
    """A passage the old edition prints elsewhere (Genèse 10: the notes on v.8-12, deferred "jusqu'à
    présent", stand after v.19's) is outside every page window the aligner reads Good's page against: its Good
    words and its JSON words are both left unlinked, in long runs. The words of such runs, in order, are
    matched against each other (blocks of DISPLACED_BLOCK words or more) and linked as the aligner's own
    matches are (`ctx` edited; returns the number of words linked)."""
    import difflib
    stream, jt, linked = ctx["stream"], ctx["jt"], ctx["linked"]

    def runs(items, free, minimum):
        out, cur = [], []
        for i in items:
            if free(i):
                cur.append(i)
            elif cur:
                out += cur if len(cur) >= minimum else []
                cur = []
        return out + (cur if len(cur) >= minimum else [])

    good = [i for i in runs([i for i, w in enumerate(stream) if w["s"] != "skip"],
                            lambda i: stream[i].get("j") is None, DISPLACED_RUN)]
    old = runs([j for j, t in enumerate(jt) if not t["path"].startswith("footnotes/")],
               lambda j: j not in linked, DISPLACED_RUN)
    if not good or not old:
        return 0
    n = 0
    sm = difflib.SequenceMatcher(None, [stream[i]["k"] for i in good], [jt[j]["k"] for j in old])
    for a, b, size in sm.get_matching_blocks():
        if size < DISPLACED_BLOCK:
            continue
        for i, j in zip(good[a:a + size], old[b:b + size]):
            t = jt[j]
            stream[i].update(s="match", j=j, page=t["page"], path=t["path"], a=t["a"], b=t["b"], near=False)
            linked.add(j)
            n += 1
    return n


def project(units, ctx):
    """Give each unit Good's words for it (`good`, `good_where`, `good_words`). A Good word linked to a JSON
    word goes to that word's unit; unlinked words between two words of one unit go to it, between two
    units to the earlier one, except: a short unit no word is linked to, found among them (_head_window); a
    lemma Good alone has (lemma_start), made a unit of its own (uid good:<chapter>:<verse>:<n>); a run of
    LONG_RUN words or more the old text holds elsewhere (the aligner missed it), made an `unaligned` unit.
    A word linked to a footnote counts as unlinked (the footnotes' block is already cut off in good_variants,
    so what is left of it is a mislink). Returns the new units (`after`: the
    unit each follows)."""
    import good_variants as gv
    idx = unit_index(units)
    by_uid = {u["uid"]: u for u in units}
    jt = ctx["jt"]
    ws, owner = [], []
    for w in ctx["stream"]:
        if w["s"] == "skip":
            continue
        if w.get("j") is None:
            ws.append(w), owner.append(None)
            continue
        at = (jt[w["j"]]["page"], jt[w["j"]]["path"])
        if at in idx:
            ws.append(w), owner.append(idx[at])
        elif at[1].startswith("footnotes/"):
            ws.append(w), owner.append(None)
        # linked to another field no unit holds (the verses' Latin): left out, the run goes on
    _mend_strays(owner, ws, jt)
    got = collections.defaultdict(list)
    # page -> its short units no Good word is linked to (a chapter's heading, a verse Kraken read inside
    # another): looked for among the unlinked words
    linked_uids = set(owner) - {None}
    heads = collections.defaultdict(list)
    for u in units:
        if u["parts"] and u["uid"] not in linked_uids and len(u["old"].split()) <= SHORT_UNIT:
            heads[u["parts"][0]["page"]].append(u)
    old_grams = gv._grams([k for u in units for k in _keys(u["old"])])
    new, count = [], collections.Counter()

    def unit(prefix, typ, chapter, verse, words, after, lemma=None):
        key = (prefix, str(chapter), str(verse))
        uid = f"{prefix}:{chapter}:{verse}:{count[key]}" if verse is not None or prefix == "good" else f"{prefix}:{chapter}:{count[key]}"
        count[key] += 1
        u = {"uid": uid, "type": typ, "chapter": chapter, "verse": verse, "lemma": lemma, "parts": [], "old": "",
             "notes": [], "after": after}
        _fill(u, words)
        new.append(u)

    def place(seg, host, chapter, split):
        """Unlinked words `seg` whose default unit is `host`."""
        start = lemma_start([w["t"] for w in seg]) if split else None
        if start:
            s, verse = start
            if host:
                got[host] += seg[:s]
            unit("good", "commentary", chapter, verse, seg[s:], host, lemma=" ".join(w["t"] for w in seg[s + 2:s + 8]))
        elif split and len(seg) >= LONG_RUN and gv._share([scan_ocr_key(w["t"]) for w in seg], old_grams) >= 0.5:
            unit("unaligned", "unaligned", chapter, None, seg, host)
        elif host:
            got[host] += seg

    i = 0
    while i < len(ws):
        if owner[i] is not None:
            got[owner[i]].append(ws[i])
            i += 1
            continue
        k = i
        while k < len(ws) and owner[k] is None:
            k += 1
        after = owner[k] if k < len(ws) else None
        prev = next((owner[m] for m in range(i - 1, -1, -1) if owner[m] is not None), None)
        nxt = next((owner[m] for m in range(k, len(ws)) if owner[m] is not None), None)
        run, host = ws[i:k], prev or nxt
        chapter = by_uid[host]["chapter"] if host else None
        split = prev != nxt
        while True:
            head = _head_window(run, heads, got)
            if not head:
                place(run, host, chapter, split)
                break
            uid, s, e = head
            place(run[:s], host, chapter, split)
            got[uid] += run[s:e]
            # after a chapter's heading: the new chapter's text
            run, host, chapter, split = run[e:], nxt or prev, by_uid[uid]["chapter"], True
        i = k
    _find_verses(units, ws, owner, got)
    for u in units:
        _fill(u, got.get(u["uid"], []))
    return new


def scan_ocr_key(t):
    import scan_ocr
    return scan_ocr.key(t)


COSMETIC_SIM = 0.8


def classify(r):
    """noise (a misreading, a word cut at a line's end), moved, cosmetic (a word or two, or nearly the
    same words once modernized), substantive."""
    import scan_ocr
    if r.get("confidence") == "low" or r.get("split"):
        return "noise"
    if r["kind"] == "moved":
        return "moved"
    if max(r.get("words", 0), r.get("old_words", 0)) <= 2:
        return "cosmetic"
    good = r.get("good_modern") or r.get("good_raw") or ""
    if r.get("old") and good and scan_ocr.similar(r["old"], good) >= COSMETIC_SIM:
        return "cosmetic"
    return "substantive"


def status(u, covered):
    """only_good, unaligned (Good text the aligner placed nowhere), uncovered (no page of it has a Good match: a missing scan, not a cut), only_old (Good has
    no word of it), substantive, cosmetic, identical."""
    if u["uid"].startswith("good:"):
        return "only_good"
    if u["uid"].startswith("unaligned:"):
        return "unaligned"
    if not any(p["page"] in covered for p in u["parts"]):
        return "uncovered"
    if not u.get("good_words"):
        return "only_old"
    classes = {c["class"] for c in u.get("changes") or []}
    if classes & {"substantive", "moved"}:
        return "substantive"
    if "cosmetic" in classes:
        return "cosmetic"
    return "identical"


def _keys(text):
    import scan_ocr
    return [scan_ocr.key(t) for t in scan_ocr.OCR_TOKEN.findall(text or "")]


def attach(units, records, covered):
    """Put good_variants' records on the units holding their field (each with its `class`,
    `gap_in_normalized`: both scans have Good's words, and `moved_with`: the unit the moved words come from or
    go to) and set each unit's `status`. Returns {"unattached": records on no unit (footnotes, Latin)}."""
    import good_variants as gv
    idx = unit_index(units)
    by_uid = {u["uid"]: u for u in units}
    for u in units:
        u["changes"] = []
    unattached = 0
    verses = {u["uid"]: gv._grams(_keys(u.get("good"))) for u in units if u["type"] == "verse" and u.get("good")}
    for r in records:
        where = [(r["page"], r["path"])] + [tuple((int(s.split(":", 1)[0]), s.split(":", 1)[1])) for s in r.get("spans", [])]
        uid = next((idx[w] for w in where if w in idx), None)
        if uid is None:
            unattached += 1
            continue
        c = dict(r, **{"class": classify(r), "gap_in_normalized": r.get("origin") == "both_scans", "moved_with": None})
        if not r.get("old") and r.get("words", 0) >= 5 and c["class"] != "noise":
            # Good words with nothing of the old text against them that a verse unit holds: the verse's French,
            # printed inline in the commentary, found by _find_verses, not an insertion
            mine = _keys(r.get("good_raw"))
            if any(gv._share(mine, g) >= 0.6 for v, g in verses.items() if v != uid):
                c["class"], c["in_verse"] = "noise", True
        if c["class"] == "moved":
            mine = _keys(r.get("old") or r.get("good_raw"))
            side = "good" if r.get("old") else "old"  # the words left here are found in another unit's Good text
            best = max(((gv._share(mine, gv._grams(_keys(o.get(side)))), o["uid"]) for o in units if o["uid"] != uid),
                       default=(0, None))
            c["moved_with"] = best[1] if best[0] >= 0.5 else None
        by_uid[uid]["changes"].append(c)
    _link_back(units, by_uid)
    for u in units:
        u["status"] = status(u, covered)
    return {"unattached": unattached}


def _link_back(units, by_uid):
    """moved_with is found from one side only; the unit it names gets the link back on its moved change that
    names nobody (the one with the most words in common, when several), so both ends open each other."""
    import good_variants as gv
    for u in units:
        for c in u["changes"]:
            other = by_uid.get(c.get("moved_with"))
            if c["class"] != "moved" or other is None:
                continue
            if any(o.get("moved_with") == u["uid"] for o in other["changes"]):
                continue
            mine = _keys(c.get("old") or c.get("good_raw"))
            free = [o for o in other["changes"] if o["class"] == "moved" and not o.get("moved_with")]
            if free:
                side = "good_raw" if c.get("old") else "old"
                best = max(free, key=lambda o: gv._share(mine, gv._grams(_keys(o.get(side)))))
                best["moved_with"] = u["uid"]


def _chapter_key(u):
    try:
        return int(u.get("chapter"))
    except (TypeError, ValueError):
        return 10 ** 6


def build(vol, chs):
    """The units of chapters `chs`, with Good's text, their changes and status."""
    import good_variants as gv
    ctx = gv.align(vol, chs)
    relink_displaced(ctx)
    units = old_units(ctx["data"])
    new = project(units, ctx)  # over the neighbouring chapters' pages too, so their words don't fall in here
    covered = covered_pages(ctx)
    summary = attach(units + new, gv.variants(vol, chs, ctx=ctx), covered)
    after = collections.defaultdict(list)
    for n in new:
        after[n["after"]].append(n)
    out = []
    for u in units:
        out.append(u)
        out += after.get(u["uid"], [])
    out += after.get(None, [])
    out = [u for u in out if u.get("chapter") is not None and _chapter_key(u) in chs]
    return {"vol": vol, "chapters": sorted(chs), "units": out, "summary": summary}


def _summary(units, unattached):
    s = dict(collections.Counter(u["status"] for u in units))
    s["unattached"] = unattached
    return s


def write(vol, chs, out):
    """Build chapters `chs` into the file `out`, keeping its units of other chapters."""
    import json
    from pathlib import Path
    out = Path(out)
    res = build(vol, chs)
    old = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {"units": [], "chapters": [], "unattached": {}}
    kept = [u for u in old["units"] if _chapter_key(u) not in chs]
    units = sorted(kept + res["units"], key=_chapter_key)  # stable: reading order within a chapter
    unattached = dict(old.get("unattached") or {})
    unattached[",".join(map(str, sorted(chs)))] = res["summary"]["unattached"]
    merged = {"vol": vol, "chapters": sorted(set(old["chapters"]) | set(chs)), "units": units,
              "unattached": unattached, "summary": _summary(units, sum(unattached.values()))}
    out.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
    return merged


def main(argv):
    import sys
    from paths import DATA
    if len(argv) < 2:
        sys.exit(__doc__)
    vol, spec = argv[0], argv[1]
    a, _, b = spec.partition("-")
    chs = set(range(int(a), int(b or a) + 1))
    out = argv[argv.index("--out") + 1] if "--out" in argv else DATA / vol / "good_units.json"
    res = write(vol, chs, out)
    mine = [u for u in res["units"] if _chapter_key(u) in chs]
    print(f"{vol} ch. {spec}: {len(mine)} units  " + str(dict(collections.Counter(u["status"] for u in mine))))
    print("  by type: " + str(dict(collections.Counter((u["type"], u["status"]) for u in mine))))
    print(f"  file {out}: {res['summary']}")


if __name__ == "__main__":
    import sys
    main(sys.argv[1:])
