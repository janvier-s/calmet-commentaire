#!/usr/bin/env python3
"""
Copy missing files from raw_json to processing directory.
Separated from fix_json_errors.py for single responsibility.

Usage:
    python copy_missing_files.py 01_genese
"""

import sys
from pathlib import Path
from shutil import copy2


def find_missing_files(commentaire_dir: Path, raw_json_dir: Path) -> list[Path]:
    """Find files that exist in raw_json but not in processing directory."""
    # Get existing files in processing directory
    existing_files = {f.name for f in commentaire_dir.glob("page_*.json")}

    # Find missing files in raw_json
    missing_files = []
    for raw_file in sorted(raw_json_dir.glob("page_*.json")):
        if raw_file.name not in existing_files:
            missing_files.append(raw_file)

    return missing_files


def copy_missing_files_to_folder(missing_files: list[Path], dest_dir: Path) -> int:
    """Copy missing files to destination directory."""
    dest_dir.mkdir(parents=True, exist_ok=True)

    copied_count = 0
    for src_file in missing_files:
        dest_file = dest_dir / src_file.name
        copy2(src_file, dest_file)
        print(f"  ✓ Copied: {src_file.name}")
        copied_count += 1

    return copied_count


def main():
    if len(sys.argv) < 2:
        print("Usage: python copy_missing_files.py <book_directory>")
        print("Example: python copy_missing_files.py 01_genese")
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
    raw_json_dir = book_path / "raw_json" / "commentaire"

    if not raw_json_dir.exists():
        print(f"Error: No raw_json/commentaire directory in {book_path}")
        sys.exit(1)

    print(f"Checking for missing files in: {commentaire_dir}")
    print(f"Source: {raw_json_dir}")

    # Find missing files
    missing_files = find_missing_files(commentaire_dir, raw_json_dir)

    if not missing_files:
        print("\nNo missing files found.")
        sys.exit(0)

    # Create missing directory and copy files
    missing_dir = processing_dir / "missing"

    print(f"\nFound {len(missing_files)} missing files:")
    for f in missing_files:
        print(f"  - {f.name}")

    print(f"\nCopying to: {missing_dir}")
    copied_count = copy_missing_files_to_folder(missing_files, missing_dir)

    print("\n" + "="*60)
    print(f"Summary:")
    print(f"  Total missing files: {len(missing_files)}")
    print(f"  Copied: {copied_count}")
    print(f"\nFiles saved to: {missing_dir}")


if __name__ == "__main__":
    main()
