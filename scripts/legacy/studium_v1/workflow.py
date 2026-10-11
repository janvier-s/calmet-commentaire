#!/usr/bin/env python3
"""
Master workflow orchestrator for processing Bible commentary JSON files.
Runs all scripts in optimal order with error handling.

Usage:
    python workflow.py 01_genese
    python workflow.py 01_genese --skip-json-fixes  # Skip JSON error fixes
    python workflow.py 01_genese --validate-only    # Only run validation
"""

import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime


class WorkflowRunner:
    def __init__(self, book_dir: str, script_dir: Path):
        self.book_dir = book_dir
        self.script_dir = script_dir
        self.steps_completed = []
        self.steps_failed = []

    def run_script(self, script_name: str, description: str) -> bool:
        """Run a script and return success status."""
        print("\n" + "="*60)
        print(f"STEP: {description}")
        print("="*60)

        script_path = self.script_dir / script_name
        if not script_path.exists():
            print(f"✗ Script not found: {script_path}")
            self.steps_failed.append((description, "Script not found"))
            return False

        try:
            # Fix #4: Add timeout to prevent hanging scripts (5 minutes max)
            result = subprocess.run(
                [sys.executable, str(script_path), self.book_dir],
                capture_output=False,
                text=True,
                check=False,
                timeout=300  # 5 minutes
            )

            if result.returncode == 0:
                print(f"\n✓ {description} completed successfully")
                self.steps_completed.append(description)
                return True
            else:
                print(f"\n✗ {description} failed with exit code {result.returncode}")
                self.steps_failed.append((description, f"Exit code {result.returncode}"))
                return False

        except subprocess.TimeoutExpired:
            print(f"\n✗ {description} timed out (exceeded 5 minutes)")
            self.steps_failed.append((description, "Timeout after 5 minutes"))
            return False
        except Exception as e:
            print(f"\n✗ {description} failed: {e}")
            self.steps_failed.append((description, str(e)))
            return False

    def print_summary(self):
        """Print final workflow summary."""
        print("\n" + "="*60)
        print("WORKFLOW SUMMARY")
        print("="*60)
        print(f"Book: {self.book_dir}")
        print(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"\nSteps completed: {len(self.steps_completed)}")
        for step in self.steps_completed:
            print(f"  ✓ {step}")

        if self.steps_failed:
            print(f"\nSteps failed: {len(self.steps_failed)}")
            for step, error in self.steps_failed:
                print(f"  ✗ {step}: {error}")
        else:
            print("\n🎉 All steps completed successfully!")

        print("\n" + "="*60)


def main():
    if len(sys.argv) < 2:
        print("Usage: python workflow.py <book_directory> [options]")
        print("Example: python workflow.py 01_genese")
        print("\nOptions:")
        print("  --skip-json-fixes   Skip JSON error fixes")
        print("  --validate-only     Only run validation")
        sys.exit(1)

    book_dir = sys.argv[1]
    skip_json_fixes = "--skip-json-fixes" in sys.argv
    validate_only = "--validate-only" in sys.argv

    # Determine paths
    script_dir = Path(__file__).parent
    data_dir = script_dir.parent / "data"
    book_path = data_dir / book_dir

    if not book_path.exists():
        print(f"Error: Book directory not found: {book_path}")
        sys.exit(1)

    print("="*60)
    print("BIBLE COMMENTARY JSON PROCESSING WORKFLOW")
    print("="*60)
    print(f"Book: {book_dir}")
    print(f"Path: {book_path}")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*60)

    runner = WorkflowRunner(book_dir, script_dir)

    if validate_only:
        # Only run validation
        runner.run_script("validate.py", "Validation (read-only)")
        runner.print_summary()
        sys.exit(0 if not runner.steps_failed else 1)

    # Full workflow
    # Step 1: Fix JSON syntax errors (in-place on 21st_*)
    if not skip_json_fixes:
        success = runner.run_script(
            "fix_json_errors.py",
            "Fix JSON syntax errors"
        )
        if not success:
            print("\nWarning: JSON fixes failed. Some files may have syntax errors.")
            print("Continuing with workflow...")

    # Step 2: Copy missing files from raw_json to missing/
    success = runner.run_script(
        "copy_missing_files.py",
        "Copy missing files from raw_json"
    )
    if not success:
        print("\nWarning: Copying missing files failed.")
        print("Continuing with workflow...")

    # Step 3: Modernize biblical references (in-place on 21st_*)
    success = runner.run_script(
        "modernize_biblical_refs.py",
        "Modernize biblical references"
    )
    if not success:
        print("\nWarning: Biblical reference modernization failed.")
        print("Continuing with workflow...")

    # Step 4: Pre-validation gate — all 21st_* files must be valid JSON
    print("\n" + "="*60)
    print("STEP: Pre-normalization validation gate")
    print("="*60)

    # Find 21st_* commentaire directory
    commentaire_dir = None
    for item in book_path.iterdir():
        if item.is_dir() and item.name.startswith("21st_"):
            commentaire_dir = item / "commentaire"
            break

    if commentaire_dir and commentaire_dir.exists():
        broken_files = []
        for filepath in sorted(commentaire_dir.glob("page_*.json")):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    json.load(f)
            except (json.JSONDecodeError, Exception) as e:
                broken_files.append((filepath.name, str(e)))

        if broken_files:
            print(f"\n✗ HALT: {len(broken_files)} file(s) have invalid JSON:")
            for name, error in broken_files:
                print(f"  - {name}: {error}")
            print("\nFix these files manually before re-running the workflow.")
            print("Move unfixable files to missing/ if they need separate handling.")
            runner.steps_failed.append(("Pre-normalization validation gate", f"{len(broken_files)} broken files"))
            runner.print_summary()
            sys.exit(1)
        else:
            print(f"\n✓ All files in {commentaire_dir.name}/ are valid JSON")
            runner.steps_completed.append("Pre-normalization validation gate")
    else:
        print("\n✗ No 21st_*/commentaire/ directory found")
        runner.steps_failed.append(("Pre-normalization validation gate", "No commentaire directory"))
        runner.print_summary()
        sys.exit(1)

    # Step 5: Normalize structure (21st_*/commentaire/ → normalized/)
    success = runner.run_script(
        "normalize.py",
        "Normalize JSON structure"
    )
    if not success:
        print("\nError: Normalization failed.")
        runner.print_summary()
        sys.exit(1)

    # Step 6: Comprehensive cleanup of normalized files
    success = runner.run_script(
        "cleanup.py",
        "Cleanup normalized files (remove underscores, fix punctuation, etc.)"
    )
    if not success:
        print("\nWarning: Cleanup failed.")
        print("Continuing with workflow...")

    # Step 7: Validate normalized output (read-only, comprehensive report)
    success = runner.run_script(
        "validate.py",
        "Validation (read-only)"
    )
    if not success:
        print("\nWarning: Validation failed.")

    # Step 8: Copy source images for uncertain/illegible markers
    success = runner.run_script(
        "copy_uncertain_images.py",
        "Copy source images for uncertain/illegible markers"
    )
    if not success:
        print("\nNote: No uncertain/illegible markers found (or script failed).")

    # Print final summary
    runner.print_summary()

    # Exit with error code if any step failed
    sys.exit(0 if not runner.steps_failed else 1)


if __name__ == "__main__":
    main()
