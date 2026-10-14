"""Field clean-ups decided during the review of volumes 1-21, in one pass.

  - verses: no underscores in `latin` or `french` (the site styles verses itself)
  - french_translation: underscores removed where they only wrap the whole translation
    (the site sets it in italic); partial italics ("_Il sera votre bouche_ ; vous…") are kept
  - annotations: [] / "[]" / "" and bare verse marks (℣. 1., †., *.) -> null;
    a bare year ("2949.") -> "An du M. 2949."
  - french_commentary: blank lines (\\n\\n) -> a single \\n (one \\n = one paragraph on the site),
    none at the end of a block
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

WHOLE = re.compile(r"\s*_([^_]*)_?\s*([.,;:]?)\s*|\s*_?([^_]*)_\s*")
MARK = re.compile(r"(℣|†|\*)\.?\s*(\d+\.?)?")
YEAR = re.compile(r"\d{3,4}\.?")
DATED = re.compile(r"An\.? du M(?:\.|onde)\s*(\d{4})")


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
    for b in d.get("commentary") or []:
        t = b.get("french_translation")
        if isinstance(t, str) and "_" in t and WHOLE.fullmatch(t):
            b["french_translation"] = t.replace("_", "").strip()
            cache[hashlib.md5(b["french_translation"].encode()).hexdigest()] = b["french_translation"]
            stats["translations unwrapped"] += 1
            changed = True
        t = b.get("french_commentary")
        if isinstance(t, str) and ("\n\n" in t or t != t.rstrip()):
            new = re.sub(r"\n(?:[ \t ]*\n)+", "\n", t).rstrip()
            if new != t:
                b["french_commentary"] = new
                cache[hashlib.md5(new.encode()).hexdigest()] = new
                stats["blank lines"] += 1
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
