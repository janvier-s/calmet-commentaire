# Handoff: step 4, editable merged that updates itself (Opus)

Work on `main` only; run tests from scripts/ before each commit; preview any batch word by word before applying.
Read first: `plans/handoff-2026-11-07-good-normalized.md` (design, step 4 requirements, gotchas).

## Done (steps 1-3, commits 8871549ca, 8bbb93adf, e1980de06)
- `good_clean.py`, `good_normalized.py`, `good_spell.py`, `good_spell_agent.py`; merge view lists cleanups with undo
  (`/api/merge/cleanup`). `merge_build.good_text` now reads `good_normalized` first.
- `data/01_genese/good_normalized.json` is gitignored (like good_units.json); regenerate with
  `python3 good_normalized.py 01_genese` from scripts/. Merged/ was NOT rebuilt after it: `good_merge_apply.py 01_genese`.

## Next: step 4 (data-integrity risk: never lose hand edits)
(a) Merged view editable (`review_web/merged_view.js` sets contentEditable false). (b) Rebuild merged for the affected
pages whenever old normalized is saved (hook in review_web save path / good_merge_apply). (c) A hand-edited field is
kept on rebuild: store the field hash it was built from; if normalized or Good/decisions changed underneath, flag it
for the user, never overwrite. (d) Undo via versions. Build on `merge_decisions` free edits (`free_edit`,
`locate_edit`), `merge_build.field_hash`, `/api/merge/edit`.

## Open / not done from steps 1-3
- Agent pass not run on the 2046 only_good Genese texts (`good_spell_agent.py prepare`).
- Undo/redo buttons in merge_unit.js untested in a browser (headless check recipe in the other handoff).
- Possible false positive: `dela` -> `delà`.
