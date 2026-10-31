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
4. `modernize_inplace.py <volume>`: the spelling rules the LLM pass leaves. Each page gets
   `clean_mechanical.py`'s rules first, then its own (§12 of NEXT_VOLUMES.md says why the order
   matters); `--dry-run` first. `clean_mechanical.py <volume>` alone runs only the first half.
5. `fix_typography.py <volume>`: ſ → s, `&c.` → etc., `&` → et.
6. `normalize_refs.py <volume>`: verse numbers and `verse_ref` to digits, no numbers in verse text.
7. `fix_markers.py <volume>`: footnote calls to `^{(a)}`, Jésus-Christ.
8. `tidy_fields.py <volume>`: underscores, empty annotations, margin years, blank lines.
9. `paragraph_breaks.py <volume>`: numbered points (1°. 2°.) on their own paragraph.
10. Psalms only: `fix_psalm_verses.py`, `psalms_check.py`, `fill_psalm_verses.py`,
   `add_psalm_titles.py` (see NEXT_VOLUMES.md).
11. `assign_chapters.py <book key>`: the `chapter` field on every verse and commentary block
   (export reads it; edit it in the editor). Writes `docs/chapter_check.json` with the places
   it had to decide; they go into the review queue.

## Checks and review

- `footnotes.py run <volume|book|all> … [99-140] [--apply]` (with Pillow: `uv run --no-project --with pillow python …`):
  Bible references written out with Calmet's names and checked against the Vulgate; Hebrew and
  Greek checked against the Hebrew Bible and the Septuagint (`cache/refs/`), the doubtful ones
  read on the scan by Claude; other abbreviations written out (`footnote_glossary.txt`) →
  `docs/footnotes/<volume>.json`. `footnotes.py apply <volume> [99-140]` writes it in, holding
  flagged notes. Claude's answers are cached in `cache/footnote_cache.json`. With
  `FOOTNOTE_BACKEND=agy` (and `AGY_MODEL` to pick a model) the abbreviations are written out by agy
  instead; the scans stay with Claude, and answers Claude already gave are reused.

- `footnote_tags.py run <volume|book|all> … [--local] [--model agy|haiku|both]`: tags each footnote
  (`"tags"` in normalized/: hebrew, greek, verse, fathers, rabbis, versions, classical, commentators,
  title, latin, explanation, abbrev, old-ref, bad-ref, ibid, uncertain) and gives the original title of
  the works it names (`"titles"`). Rules first (the glossary, `footnote_names.txt`); the notes still
  unclear go to agy, then Haiku (cached by text in `cache/footnote_tags_cache.json`). Tags changed by
  hand in the editor are kept on every run (the tagger's own result: `docs/footnotes/tags_auto.json`).
  `footnote_tags.py names` adds the works and authors not yet in `footnote_names.txt` (Haiku, from the
  notes as Calmet printed them beside their written-out form); correct that file by hand.
  `footnote_tags.py stats …` counts the tags. In the editor, "Tags" shows them under each footnote
  (click to add or remove); search `tag:fathers`, `tag:fathers Basile` or `tag:none`.

- `audit_integrity.py` (`first_no_lemma`): the first note of a page with neither `latin_quote` nor
  `french_translation` is normally the end of the page before's note. Flagged when it opens with its
  lemma in capitals (the lemma went into the commentary: a normal issue), or, as optional (`--all`),
  when the page before ended a sentence and it opens a new one that does not start with a name (the
  first word is capitalised mid-sentence more often than not in lower case across the commentary:
  Ézéchiel, Hérodote). Hyphen-cut words at the page turn are `hyphen_cut`'s.

- `sync_continuations.py <volume|book|all> … [--apply] [--verbose]`: a note split over a page turn (or in
  two on the page) is several blocks, each with its own `chapter` and `verse_ref` copied when it was made.
  A block with no lemma and no translation takes those of the block before it, in page order (rule in
  `continuations.py`). Blocks that may open a note of their own (a capital after a full stop) are left
  alone and counted. The editor does the same when you save: a changed chapter or verse_ref goes to the
  blocks that go on from that note, and from the page's last note to the next page's (page editor only).

- `audit_integrity.py` (`missing_start`): the first note of a page opens in lower case, with no lemma, but
  the page before ends on a lemma or translation with no comment (or has no notes): a comment does not
  begin mid-sentence, so its start is missing. Shown in the page-turn editor (page after the turn).

- `seam_check.py <volume> …`: reads every page break for lost or repeated lines
  (agy by default, cached in `cache/seam_cache.json`; `SEAM_BACKEND=claude`, `AGY_MODEL`,
  `AGY_EFFORT=low` for a faster pass) → `docs/seam_check.json`.
- `spellcheck.py scan <volume|book> …`: hunspell (`brew install hunspell`, French dictionary
  in `~/Library/Spelling/fr_FR`) over every French field (cached per word in
  `cache/hunspell_cache.json`) → `docs/hunspell/<volume>.json`. Then
  `spellcheck.py inspect …` (long s, -oit/-oient, trémas, frequent words) and
  `spellcheck.py candidates … [--limit N]` (likely errors by kind, `old_spelling` among them:
  azyle, succez, appella, whose modern form is elsewhere in the text) to read it; both leave out
  Latin (words of the Vulgate), abbreviations and the names in `spellcheck_names.txt`
  (`--all` keeps them). `spellcheck.py context <volume|book> <word> …` shows where a word
  occurs. Report only; a fix goes into `clean_mechanical.fix_spelling` when it is a word for a
  word (an OCR slip, an old spelling), into `modernize_inplace.py` when it depends on the words
  around it (`ferai` → `serai` only in `je ferai leur Dieu`).
- `vulgate_check.py <volume|book|all> … [--apply]`: the Latin of every verse against the Vulgate,
  word by word, edition spellings aside (cœli/caeli, tanquam/tamquam) → `docs/vulgate_check.json`,
  sorted into long s and broken words (`--apply` writes these in, in Calmet's spelling), dropped æ
  (terra/terræ), typos, other readings, verse numbering (the text is a neighbour's) and verses that
  match nothing (a lemma or French in the Latin field). All but the first two are for review.
- `ref_check.py <volume|book|all> … [--apply]`: the commentary's Bible references (chapitre:verset)
  against the Vulgate → `docs/ref_check.json`: verses that do not exist, and Latin quoted with a
  reference that is another verse, each with its candidates (a digit misread, a Roman numeral off,
  the verses around, the verse the quotation is). `--apply` writes in those the quotation settles;
  the rest go to a model (one Haiku call settled a dozen for under a cent) or a reader.
- `seam_join.py <volume|book|all> … [--apply]`: a lemma or translation the page turn cut off
  (`hyphen_cut` in the queue) goes on in the same field of the next page's first block, taken from
  its french_commentary: the capitals up to the lemma's full stop, the French up to the earliest
  stop near the lemma's length; a repeat over the turn printed once → `docs/seam_join.json`.
  `calmet.py` joins the two halves on export (a word broken by a hyphen too). Also a comment whose
  last line the transcription finished as a sentence and the next page repeats (`period_seam`:
  "aujourd'hui. ‖ d'hui"): the fragment and the made-up words are dropped. Nothing moves between pages.
- `pasted_footnotes.py <volume|book|all> … [--apply]`: footnotes pasted at the end of a comment as
  lines "(a) …" (Jérémie) moved into the page's footnotes.
- `profile_rules.py <volume|book> … [--top N]`: times each rule of
  `clean_mechanical.fix_spelling` on those pages (slowest first, with its line) and lists the
  rules that still change already-cleaned text. Changes no page.
- `audit_integrity.py ../docs/integrity_audit_<date>.json` → that report plus
  `docs/review_queue.json` (missing verses, page breaks, verse_ref order, notes without
  commentary, lemmas without translation, capitals, broken footnote calls, …).
- The scan's OCR in the editor: tick "OCR" above the scan ("Read the scan" runs Kraken on a page not
  yet read, about 15 s; `python3 scan_ocr.py VOLUME [first-last]` reads a whole volume ahead, cached
  in `cache/ocr/`, Kraken in `../.kraken-venv`). Over the scan: red, a word the JSON lacks; amber, a
  different word; dashed, nearly the same; the JSON's words the scan lacks are underlined red in the
  text. Click a box: the word in its field; the caret in a field: its word on the scan; the counter
  goes from flag to flag. Shift-drag (or "Box", then drag) a region of the scan: a to-do for it, drawn
  there whenever the page is open. The running header and "COMMENTAIRE." are left out, unsure
  readings and the footnotes (expanded by design) are not flagged.
- Work through the queue in the browser: `python3 review_web.py [VOLUME [PAGE]] [--fresh] [filters]`
  (with no book given it resumes where you stopped: the page, and without filters the same filters and
  issue; `--fresh` starts from the first open issue)
  opens the review editor (scan beside text, the page's issues on the left, chapter:verse jump box,
  three themes; anything else typed in that box searches the book's text, accents and case aside, with
  an All books switch: `review_search.py`; the book menu doubles as the book filter, each book with how many issues of the list it
  has; Issue ‹ › wraps round the list; Reopen takes back the last issue marked resolved, false positive or
  skipped; "Highlights" hides the marks an issue puts on the page; selected text gets a small menu: italics,
  copy, cut, paste (with a space after); a click in a field gets Paste alone; page to-dos, for what
  no check finds: "+ To-do" in the issue bar for the page, or "To-do" on and the "+" of a field,
  with one-click presets from `todo_presets.txt` ("Needs rescan"); they are issues of the type
  To-do, Resolved ticks one off, ✕ on its card deletes it; a to-do added while an issue of the page is
  open puts that issue On hold, a status of its own (neither resolved nor a false positive, with its
  button and filter), and opens it again once the to-do is done or deleted). Same filters as before (`--all`, `--kind`, `--category`, `--type`, `--book`,
  `--skipped`, `--resolved`, `--false-positive`, `--all-status`, `--list-fp`); it serves on
  127.0.0.1 only and the printed link carries the session key. Opening an issue marks the words it
  quotes and outlines the field it names (`where` in the queue, from `audit_integrity.py`). Saving a
  page re-runs the audit of its book (`page_audit.py`, 1–3 s): issues no longer found close as
  "fixed on save", new ones appear (the queue file itself changes only with the next full audit).
  A page edited outside the editor (by hand, by an LLM) is loaded again within a couple of seconds and
  its book re-checked the same way, so you only have to look and mark it; with unsaved edits to that
  page it asks first (Keep mine / Reload theirs).
  A page-turn issue opens the page-turn view (`T` from any page, Esc back): the foot of the page over
  the head of the next, both editable, with the text as the site joins it (`review_turns.py`).
  Proposed fixes show word by word with Accept (write and resolve), Edit (into the fields, unsaved)
  and Reject (`review_proposals.py`): `seam_join.py`'s join at a page turn, computed from the pages
  as they are; the held write-outs of `docs/footnotes/<volume>.json` and the candidates of
  `docs/ref_check.json`, which become issues of their own types ("Footnote write-out to check",
  "Verse reference to check"; Reject makes them false positives). Batch: every issue of the type
  chosen in the filters in a table: tick and accept the proposals, or tick any rows (proposal or not) and
  mark them Resolved or False positive; the field an issue points at is a text box in its row (Save n edits
  writes them, one write per page; Resolve saves a ticked row's typed text first). The foot bar marks
  the pages read through, and a chapter bar at its left fills with the share of the current chapter's
  pages reviewed, following the review as you go. The review is kept per book in
  `data/<book>/review.json` (statuses, false positives with what they said, the page to-dos), so
  that volunteers working on different books never touch the same file; the editor folds the old
  shared files (`data/.review_queue_progress.json`, `docs/false_positives.json`,
  `docs/manual_issues.json`) into them when it starts. Commit in `data/` after a session.
  Tests: `uv run --no-project --with pytest python -m pytest tests -q` and `node --test tests/js`.

## Publish

1. `python3 export.py <book key …>` or `python3 export.py --published`
2. In dom-calmet-web: `npm run build`, commit, `npm run deploy`.

`check_flow.py <site slug>` checks the exported verses for numbering gaps.

## Other folders

- `cache/`: LLM and seam caches (large; not in git: the answers are attached to the GitHub releases).
- `vulgate/`: the Clementine Vulgate, one JSON per book (a copy of janvier-s/douayrheimsbible's `static/data/vul`; `CALMET_VULGATE` points elsewhere).
- `legacy/studium_v1/`: the earlier raw → normalized scripts.
- `legacy/agy/`: one-off fixes from the agy sessions, kept for reference.
