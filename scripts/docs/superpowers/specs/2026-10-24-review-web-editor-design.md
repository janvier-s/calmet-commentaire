# Review editor as a web app: design

Date: 2026-10-24. Replaces `review_editor.py` and `page_editor.py` (Tkinter).

## Why

The Tk editors work, but only because the user has got used to them: they are ugly and Tk limits
what they can show (highlighting, diffs, side-by-side pages, theming). The user would have made it a
web app from the start. The move is also the chance to make the editor do more of the work: point at
the problem, offer the fixes the scripts already compute, and stop the flipping between pages.

## Who and where

One user, on their Mac, working alone through `docs/review_queue.json` (about 5,300 open-able items,
8,100 with the optional ones) and editing pages freely. Local only: bound to 127.0.0.1, no login, no
network access. Scripts (seam_join, footnotes, agy runs) may write pages in `data/` at the same time.

## Goals

1. The same work on a pleasant surface: three themes (paper, light, dark; following the Mac setting,
   switchable), sans-serif text throughout.
2. Every action the Tk editors have stays (list below), with better UI/UX.
3. No flipping between pages for page-break and verse/chapter-number problems.
4. Navigate by chapter and verse, not only by page.
5. See all issues on the current page at once.
6. Use the proposals the scripts already produce instead of retyping them.

## Non-goals

- No multi-user use, hosting, accounts or sync.
- No change to the data format: `data/<volume>/normalized/page_NNNN.json`, the queue, the progress
  file and `docs/false_positives.json` stay as they are, so both editors can be used during the switch.
- No new detection logic beyond what the audit and scripts already find (moving checks so they can
  run on one page is in scope; inventing checks is not).

## Anti-goals (a failure even if it works)

- Text moving between pages. Every word stays on its scan page; fixes move text between fields of the
  same page only. The page-turn view must make this impossible, not merely unlikely.
- Losing typed edits (navigation, a concurrent script write, a crash).
- Committing or overwriting files the user or a script changed outside the editor. The user often
  has uncommitted pages of their own in `data/`.
- Losing any capability of the Tk editors.

## Constraints

- Python 3.15 (Homebrew; its own `tkinter` is not importable, Tk runs via `uv run --with pillow`).
  The new editor must not need Tk.
- Reuse, don't fork: `punctuation.clean_page` + `page_editor.trim` on save, `paths.py`,
  `calmet.notes` / `join_seam` for the site preview, `audit_integrity.py` checks, `find_source_image`
  (move it out of `page_editor.py` so it no longer pulls in Tk).
- Scans are PNGs under `data/<book>/source_images/...`; serve them as files, scale in the browser.
- Started like today: one command from `scripts/`, opens the browser.

## Decided

### Main screen (user chose layout A)

Three columns:

- **Left: this page's issues.** Every queue item on the page as a card (kind label, message),
  the current one outlined, resolved ones struck through. Under them: previous/next page with open
  issues, and how many are open in the book. Status filter, category, kind and book filters (as now)
  live here or in the top bar.
- **Middle: the scan**, zoom (buttons, 1:1, Fit, Cmd+scroll) and drag to pan.
- **Right: the page's text** as blocks: page heading fields, verses, commentary blocks, footnotes.
  - Above the first block, a context strip: where the previous page ends (chapter, last verse, last
    commentary's verse_ref and tail).
  - Below the last block, a strip: where the next page starts (marked CONTINUATION when its first
    block has no lemma).
  - Opening an issue scrolls to its field and highlights the flagged words.

Top bar: book, chapter:verse jump box (`17:2` ⏎ opens the page with that verse or note; `17` the
chapter's first page), page number jump, ◀ page / page ▶, ◀ issue / issue ▶, Resolved (⌘⏎), Skip,
False positive (⌘P), save state.

### Adding and changing entries

- **New commentary block goes at the top by default**, carrying the chapter and verse_ref of the
  previous page's last commentary block (it usually continues that note).
- **"+ add below"** on every block; the new block takes the chapter and verse_ref of the block above.
- Add verse (inserted in number order, chapter from its neighbours, as now), add footnote (marker),
  add page heading fields, create a page that has a scan but no JSON.
- Delete any verse, block or footnote (with confirmation); reorder verses and blocks (drag or
  up/down), renumbering commentary_id.

### Page-turn view (user chose layout A: stacked)

Opens for any page-break issue, or from the main screen with a key. The foot of page A above the head
of page B, each next to its scan scrolled to the cut, both editable. Where a script proposes a fix, it
shows as a diff (red removed, green added) with **Accept / Edit / Reject**. Under it, the joined note
as the site will print it (from `calmet.notes`). ◀ turn / turn ▶ step to the previous/next page turn
that has an issue.

### Batch review (an option; one at a time stays the default)

For one kind of issue, a table: one row per item with its context (foot ‖ head, or the field) and the
proposal if any. Tick rows, "Accept N ticked"; "tick all with a proposal"; clicking a row opens it.

### Themes

Paper (warm off-white, as in the mockups), light (white, system look), dark (warm dark). Sans-serif
(system font) everywhere, including the text. Latin lemma in small caps, `_italics_` rendered as
italics, Hebrew kept right-to-left.

### Everything the Tk editors do, kept

From `page_editor.py`: open any book/page (and resume where you left off), page prev/next (←/→ when
not typing), go to page, edit every field with Tab / Shift-Tab between fields, ⌘S save, unsaved-changes
warning, italics toggle ⌘I on a selection and a "show `_` marks" switch, section filter (all / verses /
commentary / footnotes), the previous-page tail and next-page head strips, Open JSON in the external
editor, reveal the PNG in Finder, Flag for review (copies raw JSON + scan to `modernization_error/`),
zoom/pan, the scan dimmer (the "image overlay" slider: darkens the scan, 10% by default;
useful in the dark theme), `null` vs empty fields,
integer fields (`verse_number`, `commentary_id`, `verse_ref`, `chapter`, `chapter_number`).

From `review_editor.py`: the queue with status filter (open, false positives, skipped, resolved, all),
category, kind and book filters with counts; command-line filters (`--all`, `--kind`, `--book`,
`--category`, `--type`, `--skipped`, `--resolved`, `--false-positive`, `--all-status`, `--queue`) as
URL parameters or start options; Resolved / False positive / Skip / reopen; resolved and false
positives skipped by ◀/▶ in the open view; the false-positive sync with `docs/false_positives.json`
(including items no longer in the queue); `--list-fp`; reported issues (`docs/manual_issues.json`).

## New features (all wanted by the user)

1. **Point at the problem**: scroll to the field, highlight the words.
2. **Proposed fixes with Accept / Edit / Reject**, from what the scripts already write:
   `docs/seam_join.json` (review cases), `docs/ref_check.json` (verse candidates),
   `docs/vulgate_check.json` (readings), `docs/footnotes/<volume>.json` (held write-outs). Accept
   saves the page and marks the item resolved.
3. **Page-turn view** (above).
4. **Re-check on save**: the audit's checks run on the saved page (and its neighbours for page-turn
   checks); items that no longer apply close, new ones appear. The full audit stays for the whole run.
5. **Site preview** of the joined note, via `calmet.py`.
6. **Batch review** (above).
7. **The Vulgate beside the Latin** of each verse and lemma, differing words marked
   (`vulgate_check.py` has the comparison).
8. **Session history**: pages changed this session, each with its diff and undo; a **Commit** button
   that commits only those pages in `data/` (never `git add -u`, never other files).

## Left to the builder

- Server and front-end stack (user left it to Claude). Claude's call: a small Python server
  (standard library, or one light dependency if it clearly pays), plain HTML/CSS/JavaScript, no build
  step.
- How issue locations reach the editor. Queue items today are `{id, book_dir, page, kind, msg,
  optional}` with no field or offset; the audit (and the scripts' reports) will need to add where
  (section, index, field, span) so features 1 and 2 work. Items without it fall back to the page.
- How to split `audit_integrity.audit_book` (one ~560-line function per book) so its checks can run on
  one page; keep the full-book output identical.
- Matching proposals in the scripts' reports to queue items.
- Concurrent writes: detect that a page changed on disk since it was loaded (mtime or hash) and
  offer reload/merge rather than overwrite.
- Undo mechanics, keyboard map beyond the shortcuts named here, exact visual design within the three
  themes.
- Order of delivery. Claude's call: a port with the new layout and every existing action first (so the
  Tk editors can be retired), then the new features in the order 1, 4, 3, 2, 8, 5, 7, 6.

## Claude's calls (check these)

- The chapter:verse jump looks in the current book; it opens the page with that verse's text, or, if
  the verse has no text page, the page of the first commentary block on it. Another book: pick it first.
- Accept on a proposal saves the page and marks the item resolved; Edit applies it to the fields
  without saving, for you to adjust.
- Re-check on save marks items that no longer apply as resolved in the progress file (shown as
  "fixed on save"); new ones are added to the in-memory queue until the next full audit.
- ◀ / ▶ in the page-turn view go to the previous/next page turn with an open issue.
- The Tk editors stay until you are happy with the new one; removing them is a separate step.
- Commit asks for (or proposes) a message and lists the pages it will commit first.

## Mockups

`.superpowers/brainstorm/5036-1792855631/content/` (in STUDIUM): `layout.html` (A chosen),
`seam-view.html` (A chosen), `look.html`, `batch.html`.
