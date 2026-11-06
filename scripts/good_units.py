"""The units the two editions are compared by (a note with its lemma, a verse's French, a chapter's title,
summary or introduction), the Good_Calmet text on each, their changes and a status.

Good's OCR is not cut into units on its own: good_variants.align links each Good word to a word of the
normalized JSON, and a Good word goes to the unit that holds its linked word.
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


def project(units, ctx):
    """Give each unit Good's words for it (`good`, `good_where`, `good_words`). A Good word linked to a JSON
    word goes to that word's unit; unlinked words between two words of one unit go to it, between two
    units to the earlier one, except from a lemma Good alone has (lemma_start): those become a unit of their
    own, returned (uid good:<chapter>:<verse>:<n>, `after`: the unit it follows)."""
    idx = unit_index(units)
    by_uid = {u["uid"]: u for u in units}
    jt = ctx["jt"]
    # words linked to a field no unit holds (footnotes, the verses' Latin) belong to no unit
    ws = [w for w in ctx["stream"] if w["s"] != "skip"
          and (w.get("j") is None or (jt[w["j"]]["page"], jt[w["j"]]["path"]) in idx)]
    owner = [idx.get((jt[w["j"]]["page"], jt[w["j"]]["path"])) if w.get("j") is not None else None for w in ws]
    got = collections.defaultdict(list)
    new, count = [], collections.Counter()
    i = 0
    while i < len(ws):
        if owner[i] is not None:
            got[owner[i]].append(ws[i])
            i += 1
            continue
        k = i
        while k < len(ws) and owner[k] is None:
            k += 1
        prev = next((owner[m] for m in range(i - 1, -1, -1) if owner[m]), None)
        nxt = owner[k] if k < len(ws) else None
        run = ws[i:k]
        start = lemma_start([w["t"] for w in run]) if prev != nxt else None
        host = prev or nxt
        if start:
            s, verse = start
            if host:
                got[host] += run[:s]
            chapter = by_uid[host]["chapter"] if host else None
            key = (str(chapter), str(verse))
            u = {"uid": f"good:{chapter}:{verse}:{count[key]}", "type": "commentary", "chapter": chapter,
                 "verse": verse, "lemma": " ".join(w["t"] for w in run[s + 2:s + 8]), "parts": [], "old": "",
                 "notes": [], "after": host}
            count[key] += 1
            _fill(u, run[s:])
            new.append(u)
        elif host:
            got[host] += run
        i = k
    for u in units:
        _fill(u, got.get(u["uid"], []))
    return new
