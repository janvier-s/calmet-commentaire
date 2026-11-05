"""The Hebrew and Greek of the notes: normalized's, Good's (as Flash read it) and the right text.

    python3 good_notes_quotes.py <vol> <chapter>[-<chapter>] [--out FILE]

The aim is the correct text, not the printed one: a Hebrew quotation is set against the Masoretic text
(Open Scriptures), a Septuagint one ("70.") against the Septuagint, each searched in the chapter and the
ones beside it. For each Hebrew or Greek note good_notes.py pairs on Good:
  - each run of Hebrew (or Greek) words is looked for in the Bible text, letters only (Hebrew without its
    points, Greek without accents and breathings), word by word;
  - found (most of its words in one verse, in order): the right text is the verse's words over that span
    (Hebrew unpointed; Greek accented as the Septuagint has it); a proposal when normalized differs from it;
  - not found (a root, a rabbinic or classical quotation): a proposal of Good's reading only when Good
    differs from normalized, for review with the crop, never applied by itself.
Each proposal's `new`: the right text, Good's own where it agrees (keeping its vowel points). Kinds:
quote_fix (the Bible text settles it: normalized wrong), quote_good (Good differs, nothing settles it),
quote_points (the same letters, Good's pointed: a low-priority proposal), and quote_both (normalized and Good alike, both off the Bible text: a slip in both printings, or
Calmet's own text).
"""
import difflib
import json
import re
import sys
import unicodedata

import bible_refs as br
import good_notes as gn
import good_variants as gv

HEB_WORD = re.compile(r"[א-ת][֑-ׇא-ת]*")
GRK_WORD = re.compile(r"[Ͱ-Ͽἀ-῿][̀-ͯͰ-Ͽἀ-῿]*")


def pointed(ws):
    return any(re.search(r"[\u05b0-\u05bc\u05c1\u05c2\u05c7]", w) for w in ws)


def heb_plain(w):
    return re.sub(r"[^א-ת]", "", w).translate(str.maketrans("ךםןףץ", "כמנפצ"))


def grk_plain(w):
    t = "".join(c for c in unicodedata.normalize("NFD", w.lower()) if not unicodedata.combining(c))
    return t.replace("ς", "σ").replace("ϲ", "σ")


def runs(text, word):
    """The runs of words in one script, a few Latin words between them not breaking a run:
    [(words, said Septuagint)], a run being the Septuagint's when "70." (or Septante, LXX) stands just before it."""
    out, cur, last, start = [], [], None, 0
    for m in word.finditer(text):
        if cur and re.search(r"[A-Za-z]{2,}|[;:()]", text[last:m.start()]):
            out.append((cur, start)); cur = []
        if not cur:
            start = m.start()
        cur.append(m.group()); last = m.end()
    if cur:
        out.append((cur, start))
    return [(ws, bool(re.search(r"(?:^|[\s.(])70\s*\.|Septante|LXX", text[max(0, st - 14):st]))) for ws, st in out]


def likeness(a, b, plain):
    return difflib.SequenceMatcher(None, " ".join(plain(w) for w in a), " ".join(plain(w) for w in b), autojunk=False).ratio()


def pair_runs(jr, gr, plain, least=0.5):
    """Each JSON run with the likest Good run (one each), when alike enough; else with None."""
    cand = sorted(((likeness(j[0], g[0], plain), ji, gi) for ji, j in enumerate(jr) for gi, g in enumerate(gr)), reverse=True)
    got, used = {}, set()
    for sc, ji, gi in cand:
        if sc >= least and ji not in got and gi not in used:
            got[ji] = gi; used.add(gi)
    return [(j, gr[got[ji]] if ji in got else (None, False)) for ji, j in enumerate(jr)]


def word_errors(quote, right, plain, accented=None):
    """The quote's words that are not the verse's: a word changed or added (a verse word left out, an
    elision, is no error; nor a leading ו, the quote cut out of its verse)."""
    def k(w, i):
        t = plain(w)
        return t[1:] if i == 0 and t.startswith("ו") and len(t) > 2 else t
    q = [k(w, i) for i, w in enumerate(quote)]
    r = [k(w, i) for i, w in enumerate(right)]
    errs = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, q, r, autojunk=False).get_opcodes():
        if tag in ("replace", "delete"):
            errs.append((" ".join(quote[i1:i2]), " ".join(right[j1:j2])))
        elif tag == "equal" and accented:
            for x, y in zip(quote[i1:i2], right[j1:j2]):
                if accented(x) != accented(y) and any(unicodedata.combining(c) for c in unicodedata.normalize("NFD", y)):  # the
                    # Septuagint's text leaves proper names unaccented (Γαδ): no error to read there
                    errs.append((x, y))
    return errs


def book_of(vol):
    return br.ABBR.get(gn.plain(vol.split("_", 1)[1]))


def chapter_of(vol, page, cache={}):
    if vol not in cache:
        m = {}
        for c in range(1, 151):
            try:
                ps = gv.chapter_pages(vol, {c})
            except Exception:
                break
            for p in ps or []:
                m.setdefault(p, c)
        cache[vol] = m
    return cache[vol].get(page)


def verses(vol, ch, greek):
    """[(c, v, words)] of the chapter and the ones beside it."""
    name = book_of(vol)
    vul, oshb, lxx = br.BOOK.get(name, (None, None, None))
    out = []
    if greek:
        d = br.lxx(lxx) if lxx else {}
        for (c, v), t in d.items():
            if ch - 1 <= c <= ch + 1:
                out.append((c, v, GRK_WORD.findall(t)))
    else:
        d = br.hebrew().get(oshb, {})
        for (c, v), ws in d.items():
            if ch - 1 <= c <= ch + 1:
                out.append((c, v, ws))
    return out


def locate(run, vs, plain):
    """The verse span best matching a run: (c, v, words of the span, share of the run's words found)."""
    key = [plain(w) for w in run]
    best = None
    for c, v, ws in vs:
        wk = [plain(w) for w in ws]
        sm = difflib.SequenceMatcher(None, key, wk, autojunk=False)
        blocks = [b for b in sm.get_matching_blocks() if b.size]
        if not blocks:
            continue
        hit = sum(b.size for b in blocks)
        # near words too (a letter off): the span between the first and last matched words
        lo, hi = blocks[0].b - blocks[0].a, blocks[-1].b + blocks[-1].size + (len(key) - blocks[-1].a - blocks[-1].size)
        lo, hi = max(0, lo), min(len(ws), hi)
        near = sum(1 for a, b in zip(key, wk[lo:hi]) if difflib.SequenceMatcher(None, a, b).ratio() >= 0.75)
        share = max(hit, near) / len(key)
        if best is None or share > best[3]:
            best = (c, v, ws[lo:hi], share)
    return best


def grk_accented(w):
    """Lower case, a grave accent as acute (it is the word's place in the sentence, not its spelling)."""
    return unicodedata.normalize("NFC", unicodedata.normalize("NFD", w.lower()).replace("\u0300", "\u0301"))


def same_words(a, b, plain):
    return [plain(w) for w in a] == [plain(w) for w in b]


def check(vol, chs):
    _, hg = gn.compare(vol, chs)
    out = []
    for h in hg:
        ch = chapter_of(vol, h["page"])
        if ch is None:
            continue
        for greek, word, plain in ((False, HEB_WORD, heb_plain), (True, GRK_WORD, grk_plain)):
            jr, gr = runs(h["json_text"], word), runs(h["good_raw"] or "", word)
            if not jr and not gr:
                continue
            vs = verses(vol, ch, greek)
            for (j, j70), (g, g70) in pair_runs(jr, gr, plain):
                loc = locate(j, vs, plain) if len(j) >= 2 else None
                right = loc[2] if loc and loc[3] >= 0.6 else None
                if greek and not (j70 or g70) and not (loc and loc[3] >= 0.75 and len(j) >= 3):
                    right = None  # Greek not said to be, nor plainly, the Septuagint's (Aquila, Symmachus, Homer)
                rec = {"vol": vol, "page": h["page"], "path": h["path"], "script": "greek" if greek else "hebrew",
                       "json": " ".join(j), "good": " ".join(g) if g else None,
                       "pdf": h["pdf"], "pdf_page": h["pdf_page"], "printed": h["printed"], "crop": h["crop"], "boxes": h["boxes"]}
                if right:
                    acc = grk_accented if greek else None
                    errs = word_errors(j, right, plain, acc)
                    if errs:
                        gl = locate(g, vs, plain) if g and len(g) >= 2 else None
                        g_ok = bool(gl and gl[3] >= 0.6 and not word_errors(g, gl[2], plain, acc))
                        rec.update(ref=f"{book_of(vol)} {loc[0]}:{loc[1]}", right=" ".join(right), errors=errs,
                                   kind="quote_fix" if g_ok else "quote_both", good_agrees=g_ok,
                                   new=" ".join(g) if g_ok and g and pointed(g) else " ".join(right))
                        out.append(rec)
                        continue
                if g and not same_words(j, g, plain):
                    if not right:
                        rec.update(kind="quote_good", new=" ".join(g))
                        out.append(rec)
                elif g and not greek and pointed(g) and not pointed(j):
                    rec.update(kind="quote_points", new=" ".join(g))  # the same letters, Good's with their points
                    out.append(rec)
    return out


def main(argv):
    if not argv:
        sys.exit(__doc__)
    vol, spec = argv[0], argv[1]
    a, _, b = spec.partition("-")
    out = check(vol, set(range(int(a), int(b or a) + 1)))
    if "--out" in argv:
        with open(argv[argv.index("--out") + 1], "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=1)
    for r in out:
        print(f"{r['kind']} {r['script']} p{r['page']} {r.get('ref', '')}{' (Good agrees)' if r.get('good_agrees') else ''}")
        print(f"   JSON:  {r['json']}")
        print(f"   GOOD:  {r['good']}")
        if r.get("right"):
            print(f"   RIGHT: {r['right']}")


if __name__ == "__main__":
    main(sys.argv[1:])
