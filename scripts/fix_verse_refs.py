"""Set right the verse_ref of commentary blocks whose lemma is plainly in another verse.

Only sure cases are changed (the rest stay verse_mismatch issues in the review editor):
  - every word of the lemma is in that verse of our pages' Latin (the nearest such verse, within 3),
    and at least 4/5 of them in the Clementine Vulgate's (our verse itself is not misnumbered)
  - at most a fifth of them are in the verse it is under now
  - pages are gone over again until nothing moves, so a run of blocks all one verse off is set
    right too; a move that puts the blocks out of verse order is noted in data/verse_ref_order_ok.json
    and the audit raises no ref_order issue for it
A block cut by the page break takes the new verse on the next page too.
Psalms 113-115 are left alone (Calmet's and our Vulgate's numbering differ there).

Usage: python3 fix_verse_refs.py [--apply] [volume ...]   (dry run by default; every volume)
Changes are listed in reports/fix_verse_refs.tsv.
"""
import json
import re
import sys
from collections import defaultdict

from audit_integrity import best_verse
from bible_refs import vulgate
from paths import BOOKS, DATA, pages

# blocks whose new verse puts the page out of order on purpose: audit_integrity.py raises no
# ref_order issue for them (while their verse_ref is still the one set here)
ORDER_FILE = DATA / "verse_ref_order_ok.json"
ORDER_OK = json.loads(ORDER_FILE.read_text(encoding="utf-8")) if ORDER_FILE.exists() else {}
MOVED = {}  # (page, commentary_id) -> the verse_ref it had
VUL_OF = {v: b["vul"] for b in BOOKS.values() for v in b["studium"]}


def num(x):
    return int(x) if str(x).isdigit() else None


def fix_page(blocks, ours, vul, vol, p, log):
    moved = False
    for i, c in enumerate(blocks):
        lemma = re.sub(r"\^\{[^}]*\}", "", c.get("latin_quote") or "")
        ch, ref = str(c.get("chapter") or ""), str(c.get("verse_ref") or "")
        if len(re.findall(r"[^\W\d_]{3,}", lemma)) < 2 or num(ref) is None \
                or vol.startswith("21") and ch in ("113", "114", "115"):
            continue
        so, _ = best_verse(lemma, ours.get(ch, {}))
        sv, _ = best_verse(lemma, vul.get(ch, {}))
        if so.get(ref, 0) > 0.2:
            continue
        full = [v for v, x in so.items() if x == 1 and num(v) is not None and abs(num(v) - num(ref)) <= 3]
        if not full:
            continue
        bo = min(full, key=lambda v: abs(num(v) - num(ref)))
        if sv.get(bo, 0) < 0.8:
            continue
        same = lambda b: str(b.get("chapter") or "") == ch and num(b.get("verse_ref")) is not None
        prev = [num(b["verse_ref"]) for b in blocks[:i] if same(b)]
        nxt = [num(b["verse_ref"]) for b in blocks[i + 1:] if same(b)]
        if prev and prev[-1] > num(bo) or nxt and nxt[0] < num(bo):
            ORDER_OK[f"{vol}/{p.name}/{c.get('commentary_id')}"] = bo  # Calmet going back: on purpose
        log.append(f"{vol}/{p.stem}\t{c.get('commentary_id')}\t{ch}\t{ref}\t{bo}\t{lemma[:70]}")
        MOVED[(p, c.get("commentary_id"))] = ref
        c["verse_ref"] = bo if isinstance(c["verse_ref"], str) else int(bo)
        moved = True
    return moved


def follow(docs, moved, log, vol):
    """A block cut by the page break goes on in the first block of the next page (no lemma):
    give that one the new verse too. moved: {(page, commentary_id): old verse_ref}. Pages touched."""
    touched = set()
    for (p, d), (q, e) in zip(docs, docs[1:]):
        last, first = (d.get("commentary") or [None])[-1], (e.get("commentary") or [None])[0]
        if not last or not first or (p, last.get("commentary_id")) not in moved:
            continue
        old = moved[(p, last.get("commentary_id"))]
        while first and not (first.get("latin_quote") or "").strip() and str(first.get("verse_ref")) == str(old) \
                and str(first.get("chapter")) == str(last.get("chapter")):
            first["verse_ref"] = last["verse_ref"] if isinstance(first["verse_ref"], str) else int(last["verse_ref"])
            log.append(f"{vol}/{q.stem}\t{first.get('commentary_id')}\t{first.get('chapter')}\t{old}\t{first['verse_ref']}\t(goes on from {p.stem})")
            touched.add(q)
            # the whole next page may be that one block: go on to the page after
            if len(e.get("commentary") or []) != 1:
                break
            moved = {**moved, (q, first.get("commentary_id")): old}
            break
    return touched


def main(argv):
    apply = "--apply" in argv
    vols = [a for a in argv if not a.startswith("--")] or sorted(p.parent.name for p in DATA.glob("*/normalized"))
    log = []
    for vol in vols:
        if vol not in VUL_OF:
            continue
        vul = defaultdict(dict)
        for (c, v), t in vulgate(VUL_OF[vol]).items():
            vul[str(c)][str(v)] = t
        docs = []
        for p in pages(vol):
            try:
                docs.append((p, json.loads(p.read_text(encoding="utf-8"))))
            except json.JSONDecodeError:
                pass
        ours = defaultdict(dict)
        for _, d in docs:
            for v in d.get("verses") or []:
                ours[str(v.get("chapter"))][str(v.get("verse_number"))] = v.get("latin") or ""
        touched = set()
        for p, d in docs:
            blocks, changed = d.get("commentary") or [], False
            while fix_page(blocks, ours, vul, vol, p, log):  # again: a run of blocks all one verse off
                changed = True
            if changed:
                touched.add(p)
        touched |= follow(docs, {k: v for k, v in MOVED.items() if k[0].parent == docs[0][0].parent}, log, vol) if docs else set()
        for p, d in docs:
            if p in touched and apply:
                p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    if apply:
        ORDER_FILE.write_text(json.dumps(ORDER_OK, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    out = DATA.parent / "reports" / "fix_verse_refs.tsv"
    out.write_text("page\tnote\tchapter\twas\tnow\tlemma\n" + "\n".join(log), encoding="utf-8")
    print(f"{len(log)} verse_ref set right", "" if apply else "(dry run)", f"\nlisted in {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
