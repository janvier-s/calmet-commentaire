"""Chapter and verse_ref of the blocks that go on from a note, brought into line with that note.

  python3 sync_continuations.py <volume|book|all> ... [--apply] [--verbose]

A note split over a page turn (or in two on the page) is several blocks, the first with the lemma, the
others with neither lemma nor translation (continuations.py says which ones go on). Each keeps its own
chapter and verse_ref, copied when it was made, so a number corrected on the note stays wrong on the rest.
Each such block takes the chapter and verse_ref of the block before it, in page order (a chain of
continuations follows its note). Blocks that may open a note of their own (a capital after a full stop,
the lemma in capitals) are left alone and counted: `--verbose` lists them with their numbers.
"""
import json
import sys

from continuations import continues, copy_refs, refs, sentence_ended, opens_with_capital
from paths import pages, volumes_of


def main(argv):
    apply, verbose = "--apply" in argv, "--verbose" in argv
    vols = volumes_of([a for a in argv if not a.startswith("--")])
    if not vols:
        sys.exit(__doc__)
    fixed = files = unsure = 0
    for vol in vols:
        prev = None  # the last block of the page before, as corrected
        for p in pages(vol):
            raw = p.read_text(encoding="utf-8")
            d = json.loads(raw)
            changed = []
            for j, b in enumerate(d.get("commentary") or []):
                if prev is not None and refs(b) != refs(prev):
                    if continues(prev.get("french_commentary"), b):
                        was = refs(b)
                        copy_refs(b, prev)
                        if refs(b) != was:
                            changed.append(f"{b.get('commentary_id')}: {was[0] or '-'}:{was[1] or '-'} -> {refs(b)[0]}:{refs(b)[1]}")
                    elif not (b.get("latin_quote") or b.get("french_translation") or "").strip():
                        unsure += 1  # no lemma, but it may start a note
                        if verbose:
                            print(f"  ? {vol}/{p.stem} note {b.get('commentary_id')}: {refs(b)} after {refs(prev)}")
                prev = b
            if changed:
                files += 1
                fixed += len(changed)
                print(f"{vol}/{p.stem}: " + "; ".join(changed))
                if apply:
                    p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + ("\n" if raw.endswith("\n") else ""),
                                 encoding="utf-8")
    print(f"{fixed} blocks on {files} pages" + (" written" if apply else " (dry run: --apply writes them)")
          + f"; {unsure} left alone: no lemma, but may open a note")


if __name__ == "__main__":
    main(sys.argv[1:])
