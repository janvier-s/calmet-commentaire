#!/usr/bin/env python3
"""
Process files in modernization_error folders using the same modernization logic.

Usage:
    python3 modernize_errors.py <book_name>
    python3 modernize_errors.py 06_josue
"""

import json
import sys
from pathlib import Path

# Import modernization function from modernize.py
sys.path.insert(0, str(Path(__file__).parent))
from modernize import modernize_json_file, validate_json_output

BASE_PATH = "/Users/Janvier/Library/Mobile Documents/com~apple~CloudDocs/for-the-kingdom/STUDIUM/data"


def process_modernization_errors(book_name: str) -> None:
    """
    Process all JSON files in modernization_error directory.

    Writes processed files to modernization_error_processed directory.

    Args:
        book_name: Book name (e.g., "06_josue")
    """
    book_dir = Path(BASE_PATH) / book_name
    error_dir = book_dir / "modernization_error"
    output_dir = book_dir / "modernization_error_processed"

    if not error_dir.exists():
        print(f"Error: Directory does not exist: {error_dir}")
        return

    # Find all JSON files
    json_files = sorted(error_dir.glob("page_*.json"))

    if not json_files:
        print(f"No JSON files found in: {error_dir}")
        return

    print(f"Found {len(json_files)} JSON files in {error_dir.name}")

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {output_dir}")

    processed = 0
    errors = 0

    for source_file in json_files:
        try:
            output_file = output_dir / source_file.name

            # Read source JSON
            with open(source_file, "r", encoding="utf-8") as f:
                source_data = json.load(f)

            # Apply modernization
            modernized_data = modernize_json_file(source_data)

            # Validate output
            validate_json_output(modernized_data, source_data)

            # Write to output
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(modernized_data, f, ensure_ascii=False, indent=2)

            processed += 1

            # Progress report every 10 files
            if processed % 10 == 0:
                print(f"Processed {processed} files...")

        except json.JSONDecodeError as e:
            print(f"JSON error in {source_file.name}: {e}")
            errors += 1
        except ValueError as e:
            print(f"Validation error in {source_file.name}: {e}")
            errors += 1
        except Exception as e:
            print(f"Error processing {source_file.name}: {e}")
            errors += 1

    # Summary
    print("\n" + "=" * 60)
    print("MODERNIZATION ERROR PROCESSING SUMMARY")
    print("=" * 60)
    print(f"Total source files: {len(json_files)}")
    print(f"Successfully processed: {processed}")
    print(f"Errors: {errors}")
    print(f"\nProcessed files written to: {output_dir}")
    print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python modernize_errors.py <book_name>")
        print("Example: python modernize_errors.py 06_josue")
        sys.exit(1)

    process_modernization_errors(sys.argv[1])
