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
  9. Remove "℣." from "latin" and "french" fields in "verses".
  10. Remove the first instance of a duplicate word, when the last word of a "french_commentary" is the same as the first word of a "french_commentary" on the next page.
  11. Replace all instances of "&c." with "etc." ("ETC." in latin_quote).
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

    # Original logic to merge across punctuation
    # e.g. _word1_, _word2_ -> _word1, word2_
    # And _a_ [ _b_ ] _c_ -> _a [ b ] c_
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"_(\s*\[\]\(\),;:\s]+\s*)_", r"\1", text)

    # New logic to remove spaces inside brackets that the above regex might create
    # e.g. [ b ] -> [b]
    text = re.sub(r'\[\s+([^_]*?)\s+\]', r'[\1]', text)
    
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

def replace_etc(text, field_name=None):
    """Replace '&c.' with 'etc.' or 'ETC.' in latin_quote."""
    if not text:
        return text
    if field_name == "latin_quote":
        return text.replace("&c.", "ETC.")
    return text.replace("&c.", "etc.")

def process_data(data, prev_last_verse_ref, page_name=""):
    """Process a single normalized JSON object. Returns (changed_data, new_last_verse_ref, changes_list)."""
    original_data_str = json.dumps(data, ensure_ascii=False)
    changes = []
    
    # Apply transformations to a copy
    processed_data = json.loads(original_data_str)

    # --- chapter_summary: remove underscores ---
    if processed_data.get("chapter_summary"):
        new_val = strip_underscores(processed_data["chapter_summary"])
        if new_val != processed_data["chapter_summary"]:
            changes.append(f"  chapter_summary: stripped underscores")
            processed_data["chapter_summary"] = new_val

    # --- verses: clean latin & french ---
    for v in (processed_data.get("verses") or []):
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
            new_val = replace_etc(new_val, field)
            if new_val != old:
                changes.append(f"  verse {v.get('verse_number')}.{field}: cleaned")
                v[field] = new_val

    # --- commentary: fill verse_ref, fix double caps, merge italics, S. → Saint ---
    last_verse_ref = prev_last_verse_ref
    comms = processed_data.get("commentary") or []
    for i, c in enumerate(comms):
        if c.get("verse_ref") is not None:
            last_verse_ref = c["verse_ref"]
        else:
            if last_verse_ref is not None:
                changes.append(f"  commentary {c.get('commentary_id')}: verse_ref null → {last_verse_ref}")
                c["verse_ref"] = last_verse_ref

        for field in ("french_translation", "french_commentary", "latin_quote"):
            old = c.get(field)
            if old:
                new_val = old
                if field == "french_translation":
                    new_val = merge_italic_markers(new_val)
                new_val = replace_s_dot(new_val)
                new_val = normalize_jesus_christ(new_val)
                new_val = replace_etc(new_val, field)

                if field == "latin_quote":
                    new_val = replace_ae_ligature(new_val)

                if new_val != old:
                    changes.append(f"  commentary {c.get('commentary_id')}.{field}: normalized")
                    c[field] = new_val

    # --- footnotes: S. → Saint, normalize Jesus-Christ ---
    for fn in (processed_data.get("footnotes") or []):
        old = fn.get("text")
        if old:
            new_val = replace_s_dot(old)
            new_val = normalize_jesus_christ(new_val)
            new_val = replace_etc(new_val, 'text')
            if new_val != old:
                changes.append(f"  footnote {fn.get('marker')}: normalized")
                fn["text"] = new_val
                
    return processed_data, last_verse_ref, changes

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

    # Load all data
    all_data = []
    for jf in json_files:
        with open(jf, "r", encoding="utf-8") as f:
            all_data.append(json.load(f))

    # Handle cross-file duplicate word removal
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

        last_word_current_list = last_comm_current["french_commentary"].strip().split(" ")
        if not last_word_current_list:
            continue
        last_word_current = last_word_current_list[-1]

        first_word_next_list = first_comm_next["french_commentary"].strip().split(" ")
        if not first_word_next_list:
            continue
        first_word_next = first_word_next_list[0]

        if last_word_current and last_word_current == first_word_next:
            # Remove last word from the commentary on the current page
            words = last_comm_current["french_commentary"].strip().split(" ")
            last_comm_current["french_commentary"] = " ".join(words[:-1])
            # Mark that a change happened for logging, maybe add to a change list on the data object
            page_name = json_files[i].name
            print(f"{page_name}: Removed duplicate word '{last_word_current}' at end of french_commentary")

    # Process each file's data
    total_changes = 0
    files_changed = 0
    prev_last_verse_ref = None

    for i, jf in enumerate(json_files):
        data = all_data[i]
        original_json = json.dumps(data, ensure_ascii=False, indent=2)

        processed_data, prev_last_verse_ref, page_changes = process_data(data, prev_last_verse_ref, page_name=jf.name)
        
        new_json = json.dumps(processed_data, ensure_ascii=False, indent=2)
        
        if new_json != original_json:
            files_changed += 1
            if page_changes:
                total_changes += len(page_changes)
                print(f"{jf.name}:")
                for c in page_changes:
                    print(c)
            
            if not dry_run:
                with open(jf, "w", encoding="utf-8") as f:
                    f.write(new_json)
                    f.write("\n")

    print(f"\nDone. {total_changes} changes across {files_changed} files.")
    if dry_run:
        print("(No files were modified — remove --dry-run to apply)")

if __name__ == "__main__":
    main()