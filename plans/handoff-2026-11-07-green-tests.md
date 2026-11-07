# Handoff: get the test suite green on janvier-s/genese-merge-gaps

## Goal
Fix the failing tests and report a green run. Do not merge to main until green.

## Done so far
- Branch `janvier-s/genese-merge-gaps` (pushed, 7 commits ahead of origin/main, nothing behind).
- My fixes in scripts/good_units.py (+ tests in scripts/tests/test_good_units.py): footnote-barrier removal, `_mend_strays`,
  `_find_verses`, `relink_displaced`, `flag_unplaced`/`via`; merge_view.rows + review_web/merge_list.js/merge_state.js filter `ck=`.
- Last commit bae1a98cc "script optimizations" = the user's own edits to scripts/good_variants.py and scripts/scan_ocr.py (not mine).
- New data installed in main checkout data/01_genese/good_units.json (old copy in the session scratchpad); decisions still re-attach (14/15 + 3).

## Problem
Before the user's optimizations: 620 passed, 4 skipped. After: `10 failed, 604 passed, 4 skipped, 6 errors`
(e.g. tests/test_latin_italics.py::test_existing_italics_not_broken: FileNotFoundError).
Command: `cd scripts && uv run --with pytest --with pillow pytest -q tests --ignore=tests/test_good_mapping.py --ignore=tests/test_margin_crop.py`

## Next steps
1. `data/` is gitignored and `scripts/cache` was removed from this worktree: re-create `ln -s /Users/Janvier/Projects/calmet-commentaire/scripts/cache scripts/cache`
   (untracked, never commit it) and run with `CALMET_DATA=/Users/Janvier/Projects/calmet-commentaire/data`. Re-run tests; some failures/errors may just be this.
2. For failures left, check whether bae1a98cc caused them (`git stash`-free: compare with `git worktree`/checkout of bae1a98cc~1). If the
   optimization broke behavior, fix the code (not the test) or ask the user.
3. Commit with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`, push, tell the user.

## Preferences
Be concise. Commit freely; push only when asked (user already asked to push this branch). Ask before merging to main.
Do not regenerate good_units.json (6 min, ~10 with flags) unless a fix requires it.
