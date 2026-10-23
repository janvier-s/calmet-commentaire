"""Spellcheck the French of a volume with hunspell, then sort what it flags.

  python3 spellcheck.py scan <volume|book> ...        hunspell over every French field
        -> docs/hunspell/<volume>.json:
           {"errors": {word: {"total": n, "sugg": "a, b", "dots": n, "pages": ["0012", ...]}}}
  python3 spellcheck.py inspect <volume|book> ...     long s, -oit/-oient, trémas, frequent words
  python3 spellcheck.py candidates <volume|book> ...  likely errors, grouped by kind [--limit N]
  python3 spellcheck.py context <volume|book> <word> ...  where the words occur [--limit N]

A book key from books.json (job, psalms) stands for all its volumes; several volumes are
read together. Report only: nothing here changes the pages.

inspect and candidates leave out what hunspell flags but is right: Latin (a word of the
Vulgate, unaccented), abbreviations (followed by a full stop nearly every time: Sym., Aug.)
and the names in spellcheck_names.txt. --all shows them too.

hunspell's answers are cached per word in cache/hunspell_cache.json (reset when the
dictionary changes), so a rescan after fixing a few pages takes seconds. Unknown words are
slow (hunspell looks for suggestions), so they are spread over one process per performance
core. Not more: the suggestion search is time-limited, and on efficiency cores it returns fewer.
"""
import json
import os
import re
import signal
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from itertools import islice

from calmet import _fold, vulgate_words
from paths import BOOKS, DATA, DOCS, HUNSPELL_CACHE, HUNSPELL_DICT, SCRIPTS, load, pages

OUT = DOCS / "hunspell"
NAMES = SCRIPTS / "spellcheck_names.txt"

LETTER = "A-Za-zÀ-ÖØ-öø-ÿœŒæÆ"
WORD = re.compile(rf"[{LETTER}]+(?:['’][{LETTER}]+)?")
CALL = re.compile(r"\^\{[^}]*\}")
UNSURE = re.compile(r"\[(?:UNCERTAIN[^\]]*|ILLEGIBLE)\]")    # transcription placeholders
ACCENT = re.compile(r"[éèêëàâîïôûùüç]", re.I)
MARKUP = re.compile(r"[_*#`]")
NUMBER = re.compile(r"\b\d+([,.:]\d+)*\b")
ELISION = re.compile(r"^(?:qu|[dljcsnmt])['’]", re.I)
TOP_FIELDS = ("book_title", "chapter_title", "chapter_intro", "chapter_summary",
              "chapter_argument", "chapter_preface")


# --- scan ---

def french_texts(d):
    for k in TOP_FIELDS:
        yield d.get(k)
    for v in d.get("verses", []):
        yield v.get("french")
    for fn in d.get("footnotes", []):
        yield fn.get("text")
    for c in d.get("commentary", []):
        yield c.get("french_translation")
        yield c.get("french_commentary")


def clean(text):
    if not text or not isinstance(text, str):
        return ""
    return NUMBER.sub(" ", MARKUP.sub(" ", CALL.sub(" ", UNSURE.sub(" ", text))))


def words(text):
    """(word, followed by a full stop) for each word of text."""
    text = clean(text)
    return [(m.group(), text[m.end():m.end() + 1] == ".") for m in WORD.finditer(text)]


def performance_cores():
    try:
        out = subprocess.run(["sysctl", "-n", "hw.perflevel0.physicalcpu"],
                             capture_output=True, text=True, check=True).stdout
        return int(out)
    except (OSError, ValueError, subprocess.CalledProcessError):
        return os.cpu_count() or 4


def hunspell(ws):
    """{word: suggestions} for the words of ws that hunspell does not recognize."""
    res = subprocess.run(["hunspell", "-d", str(HUNSPELL_DICT), "-a"], input="\n".join(ws) + "\n",
                         text=True, capture_output=True, check=True)
    # One block per input line, after a version banner
    blocks = res.stdout.strip().split("\n\n")
    if blocks and blocks[0].startswith("@(#)"):
        rest = blocks[0].split("\n", 1)
        if len(rest) > 1:
            blocks[0] = rest[1]
        else:
            blocks.pop(0)
    unknown = {}
    for w, blk in zip(ws, blocks):
        line = blk.strip()
        if line and line[0] in "&#?":
            unknown[w] = line.split(":", 1)[1].strip() if ":" in line else ""
    return unknown


def dict_signature():
    return [[f.stat().st_mtime, f.stat().st_size] for f in
            (HUNSPELL_DICT.with_suffix(".dic"), HUNSPELL_DICT.with_suffix(".aff"))]


def check(ws):
    """hunspell(ws), asking hunspell only about words not in the cache."""
    sig = dict_signature()
    try:
        cache = json.loads(HUNSPELL_CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    if cache.get("dict") != sig:
        cache = {"dict": sig, "words": {}}
    known = cache["words"]                   # word -> suggestions, or None if hunspell knows it
    todo = [w for w in ws if w not in known]
    if todo:
        n = performance_cores()
        print(f"  hunspell: {len(todo)} new words ({len(ws) - len(todo)} cached), {n} processes", flush=True)
        found = {}
        with ThreadPoolExecutor(max_workers=n) as ex:
            for part in ex.map(hunspell, [todo[i::n] for i in range(n)]):
                found.update(part)
        for w in todo:
            known[w] = found.get(w)
        HUNSPELL_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return {w: known[w] for w in ws if known[w] is not None}


def page_no(p):
    return p.stem.split("_")[1]


def scan(volumes):
    counts = {}
    for vol in volumes:
        c, dots, where = Counter(), Counter(), {}
        vol_pages = pages(vol)
        for p in vol_pages:
            for t in french_texts(load(p)):
                for w, dot in words(t):
                    c[w] += 1
                    dots[w] += dot
                    where.setdefault(w, []).append(page_no(p))
        counts[vol] = c, dots, where
        print(f"{vol}: {len(vol_pages)} pages, {sum(c.values())} words, {len(c)} distinct", flush=True)

    candidates = sorted({w for c, _, _ in counts.values() for w in c if len(w) > 2})
    unknown = check(candidates)

    OUT.mkdir(parents=True, exist_ok=True)
    for vol, (c, dots, where) in counts.items():
        errors = {w: {"total": c[w], "sugg": unknown[w], "dots": dots[w],
                      "pages": sorted(set(where[w]))}
                  for w in sorted(c) if w in unknown}
        out = OUT / f"{vol}.json"
        out.write_text(json.dumps({"errors": errors}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{vol}: {len(errors)} unrecognized words -> {out.relative_to(DOCS.parent)}", flush=True)


# --- reports on a scan ---

def load_errors(volumes):
    """The scans of these volumes merged: {word: {"total": n, "sugg": str}}."""
    merged = {}
    for vol in volumes:
        f = OUT / f"{vol}.json"
        if not f.exists():
            sys.exit(f"No scan for {vol}: run  python3 spellcheck.py scan {vol}")
        for w, info in json.loads(f.read_text(encoding="utf-8"))["errors"].items():
            m = merged.setdefault(w, {"total": 0, "sugg": info["sugg"], "dots": 0, "where": []})
            m["total"] += info["total"]
            m["dots"] += info.get("dots", 0)
            m["where"] += [(vol, p) for p in info.get("pages", [])]
    return dict(sorted(merged.items()))


@lru_cache(maxsize=None)
def french_words():
    """The words hunspell recognized, in any scan so far."""
    try:
        cached = json.loads(HUNSPELL_CACHE.read_text(encoding="utf-8"))["words"]
    except (OSError, ValueError, KeyError):
        return frozenset()
    return frozenset(w for w, sugg in cached.items() if sugg is None)


def s_twin(w, errors):
    """The word w would be with a long s read as s, if the text itself backs it: hunspell
    knows it, or it is flagged too but more frequent (Athanaf / Athanas)."""
    if "f" not in w:
        return None
    for twin in dict.fromkeys((w.replace("ff", "ss"), w.replace("f", "s"))):
        if twin == w:
            continue
        if twin in french_words() or ELISION.sub("", twin) in french_words():
            return twin
        if twin in errors and errors[twin]["total"] > errors[w]["total"]:
            return twin
    return None


def noise(errors):
    """{word: why it is right after all} for Latin, abbreviations and known names."""
    names, latin = known_names(), vulgate_words()
    why = {}
    for w, info in errors.items():
        wl = bare(w)
        if wl in names:
            why[w] = "known name"
        elif info["total"] >= 3 and info["dots"] >= 0.9 * info["total"] and not s_twin(w, errors):
            why[w] = "abbreviation"
        elif not ACCENT.search(wl) and _fold(wl) in latin:
            why[w] = "Latin"
    return why


def drop_noise(errors, show_all):
    """errors without the noise, and all of them (to look up long-s twins in)."""
    if show_all:
        return errors, errors
    why = noise(errors)
    tally = Counter(why.values())
    print("Left out (--all to show): " + ", ".join(f"{n} {k}" for k, n in tally.most_common()))
    return {w: info for w, info in errors.items() if w not in why}, errors


def known_names():
    return {l.strip().lower() for l in NAMES.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#")}


def bare(w):
    """w lowercased, without an elided article or pronoun (d', l', qu'...)."""
    return ELISION.sub("", w).lower()


def suggestions(info):
    return [s.strip() for s in info["sugg"].split(",") if s.strip()]


def inspect(errors, everything):
    names = known_names()
    trema_names = {n for n in names if any(c in n for c in "ëïü")}
    print(f"Total error types: {len(errors)}")

    print("\n--- POTENTIAL LONG-S (f -> s) ---")
    for w, info in errors.items():
        wl = bare(w)
        twin = s_twin(w, everything)
        if twin:
            print(f"  {w:20} -> s-word: {twin} (cnt: {info['total']}) | in the text")
        elif re.search(r"[aeiouyéèêàâîïôû]f[aeiouyéèêàâîïôû]|f[tpdcml]", wl):
            s_word = wl.replace("f", "s")
            if any(s_word == bare(s.split()[0]) for s in suggestions(info)):
                print(f"  {w:20} -> s-word: {s_word} (cnt: {info['total']}) | sugg: {info['sugg'][:40]}")

    print("\n--- ARCHAIC IMPERFECT / CONDITIONAL (oit, oient) ---")
    for w, info in errors.items():
        if re.search(r"[a-z]{3,}(?:oit|oient)$", w.lower()):
            print(f"  {w:20} (cnt: {info['total']}) | sugg: {info['sugg'][:40]}")

    print("\n--- TREMAS / ACCENTS ---")
    for w, info in errors.items():
        wl = w.lower()
        if any(c in wl for c in "ëïü") and not any(n in wl for n in trema_names):
            print(f"  {w:20} (cnt: {info['total']}) | sugg: {info['sugg'][:40]}")

    print("\n--- FREQUENT CANDIDATES (total >= 2), not Latin or proper names ---")
    for w, info in sorted(errors.items(), key=lambda kv: kv[1]["total"], reverse=True):
        if info["total"] < 2:
            break
        wl = bare(w)
        if wl in names:
            continue
        # capitalized names ending like Latin or Hebrew names
        if w[0].isupper() and wl.endswith(("us", "as", "on", "es", "is", "a", "o", "el", "am", "im")):
            continue
        looks_french = any(c in wl for c in "éèêàâîïôûç") or info["sugg"]
        if looks_french and not w.lower().endswith(("orum", "arum", "ibus", "ium", "unt", "ant", "ent")):
            print(f"  {w:25} ({info['total']:2d}) -> {info['sugg'][:50]}")


def classify(w, info, everything):
    """(kind, suggestions to show) for a likely error, or None."""
    wl = bare(w)
    if len(wl) <= 2:
        return None
    twin = s_twin(w, everything)
    if twin:
        return "long_s", [twin + " (in the text)"]
    suggs = suggestions(info)
    if not suggs:
        return None
    lower = [bare(s) for s in suggs]
    if re.search(r"(?:oit|oient|eü|aï|aë|oë|ouë|ië)$", wl):
        return "archaic_ending", suggs[:3]
    if "f" in wl and (wl.replace("f", "s") in lower or wl.replace("ff", "ss") in lower):
        return "long_s", suggs[:3]
    if any(s == wl or s.replace("-", "") == wl for s in lower):
        return "exact_accent_diff", suggs[:3]
    for s, sl in zip(suggs[:3], lower):
        if len(sl) == len(wl) and sum(a != b for a, b in zip(wl, sl)) == 1:
            return "typo_1diff", [s]
    return None


def candidates(errors, everything, limit):
    groups = {}
    for w, info in errors.items():
        hit = classify(w, info, everything)
        if hit:
            # capitalized words are mostly names: list them after the others
            kind = hit[0] + (" (capitalized, often names)" if ELISION.sub("", w)[:1].isupper() else "")
            groups.setdefault(kind, []).append((w, info["total"], hit[1]))
    groups = dict(sorted(groups.items(), key=lambda kv: "capitalized" in kv[0]))
    print(f"Total candidate matches: {sum(len(g) for g in groups.values())}")
    for kind, items in groups.items():
        print(f"\n=== {kind} ({len(items)}) ===")
        for w, total, s in sorted(items, key=lambda x: x[1], reverse=True)[:limit]:
            print(f"  {w:25} ({total:2d}) -> {', '.join(s)}")


def occurrences(w, where):
    pat = re.compile(rf"(?<![{LETTER}]){re.escape(w)}(?![{LETTER}])")
    for vol, no in where:
        for t in french_texts(load(DATA / vol / "normalized" / f"page_{no}.json")):
            if isinstance(t, str):
                t = t.replace("\n", " ")
                for m in pat.finditer(t):
                    yield f"{vol}/{no}", t[max(0, m.start() - 50):m.end() + 50]


def context(volumes, targets, limit):
    """Each target word in its sentence, from the pages the scan noted (all pages if it did not flag it)."""
    errors = load_errors(volumes)
    for w in targets:
        info = errors.get(w)
        where = info["where"] if info else [(v, page_no(p)) for v in volumes for p in pages(v)]
        print(f"\n=== {w} ({info['total']}, sugg: {info['sugg'][:60]})" if info else f"\n=== {w} (not flagged)")
        found = list(islice(occurrences(w, where), limit + 1))
        for loc, snippet in found[:limit]:
            print(f"  {loc}: …{snippet}…")
        if len(found) > limit:
            print(f"  … (--limit to see more)")


def volumes_of(args):
    vols = []
    for a in args:
        if a in BOOKS:
            vols += BOOKS[a]["studium"]
        elif (DATA / a / "normalized").is_dir():
            vols.append(a)
        else:
            sys.exit(f"Unknown volume or book: {a}")
    return vols


def main(argv):
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)    # quiet when piped into head
    limit = 30
    if "--limit" in argv:
        i = argv.index("--limit")
        limit = int(argv[i + 1])
        del argv[i:i + 2]
    show_all = "--all" in argv
    argv = [a for a in argv if a != "--all"]
    if len(argv) < 2 or argv[0] not in ("scan", "inspect", "candidates", "context"):
        sys.exit(__doc__)
    cmd = argv[0]
    if cmd == "context":
        context(volumes_of(argv[1:2]), argv[2:], limit)
        return
    vols = volumes_of(argv[1:])
    if cmd == "scan":
        scan(vols)
    elif cmd == "inspect":
        inspect(*drop_noise(load_errors(vols), show_all))
    else:
        candidates(*drop_noise(load_errors(vols), show_all), limit)


if __name__ == "__main__":
    main(sys.argv[1:])
