# Handoff: good_normalized layer, spellcheck, editable merged

Work on `main` only (user's rule). Contributor text in French is a separate matter; this note is English.
Steps 1-3: hand to **Sonnet**. Step 4: hand to **Opus** (data-integrity risk: it must never lose hand edits).

## Goal (user's words, condensed)
After /merge takes Good text into the book, the text must be edited, italicized, modernized (étois, et c.) and
spellchecked (OCR garble like "As commencement", "ov la Terre") without an LLM pass, or with an agent pass whose
changes the editor lists so false positives can be undone. Agreed design: **three layers**

1. `normalized` = old edition, modernized, hand-fixed. Stays the modernization of "old". Never touched by this work.
2. `good_normalized` = Good's text cleaned once: italics, modernization, spelling. Every automatic change is a
   stored record (before, after, rule) that the editor lists with Undo.
3. `merged` = editable. Today `data/<vol>/merged/` is derived (good_merge_apply.py, merge_build.py) and rebuilt
   from normalized + /merge decisions + free edits, so typing in it is lost. Decided: **edits to old
   normalized must update merged automatically.**

## Done (all on main, tests 590 pass)
- Editor "Merged" toggle (`review_web/merged_view.js`, `/api/merged`): shows merged/ read-only, words taken from Good
  wavy blue; scan switches to Good_Calmet and Good's taken words are wavy blue on it (`scan` in /api/merged).
- /merge: coloured buttons, ≈ noise button, ✎ editor button (`/#edit=vol:page`).
- Modernization of Good: scan_ocr.modern gained et c. -> etc., monnaie, -oit/-oient -> -ait/-aient when hunspell
  knows the new form (every oi of connoissoit). Still missed: accent cases (possedoient -> possédaient).
- Italics: `good_variants.label` keeps each Good word's slant (`sl`); `good_italics.py` makes runs and `apply()` marks
  `_..._` through modernization; changes carry `good_italic`, used by merge_build.good_text and merge_view.
  Eval: italic words median slant 18, roman -2; thresholds ITALIC_AT 9 / ROMAN_AT 4.

## Step 1 (Sonnet): the same rules as "old"
`scan_ocr.modern()` only calls `clean_mechanical.fix_spelling` + `modernize_inplace.modernize_text` on plain text.
`normalized` went through `modernize_inplace.modernize_page`, which also does:
- `clean_mechanical.keep_printed(fn, s, lead)`: Latin spans (found through italic `_` marks) and page-turn word
  halves are left as printed (Calmet's Latin accents terrâ, cùm stay; user's editorial calls are in memory
  calmet-spelling-workflow). Good text had no italics before; now `good_italic` exists, so run modernization
  AFTER italics with keep_printed.
- `fix_spaced_letters`, HEADER_PREFIX strip, lemma/leading-call fixes; then separate scripts on normalized:
  `fix_typography.py` (already does & c. -> etc.), `latin_italics.py`, `normalize_refs.py`/`modernize_refs.py`.
Do: one function `good_clean(text_with_italics) -> text` running that pipeline; fold the new rules (etc., monnaie,
-oit) into the shared tables so normalized and good_normalized share one rule set; preview word-level diff on
Genèse before applying (workflow rule: never apply a batch without it).

## Step 2 (Sonnet): good_normalized store with undoable records
Per unit (uid), per changed span: `{before, after, rule}` list, persisted under `data/<vol>/` (suggest
`good_normalized.json`, or fields beside good_italic in good_units.json). merge_build.good_text should read the
cleaned text. Editor/merge view shows the list with Undo (false positives). Decisions are keyed on texts
(merge_decisions.change_key/text_hash): check they don't all reopen.

## Step 3 (Sonnet): spellcheck, both kinds
Rules + wordlist: spellcheck.py (hunspell via `check()`, `bare_french_words`, ocr_spelling.txt,
spelling_words.txt) for OCR garble such as `Acos`, doubled words ("la Terre ov la Terre"). Agent pass for real-word
and context errors ("As commencement"): preserves `_italics_` and ^{(a)} markers, returns changes, never applies
silently; same record/Undo format as step 2.

## Step 4 (Opus): editable merged, auto-updating
Requirements: (a) the editor edits merged text (Merged view currently read-only: merged_view.js sets
contentEditable false); (b) rebuild merged for the affected pages whenever old normalized is saved (hook in
review_web save path / good_merge_apply); (c) a field the user hand-edited is kept on rebuild: store the field
hash it was built from; if normalized or Good/decisions changed underneath a hand-edited field, flag it for the
user instead of overwriting; (d) undo via versions. Existing machinery to build on: merge_decisions free edits
(`free_edit`, `locate_edit`), `merge_build.field_hash`, `/api/merge/edit`.

## Gotchas
- Rebuilds (`python3 good_units.py 01_genese 1-50`, ~6 min; `good_merge_apply.py 01_genese`) must run from
  `~/Projects/calmet-commentaire/scripts`. The orca worktree has no French dictionary (bare_french_words = 4 words),
  which silently skips modern_words; this cost a bad rebuild once.
- `gv.align` uses ProcessPoolExecutor: debug from a script file with `if __name__ == "__main__"`; chapters are a set
  of ints; stream words carry `sl`.
- macOS `sed -i` needs `-i ''`; prefer python edits.
- Tests: `uv run --no-project --with pytest --with pillow --with numpy python -m pytest tests -q` from scripts/.
- Headless check of editor: copy-patch merged_view.js `localStorage ... || true`, start review_web.make_server on a
  scratch token, Chrome `--headless=new --screenshot` with `?key=<token>`; restore the file after.
- Server restart is needed to pick up new endpoints.
