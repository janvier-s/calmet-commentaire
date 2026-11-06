"""Good_Calmet differences turned into proposals for the review editor (docs/good_proposals/<vol>.json).

    uv run --with pillow python3 good_proposals.py <vol> <chapter>[-<chapter>] [--jobs N] [--no-llm]   (--no-llm: the rewrites already cached only)

Footnotes, from good_notes.py and good_notes_quotes.py:
  - a Hebrew or Greek quotation the Bible settles (quote_fix, quote_both, quote_points): the run replaced
    in the note by the right text (Good's own where it agrees, with its vowel points);
  - any other difference in a note normalized has (refs, text, Hebrew/Greek, additions): one proposal per
    note, the note rewritten by agy Flash (text only) to say what Good says, in normalized's style, the
    Bible text given where it settles a quotation. Cached per note and Good text (cache/good_proposals/).
Notes Good adds or drops are listed (`deferred`) but not proposed: they wait for the body text's merge.
Notes added, dropped, merged or split that no hand link settles (`pairing`) become the editor's good_note
items, where a note is linked by hand (good_links.py) when the pairing got it wrong.

A proposal: {id, item, title, why, flags, sure, options: [{label, changes: [{vol, page, path, old, new}]}],
good: [{pdf, pdf_page, printed, crop, boxes}], cause, kinds, good_text, source_text}: the shape
review_proposals.py serves, with the Good crop to show and its boxes to highlight.
"""
import asyncio
import collections
import hashlib
import json
import re
import sys

from paths import DOCS, SCRIPTS
import good_notes as gn
import good_notes_quotes as gq
import good_notes_read as gr

OUT = DOCS / "good_proposals"
CACHE = SCRIPTS / "cache" / "good_proposals"
QUOTE_KINDS = ("quote_fix", "quote_both", "quote_points")
PAIRING_KINDS = ("note_added", "note_dropped", "notes_merged", "note_split")
NOTE_KINDS = ("refs_changed", "script_text_changed", "text_added", "script_changed", "text_changed", "notes_merged")

REWRITE = """You edit a modern French edition of Dom Calmet's Bible commentary (1707-1716). Its footnotes were \
normalized from the first printing: references written out in French, Bible references as "Livre chapitre:verset", \
other works as "livre N, chapitre N", abbreviations expanded. A later, revised printing (GOOD) has this footnote \
otherwise.

MODERN (the modern edition's footnote):
{modern}

GOOD (the revised printing, as printed: Latin abbreviations, roman numerals):
{good}
{first}{bible}
Rewrite MODERN so that it says what GOOD says: the same works, the same book, chapter, verse and page numbers, the \
same quotations, and what GOOD adds; drop what GOOD no longer has. Write it in MODERN's style:
- MODERN's French wording and its references, where GOOD has the same, stay word for word as MODERN writes them;
- new references are written out the way MODERN writes its own (French names of Bible books and authors, \
chapter:verse, "livre", "chapitre", "page"; "&c." as "etc.", "&" as "et" outside quotations);
- Latin, Hebrew and Greek quotations are copied from GOOD as GOOD prints them, even where MODERN has them \
otherwise (keep Hebrew vowel points and Greek accents){bible_rule};
- where MODERN puts its items on separate lines, keep one item per line.
Where GOOD's numbers or quotation look like a plain misprint and MODERN or the first printing has the right one, \
keep the right one.

Answer with the rewritten footnote only, with nothing before or after it."""


def _id(*parts):
    return hashlib.md5("\0".join(str(x) for x in parts).encode()).hexdigest()[:10]


def tidy(t):
    """No space before a comma or a full stop (Good's « , »), one space between words, lines kept."""
    t = re.sub(r"[ \t]+([,.])", r"\1", t)
    return "\n".join(re.sub(r"[ \t]{2,}", " ", ln).strip() for ln in t.split("\n"))


def capital_as(new, old):
    """The replacement's first letter in the case of the quotation's (the Septuagint's text is lower case)."""
    if new and old and old[0].isupper() and new[0].islower():
        return new[0].upper() + new[1:]
    return new


def run_span(text, words):
    """Where a run of words (Hebrew, Greek) stands in a note: (start, end), punctuation between allowed."""
    pat = r"[\s,.;:·'’\-]*".join(re.escape(w) for w in words)
    m = re.search(pat, text)
    return (m.start(), m.end()) if m else None


def quote_proposals(vol, quotes, notes_by_path):
    out = []
    for q in quotes:
        if q["kind"] not in QUOTE_KINDS or not q.get("new"):
            continue
        page, path = q["page"], q["path"]
        old = notes_by_path.get((page, path))
        if old is None:
            continue
        sp = run_span(old, q["json"].split())
        if sp is None:
            continue
        new = old[:sp[0]] + capital_as(q["new"], old[sp[0]:sp[1]]) + old[sp[1]:]
        if new == old:
            continue
        why = [f"{q['script']} {q['kind'].replace('_', ' ')}"]
        if q.get("ref"):
            why.append(f"the {'Septuagint' if q['script'] == 'greek' else 'Masoretic text'}, {q['ref']}: {q['right']}")
        cause = "edition" if q["kind"] == "quote_points" else "normalization" if q.get("good_agrees") else "both printings"
        out.append(dict(page=page, path=path, old=old, new=new, kinds=[q["kind"]], why=why, cause=cause,
                        good=[{k: q[k] for k in ("pdf", "pdf_page", "printed", "crop", "boxes")}],
                        good_text=q.get("good"), title=f"Good_Calmet note: {q['script']} quotation",
                        sure=q["kind"] == "quote_fix"))
    return out


async def rewrite_all(groups, n, llm=True):
    sem = asyncio.Semaphore(n)

    async def one(g):
        key = _id(g["old"], g["good_text"], g.get("bible") or "", REWRITE)
        f = CACHE / g["vol"] / f"{key}.json"
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))["new"]
        if not llm:
            return None  # --no-llm: the rewrites already made only
        first = f"\nTHE FIRST PRINTING (as read from its scan):\n{g['source_text']}\n" if g.get("source_text") else ""
        bible = f"\nTHE BIBLE TEXT of its quotation: {g['bible']}\n" if g.get("bible") else ""
        prompt = REWRITE.format(modern=g["old"], good=g["good_text"], first=first, bible=bible,
                                bible_rule="; a Bible quotation as THE BIBLE TEXT has it" if g.get("bible") else "")
        for _ in range(4):
            if gr.QUOTA["hit"]:
                return None
            ans, err = await gr.call(None, sem, prompt)
            if ans and ans.strip() and "\n\n" not in ans.strip():
                new = tidy(ans.strip().strip("`").strip())
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(json.dumps({"old": g["old"], "good": g["good_text"], "new": new}, ensure_ascii=False, indent=1),
                             encoding="utf-8")
                return new
            if err and re.search(r"quota|exhausted|429", err, re.I):
                gr.QUOTA["hit"] = True
        return None
    return await asyncio.gather(*(one(g) for g in groups))


def build(vol, chs, jobs=6, llm=True):
    diffs, hg = gn.compare(vol, chs)
    quotes = gq.check(vol, chs)
    jsons = {(j["page"], j["path"]): j["text"] for j in gn.json_notes(vol, sorted({d["page"] for d in diffs} | {q["page"] for q in quotes}))}
    props = quote_proposals(vol, quotes, jsons)
    quoted = {(p["page"], p["path"]) for p in props}
    bible = {(q["page"], q["path"]): f"{q['ref']}: {q['right']}" for q in quotes if q.get("right")}
    groups = collections.OrderedDict()
    deferred = []
    pairing = [{k: d[k] for k in ("id", "kind", "vol", "page", "cause", "origin", "likeness", "notes") if k in d}
               for d in diffs if d["kind"] in PAIRING_KINDS and not d.get("linked")]
    for d in diffs:
        if d["kind"] in ("note_added", "note_dropped"):
            deferred.append(d)
            continue
        if d["kind"] not in NOTE_KINDS or not d.get("path"):
            continue
        key = (d["page"], d["path"])
        g = groups.setdefault(key, {"vol": vol, "page": d["page"], "path": d["path"], "old": jsons.get(key, d["json_text"]),
                                    "good_text": d["good_raw"], "source_text": d.get("source_raw"), "kinds": [],
                                    "causes": set(), "good": d["good"], "bible": bible.get(key)})
        g["kinds"].append(d["kind"])
        g["causes"].add(d.get("cause") or "unsure")
    groups = [g for g in groups.values() if g["good_text"]]
    news = asyncio.run(rewrite_all(groups, jobs, llm))
    for g, new in zip(groups, news):
        if not new or new == g["old"]:
            continue
        if (g["page"], g["path"]) in quoted:  # the rewrite holds the quotation's fix too: it wins
            props = [p for p in props if (p["page"], p["path"]) != (g["page"], g["path"])]
        cs = g["causes"] - {"unsure"}
        props.append(dict(page=g["page"], path=g["path"], old=g["old"], new=new, kinds=sorted(set(g["kinds"])),
                          why=[k.replace("_", " ") for k in sorted(set(g["kinds"]))] + ([f"Bible: {g['bible']}"] if g.get("bible") else []),
                          cause=" + ".join(sorted(cs)) or "unsure", good=g["good"], good_text=g["good_text"],
                          source_text=g.get("source_text"), title="Good_Calmet note", sure=False))
    out = []
    for p in props:
        i = int(p["path"].split("/")[1])
        pid = _id(vol, p["page"], p["path"], p["old"], p["new"])
        iid = f"{vol}/{p['page']:04d}/good_variant/{pid}"
        flags = [p["cause"].replace(" ", "-")]
        out.append({"id": iid, "item": iid, "vol": vol, "page": p["page"], "title": p["title"], "why": p["why"],
                    "flags": flags, "sure": p["sure"], "cause": p["cause"], "kinds": p["kinds"], "good": p["good"],
                    "good_text": p.get("good_text"), "source_text": p.get("source_text"),
                    "options": [{"label": "Good_Calmet", "changes": [
                        {"vol": vol, "page": p["page"], "path": ["footnotes", i, "text"], "old": p["old"], "new": p["new"]}]}]})
    return out, deferred, pairing


def main(argv):
    if not argv:
        sys.exit(__doc__)
    vol, spec = argv[0], argv[1]
    a, _, b = spec.partition("-")
    chs = set(range(int(a), int(b or a) + 1))
    jobs = int(argv[argv.index("--jobs") + 1]) if "--jobs" in argv else 6
    props, deferred, pairing = build(vol, chs, jobs, "--no-llm" not in argv)
    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / f"{vol}.json"
    old = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"proposals": [], "deferred": []}
    pages = {p for p in range(min(gn.gv.chapter_pages(vol, chs)), max(gn.gv.chapter_pages(vol, chs)) + 1)}
    keep = [p for p in old["proposals"] if p["page"] not in pages]  # other chapters' proposals stay
    keep_d = [d for d in old.get("deferred", []) if d["page"] not in pages]
    keep_p = [d for d in old.get("pairing", []) if d["page"] not in pages]
    f.write_text(json.dumps({"proposals": sorted(keep + props, key=lambda p: (p["page"], p["id"])),
                             "deferred": keep_d + deferred, "pairing": keep_p + pairing},
                            ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{vol} ch. {spec}: {len(props)} proposals {dict(collections.Counter(p['cause'] for p in props))}; "
          f"{len(deferred)} added/dropped notes deferred; {len(pairing)} pairings to check by hand -> {f}")
    for p in props:
        c = p["options"][0]["changes"][0]
        print(f"\n[{p['cause']}] p{p['page']} {c['path']} {', '.join(p['kinds'])}")
        print(f"   OLD: {c['old'][:160]}")
        print(f"   NEW: {c['new'][:160]}")


if __name__ == "__main__":
    main(sys.argv[1:])
