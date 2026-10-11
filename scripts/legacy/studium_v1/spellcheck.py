#!/usr/bin/env python3
"""
Spellcheck french_commentary text and produce a per-chapter corrections file.

Extracts French words from a single commentary_txt chapter, filters out
Latin/Greek (italic markers) and footnote refs, then runs remaining words
through hunspell to flag misspellings with suggested corrections.

Outputs:
  <book>/transformed/corrections/chapter_XX.json — flagged words with suggestions
  <book>/transformed/flagged_words.json           — context report for review

Reads:
  <book>/transformed/allowlist.json               — words to skip
  <book>/transformed/corrections_master.json      — already-corrected words to skip
  <book>/transformed/corrections/chapter_*.json   — previously reviewed chapters to skip

Usage: python spellcheck.py <book_directory> <chapter_number>
Example: python spellcheck.py 01_genese 1
"""

import json
import re
import subprocess
import sys
from pathlib import Path

DICT_PATH = Path.home() / "Library" / "Spelling" / "fr_FR"

FOOTNOTE_REF = re.compile(r"\^\{[^}]*\}")
ITALIC_BLOCK = re.compile(r"_([^_]+)_")
WORD_PATTERN = re.compile(r"[A-Za-zÀ-ÿŒœÆæ](?:[A-Za-zÀ-ÿŒœÆæ'-]*[A-Za-zÀ-ÿŒœÆæ])?")


def extract_french_words(text):
    """Extract French words, stripping italic blocks (Latin/foreign) and footnote refs."""
    text = FOOTNOTE_REF.sub("", text)
    text = ITALIC_BLOCK.sub(" ", text)
    return WORD_PATTERN.findall(text)


def run_hunspell(words):
    """Run unique words through hunspell in batches, return dict of misspelled -> suggestions."""
    unique = sorted(set(words))
    if not unique:
        return {}

    misspelled = {}
    batch_size = 500
    for i in range(0, len(unique), batch_size):
        batch = unique[i : i + batch_size]
        input_text = "\n".join(batch)
        result = subprocess.run(
            ["hunspell", "-d", str(DICT_PATH), "-a"],
            input=input_text,
            capture_output=True,
            text=True,
            timeout=300,
        )

        lines = result.stdout.strip().split("\n")
        for line in lines[1:]:
            if line == "":
                continue
            if line.startswith("&"):
                parts = line.split(":")
                word = parts[0].split()[1]
                suggestions = [s.strip() for s in parts[1].split(",")] if len(parts) > 1 else []
                misspelled[word] = suggestions[0] if suggestions else ""
            elif line.startswith("#"):
                word = line.split()[1]
                misspelled[word] = ""

    return misspelled


def load_already_handled(transformed_dir):
    """Load all words already handled from allowlist, master, and per-chapter corrections."""
    handled = set()

    allowlist_path = transformed_dir / "allowlist.json"
    if allowlist_path.exists():
        with open(allowlist_path, "r", encoding="utf-8") as f:
            handled |= set(json.load(f))

    master_path = transformed_dir / "corrections_master.json"
    if master_path.exists():
        with open(master_path, "r", encoding="utf-8") as f:
            handled |= set(json.load(f).keys())

    corrections_dir = transformed_dir / "corrections"
    if corrections_dir.exists():
        for cf in corrections_dir.glob("chapter_*.json"):
            with open(cf, "r", encoding="utf-8") as f:
                handled |= set(json.load(f).keys())

    return handled


def spellcheck_chapter(book_dir, chapter_num):
    script_dir = Path(__file__).parent
    data_dir = script_dir.parent / "data"
    book_path = data_dir / book_dir
    transformed_dir = book_path / "transformed"
    commentary_txt_dir = transformed_dir / "commentary_txt"
    corrections_dir = transformed_dir / "corrections"
    corrections_dir.mkdir(parents=True, exist_ok=True)

    target = commentary_txt_dir / f"chapter_{chapter_num:02d}.json"
    if not target.exists():
        print(f"Error: {target} does not exist.")
        sys.exit(1)

    if not DICT_PATH.with_suffix(".dic").exists():
        print(f"Error: French dictionary not found at {DICT_PATH}.dic")
        sys.exit(1)

    already_handled = load_already_handled(transformed_dir)
    print(f"Already handled: {len(already_handled)} words")

    # Extract words
    with open(target, "r", encoding="utf-8") as f:
        entries = json.load(f)

    word_freq = {}
    word_context = {}

    for entry in entries:
        text = entry.get("french_commentary") or ""
        words = extract_french_words(text)
        for w in words:
            wl = w if w[0].isupper() else w.lower()
            if wl in already_handled:
                continue
            word_freq[wl] = word_freq.get(wl, 0) + 1
            if wl not in word_context:
                idx = text.lower().find(w.lower())
                if idx >= 0:
                    start = max(0, idx - 30)
                    end = min(len(text), idx + len(w) + 30)
                    word_context[wl] = "..." + text[start:end] + "..."

    all_words = list(word_freq.keys())
    print(f"Chapter {chapter_num}: {len(all_words)} unique words to check...")

    # Run hunspell
    print("Running hunspell...")
    misspelled = run_hunspell(all_words)

    # Build per-chapter corrections file
    new_corrections = {}
    for word, suggestion in sorted(misspelled.items(), key=lambda x: -word_freq.get(x[0], 0)):
        new_corrections[word] = suggestion

    ch_corrections_path = corrections_dir / f"chapter_{chapter_num:02d}.json"
    with open(ch_corrections_path, "w", encoding="utf-8") as f:
        json.dump(new_corrections, f, ensure_ascii=False, indent=2)

    # Write flagged report
    report_path = transformed_dir / "flagged_words.json"
    flagged = [
        {
            "word": word,
            "suggestion": suggestion,
            "frequency": word_freq.get(word, 0),
            "context": word_context.get(word, ""),
        }
        for word, suggestion in new_corrections.items()
    ]
    flagged.sort(key=lambda x: -x["frequency"])

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(flagged, f, ensure_ascii=False, indent=2)

    print(f"\nResults:")
    print(f"  Words checked: {len(all_words)}")
    print(f"  New misspelled: {len(new_corrections)}")
    print(f"\nFiles written:")
    print(f"  {ch_corrections_path}")
    print(f"  {report_path}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python spellcheck.py <book_directory> <chapter_number>")
        print("Example: python spellcheck.py 01_genese 1")
        sys.exit(1)

    spellcheck_chapter(sys.argv[1], int(sys.argv[2]))
