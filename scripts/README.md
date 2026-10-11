# Calmet pipeline

`data/<volume>/normalized/page_NNNN.json` is the definitive text. Every script here
reads and writes those files (tracked in the git repo in `data/`), and `export.py`
turns them into the dom-calmet-web data. All locations are in `paths.py`; the books,
their volumes and website slugs are in `books.json`.

Run everything from this folder with `python3` (the editors need Pillow, see below).

## A new book

1. Seed `normalized/` from `raw_json/commentaire/` (only if it doesn't exist yet).
2. `modernize.py <volume>`: rule-based pre-pass (ſ, common OCR slips).
3. `LLM_BACKEND=claude python3 llm_modernize.py <volume>`: modernize the French with an LLM
   (cached in `cache/llm_cache.json`; run in the foreground).
4. `fix_typography.py <volume>`: ſ → s, `&c.` → etc., `&` → et.
5. `normalize_refs.py <volume>`: verse numbers and `verse_ref` to digits, no numbers in verse text.
6. `fix_markers.py <volume>`: footnote calls to `^{(a)}`, Jésus-Christ.
7. Psalms only: `fix_psalm_verses.py <volume>`.

## Checks and review

- `seam_check.py <volume> …`: reads every page break for lost or repeated lines
  (Claude, cached in `cache/seam_cache.json`) → `docs/seam_check.json`.
- `audit_integrity.py ../docs/integrity_audit_<date>.json` → that report plus
  `docs/review_queue.json` (missing verses, page breaks, verse_ref order, notes without
  commentary, capitals, broken footnote calls, …).
- Work through the queue in the editor:
  `uv run --no-project --with pillow python review_editor.py`
  (`page_editor.py` is the plain page editor.) Commit in `data/` after a session.

## Publish

1. `python3 export.py <book key …>` or `python3 export.py --published`
2. In dom-calmet-web: `npm run build`, commit, `npm run deploy`.

`check_flow.py <site slug>` checks the exported verses for numbering gaps.

## Other folders

- `cache/`: LLM and seam caches (large; not in git).
- `legacy/studium_v1/`: the earlier raw → normalized scripts.
- `legacy/agy/`: one-off fixes from the agy sessions, kept for reference.
