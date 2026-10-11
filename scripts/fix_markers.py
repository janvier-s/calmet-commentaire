"""Mechanical clean-up of footnote markers and of JÉSUS-CHRIST in normalized/.

  - footnote calls in the text: "^{ (a)}", "^{ (a) }", "^{{a}", "^(a)", "^((a))" -> "^{(a)}"
  - a bare "(b)" in the text becomes "^{(b)}" when the page has a footnote (b)
  - footnote "marker" fields: "( a )" -> "(a)"
  - "JESUS-CHRIST" / "JÉSUS-CHRIST" in the French -> "Jésus-Christ"

Changed French is added to the LLM cache, so llm_modernize.py won't resend it.
Usage: python3 fix_markers.py [--dry-run] [volume ...]   (default: every volume)
"""
import hashlib
import json
import re
import sys
from collections import Counter

from paths import DATA, LLM_CACHE, pages

FRENCH = {"french", "french_translation", "french_commentary", "chapter_summary"}
CALL = re.compile(r"\^\s*\{\s*[({]?\s*([a-z])\s*[)}]?\s*\}|\^\s*\(\(?\s*([a-z])\s*\)?\)")
BARE = re.compile(r"(?<![\^{\w])\(\s?([a-z])\s?\)(?!\})")
JC = re.compile(r"J[ÉE]SUS-CHRIST")


def fix_text(t, notes, stats):
    def call(m):
        stats["marker"] += 1
        return "^{(" + (m.group(1) or m.group(2)) + ")}"
    t2 = CALL.sub(lambda m: m.group() if re.fullmatch(r"\^\{\([a-z]\)\}", m.group()) else call(m), t)

    def bare(m):
        if m.group(1) not in notes:
            return m.group()
        stats["bare marker"] += 1
        return "^{(" + m.group(1) + ")}"
    t2 = BARE.sub(bare, t2)
    return t2


def main(argv):
    dry = "--dry-run" in argv
    vols = [a for a in argv if not a.startswith("--")] or sorted(p.parent.name for p in DATA.glob("*/normalized"))
    cache = json.loads(LLM_CACHE.read_text(encoding="utf-8"))
    stats, changed_pages = Counter(), 0
    for vol in vols:
        for p in pages(vol):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            before = json.dumps(d, ensure_ascii=False)
            for fn in d.get("footnotes") or []:
                m = re.fullmatch(r"\s*\(\s*([a-z])\s*\)\s*", str(fn.get("marker") or ""))
                if m and fn["marker"] != f"({m.group(1)})":
                    fn["marker"] = f"({m.group(1)})"
                    stats["footnote marker field"] += 1
            notes = {re.sub(r"\W", "", str(fn.get("marker") or "")) for fn in d.get("footnotes") or []}

            def walk(node):
                for k, v in (node.items() if isinstance(node, dict) else enumerate(node)):
                    if isinstance(v, (dict, list)):
                        walk(v)
                    elif isinstance(v, str) and k != "marker":
                        t = fix_text(v, notes, stats)
                        if k in FRENCH:
                            t, n = JC.subn("Jésus-Christ", t)
                            stats["Jésus-Christ"] += n
                        if t != v:
                            node[k] = t
                            if k in FRENCH:
                                cache[hashlib.md5(t.encode()).hexdigest()] = t
            walk(d)
            if json.dumps(d, ensure_ascii=False) != before:
                changed_pages += 1
                if not dry:
                    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    if not dry:
        LLM_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    print(dict(stats), f"{changed_pages} pages" + (" would change" if dry else " changed"))


if __name__ == "__main__":
    main(sys.argv[1:])
