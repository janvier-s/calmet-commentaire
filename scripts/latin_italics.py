"""Detect and italicize Latin text in French commentary (french_commentary) in normalized/.

Usage:
  python3 scripts/latin_italics.py <volume|book|all> ...           report -> docs/latin_italics.json
  python3 scripts/latin_italics.py <volume|book|all> ... --apply   write italics directly into normalized/
"""
import json
import re
import sys
from pathlib import Path

import page_text as PT
import spellcheck as SC
from calmet import _fold, proper_nouns, vulgate_words
from paths import BOOKS, DATA, DOCS, pages, volumes_of

OUT = DOCS / "latin_italics.json"

FRENCH_CHARS = re.compile(r"[éèêëç]", re.I)
FRENCH_EXCLUSIVE = set(
    "le la les des du un une il ils elle elles on nous vous je tu ce cet cette ces "
    "leur leurs mon ton son notre votre mes tes ses nos vos qui que quoi dont où "
    "dans pour avec sans sous chez entre contre sur vers depuis pendant selon par "
    "est sont était étaient fut furent été être avoir ayant avait avaient ont fait "
    "faire dit dire peut peuvent pouvoir doit doivent devoir comme ainsi alors encore "
    "toujours jamais déjà ici là point pas plus moins très bien tout tous toute toutes "
    "aussi autre autres même mêmes car donc mais en y".split()
)

LATIN_CONNECTORS = {
    "et", "in", "ad", "de", "ab", "ex", "sub", "cum", "per", "non", "nec", "neque",
    "sed", "ut", "si", "se", "te", "me", "eum", "ejus", "eius", "id", "ea", "is",
    "a", "o", "ac", "atque", "etc", "inter", "super", "propter", "quod", "quae",
    "quam", "quem", "qui", "cui", "quo", "qua", "aut", "vel", "tam", "sive", "seu",
    "ubi", "quando", "cur", "nunc", "tunc", "ante", "post", "sine"
}

DANGLING_CONNECTORS = {
    "et", "ac", "atque", "sed", "nec", "neque", "ad", "in", "de", "ab", "ex",
    "per", "sub", "cum", "ut", "si", "aut", "vel", "tam", "quam", "sive", "seu"
}

LATIN_LOCUTIONS = [
    r"\ba\s+priori\b", r"\ba\s+posteriori\b", r"\bad\s+hoc\b", r"\bad\s+hominem\b",
    r"\bad\s+infinitum\b", r"\bad\s+libitum\b", r"\bad\s+litteram\b", r"\bad\s+interim\b",
    r"\bde\s+facto\b", r"\bde\s+jure\b", r"\bex\s+cathedra\b", r"\bex\s+nihilo\b",
    r"\bex\s+professo\b", r"\bex\s+officio\b", r"\bex\s+toto\b", r"\bin\s+extenso\b",
    r"\bin\s+fine\b", r"\bin\s+loco\b", r"\bin\s+medio\b", r"\bin\s+promptu\b",
    r"\bin\s+specie\b", r"\bin\s+terminis\b", r"\bipso\s+facto\b", r"\bipso\s+jure\b",
    r"\bmanu\s+militari\b", r"\bmutatis\s+mutandis\b", r"\bne\s+varietur\b",
    r"\bnota\s+bene\b", r"\bpost\s+factum\b", r"\bpost\s+mortem\b",
    r"\bpro\s+forma\b", r"\bpro\s+hac\s+vice\b", r"\bratione\s+materiae\b",
    r"\bsecundum\s+quid\b", r"\bsensu\s+latiori\b", r"\bsensu\s+stricto\b",
    r"\bsine\s+die\b", r"\bsine\s+qua\s+non\b", r"\bstricto\s+sensu\b",
    r"\bsub\s+conditione\b", r"\bsub\s+rosa\b", r"\bsui\s+generis\b",
    r"\bvice\s+versa\b", r"\bviva\s+voce\b", r"\btertium\s+quid\b",
    r"\bjuxta\s+hebr[aæ]os\b", r"\biuxta\s+hebr[aæ]os\b", r"\bsecundum\s+hebr[aæ]os\b",
    r"\bsecundum\s+carnem\b", r"\bsecundum\s+spiritum\b", r"\bretro\s+versus\b"
]
LOCUTION_RX = re.compile("|".join(LATIN_LOCUTIONS), re.I)

INTRO_RX = re.compile(
    r"(?:le\s+mot\s+(?:de\s+)?|le\s+terme\s+(?:de\s+)?|en\s+latin\s+|"
    r"la\s+vulgate\s+(?:porte|lit|a)\s+|rendu\s+par\s+|exprimer\s+par\s+|nom\s+de\s+)$",
    re.I
)

FRENCH_DETERMINER_RX = re.compile(
    r"(?:^|\s)(?:d'|l'|qu'|un|une|le|la|les|du|des|ce|cet|cette|ces|son|sa|ses|leur|leurs)\s*$",
    re.I
)


def load_vocabularies():
    vul = vulgate_words()
    props = proper_nouns()
    names = SC.known_names()

    fn_names = set()
    for nf in ["footnote_names.txt", "spellcheck_names.txt", "latin_names.txt"]:
        p = Path(__file__).resolve().parent / nf
        if p.exists():
            for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    for w in re.findall(r"[\wÀ-ÿ]+", line):
                        fn_names.add(w.lower())
                        fn_names.add(_fold(w))

    books_json = json.loads((Path(__file__).resolve().parent / "books.json").read_text(encoding="utf-8"))
    for k, b in books_json.items():
        for w in re.findall(r"[\wÀ-ÿ]+", b.get("fr", "")):
            props.add(_fold(w))
        for w in re.findall(r"[\wÀ-ÿ]+", b.get("vul", "")):
            props.add(_fold(w))

    lex_path = Path("/Users/Janvier/Documents/Bible n stuff/sources/divinum-officium/lexicon-tools/latin_lexicon.json")
    if lex_path.exists():
        lex = json.loads(lex_path.read_text(encoding="utf-8"))
        for w in lex:
            vul.add(_fold(w))

    cached = json.loads(SC.HUNSPELL_CACHE.read_text(encoding="utf-8"))["words"]
    french_words = {w.lower() for w, sugg in cached.items() if sugg is None}
    french_words |= {
        "forte", "fortes", "ventre", "ventres", "attendant", "inventa", "servirent",
        "parentes", "graves", "conservés", "dant", "sens", "vers", "mort", "sort",
        "pont", "dent", "terre", "ciel", "eau", "eaux", "feu", "air", "mer", "pain",
        "vin", "homme", "hommes", "femme", "femmes", "roi", "rois", "fils", "père",
        "mère", "jour", "jours", "nuit", "nuits", "an", "ans", "corps", "bras",
        "main", "mains", "pied", "pieds", "œil", "yeux", "lieu", "lieux", "dieu",
        "seigneur", "saint", "sainte", "saints", "saintes", "ville", "villes", "loi",
        "homine"
    }

    pure = set()
    for w, sugg in cached.items():
        if sugg is not None:
            wl = SC.bare(w)
            if not SC.ACCENT.search(wl) and wl.lower() not in french_words:
                folded = _fold(wl.translate(SC.GRAVE))
                if folded in vul and folded not in props and wl not in names and wl not in fn_names:
                    pure.add(folded)

    core_latin = {
        "adduxit", "spiritum", "terram", "aquae", "aquæ", "coeli", "coelum", "caeli",
        "caelum", "posuit", "erat", "dixit", "fecit", "propterea", "sicut",
        "quoniam", "autem", "enim", "verbum", "dominus", "audivit", "habeo",
        "surrexit", "trono", "ausculta", "fili", "extendit", "manum", "infixit",
        "clausit", "aperuit", "portas", "vocavit", "fueris", "dederit", "stilla",
        "stillabis", "ecce", "poenituit", "redeuntes", "euntes", "resina", "medicus",
        "multiplicas", "medicamina", "arida", "aridum", "eunuchus", "accrescens",
        "habebant", "dixere", "hastas", "diademate", "sceptra", "coluere",
        "simulacris", "adhibentur", "opinassimam", "effregit", "civitatem", "sinistro",
        "ciliciae", "ciliciæ", "praedavitque", "prædavitque", "coquenti", "similitudinem",
        "argenteis", "polymita", "talari", "virilia", "hostias", "coxerunt", "lebetibus",
        "cacabis", "ollis", "permanse", "virginalis", "jugiter", "furto", "gravius",
        "furari", "liceret", "cantatione", "assaveunt", "assaverunt", "abscindere",
        "vestem", "ubere", "matris", "quercui", "lepra", "insepultum", "relinquerent",
        "nefas", "tabernaculi", "multitudinis", "immunditiam", "putredine", "pessima",
        "pessimâ", "concrevit", "sanguis", "levis", "devorabit", "eruamini",
        "inimicorum", "vestrorum", "vitiis", "acutum", "lippus", "inunctis",
        "dominandi", "cupiditate", "consulendi", "principandi", "superbia", "superbiâ",
        "misericordia", "misericordiâ", "providendi", "prophetas", "occiderunt",
        "imperarent", "infelicius", "inordinatus", "animus", "comburentur", "spinae",
        "spinæ", "congregatae", "congregatæ", "coinquinabar", "coquebant",
        "propinquitas", "perit", "noxam", "vagitus", "rubentem", "necasse", "bovem"
    }
    pure |= core_latin
    pure -= french_words
    return vul, props, pure, french_words, fn_names


def is_latin_token(w, vul, french_words):
    if FRENCH_CHARS.search(w):
        return False
    wl = w.lower()
    if wl in FRENCH_EXCLUSIVE:
        return False
    fw = _fold(w)
    if wl in french_words and fw not in LATIN_CONNECTORS:
        return False
    return fw in vul or fw in LATIN_CONNECTORS


def find_latin_spans(fc, vul, props, pure, french_words, fn_names):
    """Return non-overlapping (start, end, span_text, kind) tuples for Latin in fc."""
    runs, _, _ = PT.italic_runs(fc)
    mask = [False] * len(fc)
    for a, b in runs:
        for i in range(a, b):
            mask[i] = True

    spans = []
    # 1. Standard Latin locutions
    for m in LOCUTION_RX.finditer(fc):
        if not any(mask[i] for i in range(m.start(), m.end())):
            spans.append((m.start(), m.end(), m.group(), "locution"))
            for i in range(m.start(), m.end()):
                mask[i] = True

    # 2. Tokenize words outside italics
    tokens = []
    for m in re.finditer(r"[A-Za-zÀ-ÿœæŒÆ]+", fc):
        if not mask[m.start()]:
            if m.end() < len(fc) and fc[m.end()] == "-":
                continue  # skip hyphenated line turns
            tokens.append((m.start(), m.end(), m.group()))

    ti = 0
    while ti < len(tokens):
        w = tokens[ti][2]
        if FRENCH_CHARS.search(w) or w.lower() in french_words or w.lower() in FRENCH_EXCLUSIVE:
            ti += 1
            continue

        fw = _fold(w)
        prev_is_italic = (tokens[ti][0] > 0 and fc[:tokens[ti][0]].rstrip(" \t,;:").endswith("_"))

        if fw in pure or (prev_is_italic and is_latin_token(w, vul, french_words)):
            run = [tokens[ti]]
            tj = ti + 1
            while tj < len(tokens):
                gap = fc[tokens[tj - 1][1]:tokens[tj][0]]
                # Cannot cross sentence boundary (.!?) unless part of etc.
                if len(gap) > 6 or (re.search(r"[.!?]", gap) and not gap.strip().endswith("etc.")):
                    break
                jw = tokens[tj][2]
                if is_latin_token(jw, vul, french_words):
                    run.append(tokens[tj])
                    tj += 1
                elif jw.lower() == "etc" and gap.strip() in {"", ","}:
                    run.append(tokens[tj])
                    tj += 1
                    break
                else:
                    break

            # Trim trailing dangling connectors
            while len(run) > 1 and _fold(run[-1][2]) in DANGLING_CONNECTORS and run[-1][2].lower() != "etc":
                run.pop()
                tj -= 1
            while len(run) > 1 and _fold(run[0][2]) in DANGLING_CONNECTORS:
                run.pop(0)
                ti += 1

            # Reject if preceded by a French determiner
            before_run = fc[:run[0][0]]
            if FRENCH_DETERMINER_RX.search(before_run) and not INTRO_RX.search(before_run):
                ti = tj
                continue

            words = [t[2] for t in run]
            pure_cnt = sum(1 for rw in words if _fold(rw) in pure)
            prop_cnt = sum(1 for rw in words if _fold(rw) in props or _fold(rw) in fn_names)

            accept = False
            kind = "quote"
            if len(words) >= 3 and pure_cnt >= 2 and pure_cnt >= prop_cnt:
                accept = True
            elif len(words) == 2 and pure_cnt >= 1:
                if all(rw.lower() not in french_words for rw in words):
                    accept = True
            elif len(words) == 1 and pure_cnt == 1:
                if prev_is_italic:
                    after_tok = fc[run[-1][1]:run[-1][1] + 15].lstrip()
                    if not any(after_tok.startswith(fw + " ") for fw in FRENCH_EXCLUSIVE):
                        accept = True
                        kind = "continuation"
                else:
                    before_ctx = fc[max(0, run[0][0] - 30):run[0][0]]
                    if "_" not in before_ctx and INTRO_RX.search(before_ctx):
                        if _fold(words[0]) not in fn_names and _fold(words[0]) not in props:
                            accept = True
                            kind = "single_word"

            if accept:
                s_pos = run[0][0]
                e_pos = run[-1][1]
                if run[-1][2].lower() == "etc" and e_pos < len(fc) and fc[e_pos] == ".":
                    e_pos += 1
                else:
                    m_etc = re.match(r"[ \t]*,?[ \t]*etc\.", fc[e_pos:], re.I)
                    if m_etc:
                        e_pos += m_etc.end()
                spans.append((s_pos, e_pos, fc[s_pos:e_pos], kind))
                ti = tj
                continue
        ti += 1

    spans.sort(key=lambda x: x[0])
    return spans


def apply_spans(fc, spans):
    """Apply italics to spans in fc from right to left."""
    for s, e, _, _ in reversed(spans):
        res = PT.toggle_italics(fc, s, e)
        if res:
            fc = res[0]
    return fc


def process_volume(vol, apply_changes, vul, props, pure, french_words, fn_names):
    report_items = []
    pfiles = pages(vol)
    changed_pages = 0

    for pf in pfiles:
        d = json.loads(pf.read_text(encoding="utf-8"))
        pnum = int(pf.stem.split("_")[1])
        page_changed = False

        for comm_idx, comm in enumerate(d.get("commentary", [])):
            fc = comm.get("french_commentary") or ""
            spans = find_latin_spans(fc, vul, props, pure, french_words, fn_names)
            if spans:
                new_fc = apply_spans(fc, spans)
                if new_fc != fc:
                    for s, e, text, kind in spans:
                        report_items.append({
                            "vol": vol,
                            "page": pnum,
                            "comm_idx": comm_idx,
                            "kind": kind,
                            "text": text,
                            "context": fc[max(0, s - 30):min(len(fc), e + 30)].replace("\n", " ")
                        })
                    if apply_changes:
                        comm["french_commentary"] = new_fc
                        page_changed = True

        if page_changed and apply_changes:
            pf.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            changed_pages += 1

    return report_items, changed_pages


def main():
    apply_changes = "--apply" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--apply"]
    if not args:
        args = ["all"]
    vols = volumes_of(args)

    print(f"Loading Latin and French vocabularies...")
    vul, props, pure, french_words, fn_names = load_vocabularies()
    print(f"Loaded. Processing {len(vols)} volume(s) (apply={apply_changes})...")

    all_reports = []
    total_changed = 0

    for vol in vols:
        reps, changed = process_volume(vol, apply_changes, vul, props, pure, french_words, fn_names)
        all_reports.extend(reps)
        total_changed += changed
        if reps:
            print(f"  {vol}: {len(reps)} Latin span(s)" + (f" ({changed} pages updated)" if apply_changes else ""))

    OUT.write_text(json.dumps(all_reports, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nTotal: {len(all_reports)} Latin span(s) across {len(vols)} volume(s).")
    print(f"Report saved to {OUT}")
    if apply_changes:
        print(f"Applied changes to {total_changed} page files.")


if __name__ == "__main__":
    main()
