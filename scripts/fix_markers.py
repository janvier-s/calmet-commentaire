"""Mechanical clean-up of footnote markers and of JÉSUS-CHRIST in normalized/.

  - footnote calls in the text: "^{ (a)}", "^{ (a) }", "^{{a}", "^(a)", "^((a))" -> "^{(a)}"
  - a bare "(b)" in the text becomes "^{(b)}" when the page has a footnote (b)
  - footnote "marker" fields: missing, bare "a", non-standard -> "(a)"
  - footnote object schema: standardizes {marker, text, tags} and removes temporary keys
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
CALL = re.compile(r"\^\s*\{\s*[({]?\s*_?\s*([a-z])\s*_?\s*[)}]?\s*\}|\^\s*\(\(?\s*([a-z])\s*\)?\)")
BARE = re.compile(r"(?<![\^{\w])\(\s?([a-z])\s?\)(?!\})")
JC = re.compile(r"J[ÉE]SUS-CHRIST")

ALT_MARKER_KEYS = [
    "footnote_marker", "footnote_symbol", "footnote_ref",
    "reference_marker", "reference_symbol", "fn_ref", "ref", "reference"
]

ALT_ID_KEYS = [
    "footnote_id", "id", "footnote_number", "fn_number",
    "reference_id", "reference_number"
]

DEPRECATED_KEYS = set(ALT_MARKER_KEYS + ALT_ID_KEYS + ["footnote_text"])


def extract_letter(val):
    if not val:
        return None
    val = str(val).strip()
    m = re.search(r"([a-zA-Z])", val)
    if m:
        return m.group(1).lower()
    return None


def extract_text_prefix(text):
    if not text:
        return None, text
    text = str(text).strip()
    m = re.match(r"^(\^?\{\(?([a-zA-Z])\)?\}|\(?([a-zA-Z])\)|([a-zA-Z])\))\s*", text)
    if m:
        letter = (m.group(2) or m.group(3) or m.group(4)).lower()
        cleaned = text[m.end():].strip()
        return letter, cleaned
    return None, text


def fix_footnotes(d, stats):
    raw_fns = d.get("footnotes")
    if raw_fns is None:
        return
    fns = [fn for fn in raw_fns if fn]
    if len(fns) != len(raw_fns):
        stats["removed empty fn dict"] += len(raw_fns) - len(fns)
        d["footnotes"] = fns
    if not fns:
        return

    calls = re.findall(
        r"\^\{\(([a-z0-9]+)\)\}",
        json.dumps({k: v for k, v in d.items() if k != "footnotes"}, ensure_ascii=False)
    )

    merged_fns = []
    for idx, fn in enumerate(fns):
        has_m = fn.get("marker") or any(fn.get(k) for k in ALT_MARKER_KEYS)
        tx = fn.get("text") or fn.get("footnote_text") or ""
        has_pref = bool(re.match(r"^(\^?\{\(?([a-zA-Z])\)?\}|\(([a-zA-Z])\))\s*", tx))
        has_letter_id = False
        for k in ALT_ID_KEYS:
            if fn.get(k) and extract_letter(fn[k]):
                has_letter_id = True
                break

        if not has_m and not has_pref and not has_letter_id and len(fns) > len(calls) and merged_fns:
            if tx[:1].islower() or re.match(r"^(?:[0-9]+[.,]|_?[A-Z][a-z]|V\.\s*\d|[.,;:?!\)])", tx) or tx.startswith("28.") or tx.startswith("V. 13") or tx.startswith("Τὰ") or tx.startswith("[ILLEGIBLE]"):
                prev = merged_fns[-1]
                prev_tx = prev.get("text") or prev.get("footnote_text") or ""
                sep = " " if not prev_tx.endswith(" ") else ""
                prev["text"] = prev_tx + sep + tx
                stats["merged continuation footnote"] += 1
                continue
        merged_fns.append(fn)

    fns = merged_fns
    d["footnotes"] = fns

    for idx, fn in enumerate(fns):
        if "footnote_text" in fn:
            if "text" not in fn:
                fn["text"] = fn.pop("footnote_text")
            else:
                fn.pop("footnote_text")
            stats["footnote_text to text"] += 1

        m = fn.get("marker")
        letter = None

        if m and (re.match(r"^\([a-z]\)$", str(m)) or m == "(&)"):
            letter = m.strip("()")
        elif m:
            letter = extract_letter(m)
            if letter:
                stats["footnote marker field"] += 1

        if not letter:
            for k in ALT_MARKER_KEYS:
                if k in fn and fn[k]:
                    letter = extract_letter(fn[k])
                    if letter:
                        stats["footnote_ref to marker"] += 1
                        break

        tx = fn.get("text", "")
        cand_letter, cleaned_tx = extract_text_prefix(tx)
        if not letter and cand_letter:
            letter = cand_letter
            fn["text"] = cleaned_tx
            stats["marker extracted from text"] += 1
        elif letter and cand_letter == letter:
            fn["text"] = cleaned_tx
            stats["redundant text prefix stripped"] += 1

        if not letter:
            for k in ALT_ID_KEYS:
                if k in fn and fn[k] is not None:
                    v = fn[k]
                    if isinstance(v, str):
                        letter = extract_letter(v)
                    elif isinstance(v, int):
                        if idx < len(calls) and re.match(r"^[a-z]$", calls[idx]):
                            letter = calls[idx]
                        elif 1 <= v <= 26:
                            letter = chr(ord("a") + v - 1)
                    if letter:
                        stats["id to marker"] += 1
                        break

        if not letter and idx < len(calls) and re.match(r"^[a-z]$", calls[idx]):
            letter = calls[idx]
            stats["call at index used"] += 1

        if not letter:
            letter = chr(ord("a") + idx)
            stats["fallback index used"] += 1

        target_marker = f"({letter})"
        if fn.get("marker") != target_marker:
            fn["marker"] = target_marker
            stats["marker assigned"] += 1

        for k in DEPRECATED_KEYS:
            if k in fn:
                del fn[k]
                stats["deprecated key removed"] += 1

        if "tags" not in fn:
            fn["tags"] = []
            stats["added empty tags"] += 1

    def footnote_sort_key(fn):
        m = fn.get("marker") or ""
        clean = re.sub(r"[^a-z0-9&]", "", str(m).lower())
        if clean == "&":
            return (1, "z~")
        return (0, clean)

    orig_order = [fn.get("marker") for fn in fns]
    fns.sort(key=footnote_sort_key)
    if [fn.get("marker") for fn in fns] != orig_order:
        stats["footnotes sorted"] += 1


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
            fix_footnotes(d, stats)
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
