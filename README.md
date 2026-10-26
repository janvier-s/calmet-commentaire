# Calmet, *Commentaire littéral*

A modernized transcription of Dom Augustin Calmet's *Commentaire littéral sur tous les livres de
l'Ancien et du Nouveau Testament* (1707–1716): the Latin and French text of every verse, Calmet's
commentary and his footnotes, page by page, checked against the scans and the Vulgate. It feeds the
website [dom-calmet-web](https://github.com/janvier-s/dom-calmet-web).

Everything here is dedicated to the public domain ([CC0 1.0](LICENSE)): use it for anything, no
permission or credit needed.

## What is where

| | |
|---|---|
| `data/<volume>/normalized/page_NNNN.json` | **the text**: one file per printed page (verses, commentary, footnotes) |
| `data/.review_queue_progress.json` | which review issues are resolved, skipped or false positives |
| `docs/review_queue.json` | the review queue: every place a check found something to look at |
| `docs/*_check.json`, `docs/footnotes/` | the reports the queue is built from |
| `scripts/` | the pipeline, the checks and the review editor ([scripts/README.md](scripts/README.md)) |
| `scripts/vulgate/` | the Clementine Vulgate the checks compare against |
| `scripts/footnote_names.txt` | works and authors named in the footnotes, with their original titles |

Not in the repository: the scans (`data/<volume>/source_images/`), the raw OCR
(`data/<volume>/raw_json/`) and the model cache (`scripts/cache/`; the answers already paid for are
attached to the [releases](https://github.com/janvier-s/calmet-commentaire/releases) — unpack the
archive into `scripts/cache/` and re-runs cost nothing).

## Getting started

You need Python 3.12+ and [uv](https://docs.astral.sh/uv/) (for the tests and a few tools).

```sh
git clone https://github.com/janvier-s/calmet-commentaire
cd calmet-commentaire/scripts
python3 review_web.py 01_genese 120      # the review editor, in your browser
uv run --no-project --with pytest --with pillow python -m pytest tests -q
```

The editor works without the scans (it says "No scan for this page"); ask for the scans of the
volume you work on. Some checks need more:

- Hebrew and Greek in the footnotes: the Hebrew Bible (Open Scriptures, `scripts/cache/refs/hebrew_oshb.json`)
  and the Septuagint (getbible, `scripts/cache/refs/lxx/`).
- The French spellcheck: hunspell (`brew install hunspell`) and a French dictionary in `~/Library/Spelling/fr_FR`.
- Writing out footnotes and other model passes: [Claude Code](https://claude.com/claude-code) (`claude`) or agy.
- Exporting to the website: `dom-calmet-web` cloned beside this repository (or `CALMET_WEB=<its src/lib/data>`).

## Contributing

1. Pick a book (say which in an issue, so two people don't work on the same pages).
2. Make a branch, open the editor on that book, and work through its queue: compare the text with
   the scan, correct it, mark each issue resolved or a false positive.
3. Commit the pages you changed with `data/.review_queue_progress.json`, and open a pull request.

The conventions — what to modernize and what to keep as Calmet wrote it — are in
[scripts/README.md](scripts/README.md) and [scripts/NEXT_VOLUMES.md](scripts/NEXT_VOLUMES.md). In
short: modern French spelling, and modern forms of names (Maccabées, Israélites, Samuel), but
Calmet's Latin as he printed it (cœli, terrâ, cùm), and Latin inside French fields is never
"corrected" as French. Footnote abbreviations are written out following
`scripts/footnote_glossary.txt`.
