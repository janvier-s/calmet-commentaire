# Review Web Editor, Part 2 (point at the problem, re-check on save) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Opening an issue scrolls to its field and highlights the flagged words; saving a page re-runs
the audit's checks so fixed issues close themselves and new ones appear.

**Architecture:** The audit records where each per-note item sits (`where`: section, index, field) in
`audit_integrity.py`'s `item()`; the editor finds the words the message quotes inside that field
(pure matching in `text.js`) and draws them with `<mark>`. Re-check reuses `audit_integrity.audit_book`
unchanged for the saved page's book (0.7–3.5 s), with calmet's page caches cleared first, and merges
the result into the server's in-memory queue (`review_store.merge_recheck`).

**Tech Stack:** as Part 1 (Python 3.15 stdlib server, pytest via uv, plain ES modules, `node --test`,
headless Chrome via Playwright for browser checks — the user's browser is Helium, Chromium-based).

**Spec:** `scripts/docs/superpowers/specs/2026-10-24-review-web-editor-design.md` (features 1 and 4);
Part 1 plan: `scripts/docs/superpowers/plans/2026-10-24-review-web-editor-port.md`.

## Global Constraints

- Part 1's constraints hold (local only, token, data format unchanged, save = `trim(clean_page(...))`,
  every word stays on its page, never overwrite a page changed on disk unasked).
- Queue item ids must not change: `where` is an extra optional key; the id still hashes `msg` only.
  `docs/review_queue.json` stays readable by the Tk editor.
- The full audit's output (`python3 audit_integrity.py …`) is unchanged apart from the added `where` keys.
- Re-check never writes `docs/review_queue.json`; it changes the server's in-memory queue and the
  progress file only (fixed items → status `resolved`, as the spec's "Claude's calls" say).
- Kinds produced outside `audit_book` are never touched by a re-check: `reported`, `psalm_*`,
  `chapter_vulgate`, `chapter_heading`, `hebrew_recheck`, `latin_long_s`, `seam_missing`,
  `seam_repeat`, `seam_unclear`. For volumes listed in `docs/seam_check.json`, `possible_gap` and
  `seam_artifact` are dropped from the re-check result, as `audit_integrity.main` does.

## Review Focus

1. A re-check while another is running (two quick saves) → serialized by a lock; the second sees the
   later file. Test: Task 3 `test_recheck_serialized`.
2. A save in another book while a re-check of this book runs → only this book's items change.
   Test: Task 3 `test_merge_only_this_book`.
3. An item the user marked false positive or skipped, still produced by the audit → keeps its status;
   one no longer produced → stays as marked (only open items become "fixed on save"). Test: Task 3
   `test_merge_keeps_marked`.
4. A quoted snippet the audit cut mid-word ("…ur sage dominera") or with an ellipsis, or a field whose
   text has since changed → partial matches still highlight; no match → the field (or block) is
   flashed instead, never an error. Test: Task 2 `findSpans` cases.
5. calmet's `lru_cache` on `pages`/`apparatus` → cleared before every re-check, or the re-check reports
   the page as it was. Test: Task 3 `test_recheck_sees_fresh_page`.

---

## File Structure

| File | Responsibility |
|---|---|
| `scripts/audit_integrity.py` (modify) | `item(..., where=None)`; pass `where` in the per-note and per-verse checks. |
| `scripts/page_audit.py` (create) | `recheck_book(vol) -> list[item]`: the audit of one book, caches cleared, seam_check filter. |
| `scripts/review_store.py` (modify) | `AUDIT_KINDS`, `merge_recheck(...)`. |
| `scripts/review_web.py` (modify) | `POST /api/recheck`; `make_server(..., recheck=page_audit.recheck_book)`. |
| `scripts/review_web/text.js` (modify) | `snippets(msg, kind)`, `findSpans(text, needles)`. |
| `scripts/review_web/field.js` (modify) | `render(el, s, smallcaps, marks)`; `Field.setMarks(spans)`. |
| `scripts/review_web/point.js` (create) | Pointing at the current issue: find, mark, scroll, flash. |
| `scripts/review_web/edit.js`, `queue.js` (modify) | Call re-check after save/op; refresh issues; "fixed on save". |
| `scripts/tests/test_audit_where.py`, `test_recheck.py`, `tests/js/text.test.mjs` | Tests. |

---

### Task 1: `where` on the audit's items

**Files:**
- Modify: `scripts/audit_integrity.py:250-258` (`item`), the per-note loop (`for j, c in enumerate(cs)`),
  the `chapter_field`, `vulgate_filled`/`missing_french` and `guessed_ref`/`chapter_ref`/`footnote_asterisk` checks
- Create: `scripts/tests/test_audit_where.py`

**Interfaces:**
- Produces: queue items may carry `where = {"section": "commentary"|"verses"|"footnotes", "index": int, "field": str | None}`.
  In the per-note loop: `section="commentary", index=j`, `field=k` where the check names a field
  (`spaced_letters`, `leading_call`, `hyphen_cut`, `broken_marker`: their `k`; `caps_in_commentary`,
  `leading_punctuation`, `italic_seam`, `period_seam`, `empty_commentary`: `french_commentary`;
  `lowercase_lemma`, `lemma_no_punct`, `lemma_unknown_word`, `no_verse_ref`: `latin_quote`
  (`no_verse_ref`: `verse_ref`); `long_translation`, `hebrew_in_translation`, `translation_no_punct`,
  `lowercase_translation`: `french_translation`; `no_lemma`: `latin_quote`; `lemma_verse`,
  `verse_mismatch`: `verse_ref` (index = that block's index)); `etc_for_et`: last block,
  `french_commentary`; `chapter_ref`: that block, `french_commentary`; `chapter_field`: that entry,
  field `chapter`; `vulgate_filled`/`missing_french`: that verse, `french`.

- [ ] **Step 1: Failing test** `test_where_points_at_quoted_text` — read-only on the real data
  (skip if `../data/22_proverbes` is absent): `r = audit_book("proverbs", ...)`; for every item with
  `where` and a quoted snippet `“…”` in `msg` (first one, with leading/trailing `…` stripped and cut
  to its longest run of 12+ characters), the snippet occurs in that page's
  `data[section][index][field]`; at least 90 % of such items pass (the audit quotes some text
  re-flowed); and items of kinds `lowercase_lemma`, `long_translation`, `caps_in_commentary`,
  `hyphen_cut`, `period_seam` all have `where`. Also `test_ids_unchanged`: the set of ids equals
  the set computed with `where` stripped (ids hash msg only).
- [ ] **Step 2: Run** `uv run --no-project --with pytest python -m pytest tests/test_audit_where.py -q` — FAIL (no `where`).
- [ ] **Step 3: Implement** `item(kind, vol, page, msg, optional=False, where=None)` (adds `where`
  only when given) and pass it at the calls above.
- [ ] **Step 4: Run** — PASS; rebuild the queue `python3 audit_integrity.py ../docs/integrity_audit_2026-10-24.json`
  and check the item count is unchanged (8,098 or today's count before the change; run it once before).
- [ ] **Step 5: Commit** `audit_integrity.py`, the test (and `docs/` is not in this repo: the rebuilt queue is not committed).

### Task 2: Finding the quoted words (pure JS)

**Files:**
- Modify: `scripts/review_web/text.js`, `scripts/tests/js/text.test.mjs`

**Interfaces:**
- Produces `snippets(msg: string, kind: string) -> string[]`: every `“…”` quotation in `msg`, with
  `…` and the punctuation/space around it stripped, split at `…` into pieces of 6+ characters; plus
  for `missing_footnote`/`broken_marker` the call text (`^{(x)}` from "marker (x)", or the quoted call).
- Produces `findSpans(text: string, needles: string[]) -> [a, b][]`: each needle found in `text`
  (exact first; else whitespace-insensitive; else its longest 12+ character piece), merged and sorted.

- [ ] **Step 1: Failing tests**:
  `snippets("Capitals inside the comment: “…entre les FRÈRES insensés…”: a lemma…", "caps_in_commentary")` → `["entre les FRÈRES insensés"]`;
  `snippets("Full stop at the foot of the page (“…aujourd'hui.”) but the next page goes on in lower case (“d'hui dans le Grec…”)", "period_seam")` → `["aujourd'hui.", "d'hui dans le Grec"]`;
  `snippets("Footnote marker (b) has no footnote text on this page", "missing_footnote")` → `["^{(b)}"]`;
  `findSpans("le serviteur  sage dominera", ["serviteur sage"])` → `[[3, 19]]`;
  `findSpans("abc", ["zzz"])` → `[]`; overlapping needles merge.
- [ ] **Step 2: Run** `node --test tests/js` — FAIL.  **Step 3: Implement.**  **Step 4: Run** — PASS.
- [ ] **Step 5: Commit.**

### Task 3: Re-check on the server

**Files:**
- Create: `scripts/page_audit.py`, `scripts/tests/test_recheck.py`
- Modify: `scripts/review_store.py`, `scripts/review_web.py`

**Interfaces:**
- `page_audit.recheck_book(vol: str) -> list[dict]` — book key from `paths.BY_VOLUME[vol]`;
  `calmet.pages.cache_clear()`, `calmet.apparatus.cache_clear()`; `audit_integrity.audit_book(key, info, slug)["queue"]`;
  drop `possible_gap`/`seam_artifact` for volumes in `docs/seam_check.json`.
- `review_store.AUDIT_KINDS: frozenset` — the kinds `audit_book` emits (Global Constraints list excluded).
- `review_store.merge_recheck(items, progress, vols, new_items) -> {"fixed": [ids], "added": [ids]}` —
  mutates `items` in place: among items with `book_dir in vols` and `kind in AUDIT_KINDS`, those not in
  `new_items` and open → `progress.set(id, "resolved")`, kept in `items` with `"fixed": True`; those
  not in `new_items` and marked → left as they are; `new_items` not yet in `items` → appended
  (`where` and `msg` of existing ones refreshed).
- `make_server(..., recheck=None)`; `POST /api/recheck {vol, page}` → runs `recheck(vol)` under a
  `threading.Lock`, merges, returns `{"fixed": n, "added": n, "issues": page_issues(...), "around": ...}`.
  `issues` items carry `"fixed": true` when fixed on save.

- [ ] **Step 1: Failing tests**: `test_merge_fixed_and_added`, `test_merge_keeps_marked`,
  `test_merge_only_this_book` (pure, with the fixture queue); `test_recheck_endpoint` (server with a
  fake `recheck` returning the queue minus one item → that item `fixed`, status resolved in the
  progress file); `test_recheck_serialized` (fake recheck that sleeps 0.2 s and records overlap; two
  concurrent calls never overlap); `test_recheck_sees_fresh_page` (real `recheck_book` on a tmp copy of
  `22_proverbes` with `paths.DATA` and `audit_integrity.STUDIUM` monkeypatched: run once, lower-case a
  word in a page's `latin_quote`, run again → a new `lowercase_lemma` item for that page; skip if the
  real data is absent).
- [ ] **Step 2: Run** — FAIL.  **Step 3: Implement.**  **Step 4: Run** all tests — PASS.
- [ ] **Step 5: Commit.**

### Task 4: Pointing in the editor

**Files:**
- Create: `scripts/review_web/point.js`
- Modify: `field.js` (`render(el, s, smallcaps, marks)`, `Field.setMarks(spans)` redraws keeping the
  caret; marks cleared on the field's first edit), `main.js` (import), `queue.js` (call `point(item)`
  after an issue is opened or clicked), `style.css` (`.block.flash` animation)

**Interfaces:**
- `point(item)`: fields of `item.where` (else all fields of the page) → `findSpans(field.text, snippets(item.msg, item.kind))`;
  marks on every field with spans; scrolls the first marked field (else the `where` block, else
  nothing) to the upper third of the text pane and flashes its block for 1.2 s; the section filter
  switches to All if the target is hidden.

- [ ] **Step 1: Browser check** (Playwright, headless Chrome, Proverbes copy) written first in the
  scratchpad: open a `caps_in_commentary` item → a `<mark>` inside `french_commentary` of the `where`
  block containing the quoted capitals, and that block in view; open a `missing_footnote` item → the
  `^{(b)}` call marked; open an item whose quote no longer matches → no error, block flashed.
  Run it — FAIL.
- [ ] **Step 2: Implement.**  **Step 3: Run the check** — PASS; Part 1's edit check still passes.
- [ ] **Step 4: Commit.**

### Task 5: Re-check after saving, in the editor

**Files:**
- Modify: `scripts/review_web/edit.js` (after a successful `save()` or `op()`, `recheck()`),
  `queue.js` (`recheck()` updates `S.issues`, `S.around`, `Q.items` statuses and counts; cards with
  `fixed` show "fixed on save", struck through), `style.css`

**Interfaces:**
- `recheck()`: shows "re-checking…" next to the save state; `POST /api/recheck`; on reply a toast
  "N fixed on save, M new" (only when non-zero) and the left column redrawn; a reply for a page no
  longer shown updates counts only. Never blocks typing; a failed re-check shows a toast and changes nothing.

- [ ] **Step 1: Browser check** written first: on a Proverbes copy, open a `lowercase_lemma` item, fix
  the lemma to capitals, ⌘S → within 5 s the card shows "fixed on save" and the progress file has it
  resolved; lower-case another lemma, ⌘S → a new card appears. Run it — FAIL.
- [ ] **Step 2: Implement.**  **Step 3: Run** — PASS; all Python and JS tests pass.
- [ ] **Step 4: Commit**; README line on re-check.
