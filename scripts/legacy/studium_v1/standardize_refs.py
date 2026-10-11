#!/usr/bin/env python3
"""
Standardize biblical verse references in normalized page JSON files
with [[...]] markers for website hyperlinking.

Runs AFTER workflow.py has produced clean normalized files.
Works on normalized/ page files (not transformed/chapters/).

Two marker formats:
  [[Josué 3:16]]              — when text IS the reference
  [[verset 17|Josué 8:17]]    — inline shortcode preserving readability

Usage:
    python standardize_refs.py <book_directory> [--dry-run]
    python standardize_refs.py 06_josue --dry-run
    python standardize_refs.py 06_josue
"""

import json
import re
import sys
from functools import partial
from pathlib import Path

# Use strict=False for JSON loading to handle control characters in OCR'd text
_load_json = partial(json.loads, strict=False)

# ---------------------------------------------------------------------------
# Imports from sibling modules
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))

from normalize_refs import (
    ABBREV_MAP, FULL_NAME_MAP, NUMBERED_BOOKS, NUMBERED_REQUIRED,
    is_roman, roman_to_int, to_arabic,
)
from config import BOOK_MAPPINGS

# ---------------------------------------------------------------------------
# Vulgate → Modern French name mapping
# Source text uses Vulgate naming; we convert to modern French.
# ---------------------------------------------------------------------------
VULGATE_TO_MODERN: dict[str, str] = {
    # Rois → Samuel (Vulgate 1-2 Rois = 1-2 Samuel)
    "1 Rois": "1 Samuel",
    "2 Rois": "2 Samuel",
    # Rois → Rois (Vulgate 3-4 Rois = 1-2 Rois/Kings)
    "3 Rois": "1 Rois",
    "4 Rois": "2 Rois",
    # Paralipomènes → Chroniques
    "1 Paralipomènes": "1 Chroniques",
    "2 Paralipomènes": "2 Chroniques",
    "Paralipomènes": "1 Chroniques",  # default if no number
    # Esdras
    "1 Esdras": "Esdras",
    "2 Esdras": "Néhémie",
    # Ecclésiastique → Siracide
    "Ecclésiastique": "Siracide",
}

# Additional abbreviation→modern mappings for Vulgate-era abbreviations
# that normalize_refs.py maps to intermediate names
ABBREV_VULGATE_FIXES: dict[str, str] = {
    # "Rois" from normalize_refs needs Vulgate prefix logic
    # "Chroniques" from normalize_refs — handled via Paralipomènes
}

# ---------------------------------------------------------------------------
# French written-out numbers
# ---------------------------------------------------------------------------
FRENCH_NUMBERS: dict[str, int] = {
    "premier": 1, "première": 1, "un": 1, "une": 1,
    "deuxième": 2, "second": 2, "seconde": 2, "deux": 2,
    "troisième": 3, "trois": 3,
    "quatrième": 4, "quatre": 4,
    "cinquième": 5, "cinq": 5,
    "sixième": 6, "six": 6,
    "septième": 7, "sept": 7,
    "huitième": 8, "huit": 8,
    "neuvième": 9, "neuf": 9,
    "dixième": 10, "dix": 10,
    "onzième": 11, "onze": 11,
    "douzième": 12, "douze": 12,
    "treizième": 13, "treize": 13,
    "quatorzième": 14, "quatorze": 14,
    "quinzième": 15, "quinze": 15,
    "seizième": 16, "seize": 16,
    "dix-septième": 17, "dix-sept": 17,
    "dix-huitième": 18, "dix-huit": 18,
    "dix-neuvième": 19, "dix-neuf": 19,
    "vingtième": 20, "vingt": 20,
    "vingt-et-unième": 21, "vingt et unième": 21, "vingt-unième": 21,
    "vingt-deuxième": 22, "vingt-troisième": 23, "vingt-quatrième": 24,
    "vingt-cinquième": 25, "vingt-sixième": 26, "vingt-septième": 27,
    "vingt-huitième": 28, "vingt-neuvième": 29,
    "trentième": 30, "trente": 30,
    "trente-et-unième": 31, "trente et unième": 31,
    "quarantième": 40, "quarante": 40,
    "cinquantième": 50, "cinquante": 50,
}

# Build regex for French number matching (longest first)
_FRENCH_NUM_ALT = "|".join(
    re.escape(k) for k in sorted(FRENCH_NUMBERS.keys(), key=len, reverse=True)
)

# ---------------------------------------------------------------------------
# All canonical book names (for bare reference wrapping)
# ---------------------------------------------------------------------------
_ALL_BOOK_NAMES: set[str] = set()
_ALL_BOOK_NAMES.update(ABBREV_MAP.values())
_ALL_BOOK_NAMES.update(FULL_NAME_MAP.values())
_ALL_BOOK_NAMES.update(VULGATE_TO_MODERN.values())
# Add numbered variants
for name in list(_ALL_BOOK_NAMES):
    if name in NUMBERED_BOOKS:
        for n in range(1, 5):
            _ALL_BOOK_NAMES.add(f"{n} {name}")
# Add specific names that appear in source text
_ALL_BOOK_NAMES.update([
    "1 Samuel", "2 Samuel", "1 Rois", "2 Rois",
    "1 Chroniques", "2 Chroniques", "Siracide",
    "Esdras", "Néhémie",
])

# Build sorted list for regex (longest first to avoid partial matches)
_BOOK_NAMES_SORTED = sorted(_ALL_BOOK_NAMES, key=len, reverse=True)
_BOOK_NAMES_ALT = "|".join(re.escape(n) for n in _BOOK_NAMES_SORTED)

# Also build list including Vulgate names that appear in source
_VULGATE_NAMES = [
    "Paralipomènes", "1 Paralipomènes", "2 Paralipomènes",
    "Ecclésiastique",
]
_ALL_SOURCE_NAMES = _BOOK_NAMES_SORTED + sorted(
    _VULGATE_NAMES, key=len, reverse=True
)
_ALL_SOURCE_NAMES_ALT = "|".join(re.escape(n) for n in _ALL_SOURCE_NAMES)


# ---------------------------------------------------------------------------
# Verse formatting
# ---------------------------------------------------------------------------
def format_verses(verse_numbers: list[int]) -> str:
    """
    Format verse numbers with en-dash ranges and comma separation.

    [9,10,11,12]       → "9–12"
    [9,10,14,16]       → "9–10,14,16"
    [9,10,14,15,16]    → "9–10,14–16"
    [14,44]            → "14,44"
    [16]               → "16"
    [3,4,5,8,9,10,15]  → "3–5,8–10,15"
    """
    if not verse_numbers:
        return ""
    verses = sorted(set(verse_numbers))
    groups: list[list[int]] = []
    current_group: list[int] = [verses[0]]

    for v in verses[1:]:
        if v == current_group[-1] + 1:
            current_group.append(v)
        else:
            groups.append(current_group)
            current_group = [v]
    groups.append(current_group)

    parts = []
    for g in groups:
        if len(g) == 1:
            parts.append(str(g[0]))
        else:
            parts.append(f"{g[0]}\u2013{g[-1]}")  # en-dash
    return ",".join(parts)


def parse_verse_list(text: str) -> list[int]:
    """
    Parse verse numbers from patterns like "9. 10. 11. 12." or "9, 10, 14, 16"
    or "9. et 10." or "9. 10. et 14. 16."
    """
    # Remove "et" and other connectors
    cleaned = re.sub(r'\bet\b', '', text)
    # Find all numbers
    numbers = [int(m.group()) for m in re.finditer(r'\d+', cleaned)]
    return numbers


# ---------------------------------------------------------------------------
# Build abbreviation pattern for Layer 1
# (Ported from normalize_refs.py but outputs [[...]] markers)
# ---------------------------------------------------------------------------
def _build_abbrev_alt() -> str:
    keys = sorted(ABBREV_MAP.keys(), key=len, reverse=True)
    return "|".join(re.escape(k) for k in keys)


def _build_fullname_alt() -> str:
    # Include Vulgate names too
    all_names = dict(FULL_NAME_MAP)
    all_names["paralipomènes"] = "Paralipomènes"
    all_names["paralipomenes"] = "Paralipomènes"
    all_names["rois"] = "Rois"
    all_names["samuel"] = "Samuel"
    all_names["siracide"] = "Siracide"
    all_names["psaume"] = "Psaumes"
    keys = sorted(all_names.keys(), key=len, reverse=True)
    return "|".join(re.escape(k) for k in keys)


_ABBREV_ALT = _build_abbrev_alt()
_FULLNAME_ALT = _build_fullname_alt()
_NUM = r'(?:[IVXLCDM]+|\d+)'

# Extra-verses lookaheads: prevent capturing a number that is actually:
#   - a chapter:verse separator (e.g. ", 14:21" → chapter 14, verse 21)
#   - a numbered book prefix + abbreviation (e.g. ". 1 Par." → 1 Paralipomènes)
_EXTRA_V_LOOKAHEAD = (
    r'(?!\d)'                                          # prevent partial-number backtracking (e.g. "43" → "4")
    r'(?!\d*:\d)'                                      # not ch:v (e.g. ", 14:21")
    r'(?!\s+[A-Z][a-zA-Z\u00C0-\u00FF]*\.)'            # not prefix + abbreviation (e.g. ". 1 Par.")
    r'(?!\s+[A-Z][a-zA-Z\u00C0-\u00FF]{2,}\s+\d)'     # not prefix + full name (e.g. ", 1 Rois 14")
    r'(?!\.\s+[A-Z][a-zA-Z\u00C0-\u00FF]*\.)'         # not ". Abbrev." (e.g. "2. Esdr.", "5. I. Par.")
)

# Pattern for abbreviated references: [prefix] Abbrev. chapter. verse.
_PAT_ABBREV = re.compile(
    r'(?:_\s*)?'
    r'(?:(?:^|(?<=\s)|(?<=\.)|(?<=,))([1-4]|[IV]{1,3})[.,]?\s+)?'
    r'(?<![A-Za-z\u00C0-\u00FF\u017F0-9])'
    r'(' + _ABBREV_ALT + r')'
    r'(?:\s*_)?'
    r'\.\s*'
    r'(?:_\s*)?'
    r'(?='
        r'(?:[IVXLCDM]+[\.\s:]|\d+[\.\s:]|\s*$)'
    r')'
    r'(?:'
        r'(?:c\.?\s+|ch\.?\s+|chap\.?\s+)?'
        r'(' + _NUM + r')'
        r'(?:'
            r'(?:[\.:,]\s*)'
            r'(?:v\.?\s*|\u2123\.?\s*|verset\s+)?'
            r'(' + _NUM + r')'
            r'((?:\s*[,\.]\s*\d+' + _EXTRA_V_LOOKAHEAD + r')*)'
            r'(?:\s*[-\u2013]\s*(\d+))?'
        r')?'
    r')?',
    re.IGNORECASE
)

# Pattern for full-name references: [prefix] BookName chapter:verse
# The chapter number must be followed by a non-letter (to avoid "Jean Lucidius" → "Jean L")
_PAT_FULLNAME = re.compile(
    r'(?:_)?'
    r'(?:([1-4])\s+(?:des?\s+)?)?'
    r'\b(' + _FULLNAME_ALT + r')\b'
    r'(?:_)?'
    r'(?:\s*,?\s*(?:chapitres?\s+|ch(?:ap)?\.?\s+)|\s+)'  # optional "chapitre" between book and chapter
    r'(' + _NUM + r')'
    r'(?=[:\s,.\d;)\]\-]|$)'   # chapter must be followed by punctuation/space/digit, not a letter
    r'(?:'
        r'(?:\s*:\s*|\s*,\s+|\.\s+(?=\d))'  # colon, comma, or period (period only before digit)
        r'(\d+)'
        r'((?:\s*[,\.]\s*\d+' + _EXTRA_V_LOOKAHEAD + r')*)'
        r'(?:\s*[-\u2013]\s*(\d+))?'
    r')?',
    re.IGNORECASE
)

# Ibid / Id pattern
_IBID_PATTERN = re.compile(
    r'\b(Ibid(?:em)?|Id(?:em)?)\.'
    r'(?:\s*(?:c\.?\s*)?'
    r'(' + _NUM + r')'
    r'(?:\s*[,:]\s*(?:v\.?\s*|\u2123\.?\s*)?(' + _NUM + r'))?'
    r')?',
    re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Full-name map extended with Vulgate entries
# ---------------------------------------------------------------------------
_EXTENDED_FULL_NAME_MAP = dict(FULL_NAME_MAP)
_EXTENDED_FULL_NAME_MAP["paralipomènes"] = "Paralipomènes"
_EXTENDED_FULL_NAME_MAP["paralipomenes"] = "Paralipomènes"
_EXTENDED_FULL_NAME_MAP["rois"] = "Rois"
_EXTENDED_FULL_NAME_MAP["samuel"] = "Samuel"
_EXTENDED_FULL_NAME_MAP["siracide"] = "Siracide"
_EXTENDED_FULL_NAME_MAP["psaume"] = "Psaumes"


# ---------------------------------------------------------------------------
# PageRefNormalizer
# ---------------------------------------------------------------------------
class PageRefNormalizer:
    """Normalizes biblical references in normalized page JSON files."""

    def __init__(self):
        self.current_book: str | None = None       # e.g. "Josué"
        self.current_chapter: int | None = None     # e.g. 3
        self.last_ref_book: str | None = None       # last referenced book
        self.last_ref_chapter: str | None = None    # last referenced chapter

    def set_context(self, book: str, chapter: int | None):
        """Set the current book/chapter context from page metadata."""
        self.current_book = book
        self.current_chapter = chapter

    def _apply_vulgate(self, name: str) -> str:
        """Convert Vulgate name to modern if applicable."""
        return VULGATE_TO_MODERN.get(name, name)

    def _resolve_book(self, prefix: str | None, abbrev: str,
                      lookup: dict[str, str]) -> str | None:
        """Resolve abbreviation/name to canonical book name."""
        key = abbrev.lower()
        canonical = lookup.get(key) or lookup.get(key.replace("\u017F", "s"))
        if not canonical:
            return None

        if canonical in NUMBERED_BOOKS or canonical in ("Paralipomènes", "Samuel"):
            if prefix:
                num = to_arabic(prefix)
                full = f"{num} {canonical}"
                return self._apply_vulgate(full)
            elif canonical in NUMBERED_REQUIRED:
                return None
            else:
                return self._apply_vulgate(canonical)
        return self._apply_vulgate(canonical)

    def _format_ref(self, book: str, chapter: int | str,
                    verses: list[int] | None = None) -> str:
        """Build standardized reference string: Book chapter:verses or Book chapter"""
        ch = to_arabic(str(chapter)) if not isinstance(chapter, int) else str(chapter)
        if verses:
            return f"{book} {ch}:{format_verses(verses)}"
        return f"{book} {ch}"

    def _parse_extra_verses(self, more: str | None) -> list[int]:
        """Parse additional verse numbers from comma/dot-separated string."""
        if not more:
            return []
        return [int(m.group()) for m in re.finditer(r'\d+', more)]

    def _build_verse_list(self, first: str | None, more: str | None,
                          range_end: str | None) -> list[int] | None:
        """Build verse list from parsed groups."""
        if not first:
            return None
        verses = [int(to_arabic(first))]
        verses.extend(self._parse_extra_verses(more))
        if range_end:
            end = int(range_end)
            start = verses[-1] if verses else 0
            # Expand range
            for v in range(start + 1, end + 1):
                if v not in verses:
                    verses.append(v)
        return verses

    # -----------------------------------------------------------------------
    # Layer 1: Explicit book + chapter + verse abbreviations
    # -----------------------------------------------------------------------
    def _layer1_replace_abbrev(self, m: re.Match) -> str:
        prefix = m.group(1)
        abbrev = m.group(2)

        # Safety: abbreviation must not be part of a larger word
        start = m.start()
        text = m.string
        abbrev_start = text.find(abbrev, start, m.end())
        if abbrev_start is None:
            abbrev_start = start
        if abbrev_start > 0 and text[abbrev_start - 1].isalpha():
            return m.group(0)

        book = self._resolve_book(prefix, abbrev, ABBREV_MAP)
        if book is None:
            return m.group(0)

        chapter_raw = m.group(3)
        if chapter_raw and chapter_raw == chapter_raw.lower() and is_roman(chapter_raw):
            return m.group(0)

        verse_raw = m.group(4) if m.lastindex and m.lastindex >= 4 else None
        more = m.group(5) if m.lastindex and m.lastindex >= 5 else None
        range_end = m.group(6) if m.lastindex and m.lastindex >= 6 else None

        if chapter_raw:
            ch = int(to_arabic(chapter_raw))
            # Sanity check: chapter number should be reasonable (1-150)
            if ch < 1 or ch > 150:
                return m.group(0)
            verses = self._build_verse_list(
                to_arabic(verse_raw) if verse_raw else None, more, range_end
            )
            self.last_ref_book = book
            self.last_ref_chapter = str(ch)
            return f"[[{self._format_ref(book, ch, verses)}]]"

        self.last_ref_book = book
        return m.group(0)  # book only, no chapter — leave as-is

    def _layer1_replace_fullname(self, m: re.Match) -> str:
        # Skip if already inside [[...]]
        start = m.start()
        preceding = m.string[:start]
        if preceding.count("[[") > preceding.count("]]"):
            return m.group(0)

        prefix = m.group(1)
        name = m.group(2)
        book = self._resolve_book(prefix, name, _EXTENDED_FULL_NAME_MAP)
        if book is None:
            return m.group(0)

        chapter_raw = m.group(3)

        # Reject lowercase Roman numerals (e.g. "m" from "mettaient")
        if chapter_raw and is_roman(chapter_raw) and chapter_raw != chapter_raw.upper():
            return m.group(0)

        # Sanity check: chapter number should be reasonable (1-150)
        ch = int(to_arabic(chapter_raw))
        if ch < 1 or ch > 150:
            return m.group(0)

        verse_raw = m.group(4) if m.lastindex and m.lastindex >= 4 else None
        more = m.group(5) if m.lastindex and m.lastindex >= 5 else None
        range_end = m.group(6) if m.lastindex and m.lastindex >= 6 else None

        verses = self._build_verse_list(
            to_arabic(verse_raw) if verse_raw else None, more, range_end
        )

        self.last_ref_book = book
        self.last_ref_chapter = str(ch)

        return f"[[{self._format_ref(book, ch, verses)}]]"

    def _layer1_explicit_refs(self, text: str) -> str:
        """Layer 1: Convert explicit book abbreviations/names to [[ref]]."""
        text = _PAT_ABBREV.sub(self._layer1_replace_abbrev, text)
        text = _PAT_FULLNAME.sub(self._layer1_replace_fullname, text)
        return text

    # -----------------------------------------------------------------------
    # Layer 2: French inline references
    # -----------------------------------------------------------------------

    def _get_book_context(self) -> str | None:
        """Get current book for context-relative references."""
        return self.current_book

    # Person-name indicators: if a book name is preceded by these,
    # it's likely a person's name, not a book reference
    _PERSON_INDICATORS = re.compile(
        r'(?:nomm[ée]e?|appel[ée]e?|fils\s+de|fille\s+de|femme\s+de'
        r'|nommé|appelé|dit)\s*$',
        re.IGNORECASE
    )

    # Pattern for numbered prefix before book name:
    #   "3 des Rois", "troisième des Rois", "IV de Rois"
    #   "première Épître Pierre", "2 Épître aux Corinthiens"
    _NUMBERED_PREFIX_PAT = re.compile(
        r'(?:(\d)|([IV]{1,3})|(' + _FRENCH_NUM_ALT + r'))\s+'
        r'(?:'
            r'[ÉéEe]p[iî]tres?\s+(?:de\s+|du\s+|des\s+|aux\s+)?(?:[Ss]ainte?\s+)?'
            r'|livre\s+(?:de\s+|du\s+|des\s+)?'
            r'|des?\s+'
        r')?$',
        re.IGNORECASE
    )

    # Pattern for ordinal + "Épître" AFTER the book name:
    #   "Pierre... première Épître chapitre 3" → "1 Pierre"
    _EPITRE_AFTER_PAT = re.compile(
        r'(?:(\d)|([IV]{1,3})|(' + _FRENCH_NUM_ALT + r'))\s+'
        r'[ÉéEe]p[iî]tres?',
        re.IGNORECASE
    )

    @staticmethod
    def _extract_num_from_match(m) -> int | None:
        """Extract a number (1-4) from a numbered prefix/épître match."""
        if m.group(1):       # digit
            num = int(m.group(1))
        elif m.group(2):     # Roman numeral
            num = int(to_arabic(m.group(2)))
        else:                # French number word
            num = FRENCH_NUMBERS.get(m.group(3).lower())
        return num if num and 1 <= num <= 4 else None

    def _try_numbered_book(self, snippet, best_pos, best_name_len,
                           best_canonical) -> str | None:
        """Try to resolve a numbered book prefix/suffix. Returns full name or None."""
        if not best_canonical:
            return None
        if (best_canonical not in NUMBERED_BOOKS
                and best_canonical not in ("Paralipomènes", "Samuel", "Rois")):
            return None
        # Check BEFORE book name: "troisième des", "seconde Épître de saint"
        before_raw = snippet[:best_pos]
        prefix_m = self._NUMBERED_PREFIX_PAT.search(before_raw)
        if prefix_m:
            num = self._extract_num_from_match(prefix_m)
            if num:
                return self._apply_vulgate(f"{num} {best_canonical}")
        # Check AFTER book name: "Pierre... première Épître"
        after_book = snippet[best_pos + best_name_len:]
        epitre_m = self._EPITRE_AFTER_PAT.search(after_book)
        if epitre_m:
            num = self._extract_num_from_match(epitre_m)
            if num:
                return self._apply_vulgate(f"{num} {best_canonical}")
        return None

    def _find_preceding_book(self, preceding_text: str) -> str | None:
        """Find the last book name in the preceding text (within ~80 chars)."""
        snippet = preceding_text[-80:]
        best_pos = -1
        best_book = None
        best_canonical = None  # pre-Vulgate canonical name
        best_name_len = 0
        # Check canonical book names
        for name in _BOOK_NAMES_SORTED:
            idx = snippet.rfind(name)
            if idx >= 0 and idx > best_pos:
                best_pos = idx
                best_canonical = name
                best_book = self._apply_vulgate(name)
                best_name_len = len(name)
        # Also check FULL_NAME_MAP entries (case-insensitive)
        snippet_lower = snippet.lower()
        for key, canonical in _EXTENDED_FULL_NAME_MAP.items():
            idx = snippet_lower.rfind(key)
            if idx >= 0 and idx > best_pos:
                best_pos = idx
                best_canonical = canonical
                best_book = self._apply_vulgate(canonical)
                best_name_len = len(key)
        if not best_book or best_pos < 0:
            return None
        # Try numbered prefix/suffix BEFORE person indicators
        # (so "seconde Épître de saint Pierre" resolves instead of being
        # rejected by the "saint" person indicator)
        numbered = self._try_numbered_book(
            snippet, best_pos, best_name_len, best_canonical)
        if numbered:
            return numbered
        # Reject if the book name is preceded by person-name indicators
        before_name = snippet[:best_pos].rstrip()
        if self._PERSON_INDICATORS.search(before_name):
            return None
        # If book requires a number and none found, skip
        if best_canonical in NUMBERED_REQUIRED:
            return None
        return best_book

    def _get_chapter_context(self) -> int | None:
        """Get current chapter for context-relative references."""
        return self.current_chapter

    def _layer2_french_inline(self, text: str) -> str:
        """Layer 2: Handle French inline references."""

        # --- 2a: "chapitre N:V du/de/des BookName" ---
        # e.g. "chapitre 20:10 du Deutéronome"
        pat_chap_verse_book = re.compile(
            r'(chapitres?\s+)'
            r'(\d+|[IVXLCDM]+)'       # chapter
            r'(?:\s*:\s*|\s+verset\s+)'
            r'(\d+|[IVXLCDM]+)'       # verse
            r'((?:\s*[\.]\s*\d+)*)'   # extra verses
            r'(?:\s*[-\u2013]\s*(\d+))?'  # range end (e.g. 12-13)
            r'\s+(du|de|des|de\s+la|de\s+l\'|du\s+livre\s+(?:du|de|des|de\s+la))\s+'
            r'(' + _ALL_SOURCE_NAMES_ALT + r')',
            re.IGNORECASE
        )
        def repl_chap_verse_book(m):
            ch = int(to_arabic(m.group(2)))
            v_first = int(to_arabic(m.group(3)))
            extra = self._parse_extra_verses(m.group(4))
            range_end = m.group(5)
            verses = [v_first] + extra
            if range_end:
                v_end = int(range_end)
                if v_end > verses[-1]:
                    verses = verses + list(range(verses[-1] + 1, v_end + 1))
            connector = m.group(6)  # "du", "de la", "des", etc.
            book_raw = m.group(7)
            book = self._apply_vulgate(book_raw)
            # Try to resolve via FULL_NAME_MAP
            resolved = _EXTENDED_FULL_NAME_MAP.get(book_raw.lower())
            if resolved:
                book = self._apply_vulgate(resolved)
            self.last_ref_book = book
            self.last_ref_chapter = str(ch)
            ref = self._format_ref(book, ch, verses)
            # Preserve original connector in display
            chap_word = m.group(1).rstrip()
            display = f"{chap_word} {ch}:{format_verses(verses)} {connector} {book_raw}"
            return f"[[{display}|{ref}]]"
        text = pat_chap_verse_book.sub(repl_chap_verse_book, text)

        # --- 2b: "chapitre N verset(s) V [et V2...] [de ce Livre/chapitre]" ---
        # e.g. "chapitre 10 verset 3", "Chapitre XIX. verset 35"
        pat_chap_verset = re.compile(
            r'(chapitres?\s+)'
            r'(\d+|[IVXLCDM]+)'           # chapter (Roman OK — uppercase checked in handler)
            r'(?:\s*[,.:]?\s*)'            # separator: comma, period, colon, or space
            r'(versets?\s+)'
            r'(\d+)'                       # first verse (digits only)
            r'((?:\s*\.?\s*(?:et\s+)?\d+\.?)*)'  # more verses (digits only)
            r'(?:\s*[-\u2013]\s*(\d+))?'   # range end (e.g. 19-20)
            r'(\s+de\s+ce\s+(?:Livre|chapitre))?',
            re.IGNORECASE
        )
        def repl_chap_verset(m):
            raw = m.group(0)
            # Check if inside [[...]]
            start = m.start()
            preceding = m.string[:start]
            if preceding.count("[[") > preceding.count("]]"):
                return raw
            ch_raw = m.group(2)
            # Reject lowercase Roman (e.g. "chapitre il verset...")
            if is_roman(ch_raw) and ch_raw != ch_raw.upper():
                return raw
            ch = int(to_arabic(ch_raw))
            if ch < 1 or ch > 150:
                return raw
            v_first = int(m.group(4))
            extra_text = m.group(5) or ""
            extra = parse_verse_list(extra_text)
            range_end = m.group(6)  # range end (e.g. "20" from "19-20")
            verses = [v_first] + extra
            if range_end:
                end = int(range_end)
                last = verses[-1] if verses else v_first
                for v in range(last + 1, end + 1):
                    if v not in verses:
                        verses.append(v)
            # Check for preceding book name first
            book = self._find_preceding_book(preceding)
            book_from_text = book is not None
            if not book:
                book = self._get_book_context()
            if not book:
                return raw
            self.last_ref_chapter = str(ch)
            ref = self._format_ref(book, ch, verses)
            if book_from_text:
                # Book explicitly mentioned → direct format
                return f"[[{ref}]]"
            # Standardized display: "chapitre N:V [de ce Livre]"
            chap_word = m.group(1).rstrip()
            suffix = m.group(7) or ""
            display = f"{chap_word} {ch}:{format_verses(verses)}{suffix}"
            return f"[[{display}|{ref}]]"
        text = pat_chap_verset.sub(repl_chap_verset, text)

        # --- 2c: "Chapitre N:V[.V.V...]" (with colon, no book) ---
        # e.g. "Chapitre 10:9. 10. 11. 12"
        pat_chap_colon = re.compile(
            r'(Chapitres?\s+)'
            r'(\d+|[IVXLCDM]+)'         # chapter
            r'\s*:\s*'
            r'(\d+)'                     # first verse
            r'((?:\s*\.?\s*(?:et\s+)?\d+\.?)*)',  # more verses
            re.IGNORECASE
        )
        def repl_chap_colon(m):
            raw = m.group(0)
            # Check if inside [[...]]
            start = m.start()
            preceding = m.string[:start]
            if preceding.count("[[") > preceding.count("]]"):
                return raw
            ch = int(to_arabic(m.group(2)))
            v_first = int(m.group(3))
            extra_text = m.group(4) or ""
            extra = parse_verse_list(extra_text)
            verses = [v_first] + extra
            book = self._find_preceding_book(preceding)
            book_from_text = book is not None
            if not book:
                book = self._get_book_context()
            if not book:
                return raw
            self.last_ref_chapter = str(ch)
            ref = self._format_ref(book, ch, verses)
            if book_from_text:
                return f"[[{ref}]]"
            # Standardized display: "chapitre N:V"
            chap_word = m.group(1).rstrip()
            display = f"{chap_word} {ch}:{format_verses(verses)}"
            return f"[[{display}|{ref}]]"
        text = pat_chap_colon.sub(repl_chap_colon, text)

        # --- 2d: "verset(s) V [et V2...] [du] chapitre N [du/de Book]" ---
        # e.g. "verset 4 du chapitre 13", "versets 10 et 11 de ce chapitre",
        #       "verset 9 chapitre 38" (no preposition)
        pat_verset_du_chap = re.compile(
            r'(versets?\s+)'
            r'(\d+)'                         # first verse (digits only)
            r'((?:\s*\.?\s*(?:et\s+)?\d+\.?)*)'  # more verses (digits only)
            r'\s+(?:(?:du|de)\s+)?'          # optional preposition
            r'(?:'
                r'ce\s+chapitre'             # "de ce chapitre"
                r'|chapitre\s+(\d+|[IVXLCDM]+)'  # "[du] chapitre N"
                r'(?:\s+(?:du|de|des|du\s+livre\s+(?:du|de|des))\s+(' + _ALL_SOURCE_NAMES_ALT + r'))?'
            r')',
            re.IGNORECASE
        )
        def repl_verset_du_chap(m):
            raw = m.group(0)
            v_first = int(to_arabic(m.group(2)))
            extra_text = m.group(3) or ""
            extra = parse_verse_list(extra_text)
            verses = [v_first] + extra

            chap_raw = m.group(4)
            book_raw = m.group(5)

            if chap_raw:
                ch = int(to_arabic(chap_raw))
            else:
                # "de ce chapitre" → use current chapter
                ch = self._get_chapter_context()
                if ch is None:
                    return raw

            if book_raw:
                resolved = _EXTENDED_FULL_NAME_MAP.get(book_raw.lower())
                book = self._apply_vulgate(resolved if resolved else book_raw)
            else:
                book = self._get_book_context()
            if not book:
                return raw

            self.last_ref_book = book
            self.last_ref_chapter = str(ch)
            ref = self._format_ref(book, ch, verses)
            # Standardized display with Arabic numbers
            v_str = format_verses(verses)
            if chap_raw:
                if book_raw:
                    display = f"chapitre {ch}:{v_str} du {book_raw}"
                else:
                    display = f"chapitre {ch}:{v_str}"
            else:
                display = f"verset {v_str} de ce chapitre"
            return f"[[{display}|{ref}]]"
        text = pat_verset_du_chap.sub(repl_verset_du_chap, text)

        # --- 2e: "verset(s) V [et V2...]" (standalone, uses current context) ---
        # e.g. "au verset 17", "verset 2"
        # Must NOT match if already inside [[...]]
        pat_verset_standalone = re.compile(
            r'(?<!\|)'                       # not after pipe (already in marker)
            r'(?<!\[)'                       # not after [
            r'(versets?\s+)'
            r'(\d+)'                         # first verse (digits only for standalone)
            r'((?:\s*\.?\s*(?:et\s+)?\d+\.?)*)'  # more verses (digits only)
            r'(?!\s+(?:du|de)\s+(?:ce\s+)?chapitre)'  # not followed by "du chapitre"
            r'(?!\|)',                       # not before pipe
            re.IGNORECASE
        )
        _PAT_CHAP_DIRECTION = re.compile(
            r'chapitre\s+(suivant|pr[ée]c[ée]dent)',
            re.IGNORECASE
        )
        # Pattern to detect "chapitre N" (with optional "de ce livre/Livre")
        # recently mentioned in preceding text
        _PAT_RECENT_CHAPTER = re.compile(
            r'chapitre\s+(\d+|[IVXLCDM]+)',
            re.IGNORECASE
        )
        def repl_verset_standalone(m):
            raw = m.group(0)
            # Check if we're inside [[ ]] already
            start = m.start()
            preceding = m.string[:start]
            # Count unmatched [[ before this position
            open_count = preceding.count("[[") - preceding.count("]]")
            if open_count > 0:
                return raw

            v_first = int(to_arabic(m.group(2)))
            # Sanity: biblical verses don't exceed ~176 (Psalm 119)
            if v_first > 200:
                return raw
            extra_text = m.group(3) or ""
            extra = parse_verse_list(extra_text)
            verses = [v_first] + extra

            book = self._get_book_context()
            ch = self._get_chapter_context()
            if not book or ch is None:
                return raw

            # Check for "chapitre suivant/précédent" in recent preceding text
            snippet = preceding[-80:]
            dir_match = _PAT_CHAP_DIRECTION.search(snippet)
            if dir_match and ch is not None:
                direction = dir_match.group(1).lower()
                if "suiv" in direction:
                    ch = ch + 1
                else:
                    ch = ch - 1
                    if ch < 1:
                        return raw
            else:
                # Check for recently-mentioned "chapitre N" in preceding text
                # to use that chapter instead of the page's current chapter
                recent_snippet = preceding[-120:]
                recent_ch_matches = list(_PAT_RECENT_CHAPTER.finditer(recent_snippet))
                if recent_ch_matches:
                    last_ch_match = recent_ch_matches[-1]
                    ch_raw = last_ch_match.group(1)
                    if is_roman(ch_raw) and ch_raw == ch_raw.upper():
                        recent_ch = int(to_arabic(ch_raw))
                    elif ch_raw.isdigit():
                        recent_ch = int(ch_raw)
                    else:
                        recent_ch = None
                    if recent_ch and 1 <= recent_ch <= 150:
                        ch = recent_ch

            ref = self._format_ref(book, ch, verses)
            # Standardized display
            v_word = m.group(1).rstrip()
            display = f"{v_word} {format_verses(verses)}"
            return f"[[{display}|{ref}]]"
        text = pat_verset_standalone.sub(repl_verset_standalone, text)

        # NOTE: "chapitre suivant/précédent" is NOT wrapped as a standalone
        # reference. It only influences verset resolution (handled above in 2e)
        # and in pattern 2g ("verset N du chapitre suivant").

        # --- 2g: "verset N du chapitre suivant/précédent" ---
        pat_verset_chap_rel = re.compile(
            r'(versets?\s+)'
            r'(\d+)'                         # first verse (digits only)
            r'((?:\s*\.?\s*(?:et\s+)?\d+\.?)*)'  # more verses (digits only)
            r'\s+du\s+chapitre\s+(suivant|pr[ée]c[ée]dent)',
            re.IGNORECASE
        )
        def repl_verset_chap_rel(m):
            raw = m.group(0)
            v_first = int(to_arabic(m.group(2)))
            extra_text = m.group(3) or ""
            extra = parse_verse_list(extra_text)
            verses = [v_first] + extra
            direction = m.group(4).lower()

            book = self._get_book_context()
            ch = self._get_chapter_context()
            if not book or ch is None:
                return raw

            if "suiv" in direction:
                target_ch = ch + 1
            else:
                target_ch = ch - 1
                if target_ch < 1:
                    return raw

            ref = self._format_ref(book, target_ch, verses)
            # Standardized display
            v_word = m.group(1).rstrip()
            dir_word = m.group(4)
            display = f"{v_word} {format_verses(verses)} du chapitre {dir_word}"
            return f"[[{display}|{ref}]]"
        text = pat_verset_chap_rel.sub(repl_verset_chap_rel, text)

        # --- 2h: "Chapitre dix-huitième" / "premier chapitre [du/des Book]" ---
        pat_chap_french_num = re.compile(
            r'(chapitres?\s+(' + _FRENCH_NUM_ALT + r'))'
            r'(?:\s+(?:du|de|des|du\s+livre\s+(?:du|de|des))\s+'
            r'(' + _ALL_SOURCE_NAMES_ALT + r'))?',
            re.IGNORECASE
        )
        def repl_chap_french_num(m):
            full_display = m.group(0)
            num_text = m.group(2).lower()
            book_raw = m.group(3)

            ch = FRENCH_NUMBERS.get(num_text)
            if ch is None:
                return full_display

            if book_raw:
                resolved = _EXTENDED_FULL_NAME_MAP.get(book_raw.lower())
                book = self._apply_vulgate(resolved if resolved else book_raw)
            else:
                book = self._get_book_context()
            if not book:
                return full_display

            ref = f"{book} {ch}"
            # Standardized display: "chapitre N [du Book]"
            if book_raw:
                display = f"chapitre {ch} du {book_raw}"
            else:
                display = f"chapitre {ch}"
            return f"[[{display}|{ref}]]"
        text = pat_chap_french_num.sub(repl_chap_french_num, text)

        # --- 2i: "N-ième chapitre [du/des Book]" ---
        pat_ordinal_chap = re.compile(
            r'((' + _FRENCH_NUM_ALT + r')\s+chapitres?)'
            r'(?:\s+(?:du|de|des|du\s+livre\s+(?:du|de|des))\s+'
            r'(' + _ALL_SOURCE_NAMES_ALT + r'))?',
            re.IGNORECASE
        )
        def repl_ordinal_chap(m):
            full_display = m.group(0)
            num_text = m.group(2).lower()
            book_raw = m.group(3)

            ch = FRENCH_NUMBERS.get(num_text)
            if ch is None:
                return full_display

            if book_raw:
                resolved = _EXTENDED_FULL_NAME_MAP.get(book_raw.lower())
                book = self._apply_vulgate(resolved if resolved else book_raw)
            else:
                book = self._get_book_context()
            if not book:
                return full_display

            ref = f"{book} {ch}"
            # Standardized display: "chapitre N [du Book]"
            if book_raw:
                display = f"chapitre {ch} du {book_raw}"
            else:
                display = f"chapitre {ch}"
            return f"[[{display}|{ref}]]"
        text = pat_ordinal_chap.sub(repl_ordinal_chap, text)

        # --- 2j: "chapitres x. xi. et xv. de ce Livre" (multiple chapters) ---
        pat_multi_chap = re.compile(
            r'chapitres\s+'
            r'((?:(?:\d+|[IVXLCDM]+)\.?\s*(?:et\s+|,\s*)?)+)'
            r'(?:de\s+ce\s+Livre)?',
            re.IGNORECASE
        )
        def repl_multi_chap(m):
            full = m.group(0)
            nums_text = m.group(1)
            # Check if inside [[...]]
            start = m.start()
            preceding = m.string[:start]
            open_count = preceding.count("[[") - preceding.count("]]")
            if open_count > 0:
                return full

            book = self._get_book_context()
            if not book:
                return full

            # Find all chapter numbers
            chapter_nums = []
            for num_m in re.finditer(r'(\d+|[IVXLCDM]+)\.?', nums_text, re.IGNORECASE):
                raw = num_m.group(1)
                if is_roman(raw) or raw.isdigit():
                    chapter_nums.append((num_m.group(0), int(to_arabic(raw))))

            if len(chapter_nums) < 2:
                return full

            # Build replacement: wrap each chapter number individually
            # with standardized Arabic display
            result = full
            for raw_text, ch_num in reversed(chapter_nums):
                ref = f"{book} {ch_num}"
                old = raw_text
                new = f"[[{ch_num}|{ref}]]"
                idx = result.find(old)
                if idx >= 0:
                    result = result[:idx] + new + result[idx + len(old):]

            return result
        text = pat_multi_chap.sub(repl_multi_chap, text)

        # --- 2k: "Chapitre N" (standalone chapter, no verse, uses context book) ---
        pat_chap_standalone = re.compile(
            r'(?<!\[)'
            r'(Chapitres?\s+(\d+|[IVXLCDM]+))'
            r'(?!\s*[:\d])'              # not followed by colon+digit (already handled)
            r'(?!\s+verset)'             # not followed by verset (handled in 2b)
            r'(?!\s*\.?\s*(?:et\s+)?(?:\d|[IVXLCDM]))'  # not followed by more nums
            r'(?!\|)',                    # not before pipe
            re.IGNORECASE
        )
        # Non-biblical context indicators that precede "chapitre N"
        _NON_BIBLICAL_BEFORE_CHAP = re.compile(
            r'(?:'
                r'Cit[ée]\s+de\s+Dieu'
                r'|livre\s+\d+\s+de\s+'
                r'|livre\s+[IVXLCDM]+\s+de\s+'
                r'|livre\s+(?:\d+|[IVXLCDM]+)\s*,?\s*$'  # "livre N" right before "chapitre"
                r'|Antiq(?:uit[ée]s?)?\.'
                r'|Joseph(?:e)?\.'
                r'|Bell(?:um)?\.'
                r'|Hist(?:oire)?\.?\s+(?:Nat|Eccl)'
                r'|G[ée]ograph'
                r'|Strab(?:on)?\.'
                r'|H[ée]rodot'
                r'|Pline'
                r'|Ptolém'
                r'|Tacit'
                r'|Solin'
                r'|Chrysost'
                r'|Augustin'
            r')',
            re.IGNORECASE
        )
        def repl_chap_standalone(m):
            raw = m.group(1)
            ch_raw = m.group(2)
            # Check if inside [[...]]
            start = m.start()
            preceding = m.string[:start]
            open_count = preceding.count("[[") - preceding.count("]]")
            if open_count > 0:
                return raw

            # Reject lowercase Roman numerals
            if is_roman(ch_raw) and ch_raw != ch_raw.upper():
                return raw

            if is_roman(ch_raw) or ch_raw.isdigit():
                ch = int(to_arabic(ch_raw))
            else:
                return raw

            if ch < 1 or ch > 150:
                return raw

            # Skip non-biblical contexts (e.g. "Cité de Dieu chapitre 20")
            snippet = preceding[-80:]
            if _NON_BIBLICAL_BEFORE_CHAP.search(snippet):
                return raw

            # Resolve book from preceding text or page context
            book = self._find_preceding_book(preceding)
            if not book:
                book = self._get_book_context()
            if not book:
                return raw

            ref = f"{book} {ch}"
            # Inline format preserving original chapter word
            chap_word = raw.split()[0]  # "Chapitre" / "chapitres" / etc.
            display = f"{chap_word} {ch}"
            return f"[[{display}|{ref}]]"
        text = pat_chap_standalone.sub(repl_chap_standalone, text)

        return text

    # -----------------------------------------------------------------------
    # Layer 3: Ibid/Id resolution
    # -----------------------------------------------------------------------
    def _layer3_replace_ibid(self, m: re.Match) -> str:
        if not self.last_ref_book:
            return m.group(0)
        chapter_raw = m.group(2)
        verse_raw = m.group(3)
        if chapter_raw:
            ch = int(to_arabic(chapter_raw))
            self.last_ref_chapter = str(ch)
            if verse_raw:
                v = int(to_arabic(verse_raw))
                return f"[[{self.last_ref_book} {ch}:{v}]]"
            return f"[[{self.last_ref_book} {ch}]]"
        elif verse_raw:
            v = int(to_arabic(verse_raw))
            if self.last_ref_chapter:
                return f"[[{self.last_ref_book} {self.last_ref_chapter}:{v}]]"
            return m.group(0)
        else:
            if self.last_ref_chapter:
                return f"[[{self.last_ref_book} {self.last_ref_chapter}]]"
            return m.group(0)

    def _layer3_ibid(self, text: str) -> str:
        """Layer 3: Resolve Ibid./Id. references."""
        return _IBID_PATTERN.sub(self._layer3_replace_ibid, text)

    # -----------------------------------------------------------------------
    # Layer 4: Wrap existing bare book+chapter:verse references
    # -----------------------------------------------------------------------
    def _layer4_wrap_bare_refs(self, text: str) -> str:
        """Layer 4: Wrap already-standard BookName N:N that aren't in [[...]]."""
        pat = re.compile(
            r'(?<!\[)'    # not already inside [[
            r'(?<!\[\[)'  # also check for [[
            r'\b(' + _BOOK_NAMES_ALT + r')'
            r'\s+'
            r'(\d+)'     # chapter
            r'\s*:\s*'
            r'(\d+)'     # verse
            r'((?:\s*[,\.]\s*\d+' + _EXTRA_V_LOOKAHEAD + r')*)'  # additional verses
            r'(?:\s*[-\u2013]\s*(\d+))?'  # range end
            r'(?!\])'    # not already inside ]]
        )
        def repl_bare(m):
            book = m.group(1)
            ch = int(m.group(2))
            v_first = int(m.group(3))
            more = m.group(4) or ""
            range_end = m.group(5)

            # Check if inside [[...]]
            start = m.start()
            preceding = m.string[:start]
            open_count = preceding.count("[[") - preceding.count("]]")
            if open_count > 0:
                return m.group(0)

            verses = [v_first] + self._parse_extra_verses(more)
            if range_end:
                end = int(range_end)
                last = verses[-1] if verses else 0
                for v in range(last + 1, end + 1):
                    if v not in verses:
                        verses.append(v)

            # Apply Vulgate conversion
            book = self._apply_vulgate(book)

            self.last_ref_book = book
            self.last_ref_chapter = str(ch)
            ref = self._format_ref(book, ch, verses)
            return f"[[{ref}]]"
        return pat.sub(repl_bare, text)

    # -----------------------------------------------------------------------
    # Layer 5: Continuation references after [[...]] markers
    # -----------------------------------------------------------------------
    def _layer5_continuation_refs(self, text: str) -> str:
        """
        Wrap continuation refs (et N, et N:N) that follow [[...]] markers.

        [[Exode 24:26]] et 35 et 36:27
        → [[Exode 24:26]] et [[Exode 24:35]] et [[Exode 36:27]]

        Processes one continuation per iteration; the loop handles chains.
        """
        # Match: ]] followed by connector (et/,/;/&) and a number
        cont_pat = re.compile(
            r'(\]\])'                                 # end of preceding marker
            r'(\s*(?:et|&|,|;)\s*)'                   # connector
            r'(\d+)'                                   # number
            r'(?:\s*:\s*(\d+))?'                       # optional :verse
            r'(?=\s*[.,;:)\]!?&\[]|\s*(?:et|&|,|;)\s|\s+[A-Z\u00C0-\u00DD]|\s*$)'  # punctuation/connector/uppercase/end
        )

        result = text
        offset = 0
        while True:
            m = cont_pat.search(result, offset)
            if not m:
                break

            # Find the preceding [[...]] marker to extract its ref
            marker_open = result.rfind('[[', 0, m.start())
            if marker_open < 0:
                offset = m.end()
                continue

            marker_content = result[marker_open + 2:m.start()]
            # Extract ref part (after | if display|ref format)
            if '|' in marker_content:
                ref_str = marker_content.split('|', 1)[1].strip()
            else:
                ref_str = marker_content.strip()

            # Parse book and chapter from ref: "Book Ch:V" or "Book Ch"
            parts = ref_str.rsplit(' ', 1)
            if len(parts) != 2:
                offset = m.end()
                continue

            book = parts[0]
            ch_v = parts[1]
            if ':' in ch_v:
                ch_str = ch_v.split(':')[0]
                has_verse = True
            else:
                ch_str = ch_v
                has_verse = False

            try:
                prev_ch = int(ch_str)
            except ValueError:
                offset = m.end()
                continue

            connector = m.group(2)
            # Normalize & to et
            connector = re.sub(r'&', 'et', connector)
            num1 = int(m.group(3))
            num2_str = m.group(4)

            if num2_str:
                # Explicit ch:v — new chapter and verse
                ref = self._format_ref(book, num1, [int(num2_str)])
                display = f"{num1}:{num2_str}"
            elif has_verse:
                # Bare number after a verse ref → another verse in same chapter
                ref = self._format_ref(book, prev_ch, [num1])
                display = str(num1)
            else:
                # Bare number after a chapter-only ref → another chapter
                ref = f"{book} {num1}"
                display = str(num1)

            # Replace the connector + number portion (after ]])
            cont_start = m.start() + 2  # right after ]]
            cont_end = m.end()
            replacement = connector + f"[[{display}|{ref}]]"
            result = result[:cont_start] + replacement + result[cont_end:]
            # Back up 2 chars so the new ]] can be the start of the next chain
            offset = cont_start + len(replacement) - 2

        return result

    # -----------------------------------------------------------------------
    # Layer 6: Period-to-comma between consecutive markers
    # -----------------------------------------------------------------------
    def _layer6_period_between_markers(self, text: str) -> str:
        """Replace periods between consecutive [[...]] markers with commas."""
        return re.sub(r'\]\]\.(\s*)\[\[', r']],\1[[', text)

    # -----------------------------------------------------------------------
    # Layer 7: Deduplicate book name before its own marker
    # -----------------------------------------------------------------------
    # Match BookName, [[BookName...]] OR BookName, [[N BookName...]] (Vulgate prefix)
    _DEDUP_BOOK_PAT = re.compile(
        r'\b(' + _ALL_SOURCE_NAMES_ALT + r')\s*,?\s*(\[\[(?:\d\s+)?\1\b)'
    )

    def _layer7_dedup_bookname(self, text: str) -> str:
        """Remove redundant book name immediately before its own marker.
        e.g. 'au Deutéronome, [[Deutéronome 18:10]]' → 'au [[Deutéronome 18:10]]'
        e.g. 'des Rois, [[1 Rois 22:13]]' → 'des [[1 Rois 22:13]]'
        """
        return self._DEDUP_BOOK_PAT.sub(r'\2', text)

    # -----------------------------------------------------------------------
    # Main normalization pipeline
    # -----------------------------------------------------------------------
    def normalize_text(self, text: str) -> str:
        """Run all layers on a text string."""
        if not text:
            return text

        # Skip if text is already fully wrapped
        if text.startswith("[[") and text.endswith("]]"):
            return text

        # Layer 1: Explicit book abbreviations → [[ref]]
        text = self._layer1_explicit_refs(text)

        # Layer 2: French inline references → [[display|ref]]
        # Run specific patterns before general ones (2g before 2e, etc.)
        # The method handles ordering internally
        text = self._layer2_french_inline(text)

        # Layer 3: Ibid/Id
        text = self._layer3_ibid(text)

        # Layer 4: Wrap remaining bare references
        text = self._layer4_wrap_bare_refs(text)

        # Layer 5: Wrap continuation refs (et N, et N:N) after [[...]]
        text = self._layer5_continuation_refs(text)

        # Layer 6: Replace periods between consecutive markers with commas
        text = self._layer6_period_between_markers(text)

        # Layer 7: Remove redundant book name before its own marker
        text = self._layer7_dedup_bookname(text)

        # Cleanup: collapse editorial brackets merged with markers
        # e.g. [chapitre 8:4] → [[[chapitre 8:4|Genèse 8:4]]] → [[chapitre 8:4|Genèse 8:4]]
        text = text.replace("[[[", "[[").replace("]]]", "]]")

        return text


# ---------------------------------------------------------------------------
# Chapter context mapping
# ---------------------------------------------------------------------------
def build_chapter_map(normalized_dir: Path) -> dict[str, tuple[str, int | None]]:
    """
    Build a map of filename → (book_name, chapter_number) by scanning
    all page files in order and carrying forward the last-seen chapter.

    Returns dict like:
        {"page_0065.json": ("Josué", 1), "page_0066.json": ("Josué", 1), ...}
    """
    pages = sorted(normalized_dir.glob("page_*.json"))
    chapter_map: dict[str, tuple[str, int | None]] = {}
    book_name: str | None = None
    current_chapter: int | None = None

    for page_path in pages:
        with open(page_path, "r", encoding="utf-8") as f:
            data = _load_json(f.read())

        # Extract book name from book_title or directory
        if data.get("book_title") and not book_name:
            # Derive from BOOK_MAPPINGS using parent directory
            pass

        ch = data.get("chapter_number")
        if ch is not None:
            current_chapter = int(ch)

        chapter_map[page_path.name] = (book_name or "", current_chapter)

    return chapter_map


def get_book_name(book_dir: str) -> str:
    """Get canonical book name from directory name."""
    # First try BOOK_MAPPINGS
    name = BOOK_MAPPINGS.get(book_dir)
    if name:
        return name
    # Strip number prefix and try
    parts = book_dir.split("_", 1)
    if len(parts) > 1:
        return BOOK_MAPPINGS.get(book_dir, parts[1].replace("_", " ").title())
    return book_dir


# ---------------------------------------------------------------------------
# Context snippet extraction
# ---------------------------------------------------------------------------
_MARKER_RE = re.compile(r'\[\[.*?\]\]')

# ---------------------------------------------------------------------------
# Ambiguous / anaphoric reference detection
# ---------------------------------------------------------------------------
# Patterns that contain biblical reference context but use anaphoric pronouns
# instead of explicit book names — flagged for manual review.
_ANAPHORIC_PATTERNS = re.compile(
    r'(?:'
        r'du\s+même\s+(?:Prophète|Auteur|Apôtre|Livre|Évangéliste|Psaume|chapitre)'
        r'|de\s+ce\s+(?:Prophète|Auteur|Apôtre|Évangéliste)'
        r'|le\s+même\s+(?:Prophète|Auteur|Apôtre|Évangéliste)'
        r'|la\s+même\s+(?:Épître|Lettre)'
        r'|ce\s+même\s+(?:Prophète|Auteur|Apôtre|Livre|Évangéliste|Psaume|chapitre|endroit|passage)'
        r'|du\s+même\s+(?:Prophete|Apotre|Evangeliste)'
        r'|cet\s+(?:Auteur|Apôtre|Évangéliste)'
    r')',
    re.IGNORECASE
)


# Pattern to detect a potential Bible reference nearby (chapter/verse numbers)
_NEARBY_REF_INDICATOR = re.compile(
    r'(?:chapitre|verset|chap\.|v\.|vers\.)\s*\d'
    r'|\b\d+\s*:\s*\d+'
    r'|\[\[',
    re.IGNORECASE
)


def _detect_ambiguous(text: str, context_chars: int = 80) -> list[dict]:
    """
    Scan text for anaphoric/ambiguous reference patterns that cannot be
    automatically resolved. Only flags when a potential Bible reference
    (chapter, verse, or marker) exists nearby.
    Returns list of flagged entries for manual review.
    """
    flagged = []
    for m in _ANAPHORIC_PATTERNS.finditer(text):
        start, end = m.start(), m.end()
        # Check if there's a potential Bible reference nearby (within 120 chars)
        ctx_start = max(0, start - 120)
        ctx_end = min(len(text), end + 120)
        neighborhood = text[ctx_start:ctx_end]
        if not _NEARBY_REF_INDICATOR.search(neighborhood):
            continue  # No Bible reference nearby — skip
        # Build context snippet
        snip_start = max(0, start - context_chars)
        snip_end = min(len(text), end + context_chars)
        snippet = text[snip_start:snip_end]
        if snip_start > 0:
            snippet = "..." + snippet
        if snip_end < len(text):
            snippet = snippet + "..."
        flagged.append({
            "marker": None,
            "ref": None,
            "display": m.group(0),
            "type": "flagged",
            "reason": f"Anaphoric reference: '{m.group(0)}' — book cannot be auto-resolved",
            "context_old": snippet,
            "context_new": snippet,
        })
    return flagged


def _extract_snippets(old_text: str, new_text: str, context_chars: int = 60) -> list[dict]:
    """
    Find each [[...]] marker in new_text and extract a context snippet
    showing the surrounding text plus the old→new change.
    """
    snippets = []
    for m in _MARKER_RE.finditer(new_text):
        start, end = m.start(), m.end()
        marker = m.group(0)

        # Context window around the marker in new_text
        ctx_start = max(0, start - context_chars)
        ctx_end = min(len(new_text), end + context_chars)

        new_snippet = new_text[ctx_start:ctx_end]
        old_snippet = old_text[ctx_start:min(len(old_text), ctx_start + len(new_snippet) + 40)]

        # Trim to word boundaries and add ellipsis
        if ctx_start > 0:
            new_snippet = "..." + new_snippet
            old_snippet = "..." + old_snippet
        if ctx_end < len(new_text):
            new_snippet = new_snippet + "..."
        if ctx_start + len(old_snippet.lstrip(".")) + 40 < len(old_text):
            old_snippet = old_snippet + "..."

        # Parse the marker itself
        inner = marker[2:-2]  # strip [[ and ]]
        if "|" in inner:
            display, ref = inner.split("|", 1)
            marker_type = "inline"
        else:
            display = inner
            ref = inner
            marker_type = "direct"

        snippets.append({
            "marker": marker,
            "ref": ref,
            "display": display,
            "type": marker_type,
            "context_old": old_snippet,
            "context_new": new_snippet,
        })
    return snippets


# ---------------------------------------------------------------------------
# File processing
# ---------------------------------------------------------------------------
def process_page(page_path: Path, normalizer: PageRefNormalizer,
                 output_path: Path,
                 chapter: int | None = None,
                 dry_run: bool = False) -> list[dict]:
    """
    Process a single normalized page JSON file.

    Returns list of changes made (for dry-run reporting).
    """
    try:
        with open(page_path, "r", encoding="utf-8") as f:
            data = _load_json(f.read())
    except json.JSONDecodeError:
        return []  # skip malformed files

    changes: list[dict] = []

    # Process commentary entries
    for i, entry in enumerate(data.get("commentary", [])):
        verse_ref = entry.get("verse_ref")

        for field_name in ("french_commentary", "french_translation"):
            text = entry.get(field_name)
            if not text:
                continue
            new_text = normalizer.normalize_text(text)

            # Detect ambiguous anaphoric references for manual review
            ambiguous = _detect_ambiguous(text) if dry_run else []

            has_changes = new_text != text
            has_ambiguous = bool(ambiguous)

            if not has_changes and not has_ambiguous:
                continue

            snippets = _extract_snippets(text, new_text) if (dry_run and has_changes) else []

            changes.append({
                "file": page_path.name,
                "field": f"commentary[{i}].{field_name}",
                "chapter": chapter,
                "verse_ref": verse_ref,
                "snippets": snippets,
                "ambiguous": ambiguous,
                "old_full": text if dry_run else None,
                "new_full": new_text if dry_run else None,
            })
            if not dry_run and has_changes:
                entry[field_name] = new_text

    # Write to output path if not dry run
    if not dry_run:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        # Ensure trailing newline
        with open(output_path, "a", encoding="utf-8") as f:
            f.write("\n")

    return changes


def process_book(book_dir_name: str, dry_run: bool = False) -> None:
    """Process all normalized pages for a book."""
    script_dir = Path(__file__).parent
    data_dir = script_dir.parent / "data"
    book_path = data_dir / book_dir_name

    if not book_path.exists():
        print(f"Error: Book directory not found: {book_path}")
        sys.exit(1)

    normalized_dir = book_path / "normalized"
    if not normalized_dir.exists():
        print(f"Error: No normalized/ directory in {book_path}")
        sys.exit(1)

    # Create standardized output directory
    standardized_dir = book_path / "standardized"
    if not dry_run:
        standardized_dir.mkdir(exist_ok=True)

    # Get book name
    book_name = get_book_name(book_dir_name)
    print(f"Book: {book_name}")
    print(f"Input:  {normalized_dir}")
    if not dry_run:
        print(f"Output: {standardized_dir}")
    print(f"Mode: {'DRY RUN' if dry_run else 'APPLY'}")
    print()

    # Build chapter map (Pass 1)
    pages = sorted(normalized_dir.glob("page_*.json"))
    if not pages:
        print("No page files found.")
        return

    print(f"Scanning {len(pages)} pages...")

    # Pass 1: Build chapter context
    current_chapter: int | None = None
    page_chapters: dict[str, int | None] = {}

    skipped: list[str] = []
    for page_path in pages:
        try:
            with open(page_path, "r", encoding="utf-8") as f:
                data = _load_json(f.read())
        except json.JSONDecodeError:
            skipped.append(page_path.name)
            page_chapters[page_path.name] = current_chapter
            continue
        ch = data.get("chapter_number")
        if ch is not None:
            current_chapter = int(ch)
        page_chapters[page_path.name] = current_chapter

    if skipped:
        print(f"  Skipped {len(skipped)} malformed JSON files: {', '.join(skipped[:5])}{'...' if len(skipped) > 5 else ''}")

    # Pass 2: Process with context
    normalizer = PageRefNormalizer()
    total_changes = 0
    total_markers = 0
    files_changed = 0
    all_changes: list[dict] = []

    for page_path in pages:
        chapter = page_chapters.get(page_path.name)
        normalizer.set_context(book_name, chapter)

        # Output path in standardized folder
        output_path = standardized_dir / page_path.name if not dry_run else page_path

        changes = process_page(page_path, normalizer, output_path,
                               chapter=chapter, dry_run=dry_run)
        if changes:
            files_changed += 1
            total_changes += len(changes)
            for c in changes:
                total_markers += len(c.get("snippets", []))
            all_changes.extend(changes)

    # Count flagged items
    total_flagged = sum(len(c.get("ambiguous", [])) for c in all_changes)

    # Report
    print(f"\n{'=' * 60}")
    print(f"Results: {total_changes} field changes across {files_changed}/{len(pages)} files")
    if dry_run:
        print(f"         {total_markers} individual [[markers]] to review")
        if total_flagged:
            print(f"         {total_flagged} ambiguous references flagged for manual review")
    print(f"{'=' * 60}")

    if dry_run and all_changes:
        # Build flat review list: one entry per marker + flagged items
        review_entries: list[dict] = []
        flagged_count = 0
        for change in all_changes:
            for snippet in change.get("snippets", []):
                review_entries.append({
                    "file": change["file"],
                    "field": change["field"],
                    "chapter": change["chapter"],
                    "verse_ref": change.get("verse_ref"),
                    "marker": snippet["marker"],
                    "ref": snippet["ref"],
                    "display": snippet["display"],
                    "type": snippet["type"],
                    "context_old": snippet["context_old"],
                    "context_new": snippet["context_new"],
                })
            for flagged in change.get("ambiguous", []):
                flagged_count += 1
                review_entries.append({
                    "file": change["file"],
                    "field": change["field"],
                    "chapter": change["chapter"],
                    "verse_ref": change.get("verse_ref"),
                    "marker": None,
                    "ref": None,
                    "display": flagged["display"],
                    "type": "flagged",
                    "reason": flagged["reason"],
                    "context_old": flagged["context_old"],
                    "context_new": flagged["context_new"],
                })

        # Sort: flagged entries first, then markers in file order
        review_entries.sort(key=lambda e: (0 if e["type"] == "flagged" else 1))

        # Write JSON review file
        review_path = book_path / "dry_run_review.json"
        with open(review_path, "w", encoding="utf-8") as f:
            json.dump(review_entries, f, ensure_ascii=False, indent=2)
        print(f"\nReview file: {review_path}")
        if flagged_count:
            print(f"         {flagged_count} flagged ambiguous references for manual review")

        # Also print summary to console
        print(f"\nSample changes (first 10):\n")
        for entry in review_entries[:10]:
            ch = entry["chapter"] or "?"
            if entry["type"] == "flagged":
                print(f"  [{entry['file']} ch.{ch}] FLAGGED: {entry['display']}")
                print(f"    REASON: {entry.get('reason', '')}")
                print(f"    CONTEXT: {entry['context_old'][:120]}")
            else:
                print(f"  [{entry['file']} ch.{ch}] {entry['type']}: {entry['marker']}")
                print(f"    OLD: {entry['context_old'][:120]}")
                print(f"    NEW: {entry['context_new'][:120]}")
            print()
        if len(review_entries) > 10:
            print(f"  ... and {len(review_entries) - 10} more (see review JSON)")

    if not dry_run and total_changes > 0:
        print(f"\nApplied {total_changes} changes to {files_changed} files.")


def main():
    if len(sys.argv) < 2:
        print("Usage: python standardize_refs.py <book_directory> [--dry-run]")
        print("Example: python standardize_refs.py 06_josue --dry-run")
        sys.exit(1)

    book_dir = sys.argv[1]
    dry_run = "--dry-run" in sys.argv

    process_book(book_dir, dry_run=dry_run)


if __name__ == "__main__":
    main()
