#!/usr/bin/env python3
"""
Transform normalized page-based JSON into chapter-based entity files.

Reads all normalized/page_*.json files for a book, groups them by chapter,
merges continuation commentaries, and outputs one JSON per chapter plus
book_metadata.json.

Usage: python transform.py <book_directory>
Example: python transform.py 01_genese
"""

import json
import sys
from pathlib import Path

# Add scripts dir to path for config import
sys.path.insert(0, str(Path(__file__).parent))
from config import BOOK_MAPPINGS


def join_text(prev_text, next_text):
    """Join text across page boundaries, handling hyphenation."""
    if not prev_text:
        return next_text
    if not next_text:
        return prev_text
    if prev_text.endswith("-"):
        return prev_text[:-1] + next_text
    return prev_text + " " + next_text


def is_continuation(commentary):
    """Check if a commentary entry is a continuation from the previous page."""
    return (
        commentary.get("commentary_id") == 1
        and commentary.get("verse_ref") is None
        and commentary.get("latin_quote") is None
        and commentary.get("french_translation") is None
    )


def merge_preface(existing_preface, new_preface):
    """Merge chapter_preface sections across pages."""
    if existing_preface is None:
        return new_preface
    if new_preface is None:
        return existing_preface

    merged = {
        "intro": existing_preface.get("intro") or "",
        "sections": list(existing_preface.get("sections") or []),
    }

    # Merge intro if new page has one
    if new_preface.get("intro"):
        merged["intro"] = join_text(merged["intro"], new_preface["intro"])

    existing_nums = {s["section_number"]: i for i, s in enumerate(merged["sections"])}

    for section in new_preface.get("sections") or []:
        sn = section["section_number"]
        if sn in existing_nums:
            idx = existing_nums[sn]
            merged["sections"][idx]["content"] = join_text(
                merged["sections"][idx]["content"], section["content"]
            )
        else:
            merged["sections"].append(dict(section))
            existing_nums[sn] = len(merged["sections"]) - 1

    return merged


def transform_book(book_dir):
    script_dir = Path(__file__).parent
    data_dir = script_dir.parent / "data"
    book_path = data_dir / book_dir

    normalized_dir = book_path / "normalized"
    if not normalized_dir.exists():
        print(f"Error: {normalized_dir} does not exist")
        sys.exit(1)

    transformed_dir = book_path / "transformed"
    chapters_dir = transformed_dir / "chapters"
    chapters_dir.mkdir(parents=True, exist_ok=True)
    commentary_txt_dir = transformed_dir / "commentary_txt"
    commentary_txt_dir.mkdir(parents=True, exist_ok=True)

    book_name = BOOK_MAPPINGS.get(book_dir, book_dir)

    # Read all pages in order
    page_files = sorted(normalized_dir.glob("page_*.json"))
    if not page_files:
        print("Error: No page files found")
        sys.exit(1)

    print(f"Processing {len(page_files)} pages for {book_name}...")

    # State tracking
    chapters = {}  # chapter_num -> chapter data dict
    current_chapter = None
    book_title = None

    for page_file in page_files:
        page_name = page_file.name
        with open(page_file, "r", encoding="utf-8") as f:
            page = json.load(f)

        # Capture book title from first page that has it
        if page.get("book_title") and not book_title:
            book_title = page["book_title"]

        # Detect chapter start
        ch_num = page.get("chapter_number")
        if ch_num is not None:
            # Check if first commentary is a continuation from previous chapter
            continuation_commentary = None
            commentaries = page.get("commentary") or []
            if commentaries and is_continuation(commentaries[0]):
                continuation_commentary = commentaries[0]
                commentaries = commentaries[1:]

            # Attach continuation to previous chapter
            if continuation_commentary and current_chapter is not None:
                prev_ch = chapters[current_chapter]
                if prev_ch["commentaries"]:
                    last = prev_ch["commentaries"][-1]
                    last["french_commentary"] = join_text(
                        last["french_commentary"],
                        continuation_commentary.get("french_commentary") or "",
                    )
                    last["source_pages"].append(page_name)

            # Start new chapter
            current_chapter = ch_num
            chapters[ch_num] = {
                "book": book_name,
                "book_dir": book_dir,
                "chapter": ch_num,
                "chapter_summary": page.get("chapter_summary"),
                "chapter_preface": page.get("chapter_preface"),
                "verses": [],
                "commentaries": [],
                "footnotes": [],
                "_verse_map": {},  # verse_number -> index (internal)
                "_last_verse_ref": None,  # for footnote assignment
            }

            # Process remaining commentaries on this page (non-continuation)
            _process_commentaries(chapters[ch_num], commentaries, page_name)
        else:
            # Continuation page (no chapter_number)
            if current_chapter is None:
                # Before chapter 1 — skip
                continue

            ch_data = chapters[current_chapter]
            commentaries = page.get("commentary") or []

            # Merge chapter preface across pages
            if page.get("chapter_preface"):
                ch_data["chapter_preface"] = merge_preface(
                    ch_data["chapter_preface"], page["chapter_preface"]
                )

            # Check continuation
            if commentaries and is_continuation(commentaries[0]):
                if ch_data["commentaries"]:
                    last = ch_data["commentaries"][-1]
                    last["french_commentary"] = join_text(
                        last["french_commentary"],
                        commentaries[0].get("french_commentary") or "",
                    )
                    last["source_pages"].append(page_name)
                commentaries = commentaries[1:]

            _process_commentaries(ch_data, commentaries, page_name)

        if current_chapter is None:
            continue

        ch_data = chapters[current_chapter]

        # Process verses
        for v in page.get("verses") or []:
            vn = v.get("verse_number")
            if vn is None:
                continue
            if vn in ch_data["_verse_map"]:
                # Same verse on multiple pages — add source page
                idx = ch_data["_verse_map"][vn]
                if page_name not in ch_data["verses"][idx]["source_pages"]:
                    ch_data["verses"][idx]["source_pages"].append(page_name)
            else:
                ch_data["_verse_map"][vn] = len(ch_data["verses"])
                ch_data["verses"].append(
                    {
                        "book": book_name,
                        "chapter": current_chapter,
                        "verse_number": vn,
                        "latin": v.get("latin"),
                        "french": v.get("french"),
                        "annotations": v.get("annotations"),
                        "source_pages": [page_name],
                    }
                )

        # Process footnotes — verse_ref = last verse_ref seen on this page
        # Determine last verse_ref from commentaries on this page
        page_commentaries = page.get("commentary") or []
        last_vref = ch_data.get("_last_verse_ref")
        for c in page_commentaries:
            if c.get("verse_ref") is not None:
                last_vref = c["verse_ref"]
        ch_data["_last_verse_ref"] = last_vref

        for fn in page.get("footnotes") or []:
            ch_data["footnotes"].append(
                {
                    "book": book_name,
                    "chapter": current_chapter,
                    "verse_ref": last_vref,
                    "marker": fn.get("marker"),
                    "text": fn.get("text"),
                    "source_page": page_name,
                }
            )

    # Renumber commentary_seq and clean up internal fields, then write
    total_chapters = len(chapters)
    for ch_num, ch_data in sorted(chapters.items()):
        # Renumber commentary_seq
        for i, c in enumerate(ch_data["commentaries"], 1):
            c["commentary_seq"] = i

        # Remove internal tracking fields
        ch_data.pop("_verse_map", None)
        ch_data.pop("_last_verse_ref", None)

        # Write chapter file
        filename = f"chapter_{ch_num:02d}.json"
        out_path = chapters_dir / filename
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(ch_data, f, ensure_ascii=False, indent=2)

        # Write commentary_txt file (minimal, for spellcheck)
        commentary_txt = [
            {
                "commentary_seq": c["commentary_seq"],
                "french_commentary": c["french_commentary"],
            }
            for c in ch_data["commentaries"]
        ]
        txt_path = commentary_txt_dir / f"chapter_{ch_num:02d}.json"
        with open(txt_path, "w", encoding="utf-8") as f:
            json.dump(commentary_txt, f, ensure_ascii=False, indent=2)

    # Write book metadata
    metadata = {
        "book": book_name,
        "book_dir": book_dir,
        "book_title": book_title,
        "total_chapters": total_chapters,
    }
    meta_path = transformed_dir / "book_metadata.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print(f"Wrote {total_chapters} chapter files to {chapters_dir}")
    print(f"Wrote book_metadata.json to {transformed_dir}")


def _process_commentaries(ch_data, commentaries, page_name):
    """Add non-continuation commentaries to chapter data."""
    for c in commentaries:
        verse_ref = c.get("verse_ref")
        if verse_ref is not None:
            ch_data["_last_verse_ref"] = verse_ref
        ch_data["commentaries"].append(
            {
                "book": ch_data["book"],
                "chapter": ch_data["chapter"],
                "verse_ref": verse_ref,
                "commentary_seq": None,  # renumbered later
                "latin_quote": c.get("latin_quote"),
                "french_translation": c.get("french_translation"),
                "french_commentary": c.get("french_commentary"),
                "source_pages": [page_name],
            }
        )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python transform.py <book_directory>")
        print("Example: python transform.py 01_genese")
        sys.exit(1)

    transform_book(sys.argv[1])
