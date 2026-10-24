"""Check the Bible references of the commentary, and the verse numbers of the verses, against the Vulgate.

  python3 ref_check.py <volume|book|all> ...     report -> docs/ref_check.json
  python3 ref_check.py <volume|book|all> ... --apply   also write in the references a quotation settles

A quotation counts only when it is set right against its reference (nothing but punctuation
between): further off, it is often another reference's.

What it finds:
  missing     a reference to a verse the Vulgate does not have (Genèse 48:33: the chapter has 22)
  mismatch    the Latin quoted with a reference is another verse (Calmet's slip or the printer's)
  numbering   a verse whose Latin is a neighbouring verse's (from docs/vulgate_check.json; the
              Psalms, numbered otherwise by Calmet, aside)
Each item carries its candidates, the verses it may have meant, with their Vulgate text: the
reference with a digit misread (1/7, 3/8, 5/6), the chapter a Roman numeral off (XXII/XXIII),
the verses around it, and for a quotation, the verse of the whole Bible it is. When the quotation
settles it, the item has `fix`. The rest are for a model or a reader.

Only references written chapitre:verset are read in the commentary: in prose the abbreviated
forms catch French words (le deuil -> Deu. il).
"""
import json
import re
import sys
from collections import Counter

import bible_refs as B
from calmet import _fold, vulgate_words
from footnotes import latin_words, misread, vulgate_index
from paths import DATA, DOCS, pages, volumes_of

OUT = DOCS / "ref_check.json"
ITALIC = re.compile(r"_([^_]{12,})_")
GAP = re.compile(r"[\s,.;:()]{0,4}")  # all that may stand between a reference and its quotation


FRENCH = set("le la les des du un une il ils elle elles sont pour dans avec cette ces leur vous nous je".split())


def is_latin(t):
    """Latin, not French: most words are the Vulgate's and none is a French article or pronoun
    (Il planta un jardin dans Éden is made of Vulgate words too: planta, dans, Eden)."""
    ws = re.findall(r"[^\W\d_]+", t)
    long = [w for w in ws if len(w) >= 3]
    return (len(long) >= 4 and not any(w.lower() in FRENCH for w in ws)
            and sum(_fold(w) in vulgate_words() for w in long) >= 0.6 * len(long))


def quote_near(text, r, refs):
    """The Latin quotation set right against the reference, or "": the one after it first; the one
    before it only if no other reference stands right before that quotation (Deutéronome 32:39
    _Ego occidam…_ 1 Rois 2:6: the quotation is Deutéronome's)."""
    after = before = ""
    for m in ITALIC.finditer(text):
        if not is_latin(m.group(1)):
            continue
        if m.start() >= r.end and GAP.fullmatch(text[r.end:m.start()]) and not after:
            after = m.group(1)
        if m.end() <= r.start and GAP.fullmatch(text[m.end():r.start]):
            owned = any(o is not r and o.end <= m.start() and GAP.fullmatch(text[o.end:m.start()]) for o in refs)
            before = "" if owned else m.group(1)
    return after or before


def fit(quote, ref):
    q = latin_words(quote)
    return len(q & latin_words(B.vulgate_text(ref))) / len(q) if q else 0


def neighbours(r):
    out = []
    for d in (-2, -1, 1, 2):
        vs = [v + d for v in r.verses]
        x = B.Ref(r.start, r.end, r.book, r.name, r.chap, vs, r.src)
        if all(v > 0 for v in vs) and B.exists(x):
            out.append(x)
    return out


def anywhere(quote):
    """The verse of the whole Vulgate the quotation is, if one fits well: (Ref, score) or None."""
    q = latin_words(quote)
    if len(q) < 4:
        return None
    (name, c, v), (_, ws) = max(vulgate_index().items(), key=lambda kv: len(q & kv[1][1]))
    score = len(q & ws) / len(q)
    return (B.Ref(0, 0, name, name, c, [v], ""), score) if score >= 0.6 else None


def candidates(r, quote):
    """[(rendered reference, its Vulgate text, how well the quotation fits it)], best first."""
    seen, out = set(), []
    pool = misread(r) + neighbours(r)
    far = anywhere(quote) if quote else None
    if far:
        pool.append(far[0])
    for x in pool:
        k = x.render()
        if k in seen or k == r.render():
            continue
        seen.add(k)
        out.append((k, B.vulgate_text(x)[:200], round(fit(quote, x), 2) if quote else None))
    return sorted(out, key=lambda c: -(c[2] or 0))


def fits_here(quote, r):
    """The quotation is this verse, or runs on from it into the next (or from the one before)."""
    if fit(quote, r) >= 0.4:
        return True
    for d in (1, -1):
        x = B.Ref(r.start, r.end, r.book, r.name, r.chap, sorted({*r.verses, r.verses[-1 if d > 0 else 0] + d}), r.src)
        if B.exists(x) and fit(quote, x) >= 0.6:
            return True
    return False


def psalm_numbering(r, cands):
    """A Psalm verse one or two off: Calmet numbers the Psalms' verses otherwise (titles), no error."""
    return r.book == "Psaumes" and cands and cands[0][2] and cands[0][2] >= 0.6 and \
        re.fullmatch(r"Psaumes (\d+):(\d+)", cands[0][0]) and int(cands[0][0].split(":")[0].split()[-1]) == r.chap \
        and abs(int(cands[0][0].split(":")[1]) - r.verses[0]) <= 2


def check_text(where, field, text, items, stats):
    refs = B.find_refs(text)
    for r in refs:
        src = text[r.start:r.end]
        if not re.search(r"\d+:\d+", src) or not r.verses:
            continue
        stats["references"] += 1
        quote = quote_near(text, r, refs)
        ex = B.exists(r)
        if ex is None:
            continue
        if ex is False:
            kind = "missing"
        elif quote and not fits_here(quote, r):
            kind = "mismatch"
        else:
            continue
        cands = candidates(r, quote)
        if kind == "mismatch" and psalm_numbering(r, cands):
            stats["Psalm verse numbered Calmet's way"] += 1
            continue
        fix = None
        if quote and cands and cands[0][2] and cands[0][2] >= 0.6 and (len(cands) == 1 or cands[1][2] < cands[0][2]):
            fix = cands[0][0]  # the quotation is that verse, and no other candidate fits as well
        items.append(dict(where=where, field=field, kind=kind, ref=r.render(), written=src.strip(),
                          context=text[max(0, r.start - 160):r.end + 120], quote=quote,
                          vulgate=B.vulgate_text(r)[:200] if ex else "", candidates=cands[:6], fix=fix))


def apply_fixes(items):
    """Each settled reference written in place of the one Calmet printed (only where that is the field's
    only occurrence of it, so the right one changes)."""
    done = 0
    for x in items:
        if not x["fix"] or x["kind"] == "numbering":
            continue
        vol, stem = x["where"].split("/")
        p = DATA / vol / "normalized" / f"{stem}.json"
        raw = p.read_text(encoding="utf-8")
        d = json.loads(raw)
        i, field = re.fullmatch(r"commentary\[(\d+)\]\.(\w+)", x["field"]).groups()
        b = d["commentary"][int(i)]
        if b.get(field, "").count(x["written"]) != 1:
            print(f"  left: {x['where']} {x['written']!r} (not once in the field)")
            continue
        b[field] = b[field].replace(x["written"], x["fix"])
        p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + ("\n" if raw.endswith("\n") else ""), encoding="utf-8")
        done += 1
    print(f"{done} references set right")


def main(argv):
    apply = "--apply" in argv
    argv = [a for a in argv if not a.startswith("--")]
    vols = volumes_of(argv)
    if not vols:
        sys.exit(__doc__)
    items, stats = [], Counter()
    for vol in vols:
        for p in pages(vol):
            d = json.loads(p.read_text(encoding="utf-8"))
            for i, b in enumerate(d.get("commentary") or []):
                for field in ("french_commentary", "french_translation"):
                    t = b.get(field)
                    if isinstance(t, str) and t:
                        check_text(f"{vol}/{p.stem}", f"commentary[{i}].{field}", t, items, stats)
    vc = DOCS / "vulgate_check.json"
    if vc.exists():
        for x in json.loads(vc.read_text(encoding="utf-8"))["items"]:
            vol = x["where"].split("/")[0]
            if x["kind"] == "numbering" and vol in vols and "psaumes" not in vol:
                items.append(dict(where=x["where"], field="verse", kind="numbering", ref=x["ref"],
                                  written=x["ref"], context=x["latin"], quote=x["latin"],
                                  vulgate=x["vulgate"], candidates=[(x["vulgate_ref"], x["vulgate"][:200], None)], fix=None))
    stats.update(Counter(x["kind"] for x in items))
    stats["settled by the quotation"] = sum(1 for x in items if x["fix"])
    OUT.write_text(json.dumps(dict(stats=dict(stats), items=items), ensure_ascii=False, indent=1), encoding="utf-8")
    print(dict(stats), "->", OUT.relative_to(DOCS.parent))
    if apply:
        apply_fixes(items)


if __name__ == "__main__":
    main(sys.argv[1:])
