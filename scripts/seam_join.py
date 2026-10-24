"""Put back in its field a lemma or translation the page turn cut in two.

  python3 seam_join.py <volume|book|all> ...           report -> docs/seam_join.json
  python3 seam_join.py <volume|book|all> ... --apply   also write in the ones it is sure of

The last note of a page ends its latin_quote or french_translation mid-sentence (or on "PLAUS-"),
or with no translation at all, and the rest opens the next page's first block in french_commentary
(audit_integrity.py: hyphen_cut). The rest goes into the same field of that block, so every word
stays on the page it was printed on; calmet.py joins the two halves (and the broken word) on export.

  latin       the capitals overleaf, up to the full stop (or the first lower-case word)
  translation the text overleaf up to the earliest full stop near the lemma's length, or colon or
              semicolon past it (Calmet writes "translation ; comment"); also after a whole lemma
              whose translation is all overleaf
  comment     the cut translation had already ended ("…de large. Ce vestibule"): the few words after
              its full stop open the comment, and go to french_commentary
What the turn repeats (chanterai ‖ terai; parce ‖ ce qu'ils; a whole line) is printed once.

In the comment, the transcription often finished the page's last line as a sentence and the next
page repeats its end ("…aujourd'hui. ‖ d'hui dans le Grec"; "…commettre de plus grands. ‖ mettre
bien-tôt de plus grands": audit period_seam): the fragment overleaf is dropped and the words made
up after the word it completes (they all come again overleaf) are cut, with the full stop.
The rest is for review.
"""
import json
import re
import sys
from collections import Counter

from paths import DOCS, pages, volumes_of

OUT = DOCS / "seam_join.json"
CALL = r"(?:\s*\^\{[^}]*\})"
# a full stop after these is an abbreviation, not the end of the sentence
ABBREV = re.compile(r"(?:^|[\s(])(?:℣|ch|chap|v|vers|S|SS|Ps|art|liv|p|c|cf|l|t|n|M|MM|[A-Z]|Gen|Exod|Lev|Num|"
                    r"Deut|Jos|Judic|Jud|Reg|Par|Paral|Esdr|Tob|Esth|Prov|Eccl|Eccli|Cant|Sap|Is|Isai|Jer|"
                    r"Ezech|Dan|Os|Mich|Hab|Zach|Mal|Mac|Matth|Marc|Luc|Joan|Act|Rom|Cor|Gal|Eph|Hebr|Heb|"
                    r"Apoc|Ibid|ibid|Bar|Lib|lib|Hist|Antiq|Joseph|Hieron|Aug)$")
STOPS = re.compile(r"[.!?;:]_?" + CALL + r"?(?=\s|$)")


def bare(t):
    return re.sub(CALL, "", t or "").strip()


def unrepeat(tail, head):
    """(tail, head) with what the turn printed twice left out of head (or, for "quelque ‖
    quelques", out of tail), and how."""
    tw = re.findall(r"[^\W\d_]+", tail)
    hw = list(re.finditer(r"[^\W\d_]+", head))
    if tail.rstrip().endswith("-"):
        return tail, head, "hyphen"
    # the last words of the page set again overleaf, the first of them perhaps only its end
    for k in range(min(len(tw), len(hw), 12), 0, -1):
        a, b = [w.lower() for w in tw[-k:]], [m.group().lower() for m in hw[:k]]
        if a[1:] == b[1:] and (a[0] == b[0] or (a[0].endswith(b[0]) and len(a[0]) > len(b[0]) >= 2)):
            rest = head[hw[k - 1].end():]
            if re.search(r"[,;:.!?]\s*$", tail):
                rest = re.sub(r"^\s*[,;:.!?]", "", rest)
            return tail, rest.lstrip(), "repeat"
    if tw and hw and len(tw[-1]) >= 4 and hw[0].group().lower().startswith(tw[-1].lower()) \
            and tail.rstrip().endswith(tw[-1]):
        return tail.rstrip()[:-len(tw[-1])].rstrip(), head, "repeat"
    return tail, head, "space"


def latin_head(fc):
    """The capitals that open the comment, up to the lemma's full stop, or None."""
    m = re.match(r"\s*([A-ZÀ-ÝŒÆ][A-ZÀ-ÝŒÆ ,;:'’\-]*(?:" + CALL + r"[A-ZÀ-ÝŒÆ ,;:'’\-]*)*[.?!]" + CALL + r"?)(?=\s|$)", fc)
    if m:
        return m.group(1)
    m = re.match(r"\s*([A-ZÀ-ÝŒÆ][A-ZÀ-ÝŒÆ ,;:'’\-]*?[,;:]?)(?=\s+[A-ZÀ-Ý]?[a-zà-ÿ])", fc)
    return m.group(1).strip() if m and len(m.group(1).split()) >= 1 and m.group(1).strip() else None


def translation_head(tr, fc, lemma):
    """The start of the comment that is still the translation: up to the earliest full stop at
    which the translation is near its lemma's length, or semicolon or colon at which it is past it.
    None if there is none within about three times the lemma's length."""
    need = len(bare(lemma))
    for m in STOPS.finditer(fc):
        piece = fc[:m.end()]
        if need and len(bare(tr)) + len(bare(piece)) > max(3 * need, need + 80):
            return None
        if ABBREV.search(fc[:m.start()]) and fc[m.start()] == ".":
            continue
        if "_" in piece and piece.count("_") % 2:
            continue                          # inside italics
        if len(re.findall(r"\w+", bare(tr) + " " + bare(piece))) < 3:
            continue
        if len(bare(tr)) + len(bare(piece)) + 1 >= need * (0.7 if fc[m.start()] in ".!?" else 1.0):
            return piece
    return None


def in_verse(t, verse_fr):
    """Most of t's words are in the verse's French: the translation going on, not the comment."""
    ws = {w.lower() for w in re.findall(r"[^\W\d_]{3,}", t)}
    return bool(ws and verse_fr) and len(ws & {w.lower() for w in re.findall(r"[^\W\d_]{3,}", verse_fr)}) >= 0.5 * len(ws)


def plan(vol, a, b, la, fb, verse_fr=""):
    """The fix for the cut between la (last block of page a) and fb (first block of page b);
    verse_fr is the French of its verse."""
    lemma = la.get("latin_quote") or ""
    tr = la.get("french_translation") or ""
    fc = fb.get("french_commentary") or ""
    if not fc.strip() or (la.get("french_commentary") or "").strip() \
            or (fb.get("latin_quote") or "").strip() or (fb.get("french_translation") or "").strip():
        return None
    base = dict(where=f"{vol}/{a.stem}>{b.stem}", verse=la.get("verse_ref"), before=(tr or lemma)[-70:],
                after=fc[:120])
    if tr.strip():
        t = bare(tr)
        if re.search(r"[.!?»…)\]]_?$", t):
            return None
        # the translation may have ended already on this page ("…de large. Ce vestibule"; "…de leurs
        # jours. Ils n'auront point fourni…"): the earliest stop near the lemma's length, unless what
        # follows it is still the verse
        for m in re.finditer(r"[.!?]_?" + CALL + r"?\s+(?=[_«\"(]*[A-ZÀ-ÝŒÆ])", tr):
            if re.search(r"(?:ETC|…)\W*$", bare(lemma)) and len(tr[m.end():].split()) > 3:
                continue                      # the translation of "etc." may run on
            if ABBREV.search(tr[:m.start()]) or len(bare(tr[:m.end()])) < 0.7 * len(bare(lemma)) \
                    or tr[:m.end()].count("_") % 2:
                continue
            frag = tr[m.end():].strip()
            if t.endswith("-") and len(frag.split()) <= 1 or in_verse(frag + " " + (translation_head("", fc, "") or ""), verse_fr):
                break
            return dict(base, field="french_commentary", sure=True, how="comment",
                        set={"a.french_translation": tr[:m.end()].rstrip(), "a.french_commentary": frag},
                        show=f"{tr[:m.end()].rstrip()[-50:]} [{frag[:60]}] ‖ {fc[:50]}")
        head = translation_head(tr, fc, lemma)
        if not head:
            return dict(base, field="french_translation", sure=False, how="no stop")
        tail, kept, how = unrepeat(tr, head.strip())
        rest = fc[len(head):].lstrip()
        # a word or two up to a colon ("Le ‖ Grec : ^{(a)}") is the comment's opening, not the translation
        sure = bool(kept) and not kept.startswith("-") and \
            not (len(re.findall(r"\w+", bare(kept))) <= 2 and bare(kept).endswith(":"))
        return dict(base, field="french_translation", sure=sure, how=how,
                    set={"a.french_translation": tail, "b.french_translation": kept, "b.french_commentary": rest or None},
                    show=f"{tail[-50:]} ‖ {kept} ‖ {rest[:50]}")
    # the lemma (no translation yet on this page)
    if not lemma.strip():
        return None
    head = latin_head(fc)
    fix = dict(base, field="latin_quote", sure=True, set={})
    if re.search(r"[.!?]_?$", bare(lemma)):
        if head and len(re.findall(r"\w+", bare(head))) == 1 and unrepeat(lemma, head)[2] == "repeat":
            how = "repeat"            # DIEBUS. ‖ BUS.
        elif head:
            return dict(fix, sure=False, how="capitals after a whole lemma")
        else:
            how, head = "whole lemma", ""
    elif not head:
        return dict(fix, sure=False, how="no capitals")
    else:
        _, kept, how = unrepeat(lemma, head)
        fix["set"]["b.latin_quote"] = kept
    rest = fc[fc.index(head) + len(head):].lstrip() if head else fc.lstrip()
    fix["set"]["b.french_commentary"] = rest or None
    fix["show"] = f"{lemma[-50:]} ‖ {fix['set'].get('b.latin_quote', '')} ‖ {rest[:50]}"
    # the translation then opens what is left
    tr_head = translation_head("", rest, lemma + " " + head) if re.match(r"[_«\"(]*[A-ZÀ-Ý]", rest) else None
    if tr_head:
        fix["set"]["b.french_translation"] = tr_head.strip()
        fix["set"]["b.french_commentary"] = rest[len(tr_head):].lstrip() or None
        fix["show"] += f" ⇒ translation “{tr_head.strip()[:60]}”"
    elif how == "whole lemma":
        return dict(fix, sure=False, how="whole lemma, no translation overleaf")
    return dict(fix, how=how)


# what a fragment overleaf may also be, a word of its own
WORDS = set("ces mes des les ses tes que qui il ils elle elles de du le la et en ne se ce me te un une on nous vous "
            "leur leurs sur par pour dans sans mais ou où son sa est sont a ai as font sent".split())
TOKEN = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*")


def plan_repeat(vol, a, b, la, fb):
    """The fix for a comment the page closed with a made-up full stop and repeated overleaf."""
    fc, nfc = la.get("french_commentary") or "", fb.get("french_commentary") or ""
    if not fc.strip() or not nfc.strip() or (fb.get("latin_quote") or "").strip() \
            or (fb.get("french_translation") or "").strip():
        return None
    tail = fc.rstrip()
    first = TOKEN.match(nfc.lstrip())
    if not tail.endswith(".") or not first or not first.group()[0].islower():
        return None
    f = first.group().lower()
    base = dict(where=f"{vol}/{a.stem}>{b.stem}", verse=la.get("verse_ref"), field="french_commentary",
                before=fc[-70:], after=nfc[:120])
    toks = list(TOKEN.finditer(tail))[-10:]
    for j in range(len(toks) - 1, -1, -1):
        w = toks[j].group().lower()
        if not (w == f or (w.endswith(f) and len(f) >= 2)) or (len(f) <= 3 and j != len(toks) - 1):
            continue
        extra = tail[toks[j].end():]
        made_up = [t.lower() for t in TOKEN.findall(extra)]
        ahead = [t.lower() for t in TOKEN.findall(nfc)[:25]]
        if "^{" in extra or any(t not in ahead for t in made_up):
            break
        kept = tail[:toks[j].end()]
        if kept.count("_") % 2 != tail.count("_") % 2 and not re.search(r"_\W*$", extra):
            break
        rest = nfc.lstrip()[first.end():]
        punct = re.match(r"\s*([,;:.!?]+)\s*", rest)
        if f in WORDS and w != f and not punct:
            return dict(base, sure=False, how=f"“{f}” a word or the end of “{w}”")   # grâces. ‖ ces routes
        if punct:
            kept, rest = kept + punct.group(1), rest[punct.end():]
        if kept.count("_") % 2:
            kept += "_"                      # the italics ran to the made-up end
        return dict(base, sure=True, how="repeat at the turn" + (f" (cut: {extra.strip()})" if made_up else ""),
                    set={"a.french_commentary": kept, "b.french_commentary": rest.lstrip()},
                    show=f"{kept[-50:]} ‖ {rest.lstrip()[:50]}")
    return dict(base, sure=False, how="full stop at the turn")


def write(p, d, raw):
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + ("\n" if raw.endswith("\n") else ""), encoding="utf-8")


def main(argv):
    apply = "--apply" in argv
    vols = volumes_of([a for a in argv if not a.startswith("--")])
    if not vols:
        sys.exit(__doc__)
    items, stats = [], Counter()
    for vol in vols:
        ps = pages(vol)
        verses = {(x.get("chapter"), x.get("verse_number")): x.get("french") or ""
                  for p in ps for x in json.loads(p.read_text(encoding="utf-8")).get("verses") or []}
        for a, b in zip(ps, ps[1:]):
            ra, rb = a.read_text(encoding="utf-8"), b.read_text(encoding="utf-8")
            da, db = json.loads(ra), json.loads(rb)
            ca, cb = da.get("commentary") or [], db.get("commentary") or []
            if not ca or not cb:
                continue
            v = re.match(r"\d+", str(ca[-1].get("verse_ref") or ""))
            verse_fr = verses.get((ca[-1].get("chapter"), int(v.group()) if v else None), "")
            fix = plan(vol, a, b, ca[-1], cb[0], verse_fr) or plan_repeat(vol, a, b, ca[-1], cb[0])
            if not fix:
                continue
            items.append(fix)
            stats[("sure " if fix["sure"] else "review ") + fix["field"]] += 1
            if apply and fix["sure"]:
                for k, v in fix["set"].items():
                    (ca[-1] if k[0] == "a" else cb[0])[k[2:]] = v
                write(a, da, ra)
                write(b, db, rb)
    OUT.write_text(json.dumps(dict(stats=dict(stats), items=items), ensure_ascii=False, indent=1), encoding="utf-8")
    print(dict(stats), "->", OUT.relative_to(DOCS.parent))
    if apply:
        print(f"{sum(1 for x in items if x['sure'])} cuts joined")


if __name__ == "__main__":
    main(sys.argv[1:])
