"""Field clean-ups decided during the review of volumes 1-21, in one pass.

  - verses: no underscores in `latin` or `french` (the site styles verses itself)
  - french_translation: no underscores (the site sets the whole translation in italic)
  - chapter_summary: no underscores
  - latin_quote: no underscores; "etc." in capitals like the rest of the lemma ("…EJUS, ETC.")
  - french_commentary starting with punctuation ("; c'est-à-dire…"): the punctuation goes to
    the end of the block's french_translation (replacing a final full stop or comma there)
  - annotations: [] / "[]" / "" and bare verse marks (℣. 1., †., *.) -> null;
    a bare year ("2949.") -> "An du M. 2949."
  - french_commentary: blank lines (\\n\\n) -> a single \\n (one \\n = one paragraph on the site),
    none at the end of a block
  - footnote text: no footnote calls (^{(a)}: the note's own call repeated, or one left by the OCR);
    other superscripts written on the line (H^{ieros} -> Hieros); a note set in italic as a whole
    (_Genèse 3:5._) loses the underscores, so footnotes.py can write its references out
  - every text field (footnotes too): no spaces or line breaks at either end, no spaces around a line break
Changed French is added to the LLM cache, so llm_modernize.py won't send it again
(don't run this while llm_modernize.py is running: it rewrites the cache when it finishes).

Years out of step with the dates around them (a misread 1989 among 2989s) are only
reported: fix them by hand after checking the scan or the neighbours.

Usage: python3 tidy_fields.py [--dry-run] [volume ...]   (default: every volume)
"""
import hashlib
import json
import re
import statistics
import sys

from paths import DATA, LLM_CACHE, pages

LEAD = re.compile(r"\s*([.,;:!?»]+)[ \t\u00a0]*")
MARK = re.compile(r"(℣|†|\*)\.?\s*(\d+\.?)?")
YEAR = re.compile(r"\d{3,4}\.?")
DATED = re.compile(r"An\.? du M(?:\.|onde)\s*(\d{4})")
EMBEDDED_LEMMA = re.compile(
    r"^\s*_?([A-ZÀÂÆÇÉÈÊËÎÏÔŒÙÛÜŸ][A-ZÀÂÆÇÉÈÊËÎÏÔŒÙÛÜŸ\s,.;:?!'\’\-()&]+?(?:\s*,?\s*(?:etc|ETC)\.?)?[.,;:?!]?)_?\s+"
    r"_([^_]+?)_([.,;:?!])?"
    r"(?:\s+(.+))?$",
    re.DOTALL,
)
WRAPPED = re.compile(r"^\s*_([^_]+)_([.,;:]?)\s*$")    # the whole note one italic span

def strip_us(s):
    return re.sub(r"[ \t]{2,}", " ", s.replace("_", "")).strip()


def tidy(d, cache, stats):
    changed = False
    for v in d.get("verses") or []:
        for k in ("latin", "french"):
            t = v.get(k)
            if isinstance(t, str) and "_" in t:
                v[k] = strip_us(t)
                if k == "french":
                    cache[hashlib.md5(v[k].encode()).hexdigest()] = v[k]
                stats[f"verse {k} underscores"] += 1
                changed = True
        a = v.get("annotations")
        if a in ([], "[]") or (isinstance(a, str) and (not a.strip() or MARK.fullmatch(a.strip()))):
            v["annotations"] = None
            stats["annotations cleared"] += 1
            changed = True
        elif isinstance(a, str) and YEAR.fullmatch(a.strip()):
            v["annotations"] = "An du M. " + a.strip()
            stats["bare years dated"] += 1
            changed = True
    t = d.get("chapter_summary")
    if isinstance(t, str) and "_" in t:
        d["chapter_summary"] = strip_us(t)
        stats["summary underscores"] += 1
        changed = True
    for b_idx, b in enumerate(d.get("commentary") or []):
        if b_idx > 0 and not (b.get("latin_quote") or "").strip() and not (b.get("french_translation") or "").strip():
            m = EMBEDDED_LEMMA.match(b.get("french_commentary") or "")
            if m:
                b["latin_quote"] = strip_us(m.group(1))
                b["french_translation"] = strip_us(m.group(2) + (m.group(3) or ""))
                b["french_commentary"] = (m.group(4) or "").strip() or None
                for x in (b["french_translation"], b["french_commentary"]):
                    if x:
                        cache[hashlib.md5(x.encode()).hexdigest()] = x
                stats["embedded lemma extracted"] += 1
                changed = True
        t = b.get("latin_quote")
        if isinstance(t, str):
            if "_" in t:
                t = strip_us(t)
                b["latin_quote"] = t
                stats["lemma underscores"] += 1
                changed = True
            new = re.sub(r"(?i)\betc+\b", "ETC", t)
            if new != t:
                b["latin_quote"] = new
                stats["lemma etc"] += 1
                changed = True
        t = b.get("french_translation")
        if isinstance(t, str) and "_" in t:
            b["french_translation"] = strip_us(t)
            cache[hashlib.md5(b["french_translation"].encode()).hexdigest()] = b["french_translation"]
            stats["translation underscores"] += 1
            changed = True
        t, tr = b.get("french_commentary"), (b.get("french_translation") or "").strip()
        m = LEAD.match(t or "")
        if m and tr:
            tr = re.sub(r"(?<!etc)[.,;:]$", "", tr).rstrip()
            mark = m.group(1)
            b["french_translation"] = tr + (" " if mark[0] in ";:!?" else "") + mark
            b["french_commentary"] = t = t[m.end():]
            for x in (b["french_translation"], t):
                cache[hashlib.md5(x.encode()).hexdigest()] = x
            stats["leading punctuation moved"] += 1
            changed = True
        if isinstance(t, str) and ("\n\n" in t or t != t.rstrip()):
            new = re.sub(r"\n(?:[ \t ]*\n)+", "\n", t).rstrip()
            if new != t:
                b["french_commentary"] = new
                cache[hashlib.md5(new.encode()).hexdigest()] = new
                stats["blank lines"] += 1
                changed = True
    for f in d.get("footnotes") or []:
        t = f.get("text")
        if isinstance(t, str) and "^{" in t:
            new = re.sub(r"[ \t]*\^\{\(?(?:[a-z]|\d+)\)?\}[ \t]*", " ", t)
            new = re.sub(r"\^\{(\w+)\}", r"\1", new)
            new = re.sub(r" ?\n ?", "\n", re.sub(r" ([.,])", r"\1", new)).strip()
            if new != t:
                f["text"] = new
                stats["calls in footnotes"] += 1
                changed = True
        t = f.get("text")
        m = WRAPPED.match(t) if isinstance(t, str) else None
        if m:
            f["text"] = m.group(1).strip() + m.group(2)
            stats["footnotes unwrapped"] += 1
            changed = True
    if trim(d, cache, stats):
        changed = True
    return changed


def trim(o, cache, stats):
    """Leading and trailing spaces and line breaks off every string in the page."""
    changed = False
    for k, v in (o.items() if isinstance(o, dict) else enumerate(o)):
        if isinstance(v, (dict, list)):
            changed |= trim(v, cache, stats)
        elif isinstance(v, str):
            new = re.sub(r"[ \t\u00a0]*\n[ \t\u00a0]*", "\n", v).strip()
            if new != v:
                o[k] = new
                if k in ("french", "french_translation", "french_commentary", "chapter_summary"):
                    cache[hashlib.md5(new.encode()).hexdigest()] = new
                stats["spaces at the ends"] += 1
                changed = True
    return changed


def odd_years(volume):
    """Dates far from the median of the 6 dates around them."""
    seq = []
    for p in pages(volume):
        for v in json.loads(p.read_text(encoding="utf-8")).get("verses") or []:
            m = DATED.search(str(v.get("annotations") or ""))
            if m:
                seq.append((p.stem, int(m.group(1)), v["annotations"]))
    out = []
    for i, (stem, y, a) in enumerate(seq):
        around = [s[1] for s in seq[max(0, i - 3):i] + seq[i + 1:i + 4]]
        if len(around) >= 3 and abs(y - statistics.median(around)) > 100:
            out.append(f"{volume}/{stem}: “{a}” among {around}")
    return out


def main(argv):
    dry = "--dry-run" in argv
    vols = [a for a in argv if not a.startswith("--")] or sorted(p.parent.name for p in DATA.glob("*/normalized"))
    cache = json.loads(LLM_CACHE.read_text(encoding="utf-8")) if LLM_CACHE.exists() else {}
    from collections import Counter
    stats, npages = Counter(), 0
    for vol in vols:
        for p in pages(vol):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if tidy(d, cache, stats):
                npages += 1
                if not dry:
                    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    if not dry:
        LLM_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    print(dict(stats), f"on {npages} pages", "(dry run)" if dry else "")
    odd = [o for vol in vols for o in odd_years(vol)]
    if odd:
        print("Years to check (not changed):")
        print("\n".join("  " + o for o in odd))


if __name__ == "__main__":
    main(sys.argv[1:])
