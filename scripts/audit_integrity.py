"""Integrity audit of the Calmet commentary: source pages (STUDIUM normalized) and
what the website actually serves (dom-calmet-web raw + calmet JSON).

Usage: python3 audit_integrity.py [out.json]
Read-only: writes nothing but the JSON result.
"""
import functools, hashlib, json, re, sys, statistics
from collections import Counter, defaultdict
from pathlib import Path

from chapter_refs import REF as CH_REF, write as chapter_write
from continuations import ABBREV, LEMMA_START, opens_with_capital, sentence_ended, start_missing, strip_calls
from calmet import STRAY, _fold, notes as calmet_notes, vulgate_words
from export import chapter_of, verses_by_chapter
from modernize_refs import MANUAL as REF_MANUAL
from paths import BOOKS, DATA as STUDIUM, DOCS, VUL, WEB as SITE
from review_store import FalsePositives, fp_sig
ORDER_OK = json.loads((STUDIUM / "verse_ref_order_ok.json").read_text(encoding="utf-8")) \
    if (STUDIUM / "verse_ref_order_ok.json").exists() else {}  # fix_verse_refs.py: out of order on purpose
WHICH_BOOK = re.compile(r"\b(?:Rois|Paralipomènes|Machabées|Esdras),?\s+chapitres?\s+\d+(?::\d+(?:(?:-|, )\d+)*)?")
# In a french_translation, these words betray commentary or a variant reading rather than the verse:
# “l'hébreu”, “à la lettre”, “Septante”, “c'est-à-dire”, and the alternative “ou” (but not “où”).
TRANSLATION_COMMENTARY = re.compile(
    r"\bl['’]\s?h[ée]breu|\bà\s+la\s+lettre\b|\bSeptante\b|\bc['’]est[-\s][aà][-\s]dire\b|(?<!\w)ou(?!\w)", re.I)


def translation_markers(text):
    """The commentary / variant markers in a french_translation, in reading order, without repeats."""
    out, seen = [], set()
    for m in TRANSLATION_COMMENTARY.finditer(text or ""):
        low = m.group(0).lower()
        if low not in seen:
            seen.add(low)
            out.append(m.group(0))
    return out


def stray_underscore(text):
    """The first "_" of `text` out of place, as (its index, what is wrong), or None. Each "_" opens
    italics (a word follows it, after a space, a bracket or "…") or closes them (straight after a word
    or a stop); one that opens while they are open, or closes while they are closed, is out of place,
    and italics still open at the end are the last opener's."""
    opened = None
    for m in re.finditer("_", text):
        i = m.start()
        prev = text[i - 1] if i else " "
        nxt = text[i + 1] if i + 1 < len(text) else " "
        opener = i == 0 or prev.isspace() or prev in "([«\"“‘'’…"
        if opened is None:
            if not opener:
                return i, "“_” closing italics that were not opened"
            opened = i
        elif not opener or nxt.isspace() or nxt in ".,;:!?)»”":
            opened = None
        else:
            return i, "“_” opening italics while they are open (a closing “_” missing before it?)"
    return None if opened is None else (opened, "italics opened here and never closed")


def reviews():
    """Every book's review (data/<book>/review.json, review_store.Progress): statuses and false positives."""
    out = []
    for f in sorted(STUDIUM.glob("*/review.json")):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
    return out


# False positives tagged in the review editor: permanently excluded from review queue on every audit run
def load_false_positives():
    fp_ids = set()
    fp_sigs = []
    for d in reviews():
        fps = d.get("false_positives") or {}
        for k, v in fps.items():
            fp_ids.add(k)
            parts = k.split("/")
            if len(parts) >= 3:
                vol, pg_s, kind = parts[0], parts[1], parts[2]
                pg = int(pg_s) if pg_s.isdigit() else 0
                msg = v.get("msg") if isinstance(v, dict) else ""
                where = v.get("where") if isinstance(v, dict) else None
                fp_sigs.append(fp_sig(vol, pg, kind, msg, where))
        for k, v in (d.get("status") or {}).items():
            if v == "false_positive":
                fp_ids.add(k)
                parts = k.split("/")
                if len(parts) >= 3:
                    vol, pg_s, kind = parts[0], parts[1], parts[2]
                    pg = int(pg_s) if pg_s.isdigit() else 0
                    fp_sigs.append(fp_sig(vol, pg, kind, ""))
    return FalsePositives(fp_ids, fp_sigs)


FP_IDS = load_false_positives()

# --- archaic spelling markers (French) -------------------------------------
OK_OIT = set("""soit doit voit croit droit toit endroit étroit exploit adroit maladroit reçoit aperçoit
conçoit perçoit déçoit prévoit pourvoit revoit entrevoit soient voient croient emploient envoient
déploient noient foudroient côtoient aboient rudoient nettoient tutoient renvoient octroient broient
prévoient pourvoient revoient entrevoient guerroient flamboient larmoient verdoient ondoient
chatoient festoient fourvoient convoient louvoient apitoient coudoient fois bois trois mois vois crois
dois rois lois pois autrefois quelquefois toutefois parfois chamois carquois françois sournois courtois
bourgeois villageois patois minois putois envois convois renvois emplois choix voix poids""".split())
ARCHAIC = [
    ("ſ", re.compile(r"ſ")),
    ("&", re.compile(r"&")),
    ("-oit/-oient/-ois", re.compile(r"\b\w+(?:oit|oient|ois)\b", re.I)),
    ("oü (loüer, joüir)", re.compile(r"oü", re.I)),
    ("sç (sçavoir)", re.compile(r"sç", re.I)),
    ("connoître/paroître", re.compile(r"\b\w*(?:conno|paro|compar?o)[iî]t?\w*", re.I)),
    ("-ens/-ans plurals (enfans, tems)", re.compile(
        r"\b(?:\w+(?:emens|amens)|enfans|parens|tems|habitans|vivans|présens|innocens|différens|"
        r"puissans|serpens|talens|momens|sentimens|jugemens|commandemens)\b", re.I)),
    ("joye/voye", re.compile(r"\b(?:joye|voye|monnoye|proye)s?\b", re.I)),
    ("Pseaume", re.compile(r"\bPseaume", re.I)),
]
# "Esther 15:16*", "Isaïe* 49:16*", "et 13*" (modernize_refs.py, footnotes.py)
_VV = r"\d+:\d+(?:(?:-|,\s?)\d+)*"
GUESSED_REF = re.compile(rf"(?:(?:[1-4] )?[A-ZÉ][a-zéèëïô]+(?: des cantiques)?\*? )?{_VV}\*"
                         rf"|(?:[1-4] )?[A-ZÉ][a-zéèëïô]+\* {_VV}|(?<=et )\d+\*")
LATIN_OLD = [("ſ", re.compile(r"ſ")), ("&", re.compile(r"&")),
             ("accented (cùm, à)", re.compile(r"[àèìòùáíóú]"))]


def archaic_hits(text):
    out = Counter()
    for name, rx in ARCHAIC:
        for m in rx.finditer(text or ""):
            if name.startswith("-oit") and m.group(0).lower() in OK_OIT:
                continue
            if name.startswith("connoître") and not re.search(r"o[iî]", m.group(0)[-6:]):
                continue
            out[name] += 1
    return out


def words(text):
    return len(re.findall(r"\w+", text or ""))


def flat(s):
    """Text reduced for cross-file matching: no markers, italics or spacing."""
    s = re.sub(r"\^\{[^}]*\}|\[\d+\]|[_*]", "", s or "")
    return re.sub(r"[^a-zà-ÿœæç]", "", s.lower())


@functools.cache
def word_case_counts():
    """{word: [times in lower case, times capitalised mid-sentence]} over all the commentary, to tell
    a name (Ézéchiel, Hérodote: only ever capitalised) from a common word (Si, On: capitalised only
    because a sentence starts with it)."""
    counts = defaultdict(lambda: [0, 0])
    for f in STUDIUM.glob("*/normalized/page_[0-9][0-9][0-9][0-9].json"):
        d, err = load(f)
        for c in (d or {}).get("commentary") or []:
            text = re.sub(r"\^\{[^}]*\}|[_*]", "", c.get("french_commentary") or "")
            for m in re.finditer(r"[^\W\d_]+", text):
                w = m.group()
                before = text[:m.start()].rstrip(" «\"“‘'’(")
                if w[0].islower():
                    counts[w][0] += 1
                elif before and before[-1] not in ".!?:;»" and not w.isupper():
                    counts[w.lower()][1] += 1
    return counts


def proper_noun_start(text):
    """Does `text` open with a name? Its first word is capitalised mid-sentence more often than not
    in lower case ("L'Homme" is read as "L": the article, a common word)."""
    m = re.match(r"[\s_«\"“(]*([^\W\d_]+)", re.sub(r"^\s*\^\{[^}]*\}", "", text or ""))
    if not m:
        return False
    lower, cap_mid = word_case_counts().get(m.group(1).lower(), (0, 0))
    return cap_mid > lower


def first_note_without_lemma(tail, fc):
    """The first note of a page with neither latin_quote nor french_translation, `tail` being the end
    of the previous page's last comment: "lemma" if it opens with the lemma in capitals, "sentence" if
    the page before ended a sentence and this opens a new one that is not a name (a new note, or the
    next sentence of the same one: only a reader can tell), else None (it goes on from the page before,
    or the word is broken at the page turn, hyphen_cut's)."""
    if not fc.strip() or strip_calls(tail).endswith("-"):
        return None
    if LEMMA_START.match(fc):
        return "lemma"
    if sentence_ended(tail) and opens_with_capital(fc) and not proper_noun_start(fc):
        return "sentence"
    return None


def load(p):
    try:
        return json.loads(p.read_text(encoding="utf-8")), None
    except Exception as e:
        return None, str(e)[:80]


def site_slugs():
    m = {}
    for d in (SITE / "raw").iterdir():
        f = d / "chapter_01.json"
        if f.exists():
            m[json.loads(f.read_text())["book"]] = d.name
    return m



def lemma_added(vol, name):
    """Blocks of this page that had no latin_quote in some committed version and have one now
    (the no_lemma issues resolved by hand): {their french_commentary then}."""
    if not hasattr(lemma_added, "found"):
        lemma_added.found = _lemma_added_all()
    return lemma_added.found.get(f"{vol}/normalized/{name}", set())


def _lemma_added_all():
    """lemma_added for every page with a resolved no_lemma issue at once: one git log for their
    history, one git cat-file for all the old versions (a git process per version took half a minute)."""
    import subprocess
    done = {k: v for d in reviews() for k, v in (d.get("status") or {}).items()}
    paths = sorted({f"{vol}/normalized/page_{no}.json" for vol, no in
                    (k.split("/")[:2] for k, v in done.items() if "/no_lemma/" in k and v == "resolved")})
    if not paths:
        return {}
    # data/ is a folder of the repository: --relative and ./ keep paths as they are here
    log = subprocess.run(["git", "-C", str(STUDIUM), "log", "--format=@%H", "--name-only", "--relative", "--", *paths],
                         capture_output=True, text=True).stdout
    wanted, h = [], None
    for line in log.splitlines():
        if line.startswith("@"):
            h = line[1:]
        elif line.strip() in paths:
            wanted.append((h, line.strip()))
    cat = subprocess.run(["git", "-C", str(STUDIUM), "cat-file", "--batch"], capture_output=True,
                         input="".join(f"{h}:./{p}\n" for h, p in wanted).encode()).stdout
    out, pos = defaultdict(set), 0
    for h, p in wanted:
        end = cat.index(b"\n", pos)
        header = cat[pos:end].split()
        pos = end + 1
        if len(header) < 3 or header[1] != b"blob":  # "missing": the page did not exist in that commit
            continue
        size = int(header[2])
        blob, pos = cat[pos:pos + size], pos + size + 1
        try:
            old = json.loads(blob.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        out[p] |= {flat(c.get("french_commentary") or "") for c in old.get("commentary") or []
                   if not (c.get("latin_quote") or "").strip() and str(c.get("commentary_id")) != "1"}
    for s in out.values():
        s.discard("")
    return dict(out)


@functools.lru_cache(maxsize=None)
def latin_words(text):
    """The words of three letters or more in a Latin text, folded."""
    return frozenset(_fold(w) for w in re.findall(r"[^\W\d_]{3,}", text))


def best_verse(lemma, verses):
    """The verse whose Latin holds most of the lemma's words: (score of each verse, best key)."""
    ws = latin_words(lemma)
    if not ws:
        return {}, None
    score = {k: len(ws & latin_words(t)) / len(ws) for k, t in verses.items()}
    return score, max(score, key=score.get) if score else None

class Book:
    """One book being audited: its source pages, the result (r) and the review queue being built."""

    def __init__(self, key, info, slug):
        self.key, self.info = key, info
        self.r = dict(key=key, fr=info["fr"], slug=slug, volumes=info["studium"])
        self.pages, self.queue, self.counts, self._latin = [], [], Counter(), {}

    def item(self, kind, vol, page, msg, optional=False, where=None):
        """Queue an item for the review editor, unless it was marked a false positive: True when queued."""
        # Stable across runs, so review progress survives a re-audit; `where`: the entry and field
        uid = hashlib.md5(msg.encode()).hexdigest()[:8]
        item_id = f"{vol}/{page:04d}/{kind}/{uid}"
        if FP_IDS.matches(item_id, vol, page, kind, msg, where):
            return False
        self.queue.append(dict(id=item_id, book_dir=vol, page=page,
                               kind=kind, msg=msg, optional=optional, **({"where": where} if where else {})))
        return True

    def vol_of(self, page_name):
        return next((v for v in self.info["studium"] if (STUDIUM / v / "normalized" / page_name).exists()), None)

    def latin_of(self, vol):
        """{(chapter, verse number): Latin} of a volume's verses, as strings."""
        if vol not in self._latin:
            self._latin[vol] = {(str(v.get("chapter")), str(v.get("verse_number"))): v.get("latin") or ""
                                for vv, _, dd in self.pages if vv == vol for v in dd.get("verses") or []}
        return self._latin[vol]

    def next_page(self, i):
        """Page i+1, when it is in the same volume."""
        return self.pages[i + 1][2] if i + 1 < len(self.pages) and self.pages[i + 1][0] == self.pages[i][0] else None

    def runs_over(self, i):
        """The first note of page i+1 finishes the last note of page i (no comment yet, same verse)."""
        nxt = self.next_page(i)
        if nxt is None:
            return None
        last = (self.pages[i][2].get("commentary") or [None])[-1]
        first = (nxt.get("commentary") or [None])[0]
        if not last or not first or (last.get("french_commentary") or "").strip():
            return None
        ref = str(first.get("verse_ref") or "").strip()
        return first if not ref or ref == str(last.get("verse_ref") or "").strip() else None


class Note:
    """Commentary block j of page i, with the fields the checks read."""

    def __init__(self, b, i, j):
        self.i, self.j = i, j
        self.vol, self.name, self.d = b.pages[i]
        self.page = int(self.name[5:9])
        self.cs = self.d.get("commentary") or []
        self.c = self.cs[j]
        self.lemma = (self.c.get("latin_quote") or "").strip()
        self.tr = (self.c.get("french_translation") or "").strip()
        self.fc = self.c.get("french_commentary") or ""
        self.last = j == len(self.cs) - 1
        self.next = b.next_page(i)
        # the first note overleaf, for the last note of the page
        self.overleaf = ((self.next or {}).get("commentary") or [{}])[0] if self.last else {}
        self.ref = f"Note {self.c.get('commentary_id')} (℣ {self.c.get('verse_ref')})"

    def at(self, field):
        return dict(section="commentary", index=self.j, field=field)


# ---------- source pages ----------

def read_pages(b):
    pages, malformed, raw_only = b.pages, [], []
    for vol in b.info["studium"]:
        nd, rd = STUDIUM / vol / "normalized", STUDIUM / vol / "raw_json" / "commentaire"
        if not nd.exists():
            continue
        norm_names = {p.name for p in nd.glob("page_[0-9][0-9][0-9][0-9].json") if " " not in p.name}
        raw_names = {p.name for p in rd.glob("page_[0-9][0-9][0-9][0-9].json") if " " not in p.name} if rd.exists() else set()
        raw_only += [f"{vol}/{n}" for n in sorted(raw_names - norm_names)]
        for n in sorted(norm_names):
            d, err = load(nd / n)
            if err:
                malformed.append(f"{vol}/{n}")
                continue
            pages.append((vol, n, d))
    b.r["pages"] = len(pages)
    b.r["malformed"] = malformed
    b.r["raw_not_normalized"] = raw_only


def page_gaps(b):
    """Numbering gaps in the page sequence."""
    gaps = []
    for vol in b.info["studium"]:
        nums = sorted({int(n[5:9]) for v, n, _ in b.pages if v == vol} |
                      {int(m.split("/")[1][5:9]) for m in b.r["malformed"] if m.startswith(vol + "/")})
        gaps += [f"{vol}/page_{a+1:04d}" + (f"–{z-1:04d}" if z - a > 2 else "")
                 for a, z in zip(nums, nums[1:]) if z - a > 1]
    b.r["page_number_gaps"] = gaps


def page_sizes(b):
    """Empty and thin pages."""
    sizes, empty, thin = [], [], []
    for vol, n, d in b.pages:
        c = sum(len(x.get("french_commentary") or "") for x in d.get("commentary") or [])
        v = sum(len(x.get("french") or "") for x in d.get("verses") or [])
        i = len((d.get("chapter_intro") or "").strip())
        a = len((d.get("chapter_argument") or "").strip())
        sizes.append(c + v + i + a)
        if not (d.get("commentary") or d.get("verses") or a or i):  # Intro / argument / commentary pages
            empty.append(f"{vol}/{n}")
    med = statistics.median(sizes) if sizes else 0
    for (vol, n, d), s in zip(b.pages, sizes):
        if 0 < s < 0.2 * med:
            thin.append(f"{vol}/{n} ({s} chars)")
    b.r["empty_pages"], b.r["thin_pages"], b.r["median_page_chars"] = empty, thin, int(med)


def page_seams(b):
    """Suspicious seams between consecutive pages' commentary."""
    seams, prev = [], None
    for vol, n, d in b.pages:
        blocks = [x for x in d.get("commentary") or [] if (x.get("french_commentary") or "").strip()]
        if not blocks:
            continue
        if prev is not None:
            pn, tail = prev
            first = blocks[0]
            head = re.sub(r"^[\s_*]+", "", first.get("french_commentary") or "")
            t = re.sub(r"[\s_*]+$", "", tail)
            ended = bool(re.search(r"[.!?»]$", t))
            cont = head[:1].islower()
            new_lemma = bool((first.get("latin_quote") or "").strip())
            kind = ("gap? continuation after a full stop" if cont and ended else
                    "gap? sentence cut, next page opens a new lemma"
                    if not ended and t[-1:].isalpha() and not cont and new_lemma else
                    "continuation tagged as a new note" if cont and first.get("verse_ref") else None)
            if kind:
                seams.append(dict(seam=f"{pn}>{vol}/{n}", kind=kind, before=t[-60:], after=head[:60]))
        prev = (f"{vol}/{n}", blocks[-1].get("french_commentary") or "")
    b.r["suspicious_seams"] = seams


# ---------- review queue: what a person has to check against the scans ----------

def queue_page_problems(b):
    for g in b.r["page_number_gaps"]:
        vol, rest = g.split("/")
        a = int(rest[5:9]); last = int(rest.split("–")[1]) if "–" in rest else a
        for pg in range(a, last + 1):
            b.item("missing_page", vol, pg, "Page has no JSON at all: create it from the scan and transcribe it")
    for m in b.r["malformed"]:
        vol, n = m.split("/")
        b.item("malformed_page", vol, int(n[5:9]), "Page JSON is malformed and is skipped by every export: repair it")
    for e in b.r["empty_pages"]:
        vol, n = e.split("/")
        b.item("empty_page", vol, int(n[5:9]), "Page has neither verses nor commentary: blank/plate, or lost content?")
    for s in b.r["suspicious_seams"]:
        vol, n = s["seam"].split(">")[1].split("/")
        if s["kind"].startswith("gap? sentence cut"):
            b.item("possible_gap", vol, int(n[5:9]),
                   f"Possible lost text at the page turn: “…{s['before'][-45:]}” ‖ “{s['after'][:45]}…”")
        elif s["kind"].startswith("gap? continuation"):
            b.item("seam_artifact", vol, int(n[5:9]),
                   f"Page-turn glitch (stray full stop / repeated syllable): “…{s['before'][-40:]}” ‖ “{s['after'][:40]}…”",
                   optional=True)


def ref_order(b):
    """verse_ref must run in order within a chapter (the `chapter` field, assign_chapters.py):
    a drop inside a chapter is a misread number, or Calmet going back to a verse."""
    nums = []
    for vol, n, d in b.pages:
        for ci, c in enumerate(d.get("commentary") or []):
            m = re.match(r"(\d+)", str(c.get("verse_ref") or ""))
            if m:
                ok = ORDER_OK.get(f"{vol}/{n}/{c.get('commentary_id')}") == str(c.get("verse_ref"))
                nums.append((vol, n, c.get("chapter"), int(m.group(1)), ok, ci))
    out_of_order = []
    for j in range(1, len(nums)):
        vol, n, ch, ref, ok, ci = nums[j]
        pch, prev = nums[j - 1][2], nums[j - 1][3]
        if ch == pch and ref < prev and not (ok or nums[j - 1][4]):  # not a move made on purpose
            ctx = ", ".join(str(y[3]) for y in nums[max(0, j - 3):j + 2])
            out_of_order.append(f"{vol}/{n}")
            b.item("ref_order", vol, int(n[5:9]),
                   f"verse_ref goes back from {prev} to {ref} (… {ctx} …) in chapter {ch}: "
                   f"misread number, or Calmet returning to a verse?",
                   where=dict(section="commentary", index=ci, field="verse_ref"))
    b.r["ref_out_of_order"] = out_of_order


def chapter_field(b):
    """The chapter field: on every entry after the book's first heading, never going back
    or skipping a chapter."""
    for section, field in (("verses", "verse_number"), ("commentary", "verse_ref")):
        prev = None
        for vol, n, d in b.pages:
            for ei, e in enumerate(d.get(section) or []):
                ch = e.get("chapter")
                where = dict(section=section, index=ei, field="chapter")
                if not isinstance(ch, int):
                    if prev is not None:
                        b.item("chapter_field", vol, int(n[5:9]), f"{section}: {field} {e.get(field)} has no chapter",
                               where=where)
                    continue
                if prev is not None and not (prev <= ch <= prev + 1):
                    b.item("chapter_field", vol, int(n[5:9]),
                           f"{section}: chapter goes from {prev} to {ch} at {field} {e.get(field)}", where=where)
                prev = ch


# ---------- each note ----------

CAPS = re.compile(r"\b[A-ZÀ-ÝŒÆ]{2,}(?:[\s,;:'’.-]+[A-ZÀ-ÝŒÆ]{2,})+\b")
ODD_MARK = re.compile(r"\^[^{]|\^\{(?!\([a-z]\)\})[^}]*\}")
NOTE_FIELDS = ("latin_quote", "french_translation", "french_commentary")
STOPS = (".", ",", ";", ":", "!", "?", "…")
_NAME = r"[A-ZÀ-ÝŒÆ]+(?:-[A-ZÀ-ÝŒÆ]+)*"
# a lemma that is only names ("EN-GANNIM.", "LOD, HADID, ET ONO."): Calmet seldom translates those
NAMES_ONLY = re.compile(rf"\s*{_NAME}(?:\s*(?:,\s*ET\b|,|\bET\b)\s*{_NAME})*\s*[.,;:]?\s*")
# "or" in the Latin: an "ou" in the translation renders it
OR_IN_LATIN = re.compile(r"\b(?:AUT|VEL|SIVE|SEU|AN|NUMQUID|UTRUM)\b", re.I)


def empty_commentary(b, t):
    """Notes with no commentary. Fine when the comment opens the next page, or when
    Calmet gives only the translation; suspicious when nothing follows the lemma."""
    if t.fc.strip():
        return
    if t.last and t.lemma and not t.tr:
        problem = None  # a lemma alone at the foot of the page: its text is overleaf
    elif t.last:
        problem = None if t.next and not (t.overleaf.get("latin_quote") or "").strip() else \
            "is the last note on the page and the next page starts a new lemma: comment lost at the page break?"
    elif not (t.cs[t.j + 1].get("latin_quote") or "").strip():
        problem = "is followed by a block with no lemma: one note split in two?"
    elif not t.tr:
        problem = "has neither translation nor comment" + (" (the comment may be inside latin_quote)" if re.search(r"[a-zé]{4,}", t.lemma) else "")
    elif not re.search(r"[.!?»]_?(\s*\^\{\([a-z]\)\})?$", t.tr):
        problem = "has no comment and its translation is cut off"
    else:
        problem = None
    if problem:
        b.counts["empty_commentary"] += 1
        b.item("empty_commentary", t.vol, t.page, f"Note “{t.lemma[:40]}” (℣ {t.c.get('verse_ref')}) {problem}",
               where=t.at("french_commentary"))


def caps_in_commentary(b, t):
    fc = t.fc
    for m in CAPS.finditer(fc):
        if re.fullmatch(r"[IVXLC.\s,et]+", m.group()):
            continue
        b.counts["caps_in_commentary"] += 1
        where = "starts the comment" if m.start() < 3 else "inside the comment"
        b.item("caps_in_commentary", t.vol, t.page,
               f"Capitals {where}: “…{fc[max(0, m.start() - 25):m.end() + 15]}…”: a lemma that should start its own note, or a word to put in lower case?",
               where=t.at("french_commentary"))


def spaced_letters(b, t):
    for k in NOTE_FIELDS:
        for m in re.finditer(r"(?<![\w.])(?:[A-Za-zÀ-ÿŒÆœæ] ){3,}[A-Za-zÀ-ÿŒÆœæ](?!\w)", t.c.get(k) or ""):
            b.item("spaced_letters", t.vol, t.page,
                   f"Letter-spaced word in {k}: “{m.group()}”: close up the letters (put the word breaks back)",
                   where=t.at(k))


def leading_call(b, t):
    for k in NOTE_FIELDS:
        m = re.match(r"\s*\^\{[^}]*\}", t.c.get(k) or "")
        if m:
            b.item("leading_call", t.vol, t.page,
                   f"{k} of note {t.c.get('commentary_id')} (℣ {t.c.get('verse_ref')}) starts with the footnote call "
                   f"“{m.group().strip()}”: “{(t.c.get(k) or '')[:60]}…”: move it after the word it belongs to "
                   f"(end of the previous field or page?)",
                   where=t.at(k))


def leading_punctuation(b, t):
    if re.match(r"\s*[.,;:!?»]", t.fc):
        b.item("leading_punctuation", t.vol, t.page,
               f"Comment starts with punctuation “{t.fc[:40]}…”"
               + (": move it to the end of the translation (tidy_fields.py does)" if t.tr else
                  ": no translation in this block, so it belongs to the text before (previous page?)"),
               where=t.at("french_commentary"))


def hyphen_cut(b, t):
    """A lemma or translation cut by the page turn ("PER-", or mid-sentence in a note whose
    comment hasn't started) must go on in the same field overleaf."""
    for k in ("latin_quote", "french_translation"):
        s = re.sub(r"\^\{[^}]*\}", "", t.c.get(k) or "").rstrip()
        if not s:
            continue
        hyphen = s.endswith("-")
        open_ = (t.last and not t.fc.strip() and not re.search(r"[.!?»…)\]]$", s)
                 and (k == "french_translation" or not t.tr))
        if not (hyphen or open_) or (t.overleaf.get(k) or "").strip():
            continue
        first = t.overleaf
        overleaf = first.get("french_commentary") or first.get("french_translation") or first.get("latin_quote") or ""
        b.item("hyphen_cut", t.vol, t.page,
               f"{k} ends “…{s[-40:]}”" + ("" if hyphen else " with no full stop") + " but "
               + (f"the next page's first note has no {k} (it starts “{overleaf[:50]}…”)"
                  if t.last else "another note follows on this page")
               + f": put the rest of the {k} back together"
               + ("" if hyphen else " (or add the missing full stop)"),
               where=t.at(k))


def page_turn_seams(b, t):
    """The page turn inside a comment: italics and sentences must carry over."""
    fc, nfirst = t.fc, t.overleaf
    nfc = nfirst.get("french_commentary") or ""
    if not (fc.strip() and nfc.strip()) or (nfirst.get("latin_quote") or "").strip() \
            or (nfirst.get("french_translation") or "").strip():
        return
    if fc.count("_") % 2 and not nfc.count("_") % 2:
        b.item("italic_seam", t.vol, t.page,
               f"Italics still open at the foot of the page (“…{fc[fc.rfind('_'):][-60:]}”) but not closed "
               f"overleaf (“{nfc[:50]}…”): close them here, or a “_” is missing or extra",
               where=t.at("french_commentary"))
    tail = re.sub(r"(\s*\^\{[^}]*\})+\s*$", "", fc).rstrip()
    head = re.match(r"\s*[_«\"(]*\s*(\w)", nfc)
    # italics closed right at the foot of the page, mid-sentence, while the quotation runs
    # on in roman overleaf (Ruth 25-26: "…d'un homme_" ‖ "d'honneur.")
    run = re.search(r"_([^_]+)_$", tail)
    if (run and not fc.count("_") % 2 and not re.search(r"[.;:!?»]$", run.group(1).rstrip())
            and len(run.group(1).split()) >= 2 and not re.match(r"\s*_", nfc)
            and head and head.group(1).islower()):
        b.item("italic_seam", t.vol, t.page,
               f"Italics closed at the very foot of the page (“…{tail[-50:]}”) but the sentence goes on "
               f"in roman overleaf (“{nfc[:50]}…”): carry the italics over to where the quotation ends",
               where=t.at("french_commentary"))
    if tail.endswith(".") and head and head.group(1).islower() and not ABBREV.search(tail):
        b.item("period_seam", t.vol, t.page,
               f"Full stop at the foot of the page (“…{tail[-45:]}”) but the next page goes on in "
               f"lower case (“{nfc[:45]}…”): stray full stop, or a capital to restore?",
               where=t.at("french_commentary"))


def missing_start(b, t):
    """A comment opening mid-sentence on a page whose predecessor has nothing for it to go on from."""
    i = t.i
    if not (t.j == 0 and t.fc.strip() and i and b.pages[i - 1][0] == t.vol
            and int(b.pages[i - 1][1][5:9]) == t.page - 1):
        return
    before = (b.pages[i - 1][2].get("commentary") or [None])[-1]
    if start_missing(before, t.c):
        b.item("missing_start", t.vol, t.page,
               f"The first note opens in the middle of a sentence (“{t.fc[:50]}…”) but "
               + (f"the last note of the page before (“{(before.get('latin_quote') or before.get('french_translation') or '')[:40]}…”) has no comment"
                  if before else "the page before has no notes")
               + ": the start of the comment is missing (typed on the page before, or lost at the page turn)",
               where=t.at("french_commentary"))


def first_no_lemma(b, t):
    """The first note of a page with no lemma at all: the end of the note before, or a note whose lemma was lost."""
    if not (t.j == 0 and not t.lemma and not t.tr and t.fc.strip()):
        return
    before = next((cc[-1].get("french_commentary") or "" for vv, _, dd in reversed(b.pages[max(0, t.i - 20):t.i])
                   if vv == t.vol and (cc := dd.get("commentary") or []) and (cc[-1].get("french_commentary") or "").strip()),
                  None)
    why = first_note_without_lemma(before, t.fc) if before else None
    if why:
        b.item("first_no_lemma", t.vol, t.page,
               (f"The first note opens with what looks like its lemma in capitals (“{t.fc[:60]}…”): "
                f"move it to latin_quote" if why == "lemma" else
                f"The first note (“{t.fc[:50]}…”) has no latin_quote or french_translation, but the page "
                f"before ends a sentence (…{before.rstrip()[-40:]}): a new note whose lemma was lost, "
                f"or the next sentence of the same note?"),
               optional=why == "sentence", where=t.at("latin_quote"))


def no_lemma(b, t):
    """Only the first block of a page may lack a lemma (it continues the page before)."""
    if t.lemma or t.c.get("commentary_id") == 1:
        return
    why = ("the lemma is at the start of the comment: move it to latin_quote"
           if re.match(r"\s*[A-ZÀ-ÝŒÆ]{2,}[\sA-ZÀ-ÝŒÆ',.;:?!-]{6,}", t.fc) else
           "one note split in two, or a lemma lost?")
    b.item("no_lemma", t.vol, t.page,
           f"{t.ref} has no latin_quote: “{(t.tr or t.fc)[:70]}…”: {why}",
           where=t.at("latin_quote"))


def lemma_form(b, t):
    """The lemma: printed in capitals, with a verse_ref, in words the Vulgate has."""
    lemma = t.lemma
    if (lemma or t.tr) and not str(t.c.get("verse_ref") or "").strip():
        b.item("no_verse_ref", t.vol, t.page, f"Note “{(lemma or t.tr)[:50]}” has no verse_ref",
               where=t.at("verse_ref"))
    if re.search(r"[a-zàâçéèêëîïôûùüÿœæ]", re.sub(r"\^\{[^}]*\}", "", lemma)):
        b.item("lowercase_lemma", t.vol, t.page,
               f"Lower case in latin_quote “{lemma[:70]}”: French or commentary in the lemma field?",
               where=t.at("latin_quote"))
    # the site takes the lemma's capitals from the Vulgate (calmet.py latin_case): a word the
    # Vulgate lacks comes out in lower case
    unknown = [w for w in re.findall(r"[^\W\d_]{3,}", STRAY.sub("", lemma))
               if _fold(w) not in vulgate_words() and w.lower() != "etc"]
    if unknown:
        b.item("lemma_unknown_word", t.vol, t.page,
               f"Not in the Vulgate: {', '.join(unknown)} in “{lemma[:60]}”: a name (add it to "
               f"scripts/latin_names.txt), a misreading, French in the lemma, or a word cut in two?",
               optional=True, where=t.at("latin_quote"))


def translation_length(b, t):
    """A translation of about the lemma's length; a lemma and translation split by the page turn
    are measured whole."""
    la, fr, cut = re.sub(r"\^\{[^}]*\}", "", t.lemma), t.tr, ""
    if t.last and (rest := b.runs_over(t.i)):
        la = (la + " " + re.sub(r"\^\{[^}]*\}", "", rest.get("latin_quote") or "")).strip()
        fr, cut = (fr + " " + (rest.get("french_translation") or "")).strip(), " (with the next page)"
    if t.j == 0 and t.i and b.runs_over(t.i - 1):
        la = ""  # measured with the previous page's last note
    if la and len(fr) > 3 * len(la) and len(fr) - len(la) > 40:
        b.item("long_translation", t.vol, t.page,
               f"Translation of {len(fr)} characters for a lemma of {len(la)}{cut} “{t.lemma[:40]}”: "
               f"“{fr[:90]}…”: commentary run into the translation?",
               # "QUI JUSTIFICAT IMPIUM, ETC.": Calmet translates the whole verse
               optional=bool(re.search(r"\bETC\.?\s*$", t.lemma, re.I)),
               where=t.at("french_translation"))
    if la.strip() and not fr:
        no_translation(b, t, la)


def no_translation(b, t, la):
    fc, where = t.fc, "the comment starts"
    overleaf = t.last and not fc.strip() and t.next is not None and (t.next.get("commentary") or [None])[0]
    if overleaf:  # the last note of the page, its comment overleaf
        fc, where = overleaf.get("french_commentary") or "", "the next page starts"
    one_word = len(re.findall(r"[^\W\d_]+", la)) == 1
    why = ("French in the lemma?" if re.search(r"[a-zàâçéèêëîïôûùüÿœæ]{3}", la) else
           "the translation run into the commentary?" if re.match(r"\s*_[^_]{3,}_", fc)
           or re.match(rf"\s*[^.;:,]{{{len(la) // 2},{len(la) * 3}}}[.;:,]", fc) else
           "a name Calmet leaves untranslated?" if one_word else "a translation lost?")
    b.item("no_translation", t.vol, t.page,
           f"{t.ref}: latin_quote “{t.lemma[:50]}” has no "
           f"french_translation; {where} “{fc[:60]}…”: {why}",
           optional=one_word or bool(NAMES_ONLY.fullmatch(la)),
           where=t.at("french_translation"))


def hebrew_in_translation(b, t):
    marks = translation_markers(t.tr)
    if not marks or ([m.lower() for m in marks] == ["ou"]
                     and (OR_IN_LATIN.search(t.lemma) or re.search(r"\(\s*ou\b", t.tr))):
        return
    if re.search(r"\bl['’]\s?h[ée]breu", t.tr, re.I):
        # keep the old wording (and so the old id) for items already reviewed
        msg = (f"“L'Hébreu” in the translation of “{t.lemma[:40]}”: “{t.tr[:100]}…”: "
               "commentary run into the translation?")
    else:
        shown = " ".join(f"“{m}”" for m in marks)
        msg = (f"{shown} in the translation of “{t.lemma[:40]}”: “{t.tr[:100]}…”: "
               "commentary or a variant run into the translation?")
    b.item("hebrew_in_translation", t.vol, t.page, msg, where=t.at("french_translation"))


def field_ends(b, t):
    """Lemma and translation end with punctuation (unless the note runs over the page);
    a translation after the first note starts with a capital."""
    tr, lemma = t.tr, t.lemma
    if tr:
        tr_bare = tr.rstrip("_* \t")
        if not t.last and not re.search(r"\^\{[^\}]+\}\s*$", tr_bare) \
                and not tr_bare.rstrip("])»”\"'").endswith(STOPS):
            b.item("translation_no_punct", t.vol, t.page,
                   f"{t.ref}: french_translation does not end with punctuation: “{tr[-50:]}”",
                   where=t.at("french_translation"))
        if t.j != 0:
            clean_start = re.sub(r"^\s*(\^\{[^}]*\}|[\s_«\"'‘“\(\[\{:§.])+", "", tr)
            m = re.search(r"[A-Za-zÀ-ÖØ-öø-ÿœæŒÆ]", clean_start)
            if m and m.group(0).islower():
                b.item("lowercase_translation", t.vol, t.page,
                       f"{t.ref}: french_translation missing initial capital: starts with “{m.group(0)}” in “{tr[:50]}…”",
                       where=t.at("french_translation"))
    if lemma:
        la_bare = lemma.rstrip("_* \t")
        if not t.last and not re.search(r"\^\{[^\}]+\}\s*$", la_bare) \
                and not la_bare.rstrip("])»”\"'").endswith(STOPS):
            b.item("lemma_no_punct", t.vol, t.page,
                   f"{t.ref}: latin_quote does not end with punctuation: “{lemma[-50:]}”",
                   where=t.at("latin_quote"))


def broken_marker(b, t):
    notes_here = {re.sub(r"\W", "", str(fn.get("marker") or "")) for fn in t.d.get("footnotes") or []}
    for k in NOTE_FIELDS:
        s = t.c.get(k) or ""
        bad = [m.group() for m in ODD_MARK.finditer(s)]
        bad += [m.group() for m in re.finditer(r"(?<![\^{\w])\(\s?([a-z])\s?\)(?!\})", s) if m.group(1) not in notes_here]
        for x in bad:
            b.counts["broken_markers"] += 1
            pos = s.find(x)
            b.item("broken_marker", t.vol, t.page,
                   f"Footnote call “{x}” in {k}: “…{s[max(0, pos - 30):pos + len(x) + 10]}…”",
                   where=t.at(k))


NOTE_CHECKS = (empty_commentary, caps_in_commentary, spaced_letters, leading_call, leading_punctuation,
               hyphen_cut, page_turn_seams, missing_start, first_no_lemma, no_lemma, lemma_form,
               translation_length, hebrew_in_translation, field_ends, broken_marker)


# ---------- each page, around its notes ----------

def empty_summary(b, vol, n, d):
    if chapter_of(d) and not str(d.get("chapter_summary") or "").strip():
        b.item("empty_summary", vol, int(n[5:9]),
               f"Chapter {chapter_of(d)} opens here but chapter_summary is empty: type it from the scan "
               f"(or the heading is a running head and chapter_number/chapter_title should go)")


def guessed_ref(b, vol, n, d):
    """Bible references guessed from the context (starred), or left as printed with no such verse."""
    texts = [(f"commentary {c.get('commentary_id')}", c.get("french_commentary") or "") for c in d.get("commentary") or []]
    texts += [(f"footnote {f.get('marker')}", str(f.get("text") or "")) for f in d.get("footnotes") or []]
    guessed = [f"{where}: “{m.group()}”" for where, t in texts for m in GUESSED_REF.finditer(t)]
    printed = [f"“{src}”" for (page, src), v in REF_MANUAL.items() if v is None and page == f"{vol}/page_{n[5:9]}"]
    if guessed or printed:
        b.item("guessed_ref", vol, int(n[5:9]), "; ".join(
            ([", ".join(guessed) + " guessed from the context: check against the scan, then remove the asterisk "
              "or set the reference right"] if guessed else [])
            + ([f"Calmet's {', '.join(printed)} written out as printed, but no such verse in the Vulgate: "
                "check against the scan"] if printed else [])))


def lemma_verse(b, vol, n, d):
    """Lemmas filled in by hand where there was none, and lemmas whose words are in another verse."""
    added = lemma_added(vol, n)
    for j, c in enumerate(d.get("commentary") or []):
        lemma = c.get("latin_quote") or ""
        if not lemma.strip():
            continue
        fc = flat(c.get("french_commentary") or "")
        # the same block: one commentary holds the other's start (a lemma moved out of it, a block joined)
        by_hand = fc and any(fc[:40] in o or o[:40] in fc or fc[-40:] in o for o in added)
        ch, ref = str(c.get("chapter") or ""), str(c.get("verse_ref") or "")
        score, best = best_verse(re.sub(r"\^\{[^}]*\}", "", lemma), {v: t for (cc, v), t in b.latin_of(vol).items() if cc == ch})
        span = re.fullmatch(r"(\d+)\s*[-–]\s*(\d+)", ref)  # "16-17": the best of the verses it covers
        if span and score:
            inside = [str(v) for v in range(int(span[1]), int(span[2]) + 1)]
            score[ref] = max(score.get(v, 0) for v in inside)
            best = ref if best in inside else best
        where = dict(section="commentary", index=j, field="verse_ref")
        if by_hand:
            hint = (f"its words fit ℣ {best} better ({score[best]:.0%} against {score.get(ref, 0):.0%})"
                    if best and best != ref and score[best] > score.get(ref, 0) else
                    f"its words fit ℣ {ref}" if score.get(ref) else "")
            b.item("lemma_verse", vol, int(n[5:9]),
                   f"Note {c.get('commentary_id')} had no latin_quote; now “{lemma[:60]}” at chapter {ch}, ℣ {ref}: "
                   f"check the verse number{': ' + hint if hint else ''}", optional="better" not in hint, where=where)
        elif best and best != ref and score[best] >= 0.8 and score.get(ref, 0) <= 0.4 \
                and len(re.findall(r"[^\W\d_]{3,}", lemma)) >= 2:
            b.item("verse_mismatch", vol, int(n[5:9]),
                   f"Note {c.get('commentary_id')} “{lemma[:60]}” is under chapter {ch}, ℣ {ref}, but its words are in "
                   f"℣ {best} ({score[best]:.0%} against {score.get(ref, 0):.0%}): wrong verse_ref, or the verse misnumbered?",
                   where=where)


def unwritten_chapter_refs(b, vol, n, d):
    """Chapter references chapter_refs.py could not write out: which book, or which numbers?"""
    for j, c in enumerate(d.get("commentary") or []):
        t, where = c.get("french_commentary") or "", f"commentary {c.get('commentary_id')} (℣ {c.get('verse_ref')})"
        left = [m.group().strip(" ,") for m in CH_REF.finditer(t) if chapter_write(m, t) == m.group()]
        which = [t[max(0, m.start() - 30):m.end()].lstrip() for m in WHICH_BOOK.finditer(t)]
        at = dict(section="commentary", index=j, field="french_commentary")
        if left:
            b.item("chapter_ref", vol, int(n[5:9]), f"{where}: “{'”, “'.join(left)}” left as printed (chapters "
                   "not in order: a verse, or a word?): write it as “chapitre C:V”, or “Livre C:V” after a book", where=at)
        if which:
            b.item("chapter_ref", vol, int(n[5:9]), f"{where}: “…{'”, “…'.join(which)}”: which book? write it as "
                   "“2 Rois 1:18” / “1 Paralipomènes 9:22”", where=at)


def footnote_calls(b, vol, n, d):
    """Footnotes with guessed words (an asterisk: one item per page), and more footnotes than calls."""
    fns = d.get("footnotes") or []
    starred = [str(f.get("marker")) for f in fns if "*" in GUESSED_REF.sub("", str(f.get("text") or ""))]
    if starred:
        b.item("footnote_asterisk", vol, int(n[5:9]),
               f"Footnote{'s' if len(starred) > 1 else ''} {', '.join(starred)}: words marked * were guessed: "
               f"check them against the scan, then remove the asterisks")
    called = set(re.findall(r"\^\{\(([a-z])\)\}", json.dumps({k: v for k, v in d.items() if k != "footnotes"},
                                                            ensure_ascii=False)))
    if len(fns) > len(called):
        uncalled = [str(f.get("marker")) for f in fns if re.sub(r"\W", "", str(f.get("marker") or "")) not in called]
        b.item("extra_footnotes", vol, int(n[5:9]),
               f"{len(fns)} footnotes for {len(called)} calls in the text"
               + (f": nothing calls {', '.join(uncalled)}" if uncalled else ": a marker is used twice")
               + " (footnote from another page, a call lost, or a duplicate?)")


def check_notes(b):
    for i, (vol, n, d) in enumerate(b.pages):
        empty_summary(b, vol, n, d)
        for j in range(len(d.get("commentary") or [])):
            t = Note(b, i, j)
            for check in NOTE_CHECKS:
                check(b, t)
        for check in (guessed_ref, lemma_verse, unwritten_chapter_refs, footnote_calls):
            check(b, vol, n, d)


# ---------- whole pages ----------

ETC_END = re.compile(r"\b(?:etc|ETC)\.?[_\s»”)]*$")


def etc_for_et(b):
    """"&" (et) at the bottom of the page misread as "etc." at the end of the last commentary block."""
    for vol, n, d in b.pages:
        comm = d.get("commentary") or []
        if not comm:
            continue
        t = (comm[-1].get("french_commentary") or "").strip()
        m = ETC_END.search(t)
        if m:
            b.item("etc_for_et", vol, int(n[5:9]),
                   f"Last commentary ends with “{m.group(0).strip()}”: “…{t[max(0, m.start() - 45):]}” — "
                   f"an “&” (et) at the page turn misread as etc.? (fine if the scan has &c.)",
                   where=dict(section="commentary", index=len(comm) - 1, field="french_commentary"))


def duplicate_page(b):
    """A page whose commentary repeats a neighbour's: one of the two scans was transcribed twice."""
    def shingles(d):
        w = re.findall(r"\w+", " ".join((c.get("french_commentary") or "") + " " + (c.get("latin_quote") or "")
                                        for c in d.get("commentary") or []).lower())
        return {" ".join(w[k:k + 4]) for k in range(len(w) - 3)}
    sh = [(vol, n, shingles(d)) for vol, n, d in b.pages]
    for i, (vol, n, x) in enumerate(sh):
        for vol2, n2, y in sh[i + 1:i + 3]:
            if vol2 == vol and len(x) > 40 and len(y) > 40 and len(x & y) / min(len(x), len(y)) > 0.5:
                b.item("duplicate_page", vol, int(n[5:9]),
                       f"Commentary of page {int(n[5:9])} repeats page {int(n2[5:9])} "
                       f"({round(100 * len(x & y) / min(len(x), len(y)))}% the same): one of them must be retranscribed from its scan")


def missing_french(b):
    """Verses filled in from the Vulgate (fill_psalm_verses.py) until their French is typed;
    any other verse without French lost it in transcription."""
    for vol, n, d in b.pages:
        for vi, v in enumerate(d.get("verses") or []):
            if (v.get("french") or "").strip():
                continue
            where = dict(section="verses", index=vi, field="french")
            if str(v.get("annotations") or "").startswith("Latin from the Vulgate"):
                b.item("vulgate_filled", vol, int(n[5:9]),
                       f"Verse {v.get('verse_number')} was missing: its Latin is filled in from the Vulgate "
                       f"(“{(v.get('latin') or '')[:50]}…”). Check it against the scan, type Calmet's French, then clear the note",
                       where=where)
            else:
                b.item("missing_french", vol, int(n[5:9]),
                       f"Verse {v.get('chapter')}:{v.get('verse_number')} has no French "
                       f"(Latin: “{(v.get('latin') or '')[:50]}…”): type Calmet's translation from the scan",
                       where=where)


def text_end(s):
    """`s` without the calls, italics, quotes and brackets that close it."""
    return re.sub(r"(\s*(\^\{[^}]*\}|[_*»”\"')\]]))+\s*$", "", s.rstrip())


def verse_ends(b, vol, n, d):
    for vi, v in enumerate(d.get("verses") or []):
        for k in ("latin", "french"):
            end = text_end(v.get(k) or "")
            if end and not end.endswith(STOPS):
                b.item("verse_no_punct", vol, int(n[5:9]),
                       f"Verse {v.get('chapter')}:{v.get('verse_number')}: {k} does not end with punctuation: “…{end[-50:]}” "
                       "(a word lost, or the verse runs on overleaf?)", where=dict(section="verses", index=vi, field=k))


def footnote_ends(b, vol, n, d):
    for fi, f in enumerate(d.get("footnotes") or []):
        end = text_end(str(f.get("text") or ""))
        # Hebrew and Greek are printed without a stop after them
        if end and not end.endswith((".", "!", "?", "…")) and not re.search(r"[Ͱ-Ͽἀ-῿֐-׿יִ-ﭏ]\W*$", end) \
                and not re.search(r"\[UNCERTAIN [A-Z]+\]?$", end):
            b.item("footnote_no_period", vol, int(n[5:9]),
                   f"Footnote {f.get('marker')} does not end with a full stop: “…{end[-60:]}”",
                   where=dict(section="footnotes", index=fi, field="text"))


def italics(b, vol, n, d):
    """Italics opened and never closed (or the reverse) within a field."""
    cs = d.get("commentary") or []
    fields = [("verses", vi, v, k) for vi, v in enumerate(d.get("verses") or []) for k in ("latin", "french", "annotations")]
    fields += [("commentary", j, c, k) for j, c in enumerate(cs) for k in NOTE_FIELDS]
    fields += [("footnotes", fi, f, "text") for fi, f in enumerate(d.get("footnotes") or [])]
    for sec, i, e, k in fields:
        text = str(e.get(k) or "")
        # a comment's italics may run over the page turn (italic_seam checks those)
        if "_" not in text or (sec == "commentary" and k == "french_commentary" and i in (0, len(cs) - 1)):
            continue
        bad = stray_underscore(text)
        if bad is None:
            continue
        at, why = bad
        b.item("stray_underscore", vol, int(n[5:9]),
               f"Italics in {k} ({sec} {i + 1}): {why}: “{text[max(0, at - 40):at + 25]}”",
               where=dict(section=sec, index=i, field=k))


def field_ends_and_italics(b):
    for vol, n, d in b.pages:
        for check in (verse_ends, footnote_ends, italics):
            check(b, vol, n, d)


# ---------- assembled chapters & notes (from normalized/) ----------

class Site:
    """What the checks on the assembled chapters gather."""

    def __init__(self):
        self.verse_issues, self.empty_verse, self.site_text, self.orphan_notes = [], [], [], []
        self.fr_hits, self.la_hits, self.note_hits = Counter(), Counter(), Counter()
        self.fr_words = self.note_words = self.missing_fn = self.total_verses = 0


def verse_numbering(b, ch, vs, vul):
    """Verses missing, repeated, or missing at the end of the chapter, against the Vulgate: the
    chapter's issue, or None. The verse numbers it has."""
    key, info = b.key, b.info
    nums = [v.get("verse_number") for v in vs if isinstance(v.get("verse_number"), int)]
    have = set(nums)
    top = max(have) if have else 0
    expect = max(vul.get(ch, {0}))
    counted = key != "psalms" and ch in vul
    missing = [n for n in range(1, min(top, expect) + 1) if n not in have] if counted else []
    dups = sorted({n for n in nums if nums.count(n) > 1})
    tail = list(range(top + 1, expect + 1)) if counted else []
    if not (missing or dups or tail):
        return None, have
    located = [(v["verse_number"], v.get("source_pages", [None])[0]) for v in vs
               if isinstance(v.get("verse_number"), int) and v.get("source_pages")]

    def page_of(n):
        before = [pg for k, pg in located if k < n]
        after = [pg for k, pg in located if k > n]
        pg = before[-1] if before else (after[0] if after else None)
        return int(pg[5:9]) if pg else None

    kept_missing, kept_tail = [], []
    for n in missing + tail:
        pg = page_of(n)
        vol = pg and b.vol_of(f"page_{pg:04d}.json")
        # a missing verse marked a false positive is no longer missing
        if vol and not b.item("missing_verse", vol, pg, f"{info['fr']} {ch}:{n} is missing (page shown holds the nearest verse)"):
            continue
        (kept_missing if n in missing else kept_tail).append(n)
    for n in dups:
        for k, pg in located:
            if k == n and b.vol_of(pg):
                b.item("duplicate_verse", b.vol_of(pg), int(pg[5:9]), f"{info['fr']} {ch}:{n} appears more than once")
    if kept_missing or dups or kept_tail:
        return dict(chapter=ch, missing=kept_missing, duplicated=dups, missing_tail=kept_tail, vulgate_count=expect), have
    return None, have


def chapter_text(s, ch, vs, summary):
    """Old spellings in the chapter's verses and summary."""
    for v in vs:
        if not (v.get("french") or "").strip() or not (v.get("latin") or "").strip():
            s.empty_verse.append(f"{ch}:{v.get('verse_number')}")
        s.fr_hits += archaic_hits(v.get("french")); s.fr_words += words(v.get("french"))
        for name, rx in LATIN_OLD:
            s.la_hits[name] += len(rx.findall(v.get("latin") or ""))
    if summary:
        s.fr_hits += archaic_hits(summary); s.fr_words += words(summary)


def chapter_notes(b, s, ch, have):
    """The chapter's notes as the site builds them: footnote calls without a note, notes without a verse."""
    try:
        c = calmet_notes(b.key, ch, 1, 999)
    except Exception:
        s.verse_issues.append(dict(chapter=ch, notes_file_missing=True))
        return
    s.missing_fn += len(c.get("missing_footnotes") or [])
    for k in c.get("missing_footnotes") or []:
        m = re.match(r"page_(\d+)-(\w)", k)
        vol = m and b.vol_of(f"page_{m.group(1)}.json")
        if vol:
            b.item("missing_footnote", vol, int(m.group(1)),
                   f"Footnote marker ({m.group(2)}) has no footnote text on this page")
    for note in c.get("notes") or []:
        txt = " ".join(str(note.get(k) or "") for k in ("lemma", "text"))
        s.site_text.append(flat(txt))
        s.note_hits += archaic_hits(txt); s.note_words += words(txt)
        for name, rx in LATIN_OLD:
            s.la_hits[name] += len(rx.findall(note.get("latin_lemma") or ""))
        if note.get("verse") not in have:
            s.orphan_notes.append(f"{ch}:{note.get('verse')}")


def dropped_commentary(b, s):
    """Commentary blocks in the source that never reach the site."""
    blob = "".join(s.site_text)
    dropped, checked = [], 0
    for vol, n, d in b.pages:
        for x in d.get("commentary") or []:
            t = flat(x.get("french_commentary"))
            if len(t) < 80:
                continue
            checked += 1
            probes = [t[int(len(t) * q) - 12: int(len(t) * q) + 12] for q in (0.25, 0.5, 0.75)]
            if not any(p in blob for p in probes):
                dropped.append(dict(page=f"{vol}/{n}", verse_ref=x.get("verse_ref"),
                                    chars=len(x.get("french_commentary") or ""),
                                    start=(x.get("french_commentary") or "")[:70]))
    for x in dropped:
        vol, n = x["page"].split("/")
        b.item("dropped_commentary", vol, int(n[5:9]),
               f"Commentary block never reaches the site (verse ref: {x['verse_ref'] or 'none'}): "
               f"“{x['start'][:60].strip()}…” Usually a missing or unreadable verse_ref: set it from the scan")
    return dropped, checked


def check_site(b, published):
    r = b.r
    r["published"] = published
    chapters, summaries, _ = verses_by_chapter(b.key)
    vul = {c["chapter"]: {v["verse"] for v in c["verses"]}
           for c in json.loads((VUL / f"{b.info['vul']}.json").read_text())["chapters"]}
    r["chapters_site"], r["chapters_vulgate"] = len(chapters), len(vul)
    r["chapters_missing"] = sorted(set(vul) - set(chapters))
    s = Site()
    for ch in sorted(chapters):
        vs = chapters[ch]
        s.total_verses += len(vs)
        issue, have = verse_numbering(b, ch, vs, vul)
        if issue:
            s.verse_issues.append(issue)
        chapter_text(s, ch, vs, summaries.get(ch))
        if published:
            chapter_notes(b, s, ch, have)
    r["verses_site"] = s.total_verses
    r["verse_issues"] = s.verse_issues
    r["verses_missing_count"] = sum(len(i.get("missing", [])) + len(i.get("missing_tail", [])) for i in s.verse_issues)
    r["verses_duplicated_count"] = sum(len(i.get("duplicated", [])) for i in s.verse_issues)
    r["verses_empty_text"] = s.empty_verse
    r["notes_without_verse"] = sorted(set(s.orphan_notes), key=lambda x: [int(y) if y.isdigit() else 0 for y in x.split(":")])
    r["missing_footnotes"] = s.missing_fn
    r["french_verse_archaic"] = dict(s.fr_hits); r["french_verse_words"] = s.fr_words
    r["notes_archaic"] = dict(s.note_hits); r["notes_words"] = s.note_words
    r["latin_old_spelling"] = dict(s.la_hits)
    dropped, checked = dropped_commentary(b, s) if published else ([], 0)
    r["commentary_blocks_checked"] = checked
    r["commentary_blocks_not_on_site"] = dropped
    r["commentary_chars_not_on_site"] = sum(x["chars"] for x in dropped)


def audit_book(key, info, slug, published=True):
    """Every check on one book: the result, its review queue in r["queue"]."""
    b = Book(key, info, slug)
    r = b.r
    for check in (read_pages, page_gaps, page_sizes, page_seams):
        check(b)
    r["queue"] = b.queue
    for check in (queue_page_problems, ref_order, chapter_field, check_notes, etc_for_et, duplicate_page,
                  missing_french, field_ends_and_italics):
        check(b)
    r["empty_commentary"], r["caps_in_commentary"], r["broken_markers"] = (
        b.counts["empty_commentary"], b.counts["caps_in_commentary"], b.counts["broken_markers"])
    if not b.pages:
        r["published"] = False
        return r
    check_site(b, published)
    return r


# Left out of the audit and the review queue
EXCLUDED = set()


def seam_fully_read(read):
    """The books in seam_check.py's results whose every page break has been read. Only those replace
    the punctuation guesses for a possible gap: a partial run (say, the model ran out of quota) must
    not silently drop the checks it has not covered yet."""
    return {book for book, res in read.items() if not res.get("unread")}


def latin_long_s():
    """Latin verse words vulgate_check.py found with f where the Vulgate has s, but could not set
    right by itself (the word differs from the Vulgate's in more than the f): read on the scan."""
    f = DOCS / "vulgate_check.json"
    if not f.exists():
        return []
    out = []
    for x in json.loads(f.read_text(encoding="utf-8"))["items"]:
        if x["kind"] != "long_s" or x.get("fix"):
            continue
        vol, stem = x["where"].split("/")
        msg = (f"Latin of verse {x['ref']}: “{x['calmet']}” — an f read for a long s? The Vulgate has "
               f"“{x['vulgate_word']}”. Verse: {x['latin'][:120]}")
        out.append(dict(id=f"{vol}/{stem[5:9]}/latin_long_s/{hashlib.md5(msg.encode()).hexdigest()[:8]}",
                        book_dir=vol, page=int(stem[5:9]), kind="latin_long_s", msg=msg, optional=False))
    return out


def main():
    slugs = site_slugs()
    results = []
    for key, info in BOOKS.items():
        if key in EXCLUDED:
            continue
        r = audit_book(key, info, info.get("site") or slugs.get(info["fr"]))
        results.append(r)
        print(f"{info['number']:>2} {info['fr']:<14} pages={r['pages']:<4} "
              f"vmiss={r.get('verses_missing_count','-')} vdup={r.get('verses_duplicated_count','-')} "
              f"gaps={len(r['page_number_gaps'])} empty={len(r['empty_pages'])} "
              f"seams={len(r['suspicious_seams'])} dropped={len(r.get('commentary_blocks_not_on_site', []))}"
              f"/{r.get('commentary_blocks_checked','-')}", flush=True)
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DOCS / "integrity_audit.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1))
    print("wrote", out)
    # Worklist for the review editor (review_web.py), most serious kinds first, then in page order
    order = ["duplicate_page", "malformed_page", "missing_page", "missing_verse", "psalm_missing_verse", "missing_french", "vulgate_filled", "psalm_wrong_psalm", "psalm_unmatched", "duplicate_verse", "psalm_number", "psalm_missing_title", "latin_long_s", "chapter_field", "empty_summary", "chapter_vulgate", "chapter_heading", "dropped_commentary", "seam_missing", "seam_repeat", "seam_unclear", "ref_order", "no_verse_ref", "no_lemma", "first_no_lemma", "missing_start", "spaced_letters", "leading_punctuation", "leading_call", "hyphen_cut", "italic_seam", "period_seam", "etc_for_et", "long_translation", "no_translation", "translation_no_punct", "verse_no_punct", "footnote_no_period", "stray_underscore", "lowercase_translation", "hebrew_in_translation", "hebrew_recheck", "guessed_ref", "chapter_ref", "lemma_verse", "verse_mismatch", "footnote_asterisk", "lowercase_lemma", "lemma_no_punct", "lemma_unknown_word", "extra_footnotes", "empty_commentary", "caps_in_commentary", "broken_marker", "possible_gap",
             "missing_footnote", "empty_page", "seam_artifact"]
    queue = [q for r in results for q in r.get("queue", [])]
    # Psalms: verses checked against the Vulgate text (psalms_check.py), since Calmet's
    # numbering differs from the Vulgate's and numbers can't be compared
    import psalms_check
    for vol in BOOKS["psalms"]["studium"]:
        if not (STUDIUM / vol / "normalized").is_dir():
            continue
        for x in psalms_check.check(vol)[1]:
            kind = {"missing": "psalm_missing_verse", "missing_title": "psalm_missing_title",
                    "number": "psalm_number", "repeated": "duplicate_verse"}.get(x["kind"], "psalm_" + x["kind"])
            queue.append(dict(id=f"{vol}/{x['page']:04d}/{kind}/{hashlib.md5(x['msg'].encode()).hexdigest()[:8]}",
                              book_dir=vol, page=x["page"], kind=kind, msg=x["msg"], optional=False))
    # Where assign_chapters.py had to decide a chapter against the numbering, or saw a heading out of step
    chapter_file = DOCS / "chapter_check.json"
    if chapter_file.exists():
        for x in json.loads(chapter_file.read_text()):
            kind = {"vulgate": "chapter_vulgate", "vulgate_verse": "chapter_vulgate",
                    "restart": "chapter_heading", "jump": "chapter_heading"}.get(x["kind"])
            if kind:
                vol, stem = x["page"].split("/")
                queue.append(dict(id=f"{vol}/{stem[5:9]}/{kind}/{hashlib.md5(x['msg'].encode()).hexdigest()[:8]}",
                                  book_dir=vol, page=int(stem[5:9]), kind=kind, msg=x["msg"], optional=False))
    # Footnote Hebrew that footnotes.py's scan corrected but still couldn't find in the Hebrew Bible
    for fn_file in sorted((DOCS / "footnotes").glob("*.json")):
        vol = fn_file.stem
        if not (STUDIUM / vol).is_dir():  # held.json, tags_auto.json: not a volume's report
            continue
        for n in json.loads(fn_file.read_text())["notes"]:
            if "hebrew-recheck" in n["flags"]:
                queue.append(dict(id=f"{vol}/{n['page'][5:9]}/hebrew_recheck/{n['marker']}", book_dir=vol,
                                  page=int(n["page"][5:9]), kind="hebrew_recheck", optional=False,
                                  msg=f"footnote {n['marker']}: was {n['text'][:80]} → now {n['proposed'][:80]}. "
                                      + " ".join(n["why"])))
    queue += latin_long_s()
    # Page breaks read by seam_check.py replace the punctuation guesses for those books
    seam_file = DOCS / "seam_check.json"
    if seam_file.exists():
        read = json.loads(seam_file.read_text())
        done = seam_fully_read(read)
        queue = [q for q in queue if not (q["book_dir"] in done and q["kind"] in ("possible_gap", "seam_artifact"))]
        for book, res in read.items():
            if any(book in BOOKS[k]["studium"] for k in EXCLUDED):
                continue
            for x in res["flagged"]:
                kind = {"missing": "seam_missing", "repeat": "seam_repeat"}.get(x["verdict"], "seam_unclear")
                queue.append(dict(id=f"{book}/{x['page'][5:9]}/{kind}/{x['before_page'][5:9]}", book_dir=book,
                                  page=int(x["page"][5:9]), kind=kind, optional=False,
                                  msg=f"{x['why']} — “…{x['tail'][-50:]}” ‖ “{x['head'][:50]}…”"))
    queue = sorted(queue,
                   key=lambda q: (order.index(q["kind"]), q["book_dir"], q["page"]))
    if FP_IDS:
        before_len = len(queue)
        queue = [q for q in queue if not FP_IDS.matches(q["id"], q["book_dir"], q["page"], q["kind"], q["msg"], q.get("where"))]
        filtered = before_len - len(queue)
        if filtered:
            print(f"filtered out {filtered} permanently resolved false positive(s)")
    qpath = out.with_name("review_queue.json")
    qpath.write_text(json.dumps(queue, ensure_ascii=False, indent=1))
    print(f"wrote {qpath} ({len(queue)} items, {sum(not q['optional'] for q in queue)} required)")


if __name__ == "__main__":
    main()
