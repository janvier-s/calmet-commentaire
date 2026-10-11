#!/usr/bin/env python3
"""
Parse Glossa Ordinaria from USFX XML format and organize by book and chapter.
Output: JSON files organized by book/chapter with verses and glosses.

Usage: python parse_glossa_ordinaria.py
"""

import xml.etree.ElementTree as ET
import json
from pathlib import Path
from collections import defaultdict

# Configuration
USFX_FILE = Path("/Users/Janvier/Development/for-the-kingdom/commentary/archive/vulgata/latVUC_usfx/latVUC_usfx.xml")
OUTPUT_DIR = Path("/Users/Janvier/Development/for-the-kingdom/commentary/glossa_ordinaria")

# Book name mapping (3-letter code to French name) in canonical order
BOOK_NAMES = [
    ("GEN", "Genèse"),
    ("EXO", "Exode"),
    ("LEV", "Lévitique"),
    ("NUM", "Nombres"),
    ("DEU", "Deutéronome"),
    ("JOS", "Josué"),
    ("JDG", "Juges"),
    ("RUT", "Ruth"),
    ("1SA", "1 Samuel"),
    ("2SA", "2 Samuel"),
    ("1KI", "1 Rois"),
    ("2KI", "2 Rois"),
    ("1CH", "1 Chroniques"),
    ("2CH", "2 Chroniques"),
    ("EZR", "Esdras"),
    ("NEH", "Néhémie"),
    ("TOB", "Tobie"),
    ("JDT", "Judith"),
    ("EST", "Esther"),
    ("1MA", "1 Maccabées"),
    ("2MA", "2 Maccabées"),
    ("JOB", "Job"),
    ("PSA", "Psaumes"),
    ("PRO", "Proverbes"),
    ("ECC", "Ecclésiaste"),
    ("SNG", "Cantique des Cantiques"),
    ("WIS", "Sagesse"),
    ("SIR", "Siracide"),
    ("ISA", "Isaïe"),
    ("JER", "Jérémie"),
    ("LAM", "Lamentations"),
    ("BAR", "Baruch"),
    ("EZK", "Ézéchiel"),
    ("DAN", "Daniel"),
    ("HOS", "Osée"),
    ("JOL", "Joël"),
    ("AMO", "Amos"),
    ("OBA", "Abdias"),
    ("JON", "Jonas"),
    ("MIC", "Michée"),
    ("NAM", "Nahum"),
    ("HAB", "Habacuc"),
    ("ZEP", "Sophonie"),
    ("HAG", "Aggée"),
    ("ZEC", "Zacharie"),
    ("MAL", "Malachie"),
    ("MAT", "Matthieu"),
    ("MRK", "Marc"),
    ("LUK", "Luc"),
    ("JHN", "Jean"),
    ("ACT", "Actes"),
    ("ROM", "Romains"),
    ("1CO", "1 Corinthiens"),
    ("2CO", "2 Corinthiens"),
    ("GAL", "Galates"),
    ("EPH", "Éphésiens"),
    ("PHP", "Philippiens"),
    ("COL", "Colossiens"),
    ("1TH", "1 Thessaloniciens"),
    ("2TH", "2 Thessaloniciens"),
    ("1TI", "1 Timothée"),
    ("2TI", "2 Timothée"),
    ("TIT", "Tite"),
    ("PHM", "Philémon"),
    ("HEB", "Hébreux"),
    ("JAS", "Jacques"),
    ("1PE", "1 Pierre"),
    ("2PE", "2 Pierre"),
    ("1JN", "1 Jean"),
    ("2JN", "2 Jean"),
    ("3JN", "3 Jean"),
    ("JUD", "Jude"),
    ("REV", "Apocalypse")
]

# Create lookup dictionaries
BOOK_NAME_DICT = {code: name for code, name in BOOK_NAMES}
BOOK_ORDER = {code: idx + 1 for idx, (code, _) in enumerate(BOOK_NAMES)}


def extract_author_citations(text):
    """Extract author citations and split commentary into granular parts."""
    import re

    # Comprehensive list of authorities cited in Glossa Ordinaria
    # Based on scholarly sources and manuscript evidence
    KNOWN_AUTHORS = [
        # Church Fathers (Patristic)
        "AUGUSTINUS", "AUG",
        "HIERONYMUS", "HIERON",
        "BEDA",
        "GREGORIUS", "GREG",
        "AMBROSIUS", "AMBR",
        "ISIDORUS", "ISID",
        "ORIGENES", "ORIGEN",
        "CHRYSOSTOMUS",
        "CASSIODORUS",
        # Carolingian & Medieval
        "RABANUS", "RABAN",
        "STRABO", "STRAB", "WALAFRIDUS",
        "ALCUINUS", "ALCUIN",
        "HAIMO",
        "ANSELMUS", "ANSELM",
        "REMIGIUS",
        # Less common
        "ERIUGENA",
        "BERENGARIUS",
        "LANFRANC",
        "HUGO",
        # Abbreviations
        "FULG",  # Fulgentius
        "CYPR",  # Cyprian
        "LEO",   # Leo the Great
    ]

    # Create regex pattern that matches known authors
    # Pattern: AUTHOR_NAME followed by optional period and space
    author_pattern = '|'.join(re.escape(auth) for auth in KNOWN_AUTHORS)

    commentaries = []

    # Split text by author names (keeping the delimiter)
    # Pattern matches: word boundary + author name + optional period + word boundary
    split_pattern = rf'\b({author_pattern})\.?\b'
    parts = re.split(split_pattern, text, flags=re.IGNORECASE)

    current_author = None
    current_text = []

    for i, part in enumerate(parts):
        part_stripped = part.strip()
        if not part_stripped:
            continue

        # Check if this part is an author name
        if part_stripped.upper().rstrip('.') in KNOWN_AUTHORS:
            # Save previous commentary
            if current_author and current_text:
                commentaries.append({
                    "author": current_author,
                    "text": " ".join(current_text).strip()
                })
                current_text = []

            current_author = part_stripped.upper().rstrip('.')
        else:
            # This is commentary text
            if current_author:
                current_text.append(part_stripped)
            else:
                # Text before first author attribution
                if part_stripped:
                    current_text.append(part_stripped)

    # Add final commentary
    if current_text:
        commentaries.append({
            "author": current_author,
            "text": " ".join(current_text).strip()
        })

    # If no authors were found, return the whole text as one commentary
    if not commentaries or (len(commentaries) == 1 and not commentaries[0]["author"]):
        return [{"author": None, "text": text.strip()}]

    # Clean up each commentary: remove leading punctuation
    for comm in commentaries:
        if comm.get("text"):
            # Strip leading punctuation (commas, periods, spaces)
            comm["text"] = re.sub(r'^[,.\s]+', '', comm["text"])

    return commentaries


def parse_footnote(footnote_elem):
    """Parse a footnote/gloss element and extract structured commentary with authors."""
    verse_ref = None
    all_text_parts = []

    for child in footnote_elem:
        tag = child.tag
        text = (child.text or "").strip()
        tail = (child.tail or "").strip()

        if tag == "fr":  # Footnote reference (verse number)
            verse_ref = text
        elif tag == "ft":  # Footnote text (commentary)
            if text:
                all_text_parts.append(text)
        elif tag == "fk":  # Footnote keyword (quoted phrase) - include in text
            if text:
                all_text_parts.append(text)

        if tail:
            all_text_parts.append(tail)

    # Combine all text
    full_text = " ".join(all_text_parts).strip()

    # Extract individual commentaries with authors
    commentaries = extract_author_citations(full_text)

    # Add verse reference to each commentary
    for comm in commentaries:
        comm["verse_ref"] = verse_ref

    return commentaries


def parse_usfx():
    """Parse the USFX XML file and organize by book/chapter."""
    print(f"Parsing {USFX_FILE}...")

    # Parse XML
    tree = ET.parse(USFX_FILE)
    root = tree.getroot()

    # Data structure: {book_code: {chapter_num: {verses: [...], commentaries: [...]}}}
    books = defaultdict(lambda: defaultdict(lambda: {"verses": [], "commentaries": []}))

    current_book = None
    current_chapter = None
    current_verse_num = None
    current_verse_text = []

    # Iterate through all book elements
    for book_elem in root.findall("book"):
        book_id = book_elem.get("id")
        current_book = book_id
        print(f"Processing {book_id}...")

        # Iterate through book contents
        for elem in book_elem.iter():
            tag = elem.tag

            # Chapter marker
            if tag == "c":
                # Save previous verse if exists
                if current_verse_num and current_verse_text:
                    verse_text = " ".join(current_verse_text).strip()
                    books[current_book][current_chapter]["verses"].append({
                        "verse_num": current_verse_num,
                        "text": verse_text
                    })
                    current_verse_text = []
                    current_verse_num = None

                current_chapter = elem.get("id")

            # Verse marker
            elif tag == "v":
                # Save previous verse if exists
                if current_verse_num and current_verse_text:
                    verse_text = " ".join(current_verse_text).strip()
                    books[current_book][current_chapter]["verses"].append({
                        "verse_num": current_verse_num,
                        "text": verse_text
                    })
                    current_verse_text = []

                current_verse_num = elem.get("id")

                # Get text content after the verse marker
                if elem.tail:
                    current_verse_text.append(elem.tail.strip())

            # Verse end marker
            elif tag == "ve":
                # Save the verse
                if current_verse_num and current_verse_text:
                    verse_text = " ".join(current_verse_text).strip()
                    books[current_book][current_chapter]["verses"].append({
                        "verse_num": current_verse_num,
                        "text": verse_text
                    })
                    current_verse_text = []
                    current_verse_num = None

            # Footnote (gloss)
            elif tag == "f":
                if current_chapter:
                    commentaries = parse_footnote(elem)
                    # Add all individual commentaries
                    books[current_book][current_chapter]["commentaries"].extend(commentaries)

            # Regular text
            elif elem.text and current_verse_num:
                text = elem.text.strip()
                if text and tag not in ["fr", "fk", "ft", "f"]:
                    current_verse_text.append(text)

    return books


def save_to_files(books):
    """Save parsed data to JSON files organized by book/chapter with French names."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    stats = {
        "total_books": 0,
        "total_chapters": 0,
        "total_verses": 0,
        "total_commentaries": 0
    }

    # Process books in canonical order
    for book_code, french_name in BOOK_NAMES:
        if book_code not in books:
            continue

        chapters = books[book_code]
        book_order = BOOK_ORDER[book_code]

        # Create directory with canonical number and French name
        # e.g., "01_genese", "02_exode"
        book_slug = french_name.lower().replace(' ', '_').replace('é', 'e').replace('è', 'e').replace('ï', 'i').replace('ô', 'o')
        book_dir = OUTPUT_DIR / f"{book_order:02d}_{book_slug}"
        book_dir.mkdir(exist_ok=True)

        stats["total_books"] += 1

        for chapter_num, content in sorted(chapters.items(), key=lambda x: int(x[0])):
            stats["total_chapters"] += 1
            stats["total_verses"] += len(content["verses"])
            stats["total_commentaries"] += len(content["commentaries"])

            # French chapter filename: "chapitre_1.json"
            output_file = book_dir / f"chapitre_{chapter_num}.json"

            chapter_data = {
                "book": french_name,
                "book_code": book_code,
                "chapter": int(chapter_num),
                "verses": content["verses"],
                "commentaries": content["commentaries"]
            }

            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(chapter_data, f, ensure_ascii=False, indent=2)

        print(f"  ✓ {french_name}: {len(chapters)} chapitres")

    # Save summary stats
    stats_file = OUTPUT_DIR / "parse_stats.json"
    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)

    return stats


def main():
    print("=" * 60)
    print("Glossa Ordinaria Parser")
    print("=" * 60)
    print()

    if not USFX_FILE.exists():
        print(f"❌ Error: USFX file not found at {USFX_FILE}")
        return

    # Parse the XML
    books = parse_usfx()

    print()
    print("=" * 60)
    print("Saving to files...")
    print("=" * 60)
    print()

    # Save to JSON files
    stats = save_to_files(books)

    print()
    print("=" * 60)
    print("✓ Parsing Complete!")
    print("=" * 60)
    print(f"Books parsed: {stats['total_books']}")
    print(f"Chapters: {stats['total_chapters']}")
    print(f"Verses: {stats['total_verses']}")
    print(f"Commentaries: {stats['total_commentaries']}")
    print(f"\nOutput directory: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
