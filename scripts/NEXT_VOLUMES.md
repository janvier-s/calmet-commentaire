# Spec: bringing the next volumes to the state of volumes 1–21

Written for Claude (and anyone else) picking up the Calmet work on a new volume: Psalms
21b/21c, Proverbs (22) and on through the New Testament. Volumes 01_genese … 21a_psaumes were
taken through everything below between Oct 9 and Oct 14, 2026; this is what was done to them,
in the order to do it, with the decisions behind it. `README.md` is the short command list;
this is the full spec.

## 1. Ground rules (from the user — don't relitigate)

- **The page JSONs stay as close to the printed page as possible.** Never reorder, renumber or
  "correct" anything in `normalized/page_NNNN.json` to match the Vulgate or the verse order.
  Reordering (notes in verse order) happens only in the export. A script that edited refs
  from the Vulgate was written once and had to be reverted: don't do it again.
- **Never OCR the scans.** If text is missing, say so and list the pages; the user can supply
  the original data.
- **Run LLM jobs in the foreground** (`llm_modernize.py`, `seam_check.py`), never in the
  background.
- **Stay on the Calmet modernization**: no detours into the Lectio booklet.
- **Mechanical fixes may be applied; judgement calls are queued.** Anything that needs the scan
  goes into the review queue for the user, with a clear message, not into the data.
- **Commit only when the user says so**, and deploy only when asked. `data/` (normalized pages)
  and `scripts/` are separate git repos; the website is a third.
- Before a bulk change, run with `--dry-run`, look at a sample, then apply. Report counts and
  anything left for the user.

## 2. Where things are

- Scripts: `STUDIUM/scripts` (run from there with `python3`; the editors need
  `uv run --no-project --with pillow python …`). Every path is in `paths.py`.
- Data: `STUDIUM/data/<volume>/`
  - `raw_json/commentaire/page_NNNN.json`: the transcription (old spelling, ſ, &).
  - `source_images/commentaire/page_NNNN.png`: the scans.
  - `normalized/page_NNNN.json`: **the definitive text**, which every step reads and writes.
  - `modernization_error/`: pages the user flagged in the editor (raw JSON + PNG).
- `books.json`: book key → `{number, fr, vul, studium: [volume folders], site}`. Every book is
  already listed, Psalms with three volumes.
- The Vulgate: `douayrheimsbible/static/data/vul/<vul>.json` (all books present). In the Psalms
  its title is verse 1; Calmet leaves the title unnumbered.
- Website: `/Users/Janvier/Documents/Bible n stuff/Websites/dom-calmet-web` (SvelteKit on
  Cloudflare Workers, https://dom-calmet-web.janvier-sabates.workers.dev).
- Reports: `STUDIUM/docs/` (`review_queue.json`, `seam_check.json`, `psalms_check.json`,
  `chapter_check.json`, `manual_issues.json` for issues the user reports by hand).
- Review progress: `data/.review_queue_progress.json`. Item ids are hashes of the message, so
  progress survives a re-audit as long as the message doesn't change.

## 3. The page format (normalized)

```json
{
  "book_title": …, "chapter_title": "CHAPITRE XII." | null, "chapter_number": 12 | absent,
  "chapter_summary": …, "chapter_intro": null (right after chapter_summary, on every page; Calmet's introduction to a chapter, set chapter_number on the page where it opens, and each later page's chapter_intro continues it: export.py joins them, the site shows it under the summary), "chapter_argument": … (Psalms),
  "verses": [{"verse_number": 3, "chapter": 12, "latin": "…", "french": "…", "annotations": null}],
  "commentary": [{"commentary_id": 1, "verse_ref": 3, "chapter": 12, "latin_quote": "…",
                  "french_translation": "…", "french_commentary": "…"}],
  "footnotes": [{"marker": "(a)", "text": "…"}],
  "book_end_marker": …
}
```

Conventions fixed during the review:

| Field | Convention |
|---|---|
| `verse_number` | an int only (`"12."`, `"℣. 12"`, Roman → 12); a range stays a string `"1-2"` |
| `verse_ref` | the same; never null (a block without one continues the previous ref) |
| `chapter` | int, on every verse and commentary block, right after `verse_number`/`verse_ref` |
| `latin`, `french` (verses) | no leading verse number, no underscores; verse 1 starts with a single capital ("En", not "EN") |
| `french_translation` | no underscores when they wrap the whole thing (the site italicises it); partial italics `_…_` kept |
| `french_commentary` | one `\n` = one paragraph; no blank lines; numbered points `1°.` `2°.` start a paragraph (`" \n"` before them); italics as `_…_` |
| footnote calls | `^{(a)}` exactly; footnote `marker` fields `(a)` |
| `annotations` | `null` when empty (never `[]`, `"[]"`, `""`); margin dates as `An du M. 2949.` |
| Psalms | the title is verse **0**, verse 1 is the first line of text (Calmet's printed numbers) |
| Spelling | `Jésus-Christ`, not `JÉSUS-CHRIST` |

## 4. The pipeline for a new volume

Do one volume at a time and check each step's output before the next. `<vol>` is the folder
(`22_proverbes`), `<key>` the books.json key (`proverbs`).

1. **Seed `normalized/`** from the transcription, only if it doesn't exist yet. Volumes 1–21
   were seeded by `legacy/studium_v1/normalize.py`. Check with the user which source to use
   (`raw_json/commentaire/` or `21st_gemini/commentaire/`) before seeding. Never overwrite an
   existing `normalized/`.
2. `python3 modernize.py <vol>`: rule-based pre-pass (ſ, common OCR f/s slips).
3. `LLM_BACKEND=claude python3 llm_modernize.py <vol>`: modernize the French. **Foreground.**
   Cached in `cache/llm_cache.json` by md5 of the text; a usage limit just means re-running
   later (the cache keeps what was done). Don't run other cache writers at the same time.
4. `python3 fix_typography.py <vol>`: ſ → s, `&c.` → etc., `&` → et.
5. `python3 normalize_refs.py <key>`: verse numbers and refs to ints, no numbers in the verse
   text, single capital on verse 1. One-off mislabels go in its `MANUAL` dict.
   *Known flaw:* it fills a missing ref with the previous one, even across a chapter start,
   so the first note of a chapter can carry the last ref of the previous one (Lev 23:1 → 27).
   Step 10 finds these; the user fixes the ref in the editor.
6. `python3 fix_markers.py <vol>`: footnote calls and markers, Jésus-Christ.
7. `python3 tidy_fields.py <vol>`: underscores, annotations, blank lines (see §3). It also
   lists margin years out of step with their neighbours. Show those to the user; fix them only
   when the neighbours make the reading certain (1989 among 2989s), and say which you changed.
8. `python3 paragraph_breaks.py <vol>`: numbered points on their own paragraph; a literal
   `\n` typed in the editor becomes a real break.
9. **Psalms only** (21b, 21c), in this order:
   - `python3 fix_psalm_verses.py <vol>`: relabel verses whose text opens with a number, drop
     verses repeated across a page break;
   - `python3 psalms_check.py <vol>`: aligns every verse to the Vulgate (read-only);
   - `python3 fill_psalm_verses.py --dry-run <vol>`, then without `--dry-run`: verses missing
     from the transcription get the Vulgate Latin, empty French and an annotation saying so
     (queued as "vulgate_filled" for the user to type the French);
   - `python3 add_psalm_titles.py --dry-run <psalm numbers>`, then for real: missing titles
     as verse 0. **Edit its `VOLUME` constant and its `FIRST_LINE` / `TWO_VERSE_TITLE` tables**
     for the new psalms first (titles that share a Vulgate verse with the first line, or span
     two Vulgate verses). Ask the user which psalms they want done; don't skip any because the
     queue says "resolved" (they once marked titles resolved by mistake).
10. `python3 assign_chapters.py <key>`: the `chapter` field (§5). Read
    `docs/chapter_check.json`; the judgement cases go to the queue.
11. `python3 seam_check.py <vol>`: Claude reads every page break for lost or repeated text
    (**foreground**, cached in `cache/seam_cache.json`). Results → `docs/seam_check.json`.
12. `python3 audit_integrity.py ../docs/integrity_audit_<date>.json` → `docs/review_queue.json`.
    Report the counts by kind to the user.
13. **The user reviews** in `review_editor.py` (§7). Commit `data/` when they say.
14. **Publish** (§8).

## 5. Chapters

Calmet prints a chapter heading only on the page where the chapter opens, and that page (and
sometimes the next few) still carries the end of the previous chapter's commentary. The
`chapter` field records the answer once, so nothing downstream guesses:

- after a heading for chapter N+1, entries keep chapter N while their numbers keep rising,
  and switch at the first number that drops back;
- a commentary block with no lemma (no Latin, no French translation) continues the block
  before it and keeps its chapter, whatever its ref says;
- where a chapter changes, a lemma that clearly matches one chapter's Vulgate text decides
  (the bad refs from step 5's flaw);
- a verse whose Latin is plainly the same-numbered verse of the next/previous chapter goes
  there (a heading in the wrong place: Deut page 99). Not for the Psalms.

`chapter_of()` in export.py reads the headings (`CHAPITRE XII.`, `CHAP. XII.` via
`chapter_number`, `PSEAUME LX.`; "SUR LE PSEAUME" is a running head, not a heading).
Check new books for other heading styles before running (the New Testament may differ).

## 6. The checks (what the queue contains)

`audit_integrity.py` collects, most serious first: reported by the user, duplicate pages
(a page copied from the next one), malformed/missing pages, missing verses, Psalms issues,
chapter issues, commentary that doesn't reach the site, page breaks (seam_check), `verse_ref`
going backwards inside a chapter, notes with a lemma but no `verse_ref`, notes other than the page's first with no `latin_quote`, letter-spaced words ("J E S U S"), comments starting with punctuation, a `latin_quote`/`french_translation` cut by the page turn (ending in "-", or with no full stop in a last note with no comment yet) and not continued in the same field overleaf, italics broken at the page turn (left open at the foot of a page and not closed overleaf, or closed exactly at the foot mid-sentence while the quotation goes on in roman overleaf), a full stop at the foot of a page followed by lower case overleaf, "etc." with the sentence running on (an "&" misread as etc.), translations over 3×
the lemma's length (and 40+ characters longer), "l'Hébreu" in a translation (both: commentary
run into `french_translation`), lower case in `latin_quote` (footnote calls ignored), an empty `chapter_summary` on a page that opens a chapter, more
footnotes than distinct calls on the page, notes with no commentary (a lemma alone at the foot of a
page is fine), capitals left in commentary (Roman numerals excepted), broken footnote calls,
missing footnotes.

Lessons from tuning these: test a new check on a few books and look at a sample of what it
flags before trusting the count; the seam check gave 757 flags until it read the text at the
page edge correctly (then 359), and the first chapter assignment flagged 3,684 pages because
refs stored as strings weren't read.

## 7. The review editor

`uv run --no-project --with pillow python review_editor.py` (flags `--kind`, `--book`,
`--skipped`, `--resolved`, `--all`). It shows the scan beside the page's fields. Features the
user relies on: type and book selectors, skip/resolve/reopen, ✕ delete on each verse and
block, Reorder dialog, add verse/commentary (takes the neighbour's chapter), "Flag for Review"
(copies raw JSON + PNG to `modernization_error/`). It saves `verse_number`, `verse_ref`,
`chapter` as ints. When adding a field to the page format, add it to the field lists in
`page_editor.py` (`_build_json_editor`, `_save`) and to new entries in `review_editor.py`.

## 8. Publishing

1. `python3 export.py <key>` (or `--published` for every book already on the site). It
   writes `raw/<site>/chapter_NN.json` (verses, grouped by `chapter`, same-number entries
   merged across a page break) and `calmet/<site>/calmet_chapter_NN.json` (notes sewn across
   pages by `calmet.py`, then sorted by verse; the pages keep the printed order).
2. In the website, for a **new book**:
   - add it to the hard-coded `books` list in `src/routes/+page.svelte` (id = site slug,
     name, chapter count);
   - Psalms: `src/routes/[book]/[id]/+page.server.ts` rejects chapters > 50; verse 0 (the
     title) needs a heading-style display; `chapter_argument` isn't exported yet.
3. `npm run build`. Every exported chapter is prerendered through `entries()` in
   `+page.server.ts` (before this, only Genesis was built and every other chapter was a 404).
4. Check against the production worker, not `vite dev` (they differ: the dev server rendered
   pages the build didn't contain): `npx wrangler dev --port 8799`, then curl a few chapters of
   the new book for 200.
5. Commit the website, then `npm run deploy` (only when the user asks), and curl the live URL.

Site rendering rules already in place (`src/lib/utils/format.ts`): `_x_` → italics; each `\n`
starts a paragraph, except inside italics (quoted verse), where it is a line break; a lemma with
`_` gets partial italics, otherwise the whole lemma is italic.

## 9. Known data problems to expect

From volumes 1–21; look for the same in new volumes:

- verse numbers and refs as strings, Roman numerals, `℣.`, `"II"` meaning 11 or 2;
- refs carried across a chapter start (step 5), wrong refs at the top of a chapter;
- running heads ("COMMENTAIRE.", "ARGUMENT.") left inside `french_commentary`, sometimes with
  text missing after them: report, don't remove without asking;
- pages that duplicate the next page; lost lines at page breaks;
- misread margin years (1 for 2/3, swapped digits: 3648 for 3468);
- OCR slips the LLM leaves (`flnem` for `finem`): fix only when certain, and say so;
- Psalms: titles missing or misread as "PSEAUME", verses filed under the wrong psalm, a refrain
  repeated in two psalms (don't "fix" one from the other).

## 10. Not done yet (as of Oct 14, 2026)

- Psalms 21b, 21c: raw only (288 + 422 pages), the whole pipeline is to do; then the site
  changes in §8.2 before Psalms can be published.
- 1 Samuel: LLM modernization was noted as unfinished (6 batches).
- Margin years flagged by `tidy_fields.py` in 1 Samuel, 3/4 Kings, 2 Chronicles and Esther are
  still to check.
- Literal verse numbers inside translations (`[19.]`) were offered to the user, not done.
