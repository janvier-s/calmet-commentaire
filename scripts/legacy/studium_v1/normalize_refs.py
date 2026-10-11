#!/usr/bin/env python3
"""
Normalize Biblical references in french_commentary and footnotes.text fields.

Converts abbreviated references like "Deut. XVII. 3." to "Deutéronome 17:3".
Expands Ibid./Id. using tracked context. Handles Roman→Arabic conversion,
italic markers, long-s (ſ) OCR artifacts, and multi-verse references.

Strategy: Use a token-by-token scanner rather than a single greedy regex.
Abbreviations MUST be preceded by a word boundary and followed by a dot.

Usage:
    python normalize_refs.py <book_directory>
    python normalize_refs.py 01_genese
"""

import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Book abbreviation → canonical French name
# All keys lowercase. Short abbreviations require a dot after them.
# ---------------------------------------------------------------------------

ABBREV_MAP: dict[str, str] = {
    # --- Genèse ---
    "gen": "Genèse", "genes": "Genèse", "geneſ": "Genèse", "geneſe": "Genèse",
    # --- Exode ---
    "exod": "Exode",
    # --- Lévitique ---
    "lev": "Lévitique", "levit": "Lévitique", "lévit": "Lévitique",
    # --- Nombres ---
    "num": "Nombres", "nomb": "Nombres", "nombr": "Nombres",
    # --- Deutéronome ---
    "deut": "Deutéronome", "deuteron": "Deutéronome", "deutéron": "Deutéronome",
    # --- Josué ---
    "josue": "Josué", "josué": "Josué", "joſue": "Josué", "joſué": "Josué",
    # --- Juges ---
    "judic": "Juges",
    # --- 1-4 Rois ---
    "reg": "Rois", "ſam": "Rois", "sam": "Rois",
    # --- Chroniques ---
    "par": "Chroniques", "paral": "Chroniques", "paralip": "Chroniques",
    "chron": "Chroniques",
    # --- Esdras ---
    "esdr": "Esdras", "eſdr": "Esdras",
    # --- Néhémie ---
    "neh": "Néhémie", "nehem": "Néhémie", "néhém": "Néhémie",
    # --- Tobie ---
    "tob": "Tobie",
    # --- Esther ---
    "esth": "Esther", "eſth": "Esther",
    # --- Job ---
    "job": "Job",
    # --- Psaumes ---
    "ps": "Psaumes", "pſ": "Psaumes", "psalm": "Psaumes", "pſalm": "Psaumes",
    "psal": "Psaumes", "pſal": "Psaumes", "psaume": "Psaumes", "pſaume": "Psaumes",
    # --- Proverbes ---
    "prov": "Proverbes", "proverb": "Proverbes",
    # --- Ecclésiaste ---
    "eccle": "Ecclésiaste", "eccles": "Ecclésiaste", "eccléſ": "Ecclésiaste",
    "ecclés": "Ecclésiaste",
    # --- Cantique ---
    "cant": "Cantique des Cantiques", "cantiq": "Cantique des Cantiques",
    # --- Sagesse ---
    "sag": "Sagesse", "sap": "Sagesse", "ſag": "Sagesse", "ſap": "Sagesse",
    # --- Ecclésiastique ---
    "eccli": "Ecclésiastique", "sirac": "Ecclésiastique",
    "eccl": "Ecclésiastique",
    # --- Isaïe ---
    "isai": "Isaïe", "isaï": "Isaïe", "esai": "Isaïe",
    "iſai": "Isaïe", "iſaï": "Isaïe", "eſai": "Isaïe",
    # --- Jérémie ---
    "jer": "Jérémie", "jerem": "Jérémie", "jérém": "Jérémie",
    # --- Lamentations ---
    "lam": "Lamentations", "lament": "Lamentations",
    # --- Baruch ---
    "baruch": "Baruch",
    # --- Ézéchiel ---
    "ezech": "Ézéchiel", "ézéch": "Ézéchiel",
    # --- Daniel ---
    "dan": "Daniel",
    # --- Osée ---
    "osee": "Osée", "osée": "Osée", "oſee": "Osée", "oſée": "Osée",
    # --- Joël ---
    "joel": "Joël", "joël": "Joël",
    # --- Amos ---
    "amos": "Amos",
    # --- Abdias ---
    "abd": "Abdias", "abdi": "Abdias",
    # --- Jonas ---
    "jonas": "Jonas",
    # --- Michée ---
    "mich": "Michée",
    # --- Nahum ---
    "nahum": "Nahum",
    # --- Habacuc ---
    "hab": "Habacuc", "habac": "Habacuc",
    # --- Sophonie ---
    "soph": "Sophonie", "sophon": "Sophonie", "ſoph": "Sophonie",
    "ſophon": "Sophonie",
    # --- Aggée ---
    "agg": "Aggée",
    # --- Zacharie ---
    "zach": "Zacharie", "zachar": "Zacharie",
    # --- Malachie ---
    "malach": "Malachie",
    # --- Maccabées ---
    "mach": "Maccabées", "macch": "Maccabées", "macc": "Maccabées",
    # ===== New Testament =====
    "matth": "Matthieu", "matt": "Matthieu",
    "marc": "Marc",
    "luc": "Luc",
    "joan": "Jean", "joann": "Jean",
    "act": "Actes des Apôtres",
    "rom": "Romains",
    "cor": "Corinthiens", "corint": "Corinthiens", "corinth": "Corinthiens",
    "gal": "Galates", "galat": "Galates",
    "eph": "Éphésiens", "ephes": "Éphésiens", "éphés": "Éphésiens",
    "epheſ": "Éphésiens",
    "phil": "Philippiens", "philipp": "Philippiens",
    "col": "Colossiens", "coloss": "Colossiens", "coloſſ": "Colossiens",
    "thess": "Thessaloniciens", "theſſ": "Thessaloniciens",
    "thessal": "Thessaloniciens", "theſſal": "Thessaloniciens",
    "tim": "Timothée", "timoth": "Timothée",
    "tit": "Tite",
    "philem": "Philémon",
    "hebr": "Hébreux", "heb": "Hébreux", "hébr": "Hébreux",
    "jac": "Jacques", "jacq": "Jacques",
    "petr": "Pierre", "pier": "Pierre",
    "apoc": "Apocalypse", "apocal": "Apocalypse",
}

# Full French names (match as whole words, no dot needed)
FULL_NAME_MAP: dict[str, str] = {
    "genèse": "Genèse", "genese": "Genèse",
    "exode": "Exode",
    "lévitique": "Lévitique", "levitique": "Lévitique",
    "nombres": "Nombres",
    "deutéronome": "Deutéronome", "deuteronome": "Deutéronome",
    "josué": "Josué", "josue": "Josué",
    "juges": "Juges",
    "ruth": "Ruth",
    "chroniques": "Chroniques",
    "esdras": "Esdras",
    "néhémie": "Néhémie", "nehemie": "Néhémie",
    "tobie": "Tobie",
    "judith": "Judith",
    "esther": "Esther",
    "job": "Job",
    "psaumes": "Psaumes",
    "proverbes": "Proverbes",
    "ecclésiaste": "Ecclésiaste", "ecclesiaste": "Ecclésiaste",
    "sagesse": "Sagesse",
    "ecclésiastique": "Ecclésiastique", "ecclesiastique": "Ecclésiastique",
    "isaïe": "Isaïe", "isaie": "Isaïe",
    "jérémie": "Jérémie", "jeremie": "Jérémie",
    "lamentations": "Lamentations",
    "baruch": "Baruch",
    "ézéchiel": "Ézéchiel", "ezechiel": "Ézéchiel",
    "daniel": "Daniel",
    "osée": "Osée", "osee": "Osée",
    "joël": "Joël",
    "amos": "Amos",
    "abdias": "Abdias",
    "jonas": "Jonas",
    "michée": "Michée", "michee": "Michée",
    "nahum": "Nahum",
    "habacuc": "Habacuc",
    "sophonie": "Sophonie",
    "aggée": "Aggée", "aggee": "Aggée",
    "zacharie": "Zacharie",
    "malachie": "Malachie",
    "matthieu": "Matthieu",
    "marc": "Marc",
    "luc": "Luc",
    "jean": "Jean",
    "romains": "Romains",
    "galates": "Galates",
    "colossiens": "Colossiens",
    "tite": "Tite",
    "philémon": "Philémon", "philemon": "Philémon",
    "hébreux": "Hébreux", "hebreux": "Hébreux",
    "jacques": "Jacques",
    "jude": "Jude",
    "apocalypse": "Apocalypse",
}

# Books that MUST have a number prefix (can't stand alone)
NUMBERED_REQUIRED = {"Rois", "Chroniques", "Maccabées",
                     "Corinthiens", "Thessaloniciens", "Timothée", "Pierre"}

# Books that CAN have a number prefix
NUMBERED_BOOKS = NUMBERED_REQUIRED | {"Jean", "Esdras"}

# ---------------------------------------------------------------------------
# Roman numeral helpers
# ---------------------------------------------------------------------------
_ROMAN_RE = re.compile(r'^[IVXLCDM]+$', re.IGNORECASE)
_ROMAN_VALUES = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}


def is_roman(s: str) -> bool:
    return bool(s and _ROMAN_RE.match(s.strip()))


def roman_to_int(s: str) -> int:
    s = s.upper().strip()
    result = prev = 0
    for ch in reversed(s):
        val = _ROMAN_VALUES.get(ch, 0)
        if val < prev:
            result -= val
        else:
            result += val
        prev = val
    return result


def to_arabic(s: str) -> str:
    """Convert Roman or Arabic numeral string to Arabic string."""
    s = s.strip().rstrip(".")
    if is_roman(s):
        return str(roman_to_int(s))
    return s


# ---------------------------------------------------------------------------
# Regex patterns — conservative, explicit
# ---------------------------------------------------------------------------

def _build_abbrev_alt() -> str:
    keys = sorted(ABBREV_MAP.keys(), key=len, reverse=True)
    return "|".join(re.escape(k) for k in keys)


def _build_fullname_alt() -> str:
    keys = sorted(FULL_NAME_MAP.keys(), key=len, reverse=True)
    return "|".join(re.escape(k) for k in keys)


_ABBREV_ALT = _build_abbrev_alt()
_FULLNAME_ALT = _build_fullname_alt()

# A numeral: Roman or Arabic
_NUM = r'(?:[IVXLCDM]+|\d+)'

# --- Pattern A: [num_prefix] Abbrev. [chapter]. [verse]. [verse_list] ---
# Key safety: \b before the abbreviation, required dot after.
# The chapter/verse parts each explicitly match "NUM." or "NUM:" patterns.
_PAT_ABBREV = re.compile(
    r'(?:_\s*)?'                                 # optional italic open
    r'(?:(?:^|(?<=\s)|(?<=\.))([1-4]|[IV]{1,3})\.?\s+)?'  # group 1: number prefix (at word boundary)
    r'(?<![A-Za-zÀ-ÿſ0-9])'                     # not preceded by a letter or digit
    r'(' + _ABBREV_ALT + r')'                    # group 2: abbreviation
    r'(?:\s*_)?'                                 # optional italic close (before dot)
    r'\.\s*'                                     # REQUIRED trailing dot
    r'(?:_\s*)?'                                 # optional italic close (after dot)
    r'(?='                                       # lookahead: must be followed by an UPPERCASE Roman or Arabic numeral
        r'(?:[IVXLCDM]+[\.\s:]|\d+[\.\s:]|\s*$)'  # note: IGNORECASE disabled for this via check in callback
    r')'
    r'(?:'
        r'(?:c\.?\s+|ch\.?\s+|chap\.?\s+)?'     # optional chapter marker
        r'(' + _NUM + r')'                       # group 3: chapter
        r'(?:'                                   # chapter followed by separator+verse
            r'(?:[\.:,]\s*)'                     # separator: dot, colon, or comma
            r'(?:v\.?\s*|℣\.?\s*|verset\s+)?'   # optional verse marker
            r'(' + _NUM + r')'                   # group 4: first verse
            r'((?:\s*,\s*\d+)*)'                # group 5: additional verses (comma only)
            r'(?:\s*[-–]\s*(\d+))?'             # group 6: range end
        r')?'
    r')?',
    re.IGNORECASE
)

# --- Pattern B: full name + chapter:verse ---
_PAT_FULLNAME = re.compile(
    r'(?:_)?'
    r'(?:([1-4])\s+)?'                          # group 1: number prefix (Arabic only)
    r'\b(' + _FULLNAME_ALT + r')\b'             # group 2: full name
    r'(?:_)?'
    r'\s+'
    r'(' + _NUM + r')'                          # group 3: chapter
    r'(?:'
        r'(?:\s*:\s*|\s*,\s+)'                  # separator (colon or comma)
        r'(\d+)'                                # group 4: verse
        r'((?:\s*,\s*\d+)*)'                   # group 5: more verses
        r'(?:\s*[-–]\s*(\d+))?'                # group 6: range end
    r')?',
    re.IGNORECASE
)

# Ibid / Id
_IBID_PATTERN = re.compile(
    r'\b(Ibid(?:em)?|Id(?:em)?)\.'
    r'(?:\s*(?:c\.?\s*)?'
    r'(' + _NUM + r')'                          # group 2: chapter
    r'(?:\s*[,:]\s*(?:v\.?\s*|℣\.?\s*)?(' + _NUM + r'))?'  # group 3: verse
    r')?',
    re.IGNORECASE
)

# Standalone verse: ℣. N
_VERSE_ONLY_PATTERN = re.compile(
    r'℣\.?\s*(\d+)'
    r'\.?'
)


# ---------------------------------------------------------------------------
# Normalizer
# ---------------------------------------------------------------------------

class RefNormalizer:
    def __init__(self):
        self.last_book: str | None = None
        self.last_chapter: str | None = None

    def _resolve_book(self, prefix: str | None, abbrev: str,
                      lookup: dict[str, str]) -> str | None:
        key = abbrev.lower()
        canonical = lookup.get(key) or lookup.get(key.replace("ſ", "s"))
        if not canonical:
            return None
        if canonical in NUMBERED_BOOKS:
            if prefix:
                num = to_arabic(prefix)
                return f"{num} {canonical}"
            elif canonical in NUMBERED_REQUIRED:
                return None
            else:
                return canonical
        return canonical

    def _format_verses(self, first: str | None, more: str | None,
                       range_end: str | None) -> str:
        parts = []
        if first:
            parts.append(to_arabic(first))
        if more:
            for m in re.finditer(r'(\d+)', more):
                parts.append(m.group(1))
        result = ", ".join(parts)
        if range_end:
            result += "-" + range_end
        return result

    def _make_ref(self, book: str, chapter_raw: str | None,
                  verse_raw: str | None, more: str | None,
                  range_end: str | None) -> str:
        if chapter_raw:
            ch = to_arabic(chapter_raw)
            self.last_book = book
            self.last_chapter = ch
            if verse_raw:
                verses = self._format_verses(verse_raw, more, range_end)
                return f"{book} {ch}:{verses}"
            return f"{book} {ch}"
        self.last_book = book
        return book

    def replace_abbrev(self, m: re.Match) -> str:
        prefix = m.group(1)
        abbrev = m.group(2)

        # Safety: check character BEFORE the match — must not be a letter
        # (catches cases like "Joseph." where "eph." would match)
        start = m.start()
        text = m.string
        # Find where the abbreviation starts (skip italic/prefix)
        # We check: is the abbreviation preceded by another letter?
        abbrev_start = text.find(abbrev, start, m.end())
        if abbrev_start is None:
            abbrev_start = start
        if abbrev_start > 0 and text[abbrev_start - 1].isalpha():
            return m.group(0)  # part of a larger word

        book = self._resolve_book(prefix, abbrev, ABBREV_MAP)
        if book is None:
            return m.group(0)

        chapter_raw = m.group(3)

        # Reject if "chapter" is a lowercase-only Roman letter (l., c., d. = liber, caput, etc.)
        if chapter_raw and chapter_raw == chapter_raw.lower() and is_roman(chapter_raw):
            return m.group(0)

        verse_raw = m.group(4) if m.lastindex >= 4 else None
        more = m.group(5) if m.lastindex >= 5 else None
        range_end = m.group(6) if m.lastindex >= 6 else None

        return self._make_ref(book, chapter_raw, verse_raw, more, range_end)

    def replace_fullname(self, m: re.Match) -> str:
        prefix = m.group(1)
        name = m.group(2)
        book = self._resolve_book(prefix, name, FULL_NAME_MAP)
        if book is None:
            return m.group(0)

        chapter_raw = m.group(3)
        verse_raw = m.group(4) if m.lastindex >= 4 else None
        more = m.group(5) if m.lastindex >= 5 else None
        range_end = m.group(6) if m.lastindex >= 6 else None

        return self._make_ref(book, chapter_raw, verse_raw, more, range_end)

    def replace_ibid(self, m: re.Match) -> str:
        if not self.last_book:
            return m.group(0)
        chapter_raw = m.group(2)
        verse_raw = m.group(3)
        if chapter_raw:
            ch = to_arabic(chapter_raw)
            self.last_chapter = ch
            if verse_raw:
                return f"{self.last_book} {ch}:{to_arabic(verse_raw)}"
            return f"{self.last_book} {ch}"
        elif verse_raw:
            v = to_arabic(verse_raw)
            if self.last_chapter:
                return f"{self.last_book} {self.last_chapter}:{v}"
            return m.group(0)
        else:
            return self.last_book

    def replace_verse_only(self, m: re.Match) -> str:
        verse = m.group(1)
        if self.last_book and self.last_chapter:
            return f"{self.last_book} {self.last_chapter}:{verse}"
        return m.group(0)

    def normalize_text(self, text: str) -> str:
        if not text:
            return text

        # Pre-clean OCR
        text = text.replace("5erset", "verset")

        # Step 1: Abbreviated refs (require dot after abbrev)
        text = _PAT_ABBREV.sub(self.replace_abbrev, text)

        # Step 2: Full-name refs
        text = _PAT_FULLNAME.sub(self.replace_fullname, text)

        # Step 3: Ibid./Id.
        text = _IBID_PATTERN.sub(self.replace_ibid, text)

        # Step 4: Standalone ℣. refs
        text = _VERSE_ONLY_PATTERN.sub(self.replace_verse_only, text)

        # Step 5: Strip italic markers around canonical book names
        all_canonical = set(ABBREV_MAP.values()) | set(FULL_NAME_MAP.values())
        for name in all_canonical:
            text = text.replace(f"_{name}_", name)

        return text


# ---------------------------------------------------------------------------
# File processing
# ---------------------------------------------------------------------------

def process_chapter_file(filepath: Path, normalizer: RefNormalizer) -> bool:
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    modified = False

    for commentary in data.get("commentaries", []):
        text = commentary.get("french_commentary")
        if text:
            new_text = normalizer.normalize_text(text)
            if new_text != text:
                commentary["french_commentary"] = new_text
                modified = True

    for footnote in data.get("footnotes", []):
        text = footnote.get("text")
        if text:
            new_text = normalizer.normalize_text(text)
            if new_text != text:
                footnote["text"] = new_text
                modified = True

    if modified:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return modified


def regenerate_commentary_txt(chapters_dir: Path, commentary_txt_dir: Path):
    commentary_txt_dir.mkdir(parents=True, exist_ok=True)
    for ch_file in sorted(chapters_dir.glob("chapter_*.json")):
        with open(ch_file, "r", encoding="utf-8") as f:
            ch_data = json.load(f)
        commentary_txt = [
            {
                "commentary_seq": c["commentary_seq"],
                "french_commentary": c["french_commentary"],
            }
            for c in ch_data.get("commentaries", [])
        ]
        ch_num = ch_data["chapter"]
        txt_path = commentary_txt_dir / f"chapter_{ch_num:02d}.json"
        with open(txt_path, "w", encoding="utf-8") as f:
            json.dump(commentary_txt, f, ensure_ascii=False, indent=2)


def main():
    if len(sys.argv) < 2:
        print("Usage: python normalize_refs.py <book_directory>")
        print("Example: python normalize_refs.py 01_genese")
        sys.exit(1)

    book_dir = sys.argv[1]
    script_dir = Path(__file__).parent
    data_dir = script_dir.parent / "data"
    book_path = data_dir / book_dir

    if not book_path.exists():
        print(f"Error: Book directory not found: {book_path}")
        sys.exit(1)

    chapters_dir = book_path / "transformed" / "chapters"
    commentary_txt_dir = book_path / "transformed" / "commentary_txt"

    if not chapters_dir.exists():
        print(f"Error: No transformed/chapters/ directory in {book_path}")
        sys.exit(1)

    chapter_files = sorted(chapters_dir.glob("chapter_*.json"))
    if not chapter_files:
        print("No chapter files found.")
        sys.exit(0)

    print(f"Normalizing biblical references in: {chapters_dir}")
    print(f"Processing {len(chapter_files)} chapter files...")

    normalizer = RefNormalizer()
    modified_count = 0

    for filepath in chapter_files:
        normalizer.last_book = None
        normalizer.last_chapter = None
        was_modified = process_chapter_file(filepath, normalizer)
        if was_modified:
            modified_count += 1
            print(f"  Updated: {filepath.name}")

    print(f"\nModified {modified_count}/{len(chapter_files)} chapter files")

    if modified_count > 0:
        print("Regenerating commentary_txt/...")
        regenerate_commentary_txt(chapters_dir, commentary_txt_dir)
        print("Done.")
    else:
        print("No changes needed.")


if __name__ == "__main__":
    main()
