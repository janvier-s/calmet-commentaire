#!/usr/bin/env python3
"""
Cleanup script for normalized JSON files.
Usage: python cleanup_normalized.py 01_genese [--dry-run]

Transformations:
  1. Remove "_" from verses (french & latin)
  2. Remove leading verse numbers ("8. ...") from verses (french & latin)
  3. Remove ℣ prefix from verses ("℣. 8. ...")
  4. Fill null verse_ref in commentary (carry forward from previous commentary/page)
  5. Merge inner italic markers: _Lorem_ [_ipsum_] _sit._ → _Lorem [ipsum] sit._
  6. Fix double capitals on verse 1 latin_quote / french_translation
  7. Replace standalone "S." with "Saint"
  8. Remove "_" from chapter_summary
"""

import json
import re
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def strip_underscores(text):
    """Remove all underscores from text."""
    if not text:
        return text
    return text.replace("_", "")


def strip_verse_prefix(text):
    """Remove leading ℣. N. or just N. from verse text."""
    if not text:
        return text
    # ℣. 27. _text_ or ℣. 11. text
    text = re.sub(r"^℣\.\s*\d+\.\s*", "", text)
    # Leading "12. " at start of verse text
    text = re.sub(r"^\d+\.\s+", "", text)
    return text


def merge_italic_markers(text):
    """
    Merge adjacent italic spans separated by non-italic fragments.
    _Lorem_ [_ipsum_] _sit._ → _Lorem [ipsum] sit._

    Strategy: find sequences like _X_ Y _Z_ and merge into _X Y Z_
    where Y contains no underscores.
    """
    if not text or "_" not in text:
        return text
    # Repeatedly merge _..._<gap>_..._ patterns where gap has no underscores
    # Pattern: closing _ followed by non-underscore text, then opening _
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"_(\s*[\[\]\(\),;:\s]+\s*)_", r"\1", text)
    return text


def fix_double_capitals(text):
    """
    Fix OCR double-capital at start of text.
    "HIs ita..." → "His ita..."
    "OR le Seigneur..." → "Or le Seigneur..."
    Only applies when first 2+ chars are uppercase followed by lowercase.
    Also handles leading _: "_TRaduction" → "_Traduction"
    """
    if not text:
        return text
    # With leading underscore (italic marker)
    m = re.match(r"^(_)([A-Z])([A-Z])([a-z])", text)
    if m:
        return m.group(1) + m.group(2) + m.group(3).lower() + m.group(4) + text[m.end():]
    # Without leading underscore
    m = re.match(r"^([A-Z])([A-Z])([a-zà-ÿ])", text)
    if m:
        return m.group(1) + m.group(2).lower() + m.group(3) + text[m.end():]
    return text


def replace_s_dot(text):
    """Replace standalone 'S.' with 'Saint' (word boundary)."""
    if not text:
        return text
    return re.sub(r"\bS\.\s", "Saint ", text)


def replace_ae_ligature(text):
    """Replace 'AE' with 'Æ' ligature."""
    if not text:
        return text
    return text.replace("AE", "Æ")


def normalize_jesus_christ(text):
    """Normalize various Jesus-Christ spellings to 'Jésus-Christ'."""
    if not text:
        return text
    # Handle spaced-out version: J E S U S - C H R I S T → Jésus-Christ
    text = re.sub(r"J\s+E\s+S\s+U\s+S\s*-\s*C\s+H\s+R\s+I\s+S\s+T", "Jésus-Christ", text, flags=re.IGNORECASE)
    # Handle JESUS-CHRIST (all caps)
    text = re.sub(r"\bJESUS-CHRIST\b", "Jésus-Christ", text)
    # Handle Jesus-Christ (title case)
    text = re.sub(r"\bJesus-Christ\b", "Jésus-Christ", text)
    # Handle Jesus Christ (two words, no hyphen)
    text = re.sub(r"\bJesus\s+Christ\b", "Jésus-Christ", text)
    return text


def process_file(json_path, prev_last_verse_ref, dry_run=False):
    """Process a single normalized JSON file. Returns (changed, new_last_verse_ref)."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    original = json.dumps(data, ensure_ascii=False)
    changes = []

    # --- chapter_summary: remove underscores ---
    if data.get("chapter_summary"):
        new_val = strip_underscores(data["chapter_summary"])
        if new_val != data["chapter_summary"]:
            changes.append(f"  chapter_summary: stripped underscores")
            data["chapter_summary"] = new_val

    # --- verses: clean latin & french ---
    for v in (data.get("verses") or []):
        # Fix double capitals on verse 1 (OCR drop-cap)
        if v.get("verse_number") == 1:
            for field in ("latin", "french"):
                old = v.get(field)
                if old:
                    new_val = fix_double_capitals(old)
                    if new_val != old:
                        changes.append(f"  verse {v.get('verse_number')}.{field}: fixed double caps")
                        v[field] = new_val

        for field in ("latin", "french"):
            old = v.get(field)
            if not old:
                continue
            new_val = old
            new_val = strip_underscores(new_val)
            new_val = strip_verse_prefix(new_val)
            new_val = normalize_jesus_christ(new_val)
            if new_val != old:
                changes.append(f"  verse {v.get('verse_number')}.{field}: cleaned")
                v[field] = new_val

    # --- commentary: fill verse_ref, fix double caps, merge italics, S. → Saint ---
    last_verse_ref = prev_last_verse_ref
    comms = data.get("commentary") or []
    for i, c in enumerate(comms):
        # Fill null verse_ref
        if c.get("verse_ref") is not None:
            last_verse_ref = c["verse_ref"]
        else:
            # Case 1: continuation (commentary_id=1, no latin/french) → use prev page's ref
            # Case 2: has latin_quote & french_translation but null verse_ref → carry forward
            if last_verse_ref is not None:
                changes.append(f"  commentary {c.get('commentary_id')}: verse_ref null → {last_verse_ref}")
                c["verse_ref"] = last_verse_ref

        # Merge inner italic markers in french_translation
        for field in ("french_translation",):
            old = c.get(field)
            if old:
                new_val = merge_italic_markers(old)
                if new_val != old:
                    changes.append(f"  commentary {c.get('commentary_id')}.{field}: merged italics")
                    c[field] = new_val

        # S. → Saint in all text fields
        for field in ("latin_quote", "french_translation", "french_commentary"):
            old = c.get(field)
            if old:
                new_val = replace_s_dot(old)
                new_val = normalize_jesus_christ(new_val)
                if new_val != old:
                    changes.append(f"  commentary {c.get('commentary_id')}.{field}: normalized")
                    c[field] = new_val

        # AE → Æ in latin_quote
        old = c.get("latin_quote")
        if old:
            new_val = replace_ae_ligature(old)
            if new_val != old:
                changes.append(f"  commentary {c.get('commentary_id')}.latin_quote: AE → Æ")
                c["latin_quote"] = new_val

    # --- footnotes: S. → Saint, normalize Jesus-Christ ---
    for fn in (data.get("footnotes") or []):
        old = fn.get("text")
        if old:
            new_val = replace_s_dot(old)
            new_val = normalize_jesus_christ(new_val)
            if new_val != old:
                changes.append(f"  footnote {fn.get('marker')}: normalized")
                fn["text"] = new_val

    # Write if changed
    new_json = json.dumps(data, ensure_ascii=False, indent=2)
    changed = new_json != original

    if changed and not dry_run:
        with open(json_path, "w", encoding="utf-8") as f:
            f.write(new_json)
            f.write("\n")

    return changes, last_verse_ref


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry_run = "--dry-run" in sys.argv

    if not args:
        print("Usage: python cleanup_normalized.py <book_dir> [--dry-run]")
        print("  e.g. python cleanup_normalized.py 01_genese --dry-run")
        sys.exit(1)

    book_dir = args[0]
    book_path = DATA_DIR / book_dir
    norm_dir = book_path / "normalized"

    if not norm_dir.is_dir():
        print(f"Error: {norm_dir} not found")
        sys.exit(1)

    json_files = sorted(norm_dir.glob("page_*.json"))
    print(f"Processing {len(json_files)} files in {norm_dir}")
    if dry_run:
        print("(DRY RUN — no files will be modified)\n")

    total_changes = 0
    files_changed = 0
    prev_last_verse_ref = None

    for jf in json_files:
        page_changes, prev_last_verse_ref = process_file(jf, prev_last_verse_ref, dry_run)
        if page_changes:
            files_changed += 1
            total_changes += len(page_changes)
            print(f"{jf.name}:")
            for c in page_changes:
                print(c)

    print(f"\nDone. {total_changes} changes across {files_changed} files.")
    if dry_run:
        print("(No files were modified — remove --dry-run to apply)")


if __name__ == "__main__":
    main()
