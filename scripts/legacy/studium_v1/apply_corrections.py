#!/usr/bin/env python3
"""
Apply reviewed corrections to all chapter files.

Reads all corrections/chapter_XX.json files, merges them, applies non-empty
replacements to french_commentary in ALL chapters/chapter_XX.json files,
regenerates commentary_txt/, updates allowlist.json, and rebuilds
corrections_master.json (combined corrections for reuse on other books).

Usage: python apply_corrections.py <book_directory>
Example: python apply_corrections.py 01_genese
"""

import json
import re
import sys
from pathlib import Path


def apply_corrections_book(book_dir):
    script_dir = Path(__file__).parent
    data_dir = script_dir.parent / "data"
    book_path = data_dir / book_dir
    transformed_dir = book_path / "transformed"
    chapters_dir = transformed_dir / "chapters"
    commentary_txt_dir = transformed_dir / "commentary_txt"
    corrections_dir = transformed_dir / "corrections"

    allowlist_path = transformed_dir / "allowlist.json"
    master_path = transformed_dir / "corrections_master.json"

    if not corrections_dir.exists():
        print(f"Error: {corrections_dir} does not exist. Run spellcheck.py first.")
        sys.exit(1)

    # Load all per-chapter correction files
    all_replacements = {}
    new_allowlist = set()
    correction_files = sorted(corrections_dir.glob("chapter_*.json"))

    if not correction_files:
        print("No correction files found.")
        sys.exit(0)

    for cf in correction_files:
        with open(cf, "r", encoding="utf-8") as f:
            corrections = json.load(f)
        for word, replacement in corrections.items():
            if replacement:
                all_replacements[word] = replacement
            else:
                new_allowlist.add(word)

    print(f"Loaded {len(correction_files)} correction file(s):")
    print(f"  {len(all_replacements)} replacements, {len(new_allowlist)} allowlisted")

    # Apply replacements to ALL chapter files
    if all_replacements:
        sorted_words = sorted(all_replacements.keys(), key=len, reverse=True)
        pattern = re.compile(
            r"\b(" + "|".join(re.escape(w) for w in sorted_words) + r")\b"
        )

        chapter_files = sorted(chapters_dir.glob("chapter_*.json"))
        modified_count = 0

        for ch_file in chapter_files:
            with open(ch_file, "r", encoding="utf-8") as f:
                ch_data = json.load(f)

            modified = False
            for commentary in ch_data.get("commentaries", []):
                text = commentary.get("french_commentary") or ""
                new_text = pattern.sub(lambda m: all_replacements[m.group(0)], text)
                if new_text != text:
                    commentary["french_commentary"] = new_text
                    modified = True

            if modified:
                modified_count += 1
                with open(ch_file, "w", encoding="utf-8") as f:
                    json.dump(ch_data, f, ensure_ascii=False, indent=2)

        print(f"  Updated {modified_count}/{len(chapter_files)} chapter files")

        # Regenerate commentary_txt
        print("Regenerating commentary_txt/...")
        commentary_txt_dir.mkdir(parents=True, exist_ok=True)
        for ch_file in chapter_files:
            with open(ch_file, "r", encoding="utf-8") as f:
                ch_data = json.load(f)
            commentary_txt = [
                {
                    "commentary_seq": c["commentary_seq"],
                    "french_commentary": c["french_commentary"],
                }
                for c in ch_data.get("commentaries", [])
            ]
            ch_num = ch_data["chapter"]
            txt_path = commentary_txt_dir / f"chapter_{ch_num:02d}.json"
            with open(txt_path, "w", encoding="utf-8") as f:
                json.dump(commentary_txt, f, ensure_ascii=False, indent=2)
    else:
        print("No replacements to apply.")

    # Update allowlist
    allowlist = set()
    if allowlist_path.exists():
        with open(allowlist_path, "r", encoding="utf-8") as f:
            allowlist = set(json.load(f))

    allowlist |= new_allowlist
    allowlist |= set(all_replacements.keys())

    with open(allowlist_path, "w", encoding="utf-8") as f:
        json.dump(sorted(allowlist), f, ensure_ascii=False, indent=2)

    # Rebuild corrections_master.json (cumulative, for reuse on other books)
    master = {}
    if master_path.exists():
        with open(master_path, "r", encoding="utf-8") as f:
            master = json.load(f)

    master.update(all_replacements)

    with open(master_path, "w", encoding="utf-8") as f:
        json.dump(master, f, ensure_ascii=False, indent=2)

    print(f"\nDone:")
    print(f"  Allowlist size: {len(allowlist)}")
    print(f"  Master corrections: {len(master)}")
    print(f"  Files: {allowlist_path.name}, {master_path.name}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python apply_corrections.py <book_directory>")
        print("Example: python apply_corrections.py 01_genese")
        sys.exit(1)

    apply_corrections_book(sys.argv[1])
