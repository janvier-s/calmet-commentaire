# Spec: bringing a new volume to the state of the Old Testament

Written for Claude (and anyone else) picking up the Calmet work on a new volume: the New
Testament (`47_matthieu` onward) and 3–4 Maccabees. Volumes 01_genese … 21a_psaumes were taken
through everything below between Oct 9 and Oct 14, 2026, and the rest of the Old Testament
through most of it by Oct 30 (§13 says what is left). This is what was done to them, in the
order to do it, with the decisions behind it. `README.md` is the short command list; this is
the full spec.

## 1. Ground rules (from the user — don't relitigate)

- **The page JSONs stay as close to the printed page as possible in content, not in format.**
  Never reorder or renumber the notes or verses to match the Vulgate or the verse order (that
  happens only in the export; a script that edited refs from the Vulgate wholesale was written
  once and had to be reverted). But Calmet's own mistakes (a wrong reference, a misremembered
  book) are fixed when the context settles them, without any mark.
- **Never OCR the scans.** If text is missing, say so and list the pages; the user can supply
  the original data.
- **Run LLM jobs in the foreground** (`llm_modernize.py`, `seam_check.py`), never in the
  background.
- **Stay on the Calmet modernization**: no detours into the Lectio booklet.
- **Mechanical fixes may be applied; judgement calls are queued.** Anything that needs the scan
  goes into the review queue for the user, with a clear message, not into the data.
- **Commit and push as work is done**; deploy only when asked. `data/` (normalized pages) and
  `scripts/` are in this one repository (`calmet-commentaire`); the website is a separate one.
- Before a bulk change, run with `--dry-run`, look at a sample, then apply. Report counts and
  anything left for the user.

## 2. Where things are

- Scripts: `scripts/` (run from there with `python3`; the editors need
  `uv run --no-project --with pillow python …`). Every path is in `paths.py`, which still calls
  the repository root `STUDIUM`.
- Data: `data/<volume>/`
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
- Reports: `docs/` (`review_queue.json`, `seam_check.json`, `psalms_check.json`,
  `chapter_check.json`);
  `docs/footnotes/<vol>.json` (the footnote report of each volume) and
  `docs/footnotes/held.json` (every footnote still held, §10).
- `scripts/cache/` is not in git (`.gitignore`): Claude's caches and the downloaded sources
  in `cache/refs/` (§10) live only on this disk.
- Review progress: `data/<book>/review.json` (statuses, false positives, page to-dos). False positives
  use resilient signature matching (`review_store.fp_sig`, `FalsePositives`), so they survive text modifications
  (punctuation, spelling modernization, whitespace adjustments) across script runs and re-audits without reopening.

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
4. `python3 modernize_inplace.py <vol>`: rule-based modernization of the archaic spellings the
   LLM pass leaves, in every French field: each page gets `clean_mechanical.py`'s rules, then
   its own (§12). `--dry-run` first.
5. `python3 fix_typography.py <vol>`: ſ → s, `&c.` → etc., `&` → et.
6. `python3 normalize_refs.py <key>`: verse numbers and refs to ints, no numbers in the verse
   text, single capital on verse 1. One-off mislabels go in its `MANUAL` dict.
   *Known flaw:* it fills a missing ref with the previous one, even across a chapter start,
   so the first note of a chapter can carry the last ref of the previous one (Lev 23:1 → 27).
   The audit (step 13) finds these; the user fixes the ref in the editor.
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
16. `python3 chapter_refs.py <vol>`, then with `--apply`: references naming no book
    ("Chapitre XXXI. 3." → "chapitre 31:3"). Then `python3 modernize_refs.py <vol>`, then with
    `--apply` (twice: a first pass can open a second), then `python3 roman_refs.py <vol>` and
    `--apply` (psalms and chapters named alone, "ci-devant XVII. 6.", verses the scan read
    "I."/"II." for 1/11), then chapter_refs and modernize_refs once more: Bible references left in the old
    form (Roman chapters, abbreviations) written out in the commentary and the notes (§11).
    After the footnotes, which write out most of the notes' references themselves.
    Then `python3 ref_context.py <vol>`: every reference checked against its context (the
    quotation, or Claude); logged in docs/ref_context.json, so a rerun only sends what changed.
    What it finds wrong or unsure is in docs/ref_context_review.json.
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
  (the bad refs from step 6's flaw);
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

From the Old Testament volumes; look for the same in new volumes:

- verse numbers and refs as strings, Roman numerals, `℣.`, `"II"` meaning 11 or 2;
- refs carried across a chapter start (step 6), wrong refs at the top of a chapter;
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
  footnote citations (e.g. `(a) [UNCERTAIN HEBREW]`), missing from the page's `footnotes` list,
  or footnotes appended to the end of a genuine comment;
- verse and commentary swapped: `commentary[0]` holding the whole verse while
  `verses[0].french` duplicates a translation from a note below. Check the scan (Jérémie p. 580);
- a continuation page starting with an artificial hyphen (`-breu`, `-vaient`): the page starts
  with the text as printed;
- `COMMENTAIRE.` / `COMMENTAIRE LITTÉRAL` read as a `latin_quote` or a `chapter_title`.

When a verse turned up as commentary it was removed and the remaining `commentary_id`s
renumbered 1..n; a continuation block's copied lemma was cleared to `null`; a trapped ALL-CAPS
lemma was moved into `latin_quote` / `french_translation`.

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
  `data/<vol>/reports/modernize_refs_review.tsv` instead of being changed; a bare chapter in a list after
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
- The audit (step 13) queues every starred reference, in the commentary or the notes, and the
  `None` entries of `MANUAL` as `guessed_ref`, for the user to check on the scan in the
  editor; `footnote_asterisk` keeps the notes with other guessed words (Hebrew, Greek, fills).
- `bible_refs._VN` was changed with it: a verse number is cut off before a book name only when
  it is 1–4 (a book's number: "31. 1 Rois"); before, "XXXI. 24. 25. Isai." lost its 25.
- `bible_refs._TABLE` knows Latin and OCR spellings of the book names (`Iudic.`, `Iosuæ`,
  `Ierem.`, `Iob`, `Lævit.`, `Coloff.`, `Ysai.`, `Judicum`, `Josue`, `Josuae`): a new volume's
  unread references usually mean a spelling to add there.

## 12. Corpus-wide cleanup rules (Oct 21–30, 2026)

Between Oct 21 and 30 every volume then in `data/` (the Old Testament and Matthieu) went through
a run of mechanical passes; the commit messages list what changed, page by page. What a new
volume needs from them:

### What runs by itself

- Step 4 runs two rule sets on every page, in this order, and `tests/test_modernize_inplace.py`
  pins both:
  - `clean_mechanical.py` (`clean_page`): word-for-word repairs (OCR slips, old spellings,
    `J E S U S`), a lemma run into `french_commentary` moved to its fields, a leading footnote
    call moved onto the translation (kept where there is none);
  - `modernize_inplace.py` (`modernize_page`): the rules that read the words around them.

  The order matters: on raw New Testament transcriptions the other order left `charue`,
  `abrégez`, `revétue`, `ferai assise` in 76 fields, because the context rules look for words
  `clean_mechanical` has already repaired. On the finished corpus neither ever undoes the
  other. A new rule goes in `clean_mechanical.fix_spelling` when it is a word for a word, in
  `modernize_inplace.py` when it needs context, with a test either way.
- `modernize_inplace.py`'s families: core vocabulary (`ame`, `foible*`,
  `jusques`, `vray`, `grace`, `mesme`…), `-uë` and `-yent` endings, accents and trémas,
  obsolete hyphens (`long-temps` → `longtemps`, `tout-à-fait` → `tout à fait`, contextual
  `de-là`), obsolete circumflexes (`lû` → `lu`), `y` → `i` (`loy`, `abyme`, `aye`), `oi` → `ai`
  (`connoître`, `disoit`), plurals in `-ans`/`-ens`, long-s misreadings (`forte` → `sorte`,
  `fait` → `sait`, `ferai` → `serai`, `çç` → `ç`), participles in `-ez`, missing apostrophes
  (`d une`, `quil`), contextual `par tout` → `partout`, vocative `Ô`, `S.` → `Saint`,
  `J. C.` → `Jésus-Christ`, `l'Heb.` → `l'Hébreu`, `Chap.` → `Chapitre`, punctuation moved
  before a footnote call (`mot. ^{(a)}`) and a space after punctuation.
- `modernize.py` guards `reçoit`, `conçoit`, `aperçoit`, `déçoit` in `replace_oit()`, so the
  present of *-cevoir* is not turned into `-çait`.
- `fix_markers.py` (`fix_footnotes()`, step 7): markers recovered from the other keys the OCR
  used (`footnote_marker`, `ref`, …) and written `(a)`; every note reduced to
  `{marker, text, tags}`; unlabelled continuation notes merged into their parent; notes sorted
  by marker; bare calls in the commentary written `^{(x)}`.
- `tidy_fields.py` (step 8): a `chapter_title` is kept only on a page that opens a chapter
  (`chapter_summary`, verse 1 or 0, `chapter_number` or `chapter_intro`), so running heads
  ("SUR JEREMIE. CHAPITRE XLIX.") are cleared; `SUR LE PSEAUME N` becomes `PSEAUME N`;
  underscores around a whole `french_translation` are stripped (`WRAPPED_TRANSLATION`), partial
  italics kept.
- `calmet.py` (`COMPOUND`, `infer_join`, `join_seam`): a word after a hyphen at the foot of a
  page that makes a real compound (`peut-`‖`être`, `au-`‖`dessus`, `ci-`‖`devant`) keeps its
  hyphen on export, italic compounds included (`_consolez-_`‖`_vous_`).

### Decisions to keep (don't undo them)

- `Très-Haut` keeps its hyphen; every other `très-X` loses it.
- Modern hyphenated compounds stay (`peut-être`, `vis-à-vis`, `au-delà`, `grand-prêtre`,
  `dit-il`, `louez-le`), as do hyphenated Hebrew names (`Cariath-iarim`) and `Emmanu-el`.
- Genuine diaereses and circumflexes stay (`aiguë`, `Saül`, `Emmaüs`; `dû`, `mûr`, `sûr`;
  `qu'il parût`), and so do Latin ablatives (`aquâ`, `spiritûs`).
- `vôtre` / `nôtre` keep the circumflex only as pronouns (`le vôtre`); as adjectives they are
  `votre` / `notre`.
- A long-s misreading is rewritten only in the contexts its rule lists, and the real word stays
  everywhere else (`ville forte`, `je ferai alliance`, `faire mention`). Add a context only with
  a test.
- `-ez` becomes `-és` only for a participle or adjective; imperatives and second-person verbs
  stay (`Allez en paix`, `Sauvez-moi`, `vous possédez`).
- Vocative `O` becomes `Ô` in French only; Latin and the Hebrew letter headings are left.
- The French rules never touch `latin`, `latin_quote`, Greek or Hebrew, nor Latin quoted in a
  French field: an italic span with two Latin words, or a word with two Latin words among the
  three on either side (`clean_mechanical.keep_printed`).
- A hyphen at the foot of a page stays (`NOC-`, `re-`); a word modernized across a page break
  keeps it (`pa-`‖`rents`). The halves themselves are left as printed: the first word of a page's
  first verse or block when it is lower case (`vaient` of `de-vaient` is no misread `voient`),
  and the last word of a field that ends in a hyphen (`forti-`).
- `Machabées`, Calmet's name, everywhere (the user's choice, Oct 31): `footnotes.py` and
  `bible_refs` write it, and `clean_mechanical` turns the LLM pass's `Maccabées` back into it.
  Latin forms (`Machabæorum`, `Maccabæus`) are left as printed.
- `ferai` stays where it is *faire*: after `que` (`l'alliance que je ferai avec vous`), before an
  alliance or a pact, and in `à l'égard de`, `comme un vent`, which read either way and wait
  for the scan.

## 13. Current status & remaining work (as of Oct 30, 2026)

The only place for status: when a step is done, update it here, not in the sections above.

- **Structural Normalization**: 100% complete across all 46 Old Testament books (`01_genese` through
  `46_2_maccabees`) with **0 page gaps** in `audit_integrity.py`.
- **New Testament**: `47_matthieu` is seeded (648 pages in `normalized/`) and went through the
  Oct 27–30 corpus passes (§12); check which other §4 steps it still needs. `48_marc` onward and
  `74_3_maccabees` / `75_4_maccabees` are not seeded.
- **Commentary & Footnote Structural Cleanups**: duplicate verse commentary entries removed, inverted verse-commentary blocks corrected, continuation lemmas cleared/re-referenced, embedded ALL-CAPS lemmas extracted, 47 displaced/missing footnotes restored to `footnotes` arrays, and page-seam compound hyphens normalized across the corpus.
- **Bible References in Commentary** (§11): 100% complete across all 46 Old Testament books with
  **0 items to review**; `modernize_refs.MANUAL` holds over 150 settled entries for 21b–46.
- **French Modernization, Typography & Footnote Calls** (§12): 100% complete across all 46 Old Testament books and Matthieu (`modernize_inplace.py all`), including `Jésus-Christ` expansion, footnote punctuation repositioning, space after punctuation, and `S.` expansion.
- **Footnotes Pipeline (`footnotes.py`)**:
  - `01_genese` through `21a_psaumes`: completed and held notes indexed in `docs/footnotes/held.json`.
  - `21b_psaumes` through `26_ecclesiastique`: local checks run and applied into `normalized/` (over 1,440
    footnote updates applied across these volumes). Greek Hunspell queries cached in
    `cache/refs/grc_hunspell_asked.json` for fast replay.
  - `27_isaie` through `46_2_maccabees`: ready to run with `uv run --no-project --with pillow python footnotes.py run <vol> --local`
    and `python3 footnotes.py apply <vol>`.
- **Remaining Tasks before New Testament**:
  - Two to-dos in the review editor (`faire` or `être`?): `28_jeremie` p. 305 *Je ferai comme
    un vent brûlant*, `27_isaie` p. 333 *Je ferai à l'égard de Sennachérib*.
  - `books.json` still names the books `1 Maccabées` / `2 Maccabées` for the site (and the
    website's own book list): ask whether the site should say `Machabées` too.
  - Run and apply local footnotes for remaining OT volumes (`27_isaie` through `46_2_maccabees`).
  - Review queue audit resolution with the editor (`review_web.py`).
  - Check with user on source directory for seeding the rest of the New Testament (`48_marc` onward).
  - Website adjustments for Psalms (`src/routes/[book]/[id]/+page.server.ts` chapter bounds & verse 0
    title display) and deployment.
