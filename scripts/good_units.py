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
