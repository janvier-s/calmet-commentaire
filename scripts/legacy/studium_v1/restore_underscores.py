#!/usr/bin/env python3
"""
Restore underscores from raw_json to normalized files.
- french_translation: wraps entire text in underscores
- french_commentary: attempts to match phrases, flags ambiguous cases
"""
import json
import re
import unicodedata
from pathlib import Path

RAW_DIR = Path(__file__).parent.parent / "data/05_deuteronome/raw_json/commentaire"
NORM_DIR = Path(__file__).parent.parent / "data/05_deuteronome/normalized"

# Track results
applied = []
skipped = []
ambiguous = []


def normalize_for_matching(text):
    """Normalize text for fuzzy matching - handles old French spelling variations."""
    if not text:
        return ""
    t = text
    # Common old French → modern substitutions
    t = t.replace("ſ", "s")
    t = t.replace("œ", "oe")
    t = t.replace("æ", "ae")
    t = t.replace("&", "et")
    # Normalize unicode
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")  # strip accents
    # Collapse whitespace
    t = re.sub(r"\s+", " ", t).strip().lower()
    return t


def extract_underscored_phrases(text):
    """Extract all _phrase_ patterns from text."""
    if not text:
        return []
    # Match _..._  (non-greedy, handles multiple on same line)
    return re.findall(r"_([^_]+)_", text)


def find_phrase_in_text(phrase_normalized, norm_text, norm_text_normalized):
    """Find where a normalized phrase appears in the normalized text.
    Returns list of (start, end) positions in the ORIGINAL norm_text."""
    positions = []
    start = 0
    while True:
        idx = norm_text_normalized.find(phrase_normalized, start)
        if idx == -1:
            break
        # Map back to original positions (approximate - same length assumed)
        positions.append((idx, idx + len(phrase_normalized)))
        start = idx + 1
    return positions


def restore_french_translation(raw_comm, norm_comm, page_num, comm_id):
    """Restore underscores in french_translation - simple wrap."""
    raw_ft = raw_comm.get("french_translation") or ""
    norm_ft = norm_comm.get("french_translation") or ""

    if not norm_ft or not raw_ft:
        return None

    # Check if raw has underscores wrapping the text
    if raw_ft.startswith("_") and raw_ft.endswith("_"):
        # Check if normalized is missing them
        if not norm_ft.startswith("_"):
            new_ft = f"_{norm_ft}_"
            applied.append(f"page_{page_num:04d} comm {comm_id} french_translation: wrapped")
            return new_ft
    return None


def restore_french_commentary(raw_comm, norm_comm, page_num, comm_id):
    """Restore underscores in french_commentary - match phrases."""
    raw_fc = raw_comm.get("french_commentary") or ""
    norm_fc = norm_comm.get("french_commentary") or ""

    if not norm_fc or not raw_fc:
        return None

    # Already has underscores? Skip
    if "_" in norm_fc:
        return None

    # No underscores in raw? Nothing to restore
    if "_" not in raw_fc:
        return None

    # Extract underscored phrases from raw
    phrases = extract_underscored_phrases(raw_fc)
    if not phrases:
        return None

    # Prepare normalized versions for matching
    norm_fc_normalized = normalize_for_matching(norm_fc)

    new_fc = norm_fc
    changes_made = 0

    for phrase in phrases:
        phrase_normalized = normalize_for_matching(phrase)
        if len(phrase_normalized) < 3:
            continue  # Skip very short phrases

        # Find in normalized text
        positions = find_phrase_in_text(phrase_normalized, norm_fc, norm_fc_normalized)

        if len(positions) == 0:
            ambiguous.append(f"page_{page_num:04d} comm {comm_id}: NOT FOUND: _{phrase}_")
        elif len(positions) == 1:
            # Single match - safe to replace
            # Find the actual text at that position in the original
            start, end = positions[0]
            # We need to find the corresponding position in the original text
            # This is tricky because normalization changes length
            # Instead, search for the phrase directly
            phrase_normalized_pattern = re.escape(phrase_normalized)

            # Build a pattern that matches the normalized form in the original
            # Try direct search first
            search_start = 0
            found = False
            for match in re.finditer(r'\b\w[\w\s,;:\'\-\.]+\w\b', new_fc):
                candidate = match.group()
                if normalize_for_matching(candidate) == phrase_normalized:
                    # Found it! Replace with underscored version
                    new_fc = new_fc[:match.start()] + f"_{candidate}_" + new_fc[match.end():]
                    changes_made += 1
                    found = True
                    break

            if not found:
                # Try looser matching
                ambiguous.append(f"page_{page_num:04d} comm {comm_id}: MATCH FAILED: _{phrase}_")
        else:
            ambiguous.append(f"page_{page_num:04d} comm {comm_id}: MULTIPLE ({len(positions)}): _{phrase}_")

    if changes_made > 0:
        applied.append(f"page_{page_num:04d} comm {comm_id} french_commentary: {changes_made} phrases")
        return new_fc

    return None


def process_page(page_num):
    """Process a single page."""
    page_file = f"page_{page_num:04d}.json"
    raw_path = RAW_DIR / page_file
    norm_path = NORM_DIR / page_file

    if not raw_path.exists() or not norm_path.exists():
        return False

    try:
        with open(raw_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        with open(norm_path, "r", encoding="utf-8") as f:
            norm_data = json.load(f)
    except Exception as e:
        skipped.append(f"page_{page_num:04d}: {e}")
        return False

    raw_comms = raw_data.get("commentary", [])
    norm_comms = norm_data.get("commentary", [])

    modified = False

    for i, norm_comm in enumerate(norm_comms):
        if i >= len(raw_comms):
            break

        raw_comm = raw_comms[i]
        comm_id = norm_comm.get("commentary_id", i)

        # Restore french_translation
        new_ft = restore_french_translation(raw_comm, norm_comm, page_num, comm_id)
        if new_ft:
            norm_comms[i]["french_translation"] = new_ft
            modified = True

        # Restore french_commentary
        new_fc = restore_french_commentary(raw_comm, norm_comm, page_num, comm_id)
        if new_fc:
            norm_comms[i]["french_commentary"] = new_fc
            modified = True

    if modified:
        with open(norm_path, "w", encoding="utf-8") as f:
            json.dump(norm_data, f, ensure_ascii=False, indent=2)

    return modified


def main():
    print("Restoring underscores from raw to normalized files...")
    print(f"Range: pages 0177-0458")
    print()

    modified_count = 0
    for page_num in range(177, 459):
        if process_page(page_num):
            modified_count += 1

    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"Files modified: {modified_count}")
    print(f"Changes applied: {len(applied)}")
    print(f"Ambiguous (need manual review): {len(ambiguous)}")
    print(f"Skipped (errors): {len(skipped)}")

    if applied:
        print(f"\n{'='*60}")
        print("APPLIED CHANGES:")
        print(f"{'='*60}")
        for a in applied:
            print(f"  ✓ {a}")

    if ambiguous:
        print(f"\n{'='*60}")
        print("AMBIGUOUS - NEEDS MANUAL REVIEW:")
        print(f"{'='*60}")
        for a in ambiguous:
            print(f"  ? {a}")

    if skipped:
        print(f"\n{'='*60}")
        print("SKIPPED (errors):")
        print(f"{'='*60}")
        for s in skipped:
            print(f"  ✗ {s}")


if __name__ == "__main__":
    main()
