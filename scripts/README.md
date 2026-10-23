# Calmet pipeline

`data/<volume>/normalized/page_NNNN.json` is the definitive text. Every script here
reads and writes those files (tracked in the git repo in `data/`), and `export.py`
turns them into the dom-calmet-web data. All locations are in `paths.py`; the books,
their volumes and website slugs are in `books.json`.

Run everything from this folder with `python3` (the editors need Pillow, see below).

## A new book

The full spec, with the conventions and the reasons behind each step: `NEXT_VOLUMES.md`.

1. Seed `normalized/` from `raw_json/commentaire/` (only if it doesn't exist yet).
2. `modernize.py <volume>`: rule-based pre-pass (ſ, common OCR slips).
3. `LLM_BACKEND=claude python3 llm_modernize.py <volume>`: modernize the French with an LLM
   (cached in `cache/llm_cache.json`; run in the foreground).
4. `fix_typography.py <volume>`: ſ → s, `&c.` → etc., `&` → et.
5. `normalize_refs.py <volume>`: verse numbers and `verse_ref` to digits, no numbers in verse text.
6. `fix_markers.py <volume>`: footnote calls to `^{(a)}`, Jésus-Christ.
7. `tidy_fields.py <volume>`: underscores, empty annotations, margin years, blank lines.
8. `paragraph_breaks.py <volume>`: numbered points (1°. 2°.) on their own paragraph.
9. Psalms only: `fix_psalm_verses.py`, `psalms_check.py`, `fill_psalm_verses.py`,
   `add_psalm_titles.py` (see NEXT_VOLUMES.md).
10. `assign_chapters.py <book key>`: the `chapter` field on every verse and commentary block
   (export reads it; edit it in the editor). Writes `docs/chapter_check.json` with the places
   it had to decide; they go into the review queue.

## Checks and review

- `footnotes.py run <volume> [99-140]` (with Pillow: `uv run --no-project --with pillow python …`):
  Bible references written out with Calmet's names and checked against the Vulgate; Hebrew and
  Greek checked against the Hebrew Bible and the Septuagint (`cache/refs/`), the doubtful ones
  read on the scan by Claude; other abbreviations written out (`footnote_glossary.txt`) →
  `docs/footnotes/<volume>.json`. `footnotes.py apply <volume> [99-140]` writes it in, holding
  flagged notes. Claude's answers are cached in `cache/footnote_cache.json`.

- `seam_check.py <volume> …`: reads every page break for lost or repeated lines
  (Claude, cached in `cache/seam_cache.json`) → `docs/seam_check.json`.
- `spellcheck.py scan <volume|book> …`: hunspell (`brew install hunspell`, French dictionary
  in `~/Library/Spelling/fr_FR`) over every French field (cached per word in
  `cache/hunspell_cache.json`) → `docs/hunspell/<volume>.json`. Then
  `spellcheck.py inspect …` (long s, -oit/-oient, trémas, frequent words) and
  `spellcheck.py candidates … [--limit N]` (likely errors by kind) to read it; both leave out
  Latin (words of the Vulgate), abbreviations and the names in `spellcheck_names.txt`
  (`--all` keeps them). `spellcheck.py context <volume|book> <word> …` shows where a word
  occurs. Report only; fixes go into `clean_mechanical.py`.
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
