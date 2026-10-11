#!/usr/bin/env python3
"""
General content cleanup script for normalized JSON files.
Usage: python scripts/cleanup_content.py 01_genese [--dry-run]

Transformations:
  1. Convert 'latin_quote' content to uppercase.
  2. Add newline before numbered list items (e.g. "1°.", "2°.") in commentary fields.
  3. Apply French punctuation spacing:
     - Non-breaking space ( ) before : ; ? »
     - Non-breaking space ( ) after «
     - Replaces existing regular spaces and prevents double spacing.
"""

import json
import re
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

def process_file(file_path, dry_run=False):
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    changed = False
    commentaries = data.get("commentary", [])
    for entry in commentaries:
        # 1. Uppercase latin_quote
        latin_quote = entry.get("latin_quote")
        if latin_quote and isinstance(latin_quote, str):
            upper_quote = latin_quote.upper()
            if upper_quote != latin_quote:
                entry["latin_quote"] = upper_quote
                changed = True
        
        # Apply text transformations to specific fields
        for field in ["french_commentary", "french_translation", "latin_quote"]:
            content = entry.get(field)
            if content and isinstance(content, str):
                original_content = content
                
                # 2. Add newline before "N°."
                # Matches: (whitespace or nothing) + (digits + °.)
                content = re.sub(r"(\s*)(\d+°\.)", r"\n\2", content)
                
                # Cleanup: if the text STARTS with \n, strip it
                if content.startswith("\n") and not original_content.startswith("\n"):
                   content = content.lstrip("\n")
                
                # 3. French punctuation spacing
                # Use literal non-breaking space character: ' ' (U+00A0)
                
                # Before : ; ? »
                # Consume any mix of regular space, tab, or existing nbsp, and replace with single nbsp
                content = re.sub(r'[ \t ]*([:;?»])', r' \1', content)
                
                # After «
                # Consume any mix of regular space, tab, or existing nbsp, and replace with single nbsp
                content = re.sub(r'(«)[ \t ]*', r'\1 ', content)

                if content != original_content:
                    entry[field] = content
                    changed = True

    if changed:
        if dry_run:
            print(f"Would update {file_path.name}")
        else:
            print(f"Updated {file_path.name}")
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.write("\n")
    return changed

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry_run = "--dry-run" in sys.argv

    if not args:
        print("Usage: python scripts/uppercase_latin_quotes.py <book_dir> [--dry-run]")
        sys.exit(1)

    book_dir = args[0]
    norm_dir = DATA_DIR / book_dir / "normalized"

    if not norm_dir.is_dir():
        print(f"Error: {norm_dir} not found")
        sys.exit(1)

    json_files = sorted(norm_dir.glob("page_*.json"))
    print(f"Processing {len(json_files)} files in {norm_dir}")

    total_updated = 0
    for jf in json_files:
        if process_file(jf, dry_run):
            total_updated += 1

    print(f"\nDone. Updated {total_updated} files.")

if __name__ == "__main__":
    main()
