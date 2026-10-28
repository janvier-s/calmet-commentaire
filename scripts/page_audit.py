"""The integrity audit of one book, for the review editor's re-check on save.

Runs audit_integrity.audit_book unchanged (the same checks as the full audit), after clearing
calmet's page caches so the pages are read as they are now on disk.
"""
import json

import audit_integrity
import calmet
import paths
from paths import BOOKS, BY_VOLUME, DOCS


def recheck_book(vol, data=None):
    """The audit's queue items for the book that holds `vol`; `data`: another data folder (a copy).
    None for a book the full audit leaves out (audit_integrity.main), so nothing is closed or added."""
    key = BY_VOLUME.get(vol)
    info = BOOKS.get(key) if key else None
    if not info or key in audit_integrity.EXCLUDED:
        return None
    if data is not None:  # the audit and the export read paths.DATA and their own copy of it
        paths.DATA = audit_integrity.STUDIUM = data
    # false positives marked or reopened since the last run: the audit drops the ones in this set
    audit_integrity.FP_IDS = audit_integrity.load_false_positives()
    calmet.pages.cache_clear()
    calmet.apparatus.cache_clear()
    queue = audit_integrity.audit_book(key, info, info.get("site") or audit_integrity.site_slugs().get(info["fr"]))["queue"]
    # where seam_check.py has read every page break, its verdicts replace these guesses (as audit_integrity.main)
    seam = DOCS / "seam_check.json"
    read = json.loads(seam.read_text(encoding="utf-8")) if seam.exists() else {}
    done = audit_integrity.seam_fully_read(read)
    return [q for q in queue if not (q["book_dir"] in done and q["kind"] in ("possible_gap", "seam_artifact"))]
