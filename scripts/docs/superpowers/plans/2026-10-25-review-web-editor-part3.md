# Review editor, Part 3: page-turn view, proposals, batch table — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add to `review_web.py` the page-turn view (foot of page A over head of page B, both editable),
proposed fixes with Accept / Edit / Reject, and a batch table for one kind of issue.

**Architecture:** Two new pure-Python modules beside `review_store.py`: `review_turns.py` (which turn
an issue belongs to, the two pages' boundary blocks, the joined-text preview, the seam proposal computed
live by `seam_join.plan`) and `review_proposals.py` (the proposal model, items generated from the
footnote and ref_check reports, applying a proposal with an old-value check). `review_web.py` gains
routes over them. The front end gains `turn.js` (the view), `proposal.js` (diff card with the three
buttons) and `batch.js` (the table); `text.js` gains a word diff.

**Tech Stack:** Python 3 standard library (ThreadingHTTPServer), plain ES modules, no build step;
pytest via `uv run --no-project --with pytest`, `node --test`, Playwright headless Chrome for checks.

**Spec:** `scripts/docs/superpowers/specs/2026-10-24-review-web-editor-design.md` (sections "Page-turn
view", "Batch review", New features 2, 3, 6, "Claude's calls").

## Global Constraints

- Server: standard library only; binds 127.0.0.1; every route behind the session key (as now).
- Front end: plain HTML/CSS/JS ES modules, no build step, no new libraries.
- Three themes (paper, light, dark), sans-serif; colours from the existing `--c-*` tokens.
- A page changed on disk since it was loaded is never overwritten unasked (version check, 409).
- Accept saves the page(s) and marks the item resolved; Edit puts the proposal in the fields unsaved;
  Reject leaves the text as it is.
- ◀ turn / turn ▶ go to the previous/next page turn with an open issue.
- Icons, not words, on small buttons (user's request); type labels not all caps.
- Test commands: `uv run --no-project --with pytest python -m pytest tests -q` and `node --test tests/js`.

## Calls made in this plan (check these)

1. **Proposal sources.** Seam proposals are computed live from the current pages by
   `seam_join.plan` / `plan_repeat` (the report `docs/seam_join.json` goes stale as soon as a page is
   edited). Footnote write-outs come from `docs/footnotes/<vol>.json` (notes whose `proposed` differs
   from `text`, shown only while the page's footnote still reads `text` exactly). ref_check candidates
   from `docs/ref_check.json` (30 items, one option per candidate). **Vulgate readings are left for
   Part 4**: `vulgate_check.json` has no fixes (`fix` is null throughout), and Part 4 puts the Vulgate
   beside the Latin.
2. **Footnote write-outs and verse-reference candidates become queue items** of two new kinds,
   `footnote_writeout` ("Footnote write-out to check", category footnotes) and `ref_candidate`
   ("Verse reference to check", category commentary), added to the queue when the server starts, after
   the audit's items. They are never closed by a re-check. About 2,400 footnote items: filter them out
   by kind, or work them in the batch table.
3. **Reject** on a generated item (footnote_writeout, ref_candidate) marks it false positive. Reject on
   a seam proposal hides that proposal (recorded as `proposal:<id>` → `rejected` in the progress file)
   and leaves the issue open for a fix by hand.
4. **The page-turn view opens by itself** when the current issue is a page-turn kind, and with the
   key `T` from any page (the turn below the page). Esc or "Page" goes back to the page.
5. **Scans in the page-turn view**: the foot of A's scan and the head of B's beside each half, behind
   a "Scans" switch remembered in the browser (on by default). You said you check the JSON rather than
   the scan, so turn it off if it is in the way.
6. **What the turn view shows**: A's last verse (read-only, for the chapter and verse number) and last
   commentary block, editable; B's first commentary block and first verse, editable; and the joined
   text as `calmet.py` sews it (`infer_join` + `join_seam`), recomputed after each save.

## Review Focus

1. A proposal whose page changed since it was computed (typed in the main view, a script ran): Accept
   must refuse (409), not write over the new text. — test in Task 2 (`test_apply_refuses_changed_text`).
2. A turn whose second page has no commentary, or no JSON at all, or the last page of a book: the view
   shows what exists and no proposal, never a 500. — test in Task 1 (`test_turn_without_commentary`).
3. The new kinds must never be "fixed" by a re-check (they are not audit kinds). — test in Task 2
   (`test_generated_kinds_not_audit_kinds`).
4. Leaving the main page with unsaved edits for the turn view (and back) must ask, as page changes do;
   saving in the turn view must refresh the main page if it is one of the two. — Playwright check in
   Task 4.
5. Batch accept over many items where one fails (changed on disk): the others are applied, the failed
   one is reported and stays open. — test in Task 3 (`test_batch_accept_partial`).

---

### Task 1: `review_turns.py` — the turn, its blocks, the join preview, the seam proposal

**Files:**
- Create: `scripts/review_turns.py`
- Test: `scripts/tests/test_turns.py`

**Interfaces:**
- Consumes: `review_store.Store` (`pages`, `read`, `path`, `locate`, `scan`), `seam_join.plan`,
  `seam_join.plan_repeat`, `calmet.infer_join`, `calmet.join_seam`.
- Produces:
  - `FOOT_KINDS = {"hyphen_cut", "italic_seam", "period_seam"}` (item on page A, the page before the turn)
  - `HEAD_KINDS = {"possible_gap", "seam_artifact", "seam_missing", "seam_repeat", "seam_unclear"}` (item on page B)
  - `turn_of(store, item) -> (vol, a, b) | None`: A and B are consecutive pages with JSON in
    `store.pages(vol)`. FOOT kinds: a = item page, b = the next; None for a `hyphen_cut` whose
    `where.index` is not A's last commentary block. HEAD kinds: b = item page; a = the `before_page`
    in a seam_check id (`…/seam_missing/0130`) when present, else the previous page.
  - `turn(store, vol, a, b) -> dict`:
    `{"vol", "a": side, "b": side, "join": {"tail", "head", "joined", "mode"} | None, "proposal": dict | None}`
    where `side = {"page", "data", "version", "scan": bool, "verse": index|None, "note": index|None}`
    (`verse`/`note`: index of A's last / B's first verse and commentary block; `data`/`version` from
    `store.read`; a missing page gives `side = None`).
  - `join_preview(la, fb) -> dict | None`: tail = A's last block's last non-empty of
    `french_commentary`, `french_translation`, `latin_quote`; head = B's first block's first non-empty of
    `latin_quote`, `french_translation`, `french_commentary`; `mode, stub = infer_join(tail, head)`;
    `joined = join_seam(tail[-200:], head[:200], mode, stub)`.
  - `seam_proposal(store, vol, a, b) -> dict | None`: `seam_join.plan(...) or plan_repeat(...)` turned
    into the proposal shape of Task 2 (only when the fix has a `set`); `id = "seam/{vol}/{a:04d}>{b:04d}/" +
    md5(json(set))[:8]`; `"a.f"` keys → page a `["commentary", last, f]`, `"b.f"` → page b
    `["commentary", 0, f]`; `title` = the fix's `how`, `sure` kept. `verse_fr` is the French of A's last
    block's verse, found with `store.locate(vol, chapter, verse_ref)`.

- [ ] **Step 1: Write the failing tests** in `tests/test_turns.py`, using the `data_dir` fixture (pages
  193–195) and editing pages in the test where a case needs it:
  - `test_turn_of_foot_and_head`: hyphen_cut on 194 with `where.index` 1 → `("22_proverbes", 194, 195)`;
    with `where.index` 0 → None; seam_artifact on 195 → `(…, 194, 195)`; `seam_missing` id
    `22_proverbes/0195/seam_missing/0193` → `(…, 193, 195)`; `missing_footnote` → None.
  - `test_turn_payload`: `turn(store, VOL, 193, 194)` → `a.note == 0`, `b.note == 0`, `a.verse == 0`,
    `b.verse is None`, `join.tail` ends "victimes.", `join.head == "suite du commentaire."`,
    `join.mode == "mend"` (full stop then lower case).
  - `test_turn_without_commentary`: `turn(store, VOL, 194, 195)` (195 has no commentary) →
    `b.note is None`, `join is None`, `proposal is None`; `turn(store, VOL, 195, 196)` (196 has no JSON)
    → `b is None`, no exception.
  - `test_seam_proposal_repeat`: set 193's last `french_commentary` to "…le nom de toute sa posterité."
    and 194's first to "terité. Adam signifie roux." → proposal with `changes` == [{page 193, path
    `["commentary",0,"french_commentary"]`, old, new "…posterité."}, {page 194, …, new "Adam signifie
    roux."}] and an id starting `seam/22_proverbes/0193>0194/`.

- [ ] **Step 2: Run them to see them fail**
  Run: `uv run --no-project --with pytest python -m pytest tests/test_turns.py -q`
  Expected: FAIL, `ModuleNotFoundError: review_turns`.

- [ ] **Step 3: Implement `review_turns.py`** with the interfaces above. `seam_join.plan` takes page
  paths for `a`/`b` (it reads `.stem`): pass `store.path(vol, a)`.

- [ ] **Step 4: Run them to see them pass**, then the whole suite.
  Expected: test_turns all pass; suite 80 + new, all pass.

- [ ] **Step 5: Commit** `review_turns: the page turn of an issue, its blocks, join and seam proposal`

### Task 2: `review_proposals.py` — the proposal model, generated items, applying

**Files:**
- Create: `scripts/review_proposals.py`
- Modify: `scripts/review_store.py` (KIND_LABELS, kind_category, AUDIT_KINDS exclusion)
- Test: `scripts/tests/test_proposals.py`

**Interfaces:**
- Consumes: `Store.read/save/pages`, `review_turns.turn_of`, `review_turns.seam_proposal`, `Conflict`.
- Produces:
  - Proposal shape: `{"id", "item": item_id|None, "title", "why": [str], "flags": [str], "sure": bool,
    "options": [{"label", "changes": [{"vol", "page", "path": [section, index, field], "old", "new"}]}]}`.
  - `generated_items(store) -> list[item]`: one `footnote_writeout` item per note in
    `docs/footnotes/<vol>.json` with `proposed != text` whose page's footnote with that marker still
    reads `text` (id `{vol}/{page:04d}/footnote_writeout/{md5(marker+text)[:8]}`, msg
    `"{marker} {text[:80]} → {proposed[:80]}"`, `proposal` stored on the item); one `ref_candidate`
    item per `docs/ref_check.json` item with candidates whose field (parsed from
    `"commentary[0].french_commentary"`) still contains `written` once (one option per candidate:
    `written` → candidate[0]).
  - `proposal_for(store, progress, item) -> dict | None`: the item's stored proposal, else for a
    turn kind `seam_proposal` of `turn_of(item)`; None when `progress.status("proposal:" + id)` is
    `"rejected"`.
  - `apply(store, proposal, option=0, edited=None) -> {"pages": {page: {"data", "version"}}}`: groups
    changes by page, reads each page, refuses with `Conflict` if any field's current value != `old`,
    writes `new` (or `edited[i]` for change i when given), saves each page with its version.
  - In `review_store`: `KIND_LABELS["footnote_writeout"] = "FOOTNOTE WRITE-OUT TO CHECK"`,
    `KIND_LABELS["ref_candidate"] = "VERSE REFERENCE TO CHECK"`; `kind_category` puts them in
    footnotes / commentary; both added to the set `AUDIT_KINDS` excludes.

- [ ] **Step 1: Write the failing tests** in `tests/test_proposals.py` (a `docs/footnotes/22_proverbes.json`
  with a note for 194 `(a)` "Prov. 17. 2." → "Proverbes 17:2." flagged `uncertain`, and one whose text
  no longer matches; a `docs/ref_check.json` with one item on 194):
  - `test_footnote_items`: one item, kind footnote_writeout, page 194, proposal change path
    `["footnotes", 0, "text"]` old "Prov. 17. 2." new "Proverbes 17:2.", flags `["uncertain"]`; the
    stale note gives no item.
  - `test_ref_candidate_items`: two candidates → two options.
  - `test_apply_writes_and_versions`: apply the footnote proposal → page 194's note reads
    "Proverbes 17:2."; returned version equals `store.read(...)[1]`.
  - `test_apply_refuses_changed_text`: change the note on disk first → `Conflict`, file unchanged.
  - `test_apply_edited`: `edited=["Proverbes 17:2 et suiv."]` writes that.
  - `test_rejected_seam_proposal_hidden`: progress `proposal:<id>` = rejected → `proposal_for` None.
  - `test_generated_kinds_not_audit_kinds`: neither kind in `AUDIT_KINDS`; `merge_recheck` with an
    empty audit leaves a footnote_writeout item open.

- [ ] **Step 2: Run them to see them fail.** Expected: `ModuleNotFoundError: review_proposals`.
- [ ] **Step 3: Implement** the interfaces above.
- [ ] **Step 4: Run them, then the suite.** Expected: all pass.
- [ ] **Step 5: Commit** `review_proposals: proposals from the footnote and ref_check reports and the seam join`

### Task 3: server routes

**Files:**
- Modify: `scripts/review_web.py`
- Test: `scripts/tests/test_web_turns.py`

**Interfaces:**
- Consumes: Tasks 1 and 2.
- Produces (all JSON, key-protected):
  - `make_server` appends `generated_items(store)` to the queue (after `load_queue`).
  - `GET /api/turn?vol=V&a=A` (B = the next page with JSON) or `?id=ITEM` → `turn(...)` plus
    `"issues"` (open and closed items of both pages that are turn kinds at this turn) and
    `"around": {"prev": a|None, "next": a|None}` (the previous/next turn, by A, with an open turn issue
    in the book).
  - `GET /api/proposal?id=ITEM` → `{"proposal": dict|None}`.
  - `POST /api/proposal/accept {id, proposal_id, option, edited?}` → applies (409 on Conflict, with the
    page), marks the item resolved (under the lock), returns the new pages' `{data, version}`.
  - `POST /api/proposal/reject {id, proposal_id}` → generated item: false positive; else
    `proposal:<id>` rejected.
  - `GET /api/batch?kind=K&book=B&status=open` → `{"rows": [{id, page, msg, context, proposal}]}`;
    `context` = `{"tail", "head"}` from `join_preview` for turn kinds, else the item's `where` field text.
  - `POST /api/batch/accept {ids}` → applies option 0 for each in turn; `{"done": [ids], "failed":
    [{id, error}]}`; a failure never stops the others.
  - `/api/config` gains `"turn_kinds"` (FOOT ∪ HEAD).

- [ ] **Step 1: Write the failing tests** (server on port 0 as in `test_recheck.py`):
  `test_turn_route`, `test_turn_route_by_item`, `test_proposal_accept_marks_resolved`,
  `test_proposal_accept_conflict_409`, `test_reject_generated_is_false_positive`,
  `test_reject_seam_hides_proposal`, `test_batch_rows`, `test_batch_accept_partial` (two footnote
  items, one changed on disk first: one done, one failed with its id, the failed one still open).
- [ ] **Step 2: Run them to see them fail** (404 "no such route").
- [ ] **Step 3: Implement** the routes; accept and batch accept take the existing `lock`.
- [ ] **Step 4: Run them, then the suite.** Expected: all pass.
- [ ] **Step 5: Commit** `review_web: routes for the page turn, proposals and the batch table`

### Task 4: the page-turn view (front end)

**Files:**
- Create: `scripts/review_web/turn.js`
- Modify: `scripts/review_web/index.html` (a `#turn` pane beside `#cols`, a "Turn" button), `style.css`,
  `main.js` (import), `queue.js` (open the view for turn kinds), `edit.js` (export what the view reuses:
  `INT_FIELDS`, the Tab handling)
- Check: `pw/turn_check.py` in the scratchpad (Playwright, headless Chrome)

**Interfaces:**
- Consumes: `GET /api/turn`, `POST /api/page`, `Field` from `field.js`, `ask`, `toast`, `api`, `S`, `nav`.
- Produces: `openTurn({vol, a} | {id})`, `closeTurn()`, `T.open` (bool) for the queue module.

Layout (spec "Page-turn view", stacked): a header line "p.A → p.B" with ◀ turn / turn ▶, Save, Page
(back), Scans switch; then A's last verse (read-only line: ch:v and the French's first words), A's last
commentary block (fields as on the page, editable), a "page turn" rule, B's first commentary block and
first verse, editable; under them the joined text with the join point marked (`.join-mark`); the issue
cards of this turn; and the proposal card (Task 5) when there is one. Each side keeps its own
`{data, version, fields, dirty}`; Save writes each dirty side (409 → the same Reload theirs / Keep mine
choice as the page), then reloads the turn and runs the re-check (`hooks.afterSave` path). Opening the
view from a page with unsaved edits asks as leaving a page does; closing it reloads the main page when
it is A or B.

- [ ] **Step 1:** Write `pw/turn_check.py`: open a copy of the test data at an `italic_seam` issue →
  the turn pane is visible with both blocks; type into B's field, Save → the file on disk changed and
  the join line updated; ◀ turn / turn ▶ move; Esc returns to the page; `T` on a page opens its turn;
  leaving with unsaved edits asks. Run it: fails (no `#turn`).
- [ ] **Step 2:** Implement `turn.js`, the HTML and CSS (all three themes).
- [ ] **Step 3:** Run the check and the suites. Expected: check passes; pytest and node green.
- [ ] **Step 4: Commit** `review_web: the page-turn view`

### Task 5: proposals — diff card with Accept / Edit / Reject (front end)

**Files:**
- Create: `scripts/review_web/proposal.js`
- Modify: `scripts/review_web/text.js` (`wordDiff`), `queue.js` (card under the current issue),
  `turn.js` (card in the view), `style.css`
- Test: `scripts/tests/js/text.test.mjs`; check `pw/proposal_check.py`

**Interfaces:**
- Consumes: `GET /api/proposal`, `POST /api/proposal/accept|reject`, `Field.edit`.
- Produces: `wordDiff(a, b) -> [[op, text]]` with op in `"="`, `"-"`, `"+"` (LCS over words and the
  spaces between them; joining the `=` and `-` parts gives a, the `=` and `+` parts gives b);
  `proposalCard(item, proposal, {onEdit}) -> Element`.

The card: title (`how` / why), flags as small pills, "sure" pill, per option a diff (red struck
removed, green added) and three icon buttons: Accept (check), Edit (pencil), Reject (x). Accept →
accept route, then the page (or turn) reloads with the new text and the queue moves on as Resolved
does; 409 → toast "the text changed since: reload". Edit → each change written into its field with
`Field.edit(0, len, new)` (undoable, unsaved), the field flashed. Reject → reject route, card gone.

- [ ] **Step 1:** Add the `wordDiff` tests: `("a b c", "a x c")` → `[["=","a "],["-","b"],["+","x"],["="," c"]]`;
  identical strings → one `=`; empty to text → one `+`; and the round-trip property on three French
  sentences. Run `node --test tests/js`: fails (not exported).
- [ ] **Step 2:** Implement `wordDiff`; run: pass.
- [ ] **Step 3:** Write `pw/proposal_check.py` (footnote_writeout item: card shows the diff; Edit puts
  the text in the footnote field unsaved; Reject marks false positive; Accept writes the file and
  moves on). Run: fails.
- [ ] **Step 4:** Implement `proposal.js` and wire it into the issue bar and the turn view. Run the
  check and both suites: pass.
- [ ] **Step 5: Commit** `review_web: proposed fixes with Accept, Edit and Reject`

### Task 6: the batch table (front end)

**Files:**
- Create: `scripts/review_web/batch.js`
- Modify: `index.html` (a "Batch" icon button in the issue bar), `style.css`, `main.js`
- Check: `pw/batch_check.py`

**Interfaces:**
- Consumes: `GET /api/batch`, `POST /api/batch/accept`, `wordDiff`, the current kind/book filters.
- Produces: `openBatch()`.

A full-pane table for the kind chosen in the filter (asks to pick one if "all kinds"): a tick box (only
on rows with a proposal), page, the context (`tail ‖ head` for turns, else the field text with the
flagged words), the proposal as a diff. Buttons: "Tick all with a proposal", "Accept N ticked"
(confirm first, then the result: "N accepted, M failed" and the failed rows marked), close. Clicking a
row (not the box) opens that item in the normal view.

- [ ] **Step 1:** Write `pw/batch_check.py` (two footnote_writeout items: tick all, accept → both files
  changed, rows marked done; one changed on disk first → that row shows the failure). Run: fails.
- [ ] **Step 2:** Implement. Run the check and both suites: pass.
- [ ] **Step 3:** Update `scripts/README` (review_web section: turn view, proposals, batch) and commit
  `review_web: the batch table`
