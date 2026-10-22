"""Mechanical cleanups for common OCR and formatting artifacts.

1. Spaced letters: "J E S U S", "C H R I S T", "J E S U S - C H R I S T" -> "Jésus", "Christ", "Jésus-Christ"
2. Disentangle lemmata and translations merged into french_commentary when latin_quote is missing.
3. Fix leading footnote calls inside fields.

Usage: python3 clean_mechanical.py [--dry-run] [volume ...]
"""
import json
import re
import sys
from pathlib import Path

from paths import DATA, pages

JC_RE = re.compile(r"J\s+E\s+S\s+U\s+S(?:\s*-\s*|\s+)C\s+H\s+R\s+I\s+S\s+T")
J_RE = re.compile(r"\bJ\s+E\s+S\s+U\s+S\b")
C_RE = re.compile(r"\bC\s+H\s+R\s+I\s+S\s+T\b")

# Regex to detect Latin lemmata at start of french_commentary
# e.g., "FILII DAVID, FILII ABRAHAM. Fils de David, fils d'Abraham. L'Evangéliste..."
# or "⁼⁾. 23. ECCE VIRGO IN UTERO HABEBIT, etc. Une Vierge concevra... "
PREFIX_JUNK = re.compile(r"^\s*(?:[⁼⁾ⁱ∗∬\u200b†*℣]\s*\.?\s*|\d+\.\s*)+")
LEMMA_PATTERN = re.compile(
    r"^([A-ZÆŒ\s,;:'’\-]{4,}(?:ETC\.?|etc\.?)?)\.\s+([A-ZÀ-Ÿ][^.\n]+[.:?!])\s+(.+)$",
    re.DOTALL
)


def fix_spaced_letters(s):
    if not s:
        return s
    s = JC_RE.sub("Jésus-Christ", s)
    s = J_RE.sub("Jésus", s)
    s = C_RE.sub("Christ", s)
    return s


def clean_page(d):
    changed = False
    for c in d.get("commentary", []):
        # 1. Spaced letters
        for k in ("french_translation", "french_commentary"):
            s = c.get(k)
            if s:
                s2 = fix_spaced_letters(s)
                if s2 != s:
                    c[k] = s2
                    changed = True

        # 2. Extract missing lemma/translation if merged into french_commentary
        if not c.get("latin_quote") and c.get("french_commentary"):
            raw_fc = c["french_commentary"].strip()
            # Strip junk prefixes like "⁼⁾. 23." or "ⁱ. 12."
            stripped = PREFIX_JUNK.sub("", raw_fc).strip()
            m = LEMMA_PATTERN.match(stripped)
            if m:
                cand_lemma, cand_trans, rest_comm = m.group(1).strip() + ".", m.group(2).strip(), m.group(3).strip()
                # Check that cand_lemma looks like Latin and cand_trans looks like French
                if len(cand_lemma) >= 5 and re.search(r"[A-Z]{3,}", cand_lemma):
                    c["latin_quote"] = cand_lemma
                    if not c.get("french_translation"):
                        c["french_translation"] = cand_trans
                    c["french_commentary"] = rest_comm
                    changed = True

        # 3. Leading call in latin_quote or french_commentary
        fc = c.get("french_commentary")
        if fc:
            m = re.match(r"^\s*(\^\{[^}]+\})\s*", fc)
            if m:
                # If french_translation exists, move it to end of french_translation
                call_str = m.group(1)
                c["french_commentary"] = fc[m.end():]
                tr = c.get("french_translation")
                if tr and call_str not in tr:
                    c["french_translation"] = tr.rstrip() + " " + call_str
                changed = True

    return changed


def main(argv):
    dry = "--dry-run" in argv
    vols = [a for a in argv if not a.startswith("--")] or sorted(
        p.name for p in DATA.iterdir() if (p / "normalized").is_dir()
    )

    total_changed = 0
    for vol in vols:
        vol_changed = 0
        for p in pages(vol):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if clean_page(d):
                vol_changed += 1
                if not dry:
                    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        total_changed += vol_changed
        print(f"{vol}: {vol_changed} pages updated{' (dry run)' if dry else ''}")

    print(f"Total: {total_changed} pages updated")


if __name__ == "__main__":
    main(sys.argv[1:])
