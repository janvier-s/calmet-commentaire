#!/usr/bin/env python3
"""
Pass 1: Validate commentary JSON files and generate diagnostic report.

Usage:
    python validate.py 08_ruth
    python validate.py 01_genese
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from config import (
    BOOK_MAPPINGS,
    EXPECTED_TOP_LEVEL_FIELDS,
    EXPECTED_VERSE_FIELDS,
    EXPECTED_COMMENTARY_FIELDS,
    EXPECTED_FOOTNOTE_FIELDS,
    OCR_ERROR_PATTERNS,
    UNCERTAIN_MARKERS,
)


class ValidationReport:
    """Collects and formats validation results."""

    def __init__(self, book_dir: str, book_name: str, source_dir: str):
        self.book_dir = book_dir
        self.book_name = book_name
        self.source_dir = source_dir
        self.files_found: list[str] = []
        self.json_errors: list[dict] = []
        self.sequence_gaps: list[dict] = []
        self.chapters_detected: list[dict] = []
        self.missing_chapter_summaries: list[dict] = []
        self.verse_normalizations_simple: int = 0  # Count of simple format fixes
        self.verse_normalizations_issues: list[dict] = []  # Actual issues needing review
        self.continuation_commentaries: list[dict] = []
        self.uncertain_markers: list[dict] = []
        self.footnote_ocr_errors: list[dict] = []
        self.unexpected_fields: list[dict] = []
        self.chapter_title_issues: list[dict] = []
        self.missing_chapters: list[dict] = []  # Gaps in chapter sequence
        self.misplaced_chapter_summary: list[dict] = []  # chapter_summary on non-chapter-start pages

    def to_markdown(self) -> str:
        """Generate markdown report."""
        lines = [
            f"# Diagnostic Report: {self.book_name} ({self.book_dir})",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"Source: {self.source_dir}",
            "",
            "## Summary",
            f"- Files found: {len(self.files_found)}",
            f"- JSON parse errors: {len(self.json_errors)}",
            f"- Sequence gaps: {len(self.sequence_gaps)}",
            f"- Chapters detected: {len(self.chapters_detected)}",
            f"- Issues found: {self._total_issues()}",
            "",
        ]

        # File Sequence
        lines.append("## File Sequence")
        if self.files_found:
            first = self.files_found[0]
            last = self.files_found[-1]
            if self.sequence_gaps:
                lines.append(f"Files: {first} to {last} ({len(self.files_found)} files)")
                lines.append("")
                lines.append("**GAPS DETECTED:**")
                for gap in self.sequence_gaps:
                    lines.append(f"- Missing: page_{gap['missing']:04d}.json (between {gap['before']} and {gap['after']})")
            else:
                lines.append(f"Complete: {first} to {last} ({len(self.files_found)} files, no gaps)")
        else:
            lines.append("No files found!")
        lines.append("")

        # Chapter Detection
        lines.append("## Chapter Detection")
        if self.chapters_detected:
            lines.append("| Chapter | Start Page | Detected By | Confidence |")
            lines.append("|---------|------------|-------------|------------|")
            for ch in self.chapters_detected:
                lines.append(f"| {ch['chapter']} | {ch['page']} | {ch['detected_by']} | {ch['confidence']} |")
        else:
            lines.append("No chapters detected.")
        lines.append("")

        # JSON Errors
        lines.append("## Issues")
        lines.append("")
        lines.append(f"### JSON Parse Errors ({len(self.json_errors)})")
        if self.json_errors:
            for err in self.json_errors:
                lines.append(f"- {err['file']}: {err['error']}")
        else:
            lines.append("None")
        lines.append("")

        # Missing Chapter Summaries
        lines.append(f"### Missing Chapter Summaries ({len(self.missing_chapter_summaries)})")
        if self.missing_chapter_summaries:
            lines.append("| Page | Inferred Chapter | chapter_summary |")
            lines.append("|------|------------------|-----------------|")
            for item in self.missing_chapter_summaries:
                lines.append(f"| {item['page']} | {item['chapter']} | NULL |")
        else:
            lines.append("None")
        lines.append("")

        # Misplaced Chapter Summaries
        lines.append(f"### Misplaced Chapter Summaries ({len(self.misplaced_chapter_summary)})")
        if self.misplaced_chapter_summary:
            lines.append("Pages with chapter_summary but NO verse 1 (OCR duplication error):")
            lines.append("")
            for item in self.misplaced_chapter_summary:
                lines.append(f"- **{item['page']}**: \"{item['chapter_summary']}\"")
                lines.append("  - **ACTION**: Delete chapter_summary or move to commentary field")
        else:
            lines.append("None")
        lines.append("")

        # Chapter Title Issues
        lines.append(f"### Chapter Title Issues ({len(self.chapter_title_issues)})")
        if self.chapter_title_issues:
            for item in self.chapter_title_issues:
                lines.append(f"- {item['page']}: {item['issue']}")
        else:
            lines.append("None")
        lines.append("")

        # Missing Chapters
        lines.append(f"### Missing Chapters in Sequence ({len(self.missing_chapters)})")
        if self.missing_chapters:
            for item in self.missing_chapters:
                lines.append(f"- Chapter {item['chapter']}: Expected between chapters {item['before']} and {item['after']}")
        else:
            lines.append("None")
        lines.append("")

        # Verse Number Normalization
        total_normalizations = self.verse_normalizations_simple + len(self.verse_normalizations_issues)
        lines.append(f"### Verse Number Normalization ({total_normalizations})")
        if self.verse_normalizations_simple > 0:
            lines.append(f"- {self.verse_normalizations_simple} simple format fixes (trailing dots, versicle symbols)")
        if self.verse_normalizations_issues:
            lines.append("")
            lines.append("**Issues requiring review:**")
            for item in self.verse_normalizations_issues:
                lines.append(f"- {item['page']}: verse \"{item['original']}\" -> {item['normalized']} ({item['reason']})")
        elif self.verse_normalizations_simple == 0:
            lines.append("None")
        lines.append("")

        # Continuation Commentaries
        lines.append(f"### Continuation Commentaries ({len(self.continuation_commentaries)})")
        if self.continuation_commentaries:
            lines.append(f"Total: {len(self.continuation_commentaries)} continuation commentaries detected")
            lines.append("(These will be merged during transformation to db_ready format)")
        else:
            lines.append("None")
        lines.append("")

        # Uncertain/Illegible Markers
        lines.append(f"### Uncertain/Illegible Markers ({len(self.uncertain_markers)})")
        if self.uncertain_markers:
            for item in self.uncertain_markers:
                lines.append(f"- {item['page']}: {item['field']} contains {item['marker']}")
        else:
            lines.append("None")
        lines.append("")

        # Footnote OCR Errors
        lines.append(f"### Footnote OCR Errors ({len(self.footnote_ocr_errors)})")
        if self.footnote_ocr_errors:
            for item in self.footnote_ocr_errors:
                preview = item['text'][:50] + "..." if len(item['text']) > 50 else item['text']
                lines.append(f"- {item['page']}: footnote ({item['marker']}) contains suspicious pattern: \"{preview}\"")
        else:
            lines.append("None")
        lines.append("")

        # Unexpected Fields
        lines.append(f"### Unexpected JSON Fields ({len(self.unexpected_fields)})")
        if self.unexpected_fields:
            for item in self.unexpected_fields:
                lines.append(f"- {item['page']}: unexpected field \"{item['field']}\" in {item['location']}")
        else:
            lines.append("None")
        lines.append("")

        return "\n".join(lines)

    def _total_issues(self) -> int:
        """Count issues that need manual review (excludes simple normalizations and continuations)."""
        return (
            len(self.json_errors)
            + len(self.sequence_gaps)
            + len(self.missing_chapter_summaries)
            + len(self.misplaced_chapter_summary)
            + len(self.chapter_title_issues)
            + len(self.missing_chapters)
            + len(self.verse_normalizations_issues)
            + len(self.uncertain_markers)
            + len(self.footnote_ocr_errors)
            + len(self.unexpected_fields)
        )


def find_source_dir(book_path: Path) -> Path | None:
    """Find the normalized directory. Requires normalization to have run first."""
    normalized_dir = book_path / "normalized"
    if normalized_dir.exists():
        return normalized_dir
    return None


def get_page_number(filename: str) -> int | None:
    """Extract page number from filename like page_0003.json."""
    match = re.match(r"page_(\d+)\.json", filename)
    if match:
        return int(match.group(1))
    return None


def parse_verse_number(verse_num: str, prev_verse: int | None) -> tuple[int | None, str]:
    """
    Parse verse number string to integer.
    Returns (normalized_number, reason) or (None, error_reason).
    Uses previous verse for context-aware OCR error detection.
    """
    if verse_num is None:
        return None, "null value"

    original = str(verse_num).strip()

    # Remove versicle symbol prefix (℣. or v. or V. or *. for OCR errors)
    cleaned = re.sub(r'^[℣vV\*]\.\s*', '', original)
    # Remove trailing dot
    cleaned = re.sub(r'\.$', '', cleaned)
    cleaned = cleaned.strip()

    # Try direct integer parse
    try:
        num = int(cleaned)
        if original != str(num):
            return num, "format normalized"
        return num, "already normalized"
    except ValueError:
        pass

    # Check for Roman numeral OCR errors (II -> 11, III -> 111, etc.)
    # These look like Roman numerals but are actually OCR errors
    roman_like = re.match(r'^[IilL]+$', cleaned)
    if roman_like and prev_verse is not None:
        # Count the characters - likely OCR of repeated 1s
        likely_num = len(cleaned)
        expected_next = prev_verse + 1

        # Check if interpreting as repeated 1s makes sense
        ones_interpretation = int('1' * len(cleaned)) if len(cleaned) <= 3 else None

        if ones_interpretation and abs(ones_interpretation - expected_next) <= 1:
            return ones_interpretation, f"OCR error ('{cleaned}' -> {ones_interpretation}, follows verse {prev_verse})"

    # Check for lowercase L as 1
    if re.match(r'^l+$', cleaned.lower()):
        num = len(cleaned)
        return num, f"OCR error (lowercase L as 1)"

    return None, f"could not parse: '{original}'"


def check_uncertain_markers(text: str, page: str, field: str, report: ValidationReport):
    """Check for uncertain/illegible markers in text."""
    if text is None:
        return
    for marker in UNCERTAIN_MARKERS:
        if marker in text:
            report.uncertain_markers.append({
                "page": page,
                "field": field,
                "marker": marker,
            })


def check_footnote_ocr_errors(text: str, page: str, marker: str, report: ValidationReport):
    """Check for OCR error patterns in footnote text."""
    if text is None:
        return
    for pattern in OCR_ERROR_PATTERNS:
        if re.search(pattern, text):
            report.footnote_ocr_errors.append({
                "page": page,
                "marker": marker,
                "text": text,
            })
            break  # One match is enough


def check_unexpected_fields(data: dict, expected: set, page: str, location: str, report: ValidationReport):
    """Check for fields not in expected set."""
    for field in data.keys():
        if field not in expected:
            report.unexpected_fields.append({
                "page": page,
                "field": field,
                "location": location,
            })


def validate_file(filepath: Path, report: ValidationReport, prev_file_data: dict | None) -> dict | None:
    """Validate a single JSON file. Returns parsed data or None if error."""
    page_name = filepath.name

    # Try to parse JSON
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        report.json_errors.append({
            "file": page_name,
            "error": str(e),
        })
        return None
    except Exception as e:
        report.json_errors.append({
            "file": page_name,
            "error": f"Read error: {e}",
        })
        return None

    # Check unexpected top-level fields
    check_unexpected_fields(data, EXPECTED_TOP_LEVEL_FIELDS, page_name, "top-level", report)

    # Check verses
    prev_verse_num = None
    if prev_file_data and prev_file_data.get("verses"):
        last_verse = prev_file_data["verses"][-1]
        parsed, _ = parse_verse_number(last_verse.get("verse_number"), None)
        if parsed:
            prev_verse_num = parsed

    for verse in data.get("verses", []):
        check_unexpected_fields(verse, EXPECTED_VERSE_FIELDS, page_name, "verses[]", report)

        verse_num_raw = verse.get("verse_number")
        normalized, reason = parse_verse_number(verse_num_raw, prev_verse_num)

        if normalized is None:
            # Parse error - needs review
            report.verse_normalizations_issues.append({
                "page": page_name,
                "original": verse_num_raw,
                "normalized": "ERROR",
                "reason": reason,
            })
        elif reason == "format normalized":
            # Simple fix (trailing dot, versicle symbol) - just count it
            report.verse_normalizations_simple += 1
        elif reason not in ("already normalized",):
            # OCR error or other issue - needs review
            report.verse_normalizations_issues.append({
                "page": page_name,
                "original": verse_num_raw,
                "normalized": normalized,
                "reason": reason,
            })

        if normalized:
            prev_verse_num = normalized

        # Check for uncertain markers in verse text
        check_uncertain_markers(verse.get("latin"), page_name, "verses[].latin", report)
        check_uncertain_markers(verse.get("french"), page_name, "verses[].french", report)
        check_uncertain_markers(verse.get("annotations"), page_name, "verses[].annotations", report)

    # Check commentary
    for i, comm in enumerate(data.get("commentary", [])):
        check_unexpected_fields(comm, EXPECTED_COMMENTARY_FIELDS, page_name, "commentary[]", report)

        # Check for continuation (null verse_ref with content)
        if comm.get("verse_ref") is None and comm.get("french_commentary"):
            prev_page = "previous file"
            if prev_file_data:
                prev_page = prev_file_data.get("_filename", "previous file")
            report.continuation_commentaries.append({
                "page": page_name,
                "commentary_id": comm.get("commentary_id"),
                "continues_from": prev_page,
            })

        # Check for uncertain markers in commentary
        check_uncertain_markers(comm.get("latin_quote"), page_name, "commentary[].latin_quote", report)
        check_uncertain_markers(comm.get("french_translation"), page_name, "commentary[].french_translation", report)
        check_uncertain_markers(comm.get("french_commentary"), page_name, "commentary[].french_commentary", report)

    # Check footnotes
    for fn in data.get("footnotes", []):
        check_unexpected_fields(fn, EXPECTED_FOOTNOTE_FIELDS, page_name, "footnotes[]", report)
        check_footnote_ocr_errors(fn.get("text"), page_name, fn.get("marker", "?"), report)
        check_uncertain_markers(fn.get("text"), page_name, "footnotes[].text", report)

    # Store filename for reference
    data["_filename"] = page_name

    return data


def detect_chapters(files_data: list[tuple[Path, dict]], report: ValidationReport):
    """Detect chapter boundaries from chapter_number field and verse resets."""
    prev_verse = None
    prev_page = None

    for filepath, data in files_data:
        if data is None:
            continue

        page_name = filepath.name
        # Check both new (chapter_number) and old (chapter_title) field names for backwards compatibility
        chapter_number = data.get("chapter_number") or data.get("chapter_title")
        book_title = data.get("book_title")
        chapter_summary = data.get("chapter_summary")

        # Check for explicit chapter marker in chapter_number OR book_title (common error)
        # Only count as chapter start if it has chapter_summary OR contains verse 1
        # (not just a cross-reference or continuation)

        # chapter_number can be an integer (normalized) or string (legacy)
        chapter_number_extracted = None
        title_to_check = None

        if chapter_number:
            if isinstance(chapter_number, int):
                # Already normalized to integer
                chapter_number_extracted = chapter_number
                title_to_check = f"CHAPITRE {chapter_number}"  # For display
            else:
                # Legacy string format - extract number
                title_to_check = str(chapter_number)
                match = re.search(r'CHAP(?:ITRE)?\.?\s+(\w+)', str(chapter_number).upper())
                if match:
                    chapter_word = match.group(1).rstrip('.')
                    if chapter_word.isdigit():
                        chapter_number_extracted = int(chapter_word)
                    elif chapter_word in ['I', 'PREMIER', 'PREMIÈRE']:
                        chapter_number_extracted = 1
                    else:
                        # Roman numerals (up to 151 for Psalms)
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
                        chapter_number_extracted = roman_map.get(chapter_word)

        # Check book_title for misplaced chapters (common error)
        if not title_to_check and book_title:
            title_to_check = book_title
            match = re.search(r'CHAP(?:ITRE)?\.?\s+(\w+)', book_title.upper())
            if match:
                chapter_word = match.group(1).rstrip('.')
                if chapter_word.isdigit():
                    chapter_number_extracted = int(chapter_word)

        if title_to_check or chapter_number_extracted:
            # Check if this is a real chapter start
            verses = data.get("verses", [])
            contains_verse_1 = False
            for verse in verses:
                verse_num, _ = parse_verse_number(verse.get("verse_number"), None)
                if verse_num == 1:
                    contains_verse_1 = True
                    break

            is_chapter_start = chapter_summary is not None or contains_verse_1

            if is_chapter_start and chapter_number_extracted:
                chapter_word = str(chapter_number_extracted)  # For compatibility below
                chapter_num = parse_chapter_number(chapter_word)
                if chapter_num:
                    # Determine where chapter was found
                    detected_in = "chapter_number field"
                    if not chapter_number and book_title:
                        detected_in = "book_title field (ERROR)"
                        report.chapter_title_issues.append({
                            "page": page_name,
                            "issue": f"Chapter {chapter_num} found in book_title instead of chapter_number",
                        })

                    report.chapters_detected.append({
                        "chapter": chapter_num,
                        "page": page_name,
                        "detected_by": detected_in,
                        "confidence": "HIGH" if chapter_number else "MEDIUM",
                    })

                    # Check if chapter_summary is missing
                    if chapter_summary is None:
                        report.missing_chapter_summaries.append({
                            "page": page_name,
                            "chapter": chapter_num,
                        })

        # Check for misplaced chapter_summary (summary on non-chapter-start page)
        # A page should only have chapter_summary if it has verse 1
        if chapter_summary is not None:
            verses = data.get("verses", [])
            contains_verse_1 = False
            for verse in verses:
                verse_num, _ = parse_verse_number(verse.get("verse_number"), None)
                if verse_num == 1:
                    contains_verse_1 = True
                    break

            if not contains_verse_1:
                # This page has chapter_summary but no verse 1 - OCR error
                report.misplaced_chapter_summary.append({
                    "page": page_name,
                    "chapter_summary": chapter_summary[:100] + "..." if len(chapter_summary) > 100 else chapter_summary,
                })

        # Check for verse reset (indicates new chapter without explicit marker)
        verses = data.get("verses", [])
        if verses:
            first_verse = verses[0].get("verse_number")
            first_num, _ = parse_verse_number(first_verse, None)

            if first_num == 1 and prev_verse and prev_verse > 1:
                # Verse reset detected - new chapter without explicit chapter_number
                if not chapter_number:
                    report.chapters_detected.append({
                        "chapter": "?",
                        "page": page_name,
                        "detected_by": f"verse reset ({prev_verse} -> 1)",
                        "confidence": "MEDIUM",
                    })

                    # This is a missing chapter number
                    report.chapter_title_issues.append({
                        "page": page_name,
                        "issue": f"Verse reset detected ({prev_verse} -> 1) but no chapter_number field",
                    })

            # Track last verse for next iteration
            last_verse = verses[-1].get("verse_number")
            last_num, _ = parse_verse_number(last_verse, None)
            if last_num:
                prev_verse = last_num
                prev_page = page_name

    # Check for gaps in chapter sequence
    chapter_numbers = []
    for ch in report.chapters_detected:
        # Include HIGH and MEDIUM confidence (MEDIUM = found in book_title instead of chapter_number)
        if ch["chapter"] != "?" and ch["confidence"] in ("HIGH", "MEDIUM"):
            chapter_numbers.append(ch["chapter"])

    if chapter_numbers:
        chapter_numbers_sorted = sorted(set(chapter_numbers))
        for i in range(len(chapter_numbers_sorted) - 1):
            current = chapter_numbers_sorted[i]
            next_ch = chapter_numbers_sorted[i + 1]
            if next_ch != current + 1:
                # Gap detected
                for missing in range(current + 1, next_ch):
                    report.missing_chapters.append({
                        "chapter": missing,
                        "before": current,
                        "after": next_ch,
                    })


def parse_chapter_number(word: str) -> int | None:
    """Parse chapter number from word (Roman numeral or French ordinal)."""
    # Common Roman numerals / French ordinals
    mapping = {
        "PREMIER": 1, "PREMIÈRE": 1, "I": 1,
        "SECOND": 2, "SECONDE": 2, "DEUXIÈME": 2, "II": 2,
        "TROISIÈME": 3, "III": 3,
        "QUATRIÈME": 4, "IV": 4,
        "CINQUIÈME": 5, "V": 5,
        "SIXIÈME": 6, "VI": 6,
        "SEPTIÈME": 7, "VII": 7,
        "HUITIÈME": 8, "VIII": 8,
        "NEUVIÈME": 9, "IX": 9,
        "DIXIÈME": 10, "X": 10,
    }

    word_upper = word.upper().strip(".")

    if word_upper in mapping:
        return mapping[word_upper]

    # Try Roman numeral conversion for larger numbers
    try:
        return roman_to_int(word_upper)
    except ValueError:
        pass

    # Try direct integer
    try:
        return int(word_upper)
    except ValueError:
        pass

    return None


def roman_to_int(s: str) -> int:
    """Convert Roman numeral to integer."""
    roman_values = {
        'I': 1, 'V': 5, 'X': 10, 'L': 50,
        'C': 100, 'D': 500, 'M': 1000
    }

    s = s.upper()
    total = 0
    prev_value = 0

    for char in reversed(s):
        if char not in roman_values:
            raise ValueError(f"Invalid Roman numeral character: {char}")
        value = roman_values[char]
        if value < prev_value:
            total -= value
        else:
            total += value
        prev_value = value

    return total


def main():
    if len(sys.argv) < 2:
        print("Usage: python validate.py <book_directory>")
        print("Example: python validate.py 08_ruth")
        sys.exit(1)

    book_dir = sys.argv[1]

    # Determine paths
    script_dir = Path(__file__).parent
    data_dir = script_dir.parent / "data"
    book_path = data_dir / book_dir

    if not book_path.exists():
        print(f"Error: Book directory not found: {book_path}")
        sys.exit(1)

    # Find source directory (21st_*/commentaire)
    source_dir = find_source_dir(book_path)
    if not source_dir:
        print(f"Error: No 21st_*/commentaire directory found in {book_path}")
        sys.exit(1)

    # Get book display name
    book_name = BOOK_MAPPINGS.get(book_dir, book_dir)

    print(f"Validating: {book_name} ({book_dir})")
    print(f"Source: {source_dir}")

    # Initialize report
    report = ValidationReport(
        book_dir=book_dir,
        book_name=book_name,
        source_dir=str(source_dir.relative_to(data_dir)),
    )

    # Find all JSON files
    json_files = sorted(source_dir.glob("page_*.json"))
    report.files_found = [f.name for f in json_files]

    if not json_files:
        print("Error: No page_*.json files found")
        sys.exit(1)

    print(f"Found {len(json_files)} files")

    # Check for sequence gaps
    page_numbers = [get_page_number(f.name) for f in json_files]
    page_numbers = [p for p in page_numbers if p is not None]

    if page_numbers:
        for i in range(len(page_numbers) - 1):
            if page_numbers[i + 1] != page_numbers[i] + 1:
                for missing in range(page_numbers[i] + 1, page_numbers[i + 1]):
                    report.sequence_gaps.append({
                        "missing": missing,
                        "before": f"page_{page_numbers[i]:04d}.json",
                        "after": f"page_{page_numbers[i + 1]:04d}.json",
                    })

    # Validate each file
    files_data: list[tuple[Path, dict | None]] = []
    prev_data = None

    for filepath in json_files:
        data = validate_file(filepath, report, prev_data)
        files_data.append((filepath, data))
        if data is not None:
            prev_data = data

    # Detect chapters
    detect_chapters(files_data, report)

    # Generate report
    report_dir = book_path / "reports" / "commentaire"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "commentaire_diagnostic_report.md"

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report.to_markdown())

    print(f"\nReport written to: {report_path}")
    print(f"Total issues found: {report._total_issues()}")


if __name__ == "__main__":
    main()
