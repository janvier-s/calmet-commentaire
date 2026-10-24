"""The integrity audit of one book, for the review editor's re-check on save.

Runs audit_integrity.audit_book unchanged (the same checks as the full audit), after clearing
calmet's page caches so the pages are read as they are now on disk.
"""
import json

import audit_integrity
import calmet
from paths import BOOKS, BY_VOLUME, DOCS


def recheck_book(vol):
    """The audit's queue items for the book that holds `vol`."""
    key = BY_VOLUME[vol]
    info = BOOKS[key]
    calmet.pages.cache_clear()
    calmet.apparatus.cache_clear()
    queue = audit_integrity.audit_book(key, info, info.get("site") or audit_integrity.site_slugs().get(info["fr"]))["queue"]
    # where seam_check.py has read the page breaks, its verdicts replace these guesses (as audit_integrity.main)
    seam = DOCS / "seam_check.json"
    read = json.loads(seam.read_text(encoding="utf-8")) if seam.exists() else {}
    return [q for q in queue if not (q["book_dir"] in read and q["kind"] in ("possible_gap", "seam_artifact"))]
