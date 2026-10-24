# Review Web Editor, Part 1 (the port) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local web app that does everything `review_editor.py` and `page_editor.py` do, in the
chosen layout and three themes, with chapter:verse navigation, the page's issues in a column,
previous/next page context, and new commentary blocks at the top or below any block.

**Architecture:** A standard-library Python HTTP server (`review_web.py`) over a tested, Tk-free core
(`page_text.py` for text helpers, `review_store.py` for pages, context, entry operations, queue and
progress). The browser side is plain ES modules with no build step; its pure logic (`text.js`) is
tested with `node --test` against the same cases as the Python.

**Tech Stack:** Python 3.15 stdlib (`http.server`, `json`, `pathlib`), pytest via
`uv run --no-project --with pytest`, plain HTML/CSS/JavaScript (ES modules), Node 26 `node --test`.

**Spec:** `scripts/docs/superpowers/specs/2026-10-24-review-web-editor-design.md`

Part 1 covers the spec's "Decided" section except the page-turn view, batch review and proposals,
plus every action in "Everything the Tk editors do, kept". Later plans: Part 2 (issue locations,
pointing at the problem, re-check on save), Part 3 (page-turn view, proposals, batch table),
Part 4 (session history and commit, site preview, the Vulgate beside the Latin).

## Global Constraints

- Local only: bind `127.0.0.1`; every `/api/` request carries the session token (`X-Token` header,
  or `?key=` on first load which sets a cookie); requests without it get 403.
- No Tk, no Pillow in the web editor's import chain.
- Data format unchanged: `data/<volume>/normalized/page_NNNN.json`, `docs/review_queue.json`,
  `data/.review_queue_progress.json`, `docs/false_positives.json`, `docs/manual_issues.json`,
  `data/.page_editor_state.json`. The Tk editors keep working on the same files throughout.
- Save = `trim(clean_page(data))` (punctuation.py + trim), written `json.dumps(..., ensure_ascii=False,
  indent=2)`, exactly as the Tk editors.
- Every word stays on its page: no operation in Part 1 writes to any page other than the one shown.
- Never overwrite a page changed on disk since it was loaded without the user choosing to.
- Themes: paper, light, dark; default follows `prefers-color-scheme` (light → paper), switchable and
  remembered in `localStorage`. Sans-serif (system font stack) everywhere.
- Kind labels: copy `KIND_LABELS` from `review_editor.py` verbatim (served by the API, not duplicated in JS).
- Run tests from `scripts/`: Python `uv run --no-project --with pytest python -m pytest tests -q`;
  JS `node --test tests/js`.

## Review Focus

1. A script (seam_join, footnotes `--apply`) writes the page while it is open with unsaved edits →
   save answers 409 with the disk version; the UI offers "Reload theirs" / "Keep mine (overwrite)";
   nothing is lost silently. Test: Task 2 `test_save_conflict`.
2. Unsaved edits when marking, moving to another issue/page, jumping, or closing the tab → mark and
   issue/page moves save first (a failed save stops the move, as in Tk); closing the tab warns
   (`beforeunload`). Test: Task 8 `test_mark_saves_first` (manual check list) and Task 6
   `test_mark_does_not_save_page`.
3. Hebrew text: display isolation marks (U+200E) never reach the file. Test: Task 2
   `test_save_strips_lrm`.
4. Conflict copies (`page_0001 2.json`) and missing pages: never listed, never written; a queue item on
   a page with a scan but no JSON offers "Create page". Test: Task 2 `test_pages_ignore_conflict_copies`,
   `test_create_page`.
5. Typed values in integer fields (`verse_number`, `commentary_id`, `verse_ref`, `chapter`,
   `chapter_number`): digits → int, `null` or emptied null → None, anything else kept as typed text (as
   Tk). Test: Task 2 `test_form_values`.

---

## File Structure

| File | Responsibility |
|---|---|
| `scripts/page_text.py` (create) | Pure text/file helpers moved out of `page_editor.py`: `trim`, `LRM`, `isolate_hebrew`, `italic_runs`, `toggle_italics`, `find_source_image`, `save_state`, `load_state`. |
| `scripts/page_editor.py` (modify) | Import those helpers from `page_text` (no behaviour change). |
| `scripts/review_store.py` (create) | `Store`: page list, read/save with version check, create page, form values, previous/next context, chapter:verse index; entry operations; queue, progress, filters, counts. |
| `scripts/review_web.py` (create) | HTTP server: token, static files, scans, JSON API over `review_store`; CLI; opens the browser. |
| `scripts/review_web/index.html`, `style.css` (create) | Page shell and the three themes. |
| `scripts/review_web/text.js` (create) | Pure JS: `italicRuns`, `toggleItalics`, `parseRef`. |
| `scripts/review_web/field.js` (create) | The editable field: rendering, caret, undo, paste, Cmd+I, Tab. |
| `scripts/review_web/app.js` (create) | Layout, page view, scan pane, queue column, top bar, dialogs. |
| `scripts/tests/` (create) | `conftest.py` (tmp data fixture), `test_page_text.py`, `test_store.py`, `test_ops.py`, `test_queue.py`, `test_web.py`; `tests/js/text.test.mjs`. |
| `scripts/README.md` (modify) | How to start it. |

---

### Task 1: Tk-free text helpers

**Files:**
- Create: `scripts/page_text.py`, `scripts/tests/conftest.py`, `scripts/tests/test_page_text.py`
- Modify: `scripts/page_editor.py:24-143` (definitions move out; replaced by imports)

**Interfaces:**
- Produces: `page_text.trim(o)`, `LRM`, `isolate_hebrew(s) -> str`, `italic_runs(s) -> (runs, marks, open_at)`,
  `toggle_italics(s, sa, sb) -> (text, start, end) | None`, `find_source_image(book_path: Path, page_num: int) -> Path | None`,
  `save_state(book, page, state_file=STATE_FILE)`, `load_state(state_file=STATE_FILE) -> (book, page)`,
  `DATA_DIR`, `STATE_FILE` — identical behaviour to today's `page_editor` versions.
- `conftest.py` produces fixture `data_dir(tmp_path)`: a `data/` with volume `22_proverbes`, pages
  193–195 (p.193 verses ch.17 v.1 and one commentary on 17:1 ending "…pleine de victimes.";
  p.194 a continuation block then a block on 17:2 and footnote (a); p.195 verse 17:4), a scan
  `source_images/commentaire/page_0194.png`, and a conflict copy `normalized/page_0194 2.json`.
  Also `docs/` with `review_queue.json` (4 items: two on p.194, one `optional`, one on p.196 which has a
  scan but no JSON), `false_positives.json` `{}`, `manual_issues.json` `[]`.

- [ ] **Step 1: Write the failing tests** — `test_toggle_italics_cases` (copy-in cases:
  `("a b c", 2, 3) -> ("a _b_ c", 3, 4)`; `("_a b c_", 2, 3) -> ("_a_ b _c_", ...)` un-italicizes the
  middle; selection of only spaces → `None`), `test_italic_runs_open_edge` (`"fin_ suite"` →
  `open_at == "start"`), `test_isolate_hebrew` (Hebrew run fenced with LRM, idempotent),
  `test_find_source_image(data_dir)` (p.194 found, p.193 → None), `test_state_roundtrip(tmp_path)`.
  Fill the expected values of the toggle cases by running today's `page_editor.toggle_italics` under
  `uv run --no-project --with pillow` before moving it, and paste them in.
- [ ] **Step 2: Run** `uv run --no-project --with pytest python -m pytest tests/test_page_text.py -q` — FAIL (no module).
- [ ] **Step 3: Move the definitions** into `page_text.py`; in `page_editor.py` replace them with
  `from page_text import DATA_DIR, STATE_FILE, LRM, trim, isolate_hebrew, italic_runs, toggle_italics, find_source_image, save_state, load_state`.
- [ ] **Step 4: Run** the tests — PASS; and `uv run --no-project --with pillow python -c "import page_editor, review_editor"` — no error.
- [ ] **Step 5: Commit** `git add page_text.py page_editor.py tests/ && git commit -m "Move the editors' text helpers into page_text.py"`

### Task 2: Pages: list, read, save, create, form values

**Files:**
- Create: `scripts/review_store.py`, `scripts/tests/test_store.py`

**Interfaces:**
- Consumes: `page_text.trim`, `LRM`, `find_source_image`; `punctuation.clean_page`.
- Produces:
  - `class Conflict(Exception)` with `.disk: dict`, `.version: str`.
  - `class Store(data: Path, docs: Path)`;
    `volumes() -> list[str]` (folders with `normalized/`);
    `pages(vol) -> list[int]` (only `page_NNNN.json`);
    `read(vol, page) -> (dict, version: str)` — version = `f"{st_mtime_ns}-{st_size}"`;
    `save(vol, page, data: dict, version: str | None, force=False) -> (dict, str)` — raises `Conflict`
    when the file's version differs and not `force`; applies `form_values` then `trim(clean_page(...))`;
    `create(vol, page) -> (dict, str)` — writes `EMPTY_PAGE` (copy from `review_editor.py`), refuses if
    the file exists;
    `scan(vol, page) -> Path | None`.
  - `form_values(data: dict) -> dict` — strips `LRM` from every string; in fields `verse_number`,
    `commentary_id`, `verse_ref`, `chapter_number`, `chapter`: `"12"` → `12`, `"null"`/`""`/None → None,
    other text kept.

- [ ] **Step 1: Failing tests** — `test_pages_ignore_conflict_copies` (`[193, 194, 195]`),
  `test_read_save_roundtrip` (save unchanged data → file content equals `json.dumps(trim(clean_page(d)), ensure_ascii=False, indent=2)`),
  `test_save_conflict` (read, then rewrite the file behind the store, save → `Conflict` whose `.disk`
  is the new content; `force=True` → written), `test_save_strips_lrm`, `test_form_values`
  (`{"verse_number": "7", "chapter": "null", "verse_ref": "7-8"}` → `7, None, "7-8"`),
  `test_create_page` (p.196 created equal to `EMPTY_PAGE`; second call raises `FileExistsError`).
- [ ] **Step 2: Run** `... pytest tests/test_store.py -q` — FAIL.
- [ ] **Step 3: Implement** `Store` and `form_values` in `review_store.py` (write with a temp file + `os.replace`).
- [ ] **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** `git add review_store.py tests/test_store.py && git commit -m "review_store: pages with version check"`

### Task 3: Context and chapter:verse navigation

**Files:**
- Modify: `scripts/review_store.py`
- Create: `scripts/tests/test_context.py`

**Interfaces:**
- Produces:
  - `Store.context(vol, page) -> {"prev": {...} | None, "next": {...} | None}`.
    `prev`: walk back from `page-1` up to 20 pages to the first page with a verse or a commentary
    block; `{"page", "chapter", "verse"` (last verse's chapter/number on that page, or None),
    `"verse_ref"`, `"commentary_chapter"` (last block's), `"tail"` (last block's `french_commentary`, last
    line, last 7 words, prefixed `…`) `}`.
    `next`: the following page: `{"page", "chapter", "verse"` (first verse), `"verse_ref"`, `"head"`
    (first block's `french_commentary`, 250 chars + `…`), `"continuation": bool` (first block has no
    `verse_ref`, `latin_quote`, `french_translation`)`}`.
  - `Store.locate(vol, chapter: int, verse: int | None) -> int | None` — the page whose verses hold
    (chapter, verse); else the page of the first commentary block with that `chapter` and int
    `verse_ref == verse`; with `verse=None`, the first page holding anything of that chapter. Index built
    per volume on first use, dropped on `save`/`create` of that volume.

- [ ] **Step 1: Failing tests** — `test_prev_context` (p.194 → prev page 193, chapter 17, verse 1,
  tail ends "pleine de victimes."), `test_prev_walks_back` (blank p.194 commentary/verses → p.195's prev
  is 193), `test_next_context_continuation` (p.193 → next 194, continuation True),
  `test_locate` (`(17, 2)` → 194 via commentary, `(17, 4)` → 195 via verse, `(17, None)` → 193,
  `(99, 1)` → None), `test_locate_after_save` (move 17:4 to p.194 and save → 194).
- [ ] **Step 2: Run** — FAIL.  **Step 3: Implement.**  **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** `git commit -am "review_store: page context and chapter:verse index"` (add the new test file first).

### Task 4: Entry operations

**Files:**
- Modify: `scripts/review_store.py`
- Create: `scripts/tests/test_ops.py`

**Interfaces:**
- Produces pure functions on a page dict (return the new dict, never touch disk):
  - `add_verse(page, n: int) -> dict` — insertion and chapter rule exactly as `ReviewEditor._add_verse`
    / `_neighbour_chapter`.
  - `add_commentary(page, after: int | None, prev_page: dict | None) -> dict` — `after=None`: new block
    at index 0 with `chapter` and `verse_ref` of `prev_page`'s last commentary block (None if absent);
    `after=i`: inserted at `i+1` with block `i`'s `chapter` and `verse_ref`. New block:
    `{"commentary_id", "verse_ref", "chapter", "latin_quote": None, "french_translation": None, "french_commentary": ""}`;
    `commentary_id` renumbered 1..n.
  - `add_footnote(page, marker: str) -> dict` — appends `{"marker": "(x)", "text": ""}` from `"x"`, `"(x)"`, `" x "`.
  - `delete_entry(page, section, i) -> dict` — renumbers `commentary_id` when section is commentary.
  - `move_entry(page, section, i, j, renumber=True) -> dict` — moves entry i to position j.
  - `apply_op(page, op: dict, prev_page) -> dict` dispatching on `op["op"]` in
    `add_verse | add_commentary | add_footnote | delete | move`.

- [ ] **Step 1: Failing tests** — `test_add_verse_keeps_order_across_chapters` (page ending ch.17 v.30
  and starting ch.18 v.1; add 31 → index after 30, chapter 17), `test_add_commentary_top_inherits_prev`
  (on p.194 with p.193 as prev → index 0, chapter 17, verse_ref 1, ids 1..n),
  `test_add_commentary_below` (after=1 → index 2 with block 1's chapter/verse_ref),
  `test_add_commentary_top_no_prev` (None, None), `test_add_footnote_marker_forms`,
  `test_delete_renumbers`, `test_move_renumbers` and `test_move_keep_ids` (renumber=False).
- [ ] **Step 2: Run** — FAIL.  **Step 3: Implement.**  **Step 4: Run** — PASS.
- [ ] **Step 5: Commit** "review_store: entry operations".

### Task 5: Queue, progress, filters, counts

**Files:**
- Modify: `scripts/review_store.py`
- Create: `scripts/tests/test_queue.py`

**Interfaces:**
- Produces:
  - `KIND_LABELS`, `VERSE_KINDS`, `FOOTNOTE_KINDS`, `kind_category(kind)` — moved from
    `review_editor.py` (which then imports them from here).
  - `class Progress(path: Path, fp_path: Path)` — same file formats and false-positive sync as today's
    `review_editor.Progress`; `status(id)`, `set(id, status | None, info: dict | None)`; writes
    `false_positives.json` only when its content changes.
  - `load_queue(queue_path, fp_path, include_optional=False) -> list[dict]` — today's `load_queue`
    minus argv parsing (false positives no longer in the queue are added back).
  - `STATUSES = ("open", "false_positive", "skipped", "resolved", "all")`;
    `in_status(item, progress, status) -> bool` (open = none of resolved/false_positive/skipped).
  - `select(items, progress, status, cat=None, kind=None, book=None) -> list[dict]`.
  - `counts(items, progress, status, cat, kind, book) -> {"status": {s: n}, "cat": {c: n}, "kind": {k: n}, "book": {b: n}}`
    — each facet counted with the other three filters applied, as the Tk combo boxes do.
  - `page_issues(items, progress, vol, page) -> list[dict]` — every item on that page with `"status"` added.
  - `neighbour_issue_pages(items, progress, vol, page) -> {"prev": int | None, "next": int | None, "open_in_book": int}`.

- [ ] **Step 1: Failing tests** — `test_load_queue_optional` (3 vs 4 items), `test_fp_added_back`,
  `test_progress_fp_sync` (mark false_positive → in fp file; reopen → removed),
  `test_select_open_excludes_skipped`, `test_counts_facets`, `test_page_issues_status`,
  `test_neighbour_issue_pages`.
- [ ] **Step 2: Run** — FAIL.  **Step 3: Implement; switch `review_editor.py` to import the moved names.**
- [ ] **Step 4: Run** — PASS; `uv run --no-project --with pillow python -c "import review_editor"` — OK.
- [ ] **Step 5: Commit** "review_store: queue and progress".

### Task 6: HTTP server and API

**Files:**
- Create: `scripts/review_web.py`, `scripts/tests/test_web.py`

**Interfaces:**
- Consumes: everything in `review_store`, `page_text.toggle_italics`, `page_text.save_state/load_state`,
  `calmet.latin_case`.
- Produces `make_server(store, queue_path, port=0, token=None, include_optional=False) -> (ThreadingHTTPServer, token)`
  and these routes (JSON in/out; errors as `{"error": msg}` with 4xx):

| Route | Body / query | Returns |
|---|---|---|
| `GET /` , `/static/*` | `?key=` sets cookie | files from `review_web/` |
| `GET /scan/<vol>/<page>` | | PNG or 404 |
| `GET /api/config` | | `{token, labels: KIND_LABELS, categories, volumes, start: {status, cat, kind, book, vol, page}}` |
| `GET /api/page` | `vol, page` | `{data, version, scan: bool, context, issues, around: neighbour_issue_pages}`; 404 `{missing: true, scan: bool}` when no JSON |
| `POST /api/page` | `{vol, page, data, version, force?}` | `{data, version}`; 409 `{disk, version}` on `Conflict` |
| `POST /api/page/create` | `{vol, page}` | as GET |
| `POST /api/op` | `{vol, page, data, version, op}` | saves `data` first (as Tk does), applies `apply_op` with the previous page for `add_commentary`, saves, returns `{data, version}` |
| `GET /api/locate` | `vol, ref` (`"17:2"`, `"17"`) | `{page}` or 404 |
| `GET /api/queue` | `status, cat, kind, book` | `{items: [{id, book_dir, page, kind, msg, status}], counts}` |
| `POST /api/mark` | `{id, status \| null}` | `{ok: true}` (never touches the page) |
| `POST /api/italics` | `{text, start, end}` | `{text, start, end}` or `null` |
| `POST /api/latin_case` | `{text}` | `{text}` |
| `POST /api/flag` , `/api/open` | `{vol, page}` ; `{vol, page, what: "json" \| "png"}` | as `_flag_for_review`, `_open_in_editor`, `_open_png` |
| `GET/POST /api/state` | `{vol, page}` | resume state |

- CLI: `python3 review_web.py [--port N] [--no-open] [--all] [--kind K] [--category C] [--type T] [--book B] [--skipped | --resolved | --false-positive | --all-status] [--queue PATH] [--data DIR] [--docs DIR] [--list-fp] [VOLUME [PAGE]] [--resume]`
  — same meanings as the Tk editors; prints the URL with `?key=` and opens it unless `--no-open`.
  `--list-fp` prints as today and exits. `--data` / `--docs` point at a copy (for testing; the
  queue defaults to `<docs>/review_queue.json`, progress to `<data>/.review_queue_progress.json`).

- [ ] **Step 1: Failing tests** (server on port 0 in a thread over the `data_dir` fixture, `urllib`):
  `test_token_required` (403 without), `test_get_page` (context and two issues for p.194),
  `test_missing_page_then_create` (p.196 404 `missing`, scan True; create → 200),
  `test_save_and_conflict` (409 carries disk), `test_op_add_commentary_top` (via API, chapter/verse_ref
  from p.193), `test_locate`, `test_queue_counts`, `test_mark_does_not_save_page` (page file mtime
  unchanged), `test_italics`, `test_scan`, `test_path_traversal` (`/scan/../x/1` and
  `/static/../review_store.py` → 404).
- [ ] **Step 2: Run** `... pytest tests/test_web.py -q` — FAIL.
- [ ] **Step 3: Implement** with `http.server.ThreadingHTTPServer` and `BaseHTTPRequestHandler`;
  volumes validated against `store.volumes()`, static paths resolved inside `review_web/`.
- [ ] **Step 4: Run** all Python tests — PASS.
- [ ] **Step 5: Commit** "review_web: local server and API".

### Task 7: Shell, themes, scan pane, read-only page view

**Files:**
- Create: `scripts/review_web/index.html`, `style.css`, `app.js`, `text.js`, `scripts/tests/js/text.test.mjs`

**Interfaces:**
- Consumes: the API of Task 6.
- Produces in `text.js`: `italicRuns(s) -> {runs: [[a,b]], marks: [i], openAt: "start"|"end"|null}`,
  `toggleItalics(s, sa, sb) -> {text, start, end} | null` (port of the Python; the server endpoint stays
  as reference), `parseRef("17:2") -> {chapter: 17, verse: 2}`, `parseRef("17") -> {chapter: 17, verse: null}`,
  `parseRef("p194") / parseRef("194p") -> {page: 194}`, otherwise `null`.
- Produces in `app.js`: `state = {vol, page, data, version, dirty, items, idx, filters}`,
  `loadPage(vol, page)`, `api(path, body?)` (adds `X-Token`).

Layout (mockup `layout.html`, option A): top bar (book select, jump box, page ◀ ▶, issue ◀ ▶,
Resolved, Skip, False positive, theme switch, save state); grid `minmax(220px, 260px) 1fr 1.25fr`
with draggable divider between scan and text; left column issues; middle scan; right text with
context strips. Scan pane: zoom − / + / Fit / 1:1 using the Tk `ZOOM_STEPS`, Cmd+scroll zoom at the
pointer, drag to pan, dimmer slider 0–100 % (default 10, a black overlay at that opacity), "no scan"
message. Themes as CSS custom properties on `:root[data-theme=paper|light|dark]`; palette from the
mockups (`paper` bg `#faf7f0`, accents `#d98b1a`, lemma `#6b3d1f`; `dark` bg `#1f1c17`, text `#e8e1d2`).

- [ ] **Step 1: Failing JS tests** in `tests/js/text.test.mjs`: the same toggle/italic cases as
  `test_page_text.py`, and `parseRef` cases above.
- [ ] **Step 2: Run** `node --test tests/js` — FAIL.
- [ ] **Step 3: Implement** `text.js`, then the shell, themes, scan pane and a read-only rendering of
  every field (verses, commentary, footnotes, page heading fields, context strips).
- [ ] **Step 4: Verify** `node --test tests/js` PASS; start `python3 review_web.py 22_proverbes 194`
  and check in the browser (claude-in-chrome or the built-in browser): p.194 shows its scan, the
  "p.193 ends: ch.17 v.1" strip and the next-page strip; each theme renders; zoom/pan/dimmer work;
  no console errors.
- [ ] **Step 5: Commit** "review_web: shell, themes, scan pane".

### Task 8: Editable fields, saving, conflicts

**Files:**
- Create: `scripts/review_web/field.js`
- Modify: `scripts/review_web/app.js`, `style.css`

**Interfaces:**
- Produces `class Field(el, {name, value, italicField: bool, onChange})` with `.value` (string | null),
  `.focus(selectAll)`, `.setShowMarks(bool)`; rendering from `italicRuns` (italic spans, `_` marks
  dimmed or hidden), small caps for `latin_quote` (from `/api/latin_case`, debounced 300 ms, Tk's
  `_render_smallcaps` rule), Hebrew runs in `<span dir="rtl">`; null shown as grey `null`.

Behaviour to reproduce from `page_editor.py`: `contenteditable` with the caret kept by character
offset across re-render; own undo/redo per field (⌘Z / ⇧⌘Z, coalescing typing, Cmd+I one step);
paste as plain text only; Cmd+I toggles italics on the selection (`toggleItalics`); Tab / Shift-Tab to
next / previous field with its text selected; right-click menu Cut / Copy / Paste / Italics; empty
`french_commentary` gets room for four lines; ← / → change page only when no field has focus;
⌘S saves; section filter (All / Verses / Commentary / Footnotes); "Show _ marks" switch.
Saving sends every field's `.value` as typed (server applies `form_values`). On 409 a dialog: "This page
was changed on disk since you opened it" with "Reload theirs" and "Keep mine"; nothing is written until
one is chosen. Dirty state in the top bar; `beforeunload` warns while dirty; leaving the page while
dirty saves first and stays put if the save fails.

- [ ] **Step 1: Write a manual check list** at the top of `field.js` as a comment (the behaviours above),
  used as the acceptance test for this task.
- [ ] **Step 2: Implement.**
- [ ] **Step 3: Verify** in the browser on a copy of the data (`cp -R ../data/22_proverbes` into a temp
  data dir and start with `--data <tmp> --docs <tmp docs copy>`): type, undo,
  italicize, paste formatted text, Tab through fields, save, check the file diff with `git diff --no-index`;
  touch the file from the shell then save → conflict dialog; Hebrew page (find one with `grep -l "[א-ת]"`)
  keeps its text after save with no U+200E in the file.
- [ ] **Step 4: Run** all Python and JS tests — PASS.
- [ ] **Step 5: Commit** "review_web: editable fields and saving".

### Task 9: Queue column and navigation

**Files:**
- Modify: `scripts/review_web/app.js`, `style.css`

Behaviour: the left column lists `issues` of the page (kind label, msg, status; current outlined;
resolved/false positive struck through; clicking one makes it current); under them "◀ page N with
issues", "page M with issues ▶", "K open in this book". Filters (status, category, type, book) with
counts from `/api/queue` as in the Tk combo boxes; changing a filter goes to the first item; an empty
result shows "No issues matching these filters" and keeps the old list. Issue ◀ ▶ (⌘[ / ⌘]) step
through the filtered list, in the open view passing over items whose status changed this session.
Resolved (⌘⏎), False positive (⌘P), Skip, Reopen on the current item: save first if dirty (stop if the
save fails), mark, refresh counts, go to the next. Item on a missing page → "Create page" prompt
(mentions when there is no scan). Jump box: `parseRef` → `/api/locate` (or page number) → load; not
found → inline message. Book select + page number jump; position saved to `/api/state` on each
load; `--resume` and `VOLUME PAGE` start options honoured. "(you have navigated away from this issue's
page)" note as in Tk.

- [ ] **Step 1: Verify (manual check list in the commit message)** with the real queue on a temp data copy:
  filters and counts match the Tk editor's for the same filters (open both on the same copy);
  Resolved writes `.review_queue_progress.json`; False positive updates `docs/false_positives.json`;
  ⌘⏎ with unsaved edits saves then moves; jump `17:2` in Proverbes lands on p.194.
- [ ] **Step 2: Commit** "review_web: queue column and navigation".

### Task 10: Adding, deleting, reordering; page tools

**Files:**
- Modify: `scripts/review_web/app.js`, `style.css`

Behaviour: "+ add block at top (continues ch:v)" above the first commentary block (label from the
previous page's last block); "+ add below" under every block; "+ Verse" (asks the number), "+ Footnote"
(asks the letter), page heading fields (`chapter_title` and the others) shown and editable; ✕ on each
verse, block and footnote with a confirmation naming the entry (as `_delete_one`); Reorder: drag
handle on each verse/block plus ↑ ↓ ⤒ ⤓ buttons, "Renumber commentary_id" checked by default; all
via `POST /api/op` (which saves typed edits first). Page tools menu: Flag for review, Open JSON, Reveal
PNG.

- [ ] **Step 1: Verify** on a temp data copy: add at top on p.194 → block 1 has chapter 17, verse_ref 1;
  add below block 2 → new block 3 with block 2's refs; delete and reorder renumber ids; Flag copies to
  `modernization_error/`.
- [ ] **Step 2: Run** all tests — PASS.
- [ ] **Step 3: Commit** "review_web: add, delete, reorder, page tools".

### Task 11: README and hand-over

**Files:**
- Modify: `scripts/README.md` ("Work through the queue" line)

- [ ] **Step 1:** Replace the editor line with: start `python3 review_web.py [filters]` (opens the
  browser; same filters as before; `--resume`); the Tk editors remain available during the switch.
- [ ] **Step 2:** Run all tests; start the server on the real data with `--no-open`, load one page, stop it.
- [ ] **Step 3: Commit** "README: the web review editor".
