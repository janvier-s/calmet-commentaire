"""Correct verse_ref from the Vulgate: find which verse each lemma quotes.

A lemma (latin_quote) is matched against the Vulgate verses of its chapter (and the
chapters either side, since a page can straddle two). When the match is certain and
the current verse_ref breaks the order of its neighbours while the matched verse fits
between them, verse_ref is replaced, and so are the lemma-less continuation blocks
after it that carried the same wrong number. Typical cases: a misread number
(24 for 14), or the previous chapter's last verse carried onto a new chapter's first
note.

Usage: python3 fix_refs_vulgate.py [--dry-run] [book key ...]   (default: published books)
`match_verse` is also used by audit_integrity.py to list the mismatches left over.
"""
import json
import re
import sys
import unicodedata
from functools import lru_cache

from export import chapter_of
from paths import BOOKS, VUL, WEB, load, pages


def words(s):
    s = unicodedata.normalize("NFKD", (s or "").lower()).encode("ascii", "ignore").decode()
    s = s.replace("j", "i").replace("v", "u").replace("ae", "e").replace("oe", "e")
    return [w for w in re.findall(r"[a-z]+", s) if w != "etc"]


@lru_cache(maxsize=None)
def vulgate(vul):
    return {c["chapter"]: {v["verse"]: v["text"] for v in c["verses"]}
            for c in json.loads((VUL / f"{vul}.json").read_text())["chapters"]}


@lru_cache(maxsize=None)
def verse_words(vul, ch):
    return {n: (set(w), " ".join(w)) for n, t in vulgate(vul).get(ch, {}).items() for w in [words(t)]}


def candidates(vul, chapters, lemma):
    """The (chapter, verse) pairs the lemma may quote: a strong match and its near ties."""
    lw = words(lemma)
    if len(lw) < 2:
        return []
    scores = []
    for ch in chapters:
        for n, (vs, joined) in verse_words(vul, ch).items():
            hit = sum(w in vs for w in lw) / len(lw)
            scores.append((hit + (0.5 if " ".join(lw[:3]) in joined else 0), ch, n))
    scores.sort(reverse=True)
    if not scores or scores[0][0] < 1.2:
        return []
    return list(dict.fromkeys(s[1:] for s in scores if s[0] > scores[0][0] - 0.3))


def match_verse(vul, chapters, lemma):
    """(chapter, verse) the lemma quotes, or None when it isn't certain."""
    c = candidates(vul, chapters, lemma)
    return c[0] if len(c) == 1 else None


def ref_num(c):
    m = re.match(r"\d+", str(c.get("verse_ref") or ""))
    return int(m.group()) if m else None


def blocks(key):
    """Every commentary block of the book in order: (page path, page, block, chapter guess)."""
    out, cur = [], None
    for vol in BOOKS[key]["studium"]:
        for p in pages(vol):
            try:
                d = load(p)
            except json.JSONDecodeError:
                continue
            cur = chapter_of(d) or cur
            for c in d.get("commentary") or []:
                out.append((p, d, c, cur))
    return out


def corrections(key):
    """[(path, page, block, old, new, lemma)] for one book.

    Neighbours are judged only by "anchors": notes of the same chapter whose verse_ref
    the Vulgate confirms. Notes carrying the same wrong number would vouch for each other.
    """
    vul = BOOKS[key]["vul"]
    bl = blocks(key)
    lemmas = [i for i, (_, _, c, _) in enumerate(bl) if (c.get("latin_quote") or "").strip() and ref_num(c)]
    cands = {}
    for i in lemmas:
        ch = bl[i][3]
        if ch:
            cands[i] = candidates(vul, tuple(x for x in (ch - 1, ch, ch + 1) if x > 0), bl[i][2]["latin_quote"])
    found = {i: c[0] for i, c in cands.items() if len(c) == 1}
    anchors = [i for i in lemmas if found.get(i) and found[i][1] == ref_num(bl[i][2])]

    def bounds(i, chapter):
        prev = max((found[a][1] for a in anchors if a < i and found[a][0] == chapter), default=0)
        nxt = min((found[a][1] for a in anchors if a > i and found[a][0] == chapter), default=999)
        return prev, nxt

    out = []
    for i in lemmas:
        p, d, c, _ = bl[i]
        ref = ref_num(c)
        # near ties (e.g. a phrase repeated in the chapter) are settled by the anchors
        cs = cands.get(i, [])
        if len({m[0] for m in cs}) > 1:  # a formula found in several chapters ("fecit quod erat placitum…")
            continue
        fitting = [m for m in cs if bounds(i, m[0])[0] <= m[1] <= bounds(i, m[0])[1]]
        if len(fitting) != 1 or fitting[0][1] == ref or any(m[1] == ref for m in cands[i]):
            continue
        m = fitting[0]
        prev, nxt = bounds(i, m[0])
        if not prev <= ref <= nxt:
            out.append((p, d, c, ref, m[1], c["latin_quote"]))
            # continuation blocks that carried the same wrong number
            for p2, d2, c2, _ in bl[i + 1:]:
                if (c2.get("latin_quote") or "").strip() or ref_num(c2) != ref:
                    break
                out.append((p2, d2, c2, ref, m[1], None))
    return out


def main(argv):
    dry = "--dry-run" in argv
    keys = [a for a in argv if not a.startswith("--")] or [
        k for k, b in BOOKS.items() if (WEB / "calmet" / b["site"]).is_dir()]
    total, touched = 0, {}
    for key in keys:
        fixes = corrections(key)
        for p, d, c, old, new, lemma in fixes:
            if lemma:
                print(f"{p.parent.parent.name}/{p.stem}: {old} -> {new}  {lemma[:60]}")
            r = str(c["verse_ref"])
            c["verse_ref"] = str(new) + (r[r.index("-"):] if "-" in r and int(r.split("-")[1]) > new else "")
            touched[p] = d
        total += sum(1 for f in fixes if f[5])
    if not dry:
        for p, d in touched.items():
            p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{total} notes {'would be' if dry else ''} corrected on {len(touched)} pages")


if __name__ == "__main__":
    main(sys.argv[1:])
