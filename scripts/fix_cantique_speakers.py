#!/usr/bin/env python3
"""Standardize speaker headings in Cantique des Cantiques and fix split verse 8:5."""

import argparse
import glob
import json
import re
from pathlib import Path

CANONICAL_SPEAKERS = {
    "L'EPOUX": "L'ÉPOUX.",
    "L'ÉPOUX": "L'ÉPOUX.",
    "L'EPOUSE": "L'ÉPOUSE.",
    "L'ÉPOUSE": "L'ÉPOUSE.",
    "LES COMPAGNES DE L'EPOUSE": "LES COMPAGNES DE L'ÉPOUSE.",
    "LES COMPAGNES DE L'ÉPOUSE": "LES COMPAGNES DE L'ÉPOUSE.",
    "LES PARENTS DE L'EPOUSE": "LES PARENTS DE L'ÉPOUSE.",
    "LES PARENTS DE L'ÉPOUSE": "LES PARENTS DE L'ÉPOUSE.",
    "L'ÉPOUSE, ET LES FILLES DE LA NÔCE": "L'ÉPOUSE, ET LES FILLES DE LA NÔCE.",
    "L'EPOUSE, ET LES FILLES DE LA NÔCE": "L'ÉPOUSE, ET LES FILLES DE LA NÔCE.",
    "L'ÉPOUSE, ET LES FILLES DE LA NOCE": "L'ÉPOUSE, ET LES FILLES DE LA NÔCE.",
}

# Regex to find speaker headings at start of string or after newline
# Matches speaker name optionally followed by period, optional section sign, optional newline, optional verse number
SPEAKER_PATTERNS = [
    re.escape(k) for k in sorted(CANONICAL_SPEAKERS.keys(), key=lambda x: -len(x))
]
SPEAKER_RE = re.compile(
    r"(?m)^(?:[§\s\.\-]*)"
    r"(" + "|".join(SPEAKER_PATTERNS) + r")"
    r"[\.\s]*"
    r"(?:§\.?\s*)?"
    r"(?:\n\s*)?"
    r"(?:\d+\.\s*)?"
)

def fix_french_speakers(text: str) -> str:
    """Normalize speaker headings in French verse text."""
    if not text:
        return text

    # Split text into lines/chunks or process with regex
    # We want each canonical speaker on its own line: "<SPEAKER>.\n<text>"
    def replace_speaker(match):
        raw_name = match.group(1).strip().rstrip(".")
        canonical = CANONICAL_SPEAKERS.get(raw_name, raw_name + ".")
        # If match was preceded by something other than start of text or newline, insert newline
        return f"{canonical}\n"

    # Replace speaker occurrences
    res = SPEAKER_RE.sub(replace_speaker, text)
    # If a speaker was replaced, ensure no double newlines or leading spaces right after speaker
    lines = [l.strip() for l in res.split("\n") if l.strip()]
    return "\n".join(lines)


def process_cantique(dry_run: bool = True):
    repo_dir = Path(__file__).resolve().parent.parent
    cantique_dir = repo_dir / "data" / "24_cantique" / "normalized"
    files = sorted(cantique_dir.glob("page_*.json"))

    modified_count = 0

    for path in files:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        verses = data.get("verses", [])
        if not verses:
            continue

        file_changed = False

        # Check for split verse 8:5 on page_0120.json
        if path.name == "page_0120.json" and len(verses) == 2:
            v0, v1 = verses[0], verses[1]
            if v0.get("chapter") == 8 and v0.get("verse_number") == 5 and \
               v1.get("chapter") == 8 and v1.get("verse_number") == 5:
                # Merge into single verse object
                latin_merged = f"{v0['latin'].strip()}\n{v1['latin'].strip()}"
                
                # First part french
                fr0 = v0["french"].strip()
                # strip any leading speaker and §.
                fr0_body = re.sub(r"^LES COMPAGNES DE L'E?POUSE\.\s*(?:§\.\s*)?", "", fr0).strip()
                # Ensure question mark at end if ending with period
                if fr0_body.endswith("."):
                    fr0_body = fr0_body[:-1] + " ?"
                elif not fr0_body.endswith("?"):
                    fr0_body += " ?"

                fr1 = v1["french"].strip()
                fr1_body = re.sub(r"^L'E?POUX\.\s*", "", fr1).strip()

                french_merged = (
                    "LES COMPAGNES DE L'ÉPOUSE.\n"
                    f"{fr0_body}\n"
                    "L'ÉPOUX.\n"
                    f"{fr1_body}"
                )

                merged_verse = {
                    "verse_number": 5,
                    "chapter": 8,
                    "latin": latin_merged,
                    "french": french_merged,
                    "annotations": None
                }
                print(f"[{path.name}] MERGING split verse 8:5:")
                print(f"  Latin: {latin_merged}")
                print(f"  French: {french_merged}")
                data["verses"] = [merged_verse]
                file_changed = True
                verses = data["verses"]

        # Check all verses for speaker normalization
        for v in verses:
            fr = v.get("french") or ""
            new_fr = fix_french_speakers(fr)
            if new_fr != fr:
                print(f"[{path.name}] v.{v.get('chapter')}:{v.get('verse_number')} French speaker fix:")
                print(f"  OLD: {repr(fr)}")
                print(f"  NEW: {repr(new_fr)}")
                v["french"] = new_fr
                file_changed = True

        if file_changed:
            modified_count += 1
            if not dry_run:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                    f.write("\n")

    print(f"\nDone. Files modified: {modified_count} (dry_run={dry_run})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", default=False)
    args = parser.parse_args()
    process_cantique(dry_run=args.dry_run)
