#!/usr/bin/env python3
"""
Fix JSON syntax errors: invalid escape sequences and control characters.
Read-only validation in validate.py, write operations here.

Usage:
    python fix_json_errors.py 01_genese
"""

import json
import re
import sys
from pathlib import Path


def fix_json_content(content: str) -> str:
    """
    Fix common JSON errors:
    1. Escape literal newlines/tabs inside JSON strings
    2. Remove invalid escape sequences like \\^, \\{, \\}
    3. Remove control characters
    """
    # First pass: escape literal newlines/tabs/returns inside JSON string values
    result = []
    in_string = False
    escape_next = False

    for i, char in enumerate(content):
        if escape_next:
            result.append(char)
            escape_next = False
            continue

        if char == '\\':
            result.append(char)
            escape_next = True
            continue

        if char == '"':
            in_string = not in_string
            result.append(char)
            continue

        if in_string:
            # Inside a string - escape control characters
            if char == '\n':
                result.append('\\n')
            elif char == '\t':
                result.append('\\t')
            elif char == '\r':
                result.append('\\r')
            elif ord(char) < 0x20 or ord(char) == 0x7F:
                # Other control characters - remove them
                pass
            else:
                result.append(char)
        else:
            # Outside strings - keep as-is
            result.append(char)

    content = ''.join(result)

    # Second pass: fix invalid escape sequences
    # Valid JSON escapes: \", \\, \/, \b, \f, \n, \r, \t, \uXXXX
    def fix_escape(match):
        char = match.group(1)
        if char in '"\\/bfnrtu':
            # Valid escape, keep it
            return match.group(0)
        else:
            # Invalid escape, remove the backslash
            return char

    content = re.sub(r'\\(.)', fix_escape, content)

    return content


def fix_json_file(filepath: Path) -> tuple[bool, str]:
    """
    Try to fix and reparse a JSON file.
    Returns (success, error_message)
    """
    try:
        # Read raw content
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        # Try to parse first
        try:
            json.loads(content)
            return True, "Already valid"
        except json.JSONDecodeError:
            pass  # Need to fix

        # Apply fixes
        fixed_content = fix_json_content(content)

        # Try to parse fixed content
        try:
            parsed = json.loads(fixed_content)
            # Success - write back with proper formatting
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(parsed, f, ensure_ascii=False, indent=2)
            return True, "Fixed and saved"
        except json.JSONDecodeError as e:
            return False, f"Still invalid: {e}"

    except Exception as e:
        return False, f"Error: {e}"


def main():
    if len(sys.argv) < 2:
        print("Usage: python fix_json_errors.py <book_directory>")
        print("Example: python fix_json_errors.py 01_genese")
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

    print(f"Fixing JSON errors in: {commentaire_dir}")

    # Find all JSON files
    json_files = sorted(commentaire_dir.glob("page_*.json"))

    fixed_count = 0
    already_valid_count = 0
    failed_count = 0
    failed_files = []

    for filepath in json_files:
        success, message = fix_json_file(filepath)

        if success:
            if message == "Already valid":
                already_valid_count += 1
            else:
                fixed_count += 1
                print(f"✓ Fixed: {filepath.name}")
        else:
            failed_count += 1
            failed_files.append((filepath.name, message))
            print(f"✗ Failed: {filepath.name} - {message}")

    print("\n" + "="*60)
    print(f"Summary:")
    print(f"  Already valid: {already_valid_count}")
    print(f"  Fixed: {fixed_count}")
    print(f"  Failed: {failed_count}")

    if failed_files:
        print(f"\nFailed files:")
        for filename, message in failed_files:
            print(f"  - {filename}: {message}")


if __name__ == "__main__":
    main()
