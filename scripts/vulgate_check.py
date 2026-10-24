"""Check the Latin of the verses (verses[].latin) against the Vulgate, word by word.

  python3 vulgate_check.py <volume|book|all> ...          report -> docs/vulgate_check.json
  python3 vulgate_check.py <volume|book|all> ... --apply  also write in the sure fixes

Both texts are compared without what only differs in spelling between editions (cœli/caeli,
tanquam/tamquam, exspecto/expecto, j/i, u/v, accents). What is left is sorted:
  long_s     the word with f read as s is the Vulgate's (noftris -> nostris)      sure
  split      a word broken by a space, a piece no Latin word (sp ritus -> spiritus)  sure
  joined     words our Vulgate writes as one (nec non / necnon): only the edition's way
  ligature   the word with -a where the Vulgate has -æ (aqua enim erant / aquæ): the æ
             read as a; Juda aside (the Clementine's rex Juda)                      sure
  slip       a typo where Calmet's word is no Latin word, rare in his Latin, and wrong
             before its ending (morse / morte, sultorum / stultorum)               sure
  spelling   a typo that is only the edition's spelling (annunciata / annuntiata)
  typo       one word for one, a letter or two apart (rispondebit / respondebit)  check
  confirmed  a typo or ligature where Calmet's own lemma for the verse has the
             Vulgate's word: the verse's transcription slipped; the lemma's word goes in  sure
  reading    anything else: another word, one missing or added                      check
  numbering  the text is a neighbouring verse's (or two verses): Calmet's numbers differ, or a slip
  mismatch   the verse is not the Vulgate's verse, nor a neighbour (a lemma, a gloss)  check
--apply writes only the sure kinds (long_s, split, confirmed, ligature, slip), in Calmet's own spelling (the word is changed, not
replaced by the Vulgate's). The others are for review against the scan: Calmet's Latin
can differ from our Vulgate text, and a transcription slip can look like a variant.
"""
import difflib
import json
import re
import sys
import unicodedata
from collections import Counter

import bible_refs as B
from paths import BOOKS, BY_VOLUME, DOCS, pages, volumes_of

OUT = DOCS / "vulgate_check.json"
ORIG_WORD = re.compile(r"[^\W\d_]+(?:-[^\W\d_]+)*")   # Beth-marchaboth is one word, as the Vulgate's Bethmarchaboth
# spellings that differ between Calmet's Clementine and our (Stuttgart) Vulgate, made one:
# cœli/caeli, tanquam/tamquam, exspecto/expecto, hæreditas/hereditas, Ismael/Ismahel,
# lacrymis/lacrimis, Philistiim/Philisthiim, Debora/Debbora, eundem/eumdem, quicquam/quidquam, u/v
EDITION = [(re.compile(p), r) for p, r in [(r"oe|ae", "e"), (r"exs", "ex"), (r"h", ""), (r"v", "u"), (r"y", "i"),
                                           (r"m(?=[qdtn])", "n"), (r"dq", "cq"), (r"ph", "f"), (r"([a-z])\1", r"\1")]]


def fold(w):
    """A word without accents, in lower case, æ/œ written out, j -> i."""
    w = unicodedata.normalize("NFD", w.lower().replace("æ", "ae").replace("œ", "oe"))
    return "".join(c for c in w if not unicodedata.combining(c)).replace("j", "i").replace("-", "")


def same(w):
    """The word with the differences between editions taken out."""
    for rx, r in EDITION:
        w = rx.sub(r, w)
    return w


def spelling(w):
    """same(), and also nunciare/nuntiare, mixtus/mistus: to tell a slip from a way of spelling."""
    return same(w).replace("ci", "ti").replace("x", "s")


LATIN = None    # every word of the Vulgate, in same() form (set in main)
SPELLED = None  # the same in spelling() form
# Calmet's words that slip() would take for slips, read and found to be Latin (another word or form,
# or his edition's spelling): left for review against the scan
NOT_SLIPS = set("""abscedentibus adfuit adscendens adscribatur astamus assistantibus adtor adversa aperient arrogant
asseratis audibant celebrabant coepis complevisset concidendum conseratur considerunt correctionem dirumpatur
disrupit edentium egressu esuriebant exaltationem expellemus expellitur explicavit festinansque genitrici genitricis
impudentissimi infectus inflabat inflaret iniquiorem lucescat levans marcescent obedientium oblitusque oppugnet
pendentia professus reportandam requisitionis retractatione scripturaque stimulabatur stupefacere transfixit
verberum vestibusque vicesimus loquutus caerimonias caerimoniis authoribus prophanum lapidicinis thesaurisaverunt
thezaurizantes holocaustomatis nulliusque infestationibus ivisset collidant funiculumque spatulisque pelliculisque
respicientque incidimus recubabat succindit expiatisque tradesque traditque facitque praecipitque fotum sons atrum
salto sumque clamque lapsam tinge""".split())
USAGE = None    # how often each word (folded) occurs in Calmet's Latin verses


def slip(x, y):
    """Calmet's word x is a slip for the Vulgate's y: no Latin word, rare in his Latin (not his edition's
    spelling), wrong before its ending (an ending can be grammar: invenias / inveniat), and not y with
    a negative in- (iniustitiis / iustitiis: the sense, not a letter)."""
    head = next((i for i, (a, b) in enumerate(zip(x, y)) if a != b), min(len(x), len(y)))  # letters alike
    return (x not in NOT_SLIPS and spelling(x) not in SPELLED and USAGE[x] <= 2 and head < min(len(x), len(y)) - 3
            and x != "in" + y and y != "in" + x)


def lev(a, b):
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def compare(latin, vulgate):
    """(similarity, [(kind, Calmet's words, the Vulgate's, (start, end) of Calmet's in `latin`)])."""
    spans = [m.span() for m in ORIG_WORD.finditer(latin)]
    a = [fold(latin[s:e]) for s, e in spans]
    vg_words = ORIG_WORD.findall(vulgate)
    b = [fold(w) for w in vg_words]
    sa, sb = [same(w) for w in a], [same(w) for w in b]
    sm = difflib.SequenceMatcher(None, sa, sb, autojunk=False)
    out = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        x, y = a[i1:i2], b[j1:j2]
        span = (spans[i1][0], spans[i2 - 1][1]) if i2 > i1 else None
        if len(x) >= 2 and len(y) == 1 and same("".join(x)) == sb[j1]:
            # a word broken by a space (sp ritus); words the editions only write apart (nec non) are not
            pieces = latin[span[0]:span[1]]
            kind = "split" if re.fullmatch(r"[^\W\d_]+(?: [^\W\d_]+)+", pieces) and \
                any(same(w) not in LATIN for w in x) else "joined"
        elif len(x) == 1 and len(y) == 1 and "f" in x[0] and same(x[0].replace("f", "s")) == sb[j1]:
            kind = "long_s"
        elif len(x) == 1 and len(y) == 1 and x[0].endswith("a") and y[0].endswith("ae") and x[0] + "e" == y[0] \
                and x[0] not in ("iuda", "pascha"):  # the Clementine's Juda, Pascha are indeclinable
            kind = "ligature"  # terra for terræ: the æ read as a
        elif len(x) == 1 and len(y) == 1 and lev(sa[i1], sb[j1]) <= 2:
            kind = "typo"
        else:
            kind = "reading"
        out.append((kind, " ".join(x), " ".join(y), span, " ".join(vg_words[j1:j2])))
    return sm.ratio(), out


def cover(latin, vulgate):
    """The share of Calmet's words found, in order, in the Vulgate text."""
    # f and s made one here, so a verse full of long s still finds its place
    a = [same(fold(w)).replace("f", "s") for w in ORIG_WORD.findall(latin)]
    b = [same(fold(w)).replace("f", "s") for w in ORIG_WORD.findall(vulgate)]
    if not a:
        return 0
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return sum(m.size for m in sm.get_matching_blocks()) / len(a)


def best_verse(latin, vg, ch, n):
    """("chapter:verse", text) of the Vulgate verse the Latin is: its own number if it fits, else a
    neighbour (±1, ±2) or two verses together; None if nothing fits."""
    own = vg.get((ch, n))
    if own and cover(latin, own) >= 0.6:
        return f"{ch}:{n}", own
    tries = [(f"{ch}:{m}", vg[(ch, m)]) for m in (n - 1, n + 1, n - 2, n + 2) if (ch, m) in vg]
    tries += [(f"{ch}:{m}-{m + 1}", vg[(ch, m)] + " " + vg[(ch, m + 1)])
              for m in (n - 1, n) if (ch, m) in vg and (ch, m + 1) in vg]
    scored = [(cover(latin, t), r, t) for r, t in tries]
    best = max(scored, default=None)
    return (best[1], best[2]) if best and best[0] >= 0.6 else None


def fixed_word(orig, vg_word, kind):
    """Calmet's word set right in his own spelling: f -> s where the Vulgate has s (an æ counts as
    the two letters it stands for), or the pieces joined. Where Calmet's edition spells the word
    otherwise (chariffimum / carissimum), every f made s (and sf, a long s read as two letters, made s),
    if that brings the word nearer the Vulgate's and within a letter or two of it."""
    if kind == "split":
        return re.sub(r"\s+", "", orig)
    if "-" in orig and "-" not in vg_word and vg_word[:1].islower():
        orig = orig.replace("-", "")  # novif-fimo: a word broken at the line end, not a name
    target, out, i = fold(vg_word), [], 0
    for c in orig:
        f = fold(c)
        if target[i:i + len(f)] != f and not (c == "f" and target[i:i + 1] == "s"):
            break
        out.append("s" if c == "f" and target[i:i + 1] == "s" else c)
        i += len(f)
    else:
        if i == len(target):
            return "".join(out)
    cand = orig.replace("sf", "s").replace("f", "s")
    d_old, d_new = lev(same(fold(orig)), same(fold(vg_word))), lev(same(fold(cand)), same(fold(vg_word)))
    return cand if d_new < d_old and d_new <= 2 else None


def lemma_words(vol):
    """{(chapter, verse): {folded word: the word as the lemma prints it}} from the commentary's
    latin_quote: Calmet's verse a second time, transcribed apart."""
    out = {}
    for p in pages(vol):
        for c in json.loads(p.read_text(encoding="utf-8")).get("commentary") or []:
            q = c.get("latin_quote")
            if isinstance(q, str) and q.strip():
                d = out.setdefault((str(c.get("chapter")), str(c.get("verse_ref"))), {})
                for w in ORIG_WORD.findall(q):
                    d.setdefault(fold(w), w)
    return out


def from_lemma(orig, lemma_word):
    """The lemma's word (in capitals) in the case of the verse's word."""
    w = lemma_word.lower()
    return w[:1].upper() + w[1:] if orig[:1].isupper() else w


def main(argv):
    apply = "--apply" in argv
    vols = volumes_of([a for a in argv if not a.startswith("--")])
    if not vols:
        sys.exit(__doc__)
    global LATIN
    LATIN = {same(fold(w)) for vul in {b["vul"] for b in BOOKS.values()} for t in B.vulgate(vul).values()
             for w in ORIG_WORD.findall(t)}
    global SPELLED, USAGE
    SPELLED = {spelling(w) for w in LATIN}
    USAGE = Counter(fold(w) for vol in volumes_of(["all"]) for p in pages(vol)
                    for v in json.loads(p.read_text(encoding="utf-8")).get("verses") or []
                    if isinstance(v.get("latin"), str) for w in ORIG_WORD.findall(v["latin"]))
    report, stats, kinds = [], Counter(), Counter()
    for vol in vols:
        vg = B.vulgate(BOOKS[BY_VOLUME[vol]]["vul"])
        lemmas = lemma_words(vol)
        for p in pages(vol):
            raw = p.read_text(encoding="utf-8")
            d = json.loads(raw)
            changed = False
            for v in d.get("verses") or []:
                lat, ch, n = v.get("latin"), v.get("chapter"), str(v.get("verse_number", ""))
                if not isinstance(lat, str) or not lat.strip() or not ch or not n.isdigit():
                    stats["no Latin or no reference"] += 1
                    continue
                where = f"{vol}/{p.stem}"
                found = best_verse(lat, vg, ch, int(n))
                if not found:
                    kind = "mismatch" if (ch, int(n)) in vg else "not in the Vulgate"
                    report.append(dict(where=where, ref=f"{ch}:{n}", kind=kind, latin=lat, vulgate=vg.get((ch, int(n)))))
                    kinds[kind] += 1
                    continue
                vref, ref = found
                if vref != f"{ch}:{n}":  # the text is another verse's: Calmet's numbering, or a slip
                    report.append(dict(where=where, ref=f"{ch}:{n}", kind="numbering", vulgate_ref=vref, latin=lat, vulgate=ref))
                    kinds["numbering"] += 1
                ratio, diffs = compare(lat, ref)
                stats["verses compared"] += 1
                new = lat
                lem = lemmas.get((str(ch), n), {})
                for kind, x, y, span, y_orig in sorted(diffs, key=lambda t: -(t[3] or (0, 0))[0]):
                    fix = fixed_word(lat[span[0]:span[1]], y, kind) if kind in ("long_s", "split") and span else None
                    orig = lat[span[0]:span[1]] if span else ""
                    if kind in ("typo", "ligature") and span and fold(y) in lem and x not in lem:
                        kind = "confirmed"   # Calmet's lemma for this verse has the Vulgate's word
                        fix = from_lemma(orig, lem[fold(y)])
                    elif kind == "ligature" and span and not orig.isupper():
                        fix = orig[:-1] + "æ"
                    elif kind == "typo" and spelling(x) == spelling(y):
                        kind = "spelling"    # annunciata / annuntiata: the edition's way, not a slip
                    elif kind == "typo" and span and slip(x, y) and not orig.isupper():
                        kind = "slip"
                        fix = (y_orig[:1].upper() if orig[:1].isupper() else y_orig[:1].lower()) + y_orig[1:]
                    kinds[kind] += 1
                    report.append(dict(where=where, ref=f"{ch}:{n}", kind=kind, calmet=x, vulgate_word=y,
                                       fix=fix, latin=lat, vulgate=ref))
                    if apply and fix and kind in ("long_s", "split", "confirmed", "ligature", "slip"):
                        new = new[:span[0]] + fix + new[span[1]:]
                if apply and new != lat:
                    v["latin"] = new
                    changed = True
                    stats["verses fixed"] += 1
            if changed:
                p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + ("\n" if raw.endswith("\n") else ""),
                             encoding="utf-8")
    order = ["mismatch", "not in the Vulgate", "numbering", "reading", "typo", "spelling", "joined",
             "slip", "ligature", "confirmed", "long_s", "split"]
    report.sort(key=lambda r: (order.index(r["kind"]), r["where"]))
    OUT.write_text(json.dumps(dict(stats=dict(stats), kinds=dict(kinds), items=report), ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(dict(stats))
    print("differences:", dict(kinds), "->", OUT.relative_to(DOCS.parent))


if __name__ == "__main__":
    main(sys.argv[1:])
