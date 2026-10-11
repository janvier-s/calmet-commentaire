#!/usr/bin/env python3
"""
Normalize JSON structure: book_title placement, chapter_number, verse numbers.
Separated from validation for single responsibility.

Converts chapter_title field to chapter_number (integer).
By default, writes normalized files to data/<book>/normalized/
to preserve original files in data/<book>/21st_*/commentaire/

Usage:
    python normalize.py 01_genese
    python normalize.py 01_genese --output-dir custom_output
"""

import json
import re
import sys
import fcntl
from pathlib import Path
from contextlib import contextmanager
from json.decoder import JSONDecodeError

# Precompile regex patterns (Fix #8: Performance)
CHAPTER_PATTERN = re.compile(r'CHAP(?:ITRE)?\.?\s+(\w+)', re.IGNORECASE)
VERSE_PREFIX_PATTERN = re.compile(r'^[℣vV\*]\.\s*')
RANGE_PATTERN = re.compile(r'-')

@contextmanager
def file_lock(file_handle):
    """Context manager for file locking (Fix #1: Race conditions)."""
    try:
        fcntl.flock(file_handle.fileno(), fcntl.LOCK_EX)
        yield file_handle
    finally:
        fcntl.flock(file_handle.fileno(), fcntl.LOCK_UN)


def parse_verse_number(verse_num_str, prev_verse_num):
    """
    Parse verse number string to integer.
    Returns (number, is_range) tuple.

    Handles formats: ℣. 1, v. 2, V. 3, *. 4, 1-2, II. (OCR error for 11)
    """
    if not verse_num_str:
        return None, False

    text = str(verse_num_str).strip()

    # Check for range (e.g., "1-2" or "1-2.")
    if RANGE_PATTERN.search(text):
        parts = text.split('-')
        if len(parts) == 2:
            # Strip periods from both parts
            first = parts[0].strip().rstrip('.')
            second = parts[1].strip().rstrip('.')
            if first.isdigit():
                return int(first), True

    # Remove common prefixes (using precompiled pattern)
    text = VERSE_PREFIX_PATTERN.sub('', text)

    # Strip any remaining non-alphanumeric leading characters (e.g. ✚, †, etc.)
    text = re.sub(r'^[^a-zA-Z0-9]+', '', text).strip()

    # Remove trailing periods
    text = text.rstrip('.')

    # Handle Roman numerals - check context to distinguish II from OCR error
    if re.match(r'^[IVX]+$', text.upper()):
        # If previous verse was >= 10, likely OCR error (II = 11)
        if text.upper() == 'II' and prev_verse_num and prev_verse_num >= 10:
            return 11, False
        # Otherwise parse as Roman numeral
        roman_map = {'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5,
                     'VI': 6, 'VII': 7, 'VIII': 8, 'IX': 9, 'X': 10}
        if text.upper() in roman_map:
            return roman_map[text.upper()], False

    # Try to parse as integer
    if text.isdigit():
        return int(text), False

    return None, False


def normalize_file(filepath: Path, book_title_value: str = None, output_path: Path = None, raw_json_path: Path = None) -> tuple[bool, str, dict]:
    """
    Normalize a single JSON file.
    Returns (modified, message, data)

    Args:
        filepath: Input file path
        book_title_value: Expected book title from config
        output_path: Optional output path (if None, writes to same location)
        raw_json_path: Optional path to raw_json version of same file (fallback for missing chapter_title)
    """
    try:
        # Fix #2: Better error handling with file locking
        with open(filepath, 'r', encoding='utf-8') as f:
            with file_lock(f):
                data = json.load(f)
    except JSONDecodeError as e:
        return False, f"JSON Parse Error at line {e.lineno}, col {e.colno}: {e.msg}", {}
    except FileNotFoundError:
        return False, "File not found", {}
    except PermissionError:
        return False, "Permission denied", {}
    except IOError as e:
        return False, f"I/O Error: {e}", {}

    modified = False

    # Normalize chapter_number to integer (only on chapter-start pages)
    chapter_title = data.get("chapter_title")  # Read from old field name
    chapter_summary = data.get("chapter_summary")
    chapter_number = None

    # Check if this is a chapter start page
    is_chapter_start = False

    # Fallback 1: if no chapter_title, try extracting from book_title (OCR misclassification)
    # e.g. book_title: "SUR LA GENESE. Chap. X." → chapter 10
    if not chapter_title:
        book_title = data.get("book_title")
        if isinstance(book_title, str):
            chapter_match = CHAPTER_PATTERN.search(book_title)
            if chapter_match:
                chapter_title = book_title  # Use book_title as source for chapter parsing

    # Fallback 2: check if chapter info was misplaced into a verse entry by OCR
    # e.g. verse_number: "CHAPITRE 15", french: "Ordonnances qui regardent les Sacrifices."
    if not chapter_title:
        verses = data.get("verses", [])
        for i, verse in enumerate(verses):
            vn = verse.get("verse_number")
            if isinstance(vn, str) and CHAPTER_PATTERN.search(vn):
                chapter_title = vn
                # If the verse's french text looks like a chapter summary, adopt it
                if not chapter_summary and verse.get("french") and not verse.get("latin"):
                    data["chapter_summary"] = verse["french"]
                    chapter_summary = verse["french"]
                # Remove this pseudo-verse from the verses list
                verses.pop(i)
                data["verses"] = verses
                modified = True
                break

    # Fallback 3: if still no chapter_title, try raw_json as fallback
    if not chapter_title and raw_json_path and raw_json_path.exists():
        try:
            with open(raw_json_path, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
            raw_chapter_title = raw_data.get("chapter_title")
            if isinstance(raw_chapter_title, str) and CHAPTER_PATTERN.search(raw_chapter_title):
                chapter_title = raw_chapter_title
        except Exception:
            pass

    if chapter_title:
        # Extract chapter number from chapter_title (or book_title fallback)
        if isinstance(chapter_title, int):
            chapter_number = chapter_title
            is_chapter_start = True  # Already normalized, assume it's a start
        elif isinstance(chapter_title, str):
            # Extract chapter number from string (e.g., "CHAPITRE 6." → 6)
            chapter_match = CHAPTER_PATTERN.search(chapter_title)
            if chapter_match:
                chapter_num_str = chapter_match.group(1).rstrip('.')

                # Parse Roman/Arabic numerals
                if chapter_num_str.isdigit():
                    chapter_number = int(chapter_num_str)
                elif chapter_num_str in ['I', 'PREMIER', 'PREMIÈRE']:
                    chapter_number = 1
                else:
                    # Try Roman numerals (up to 151 for Psalms)
                    roman_map = {
                        'II': 2, 'III': 3, 'IV': 4, 'V': 5, 'VI': 6, 'VII': 7, 'VIII': 8, 'IX': 9,
                        'X': 10, 'XI': 11, 'XII': 12, 'XIII': 13, 'XIV': 14, 'XV': 15, 'XVI': 16, 'XVII': 17,
                        'XVIII': 18, 'XIX': 19, 'XX': 20, 'XXI': 21, 'XXII': 22, 'XXIII': 23, 'XXIV': 24, 'XXV': 25,
                        'XXVI': 26, 'XXVII': 27, 'XXVIII': 28, 'XXIX': 29, 'XXX': 30, 'XXXI': 31, 'XXXII': 32, 'XXXIII': 33,
                        'XXXIV': 34, 'XXXV': 35, 'XXXVI': 36, 'XXXVII': 37, 'XXXVIII': 38, 'XXXIX': 39, 'XL': 40, 'XLI': 41,
                        'XLII': 42, 'XLIII': 43, 'XLIV': 44, 'XLV': 45, 'XLVI': 46, 'XLVII': 47, 'XLVIII': 48, 'XLIX': 49,
                        'L': 50, 'LI': 51, 'LII': 52, 'LIII': 53, 'LIV': 54, 'LV': 55, 'LVI': 56, 'LVII': 57,
                        'LVIII': 58, 'LIX': 59, 'LX': 60, 'LXI': 61, 'LXII': 62, 'LXIII': 63, 'LXIV': 64, 'LXV': 65,
                        'LXVI': 66, 'LXVII': 67, 'LXVIII': 68, 'LXIX': 69, 'LXX': 70, 'LXXI': 71, 'LXXII': 72, 'LXXIII': 73,
                        'LXXIV': 74, 'LXXV': 75, 'LXXVI': 76, 'LXXVII': 77, 'LXXVIII': 78, 'LXXIX': 79, 'LXXX': 80, 'LXXXI': 81,
                        'LXXXII': 82, 'LXXXIII': 83, 'LXXXIV': 84, 'LXXXV': 85, 'LXXXVI': 86, 'LXXXVII': 87, 'LXXXVIII': 88, 'LXXXIX': 89,
                        'XC': 90, 'XCI': 91, 'XCII': 92, 'XCIII': 93, 'XCIV': 94, 'XCV': 95, 'XCVI': 96, 'XCVII': 97,
                        'XCVIII': 98, 'XCIX': 99, 'C': 100, 'CI': 101, 'CII': 102, 'CIII': 103, 'CIV': 104, 'CV': 105,
                        'CVI': 106, 'CVII': 107, 'CVIII': 108, 'CIX': 109, 'CX': 110, 'CXI': 111, 'CXII': 112, 'CXIII': 113,
                        'CXIV': 114, 'CXV': 115, 'CXVI': 116, 'CXVII': 117, 'CXVIII': 118, 'CXIX': 119, 'CXX': 120, 'CXXI': 121,
                        'CXXII': 122, 'CXXIII': 123, 'CXXIV': 124, 'CXXV': 125, 'CXXVI': 126, 'CXXVII': 127, 'CXXVIII': 128, 'CXXIX': 129,
                        'CXXX': 130, 'CXXXI': 131, 'CXXXII': 132, 'CXXXIII': 133, 'CXXXIV': 134, 'CXXXV': 135, 'CXXXVI': 136, 'CXXXVII': 137,
                        'CXXXVIII': 138, 'CXXXIX': 139, 'CXL': 140, 'CXLI': 141, 'CXLII': 142, 'CXLIII': 143, 'CXLIV': 144, 'CXLV': 145,
                        'CXLVI': 146, 'CXLVII': 147, 'CXLVIII': 148, 'CXLIX': 149, 'CL': 150, 'CLI': 151
                    }
                    chapter_number = roman_map.get(chapter_num_str)

        # Verify this is actually a chapter start page
        # MUST have verse 1 to be a chapter start (chapter_summary/chapter_title can be duplicated by OCR)
        if chapter_number:
            verses = data.get("verses", [])
            contains_verse_1 = False
            for verse in verses:
                vn = verse.get("verse_number")
                verse_num = vn if isinstance(vn, int) else None
                if not verse_num and isinstance(vn, str):
                    verse_num, _ = parse_verse_number(vn, None)

                if verse_num == 1:
                    contains_verse_1 = True
                    break

            # Only treat as chapter start if it has verse 1
            is_chapter_start = contains_verse_1

    # Update chapter_number based on whether this is a chapter start
    # Maintain correct field order by rebuilding the dict
    new_chapter_number = chapter_number if (is_chapter_start and chapter_number) else None

    if data.get("chapter_number") != new_chapter_number or "chapter_title" in data:
        # Rebuild dict with correct field order
        new_data = {}
        new_data["book_title"] = data.get("book_title")
        new_data["chapter_number"] = new_chapter_number
        new_data["chapter_summary"] = data.get("chapter_summary")
        new_data["verses"] = data.get("verses", [])
        new_data["commentary"] = data.get("commentary", [])
        new_data["footnotes"] = data.get("footnotes", [])
        new_data["book_end_marker"] = data.get("book_end_marker")

        data.clear()
        data.update(new_data)
        modified = True

    # Duplicate chapter_summary removal is handled in second pass (see normalize_directory)

    # Fix book_title placement
    # Only keep book_title in files where it should be (chapter 1 start pages)
    current_book_title = data.get("book_title")
    is_chapter_1_start = (is_chapter_start and chapter_number == 1)

    # If book_title_value is provided and this is not chapter 1 start, remove book_title
    if book_title_value and not is_chapter_1_start and current_book_title:
        data["book_title"] = None
        modified = True

    # Normalize verse numbers
    verses = data.get("verses", [])
    prev_verse_num = None
    has_ranges = False

    for verse in verses:
        verse_num_str = verse.get("verse_number")
        verse_num, is_range = parse_verse_number(verse_num_str, prev_verse_num)

        if is_range:
            has_ranges = True

        # Update verse_number to integer (or keep original if parse failed)
        if verse_num is not None:
            if verse.get("verse_number") != verse_num:
                verse["verse_number"] = verse_num
                modified = True
            prev_verse_num = verse_num

        # Update verse_ref to integer if present
        verse_ref = verse.get("verse_ref")
        if verse_ref:
            verse_ref_num, verse_ref_is_range = parse_verse_number(verse_ref, None)
            if verse_ref_num is not None and verse.get("verse_ref") != verse_ref_num:
                verse["verse_ref"] = verse_ref_num
                modified = True
            if verse_ref_is_range:
                has_ranges = True

    # Normalize commentary verse_ref and commentary_id
    commentaries = data.get("commentary", [])
    for comment in commentaries:
        # Normalize verse_ref
        verse_ref = comment.get("verse_ref")
        if verse_ref:
            verse_ref_num, verse_ref_is_range = parse_verse_number(verse_ref, None)
            if verse_ref_num is not None and comment.get("verse_ref") != verse_ref_num:
                comment["verse_ref"] = verse_ref_num
                modified = True
            if verse_ref_is_range:
                has_ranges = True

        # Normalize commentary_id (ensure int, not float or string)
        commentary_id = comment.get("commentary_id")
        if commentary_id is not None:
            try:
                # Convert to int (handles floats like 1.0 and strings like "1")
                normalized_id = int(float(commentary_id))
                if comment.get("commentary_id") != normalized_id:
                    comment["commentary_id"] = normalized_id
                    modified = True
            except (ValueError, TypeError):
                pass  # Keep original if conversion fails

    # Save if modified (Fix #9: Write to output directory)
    write_path = output_path if output_path else filepath

    if modified or output_path:
        # Create output directory if needed
        write_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(write_path, 'w', encoding='utf-8') as f:
                with file_lock(f):
                    json.dump(data, f, ensure_ascii=False, indent=2)
        except IOError as e:
            return False, f"Failed to write file: {e}", {}

        if has_ranges:
            return True, "Normalized (contains ranges)", data
        else:
            return True, "Normalized", data
    else:
        return False, "No changes needed", data


def validate_book_dir(book_dir: str) -> bool:
    """Validate book directory name (Fix #3: Prevent path traversal)."""
    # Only allow alphanumeric, underscore, hyphen
    if not re.match(r'^[\w\-]+$', book_dir):
        return False
    # Additional safety: no parent directory references
    if '..' in book_dir or '/' in book_dir or '\\' in book_dir:
        return False
    return True


def main():
    if len(sys.argv) < 2:
        print("Usage: python normalize.py <book_directory> [--output-dir DIR]")
        print("Example: python normalize.py 01_genese")
        print("         python normalize.py 01_genese --output-dir custom_output")
        print("\nDefaults to writing normalized files to data/<book>/normalized/")
        sys.exit(1)

    book_dir = sys.argv[1]

    # Fix #3: Validate input to prevent path traversal
    if not validate_book_dir(book_dir):
        print(f"Error: Invalid book directory name: {book_dir}")
        print("Book directory must contain only alphanumeric characters, underscore, or hyphen")
        sys.exit(1)

    # Parse optional output directory (default: "normalized")
    output_dir_name = "normalized"  # Default output directory
    if '--output-dir' in sys.argv:
        idx = sys.argv.index('--output-dir')
        if idx + 1 < len(sys.argv):
            output_dir_name = sys.argv[idx + 1]

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

    # Setup output directory (Fix #9) - at book level by default
    output_commentaire_dir = book_path / output_dir_name
    output_commentaire_dir.mkdir(parents=True, exist_ok=True)
    print(f"Normalizing JSON structure in: {commentaire_dir}")
    print(f"Writing normalized files to: {output_commentaire_dir}")

    # Load config to get expected book_title
    try:
        config_path = script_dir / "config.py"
        if config_path.exists():
            import importlib.util
            spec = importlib.util.spec_from_file_location("config", config_path)
            config = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(config)

            book_title_value = config.BOOK_MAPPINGS.get(book_dir)
        else:
            book_title_value = None
    except:
        book_title_value = None

    # Find all JSON files
    json_files = sorted(commentaire_dir.glob("page_*.json"))

    # Resolve raw_json directory for fallback chapter_title lookups
    raw_json_commentaire_dir = book_path / "raw_json" / "commentaire"
    has_raw_json = raw_json_commentaire_dir.exists()

    normalized_count = 0
    no_change_count = 0
    failed_count = 0
    files_with_ranges = []
    failed_files = []
    for filepath in json_files:
        # Calculate output path if writing to separate directory
        output_path = None
        if output_commentaire_dir:
            output_path = output_commentaire_dir / filepath.name

        # Resolve raw_json fallback path for this file
        raw_json_path = (raw_json_commentaire_dir / filepath.name) if has_raw_json else None

        modified, message, data = normalize_file(filepath, book_title_value, output_path, raw_json_path)

        if "Error" in message:
            failed_count += 1
            failed_files.append((filepath.name, message))
            print(f"✗ Failed: {filepath.name} - {message}")
        elif modified:
            normalized_count += 1
            if "ranges" in message:
                files_with_ranges.append(filepath.name)
            print(f"✓ {message}: {filepath.name}")
        else:
            no_change_count += 1

    # Second pass: remove duplicate chapter starts and chapter summaries
    # A chapter can only start once; if the same chapter_number appears on multiple
    # pages, only the first occurrence (in page order) is the real chapter start.
    # Later occurrences are caused by OCR repeating the chapter header on continuation
    # pages combined with a mislabeled verse number.
    output_dir = output_commentaire_dir or commentaire_dir
    output_files = sorted(output_dir.glob("page_*.json"))
    seen_chapters = {}  # chapter_number -> first file path
    chapter_summaries = set()
    for fpath in output_files:
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                d = json.load(f)
            cn = d.get("chapter_number")
            if cn and d.get("chapter_summary"):
                chapter_summaries.add(d["chapter_summary"])
            if cn is not None:
                if cn in seen_chapters:
                    # Duplicate chapter start — null out chapter_number on the later page
                    d["chapter_number"] = None
                    with open(fpath, 'w', encoding='utf-8') as f:
                        json.dump(d, f, ensure_ascii=False, indent=2)
                        f.write('\n')
                    normalized_count += 1
                    print(f"✓ Removed duplicate chapter_number {cn}: {fpath.name}")
                else:
                    seen_chapters[cn] = fpath
        except Exception:
            continue

    # Then delete duplicate chapter_summary on non-chapter-start pages
    for fpath in output_files:
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                d = json.load(f)
            if not d.get("chapter_number") and d.get("chapter_summary") and d["chapter_summary"] in chapter_summaries:
                d["chapter_summary"] = None
                with open(fpath, 'w', encoding='utf-8') as f:
                    json.dump(d, f, ensure_ascii=False, indent=2)
                    f.write('\n')
                normalized_count += 1
                print(f"✓ Removed duplicate chapter_summary: {fpath.name}")
        except Exception:
            continue

    print("\n" + "="*60)
    print(f"Summary:")
    print(f"  No changes needed: {no_change_count}")
    print(f"  Normalized: {normalized_count}")
    print(f"  Failed: {failed_count}")

    if files_with_ranges:
        print(f"\nFiles with verse ranges ({len(files_with_ranges)}):")
        for filename in files_with_ranges:
            print(f"  - {filename}")

    if failed_files:
        print(f"\nFailed files:")
        for filename, message in failed_files:
            print(f"  - {filename}: {message}")


if __name__ == "__main__":
    main()
