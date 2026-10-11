#!/usr/bin/env python3
"""
Modernize biblical references in footnotes.
Converts old French abbreviations to modern standard format.

Usage:
    python modernize_biblical_refs.py 01_genese
"""

import json
import re
import sys
from pathlib import Path


# Book name mappings from old French to modern
BOOK_ABBREVIATIONS = {
    # Old Testament
    'gen': 'Genèse', 'genes': 'Genèse', 'genese': 'Genèse',
    'exod': 'Exode', 'exode': 'Exode',
    'levit': 'Lévitique', 'lev': 'Lévitique',
    'num': 'Nombres', 'nomb': 'Nombres',
    'deut': 'Deutéronome', 'deuteron': 'Deutéronome',
    'jos': 'Josué', 'josue': 'Josué',
    'jud': 'Juges', 'judic': 'Juges',
    'ruth': 'Ruth',
    '1 reg': '1 Samuel', 'i reg': '1 Samuel', '1. reg': '1 Samuel',
    '2 reg': '2 Samuel', 'ii reg': '2 Samuel', '2. reg': '2 Samuel',
    '3 reg': '1 Rois', 'iii reg': '1 Rois', '3. reg': '1 Rois',
    '4 reg': '2 Rois', 'iv reg': '2 Rois', '4. reg': '2 Rois',
    '1 par': '1 Chroniques', 'i par': '1 Chroniques', '1. par': '1 Chroniques',
    '2 par': '2 Chroniques', 'ii par': '2 Chroniques', '2. par': '2 Chroniques',
    '1 esdr': '1 Esdras', 'i esdr': '1 Esdras',
    '2 esdr': '2 Esdras', 'ii esdr': '2 Esdras', 'neh': 'Néhémie',
    'tob': 'Tobie', 'tobie': 'Tobie',
    'jud': 'Judith', 'judith': 'Judith',
    'esth': 'Esther', 'esther': 'Esther',
    'job': 'Job',
    'ps': 'Psaumes', 'psalm': 'Psaumes', 'psaume': 'Psaumes',
    'prov': 'Proverbes', 'proverb': 'Proverbes',
    'eccle': 'Ecclésiaste', 'qohel': 'Qohélet',
    'cant': 'Cantique des Cantiques', 'cantiq': 'Cantique des Cantiques',
    'sag': 'Sagesse', 'sap': 'Sagesse',
    'eccli': 'Ecclésiastique', 'sir': 'Siracide',
    'isa': 'Isaïe', 'isai': 'Isaïe', 'esai': 'Isaïe',
    'jer': 'Jérémie', 'jerem': 'Jérémie',
    'lam': 'Lamentations', 'lament': 'Lamentations',
    'bar': 'Baruch', 'baruch': 'Baruch',
    'ezech': 'Ézéchiel', 'ezech': 'Ézéchiel',
    'dan': 'Daniel', 'daniel': 'Daniel',
    'os': 'Osée', 'osee': 'Osée',
    'joel': 'Joël',
    'am': 'Amos', 'amos': 'Amos',
    'abd': 'Abdias', 'abdi': 'Abdias',
    'jon': 'Jonas', 'jonas': 'Jonas',
    'mich': 'Michée', 'michee': 'Michée',
    'nah': 'Nahum', 'nahum': 'Nahum',
    'hab': 'Habacuc', 'habac': 'Habacuc',
    'soph': 'Sophonie', 'sophon': 'Sophonie',
    'agg': 'Aggée', 'aggee': 'Aggée',
    'zach': 'Zacharie', 'zachar': 'Zacharie',
    'mal': 'Malachie', 'malach': 'Malachie',
    '1 mach': '1 Maccabées', 'i mach': '1 Maccabées',
    '2 mach': '2 Maccabées', 'ii mach': '2 Maccabées',

    # New Testament
    'matth': 'Matthieu', 'matt': 'Matthieu', 'mt': 'Matthieu',
    'marc': 'Marc', 'mc': 'Marc',
    'luc': 'Luc', 'lc': 'Luc',
    'joan': 'Jean', 'jean': 'Jean', 'jn': 'Jean',
    'act': 'Actes', 'actes': 'Actes',
    'rom': 'Romains', 'rom': 'Romains',
    '1 cor': '1 Corinthiens', 'i cor': '1 Corinthiens',
    '2 cor': '2 Corinthiens', 'ii cor': '2 Corinthiens',
    'gal': 'Galates', 'galat': 'Galates',
    'eph': 'Éphésiens', 'ephes': 'Éphésiens',
    'phil': 'Philippiens', 'philipp': 'Philippiens',
    'col': 'Colossiens', 'coloss': 'Colossiens',
    '1 thess': '1 Thessaloniciens', 'i thess': '1 Thessaloniciens',
    '2 thess': '2 Thessaloniciens', 'ii thess': '2 Thessaloniciens',
    '1 tim': '1 Timothée', 'i tim': '1 Timothée',
    '2 tim': '2 Timothée', 'ii tim': '2 Timothée',
    'tit': 'Tite', 'tite': 'Tite',
    'philem': 'Philémon', 'philemon': 'Philémon',
    'hebr': 'Hébreux', 'heb': 'Hébreux',
    'jac': 'Jacques', 'jacq': 'Jacques',
    '1 petr': '1 Pierre', 'i petr': '1 Pierre',
    '2 petr': '2 Pierre', 'ii petr': '2 Pierre',
    '1 joan': '1 Jean', 'i joan': '1 Jean',
    '2 joan': '2 Jean', 'ii joan': '2 Jean',
    '3 joan': '3 Jean', 'iii joan': '3 Jean',
    'jud': 'Jude', 'jude': 'Jude',
    'apoc': 'Apocalypse', 'apoc': 'Apocalypse', 'ap': 'Apocalypse',
}


def clean_footnote_text(text: str) -> str:
    """
    Clean footnote text: remove italics, expand abbreviations, fix capitalization.

    Handles:
    - Remove italics: _text_ or *text* → text
    - Abbreviations: et c. → etc., &c. → etc.
    - Capitalize sentence starts and "Chapitre"
    - Remove trailing periods from references
    """
    if not text:
        return text

    # Remove italics markers (both _ and *)
    text = re.sub(r'_([^_]+)_', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)

    # Expand abbreviations
    text = re.sub(r'\bet\s+c\.', 'etc.', text, flags=re.IGNORECASE)
    text = re.sub(r'&c\.', 'etc.', text)

    # Latin to French
    text = re.sub(r'\bVide\b', 'Voyez', text)

    # Standardize verse abbreviations
    text = re.sub(r'\bv\.\s+(\d+)', r'verset \1', text)
    text = re.sub(r'\bV\.\s+(\d+)', r'Verset \1', text)

    # Capitalize "chapitre" when it starts a sentence or reference
    text = re.sub(r'\bchapitre\b', 'Chapitre', text)

    # Capitalize first letter if it's lowercase
    if text and text[0].islower():
        text = text[0].upper() + text[1:]

    # Fix spacing issues (multiple spaces)
    text = re.sub(r'\s{2,}', ' ', text)

    return text.strip()


def modernize_reference(text: str) -> tuple[str, bool]:
    """
    Modernize biblical reference format.
    Returns (modernized_text, is_uncertain)

    Converts formats like:
    - "Gen. c. 3, v. 15" → "Genèse 3:15"
    - "Matth. xxv. 1." → "Matthieu 25:1"
    - "1 Reg. chap. 2." → "1 Samuel 2"
    """
    uncertain = False

    # Pattern: Book abbreviation, chapter, verse
    # Examples: "Gen. c. 3, v. 15", "Matth. chap. xxv. v. 1"
    pattern = r'\b([A-Za-z0-9\s\.]+?)\.\s*(?:c\.|ch\.|chap\.|chapitre)?\s*([ivxlcdmIVXLCDM0-9]+)[,\.]?\s*(?:v\.|vers\.|verset)?\s*([ivxlcdmIVXLCDM0-9]+)?'

    def replace_ref(match):
        nonlocal uncertain
        book_abbr = match.group(1).strip().lower()
        chapter = match.group(2).strip()
        verse = match.group(3).strip() if match.group(3) else None

        # Look up book name
        book_name = BOOK_ABBREVIATIONS.get(book_abbr)
        if not book_name:
            uncertain = True
            return match.group(0)  # Keep original if uncertain

        # Convert Roman numerals to Arabic
        chapter_num = roman_to_int(chapter) if is_roman(chapter) else chapter
        verse_num = roman_to_int(verse) if verse and is_roman(verse) else verse

        # Format: "Book chapter:verse" or "Book chapter"
        if verse_num:
            return f"{book_name} {chapter_num}:{verse_num}"
        else:
            return f"{book_name} {chapter_num}"

    modernized = re.sub(pattern, replace_ref, text, flags=re.IGNORECASE)

    return modernized, uncertain


def is_roman(text: str) -> bool:
    """Check if text is a Roman numeral."""
    if not text:
        return False
    return bool(re.match(r'^[ivxlcdmIVXLCDM]+$', text.strip()))


def roman_to_int(s: str) -> int:
    """Convert Roman numeral to integer."""
    if not s:
        return 0

    roman_map = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
    s = s.upper().strip()
    result = 0
    prev_value = 0

    for char in reversed(s):
        value = roman_map.get(char, 0)
        if value < prev_value:
            result -= value
        else:
            result += value
        prev_value = value

    return result


def modernize_file(filepath: Path) -> tuple[bool, str, list[str]]:
    """
    Modernize biblical references in a file.
    Returns (modified, message, uncertain_refs)
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        modified = False
        uncertain_refs = []

        # Process footnotes
        footnotes = data.get("footnotes", [])
        for footnote in footnotes:
            text = footnote.get("text", "")
            if not text:
                continue

            original_text = text

            # Step 1: Clean text (remove italics, expand abbreviations, etc.)
            text = clean_footnote_text(text)

            # Step 2: Modernize biblical references
            text, is_uncertain = modernize_reference(text)

            # Update if changed
            if text != original_text:
                footnote["text"] = text
                modified = True

            if is_uncertain:
                uncertain_refs.append(f"{filepath.name}: {original_text[:100]}")

        # Save if modified
        if modified:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            if uncertain_refs:
                return True, "Modernized (with uncertain refs)", uncertain_refs
            else:
                return True, "Modernized", uncertain_refs
        else:
            return False, "No changes needed", uncertain_refs

    except Exception as e:
        return False, f"Error: {e}", []


def main():
    if len(sys.argv) < 2:
        print("Usage: python modernize_biblical_refs.py <book_directory>")
        print("Example: python modernize_biblical_refs.py 01_genese")
        sys.exit(1)

    book_dir = sys.argv[1]

    # Determine paths
    script_dir = Path(__file__).parent
    data_dir = script_dir.parent / "data"
    book_path = data_dir / book_dir

    if not book_path.exists():
        print(f"Error: Book directory not found: {book_path}")
        sys.exit(1)

    # Find 21st_* directory
    processing_dir = None
    for item in book_path.iterdir():
        if item.is_dir() and item.name.startswith("21st_"):
            processing_dir = item
            break

    if not processing_dir:
        print(f"Error: No 21st_* directory found in {book_path}")
        sys.exit(1)

    commentaire_dir = processing_dir / "commentaire"
    if not commentaire_dir.exists():
        print(f"Error: No commentaire directory in {processing_dir}")
        sys.exit(1)

    print(f"Modernizing biblical references in: {commentaire_dir}")

    # Find all JSON files
    json_files = sorted(commentaire_dir.glob("page_*.json"))

    modernized_count = 0
    no_change_count = 0
    failed_count = 0
    all_uncertain_refs = []
    failed_files = []

    for filepath in json_files:
        modified, message, uncertain_refs = modernize_file(filepath)

        if "Error" in message:
            failed_count += 1
            failed_files.append((filepath.name, message))
            print(f"✗ Failed: {filepath.name} - {message}")
        elif modified:
            modernized_count += 1
            all_uncertain_refs.extend(uncertain_refs)
            print(f"✓ {message}: {filepath.name}")
        else:
            no_change_count += 1

    print("\n" + "="*60)
    print(f"Summary:")
    print(f"  No changes needed: {no_change_count}")
    print(f"  Modernized: {modernized_count}")
    print(f"  Failed: {failed_count}")

    if all_uncertain_refs:
        print(f"\nUncertain references ({len(all_uncertain_refs)}):")
        for ref in all_uncertain_refs[:20]:  # Show first 20
            print(f"  - {ref}")
        if len(all_uncertain_refs) > 20:
            print(f"  ... and {len(all_uncertain_refs) - 20} more")

    if failed_files:
        print(f"\nFailed files:")
        for filename, message in failed_files:
            print(f"  - {filename}: {message}")


if __name__ == "__main__":
    main()
