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
- The Vulgate: `scripts/vulgate/<vul>.json` (a copy of douayrheimsbible/static/data/vul; all books present). In the Psalms
  its title is verse 1; Calmet leaves the title unnumbered.
- Website: `dom-calmet-web` (github.com/janvier-s/dom-calmet-web, cloned beside this repository or set with CALMET_WEB; SvelteKit on
  Cloudflare Workers, https://dom-calmet-web.janvier-sabates.workers.dev).
- Reports: `STUDIUM/docs/` (`review_queue.json`, `seam_check.json`, `psalms_check.json`,
  `chapter_check.json`);
  `docs/footnotes/<vol>.json` (the footnote report of each volume) and
  `docs/footnotes/held.json` (every footnote still held, §10).
- `scripts/cache/` is not in git (`.gitignore`): Claude's caches and the downloaded sources
  in `cache/refs/` (§10) live only on this disk.
- Review progress: `data/<book>/review.json` (statuses, false positives, page to-dos). Item ids are
  hashes of the message, so progress survives a re-audit as long as the message doesn't change.

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
4. `python3 modernize_inplace.py <vol>`: high-coverage rule-based and Hunspell-audited in-place
   modernization for archaic vocabulary (`ame` → `âme`, `foible*` → `faible*`, `jusques` elisions,
   `vôtre`/`nôtre` adjective corrections, `playe`, `vray`, `grace`, `très-X` → `très X`, `-uë`
   participles, `-yent` verb endings, accents and trémas) across French verses, translations,
   commentary, and chapter summaries (§12).
5. `python3 fix_typography.py <vol>`: ſ → s, `&c.` → etc., `&` → et.
6. `python3 normalize_refs.py <key>`: verse numbers and refs to ints, no numbers in the verse
   text, single capital on verse 1. One-off mislabels go in its `MANUAL` dict.
   *Known flaw:* it fills a missing ref with the previous one, even across a chapter start,
   so the first note of a chapter can carry the last ref of the previous one (Lev 23:1 → 27).
   Step 10 finds these; the user fixes the ref in the editor.
7. `python3 fix_markers.py <vol>`: footnote calls and markers, Jésus-Christ.
8. `python3 tidy_fields.py <vol>`: underscores, annotations, blank lines, spaces at the ends
   of fields, calls inside footnote text (see §3), then `python3 punctuation.py --apply <vol>`:
   French spacing with ordinary spaces (space before ; : ? ! », after «; none before , .;
   straight ' apostrophes; no non-breaking spaces or curly ’ in the data: export.py adds them
   for the site), … for .... The editors apply the same rules on every save. `tidy_fields.py` also
   lists margin years out of step with their neighbours. Show those to the user; fix them only
   when the neighbours make the reading certain (1989 among 2989s), and say which you changed.
9. `python3 paragraph_breaks.py <vol>`: numbered points on their own paragraph; a literal
   `\n` typed in the editor becomes a real break.
10. **Psalms only** (21b, 21c), in this order:
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
11. `python3 assign_chapters.py <key>`: the `chapter` field (§5). Read
    `docs/chapter_check.json`; the judgement cases go to the queue.
12. `python3 seam_check.py <vol>`: Claude reads every page break for lost or repeated text
    (**foreground**, cached in `cache/seam_cache.json`). Results → `docs/seam_check.json`.
13. `python3 audit_integrity.py ../docs/integrity_audit_<date>.json` → `docs/review_queue.json`.
    Report the counts by kind to the user.
14. **The user reviews** in `review_web.py` (§7). Commit `data/` when they say.
15. **Footnotes** (§10): references and authors written out in French, Hebrew and Greek
    checked, doubtful notes settled from context; what is left waits for the scans.
16. `python3 modernize_refs.py <vol>`, then with `--apply`: Bible references left in the old
    form (Roman chapters, abbreviations) written out in the commentary and the notes (§11).
    After the footnotes, which write out most of the notes' references themselves.
17. **Publish** (§8).

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
run into `french_translation`), `french_translation` not ending with punctuation (`translation_no_punct`, page's final commentary and footnote calls ignored),
missing capital in `french_translation` 1st letter (`lowercase_translation`, page's first commentary ignored), lower case in `latin_quote`
(footnote calls ignored), `latin_quote` not ending with punctuation (`lemma_no_punct`, page's final commentary and footnote calls ignored), an empty `chapter_summary` on a page that opens a chapter, more
footnotes than distinct calls on the page, notes with no commentary (a lemma alone at the foot of a
page is fine), capitals left in commentary (Roman numerals excepted), broken footnote calls,
missing footnotes.

Lessons from tuning these: test a new check on a few books and look at a sample of what it
flags before trusting the count; the seam check gave 757 flags until it read the text at the
page edge correctly (then 359), and the first chapter assignment flagged 3,684 pages because
refs stored as strings weren't read.

## 7. The review editor

`python3 review_web.py` (the browser editor; scripts/README.md, "Work through the queue"). It
resumes where the last session stopped; flags `--kind`, `--book`, `--skipped`, `--resolved`,
`--all`, `--fresh`. It saves `verse_number`, `verse_ref`, `chapter` as ints. When adding a field to
the page format, add it to the field lists in `review_web/app.js` and `review_store.py`.

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
  repeated in two psalms (don't "fix" one from the other);
- verses accidentally formatted as commentary: a lowercase lemma identical to the verse text with
  empty commentary, or continuation notes where the verse was duplicated into `latin_quote` and
  `french_translation`;
- embedded lemmas in commentary: printed ALL-CAPS Latin lemmas and French translations trapped
  inside `french_commentary` instead of in their structured fields;
- displaced footnotes in commentary: blocks with no lemma or translation whose text consists of
  footnote citations (e.g. `(a) [UNCERTAIN HEBREW]`), missing from the page's `footnotes` list.

## 10. Footnotes (`footnotes.py`, Oct 15–18, 2026)

Calmet's notes are abbreviated Latin citations ("Aug. l. 22. contra Faust. c. 10.", "Joseph.
Antiq. l. 5. c. 1."), Bible references, and quotations in Hebrew and Greek that the
transcription often garbled. Volumes 01–21a went through all of this; 1,579 notes of about
25,000 are still held for the scans.

### What the user decided (memory: footnote-fix-conventions)

- Everything written out in French: "Saint Augustin, Contre Fauste, livre 22, chapitre 10";
  Bible books with Calmet's Vulgate names (1–4 Rois, 1–2 Paralipomènes, 1–2 Esdras = Ezra and
  Nehemiah, Ecclésiastique, Machabées), Psalms in Vulgate numbering. A quotation before the
  citations stays as printed.
- Hebrew and Greek as printed; misreadings set right silently.
- **An asterisk marks only text guessed from context** (`צלם*`, `Isaïe* 49:16*`), never a
  correction confirmed by a source.
- Calmet's own forms stay: Μωσῆς, ἀναμέσον, readings of other editions than our Septuagint.
- "Theod." beside Aquila and Symmachus is **Théodotion**; "Theodoret." printed in full is
  Théodoret (his commentary on the Psalms reports the Hexapla readings).
- Psalm 115 is in Clementine numbering (verses 10–19: *Pretiosa* is 115:15); our Vulgate text
  numbers it from 1, `bible_refs.clementine()` maps it.

### The commands, in order (run from `scripts/`)

```
uv run --no-project --with pillow python footnotes.py run <vol> --local            # free: all the local checks, report only
uv run --no-project --with pillow python footnotes.py run <vol> --no-scan --context # + Claude, text only
python3 footnotes.py apply <vol>                                                    # proposals into normalized/; flagged notes held
python3 footnotes.py held                                                           # every held note, all volumes -> docs/footnotes/held.json
```

`run` writes `docs/footnotes/<vol>.json` (each changed or flagged note: text, proposal, why,
flags). Every Claude answer is cached (`cache/footnote_cache.json`), so re-running is free for
what was done; usage goes to `cache/usage.log`. On "hit your limit" the run stops calling
Claude, writes what it has and ends: it does not wait or resume by itself.

### What `run` does

1. **Local, free.**
   - Bible references rendered (`render_bible`): only when the note is references alone after
     a bare "Voyez/Vide/Voir"; anything else in front ("Voyez Grotius sur…") goes to the
     expander. (This check was too loose once and cut 16 notes down to their reference.)
   - Hebrew against the Hebrew Bible (OSHB) and Greek against the Septuagint, allowing for
     the type: ר/ד ה/ח ב/כ ו/ז/ן confused, ו/י spelt full or not; the ου ligature read ε ω υ
     ῦ ȣ ẽ, στ read ς, καὶ read κὶ. A quotation found there is corrected word by word from it
     (accents kept as Calmet prints them; proper nouns, unaccented in the Septuagint text,
     left alone).
   - Greek not from the Bible: each word against an Ancient Greek dictionary
     (`footnote_spell.py`, hunspell-grc): misread ligatures set right when one reading is a
     word; missing breathings/accents completed (keeping Calmet's); one-letter misprints when
     the dictionary has one candidate; words with no accent at all get the Septuagint's usual
     form. The dictionary writes acutes as *oxia* (U+1F79…), our text as *tonos*: map before
     looking up (`OXIA`). Keep one hunspell process for the run (it loads 760,000 forms).
   - Hebrew not from the Bible: each word in the Hebrew Bible, the Targums or Strong's lexicon,
     as written, after its prefixes (ו ה ב כ ל מ ש) or its plural/possessive suffixes (two
     letters at least, stem of three). Only a non-final letter at a word's end is corrected
     automatically (תקפ → תקף); one-letter guesses on short unpointed words proved wrong too
     often. Known gap: a misreading that splits into real parts passes (הבטים for הבטחים).
   - References: "1/2 Rois" left by an older expansion (Calmet's 1 Samuel or a modern 1 Kings?)
     settled by the volume, by which verse exists, or by the Latin quoted; a verse that does
     not exist corrected only when the Latin quoted confirms the right one.
   - Abbreviations written out by `footnote_expand.py` from `footnote_glossary.txt` where every
     citation is known.
2. **Scan** (not run on 01–21a beyond Genesis): Claude reads the crop of the footnote area
   (`crop()`: from the lowest rule, margins trimmed, ~1560 px across), several pages a call.
   `--uncertain-only` limits it to [UNCERTAIN]/[ILLEGIBLE] notes.
3. **Context** (`--context`): the notes still doubtful go to Claude as text, 75 a call, with
   the passage the note is called from, the Bible verse (Vulgate, Septuagint, Hebrew), and the
   problem; Claude answers with edits only (`from`/`to`/`guessed`). Guessed text is starred;
   a placeholder may be replaced, never deleted; anything Claude is unsure of stays held.
   About $0.005 a note (Sonnet); $16 for all of 01–21a.
4. **Expand**: Claude writes out what the glossary could not (50 notes a call).

Run with `--local` first and look at the report; then the Claude stages; `apply`; then sample
`docs/footnotes/<vol>.json` (`why` says what changed and why) before committing.

### The sources (`scripts/cache/refs/`, downloaded once)

| Folder | What | From |
|---|---|---|
| `hebrew_oshb.json` | Hebrew Bible | Open Scriptures (OSHB) |
| `lxx/` | Septuagint | getbible |
| `grc_hunspell/` | Ancient Greek dictionary (grc.dic/.aff) | Fedora `hunspell-grc` RPM (archives.fedoraproject.org, release 38), himeros.eu |
| `targum/` | Onkelos, Jonathan, Jerusalem, the Writings | Sefaria export bucket (storage.googleapis.com/sefaria-export, `json/Tanakh/Targum/…/Hebrew/merged.json`); Tafsir Rasag left out (Arabic in Hebrew letters) |
| `strongs/StrongHebrewG.xml` | Strong's Hebrew lexicon | github.com/openscriptures/strongs |

### Costs and lessons

- Each Claude call is a `claude -p --safe-mode` subprocess: a fixed ~10k tokens a call,
  whatever its size, so batch large. Output (Greek and Hebrew are about a token a character)
  costs five times input: ask for edits, not whole notes.
- Scanning every flagged note would have meant 3,630 pages. The local checks, the dictionary,
  the Targums and the context pass brought 6,340 notes waiting for a scan down to 1,579 on
  1,230 pages, for about $16 of Claude.
- Sample every new rule's corrections before applying: each round found a few wrong ones
  (ἄυλης "fixed" to αὔλης, a lone ἐ read οὐ, Νωεμὶ aligned to the Septuagint).

## 11. Bible references in the commentary (`modernize_refs.py`, Oct 19, 2026)

The footnote pipeline writes out the references in the notes; the commentary kept Calmet's
form ("Voyez 3. Reg. IV. 9.", "le Pseaume XXXV. 25."), and some notes slipped through. The
script finds them with `bible_refs.find_refs` and writes them as the notes are written
("3 Rois 4:9", "le Psaume 36:25"). No model is called; volumes 01–21a: about 1,640 references.

- Only references with an old tell are touched (Roman chapter, abbreviated or old spelling,
  "3." / "I." before the name, "℣."); modern ones are left alone.
- Also read: book names in italics (`_Genes._ XXI. 14.`, the italics are dropped), and lists
  that go on with bare chapters (`Prov. II. 2. VI. 21. et XI. 21.`), even past items already
  written out.
- Every rewrite is checked against the Clementine Vulgate. What fails goes to
  `reports/modernize_refs_review.tsv` instead of being changed; a bare chapter in a list after
  a good reference is written as printed (a misprint of Calmet's, not a misreading).
- Words read as references are thrown out: "deuil" (Deu + il = 49), "deux", "Lévi", "exil",
  "collet", "Genèse. Cet" (C = 100). These passed the Vulgate check, so don't loosen this.
- Settled cases go in its `MANUAL` dict, keyed by page and the reference as printed: the
  reference it is, `None` (write out as printed), or `""` (not a reference: leave). The user
  asked that **no tokens be spent on scans** for this: settle from the passage and the Vulgate
  (the Latin quoted, the theme of a list), star what is guessed, write the rest as printed.
- What the review found in 01–21a: Hebrew numbering (Num 11:35 = Vulgate 11:34, Psalm 116:10 =
  115:10, Psalm 10:7, 14 = 9:28, 35), Roman numerals misread (XXVIII as XVIII, II as LII),
  "70" = the Septuagint, not a verse ("Genes. XXVI. 14. 70."), and **"Sup." = *Supra***, not
  Sagesse (*Sap.*).
- The audit (step 12) queues every starred reference, in the commentary or the notes, and the
  `None` entries of `MANUAL` as `guessed_ref`, for the user to check on the scan in the
  editor; `footnote_asterisk` keeps the notes with other guessed words (Hebrew, Greek, fills).
- `bible_refs._VN` was changed with it: a verse number is cut off before a book name only when
  it is 1–4 (a book's number: "31. 1 Rois"); before, "XXXI. 24. 25. Isai." lost its 25.
- **Completed across all 46 Old Testament books (Oct 21, 2026)**: `bible_refs._TABLE` was
  expanded with Latin and OCR spelling variants (`Iudic.`, `Iosuæ`, `Ierem.`, `Iob`, `Lævit.`,
  `Coloff.`, `Ysai.`, `Judicum`, `Josue`, `Josuae`). `modernize_refs.MANUAL` was populated with
  over 150 settled entries across books 21b through 46. Full backwards verification ran clean
  with **0 left to review** in `reports/modernize_refs_review.tsv`.

## 12. In-place French & Hunspell modernization (`modernize_inplace.py`, Oct 21, 2026)

Runs high-coverage in-place French modernization across all French fields (`verses[].french`,
`commentary[].french_translation`, `commentary[].french_commentary`, and chapter arguments/summaries).
Over 16,600 replacements applied across all 46 Old Testament volumes in two stages:

- **Core vocabulary pass (9,376 replacements)**:
  - `ame` / `ames` → `âme` / `âmes` (1,340+ instances);
  - `foible*` → `faible*` (`foible`, `foibles`, `foiblesse`, `foiblesses`, `foiblement`, `affoiblir`,
    `affoibli`, `affoiblit`, `affoiblis`, `affoiblie`, `affoiblies`, `affoiblissement`, `affoiblissements`);
  - `jusques` / `jusque` elisions: `jusques à/au/aux/en/ici/où/aujourd'hui/au-delà` → `jusqu'à/au/aux/en/ici/où/aujourd'hui/au-delà`,
    `jusques-là` → `jusque-là`, and remaining standalone `jusques` → `jusque`;
  - `vôtre` / `nôtre` adjective vs pronoun: converted 5,000+ possessive adjectives to `votre` / `notre`
    (`vôtre serviteur`, `nôtre Dieu`) while preserving the circumflex on pronouns (`le vôtre`, `la nôtre`,
    `les vôtres`, `les nôtres`);
  - Other 18th-century forms: `playe(s)` → `plaie(s)`, `vray(e)(s)` → `vrai(e)(s)`, `grace(s)` → `grâce(s)`,
    `isle(s)` → `île(s)`, `mesme(s)` → `même(s)`, `maistre(s)` → `maître(s)`, `roide(ur)` → `raide(ur)`,
    `pourquoy` → `pourquoi`, `voute(s)` → `voûte(s)`, `prestre(s)` → `prêtre(s)`, `hoste(s)` → `hôte(s)`;
  - Participles after auxiliaries: `sont étonnez` → `sont étonnés`, `mes os sont troublez` → `mes os sont troublés`;
  - Trailing OCR apostrophes: `moi'` → `moi`, `toi'` → `toi`, `lui'` → `lui`.

- **Hunspell-audited pass & `très-X` (7,320 replacements)**:
  - **`très-X` hyphen modernization**: standardized all 1,225 occurrences (`très-grand` → `très grand`,
    `très-peu` → `très peu`, `très-saint` → `très saint`, `très-fort` → `très fort`), while strictly
    preserving the Divine Title `Très-Haut` (`le Très-Haut`);
  - **Feminine participles (`-uë`)**: `venuë` → `venue`, `étenduë` → `étendue`, `connuë` → `connue`,
    `dûë` → `due`, `résoluë` → `résolue`, etc.;
  - **Verb endings (`-yent`)**: `croyent` → `croient`, `ayent` → `aient`, `voyent` → `voient`,
    `employent` → `emploient`, etc.;
  - **Accents**: `déja` → `déjà`, `regne(s)` → `règne(s)`, `misericorde(s)` → `miséricorde(s)`,
    `siécle(s)` → `siècle(s)`, `fléche(s)` → `flèche(s)`, `chûte(s)` → `chute(s)`, `plûpart` → `plupart`,
    `disgrace(s)` → `disgrâce(s)`;
  - **Diphthongs & trémas**: `autrefais` → `autrefois`, `toutefais` → `toutefois`, `stile(s)` → `style(s)`,
    `proye(s)` → `proie(s)`, `orgüeil` → `orgueil`, `obéïssance` → `obéissance`, `louë` → `loue`, `avouë` → `avoue`;
  - **Saints & Titles (`S.` expansion & capitalization)**:
    - Expanded abbreviation `S.` → `Saint` / `saint` before Church Fathers and Apostles across commentary and footnotes (`S. Jérôme` → `Saint/saint Jérôme`, `S. Augustin` → `Saint/saint Augustin`, `S. Paul` → `Saint/saint Paul`, `S. Esprit` → `Saint-Esprit`, `S. Siège` → `Saint-Siège`);
    - Capitalized `saint` → `Saint` at the start of fields/sentences or after semicolons (`;`) and colons (`:`) across all commentary and footnote text fields (`footnotes[].text`).
  - **Expansion of `J. C.` to `Jésus-Christ`**:
    - Expanded all variants (`J. C.`, `J.-C.`, `J.C.`, `J. C`, `J.-C`, `Jesus-Christ`, `JESUS-CHRIST`, `Jésus Christ`, `JESUS CHRIST`) to standardized `Jésus-Christ` (rendered in small caps on the website), retaining sentence-ending periods where applicable (`J.-C. Qui...` → `Jésus-Christ. Qui...`).
  - **Footnote Calls Punctuation Movement**:
    - Moved punctuation placed after footnote calls to the left of the call (`mot ^{(a)}.` → `mot. ^{(a)}`, `mot ^{(a)},` → `mot, ^{(a)}`, `mot ^{(a)} ;` → `mot ; ^{(a)}`, `mot ^{(a)} :` → `mot : ^{(a)}`, `mot ^{(a)} ?` → `mot ? ^{(a)}`), deduplicating when punctuation already existed on the left and respecting French typographic spacing around high punctuation.
  - **Punctuation Spacing**:
    - Enforced mandatory spacing after punctuation marks (`,`, `;`, `:`, `!`, `?`, `.`) when immediately followed by text or opening quotes, and after footnote calls.

- **OCR Long-S & Typographical Confusions Pass (Oct 27–28, 2026)**:
  - **`forte(s)` → `sorte(s)` (324 replacements)**:
    - Adverbial phrases: `en sorte que`, `de sorte que`, `en quelque sorte`, `de cette sorte`, `en cette sorte`, `de la sorte`, `de même sorte`, `de telle sorte`, `en telle sorte`, `faire en sorte`.
    - Determiners & noun phrases: `cette sorte de`, `ces sortes de`, `une sorte de`, `autre sorte de`, `plusieurs sortes de`, `toutes sortes de`, `toute sorte de`, `différentes/diverses sortes de`, `nouvelle(s) sorte(s) de`, number words `deux/trois/... sortes de`.
    - Strictly preserves genuine adjectives: `ville forte`, `places fortes`, `armée forte`, `femme forte`, `la plus forte de leurs raisons`.
  - **`fait` → `sait` (133 replacements)**:
    - Propositional / knowledge clauses: `On sait que / qu'`, `l'on sait que / qu'`, `Ne sait-on pas que / qu'`, `Qui sait si`, `Nul ne sait ce qui / que`, `Elle ne sait ce que c'est`.
    - Negative knowledge constructions: `On ne sait que trop`, `On ne sait pas précisément`, `On ne sait point` (while preserving `ne fait point la cuisine`), `On ne sait ni le`, `On ne sait comment`, `On ne sait quel / quelle / quels / quelles`.
    - Adverbs of certitude / manner with *savoir*: `On sait d'ailleurs que`, `On sait certainement que`, `On sait indubitablement que`, `On sait pourtant que`, `On sait très peu`, `On sait par l'Histoire / par Joseph`.
    - Strictly preserves genuine forms of *faire*: `faire attention`, `faire mention`, `faire cas`, `faire difficulté`, `faire des présents`, `faire la cuisine`, `a-t'on fait`.
  - **`çç` → `ç` & contextual restorations (207 replacements)**:
    - Standard `çç` → `ç`: `commençait`, `avançait`, `exerçait`, `menaçait`, `aperçait`, `apperçait`, `plaçait`, `lançait`, `prononçait`, `Français`, etc.
    - Contextual restoration `conççait` → `conçoit`: restores the 3rd-person singular present indicative of *concevoir* (*« On conçoit aisément »*, *« il conçoit de grands projets »*), preventing erroneous conversion to non-existent `conçait`.
    - Contextual restoration `diççait` → `disait`: restores *disait* (printed *difoit* in source).
    - Page seam hyphenation: `re-` + `ççait` → `re-çoit` (Job 78), `avan-` + `ççait` → `avan-çait` (Zacharie 60).
  - **Vocative `O` → `Ô` (186 replacements)**:
    - Standardizes standalone French vocative/exclamative `O` to `Ô` before divine names, personal address, and vocatives (`Ô Dieu`, `Ô Seigneur`, `Ô Israël`, `Ô mon âme`, `Ô Père`, `Ô Roi`, `Ô vous`, etc.), while preserving Latin quotes and Hebrew letter headings (`COPH`, `O`).
  - **Obsolete Diaeresis (`¨`) Normalization (222 replacements across 199 files)**:
    - **Participles & Adjectives in `-uë / -uës`**: modernized to standard `-ue / -ues` (`tonduë` → `tondue`, `abbatuë` → `abattue`, `cheveluës` → `chevelues`, `interrompuës` → `interrompues`, `prévûë` → `prévue`, `devenuë` → `devenue`, `bleuës` → `bleues`, `accouruës` → `accourues`, `fouvenuë` → `souvenue`, etc.).
    - **Verbs in `-uer`**: stripped mute tréma on indicative/subjunctive forms (`diminuë` → `diminue`, `contribuë` → `contribue`, `remuë` → `remue`, `infinuë` → `insinue`, `influë` → `influe`, `statuë` → `statue`, `perpetuë` → `perpétue`, `restituë` → `restitue`, `exténuë` → `exténue`, `substituë` → `substitue`, etc.).
    - **Tréma on `ÿ`**: normalized 18th-century/OCR spellings (`Enÿvrée` → `Enivrée`, `paÿs` → `pays`, `Martianaÿ` → `Martianay`, `Tÿrin` → `Tyrin`, `Ieronÿm` → `Ieronym`, `ÿ. 6.` → `℣. 6.`).
    - **Archaic `oë` & `ü`**: normalized to modern French (`boëte` → `boîte`, `coëffure` → `coiffure`, `moëlle` / `moüelleuse` → `moelle / moelleuse`, `secoüez` → `secouez`, `joüions` → `jouions`, `réüniffez` → `réunissez`, `réüffit` → `réussit`, `doüane` → `douane`, `soüetté` → `fouetté`, `remüement` → `remuement`, etc.).
    - **Strict Preservations**: strictly preserved genuine French diaereses (`aiguë`, `ciguë`, `contiguë`, `ambiguë`, `exiguë`) and proper names (`Manuë`, `Suë`, `Thécuë`, `Saül`, `Ésaü`, `Emmaüs`, `Capharnaüm`, etc.).
  - **Obsolete & Broken Hyphens Normalization (2,618 replacements across 1,995 files)**:
    - **Single-Word Compound Normalization**: 18th-century hyphenated compound adverbs and words modernized to a single unhyphenated word (`long-temps` → `longtemps` [567], `bien-tôt` → `bientôt` [292], `aussi-tôt` → `aussitôt` [279], `si-tôt` → `sitôt` [16], `sur-tout` → `surtout` [25], `par-tout` → `partout` [26], `mal-aisé(e)(s)` → `malaisé(e)(s)` [78], `marche-pied(s)` → `marchepied(s)` [37], `vrai-semblable(s)` → `vraisemblable(s)` [16], `vrai-semblance(s)` → `vraisemblance(s)` [11], `vrai-semblablement` → `vraisemblablement`, `contre-temps` → `contretemps` [19], `contre-sens` → `contresens` [2], `haut-bois` → `hautbois` [5], `bien-faisant(e)(s)` → `bienfaisant(e)(s)` [12], `bien-heureux(-se)(s)` → `bienheureux / bienheureuse(s)` [3], `bien-séant(e)(s)` → `bienséant(e)(s)` [2], `mal-habile(s)` → `malhabile(s)` [2], `mal-propre(s)` / `mal-propreté` → `malpropre(s) / malpropreté` [5], `mal-faire` → `malfaire` [4], `mal-avisé(e)(s)` → `malavisé(e)(s)` [1], `mal-heur` → `malheur` [1], `non-obstant` → `nonobstant` [1], `quelque-fois` → `quelquefois` [1], `clair-voyant(e)(s)` → `clairvoyant(e)(s)` [1]).
    - **Spaced Compound Normalization**: 18th-century hyphenated adverbial/prepositional turns modernized to standard unhyphenated spaced words (`même-temps` → `même temps` [163], `aussi-bien` → `aussi bien` [176], `non-seulement` / `Non-seulement` → `non seulement / Non seulement` [271], `dès-lors` / `dés-lors` → `dès lors` [29], `bonne-heure` → `bonne heure` [13], `bonne-chère` → `bonne chère` [14], `peu-près` → `peu près` [27], `mal-à-propos` → `mal à propos` [52], `tout-à-fait` → `tout à fait` [64], `petit-à-petit` → `petit à petit` [9], `bien-aise` → `bien aise` [8], `bien-fait(s)` → `bien fait(s)` [5], `au-long` → `au long` [1], `au-travers` → `au travers` [5], `à-cause` → `à cause` [2], `d'en-bas` / `en-bas` → `d'en bas / en bas` [12], `d'en-haut` / `en-haut` → `d'en haut / en haut` [6]).
    - **Contextual Adverbial `de-là` → `de là` (205 replacements)**: converted `de-là` to `de là` when used demonstratively/adverbially (*« de là vient »*, *« de là il s'ensuit »*, *« sortir de là »*), while strictly preserving `au-delà`, `par-delà`, `en-deçà`, and `jusque-là`. Also normalized `au-de-là` → `au-delà`, and prepositional `au-tour de` → `autour de`, `au-près de` → `auprès de`.
    - **OCR Mid-Word Line-Wrap Hyphenations**: collapsed mid-word hyphenation artifacts caused by line breaks in original prints or OCR scanning (`com-me` → `comme`, `di-sant` → `disant`, `afflic-tion` → `affliction`, `cui-vre` → `cuivre`, `in-constant(s)` → `inconstant(s)`, `Sau-veur` → `Sauveur`, `Ben-jamin` → `Benjamin`, `Jo-seph` → `Joseph`, `Crain-dre` → `Craindre`, `Offi-ciers` → `Officiers`, `Prê-tres` → `Prêtres`, `Commenta-teurs` → `Commentateurs`, `Ro-mains` → `Romains`, `Biblio-thécaires` → `Bibliothécaires`, `Baby-lonie` → `Babylonie`, `Is-raël` → `Israël`, `Jé-rusalem` → `Jérusalem`, `Zacha-rie` → `Zacharie`, `Na-zareth` → `Nazareth`, `Eusè-be` → `Eusèbe`, `Jérô-me` → `Jérôme`, `Jean-Bapriste` → `Jean-Baptiste`, `non-feulement` → `non seulement`, etc.). Preserves Hebrew decomposition `Emmanu-el` (*« Quia Emmanu-el »* in Isaïe 8:10).
    - **Strict Compound Preservations**: strictly preserved legitimate modern French hyphenated compounds (`peut-être`, `grand-prêtre`, `vis-à-vis`, `par-dessus`, `au-dessus`, `au-dessous`, `au-delà`, `par-delà`, `ci-devant`, `ci-après`, `arc-en-ciel`, `chef-d'œuvre`, `petit-fils`, `beau-père`, `plate-forme`, inverted verb-pronoun pairs `est-ce`, `dit-il`, `a-t-on`, imperative pronouns `louez-le`, `mettez-la`, `animez-les`, and Biblical Hebrew hyphenated names `Cariath-iarim`, `Cadés-Barné`).
  - **Obsolete & Erroneous Circumflex (`^`) Normalization (821 replacements across 650 files)**:
    - **Past participles in `-û`**: modernized 18th-century participles to modern standard French (`lû` → `lu` [409], `bû` → `bu` [63], `tû` → `tu` [23], `eû` → `eu` [12], `deçû` → `déçu`, `dépoûrû` → `dépourvu`), while strictly preserving legitimate modern circumflex words `dû`, `mûr`, `sûr`.
    - **OCR & long-s artifacts**: `foû` → `fou` [15], `soû` → `fou` [2], `fû` → `su` [1], `affûre` / `asûre` → `assure` [12], `mê ne` → `même`, `ellemême` → `elle-même`.
    - **Archaic spellings & doubled consonants**: `aîlez` → `ailés` [10], `flâme(s)` → `flamme(s)` [9], `phantôme(s)` → `fantôme(s)` [4], `paîtri(s/t/r)` / `pâtris` → `pétri(s/t/r/s)` [11], `piquûre(s)` → `piqûre(s)` [3], `pêles` → `pelles`, `jarêts` → `jarrets`, `plustôt` → `plutôt`, `accoûtumance` → `accoutumance`, etc.
    - **Verbs in `-oître`**: normalized future and conditional stems (`connoîtra...` → `connaîtra...`, `disparoît...` → `disparaît...`, `apparoît...` → `apparaît...`, `reparoît...` → `reparaît...`).
    - **Proper names**: `ierôme` / `iérôme` → `Jérôme`, `mathâthias` → `Mathathias`, `lasthêne` → `Lasthène`, `hérodiâs` → `Hérodias`, `sennachêrib` → `Sennachérib`.
    - **Strict Preservations**: strictly preserved genuine French circumflex words (`fête`, `même`, `être`, `père`, `grâce`, `âme`, `bête`, `tête`, `maître`, `connaître`, `abîme`, `apôtre`, `août`, `sûr`, `mûr`, `dû`, `jeûne`, `goût`, `croître`, `traînoir`, `droit d'aînesse`), all 3rd-person singular imperfect subjunctives (`qu'il éteignît`, `qu'il parût`, `qu'il connût`, `qu'il s'abstînt`, etc.), and Latin ablatives/genitives (`aquâ`, `terrâ`, `suâ`, `spiritûs`, `exercitûs`, etc.).
  - **Obsolete `y` $\rightarrow$ `i` / `î` / `aie` / `oi` Normalization (355 replacements across 264 files)**:
    - **`abyme` $\rightarrow$ `abîme`**: `l'abyme` → `l'abîme` [9], `abymes` → `abîmes` [5], `d'abyme` → `d'abîme` [1], `abysme` → `abîme` [1].
    - **`envyrez` / `envyre` $\rightarrow$ `enivrés` / `enivre`**: `envyrez` → `enivrés`, `envyre` / `envyvre` → `enivre`, `envyvrera` → `enivrera`, `enyvrait` / `s'enyvrait` → `enivrait / s'enivrait`, `n'envyez` → `n'enviez`.
    - **Auxiliary & subjunctive of *avoir***: `qu'il n'y aye` → `qu'il n'y ait`, `j'aye` → `j'aie` [22], `n'aye` → `n'aie` [8], `l'aye` → `l'aie` [2], `m'aye` → `m'aie`, `aye` → `aie` [22], `j'ay` → `j'ai`, `n'ay` → `n'ai`, `qu'ay-je` → `qu'ai-je`, `ay` → `ai`.
    - **Ancêtres**: `ayeul(e)(s)` → `aïeul(e)(s)` [19], `ayeux` → `aïeux` [7], `bisayeul` / `bifayeul` → `bisaïeul` [2].
    - **Asile, haie, craie, taie, futaie, claies, braies**: `asyle(s)` → `asile(s)` [10], `haye(s)` → `haie(s)` [7], `futaye(s)` → `futaie(s)` [5], `taye(s)` → `taie(s)` [7], `clayes` → `claies` [2], `brayes` → `braies` [2], `craye` → `craie` [1], `chênaye` → `chênaie` [1].
    - **Gaieté & gai**: `gayeté(s)` → `gaieté(s)` [25], `gayement` → `gaiement` [2], `gay` → `gai` [8].
    - **Days & time**: `lundy`, `mardy`, `mercredy`, `jeudy`, `vendredy`, `samedy` → `lundi`, `mardi`, `mercredi`, `jeudi`, `vendredi`, `samedi`, `midy` → `midi` [5].
    - **Demonstratives & Adverbs with `cy`**: `cy-après` / `cy après` → `ci-après` [11], `voicy` → `voici` [3], `celle-cy` → `celle-ci`, `gens-cy` → `gens-ci`.
    - **Monosyllables**: `loy(s)` → `loi(s)` [22], `foy` → `foi` [6], `moy` → `moi` [1].
    - **Words with `y` before consonants**: `hyrondelle(s)` → `hirondelle(s)` [4], `éclypse(s)` → `éclipse(s)` [14], `crystal` → `cristal` [5], `tymbale(s)` → `timbale(s)` [8], `cythare(s)` → `cithare(s)` [4], `chymérique` → `chimérique`, `acrostyche` → `acrostiche`, `phtysie` → `phtisie`, `hydeux` → `hideux`, `vrayment` → `vraiment`, `quoyque` → `quoique`, `aujourd'huy` → `aujourd'hui`, `doyvent` → `doivent`, `suye` → `suie` [4], `truyes` → `truies`, `enfuye` → `enfuie`, `buys` → `buis`, `luy` → `lui`, `courroyes` → `courroies` [5], `tygre(s)` → `tigre(s)` [7], `sphynx` → `sphinx`.
    - **Future verbs**: `rendray` → `rendrai`, `répandray` → `répandrai` [9], `réduiray` → `réduirai`, `traiteray` → `traiterai`.
    - **OCR artifact**: `rugissement du Lyon` → `rugissement du lion` [2].
    - **Strict Preservations**: legitimate French words (`yeux`, `pays`, `style`, `moyen`, `payer`, `envoyer`, `aboyer`, `croire`, `ayez`, `ayons`, etc.) and proper names (`Égypte`, `Babylone`, `Cyrus`, `Syrie`, `Chypre`, `Cyme`, and the city of `Lyon`).
  - **Missing Apostrophes & Elisions Normalization (118 replacements across 49 files)**:
    - **Single-Letter & Word Elisions with Space**: `d Orient` → `d'Orient`, `d airain` → `d'airain`, `d une` → `d'une`, `d un` → `d'un`, `d adam` → `d'Adam`, `d endroit` → `d'endroit`, `d elle` → `d'elle`, `d officier` → `d'Officier`, `d habits` → `d'habits`, `d autres` / `D autres` → `d'autres` / `D'autres`, `l animal` → `l'animal`, `l a mordu` → `l'a mordu`, `l évangile` → `l'Évangile`, `l homme` → `l'homme`, `l on` → `l'on`, `l entendre` → `l'entendre`, `l entendons` → `l'entendons`, `l absence` → `l'absence`, `l écriture` → `l'Écriture`, `l âme` → `l'âme`, `l équinoxe` → `l'équinoxe`, `l hébreu` / `L Hébreu` → `l'Hébreu` / `L'Hébreu`, `qu il` → `qu'il`, `qu elle` → `qu'elle`, `qu est` → `qu'est`, `c étaient` → `c'étaient`, `c est` / `C est` → `c'est` / `C'est`, `n y` → `n'y`, `n ait` → `n'ait`, `n en` → `n'en`, `s y` → `s'y`, `quelqu un` / `Quelqu un` → `quelqu'un` / `Quelqu'un`, `quelqu une` → `quelqu'une`, `jusque au` → `jusqu'au`, `jusque aux` → `jusqu'aux`, `lorsque il` → `lorsqu'il`, `lorsque elle` → `lorsqu'elle`, `que il` / `que\nil` → `qu'il`.
    - **Glued Tokens without Apostrophe or Space**: `dautres` / `Dautres` → `d'autres` / `D'autres`, `quil` → `qu'il`, `quils` → `qu'ils`, `quon` → `qu'on`, `dun` → `d'un`, `dune` → `d'une`, `sentendre` → `s'entendre`, `lopposition` → `l'opposition`, `noffrirez` → `n'offrirez`, `lchangeait` → `l'échangeait`, `si/que lon` → `si/que l'on`, `qu'on nen` → `qu'on n'en`.
    - **Whitespace / Newline after Apostrophe**: `l' honneur` → `l'honneur`, `l'\nabandonné` → `l'abandonné`.
    - **OCR Typographical Confusions**: `I's ont lu` → `Ils ont lu`, `si's, écoutez` → `fils, écoutez`, `lui-n.ême` → `lui-même`, `Y a-t il` → `Y a-t-il`, `ma's emporté` → `mais emporté`, `lorsque il nuit approche` → `lorsque la nuit approche`, `s aint Matthieu` → `saint Matthieu`, `s e prend` → `se prend`, `s ouvent` → `souvent`, `C'es -là` → `C'est-là`, `l'His toire` → `l'Histoire`.
    - **Strict Preservations**: Latin text fields (`latin`, `latin_quote`), Greek transliterations (`d' eè`, `d' enèsi`), Hebrew transcriptions (`Negedyali 'm iphôd`), and linguistic mentions of single letters (*« le D en T, et l'l en r »*, *« L est mis au lieu de R »*).
  - **Miscellaneous Archaic Spellings and Pattern Families (749 replacements across 579 files)**:
    - `éthimologies` family: `éthimologies` → `étymologies`, `éthimologie` → `étymologie`. Preserves Hebrew names `Séthim`, `Céthim`, `Céréthims`.
    - `monstrer` family: `monstrer`, `monstrèrent`, `monstrée(s)`, `monstrera`, `monstreront`, `monstrez`, `monstrant` → `montr...`. Preserves noun `monstre`.
    - `-ans` / `-ens` plurals (`croissans` family): `croissans` → `croissants`, `fréquens` → `fréquents`, `mécontens` → `mécontents`, `équivalens` → `équivalents`, `menaçans` → `menaçants`, `inconvéniens` → `inconvénients`, `permanens` → `permanents`, `fainéans` → `fainéants`, `turbulens` → `turbulents`, `glissans` → `glissants`, `coulans` → `coulants`, `indifférens` → `indifférents`, `apparens` → `apparents`, `commençans` → `commençants`, `contractans` → `contractants`, `étonnans` → `étonnants`, `suffocans` → `suffocants`, `défians` → `défiants`, `arpens` → `arpents`, `accens` → `accents`, `règlemens` → `règlements`, `entablemens` → `entablements`, `battemens` → `battements`, `relâchemens` → `relâchements`, `assoupissemens` → `assoupissements`, `abaissemens` → `abaissements`, `vomissemens` → `vomissements`, `applaudissemens` → `applaudissements`, `puiffans` → `puissants`, `mésdisans` → `médisants`, `judaïzans` → `judaïsants`, `impénitens` → `impénitents`, `déficiens` → `déficients`, `palpitans` → `palpitants`, `quadrans` → `quadrants`, `ingrédiens` → `ingrédients`, `opulens` → `opulents`, `insinuans` → `insinuants`, `communians` → `communiants`, `fermans` → `fermants`, `volans` → `volants`, `clairvoyans` → `clairvoyants`, `concurrens` → `concurrents`, `tempéramens` → `tempéraments`, `truchemens` → `truchements`, `rassasiemens` → `rassasiements`, `vos agens` → `vos agents`, `les continens` → `les continents`.
    - `brasselets` family (`ss` → `c`): `brasselet(s)` → `bracelet(s)`, `sausse(s)` → `sauce(s)`, `nasselle(s)` → `nacelle(s)`, `entrelassé(e)(s)` → `entrelacé(e)(s)`, `entrelassent` → `entrelacent`, `entrelassez` → `entrelacez`, `enlassez` → `enlacez`.
    - `Genéfe` OCR long-s: `Genéfe` → `Genèse`.
    - Contextual `par tout` → `partout` (243 replacements): converted before punctuation, `où`, `ailleurs`, and in verbal/adverbial constructions, while strictly preserving determiner phrases (`par tout le...`, `par tout un...`, `par tout ce...`, `par tout cet...`, `par tout ceci...`, `par tout cela...`, `par tout son...`, `par tout Israël`, `par tout homme`, `par tout l'...`).
    - `bled` family: `bled` → `blé`, `bleds` → `blés`.
    - `gozier` family (`z` → `s`): `gozier(s)` → `gosier(s)`, `magazin(s)` → `magasin(s)`, `cizeau(x)` → `ciseau(x)`, `cizelé(e)(s)` → `ciselé(e)(s)`, `hazard(s)` → `hasard(s)`, `hazarder...` → `hasarder...`, `nazeaux` → `naseaux`, `azile(s)` → `asile(s)`, `ozier(s)` → `osier(s)`, `bize` → `bise`, `sarrazin(s)` → `sarrasin(s)`.
    - `robbe` family (consonant normalization): `robbe(s)` → `robe(s)`, `abbattre...` → `abatt...`, `abbattement(s)` → `abattement(s)`, `abbat` → `abat`, `rabbaissaient` → `rabaissaient`, `abbaisser...` → `abaiss...`, `embaras...` → `embarras...`, `débarasser...` → `débarrasser...`, `nouriture(s)` → `nourriture(s)`, `nourir` → `nourrir`, `canelle(s)` → `cannelle(s)`, `houpe(s)` → `houppe(s)`, `hupe(s)` → `huppe(s)`, `échaper...` → `échapp...`, `bastonade(s)` → `bastonnade(s)`, `fanné(e)(s)` → `fané(e)(s)`, `floccon(s)` → `flocon(s)`, `agraffe(s)` → `agrafe(s)`, `applanir...` → `aplanir...`, `appaiser...` → `apaiser...`, `abboyeur` → `aboyeur`, `abbreuvera` → `abreuvera`, `abbréviateur` → `abréviateur`, `carrouge` → `carouge`.
  - **Expansion of Abbreviations: `l'Heb.` and `Chap.` (1,339 replacements across 1,193 files in 49 volumes)**:
    - **`l'Heb.` family $\rightarrow$ `l'Hébreu` / `L'Hébreu`**: expanded residual abbreviations `l'Heb.`, `l'Héb.`, `l'Hebr.`, `l'Hébr.`, `L'Heb.`, `L'Héb.`, `L'Hebr.`, `L'Hébr.` and OCR artifacts (`l'Héb.eu`, `l'Hébr u :`) to standard `l'Hébreu` / `L'Hébreu`. Also updated phrasal `texte Heb.` / `texte Héb.` → `texte hébreu` / `Texte Hébreu` and parenthetical `(Hébr. ...)` → `(Hébreu ...)`.
    - **`Chap.` family $\rightarrow$ `Chapitre` / `CHAPITRE`**:
      - `chapter_title`: expanded 500 instances of `CHAP. <num>` → `CHAPITRE <num>`, standardizing all chapter titles in the corpus.
      - Singular cross-references: `Chap.` / `chap.` / `Ch.` / `ch.` before numerals or ordinals → `Chapitre` / `chapitre` (`Chap. 11.` → `Chapitre 11.`, `chap. 10:23.` → `chapitre 10:23.`, `Ch. x.` → `Chapitre x.`, `ch. 13.` → `chapitre 13.`, `Ch. suivant` → `Chapitre suivant`, unpunctuated `Chap 37:14` → `Chapitre 37:14`).
      - Plural cross-references: after plural determiners (`les`, `ces`, `aux`, `des`, `deux`, `trois`, `plusieurs`) → `Chapitres` / `chapitres` (`les Chap.` → `les Chapitres`, `aux chap.` → `aux chapitres`); before plural adjectives (`Chap. précédents` → `Chapitres précédents`, `chap. suivants` → `chapitres suivants`).
      - Punctuation: stripped abbreviation dots before numbers, ordinals, words, and footnote calls; preserved sentence-ending periods at the end of clauses (`...de ce Chap.` → `...de ce Chapitre.`).
      - Strict preservations: verse numbers (`verses[].french`), Latin critical apparatus in footnotes, and the French noun `vers` (worms / verses) strictly preserved.
  - **Archaic `oi` $\rightarrow$ `ai` and Verb Endings (125 replacements across 119 files in 49 volumes)**:
    - **`connoître` / `paroître` family inflections and long-s variants**: `paroissez` → `paraissez`, `paroissoit` → `paraissait`, `paroissoient` → `paraissaient`, `paroissons` → `paraissons`, `paroissiez` → `paraissiez`, `paroissions` → `paraissions`, `paroitre` → `paraître`, `disparoitre` → `disparaître`, `disparoisse` / `disparoiffe` → `disparaisse`, `apparoissait` → `apparaissait`, `apparoissaient` / `apparoissoient` → `apparaissaient`, `comparoissaient` → `comparaissaient`, `paroiffent` / `paroißent` → `paraissent`, `connoiffance(s)` → `connaissance(s)`, `connoiffent` → `connaissent`, `connoiffant` → `connaissant`, `connoissoient` → `connaissaient`, `connoisseurs` → `connaisseurs`, `connoissables` → `connaissables`, `reconnoissiez` → `reconnaissiez`, `reconnoissions` → `reconnaissions`, `reconnoissoient` → `reconnaissaient`, `reconnoiffance(s)` → `reconnaissance(s)`, `reconnoiffait` → `reconnaissait`, `reconnoiffe` → `reconnaisse`, `reconnoissables` → `reconnaissables`, `méconnoissez` → `méconnaissez`, `méconnoîtront` → `méconnaîtront`, `reconnoi-tront` → `reconnaîtront`.
    - **`foible` / `affoiblir` family**: `affoiblissent` / `affoiblifsent` → `affaiblissent`, `affoiblira` → `affaiblira`, `affoiblirai` → `affaiblirai`, `affoibliffe` → `affaiblisse`, `affoiblissait` → `affaiblissait`, `affoibliraient` → `affaibliraient`, `assoiblis` → `affaiblis`.
    - **`roide` / `roidir` family**: `roidissez` → `raidissez`, `roidir` → `raidir`, `roidi` → `raidi`, `Ce Roid'Égypte` → `Ce Roi d'Égypte`.
    - **`monnoie` family**: `monnoie(s)` → `monnaie(s)`.
    - **`Françoise` / `Narbonnoise` adjectives**: `Françoise(s)` / `françoise(s)` → `Française(s)` / `française(s)`, `Narbonnoise` → `Narbonnaise`. Preserves proper noun `François` (27 occurrences like *François de Vitoria*).
    - **Archaic `-oit` / `-oient` endings and contractions**: `duisoit` → `duisait`, `obsedoit` → `obsédait`, `laveroît` → `laverait`, `dérivoit` / `dévivoit` → `dérivait`, `disoit` → `disait`, `lisoient` / `liloit` → `lisaient` / `lisait`, `blanchissoit` → `blanchissait`, `siffloient` → `sifflaient`, `assiégeoint` → `assiégeaient`, `prenoiens` → `prenaient`, `descendroiens` → `descendraient`, `étoiens` → `étaient`, `croistrons` → `croîtront`, `estoit` → `était` (`c'estoit` → `c'était`, `N'estoit-ce` → `N'était-ce`), `empêcheroitelle` → `empêcherait-elle`, `dequoi` → `de quoi`, `veloppoit` → `enveloppait`, `moïen` → `moyen`, `cicoigne` → `cigogne`, `refectoire` / `resectoire` → `réfectoire`.
    - **Classical plural past participles in `-ez` vs 2nd person plural verbs**:
      - Pure participles & adjectives (103 words): `passionnez` → `passionnés`, `ensanglantez` → `ensanglantés`, `entortillez` → `entortillés`, `désignez` → `désignés`, `distinguez` → `distingués`, `efféminez` → `efféminés`, `enchaînez` → `enchaînés`, `enfermez` → `enfermés`, `habituez` → `habitués`, `intéressez` → `intéressés`, `échappez` → `échappés`, etc.
      - Archaic nouns in `-ez` (10 words): `accez` → `accès`, `comoditez` → `commodités`, `procez` → `procès`, `damnez` → `damnés`, `incensez` → `insensés`, `succcez` → `succès`, etc.
      - Contextual participles (guarded against verbs & imperatives, 155 occurrences): `allez` → `allés` (with être/s'en), `retirez` → `retirés` (with être/se sont), `tirez` → `tirés` (with être), `tuez` → `tués` (after number + de), `rassasiez` → `rassasiés`, `éclairez` → `éclairés`, `considérez` → `considérés`, `armez` → `armés` (gens/hommes armez), `sans souliez` → `sans souliers`, `mêlez` → `mêlés`, `engraissez` → `engraissés`, `percez` → `percés`, `possédez` → `possédés` (deux possédez), `éloignez`/`assemblez` → `éloignés`/`assemblés` (peuples), `fondez` → `fondés` (except `Fondez votre or`), `déchirez` → `déchirés` (after habits/vêtements), `abaissez` → `abaissés`, `avancez` → `avancés`, `appuyez` → `appuyés`, `sauvez` → `sauvés`, `élevez` → `élevés`, plus 28 editorial chapter summary participles (`Songes expliqués`, `chargés de présents`, `Lévites souillés`, etc.). All imperatives and 2nd person plural forms (`Sauvez-moi`, `Élevez vos mains`, `Déchirez vos cœurs`, `Abaissez vos mains`, `avancez hardiment`, `ne vous appuyez point`, `Allez en paix`, `Retirez votre main`, `Tirez votre épée`) strictly preserved.
    - **Strict preservations**: all genuine modern French `oi` words (`froid`, `froide`, `parois`, `bois`, `roi`, `loi`, `reçoit`, `conçoit`, etc.), proper nouns (`Paros`, `François`, `Mendez`, `Sánchez`, `Séez`, `Tellez`), and Hebrew terms (`taschbez`).
  - **Hyphen Normalization in Latin Lemmas and French Translations (73 replacements across 67 pages in 49 volumes)**:
    - **Latin Lemmas (`clean_latin_quote`)**: fixed 27 broken Latin words (`AN-NORUM` / `ANNO-RUM` → `ANNORUM`, `CECIDERIT-QUE` → `CECIDERITQUE`, `CIBA-RIA` → `CIBARIA`, `MONTE-LIBANO` → `MONTE LIBANO`, `BETHLE-HEM` → `BETHLEHEM`, `PLAUS-TRUM` → `PLAUSTRUM`, `EXCELSO-RUM` → `EXCELSORUM`, `AQUÆ-DUCTUM` → `AQUÆDUCTUM`, `AN-NULUM` → `ANNULUM`, `DI-NUMERAVERUNT` → `DINUMERAVERUNT`, `AUXILIUM-TUUM` → `AUXILIUM TUUM`, `LE-GEM` → `LEGEM`, `ANI-MA` → `ANIMA`, `PEC-CATORUM` → `PECCATORUM`, `IL-LIUS` → `ILLIUS`, `VISITA-TIO` / `VISI-TATIO` → `VISITATIO`, `SUAVE-OLENTEM` → `SUAVEOLENTEM`, `VASTA-TORES` → `VASTATORES`, `AU-SITIDIS` → `AUSITIDIS`, `ULTO-RI` → `ULTORI`, `VOVE-RUNT` → `VOVERUNT`, `NE-QUE` → `NEQUE`, `DESER-TUROS` → `DESERTUROS`, `IMMUNDO-RUM` → `IMMUNDORUM`, `ADIMPLE-TUR` → `ADIMPLETUR`), cleaned spaced hyphens (`SAVE - KARIATHAIM` → `SAVE-KARIATHAIM`, `SCRIBAM PRINCIPEM MILITUM, - QUI` → `SCRIBAM PRINCIPEM MILITUM, QUI`), and resolved interleaved multi-column OCR corruption on Daniel 10:16 (`32_daniel/page_0188.json`).
    - **French Translations (`modernize_text`)**: fixed broken words (`au-jourd'hui` → `aujourd'hui`, `Héré-mie` → `Jérémie`), erroneous hyphens (`C'est-pourquoi` → `C'est pourquoi`, `Abel-maison-de-Maacha` → `Abel-maison de Maacha`, `Du-fondement` → `Du fondement`, `assez-cruel` → `assez cruel`, `donnez-point` → `donnez point`, `des-hommes` → `des hommes`, `est-dans` → `est dans`, `la-clef` → `la clef`, `mesura-tout` → `mesura tout`, `faux-Prophètes` → `faux Prophètes`, `grand-Champ` → `grand Champ`, `point-là` → `point là`, `c'est-à dire` → `c'est-à-dire`), and joined spaced hyphens (`Grand - Pontife` → `Grand-Pontife`, `grand - Prêtre` → `grand-Prêtre`, `Laissez - les` → `Laissez-les`).
    - **Strict Preservations**: Trailing page-seam hyphens (`NOC-`, `Nem-`, `re-`, `bé-`, etc.), valid French pronominal enclitics and compounds (`souvenez-vous`, `lui-même`, `au-dessus`), Biblical proper names (`BETH-HORON`, `OBED-EDOM`), and Latin numerals (`TRIGINTA-DUOS`, `OCTAVO-DECIMO`) strictly preserved.
  - **Commentary and Footnote Structural Cleanups (Oct 30, 2026)**:
    - **Accidental Verses in Commentary (13 items across 11 files)**:
      - Transcriptions occasionally duplicated verse text into a commentary block with a lowercase `latin_quote` (>90% lowercase, matching the verse text) and empty `french_commentary`.
      - Resolved by removing the phantom commentary entry and renumbering remaining `commentary_id`s 1..$n$ (`28_jeremie/page_0264.json`, `page_0266.json`, `page_0272.json`, `page_0352.json`, `page_0408.json`, `page_0448.json`, `page_0496.json`, `page_0630.json`, `31_ezechiel/page_0482.json`, `21a_psaumes/page_0854.json`, `21b_psaumes/page_0444.json`).
    - **Continuation Commentary with Erroneous Verse Lemmas (17 items across 16 files)**:
      - **Spurious Verse Copy in Continuations (15 items)**: Continuation commentary blocks across page breaks where the previous verse text was erroneously copied into `latin_quote` and `french_translation`. Cleared `latin_quote` and `french_translation` to `null` and carried forward the active `verse_ref` from the preceding page (`28_jeremie` and `21a_psaumes`).
      - **Embedded ALL-CAPS Lemmas in Commentary (2 items)**: Commentary blocks where genuine printed ALL-CAPS Latin lemmas and French translations were trapped at the beginning of `french_commentary`. Extracted the lemma into `latin_quote`, the translation into `french_translation`, and cleaned `french_commentary` (`21c_psaumes/page_0056.json`, `page_0204.json`).
    - **Displaced Footnotes Trapped in Commentary (43 items across 26 files)**:
      - **Empty Commentary Blocks (23 items across 15 files)**: Commentary blocks with `null` `latin_quote` and `french_translation` that actually contained footnote text (starting with footnote markers `(a)`, `(b)`, etc., or Hebrew/Greek citations corresponding to footnote callouts `^{(a)}`, `^{(b)}` in the page text). Resolved across `28_jeremie` (14 files) and `29_lamentations` (`page_0045.json`): extracted each footnote into `footnotes` with stripped markers and tags, deleted the displaced commentary entries, and renumbered remaining `commentary_id`s 1..$n$. On `28_jeremie/page_0291.json`, merged trailing commentary text `L'Hébreu : ^{(d)}` into the preceding commentary note before extracting footnotes `(a)` through `(d)`.
      - **Non-Empty Commentary Blocks (20 items across 11 files)**: Footnotes accidentally appended to the end of genuine commentary paragraphs or pasted into the `french_commentary` field of an un-commented lemma block across page turns. Resolved across `28_jeremie` (8 files: `page_0245`, `page_0256`, `page_0299`, `page_0404`, `page_0413`, `page_0519`, `page_0609`, `page_0646`) and `29_lamentations` (3 files: `page_0037`, `page_0044`, `page_0053`): stripped trailing footnote text from commentary (or reset `french_commentary: null` where appropriate), added the extracted footnotes to the page's `footnotes` array with computed tags, sorted by marker, and removed empty displaced blocks (e.g. `28_jeremie/page_0646.json` cid 5) with renumbering.
    - **Inverted Verse Translation and Commentary Block (`28_jeremie/page_0580.json`)**:
      - Transcriber inverted verse and commentary: `verses[0]["french"]` had been mistakenly filled with the commentary translation of Note 4 (`Tyr, et Sidon seront détruites...`), while the true French translation of verse 4 was placed into `commentary[0]` with full Latin verse in `latin_quote` and French verse in `french_commentary`.
      - Resolved by restoring genuine French verse 4 into `verses[0]["french"]`, removing the duplicate `commentary[0]`, realigning preceding notes 1 and 2 to Verse 3 (`EJUS.` continuation from p. 579, and `NON RESPEXERUNT...`) with extracted translations, renumbering remaining notes 1..3, restoring 4 missing footnotes from the scan (`(a)` Hebrew, `(b)` Greek Septuagint, `(c)` `Isaïe 23:4.`, `(d)` `Joël 3:4. & Ézéchiel 28:24.`), and correcting long-s OCR error `sa sille` → `sa fille`.
      - Rule for future volumes: If `commentary[0]` holds full-verse Latin/French while `verses[0]["french"]` duplicates a commentary translation below, check the scan for inverted verse-commentary blocks.
    - **Page Seam Hyphenation & Compound Normalization (Oct 30, 2026)**:
      - **Expanded Compound Recognition in `scripts/calmet.py` (`COMPOUND`)**:
        - `COMPOUND` identifies words that follow a hyphen in a genuine compound word broken across a page break (preventing them from being spliced and losing their hyphen on export).
        - Added: `être` (from `peut-être`, 5 volumes: *02_exode 547*, *05_deuteronome 457*, *16_nehemie 97*, *19_esther 171*, *31_ezechiel 498*), `dessus` / `dessous` (`au-dessus`, `par-dessus`, `au-dessous`, `par-dessous`), `devant` / `après` (`ci-devant`, `ci-après`), `delà` / `deçà` (`au-delà`, `au-deçà`), `dedans` / `dehors` (`par-dedans`).
        - Enhanced `infer_join` and `join_seam` in `calmet.py` to support italic compound turns (`_consolez-_` ‖ `_vous_` joins cleanly without doubling underscores).
      - **Stripped Superfluous Leading Hyphens on Continuation Pages (12 items across 11 files)**:
        - Continuation pages must transcribe the text as printed on the physical page (without an artificial leading hyphen).
        - Fixed 3 broken-word bugs where the leading hyphen corrupted single words into spurious hyphenated forms: `12_4_rois/page_0035.json` (`-breu` → `breu`, fixing `Ni l'Hé-breu` → `Ni l'Hébreu`), `12_4_rois/page_0137.json` (`-vaient` → `vaient`, fixing `poursui-vaient` → `poursuivaient`), `21b_psaumes/page_0440.json` (`-lui` → `lui`, fixing `ce-lui` → `celui`).
        - Cleaned redundant leading hyphens in compounds across page breaks: `07_juges/page_0249.json` (`-même` → `même`), `21b_psaumes/page_0609.json` (`- même` → `même`), `24_cantique/page_0086.json` & `page_0087.json` (`par.` → `par-`, `-dedans` → `dedans`), `26_ecclesiastique/page_0267.json` (`-là` → `là`), `26_ecclesiastique/page_0327.json` (`-t-il` → `t-il`), `26_ecclesiastique/page_0584.json` (`_-vous` → `_vous`), `27_isaie/page_0617.json` (`-vous` → `vous`), `27_isaie/page_0821.json` & `page_0822.json` (`_Conduirai-_…` → `_Conduirai-_`, `_-je` → `_je`), `28_jeremie/page_0304.json` (`-on` → `on`).
      - Unit tests added to `scripts/tests/test_turns.py` (`test_compound_joins`). All 216 tests pass.
    - **Footnote Marker Standardization & Schema Cleanup (Oct 30, 2026)**:
      - Enhanced `scripts/fix_markers.py` (`fix_footnotes()`) to mechanically resolve and standardize all footnote markers across the corpus:
        - Restored missing markers `(a)`, `(b)`, etc., across 1,364 notes (primarily in `28_jeremie`, `29_lamentations`, `45_1_maccabees`, and `27_isaie`) from alternative OCR keys (`footnote_marker`, `footnote_symbol`, `footnote_ref`, `ref`, `reference`, `footnote_id`, `id`), leading text prefixes (`^{(a)}`, `(a)`), page call alignment, or page index.
        - Normalized non-canonical markers (`a` → `(a)`, `^{(a)}` → `(a)`, `*(c)` → `(c)`, `(A)` → `(a)`).
        - Stripped redundant leading marker prefixes from footnote `text` where duplicated from the marker.
        - Converted `footnote_text` fields to canonical `text`.
        - Removed 1,819 obsolete LLM/OCR temporary keys (`footnote_id`, `footnote_ref`, `footnote_marker`, `footnote_symbol`, `footnote_number`, `footnote_reference`, `reference_marker`, `reference_symbol`, `ref`, `reference`, `id`, `fn_number`, `reference_id`, etc.) to enforce uniform `{marker, text, tags}` schema.
        - Merged 11 unlabelled split continuation notes back into their parent footnotes.
        - Removed empty footnote dict `{}` on `01_genese/page_0725.json`.
        - Converted 39 bare calls in French commentary to `^{(x)}` now that footnote markers are recognized.
        - Enforced strict canonical alphabetical sorting of footnotes by marker across all pages (resolving multi-column OCR reading inversions across 32 pages).
        - Added unit tests in `scripts/tests/test_fix_markers.py`. All 217 tests pass. Corresponds to 0 missing or non-canonical footnote markers, and 0 out-of-order footnote arrays across all 2,160 pages.
    - **Spurious Running Heads Cleared from `chapter_title` (Oct 30, 2026)**:
      - Cleared 702 spurious running heads (`chapter_title: null`) captured by OCR from physical margin headers on continuation pages mid-chapter (e.g. `SUR JEREMIE. CHAPITRE XLIX.`, `SUR JOSUE. CHAPITRE XV.`, `COMMENTAIRE.`, repeated `CHAPITRE VIII.`).
      - Normalized 13 Psalm opening titles from `SUR LE PSEAUME <num>` / `SUR LE PSAUME <num>` to canonical `PSEAUME <num>` on their true opening pages.
      - Integrated the rule into `scripts/tidy_fields.py` to ensure future volume processing preserves only true chapter opening titles (where `chapter_summary`, `verse_number == 1/0`, `chapter_number`, or `chapter_intro` are present).
      - Eliminated over 500 false-positive `empty_summary` warnings across the corpus in `audit_integrity.py`. All 217 unit tests pass.
    - **100% Wrapped Translation Underscores Stripped (Oct 30, 2026)**:
      - Stripped redundant outer underscores from all 20 fully wrapped `french_translation` fields across the corpus (as the website styles commentary translations in italic by default).
      - Preserved 14 partial internal italics (e.g. `_(ou les femmes esclaves)_`, `_(sur Sennachérib)_`) denoting textual variants and glosses.
      - Integrated `WRAPPED_TRANSLATION` matching into `scripts/tidy_fields.py` to replace indiscriminate `strip_us` and maintain this distinction automatically. All 217 unit tests pass.
    - **Spelling Modernizations: `par tout` $\rightarrow$ `partout` & `Possédez` Participles (Oct 30, 2026)**:
      - Refined contextual `par tout` $\rightarrow$ `partout` in `modernize_inplace.py` to resolve adverbial constructions preceding elided nouns (`l'Évangile`, `l'effroi`, `l'harmonie`, `l'ordre des temps`), direct objects (`le ménage`, `le désintéressement`, `le feu`), possessive constructions (`son injustice`, `son horreur`, `son attachement`), and indefinite phrases (`un pain entier`, `un et`). Applied across 13 pages, while strictly preserving prepositional determiner phrases (`par tout le monde`, `par tout le peuple`, `par tout ce récit`, `par tout cela`, `par tout Israël`, `par tout son Royaume`).
      - Modernized archaic `-ez` spellings of `Possédez` / `possédez` when functioning as past participles or plural nouns (*« hommes ou possédés par leur affection »*, *« Possédés par leur affection »*, *« de vrais possédés »*, *« les possédés aux dépens »*) in Sagesse 14:21 and Matthieu 17:14 / 8:34. Preserved true 2nd-person plural verbs (*« Possédez la terre »*, *« vous possédez »*). All 217 unit tests pass.
    - **OCR Long-S Normalization: `ferai` $\rightarrow$ `serai` & Companion *Être* Forms (Oct 30, 2026)**:
      - Resolved long-s (`ſ`) confusion where future and conditional forms of *être* (*ſerai*, *ſeront*, *ſerez*, *ſeroit*, *ſeroient*, *ſuis*) were scanned as forms of *faire* (*ferai*, *feront*, *ferez*, *ferait*, *feraient*, *fuis*).
      - Applied 41 verified replacements across 41 pages in the Old Testament and Matthieu:
        - `ferai` $\rightarrow$ `serai` (19 instances: covenant formulas *« je serai leur Dieu »*, *« moi je serai votre Dieu »*, *« je ne serai plus votre Dieu »*; predicatives *« ne vous serai-je pas favorable »*, *« Je serai avec vous »*, *« je serai bien aise »*, *« je serai agréable »*, *« je serai fidèle »*, *« je serai touché »*, *« serai-je votre Prince »*, *« je serai dans votre bouche »*, *« je serai comme... »*, *« je serai ta mort... ta ruine »*, *« pendant que je serai assise »*).
        - `feront` $\rightarrow$ `seront` (15 instances: *« seront circoncis »*, *« seront au Seigneur »*, covenant *« ils seront mon peuple »*, *« seront savants »*, *« ne lui seront point agréables »*, *« seront rassemblés »*, *« seront enterrés »*, *« ne seront point vaines / pleurés »*, *« en seront restés / chassés »*, *« seront desséchés / dispersés / enveloppées »*, *« nous seront toujours aussi chers »*, *« seront appelés »*, *« où les Élus seront assis, et feront bonne chère »*, *« seront comblés de biens »*).
        - `ferez` $\rightarrow$ `serez` (4 instances: *« Vous ne serez point obligé »*, covenant *« vous serez mon peuple »*, *« Vous serez aplanie »*).
        - `ferait`/`feraient` $\rightarrow$ `serait`/`seraient` (2 instances: *« l'armée serait morte de soif »*, *« ceux qui seraient avec lui »*).
        - `fuis` $\rightarrow$ `suis` (1 instance: *« de ce que je suis tombée »*).
      - Strictly preserved legitimate *faire* idioms (*« je ferai avec vous une alliance »*, *« je ferai alliance »*, *« ils feront bonne chère »*, *« feront des présents »*, *« ils feront la guerre »*, *« ce que je ferai »*, *« ce qui ferait tort »*).
      - Codified regexes into `scripts/modernize_inplace.py` (section 5h.3b) and added comprehensive unit tests in `scripts/tests/test_modernize_inplace.py`. All 218 unit tests pass.
    - **Page Seam Broken Word Modernization & OCR Normalization (Oct 30, 2026)**:
      - Audited all 1,983 hyphenated word breaks split across page seams (`prefix-` at page foot and `suffix` at page head) in commentary, translations, and verses across the entire corpus.
      - Modernized archaic French spellings and accents across the break while strictly maintaining the hyphen:
        - **Verb endings**: `de-` + `voient`/`voit` $\rightarrow$ `de-` + `vaient`/`vait`, `pou-` + `voit` $\rightarrow$ `pou-` + `vait`, `a-` + `voient`/`voit` $\rightarrow$ `a-` + `vaient`/`vait`, `é-` + `toit` $\rightarrow$ `é-` + `tait`, `vi-` + `voient` $\rightarrow$ `vi-` + `vaient`, `fai-` + `soient` $\rightarrow$ `fai-` + `saient`, `por-` + `toit` $\rightarrow$ `por-` + `tait`, `en-` + `gagerent` $\rightarrow$ `en-` + `gagèrent`.
        - **Plural nouns and participles in `-ens`/`-ans`/`-ez`**: `pa-` + `rens` $\rightarrow$ `pa-` + `rents`, `comman-` + `demens` $\rightarrow$ `comman-` + `dements`, `commen-` + `cemens` $\rightarrow$ `commen-` + `cements`, `châti-` + `mens` $\rightarrow$ `châti-` + `ments`, `descen-` + `dans` $\rightarrow$ `descen-` + `dants`, `pen-` + `chans` $\rightarrow$ `pen-` + `chants`, `précé-` + `dens` $\rightarrow$ `précé-` + `dents`, `sui-` + `vans` $\rightarrow$ `sui-` + `vants`, `mé-` + `chans` $\rightarrow$ `mé-` + `chants`, `qua-` + `litez` $\rightarrow$ `qua-` + `lités`, `impure-` + `tez` $\rightarrow$ `impure-` + `tés`.
        - **Archaic spellings & accents**: `Pro-` + `phétes` $\rightarrow$ `Pro-` + `phètes`, `Inter-` + `prêtes` $\rightarrow$ `Inter-` + `prètes`, `cé-` + `lébre` $\rightarrow$ `cé-` + `lèbre`, `Heur-` + `lez` $\rightarrow$ `Hur-` + `lez`, `en-` + `voyera` $\rightarrow$ `en-` + `verra`, `Sab-` + `bath` $\rightarrow$ `Sab-` + `bat`, `Vul-` + `gâte` $\rightarrow$ `Vul-` + `gate`, `Is-` + `raëlites` $\rightarrow$ `Is-` + `raélites`, initial `E-` $\rightarrow$ `É-` in `Égypte`, `Écriture`, `Éphraïm`, `Élam`, `Évangéliste`, `Évitez`.
        - **Compound noun normalization**: normalized unhyphenated `basse fosse` $\rightarrow$ `basse-fosse` across verses, translations, and commentary.
      - **Long-S (`f` $\rightarrow$ `s`) conversions across seam breaks**:
        - `fem-` + `blables` $\rightarrow$ `sem-` + `blables` (*semblables*), `four-` + `ce` $\rightarrow$ `sour-` + `ce` (*source*), `fou-` + `vent` $\rightarrow$ `sou-` + `vent` (*souvent*), `fou-` + `veraine` $\rightarrow$ `sou-` + `veraine` (*souveraine*), `def-` + `cription` $\rightarrow$ `des-` + `cription` (*description*), `def-` + `cendit` $\rightarrow$ `des-` + `cendit` (*descendit*), `foli-` + `tude` $\rightarrow$ `soli-` + `tude` (*solitude*), `ef-` + `prit` $\rightarrow$ `es-` + `prit` (*esprit*), `Jéru-` + `falem` $\rightarrow$ `Jéru-` + `salem` (*Jérusalem*), `ap-` + `plaudiffemens` $\rightarrow$ `ap-` + `plaudissements` (*applaudissements*).
      - **OCR seam defect corrections**:
        - `pieu-` + `reuses` $\rightarrow$ `pleu-` + `reuses` (*pleureuses*), `en-` + `voyez` $\rightarrow$ `en-` + `voya` (*envoya*), `con-` + `elaient` $\rightarrow$ `con-` + `cluent` (*concluent*), `mon-` + `sagne` $\rightarrow$ `mon-` + `tagne` (*montagne*), `Inter-` + `prêtres` $\rightarrow$ `Inter-` + `prètes` (*Interprètes*).
      - Applied across 89 files corpus-wide, preserving page break boundaries and hyphenation.
    - **Removal of Spurious Print Headers `COMMENTAIRE.` and `COMMENTAIRE LITTÉRAL` (Oct 30, 2026)**:
      - Audited all normalized files across the corpus for misplaced running column/page headers of `COMMENTAIRE.` / `COMMENTAIRE LITTÉRAL`:
        - `28_jeremie/page_0250.json` (commentary[0]): cleared `latin_quote: "COMMENTAIRE."` $\rightarrow$ `null` on verse 4 continuation from page 249.
        - `17_tobie/page_0127.json` (commentary[0]): cleared `latin_quote: "COMMENTAIRE."` $\rightarrow$ `null` on verse 1 continuation from page 126.
        - `21b_psaumes/page_0509.json`: cleared spurious `chapter_title: "COMMENTAIRE."` $\rightarrow$ `null` on Psalm 85 $\rightarrow$ 86 continuation.
        - `21a_psaumes/page_0527.json` (commentary[0]): stripped duplicated verse 12 header text and `COMMENTAIRE.\n` captured in `french_commentary` so the page seamlessly continues from page 526 (*« ...en particulier dans les Livres prophétiques... »*).
        - `21b_psaumes/page_0595.json`: cleared spurious running header `chapter_title: "COMMENTAIRE LITTÉRAL"` $\rightarrow$ `null` on Psalm 94 continuation.
  - **Integrated Execution**:
    - All of these rules are now built directly into `modernize_inplace.py` (`modernize_text()`), tested in `tests/test_modernize_inplace.py`, and run automatically whenever `python3 modernize_inplace.py <vol>` is called on new books.
    - `modernize.py` has also been hardened: `reçoit`, `conçoit`, `aperçoit`, `apperçoit`, and `déçoit` are explicitly guarded in `replace_oit()` to prevent present-tense forms of *-cevoir* from being mutated to *-çait*.

## 13. Current status & remaining work (as of Oct 30, 2026)

- **Structural Normalization**: 100% complete across all 46 Old Testament books (`01_genese` through
  `46_2_maccabees`) with **0 page gaps** in `audit_integrity.py`.
- **Commentary & Footnote Structural Cleanups**: duplicate verse commentary entries removed, inverted verse-commentary blocks corrected, continuation lemmas cleared/re-referenced, embedded ALL-CAPS lemmas extracted, 47 displaced/missing footnotes restored to `footnotes` arrays, and page-seam compound hyphens normalized across the corpus.
- **Bible References in Commentary**: 100% complete across all 46 Old Testament books with **0 items to review**.
- **French Modernization, Typography & Footnote Calls**: 100% complete across all 46 Old Testament books (`modernize_inplace.py all`), including `Jésus-Christ` expansion, footnote punctuation repositioning, space after punctuation, and `S.` expansion.
- **Footnotes Pipeline (`footnotes.py`)**:
  - `01_genese` through `21a_psaumes`: completed and held notes indexed in `docs/footnotes/held.json`.
  - `21b_psaumes` through `26_ecclesiastique`: local checks run and applied into `normalized/` (over 1,440
    footnote updates applied across these volumes). Greek Hunspell queries cached in
    `cache/refs/grc_hunspell_asked.json` for fast replay.
  - `27_isaie` through `46_2_maccabees`: ready to run with `uv run --no-project --with pillow python footnotes.py run <vol> --local`
    and `python3 footnotes.py apply <vol>`.
- **Remaining Tasks before New Testament**:
  - Run and apply local footnotes for remaining OT volumes (`27_isaie` through `46_2_maccabees`).
  - Review queue audit resolution with the editor (`review_web.py`).
  - Check with user on source directory for seeding the New Testament (`47_matthieu` onward).
  - Website adjustments for Psalms (`src/routes/[book]/[id]/+page.server.ts` chapter bounds & verse 0
    title display) and deployment.
