"""Tidy verse numbers, commentary references and verse text in normalized/.

  - verse_number: a number only. A verse with no number continues the verse before it
    (top of a page, or one of Jerome's rubrics at the end of a chapter) and takes its
    number; dump_verses.py joins the two. A psalm title gets 0. Empty verses are dropped.
  - verse_ref: digits only ("12", or "12-14" for a range), never null: a block without a
    reference belongs to the verse of the block before it, across pages.
  - latin / french: verse numbers ("12.", "℣. 12.") and marginal dates ("An. 2553.")
    are removed.
  - verse 1: the first word is in small letters after its capital ("EN" -> "En").

Usage: python3 normalize_refs.py [--dry-run] [book ...]   (default: every book)
"""
import hashlib, json, re, sys
from pathlib import Path

from paths import DATA, LLM_CACHE as CACHE, VUL
VUL_FIRST = {re.sub(r"[^a-zà-ÿæœ]", "", v["text"].split()[0].lower())
             for f in VUL.glob("*.json") for c in json.loads(f.read_text())["chapters"]
             for v in c["verses"] if v["verse"] == 1 and v["text"].split()}
ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
PSALM_TITLE = re.compile(r"[\W_]*(In finem|Psalmus|Pſalmus|Ne disperdas|Canticum|Intellectus|Oratio|Alleluia)")
# verses with no number that begin a new verse rather than continue one
MANUAL = {("20_job/page_0113", "Voca ergo, s"): 1, ("21a_psaumes/page_0234", "Notas mihi f"): 11}
NUM = r"(\d+|[IVXLC]+\b|i\b)"


def roman(s):
    total = prev = 0
    for ch in reversed(s):
        v = ROMAN[ch]
        total += -v if v < prev else v
        prev = max(prev, v)
    return total


def as_int(tok):
    if tok.isdigit():
        return int(tok)
    return roman(tok.upper())


def parse_ref(ref):
    """'℣. 14. 15. et 16.' -> ('14-16', ''); '℣. 16. VOCEM QUASI…' -> ('16', 'VOCEM QUASI…');
    'An. 3092.' -> (None, '')."""
    s = (ref or "").strip()
    m = re.match(r"(?:Alors\s+)?(?:[†✟℣]\s*\.?\s*|V\.\s*|Verset\s+|\[|\(\s*)*" + NUM + r"(?=$|[\s.)\]:°-])[.)\]:°]*", s)
    if not m:
        return None, ""
    tok = m.group(1)
    nums = [as_int(tok)]
    rest = s[m.end():]
    while True:
        n = re.match(r"(?:\s*(?:-|\.\.\.|et|,|\(|\)|℣\.?|verset))*\s*(\d+)[.)\]]*", rest)
        if not n:
            break
        nums.append(int(n.group(1)))
        rest = rest[n.end():]
    if not tok.isdigit() and len(nums) > 1:  # "XXXII. 12. 13." = chapter, then verses
        nums = nums[1:]
    elif tok.upper() == "II" and len(nums) == 1:  # often a misread 11
        return "II", rest.strip()
    seq = nums[:1]
    for x in nums[1:]:
        if x <= seq[-1]:
            break
        seq.append(x)
    nums = seq
    if not 0 < nums[0] <= 176:
        return None, ""
    out = str(nums[0]) if len(nums) == 1 else f"{nums[0]}-{nums[-1]}"
    return out, rest.strip()


LEAD = re.compile(r"^(\s*_?)(?:(?:[vV℣]\.?\s*|An\.\s*\d{3,4}\.\s*)?\d{1,3}\s*\.\s+)+")
DATE = re.compile(r",?\s*\b[Aa]n(?:\.|\s+du\s+[Mm]onde)\s*(?:du\s+[Mm]onde\s*)?\d{3,4}\.?(?:\s*avant\s+J\.-\s*C\.\s*\d+\.?)?")


def norm(t):
    return " ".join(re.findall(r"\w+", (t or "").lower().replace("ò", "o").replace("ù", "u").replace("è", "e")))


def clean_text(t):
    t2 = LEAD.sub(r"\1", t)
    t2 = DATE.sub("", t2)
    t2 = LEAD.sub(r"\1", t2.lstrip())
    return re.sub(r"  +", " ", t2).strip() if t2 != t else t


def lower_first_word(t, vulgate_first=None):
    m = re.match(r"([^A-Za-zÀ-ÿŒœÆæ]*)([A-Za-zÀ-ÿŒœÆæ]+)((?:['’][A-Za-zÀ-ÿŒœÆæ]+)?)", t)
    if not m:
        return t
    word, tail = m.group(2), m.group(3)
    if sum(c.isupper() for c in word + tail) < 2:
        return t
    word = word[0] + word[1:].lower()
    if vulgate_first and word.lower() not in vulgate_first:  # drop capital lost: "CCidit" -> "Accidit"
        full = [w for w in vulgate_first if len(w) == len(word) + 1 and w.endswith(word.lower())]
        if len(full) == 1:
            word = full[0].capitalize()
    if tail:
        tail = tail[:2] + tail[2:].lower()
    return m.group(1) + word + tail + t[m.end():]


def main(argv):
    dry = "--dry-run" in argv
    books = [a for a in argv if not a.startswith("--")] or sorted(
        p.parent.name for p in DATA.glob("*/normalized"))
    cache = json.loads(CACHE.read_text(encoding="utf-8"))
    log, warn = [], []
    for book in books:
        last_num, last_ref = None, None
        pages = sorted((DATA / book / "normalized").glob("page_[0-9][0-9][0-9][0-9].json"))
        first_ref = None  # for blocks before any reference in the book
        parsed = []
        for p in pages:
            try:
                parsed.append((p, json.loads(p.read_text(encoding="utf-8"))))
            except json.JSONDecodeError:
                warn.append(f"{book}/{p.name}: malformed JSON, skipped")
        for p, d in parsed:
            for c in d.get("commentary") or []:
                r, _ = parse_ref(str(c.get("verse_ref") or ""))
                if r:
                    first_ref = first_ref or r
        for p, d in parsed:
            where = f"{book}/{p.stem}"
            changed = False
            verses = []
            for v in d.get("verses") or []:
                n = v.get("verse_number")
                if not isinstance(n, int):
                    s = str(n or "").strip()
                    if not (v.get("latin") or "").strip() and not (v.get("french") or "").strip():
                        log.append(f"{where}: dropped empty verse {n!r}")
                        changed = True
                        continue
                    m = re.search(r"\d+", s)
                    if (where, (v.get("latin") or "")[:12]) in MANUAL:
                        new = MANUAL[(where, (v.get("latin") or "")[:12])]
                    elif m:
                        new = int(m.group())
                    elif book.startswith("21") and PSALM_TITLE.match(v.get("latin") or ""):
                        new = 0
                    else:
                        new = last_num
                    log.append(f"{where}: verse_number {n!r} -> {new}  ({(v.get('latin') or '')[:40]})")
                    v["verse_number"] = n = new
                    changed = True
                for k in ("latin", "french"):
                    t = v.get(k) or ""
                    t2 = clean_text(t)
                    if n == 1:
                        t2 = lower_first_word(t2, VUL_FIRST if k == "latin" else None)
                    if t2 != t:
                        log.append(f"{where}: v{n} {k}: {t[:30]!r} -> {t2[:30]!r}")
                        v[k] = t2
                        changed = True
                        if k == "french":
                            cache[hashlib.md5(t2.encode()).hexdigest()] = t2
                    cut = re.search(r"[;:,]\s+(\d{1,3})\.\s+(\S+\s+\S+\s+\S+)", t2)
                    nxt = (d.get("verses") or [])
                    nxt = [w for w in nxt if w.get("verse_number") == int(cut.group(1))] if cut else []
                    if cut and nxt and norm(nxt[0].get(k)).startswith(norm(cut.group(2))):
                        log.append(f"{where}: v{n} {k}: cut text of verse {cut.group(1)} repeated in it")
                        t2 = t2[:cut.start() + 1].rstrip()
                        v[k] = t2
                        changed = True
                    two = re.search(r".{0,25}[;:,]\s+\d{1,3}\.\s+[A-ZÀ-Ý].{0,15}", t2)
                    if two:
                        warn.append(f"{where}: v{n} {k} may hold two verses: …{two.group()}…")
                if isinstance(n, int):
                    last_num = n
                verses.append(v)
            if "verses" in d:
                d["verses"] = verses
            for c in d.get("commentary") or []:
                old = c.get("verse_ref")
                r, rest = parse_ref(str(old or ""))
                if rest and re.search(r"[A-Za-z]{3}", rest):
                    if not (c.get("latin_quote") or "").strip():
                        c["latin_quote"] = rest
                        log.append(f"{where}: lemma moved from verse_ref to latin_quote: {rest[:40]!r}")
                    elif rest.rstrip(" .").upper() not in c["latin_quote"].upper():
                        c["latin_quote"] = rest + " " + c["latin_quote"]
                        log.append(f"{where}: lemma prepended from verse_ref to latin_quote: {rest[:40]!r}")
                if r == "II":
                    prev = int(re.match(r"\d+", last_ref or "0").group())
                    r = "11" if abs(11 - (prev + 1)) < abs(2 - (prev + 1)) else "2"
                    log.append(f"{where}: verse_ref {old!r} read as {r} (previous {last_ref})")
                new = r or last_ref or first_ref or "1"
                if old is not None and not r:
                    log.append(f"{where}: verse_ref {old!r} unreadable -> {new}")
                if old is not None and r and not re.fullmatch(r"\s*℣\. \d+\.\s*|\d+(-\d+)?", str(old)):
                    log.append(f"{where}: verse_ref {old!r} -> {new}")
                if new != old:
                    c["verse_ref"] = new
                    changed = True
                last_ref = new
            if changed and not dry:
                p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    if not dry:
        CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    return log, warn


if __name__ == "__main__":
    log, warn = main(sys.argv[1:])
    print("\n".join(log))
    print("\n--- check by hand ---")
    print("\n".join(warn))
