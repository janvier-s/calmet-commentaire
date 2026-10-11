#!/usr/bin/env python3
"""
Comprehensive cleanup script for normalized JSON files.
Combines all content cleanup transformations.

Usage: python cleanup.py <book_dir> [--dry-run]
  e.g. python cleanup.py 01_genese --dry-run

Transformations:
  1. Remove underscores from verses & chapter_summary
  2. Remove verse prefixes (℣. N.) from verse text
  3. Fill null verse_ref (carry forward)
  4. Merge italic markers: _a_ [_b_] _c_ → _a [b] c_
  5. Fix double capitals at start of text
  6. Replace long s (ſ) with regular s
  7. Replace "&" with "et" in French text
  8. Replace "℣." with "verset" in commentary text
  9. Replace "S." with "Saint"
  10. Normalize "Jésus-Christ" spelling (including "J. C." and "J.-C")
  11. Replace "&c." with "etc." (or "ETC." in latin)
  12. Replace "AE" with "Æ" in latin_quote
  13. Uppercase latin_quote
  14. Add newlines before numbered lists (N°.)
  15. French punctuation spacing (nbsp, except before : in verse refs)
  16. Remove duplicate words across pages
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
    # ℣. 27. _text_ or ℣. 11. text or ℣. text
    text = re.sub(r"^℣\.\s*(\d+\.\s*)?", "", text)
    # Leading "12. " at start of verse text
    text = re.sub(r"^\d+\.\s+", "", text)
    # Standalone ℣.
    text = text.replace("℣.", "")
    return text


def merge_italic_markers(text):
    """
    Merge adjacent italic spans separated by non-italic fragments.
    _Lorem_ [_ipsum_] _sit._ → _Lorem [ipsum] sit._
    """
    if not text or "_" not in text:
        return text

    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"_(\s*\[\]\(\),;:\s]+\s*)_", r"\1", text)

    # Remove spaces inside brackets
    text = re.sub(r'\[\s+([^_]*?)\s+\]', r'[\1]', text)

    return text


def fix_double_capitals(text):
    """
    Fix OCR double-capital at start of text.
    "HIs ita..." → "His ita..."
    "_TRaduction" → "_Traduction"
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
    # Handle J. C. and J.-C. abbreviations
    text = re.sub(r"\bJ\.\s*C\.", "Jésus-Christ", text)
    text = re.sub(r"\bJ\.-C\.?", "Jésus-Christ", text)
    # Handle JESUS-CHRIST (all caps)
    text = re.sub(r"\bJESUS-CHRIST\b", "Jésus-Christ", text)
    # Handle Jesus-Christ (title case)
    text = re.sub(r"\bJesus-Christ\b", "Jésus-Christ", text)
    # Handle Jesus Christ (two words, no hyphen)
    text = re.sub(r"\bJesus\s+Christ\b", "Jésus-Christ", text)
    return text


def replace_etc(text, is_latin=False):
    """Replace '&c.' with 'etc.' or 'ETC.' in latin."""
    if not text:
        return text
    if is_latin:
        return text.replace("&c.", "ETC.")
    return text.replace("&c.", "etc.")


def replace_long_s(text):
    """Replace long s (ſ) with regular s."""
    if not text:
        return text
    return text.replace("ſ", "s")


def replace_ampersand(text):
    """Replace standalone & with 'et' in French text."""
    if not text:
        return text
    # Replace & when surrounded by spaces
    text = re.sub(r'\s&\s', ' et ', text)
    return text


def replace_verse_symbol(text):
    """Replace ℣. with 'verset' in commentary text."""
    if not text:
        return text
    # Replace ℣. N. with 'verset N'
    text = re.sub(r'℣\.\s*(\d+)', r'verset \1', text)
    # Replace standalone ℣.
    text = text.replace("℣.", "verset")
    return text


def add_list_newlines(text):
    """Add newline before numbered list items (N°.)"""
    if not text:
        return text
    # Matches: (whitespace or nothing) + (digits + °.)
    text = re.sub(r"(\s*)(\d+°\.)", r"\n\2", text)
    # Cleanup: if the text STARTS with \n, strip it
    text = text.lstrip("\n")
    return text


def french_punctuation_spacing(text):
    """
    Apply French punctuation spacing using non-breaking space.
    - nbsp before : ; ? »
    - nbsp after «
    - Exception: no nbsp before : in verse references (e.g., Genèse 10:35)
    """
    if not text:
        return text
    # Before ; ? » (always)
    text = re.sub(r'[ \t ]*([;?»])', r' \1', text)
    # Before : (but NOT after digits in verse references)
    text = re.sub(r'(?<!\d)[ \t ]*(:)', r' \1', text)
    # After «
    text = re.sub(r'(«)[ \t ]*', r'\1 ', text)
    return text


def process_file(data, prev_last_verse_ref):
    """Process a single JSON file. Returns (processed_data, new_last_verse_ref, changes)."""
    changes = []

    # --- Chapter summary: remove underscores ---
    if data.get("chapter_summary"):
        new_val = strip_underscores(data["chapter_summary"])
        if new_val != data["chapter_summary"]:
            changes.append("chapter_summary: stripped underscores")
            data["chapter_summary"] = new_val

    # --- Verses: comprehensive cleanup ---
    for v in data.get("verses", []):
        verse_num = v.get("verse_number")

        # Fix double capitals on verse 1
        if verse_num == 1:
            for field in ("latin", "french"):
                old = v.get(field)
                if old:
                    new_val = fix_double_capitals(old)
                    if new_val != old:
                        changes.append(f"verse {verse_num}.{field}: fixed double caps")
                        v[field] = new_val

        # Clean all verse fields
        for field in ("latin", "french"):
            old = v.get(field)
            if not old:
                continue

            new_val = old
            new_val = strip_underscores(new_val)
            new_val = strip_verse_prefix(new_val)
            new_val = replace_long_s(new_val)
            if field == "french":
                new_val = replace_ampersand(new_val)
            new_val = normalize_jesus_christ(new_val)
            new_val = replace_etc(new_val, is_latin=(field == "latin"))

            if new_val != old:
                changes.append(f"verse {verse_num}.{field}: cleaned")
                v[field] = new_val

    # --- Commentary: comprehensive cleanup ---
    last_verse_ref = prev_last_verse_ref
    for c in data.get("commentary", []):
        # Fill null verse_ref
        if c.get("verse_ref") is not None:
            last_verse_ref = c["verse_ref"]
        elif last_verse_ref is not None:
            changes.append(f"commentary {c.get('commentary_id')}: filled verse_ref → {last_verse_ref}")
            c["verse_ref"] = last_verse_ref

        # Process latin_quote
        if c.get("latin_quote"):
            old = c["latin_quote"]
            new_val = old
            new_val = replace_long_s(new_val)
            new_val = replace_ae_ligature(new_val)
            new_val = replace_etc(new_val, is_latin=True)
            new_val = new_val.upper()  # Uppercase

            if new_val != old:
                changes.append(f"commentary {c.get('commentary_id')}.latin_quote: cleaned")
                c["latin_quote"] = new_val

        # Process french_translation
        if c.get("french_translation"):
            old = c["french_translation"]
            new_val = old
            new_val = merge_italic_markers(new_val)
            new_val = replace_long_s(new_val)
            new_val = replace_ampersand(new_val)
            new_val = replace_verse_symbol(new_val)
            new_val = replace_s_dot(new_val)
            new_val = normalize_jesus_christ(new_val)
            new_val = replace_etc(new_val)
            new_val = add_list_newlines(new_val)
            new_val = french_punctuation_spacing(new_val)

            if new_val != old:
                changes.append(f"commentary {c.get('commentary_id')}.french_translation: cleaned")
                c["french_translation"] = new_val

        # Process french_commentary
        if c.get("french_commentary"):
            old = c["french_commentary"]
            new_val = old
            new_val = replace_long_s(new_val)
            new_val = replace_ampersand(new_val)
            new_val = replace_verse_symbol(new_val)
            new_val = replace_s_dot(new_val)
            new_val = normalize_jesus_christ(new_val)
            new_val = replace_etc(new_val)
            new_val = add_list_newlines(new_val)
            new_val = french_punctuation_spacing(new_val)

            if new_val != old:
                changes.append(f"commentary {c.get('commentary_id')}.french_commentary: cleaned")
                c["french_commentary"] = new_val

    # --- Footnotes: cleanup ---
    for fn in data.get("footnotes", []):
        if fn.get("text"):
            old = fn["text"]
            new_val = old
            new_val = replace_long_s(new_val)
            new_val = replace_ampersand(new_val)
            new_val = replace_verse_symbol(new_val)
            new_val = replace_s_dot(new_val)
            new_val = normalize_jesus_christ(new_val)
            new_val = replace_etc(new_val)
            new_val = french_punctuation_spacing(new_val)

            if new_val != old:
                changes.append(f"footnote {fn.get('marker')}: cleaned")
                fn["text"] = new_val

    return data, last_verse_ref, changes


def remove_duplicate_words_across_pages(all_data, json_files):
    """Remove duplicate words where last word of page N == first word of page N+1."""
    changes = []

    for i in range(len(all_data) - 1):
        current_data = all_data[i]
        next_data = all_data[i+1]

        current_comms = [c for c in current_data.get("commentary", []) if c.get("french_commentary")]
        next_comms = [c for c in next_data.get("commentary", []) if c.get("french_commentary")]

        if not current_comms or not next_comms:
            continue

        last_comm_current = current_comms[-1]
        first_comm_next = next_comms[0]

        if not last_comm_current.get("french_commentary") or not first_comm_next.get("french_commentary"):
            continue

        last_words = last_comm_current["french_commentary"].strip().split()
        first_words = first_comm_next["french_commentary"].strip().split()

        if not last_words or not first_words:
            continue

        if last_words[-1] == first_words[0]:
            # Remove last word from current page
            last_comm_current["french_commentary"] = " ".join(last_words[:-1])
            changes.append(f"{json_files[i].name}: Removed duplicate word '{last_words[-1]}'")

    return changes


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry_run = "--dry-run" in sys.argv

    if not args:
        print("Usage: python cleanup.py <book_dir> [--dry-run]")
        print("  e.g. python cleanup.py 01_genese --dry-run")
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

    # Load all data
    all_data = []
    for jf in json_files:
        with open(jf, "r", encoding="utf-8") as f:
            all_data.append(json.load(f))

    # Step 1: Remove duplicate words across pages
    print("Step 1: Removing duplicate words across pages...")
    dup_changes = remove_duplicate_words_across_pages(all_data, json_files)
    for change in dup_changes:
        print(f"  {change}")

    # Step 2: Process each file
    print("\nStep 2: Applying comprehensive cleanup...")
    total_changes = 0
    files_changed = 0
    prev_last_verse_ref = None

    for i, jf in enumerate(json_files):
        data = all_data[i]
        original_json = json.dumps(data, ensure_ascii=False, indent=2)

        processed_data, prev_last_verse_ref, page_changes = process_file(data, prev_last_verse_ref)

        new_json = json.dumps(processed_data, ensure_ascii=False, indent=2)

        if new_json != original_json:
            files_changed += 1
            if page_changes:
                total_changes += len(page_changes)
                print(f"{jf.name}:")
                for c in page_changes:
                    print(f"  {c}")

            if not dry_run:
                with open(jf, "w", encoding="utf-8") as f:
                    f.write(new_json)
                    f.write("\n")

    print(f"\nDone. {total_changes} changes across {files_changed} files.")
    if dry_run:
        print("(No files were modified — remove --dry-run to apply)")


if __name__ == "__main__":
    main()
