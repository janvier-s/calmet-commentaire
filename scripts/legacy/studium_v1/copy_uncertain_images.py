#!/usr/bin/env python3
"""
Copy source images for files with UNCERTAIN/ILLEGIBLE markers.

Usage:
    python copy_uncertain_images.py 02_exode
"""

import json
import re
import sys
from pathlib import Path
from shutil import copy2


def find_uncertain_files(book_dir: str, data_dir: Path) -> list[str]:
    """Find all JSON files with UNCERTAIN/ILLEGIBLE markers."""
    book_path = data_dir / book_dir

    # Find 21st_* directory
    processing_dir = None
    for item in book_path.iterdir():
        if item.is_dir() and item.name.startswith("21st_"):
            processing_dir = item
            break

    if not processing_dir:
        print(f"Error: No 21st_* directory found in {book_path}")
        return []

    commentaire_dir = processing_dir / "commentaire"
    if not commentaire_dir.exists():
        print(f"Error: No commentaire directory in {processing_dir}")
        return []

    # Markers to search for
    uncertain_markers = [
        "[UNCERTAIN HEBREW]",
        "[UNCERTAIN GREEK]",
        "[ILLEGIBLE]",
        "[ILLEGIBLE TEXT]",
    ]

    uncertain_files = []

    # Find all JSON files
    json_files = sorted(commentaire_dir.glob("page_*.json"))

    for filepath in json_files:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            # Check if any uncertain marker is in the content
            has_marker = any(marker in content for marker in uncertain_markers)

            if has_marker:
                uncertain_files.append(filepath.stem)  # Just the filename without .json
        except Exception as e:
            print(f"Error reading {filepath.name}: {e}")

    return uncertain_files


def copy_source_images(book_dir: str, data_dir: Path, uncertain_files: list[str]):
    """Copy source images for uncertain files."""
    book_path = data_dir / book_dir

    # Source and destination directories
    source_images_dir = book_path / "source_images" / "commentaire"
    dest_dir = book_path / "uncertain_illegible"

    if not source_images_dir.exists():
        print(f"Error: Source images directory not found: {source_images_dir}")
        return

    # Create destination directory
    dest_dir.mkdir(parents=True, exist_ok=True)

    copied_count = 0
    not_found_count = 0

    print(f"\nCopying {len(uncertain_files)} source images to {dest_dir}:")

    for page_name in uncertain_files:
        # Try different image extensions
        found = False
        for ext in ['.jpg', '.jpeg', '.png', '.tif', '.tiff', '.pdf']:
            src_file = source_images_dir / f"{page_name}{ext}"
            if src_file.exists():
                dst_file = dest_dir / src_file.name
                copy2(src_file, dst_file)
                print(f"  ✓ Copied: {src_file.name}")
                copied_count += 1
                found = True
                break

        if not found:
            print(f"  ✗ Not found: {page_name}.*")
            not_found_count += 1

    print(f"\nSummary:")
    print(f"  Copied: {copied_count}")
    print(f"  Not found: {not_found_count}")
    print(f"\nImages saved to: {dest_dir}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python copy_uncertain_images.py <book_directory>")
        print("Example: python copy_uncertain_images.py 02_exode")
        sys.exit(1)

    book_dir = sys.argv[1]

    # Determine paths
    script_dir = Path(__file__).parent
    data_dir = script_dir.parent / "data"
    book_path = data_dir / book_dir

    if not book_path.exists():
        print(f"Error: Book directory not found: {book_path}")
        sys.exit(1)

    print(f"Finding files with UNCERTAIN/ILLEGIBLE markers in {book_dir}...")
    uncertain_files = find_uncertain_files(book_dir, data_dir)

    if not uncertain_files:
        print("No files with UNCERTAIN/ILLEGIBLE markers found.")
        sys.exit(0)

    print(f"Found {len(uncertain_files)} files with uncertain/illegible markers:")
    for filename in uncertain_files:
        print(f"  - {filename}")

    # Copy source images
    copy_source_images(book_dir, data_dir, uncertain_files)


if __name__ == "__main__":
    main()
