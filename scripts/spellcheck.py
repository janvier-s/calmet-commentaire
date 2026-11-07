"""Spellcheck the French of a volume with hunspell, then sort what it flags.

  python3 spellcheck.py scan <volume|book> ...        hunspell over every French field
        -> docs/hunspell/<volume>.json:
           {"errors": {word: {"total": n, "sugg": "a, b", "dots": n, "pages": ["0012", ...]}}}
  python3 spellcheck.py inspect <volume|book> ...     long s, -oit/-oient, trémas, frequent words
  python3 spellcheck.py candidates <volume|book> ...  likely errors, grouped by kind [--limit N]
  python3 spellcheck.py context <volume|book> <word> ...  where the words occur [--limit N]
  python3 spellcheck.py ez <volume|book|all> ...      archaic -ez -> -és participles/nouns [--limit N] [--fp] [--apply]
        -> docs/hunspell/<volume>_ez.json (or updates normalized/ pages with --apply)

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
from paths import DATA, DOCS, HUNSPELL_CACHE, HUNSPELL_DICT, LLM_CACHE, SCRIPTS, load, pages, volumes_of

OUT = DOCS / "hunspell"
NAMES = SCRIPTS / "spellcheck_names.txt"

LETTER = "A-Za-zÀ-ÖØ-öø-ÿœŒæÆ"
WORD = re.compile(rf"[{LETTER}]+(?:['’][{LETTER}]+)*")
HYPHENATED = re.compile(rf"([{LETTER}]+)-\s*$")          # a word the printer broke at the end of a page
CALL = re.compile(r"\^\{[^}]*\}")
UNSURE = re.compile(r"\[(?:UNCERTAIN[^\]]*|ILLEGIBLE)\]")    # transcription placeholders
ACCENT = re.compile(r"[éèêëàâîïôûùüç]", re.I)
MARKUP = re.compile(r"[_*#`]")
NUMBER = re.compile(r"\b\d+([,.:]\d+)*\b")
ELISION = re.compile(r"^(?:qu|[dljcsnmt])['’]", re.I)
GRAVE = str.maketrans("àèìòù", "aeiou")
# The spellings of Calmet's time that the modernization missed, as (old, modern) letter groups:
# azyle -> asile, hazard -> hasard, isle -> île, enfans -> enfants, appeller -> appeler, vûe -> vue
OLD_SPELLINGS = [("y", "i"), ("z", "s"), ("s", "z"), ("ans", "ants"), ("ens", "ents"), ("ll", "l"),
                 ("tt", "t"), ("pp", "p"), ("mm", "m"), ("nn", "n"), ("rr", "r"), ("l", "ll"), ("t", "tt"),
                 ("es", "ê"), ("is", "î"), ("os", "ô"), ("as", "â"), ("us", "û"), ("ë", "e"), ("ü", "u"),
                 ("ë", "é"), ("û", "u"), ("ô", "o"), ("î", "i"), ("â", "a"), ("ê", "e"), ("ê", "è"), ("é", "è"),
                 ("è", "é"), ("e", "é"), ("e", "è"), ("sç", "s"), ("th", "t"), ("ay", "ai"), ("oy", "oi"),
                 ("ai", "oi"), ("oi", "ai"), ("ez", "és"), ("c", "qu"), ("qu", "c"), ("x", "s"), ("s", "x")]
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
    return NUMBER.sub(" ", MARKUP.sub(" ", CALL.sub(" ", UNSURE.sub(" ", text.replace("\xad", "")))))


def words(text):
    """(word, followed by a full stop) for each word of text. A word with two apostrophes
    loses its elision (jusqu'aujourd'hui -> aujourd'hui: hunspell knows only the second)."""
    text = clean(text)
    out = []
    for m in WORD.finditer(text):
        w = m.group()
        if len(re.findall("['’]", w)) > 1:
            w = re.sub(r"^[^'’]+['’]", "", w)
        out.append((w, text[m.end():m.end() + 1] == "."))
    return out


def volume_texts(vol):
    """(page number, French texts) for each page of vol, with the words the printer broke
    across a page turn put back together ("re-" / "vient de" -> "revient de"), as calmet.py
    sews them; if the next page reprints the whole word ("con-" / "concupiscence"), the
    fragment goes. A fragment ending a field inside a page (a note cut short) is left out."""
    out = []
    for p in pages(vol):
        out.append((page_no(p), [t for t in french_texts(load(p)) if isinstance(t, str) and t.strip()]))
    for i, (_, texts) in enumerate(out):
        for j, t in enumerate(texts):
            m = HYPHENATED.search(t)
            if not m:
                continue
            texts[j] = t[:m.start()]
            nxt = out[i + 1][1] if j == len(texts) - 1 and i + 1 < len(out) else []
            if nxt and nxt[0].lstrip()[:1].islower():
                head = nxt[0].lstrip()
                first = WORD.match(head)
                if first and first.group().lower().startswith(m.group(1).lower()):
                    continue
                nxt[0] = m.group(1) + head
    return out


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
        vol_pages = volume_texts(vol)
        for no, texts in vol_pages:
            for t in texts:
                for w, dot in words(t):
                    c[w] += 1
                    dots[w] += dot
                    where.setdefault(w, []).append(no)
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
        elif not ACCENT.search(wl.translate(GRAVE)) and _fold(wl.translate(GRAVE)) in latin:
            why[w] = "Latin"    # with Calmet's grave accents too: cùm, quàm, ità
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


def classify_all(w, info, everything):
    """classify, then for what it leaves: an old spelling whose modern form is in the text."""
    hit = classify(w, info, everything)
    if hit or len(bare(w)) <= 3:
        return hit
    modern = old_spelling(bare(w))
    if not modern:
        return None
    head = w[:len(w) - len(bare(w))]                    # the elided article, as written
    if w[len(head):][:1].isupper():
        modern = modern[:1].upper() + modern[1:]
    return "old_spelling", [head + modern + " (in the text)"]


@lru_cache(maxsize=None)
def bare_french_words():
    return frozenset(bare(w) for w in french_words())


def old_spelling(wl):
    """The modern word wl is, one or two old letter groups changed (OLD_SPELLINGS), if hunspell
    knows it from the text; None if none or several."""
    known = bare_french_words()

    def step(w):
        for old, new in OLD_SPELLINGS:
            i = w.find(old)
            while i >= 0:
                yield w[:i] + new + w[i + len(old):]
                i = w.find(old, i + 1)

    first = set(step(wl))
    found = {v for v in first if v in known}
    if not found:
        found = {v2 for v in first for v2 in step(v) if v2 in known}
    found.discard(wl)
    return found.pop() if len(found) == 1 else None


def candidates(errors, everything, limit):
    groups = {}
    for w, info in errors.items():
        hit = classify_all(w, info, everything)
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


# --- archaic -ez -> -és scan (valid in hunspell as 2p verbs / "nez", so missed by plain scan) ---

ETRE_PL = (r"(?:sont|étaient|étoient|furent|seront|seraient|seroient|soient|fussent|"
           r"sommes|étions|fûmes|fumes|êtes|étiez|fûtes|futes|serez|soyez|être|étant|été|feront|"
           r"deviendront|deviennent|devenus|devenez)")
AVOIR_COD = (r"(?:(?:les|nous|vous|que(?:\s+(?:le|la|les|ce|cet|cette|ces|mon|ton|son|notre|votre|leur|mes|tes|ses|nos|vos|leurs))?(?:\s+[a-zà-ÿ]+){0,2}|qu['’]\s*(?:il|ils|elle|elles|on|un|[a-zà-ÿ]+))\s+"
             r"(?:n['’]|ne\s+)?(?:en\s+|y\s+|vous\s+|nous\s+|les\s+|lui\s+|leur\s+)?(?:ont|avaient|avoient|eurent|auront|auraient|"
             r"auroient|aient|ayent|eussent|avons|avions|avez|aviez|aurez|ayez|avoir|ayant|"
             r"a|avait|avoit|eut|aura|aurait|auroit|ait|eût|ai|avais|avois))")
STATE_PL = (r"(?:(?<!au\s)(?<!Au\s)(?:tient|tiennent|tenait|tenoient|tenaient|tint|tinrent|"
            r"demeurent|demeuraient|demeureront|demeurer|restent|restaient|resteront|paraissent|semblent|"
            r"trouvent|trouvaient|trouvé|trouvés|trouvez|voient|voyaient|virent|rendent|rendaient|laissent|laissaient)"
            r"(?:\s+(?:les\s+[a-zà-ÿ]+|leurs\s+[a-zà-ÿ]+|des\s+[a-zà-ÿ]+|[a-zà-ÿ]+))?)")
ADV = (r"(?:tout\s+d['’]un\s+coup|plus|moins|si|fort|bien|mal|très|tout|tous|toutes|souvent|toujours|jamais|point|"
       r"pas|autrefois|dès-lors|encore|ainsi|aussi|même|eux-mêmes|entièrement|éternellement|"
       r"heureusement|proprement|fortement|étroitement|ensemble|déjà|bientôt|presque|comme|"
       r"donc|peut-être|quelquefois|pourtant|cependant|néanmoins|enfin|aussitôt|peu|tant|"
       r"trop|assez|ici|là|y|en|[a-zà-ÿ]+ment)")
AUX_CHAIN = (rf"(?:\b(?:{ETRE_PL}|{AVOIR_COD}|{STATE_PL})\b(?:\s+{ADV})*"
             rf"(?:\s+[a-zà-ÿ]+(?:és|ez|is|us|ts)(?:\s+(?:à|au|aux|de|du|des|dans|en|par|pour|sur|sous|avec|sans)\s+(?:la\s+|le\s+|les\s+|l['’]|un\s+|une\s+)?[a-zà-ÿ]+)?\s*(?:,\s*)?(?:(?:et|ou|ni)\s+)?(?:\s*{ADV}\s*)*)*)")
PLURAL_NP = (
    r"(?:"
    r"\b(?:les|des|aux|ces|ses|mes|tes|nos|vos|leurs|plusieurs|quelques|tous|autres|premiers|"
    r"nouveaux|anciens|grands|petits|bons|mauvais|faux|vrais|saints|mêmes|tels|quels|"
    r"deux|trois|quatre|cinq|six|sept|huit|neuf|dix|cent|mille\s+de)\s+(?:[a-zà-ÿ]+(?:s|x)\s+){1,3}"
    r"(?:(?:bien|mal|plus|moins|si|fort|très|tout|tous|souvent|toujours|encore|ainsi|aussi|même|déjà|presque|comme|[a-zà-ÿ]+(?:és|ez|is|us|ts)\s*,?)\s+)*"
    r"|(?<!\bet\s)(?<!\bou\s)(?<!\bmais\s)\b(?:les|des|aux|ces|ses|mes|tes|nos|vos|leurs|plusieurs|quelques|tous|autres)\s+"
    r"|\b(?:des|aux)\s+"
    r")"
)
POS_EZ_BEFORE = re.compile(rf"(?:{AUX_CHAIN}|{PLURAL_NP})\s*$", re.I)
APPOS_NP_BEFORE = re.compile(
    r"\b(?:les|des|aux|ces|ses|mes|tes|nos|vos|leurs|plusieurs|quelques|tous|autres)\s+(?:[a-zà-ÿ]+(?:s|x)\s+){1,3},\s*"
    r"(?:(?:[a-zà-ÿ]+(?:és|ez|is|us|ts)\s*,\s*(?:et\s+)?)*)$",
    re.I
)
APPOS_EZ_AFTER = re.compile(
    r"^\s*(?:[,.;:!?)]|\b(?:par|de|du|d['’]|dans|à|au|aux|en|sur|sous|avec|sans|pour|contre|entre|vers|chez|selon|comme|depuis|pendant|après|avant|ici|et|ou)\b)",
    re.I
)
IMMED_ETRE = re.compile(rf"\b{ETRE_PL}\b(?:\s+{ADV})*\s*$", re.I)
VOUS_VERB_SPAN = re.compile(
    r"^\s*(?:ne\s+|n['’]\s*)?(?:me\s+|m['’]\s*|te\s+|t['’]\s*|se\s+|s['’]\s*|le\s+|la\s+|les\s+|l['’]\s*|nous\s+|vous\s+|lui\s+|leur\s+|y\s+|en\s+)*"
    rf"(?:{ADV}\s+)*$",
    re.I
)
EZ_TOKEN = re.compile(rf"(?<![{LETTER}-])([{LETTER}]+(?:-[{LETTER}]+)*ez)(?![{LETTER}-])")

NEVER_ES = {
    "assez", "chez", "rez", "avez", "aviez", "aurez", "ayez",
    "serez", "soyez", "étiez", "ferez", "feriez", "direz", "diriez",
    "irez", "iriez", "viendrez", "verrez", "voudrez", "voulez", "vouliez",
    "pouvez", "pouviez", "pourrez", "savez", "saviez", "saurez",
    "devez", "deviez", "devrez", "allez", "venez", "tenez", "prenez",
    "comprenez", "apprenez", "entreprenez", "craignez", "joignez",
    "peignez", "feignez", "atteignez", "éteignez", "ceignez", "plaignez",
    "oignez", "buvez", "recevez", "apercevez", "concevez", "décevez",
    "mouvez", "pleuvez", "vivez", "suivez", "écrivez", "serviez",
    "sortez", "partez", "dormez", "mentez", "sentez", "repentez",
    "ouvrez", "couvrez", "offrez", "souffrez", "cueillez", "assaillez",
    "bouillez", "mourez", "mourrez", "courez", "courrez", "secourez",
    "acquérez", "conquérez", "requérez", "asseyez", "voyez", "croyez",
    "fuyez", "oyez", "riez", "conduisez", "instruisez", "détruisez",
    "produisez", "réduisez", "séduisez", "traduisez", "luisez", "nuisez",
    "cuisez", "lisez", "élisez", "plaisiez", "taisez", "faisez", "disiez",
    "connaissez", "paraissez", "naissez", "paissez", "croissez", "haïssez",
    "mettez", "permettez", "promettez", "commettez", "soumettez", "remettez",
    "admettez", "omettez", "transmettez", "battez", "combattez", "abattez",
    "rompez", "corrompez", "interrompez", "poursuivez", "vainquez", "convainquez",
    "rendez", "vendez", "pendez", "tendez", "étendez", "entendez", "attendez",
    "défendez", "descendez", "fendez", "répandez", "répondez", "confondez",
    "tondez", "fondez", "mordez", "perdez", "tordez", "puissiez", "fussiez",
    "eussiez", "faisiez", "voyiez", "croyiez", "sachiez", "veuillez",
    "daignez", "fez", "suez", "jabez", "pharez", "suarez", "alvarez", "sanchez",
    "vasquez", "valez", "gomez", "lopez", "perez", "abez", "remez", "éliez",
    "cortez", "rodanez", "bouez", "renez",
}
ER_EREZ_STEMS = (
    "espérez", "considérez", "modérez", "préférez", "référez", "différez", "conférez",
    "altérez", "tempérez", "vénérez", "libérez", "opérez", "insérez", "exagérez",
    "digérez", "suggérez", "tolérez", "accélérez", "énumérez", "rémunérez", "délibérez",
    "avérez", "persévérez", "révérez", "ulcérez", "lacérez", "macérez", "incarcérez",
    "désespérez", "coopérez", "récupérez", "exaspérez", "prospérez", "réinsérez",
    "adultérez", "oblitérez", "réitérez", "dégénérez", "régénérez", "pondérez",
    "confédérez", "inférez", "proférez", "transférez", "inconsidérez",
)


def classify_ez(w, t, start, end, unconditional):
    """(is_archaic_es, reason) for an occurrence of an -ez word at t[start:end]."""
    wl = w.lower()
    if start == 0 and w[0].islower():
        return False, "page-turn fragment"
    if w in unconditional:
        return True, "unconditional (-ez not a verb)"
    before = t[max(0, start - 100):start]
    after = t[end:min(len(t), end + 60)]
    b_clean = re.sub(r"\^\{[^}]*\}|[_*]", " ", before)
    a_clean = re.sub(r"\^\{[^}]*\}|[_*]", " ", after)
    clause_before = re.split(r"[.;:!?«»]", b_clean)[-1]

    if re.match(r"^\s*-(?:vous|le|la|les|moi|nous|lui|leur|y|en)\b", a_clean, re.I):
        return False, "imperative/inverted pronoun"
    if wl == "nez":
        if re.search(r"\b(?:le|du|au|aux|un|son|mon|ton|votre|vôtre|notre|nôtre|leur|leurs|les|des|ces|ni)\s+$", b_clean, re.I):
            return False, "nose (determiner)"
        if re.match(r"^\s*(?:tortu|camus|écrasé|coupé|plat|aquilin|long|court|en\s+fut|fumera)", a_clean, re.I):
            return False, "nose (adj/verb)"
        return True, "nés (born)"

    vous_matches = list(re.finditer(r"\bvous\b", clause_before, re.I))
    if vous_matches:
        inter = clause_before[vous_matches[-1].end():]
        if VOUS_VERB_SPAN.match(inter):
            return False, "2p vous subject"

    if re.search(r"\bqui\s+(?:ne\s+|n['’]\s*|les\s+|la\s+|le\s+|l['’]|en\s+|y\s+|vous\s+|nous\s+|me\s+|m['’]|se\s+|s['’])*$", clause_before, re.I):
        return False, "qui + 2p verb"

    if re.search(r"\b(?:ne|n['’])\s*(?:me\s+|m['’]\s*|te\s+|t['’]\s*|se\s+|s['’]\s*|la\s+|les\s+|le\s+|l['’]\s*|vous\s+|nous\s+|lui\s+|leur\s+|en\s+|y\s+)*$", clause_before, re.I):
        return False, "negative imperative/2p"

    has_direct_obj = bool(re.match(
        r"^\s+(?:le|la|les|l['’]|un|une|ce|cet|cette|ces|mon|ton|son|notre|votre|leur|"
        r"mes|tes|ses|nos|vos|leurs|tous\s+les|toutes\s+les|tout\s+le|toute\s+la|toutes\s+choses|tout\s+ce)\b",
        a_clean, re.I
    ))
    if has_direct_obj and not re.search(r"\b(?:tenait|tenaient|tient|tiennent)\s+$", clause_before, re.I) and not IMMED_ETRE.search(clause_before):
        return False, "active verb + direct object"

    if POS_EZ_BEFORE.search(clause_before):
        return True, "participle/noun"

    if not re.search(r",\s*_\s*$", before) and APPOS_NP_BEFORE.search(clause_before) and APPOS_EZ_AFTER.search(a_clean):
        return True, "appositive participle"

    return False, "imperative/2p verb (no plural/aux context)"


def _build_ez_maps(all_ez):
    cands_to_check = set()
    es_candidates = {}
    ez_variants = {}
    for w in all_ez:
        wl = w.lower()
        if wl.endswith(("issez", "erez", "irez", "drez")) and not wl.endswith(ER_EREZ_STEMS):
            continue
        cands = [w[:-2] + "és", wl[:-2] + "és"]
        ez_vars = [w, wl]
        stem = w[:-2]
        for m in re.finditer(r"e(?=[^aeiouyéèêëàâîïôûùü]{1,3}$)", stem, re.I):
            rep = "É" if stem[m.start()].isupper() else "é"
            acc_stem = stem[:m.start()] + rep + stem[m.start() + 1:]
            cands.append(acc_stem + "és")
            ez_vars.append(acc_stem + "ez")
            ez_vars.append(acc_stem.lower() + "ez")
        es_candidates[w] = cands
        ez_variants[w] = ez_vars
        cands_to_check.update((*ez_vars, *cands))

    unknown = check(sorted(cands_to_check))
    names, latin = known_names(), vulgate_words()

    valid_replacement = {}
    unconditional = set()
    for w, cands in es_candidates.items():
        wl = w.lower()
        if wl in names or _fold(wl) in latin:
            continue
        good = [c for c in cands if c not in unknown]
        if not good:
            continue
        best = good[0]
        if w[0].isupper() and best[0].islower():
            best = best[0].upper() + best[1:]
        valid_replacement[w] = best
        # Only unconditional if NO -ez variant (even with restored accent on stem) is a known verb in hunspell,
        # OR if it is a hyphenated compound (premiers-nez, bien-aimez, nouveau-nez)
        any_ez_known = any(v not in unknown for v in ez_variants[w])
        if (not any_ez_known and len(wl) >= 4) or "-" in w:
            unconditional.add(w)
    return valid_replacement, unconditional


def _replace_ez_in_text(t, valid_replacement, unconditional):
    if not t or not isinstance(t, str):
        return t, 0
    count = 0

    def _repl(m):
        nonlocal count
        w = m.group(1)
        if w not in valid_replacement:
            return w
        ok, _ = classify_ez(w, t, m.start(), m.end(), unconditional)
        if ok:
            count += 1
            return valid_replacement[w]
        return w

    new_t = EZ_TOKEN.sub(_repl, t)
    return new_t, count


def scan_ez(volumes, limit=30, show_fp=False, apply=False):
    """Scan volumes for archaic -ez words that should be -és, excluding 2p verbs and 'le nez'."""
    vol_occurrences = {}
    all_ez = Counter()
    for vol in volumes:
        occ = []
        for p in pages(vol):
            no = page_no(p)
            for t in french_texts(load(p)):
                if t and isinstance(t, str):
                    for m in EZ_TOKEN.finditer(t):
                        w = m.group(1)
                        if w.lower() not in NEVER_ES and not w.isupper() and len(w) >= 3:
                            all_ez[w] += 1
                            occ.append((no, w, t, m.start(), m.end()))
        vol_occurrences[vol] = occ

    valid_replacement, unconditional = _build_ez_maps(all_ez)

    OUT.mkdir(parents=True, exist_ok=True)
    merged_hits = Counter()
    merged_fp = Counter()
    examples = {}
    fp_examples = {}
    pages_updated = 0
    replacements_applied = 0
    llm_cache = None
    if apply:
        import hashlib
        try:
            llm_cache = json.loads(LLM_CACHE.read_text(encoding="utf-8")) if LLM_CACHE.exists() else {}
        except Exception:
            llm_cache = None

    for vol, occ in vol_occurrences.items():
        vol_words = {}
        for no, w, t, start, end in occ:
            if w not in valid_replacement:
                continue
            ok, why = classify_ez(w, t, start, end, unconditional)
            snippet = t[max(0, start - 35):min(len(t), end + 35)].replace("\n", " ")
            if ok:
                merged_hits[w] += 1
                examples.setdefault(w, []).append((f"{vol}/{no}", why, snippet))
                entry = vol_words.setdefault(w, {"replacement": valid_replacement[w], "total": 0, "fp_skipped": 0, "pages": []})
                entry["total"] += 1
                if no not in entry["pages"]:
                    entry["pages"].append(no)
            else:
                merged_fp[w] += 1
                fp_examples.setdefault(w, []).append((f"{vol}/{no}", why, snippet))
                if w in vol_words:
                    vol_words[w]["fp_skipped"] += 1
        out = OUT / f"{vol}_ez.json"
        out.write_text(json.dumps({"ez_errors": dict(sorted(vol_words.items()))}, ensure_ascii=False, indent=2), encoding="utf-8")

        if apply:
            vol_page_cnt = 0
            vol_repl_cnt = 0
            for p in pages(vol):
                d = load(p)
                changed = False
                for k in TOP_FIELDS:
                    v = d.get(k)
                    if v and isinstance(v, str):
                        v2, n_rep = _replace_ez_in_text(v, valid_replacement, unconditional)
                        if n_rep:
                            d[k] = v2
                            if llm_cache is not None and k == "chapter_summary":
                                llm_cache[hashlib.md5(v2.encode()).hexdigest()] = v2
                            vol_repl_cnt += n_rep
                            changed = True
                for v in d.get("verses", []):
                    s = v.get("french")
                    if s and isinstance(s, str):
                        s2, n_rep = _replace_ez_in_text(s, valid_replacement, unconditional)
                        if n_rep:
                            v["french"] = s2
                            if llm_cache is not None:
                                llm_cache[hashlib.md5(s2.encode()).hexdigest()] = s2
                            vol_repl_cnt += n_rep
                            changed = True
                for fn in d.get("footnotes", []):
                    s = fn.get("text")
                    if s and isinstance(s, str):
                        s2, n_rep = _replace_ez_in_text(s, valid_replacement, unconditional)
                        if n_rep:
                            fn["text"] = s2
                            vol_repl_cnt += n_rep
                            changed = True
                for c in d.get("commentary", []):
                    for k in ("french_translation", "french_commentary"):
                        s = c.get(k)
                        if s and isinstance(s, str):
                            s2, n_rep = _replace_ez_in_text(s, valid_replacement, unconditional)
                            if n_rep:
                                c[k] = s2
                                if llm_cache is not None:
                                    llm_cache[hashlib.md5(s2.encode()).hexdigest()] = s2
                                vol_repl_cnt += n_rep
                                changed = True
                if changed:
                    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
                    vol_page_cnt += 1
            pages_updated += vol_page_cnt
            replacements_applied += vol_repl_cnt
            if vol_page_cnt:
                print(f"  {vol}: updated {vol_page_cnt} pages ({vol_repl_cnt} replacements)", flush=True)

    if apply and llm_cache is not None and replacements_applied:
        LLM_CACHE.write_text(json.dumps(llm_cache, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Scanned {len(volumes)} volume(s): {sum(merged_hits.values())} archaic -ez occurrences "
          f"across {len(merged_hits)} distinct words ({sum(merged_fp.values())} verb/nose false positives excluded)")
    if apply:
        print(f"Applied {replacements_applied} replacements across {pages_updated} pages.")
    for w, cnt in merged_hits.most_common(limit):
        rep = valid_replacement[w]
        fp_cnt = merged_fp[w]
        loc, why, snip = examples[w][0]
        print(f"  {w:22} -> {rep:22} (archaic: {cnt:3d}, fp skipped: {fp_cnt:3d}) | {loc}: …{snip}…")
        if show_fp and fp_examples.get(w):
            floc, fwhy, fsnip = fp_examples[w][0]
            print(f"      [FP skipped ({fwhy})]: {floc}: …{fsnip}…")


def main(argv):
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)    # quiet when piped into head
    limit = 30
    if "--limit" in argv:
        i = argv.index("--limit")
        limit = int(argv[i + 1])
        del argv[i:i + 2]
    show_all = "--all" in argv
    show_fp = "--fp" in argv
    apply = "--apply" in argv
    argv = [a for a in argv if a not in ("--all", "--fp", "--apply")]
    if len(argv) < 2 or argv[0] not in ("scan", "inspect", "candidates", "context", "ez"):
        sys.exit(__doc__)
    cmd = argv[0]
    if cmd == "context":
        context(volumes_of(argv[1:2]), argv[2:], limit)
        return
    vols = volumes_of(argv[1:])
    if cmd == "scan":
        scan(vols)
    elif cmd == "ez":
        scan_ez(vols, limit, show_fp, apply)
    elif cmd == "inspect":
        inspect(*drop_noise(load_errors(vols), show_all))
    else:
        candidates(*drop_noise(load_errors(vols), show_all), limit)


if __name__ == "__main__":
    main(sys.argv[1:])
