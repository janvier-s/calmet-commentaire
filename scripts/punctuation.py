"""French punctuation spacing in the normalized pages, with ordinary spaces only.

  - non-breaking and thin spaces (U+00A0, U+202F, U+2009) -> ordinary spaces: they trip up
    the scripts; export.py puts the non-breaking ones back for the site
  - runs of spaces -> one space (line breaks are kept)
  - a space before ; : ? ! » and after «  ("Domini:" -> "Domini :", "«mot»" -> "« mot »")
    but not in a chapter:verse reference (13:18), not after Greek (; is its question mark),
    not after Hebrew (: is the sof pasuq), not inside ?! or (?)
  - no space before , and .  ("modération , qui" -> "modération, qui")
  - no space inside parentheses  ("( le péché )" -> "(le péché)")
  - a space after , ; : when a letter follows straight on ("Seigneur:Me" -> "Seigneur : Me")
  - curly apostrophe ’ -> straight ' (export.py makes them curly for the site), not next to Greek
  - ... and . . . (and longer runs of dots) -> …
Changed French is added to the LLM cache, so llm_modernize.py won't send it again.

Usage: python3 punctuation.py [--apply] [volume ...]   (dry run by default; every volume)
Changes are listed in reports/punctuation_changes.tsv.
"""
import hashlib
import json
import re
import sys
from collections import Counter

from paths import DATA, LLM_CACHE, pages

TEXT = {"latin", "french", "annotations", "chapter_summary", "chapter_intro", "chapter_argument",
        "chapter_title", "book_title", "latin_quote", "french_translation", "french_commentary",
        "text", "book_end_marker"}
FRENCH = {"french", "french_translation", "french_commentary", "chapter_summary"}
GREEK_HEBREW = "\u0370-\u03ff\u1f00-\u1fff\u0590-\u05ff\ufb1d-\ufb4f"

RULES = [
    ("non-breaking space", re.compile(r"[\u00a0\u202f\u2009]"), " "),
    ("straight apostrophe", re.compile(rf"(?<![{GREEK_HEBREW}])’(?![{GREEK_HEBREW}])"), "'"),
    ("ellipsis", re.compile(r"(?!…(?! ?[.…]))\.*(?:\.(?: ?\.){2,}|…)(?: ?(?:\.(?: ?\.){2,}|…))*"), "…"),
    ("space after , ; :", re.compile(r"(?<=[a-zà-ÿ_)])([,;]|:(?!\d))(?=[A-Za-zÀ-ÿ])"), r"\1 "),
    ("space before ; : ? ! »", re.compile(
        rf"(?<=[^\s({{\[«?!{GREEK_HEBREW}])([;?!»]|:(?!\d))"), r" \1"),
    ("space after «", re.compile(r"«(?=\S)"), "« "),
    ("space before , .", re.compile(r"(?<=\S) +(,|\.(?!\.|\d))"), r"\1"),
    ("space inside ( )", re.compile(r"\( +| +\)"), lambda m: m.group().strip()),
    ("double space", re.compile(r"(?<=\S) {2,}"), " "),
]


def clean(s, stats, log=None, where=""):
    for name, rx, rep in RULES:
        if log is not None and name != "non-breaking space":
            log += [f"{where}\t{name}\t{s[max(0, m.start() - 20):m.end() + 10]!r}" for m in rx.finditer(s)]
        s, n = rx.subn(rep, s)
        stats[name] += n
    return s


def clean_page(d):
    """The same rules on one page, for the editors' save (no log, no cache)."""
    return walk(d, None, {}, Counter(), None, "")


def walk(o, key, cache, stats, log, where):
    if isinstance(o, dict):
        return {k: walk(v, k, cache, stats, log, where) for k, v in o.items()}
    if isinstance(o, list):
        return [walk(v, key, cache, stats, log, where) for v in o]
    if isinstance(o, str) and key in TEXT:
        new = clean(o, stats, log, f"{where}\t{key}")
        if new != o:
            if key in FRENCH:
                cache[hashlib.md5(new.encode()).hexdigest()] = new
        return new
    return o


def main(argv):
    apply = "--apply" in argv
    vols = [a for a in argv if not a.startswith("--")] or sorted(p.parent.name for p in DATA.glob("*/normalized"))
    cache = json.loads(LLM_CACHE.read_text(encoding="utf-8")) if LLM_CACHE.exists() else {}
    stats, log, npages = Counter(), [], 0
    for vol in vols:
        for p in pages(vol):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            new = walk(d, None, cache, stats, log, f"{vol}/{p.stem}")
            if new != d:
                npages += 1
                if apply:
                    p.write_text(json.dumps(new, ensure_ascii=False, indent=2), encoding="utf-8")
    if apply:
        LLM_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    out = DATA.parent / "reports" / "punctuation_changes.tsv"
    out.parent.mkdir(exist_ok=True)
    out.write_text("page\tfield\trule\tbefore\n" + "\n".join(log), encoding="utf-8")
    print(dict(stats), f"on {npages} pages", "" if apply else "(dry run)", f"\nlisted in {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
