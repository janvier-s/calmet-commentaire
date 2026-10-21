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
  `chapter_check.json`, `manual_issues.json` for issues the user reports by hand);
  `docs/footnotes/<vol>.json` (the footnote report of each volume) and
  `docs/footnotes/held.json` (every footnote still held, §10).
- `scripts/cache/` is not in git (`.gitignore`): Claude's caches and the downloaded sources
  in `cache/refs/` (§10) live only on this disk.
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
14. **The user reviews** in `review_editor.py` (§7). Commit `data/` when they say.
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

## 13. Current status & remaining work (as of Oct 21, 2026)

- **Structural Normalization**: 100% complete across all 46 Old Testament books (`01_genese` through
  `46_2_maccabees`) with **0 page gaps** in `audit_integrity.py`.
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
  - Review queue audit resolution with the editor (`review_editor.py`).
  - Check with user on source directory for seeding the New Testament (`47_matthieu` onward).
  - Website adjustments for Psalms (`src/routes/[book]/[id]/+page.server.ts` chapter bounds & verse 0
    title display) and deployment.
