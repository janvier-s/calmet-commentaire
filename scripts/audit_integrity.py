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
ORDER_OK = json.loads((STUDIUM / "verse_ref_order_ok.json").read_text(encoding="utf-8")) \
    if (STUDIUM / "verse_ref_order_ok.json").exists() else {}  # fix_verse_refs.py: out of order on purpose
WHICH_BOOK = re.compile(r"\b(?:Rois|Paralipomènes|Machabées|Esdras),?\s+chapitres?\s+\d+(?::\d+(?:(?:-|, )\d+)*)?")

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
    for d in reviews():
        fp_ids.update(d.get("false_positives") or {})
        fp_ids.update(k for k, v in (d.get("status") or {}).items() if v == "false_positive")
    return fp_ids

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

def audit_book(key, info, slug, published=True):
    r = dict(key=key, fr=info["fr"], slug=slug, volumes=info["studium"])
    # ---------- source pages ----------
    pages, malformed, raw_only = [], [], []
    for vol in info["studium"]:
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
    r["pages"] = len(pages)
    r["malformed"] = malformed
    r["raw_not_normalized"] = raw_only
    # numbering gaps in the page sequence
    gaps = []
    for vol in info["studium"]:
        nums = sorted({int(n[5:9]) for v, n, _ in pages if v == vol} |
                      {int(m.split("/")[1][5:9]) for m in malformed if m.startswith(vol + "/")})
        gaps += [f"{vol}/page_{a+1:04d}" + (f"–{b-1:04d}" if b - a > 2 else "")
                 for a, b in zip(nums, nums[1:]) if b - a > 1]
    r["page_number_gaps"] = gaps
    # empty / thin pages
    sizes = []
    empty, thin = [], []
    for vol, n, d in pages:
        c = sum(len(b.get("french_commentary") or "") for b in d.get("commentary") or [])
        v = sum(len(x.get("french") or "") for x in d.get("verses") or [])
        i = len((d.get("chapter_intro") or "").strip())
        a = len((d.get("chapter_argument") or "").strip())
        sizes.append(c + v + i + a)
        if not (d.get("commentary") or d.get("verses") or a or i):  # Intro / argument / commentary pages
            empty.append(f"{vol}/{n}")
    med = statistics.median(sizes) if sizes else 0
    for (vol, n, d), s in zip(pages, sizes):
        if 0 < s < 0.2 * med:
            thin.append(f"{vol}/{n} ({s} chars)")
    r["empty_pages"], r["thin_pages"], r["median_page_chars"] = empty, thin, int(med)
    # suspicious seams between consecutive pages' commentary
    seams = []
    prev = None
    for vol, n, d in pages:
        blocks = [b for b in d.get("commentary") or [] if (b.get("french_commentary") or "").strip()]
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
            if cont and ended:
                seams.append(dict(seam=f"{pn}>{vol}/{n}", kind="gap? continuation after a full stop",
                                  before=t[-60:], after=head[:60]))
            elif not ended and t[-1:].isalpha() and not cont and new_lemma:
                seams.append(dict(seam=f"{pn}>{vol}/{n}", kind="gap? sentence cut, next page opens a new lemma",
                                  before=t[-60:], after=head[:60]))
            elif cont and first.get("verse_ref"):
                seams.append(dict(seam=f"{pn}>{vol}/{n}", kind="continuation tagged as a new note",
                                  before=t[-60:], after=head[:60]))
        prev = (f"{vol}/{n}", blocks[-1].get("french_commentary") or "")
    r["suspicious_seams"] = seams

    # ---------- review queue: what a person has to check against the scans ----------
    queue = r["queue"] = []
    def vol_of(page_name):
        return next((v for v in info["studium"] if (STUDIUM / v / "normalized" / page_name).exists()), None)

    latin = {}
    def latin_of(vol):
        if vol not in latin:
            latin[vol] = {(str(v.get("chapter")), str(v.get("verse_number"))): v.get("latin") or ""
                          for vv, _, dd in pages if vv == vol for v in dd.get("verses") or []}
        return latin[vol]

    def item(kind, vol, page, msg, optional=False, where=None):
        # Stable across runs, so review progress survives a re-audit; `where`: the entry and field
        uid = hashlib.md5(msg.encode()).hexdigest()[:8]
        item_id = f"{vol}/{page:04d}/{kind}/{uid}"
        if item_id in FP_IDS:
            return
        queue.append(dict(id=item_id, book_dir=vol, page=page,
                          kind=kind, msg=msg, optional=optional, **({"where": where} if where else {})))

    for g in gaps:
        vol, rest = g.split("/")
        a = int(rest[5:9]); b = int(rest.split("–")[1]) if "–" in rest else a
        for pg in range(a, b + 1):
            item("missing_page", vol, pg, "Page has no JSON at all: create it from the scan and transcribe it")
    for m in malformed:
        vol, n = m.split("/")
        item("malformed_page", vol, int(n[5:9]), "Page JSON is malformed and is skipped by every export: repair it")
    for e in empty:
        vol, n = e.split("/")
        item("empty_page", vol, int(n[5:9]), "Page has neither verses nor commentary: blank/plate, or lost content?")
    for s in seams:
        a, b = s["seam"].split(">")
        vol, n = b.split("/")
        if s["kind"].startswith("gap? sentence cut"):
            item("possible_gap", vol, int(n[5:9]),
                 f"Possible lost text at the page turn: “…{s['before'][-45:]}” ‖ “{s['after'][:45]}…”")
        elif s["kind"].startswith("gap? continuation"):
            item("seam_artifact", vol, int(n[5:9]),
                 f"Page-turn glitch (stray full stop / repeated syllable): “…{s['before'][-40:]}” ‖ “{s['after'][:40]}…”",
                 optional=True)

    # verse_ref must run in order within a chapter (the `chapter` field, assign_chapters.py):
    # a drop inside a chapter is a misread number, or Calmet going back to a verse.
    nums = []
    for vol, n, d in pages:
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
            item("ref_order", vol, int(n[5:9]),
                 f"verse_ref goes back from {prev} to {ref} (… {ctx} …) in chapter {ch}: "
                 f"misread number, or Calmet returning to a verse?",
                 where=dict(section="commentary", index=ci, field="verse_ref"))

    # The chapter field: on every entry after the book's first heading, never going back
    # or skipping a chapter.
    for section, field in (("verses", "verse_number"), ("commentary", "verse_ref")):
        prev = None
        for vol, n, d in pages:
            for ei, e in enumerate(d.get(section) or []):
                ch = e.get("chapter")
                if not isinstance(ch, int):
                    if prev is not None:
                        item("chapter_field", vol, int(n[5:9]), f"{section}: {field} {e.get(field)} has no chapter",
                             where=dict(section=section, index=ei, field="chapter"))
                    continue
                if prev is not None and not (prev <= ch <= prev + 1):
                    item("chapter_field", vol, int(n[5:9]),
                         f"{section}: chapter goes from {prev} to {ch} at {field} {e.get(field)}",
                         where=dict(section=section, index=ei, field="chapter"))
                prev = ch
    r["ref_out_of_order"] = out_of_order

    # Notes with no commentary. Fine when the comment opens the next page, or when
    # Calmet gives only the translation; suspicious when nothing follows the lemma.
    CAPS = re.compile(r"\b[A-ZÀ-ÝŒÆ]{2,}(?:[\s,;:'’.-]+[A-ZÀ-ÝŒÆ]{2,})+\b")
    ODD_MARK = re.compile(r"\^[^{]|\^\{(?!\([a-z]\)\})[^}]*\}")
    empty_notes = caps_runs = odd_marks = 0

    def runs_over(i):
        """The first note of page i+1 finishes the last note of page i (no comment yet, same verse)."""
        if i + 1 >= len(pages) or pages[i + 1][0] != pages[i][0]:
            return None
        last = (pages[i][2].get("commentary") or [None])[-1]
        first = (pages[i + 1][2].get("commentary") or [None])[0]
        if not last or not first or (last.get("french_commentary") or "").strip():
            return None
        ref = str(first.get("verse_ref") or "").strip()
        return first if not ref or ref == str(last.get("verse_ref") or "").strip() else None

    for i, (vol, n, d) in enumerate(pages):
        if chapter_of(d) and not str(d.get("chapter_summary") or "").strip():
            item("empty_summary", vol, int(n[5:9]),
                 f"Chapter {chapter_of(d)} opens here but chapter_summary is empty: type it from the scan "
                 f"(or the heading is a running head and chapter_number/chapter_title should go)")
        cs = d.get("commentary") or []
        nxt_page = pages[i + 1][2] if i + 1 < len(pages) and pages[i + 1][0] == vol else None
        notes_here = {re.sub(r"\W", "", str(fn.get("marker") or "")) for fn in d.get("footnotes") or []}
        for j, c in enumerate(cs):
            lemma = (c.get("latin_quote") or "").strip()
            tr = (c.get("french_translation") or "").strip()
            fc = c.get("french_commentary") or ""
            if not fc.strip():
                if j == len(cs) - 1 and lemma and not tr:
                    problem = None  # a lemma alone at the foot of the page: its text is overleaf
                elif j == len(cs) - 1:
                    first = ((nxt_page or {}).get("commentary") or [{}])[0]
                    problem = None if nxt_page and not (first.get("latin_quote") or "").strip() else \
                        "is the last note on the page and the next page starts a new lemma: comment lost at the page break?"
                elif not (cs[j + 1].get("latin_quote") or "").strip():
                    problem = "is followed by a block with no lemma: one note split in two?"
                elif not tr:
                    problem = "has neither translation nor comment" + (" (the comment may be inside latin_quote)" if re.search(r"[a-zé]{4,}", lemma) else "")
                elif not re.search(r"[.!?»]_?(\s*\^\{\([a-z]\)\})?$", tr):
                    problem = "has no comment and its translation is cut off"
                else:
                    problem = None
                if problem:
                    empty_notes += 1
                    item("empty_commentary", vol, int(n[5:9]), f"Note “{lemma[:40]}” (℣ {c.get('verse_ref')}) {problem}",
                         where=dict(section="commentary", index=j, field="french_commentary"))
            for m in CAPS.finditer(fc):
                if re.fullmatch(r"[IVXLC.\s,et]+", m.group()):
                    continue
                caps_runs += 1
                where = "starts the comment" if m.start() < 3 else "inside the comment"
                item("caps_in_commentary", vol, int(n[5:9]),
                     f"Capitals {where}: “…{fc[max(0, m.start() - 25):m.end() + 15]}…”: a lemma that should start its own note, or a word to put in lower case?",
                     where=dict(section="commentary", index=j, field="french_commentary"))
            for k in ("latin_quote", "french_translation", "french_commentary"):
                for m in re.finditer(r"(?<![\w.])(?:[A-Za-zÀ-ÿŒÆœæ] ){3,}[A-Za-zÀ-ÿŒÆœæ](?!\w)", c.get(k) or ""):
                    item("spaced_letters", vol, int(n[5:9]),
                         f"Letter-spaced word in {k}: “{m.group()}”: close up the letters (put the word breaks back)",
                         where=dict(section="commentary", index=j, field=k))
            for k in ("latin_quote", "french_translation", "french_commentary"):
                m = re.match(r"\s*\^\{[^}]*\}", c.get(k) or "")
                if m:
                    item("leading_call", vol, int(n[5:9]),
                         f"{k} of note {c.get('commentary_id')} (℣ {c.get('verse_ref')}) starts with the footnote call "
                         f"“{m.group().strip()}”: “{(c.get(k) or '')[:60]}…”: move it after the word it belongs to "
                         f"(end of the previous field or page?)",
                         where=dict(section="commentary", index=j, field=k))
            if re.match(r"\s*[.,;:!?»]", fc):
                item("leading_punctuation", vol, int(n[5:9]),
                     f"Comment starts with punctuation “{fc[:40]}…”"
                     + (": move it to the end of the translation (tidy_fields.py does)" if tr else
                        ": no translation in this block, so it belongs to the text before (previous page?)"),
                     where=dict(section="commentary", index=j, field="french_commentary"))
            # a lemma or translation cut by the page turn ("PER-", or mid-sentence in a note whose
            # comment hasn't started) must go on in the same field overleaf
            for k in ("latin_quote", "french_translation"):
                t = re.sub(r"\^\{[^}]*\}", "", c.get(k) or "").rstrip()
                if not t:
                    continue
                hyphen = t.endswith("-")
                open_ = (j == len(cs) - 1 and not fc.strip() and not re.search(r"[.!?»…)\]]$", t)
                         and (k == "french_translation" or not tr))
                if not (hyphen or open_):
                    continue
                first = ((nxt_page or {}).get("commentary") or [{}])[0] if j == len(cs) - 1 else {}
                if (first.get(k) or "").strip():
                    continue
                overleaf = (first.get("french_commentary") or first.get("french_translation")
                            or first.get("latin_quote") or "")
                item("hyphen_cut", vol, int(n[5:9]),
                     f"{k} ends “…{t[-40:]}”" + ("" if hyphen else " with no full stop") + " but "
                     + (f"the next page's first note has no {k} (it starts “{overleaf[:50]}…”)"
                        if j == len(cs) - 1 else "another note follows on this page")
                     + f": put the rest of the {k} back together"
                     + ("" if hyphen else " (or add the missing full stop)"),
                     where=dict(section="commentary", index=j, field=k))
            # the page turn inside a comment: italics and sentences must carry over
            nfirst = ((nxt_page or {}).get("commentary") or [{}])[0] if j == len(cs) - 1 else {}
            nfc = nfirst.get("french_commentary") or ""
            if fc.strip() and nfc.strip() and not (nfirst.get("latin_quote") or "").strip() \
                    and not (nfirst.get("french_translation") or "").strip():
                if fc.count("_") % 2 and not nfc.count("_") % 2:
                    item("italic_seam", vol, int(n[5:9]),
                         f"Italics still open at the foot of the page (“…{fc[fc.rfind('_'):][-60:]}”) but not closed "
                         f"overleaf (“{nfc[:50]}…”): close them here, or a “_” is missing or extra",
                         where=dict(section="commentary", index=j, field="french_commentary"))
                tail = re.sub(r"(\s*\^\{[^}]*\})+\s*$", "", fc).rstrip()
                head = re.match(r"\s*[_«\"(]*\s*(\w)", nfc)
                # italics closed right at the foot of the page, mid-sentence, while the quotation runs
                # on in roman overleaf (Ruth 25-26: "…d'un homme_" ‖ "d'honneur.")
                run = re.search(r"_([^_]+)_$", tail)
                if (run and not fc.count("_") % 2 and not re.search(r"[.;:!?»]$", run.group(1).rstrip())
                        and len(run.group(1).split()) >= 2 and not re.match(r"\s*_", nfc)
                        and head and head.group(1).islower()):
                    item("italic_seam", vol, int(n[5:9]),
                         f"Italics closed at the very foot of the page (“…{tail[-50:]}”) but the sentence goes on "
                         f"in roman overleaf (“{nfc[:50]}…”): carry the italics over to where the quotation ends",
                         where=dict(section="commentary", index=j, field="french_commentary"))
                if tail.endswith(".") and head and head.group(1).islower() and not ABBREV.search(tail):
                    item("period_seam", vol, int(n[5:9]),
                         f"Full stop at the foot of the page (“…{tail[-45:]}”) but the next page goes on in "
                         f"lower case (“{nfc[:45]}…”): stray full stop, or a capital to restore?",
                         where=dict(section="commentary", index=j, field="french_commentary"))
            # a comment opening mid-sentence on a page whose predecessor has nothing for it to go on from
            if j == 0 and fc.strip() and i and pages[i - 1][0] == vol and int(pages[i - 1][1][5:9]) == int(n[5:9]) - 1:
                before = (pages[i - 1][2].get("commentary") or [None])[-1]
                if start_missing(before, c):
                    item("missing_start", vol, int(n[5:9]),
                         f"The first note opens in the middle of a sentence (“{fc[:50]}…”) but "
                         + (f"the last note of the page before (“{(before.get('latin_quote') or before.get('french_translation') or '')[:40]}…”) has no comment"
                            if before else "the page before has no notes")
                         + ": the start of the comment is missing (typed on the page before, or lost at the page turn)",
                         where=dict(section="commentary", index=0, field="french_commentary"))
            # the first note of a page with no lemma at all: the end of the note before, or a note whose lemma was lost
            if j == 0 and not lemma and not tr and fc.strip():
                before = next((cc[-1].get("french_commentary") or "" for vv, _, dd in reversed(pages[max(0, i - 20):i])
                               if vv == vol and (cc := dd.get("commentary") or []) and (cc[-1].get("french_commentary") or "").strip()),
                              None)
                why = first_note_without_lemma(before, fc) if before else None
                if why:
                    item("first_no_lemma", vol, int(n[5:9]),
                         (f"The first note opens with what looks like its lemma in capitals (“{fc[:60]}…”): "
                          f"move it to latin_quote" if why == "lemma" else
                          f"The first note (“{fc[:50]}…”) has no latin_quote or french_translation, but the page "
                          f"before ends a sentence (…{before.rstrip()[-40:]}): a new note whose lemma was lost, "
                          f"or the next sentence of the same note?"),
                         optional=why == "sentence", where=dict(section="commentary", index=0, field="latin_quote"))
            # only the first block of a page may lack a lemma (it continues the page before)
            if not lemma and c.get("commentary_id") != 1:
                why = ("the lemma is at the start of the comment: move it to latin_quote"
                       if re.match(r"\s*[A-ZÀ-ÝŒÆ]{2,}[\sA-ZÀ-ÝŒÆ',.;:?!-]{6,}", fc) else
                       "one note split in two, or a lemma lost?")
                item("no_lemma", vol, int(n[5:9]),
                     f"Note {c.get('commentary_id')} (℣ {c.get('verse_ref')}) has no latin_quote: “{(tr or fc)[:70]}…”: {why}",
                 where=dict(section="commentary", index=j, field="latin_quote"))
            # the lemma: printed in capitals, with a verse_ref, and a translation of about its length
            bare = re.sub(r"\^\{[^}]*\}", "", lemma)
            if (lemma or tr) and not str(c.get("verse_ref") or "").strip():
                item("no_verse_ref", vol, int(n[5:9]), f"Note “{(lemma or tr)[:50]}” has no verse_ref",
                     where=dict(section="commentary", index=j, field="verse_ref"))
            if re.search(r"[a-zàâçéèêëîïôûùüÿœæ]", bare):
                item("lowercase_lemma", vol, int(n[5:9]),
                     f"Lower case in latin_quote “{lemma[:70]}”: French or commentary in the lemma field?",
                     where=dict(section="commentary", index=j, field="latin_quote"))
            # the site takes the lemma's capitals from the Vulgate (calmet.py latin_case): a word the
            # Vulgate lacks comes out in lower case
            unknown = [w for w in re.findall(r"[^\W\d_]{3,}", STRAY.sub("", lemma))
                       if _fold(w) not in vulgate_words() and w.lower() != "etc"]
            if unknown:
                item("lemma_unknown_word", vol, int(n[5:9]),
                     f"Not in the Vulgate: {', '.join(unknown)} in “{lemma[:60]}”: a name (add it to "
                     f"scripts/latin_names.txt), a misreading, French in the lemma, or a word cut in two?",
                     optional=True, where=dict(section="commentary", index=j, field="latin_quote"))
            # a lemma and translation split by the page turn are measured whole
            la, fr, cut = bare, tr, ""
            if j == len(cs) - 1 and (rest := runs_over(i)):
                la = (la + " " + re.sub(r"\^\{[^}]*\}", "", rest.get("latin_quote") or "")).strip()
                fr, cut = (fr + " " + (rest.get("french_translation") or "")).strip(), " (with the next page)"
            if j == 0 and i and runs_over(i - 1):
                la = ""  # measured with the previous page's last note
            if la and len(fr) > 3 * len(la) and len(fr) - len(la) > 40:
                item("long_translation", vol, int(n[5:9]),
                     f"Translation of {len(fr)} characters for a lemma of {len(la)}{cut} “{lemma[:40]}”: "
                     f"“{fr[:90]}…”: commentary run into the translation?",
                     where=dict(section="commentary", index=j, field="french_translation"))
            if la.strip() and not fr:
                fc, where = c.get("french_commentary") or "", "the comment starts"
                overleaf = (j == len(cs) - 1 and not fc.strip() and i + 1 < len(pages) and pages[i + 1][0] == vol
                            and (pages[i + 1][2].get("commentary") or [None])[0])
                if overleaf:  # the last note of the page, its comment overleaf
                    fc, where = overleaf.get("french_commentary") or "", "the next page starts"
                one_word = len(re.findall(r"[^\W\d_]+", la)) == 1
                why = ("French in the lemma?" if re.search(r"[a-zàâçéèêëîïôûùüÿœæ]{3}", la) else
                       "the translation run into the commentary?" if re.match(r"\s*_[^_]{3,}_", fc)
                       or re.match(rf"\s*[^.;:,]{{{len(la) // 2},{len(la) * 3}}}[.;:,]", fc) else
                       "a name Calmet leaves untranslated?" if one_word else "a translation lost?")
                item("no_translation", vol, int(n[5:9]),
                     f"Note {c.get('commentary_id')} (℣ {c.get('verse_ref')}): latin_quote “{lemma[:50]}” has no "
                     f"french_translation; {where} “{fc[:60]}…”: {why}", optional=one_word,
                     where=dict(section="commentary", index=j, field="french_translation"))
            if re.search(r"\bl['’]\s?h[ée]breu", tr, re.I):
                item("hebrew_in_translation", vol, int(n[5:9]),
                     f"“L'Hébreu” in the translation of “{lemma[:40]}”: “{tr[:100]}…”: commentary run into the translation?",
                     where=dict(section="commentary", index=j, field="french_translation"))
            if tr:
                tr_bare = tr.rstrip("_* \t")
                if j != len(cs) - 1 and not re.search(r"\^\{[^\}]+\}\s*$", tr_bare):
                    if not tr_bare.rstrip("])»”\"'").endswith((".", ",", ";", ":", "!", "?", "…")):
                        item("translation_no_punct", vol, int(n[5:9]),
                             f"Note {c.get('commentary_id')} (℣ {c.get('verse_ref')}): french_translation does not end with punctuation: “{tr[-50:]}”",
                             where=dict(section="commentary", index=j, field="french_translation"))
                if j != 0:
                    clean_start = re.sub(r"^\s*(\^\{[^}]*\}|[\s_«\"'‘“\(\[\{:§.])+", "", tr)
                    m = re.search(r"[A-Za-zÀ-ÖØ-öø-ÿœæŒÆ]", clean_start)
                    if m and m.group(0).islower():
                        item("lowercase_translation", vol, int(n[5:9]),
                             f"Note {c.get('commentary_id')} (℣ {c.get('verse_ref')}): french_translation missing initial capital: starts with “{m.group(0)}” in “{tr[:50]}…”",
                             where=dict(section="commentary", index=j, field="french_translation"))
            if lemma:
                la_bare = lemma.rstrip("_* \t")
                if j != len(cs) - 1 and not re.search(r"\^\{[^\}]+\}\s*$", la_bare):
                    if not la_bare.rstrip("])»”\"'").endswith((".", ",", ";", ":", "!", "?", "…")):
                        item("lemma_no_punct", vol, int(n[5:9]),
                             f"Note {c.get('commentary_id')} (℣ {c.get('verse_ref')}): latin_quote does not end with punctuation: “{lemma[-50:]}”",
                             where=dict(section="commentary", index=j, field="latin_quote"))
            for k in ("latin_quote", "french_translation", "french_commentary"):
                t = c.get(k) or ""
                bad = [m.group() for m in ODD_MARK.finditer(t)]
                bad += [m.group() for m in re.finditer(r"(?<![\^{\w])\(\s?([a-z])\s?\)(?!\})", t) if m.group(1) not in notes_here]
                for b in bad:
                    odd_marks += 1
                    pos = t.find(b)
                    item("broken_marker", vol, int(n[5:9]),
                         f"Footnote call “{b}” in {k}: “…{t[max(0, pos - 30):pos + len(b) + 10]}…”",
                         where=dict(section="commentary", index=j, field=k))
        fns = d.get("footnotes") or []
        # Bible references guessed from the context (starred), or left as printed with no such verse
        texts = [(f"commentary {c.get('commentary_id')}", c.get("french_commentary") or "") for c in d.get("commentary") or []]
        texts += [(f"footnote {f.get('marker')}", str(f.get("text") or "")) for f in fns]
        guessed = [f"{where}: “{m.group()}”" for where, t in texts for m in GUESSED_REF.finditer(t)]
        printed = [f"“{src}”" for (page, src), v in REF_MANUAL.items() if v is None and page == f"{vol}/page_{n[5:9]}"]
        if guessed or printed:
            item("guessed_ref", vol, int(n[5:9]), "; ".join(
                ([", ".join(guessed) + " guessed from the context: check against the scan, then remove the asterisk "
                  "or set the reference right"] if guessed else [])
                + ([f"Calmet's {', '.join(printed)} written out as printed, but no such verse in the Vulgate: "
                    "check against the scan"] if printed else [])))
        # lemmas filled in by hand where there was none, and lemmas whose words are in another verse
        added = lemma_added(vol, n)
        for j, c in enumerate(d.get("commentary") or []):
            lemma = c.get("latin_quote") or ""
            if not lemma.strip():
                continue
            fc = flat(c.get("french_commentary") or "")
            # the same block: one commentary holds the other's start (a lemma moved out of it, a block joined)
            by_hand = fc and any(fc[:40] in o or o[:40] in fc or fc[-40:] in o for o in added)
            ch, ref = str(c.get("chapter") or ""), str(c.get("verse_ref") or "")
            score, best = best_verse(re.sub(r"\^\{[^}]*\}", "", lemma), {v: t for (cc, v), t in latin_of(vol).items() if cc == ch})
            span = re.fullmatch(r"(\d+)\s*[-–]\s*(\d+)", ref)  # "16-17": the best of the verses it covers
            if span and score:
                inside = [str(v) for v in range(int(span[1]), int(span[2]) + 1)]
                score[ref] = max(score.get(v, 0) for v in inside)
                best = ref if best in inside else best
            if by_hand:
                hint = (f"its words fit ℣ {best} better ({score[best]:.0%} against {score.get(ref, 0):.0%})"
                        if best and best != ref and score[best] > score.get(ref, 0) else
                        f"its words fit ℣ {ref}" if score.get(ref) else "")
                item("lemma_verse", vol, int(n[5:9]),
                     f"Note {c.get('commentary_id')} had no latin_quote; now “{lemma[:60]}” at chapter {ch}, ℣ {ref}: "
                     f"check the verse number{': ' + hint if hint else ''}", optional="better" not in hint,
                     where=dict(section="commentary", index=j, field="verse_ref"))
            elif best and best != ref and score[best] >= 0.8 and score.get(ref, 0) <= 0.4 \
                    and len(re.findall(r"[^\W\d_]{3,}", lemma)) >= 2:
                item("verse_mismatch", vol, int(n[5:9]),
                     f"Note {c.get('commentary_id')} “{lemma[:60]}” is under chapter {ch}, ℣ {ref}, but its words are in "
                     f"℣ {best} ({score[best]:.0%} against {score.get(ref, 0):.0%}): wrong verse_ref, or the verse misnumbered?",
                     where=dict(section="commentary", index=j, field="verse_ref"))
        # chapter references chapter_refs.py could not write out: which book, or which numbers?
        for j, c in enumerate(d.get("commentary") or []):
            t, where = c.get("french_commentary") or "", f"commentary {c.get('commentary_id')} (℣ {c.get('verse_ref')})"
            left = [m.group().strip(" ,") for m in CH_REF.finditer(t) if chapter_write(m, t) == m.group()]
            which = [t[max(0, m.start() - 30):m.end()].lstrip() for m in WHICH_BOOK.finditer(t)]
            if left:
                item("chapter_ref", vol, int(n[5:9]), f"{where}: “{'”, “'.join(left)}” left as printed (chapters "
                     "not in order: a verse, or a word?): write it as “chapitre C:V”, or “Livre C:V” after a book",
                     where=dict(section="commentary", index=j, field="french_commentary"))
            if which:
                item("chapter_ref", vol, int(n[5:9]), f"{where}: “…{'”, “…'.join(which)}”: which book? write it as "
                     "“2 Rois 1:18” / “1 Paralipomènes 9:22”",
                     where=dict(section="commentary", index=j, field="french_commentary"))
        # an asterisk marks footnote text that was guessed, not read on the scan: one item per page
        starred = [str(f.get("marker")) for f in fns if "*" in GUESSED_REF.sub("", str(f.get("text") or ""))]
        if starred:
            item("footnote_asterisk", vol, int(n[5:9]),
                 f"Footnote{'s' if len(starred) > 1 else ''} {', '.join(starred)}: words marked * were guessed: "
                 f"check them against the scan, then remove the asterisks")
        called = set(re.findall(r"\^\{\(([a-z])\)\}", json.dumps({k: v for k, v in d.items() if k != "footnotes"},
                                                                ensure_ascii=False)))
        if len(fns) > len(called):
            uncalled = [str(f.get("marker")) for f in fns if re.sub(r"\W", "", str(f.get("marker") or "")) not in called]
            item("extra_footnotes", vol, int(n[5:9]),
                 f"{len(fns)} footnotes for {len(called)} calls in the text"
                 + (f": nothing calls {', '.join(uncalled)}" if uncalled else ": a marker is used twice")
                 + " (footnote from another page, a call lost, or a duplicate?)")
    # "&" (et) at the bottom of the page misread as "etc." at the end of the last commentary block
    ETC_END = re.compile(r"\b(?:etc|ETC)\.?[_\s»”)]*$")
    for vol, n, d in pages:
        comm = d.get("commentary") or []
        if not comm:
            continue
        t = (comm[-1].get("french_commentary") or "").strip()
        m = ETC_END.search(t)
        if m:
            item("etc_for_et", vol, int(n[5:9]),
                 f"Last commentary ends with “{m.group(0).strip()}”: “…{t[max(0, m.start() - 45):]}” — "
                 f"an “&” (et) at the page turn misread as etc.? (fine if the scan has &c.)",
                 where=dict(section="commentary", index=len(comm) - 1, field="french_commentary"))
    # A page whose commentary repeats a neighbour's: one of the two scans was transcribed twice
    def shingles(d):
        w = re.findall(r"\w+", " ".join((c.get("french_commentary") or "") + " " + (c.get("latin_quote") or "")
                                        for c in d.get("commentary") or []).lower())
        return {" ".join(w[k:k + 4]) for k in range(len(w) - 3)}
    sh = [(vol, n, shingles(d)) for vol, n, d in pages]
    for i, (vol, n, a) in enumerate(sh):
        for vol2, n2, b in sh[i + 1:i + 3]:
            if vol2 == vol and len(a) > 40 and len(b) > 40 and len(a & b) / min(len(a), len(b)) > 0.5:
                item("duplicate_page", vol, int(n[5:9]),
                     f"Commentary of page {int(n[5:9])} repeats page {int(n2[5:9])} "
                     f"({round(100 * len(a & b) / min(len(a), len(b)))}% the same): one of them must be retranscribed from its scan")
    # verses filled in from the Vulgate (fill_psalm_verses.py) until their French is typed;
    # any other verse without French lost it in transcription
    for vol, n, d in pages:
        for vi, v in enumerate(d.get("verses") or []):
            if (v.get("french") or "").strip():
                continue
            if str(v.get("annotations") or "").startswith("Latin from the Vulgate"):
                item("vulgate_filled", vol, int(n[5:9]),
                     f"Verse {v.get('verse_number')} was missing: its Latin is filled in from the Vulgate "
                     f"(“{(v.get('latin') or '')[:50]}…”). Check it against the scan, type Calmet's French, then clear the note",
                     where=dict(section="verses", index=vi, field="french"))
            else:
                item("missing_french", vol, int(n[5:9]),
                     f"Verse {v.get('chapter')}:{v.get('verse_number')} has no French "
                     f"(Latin: “{(v.get('latin') or '')[:50]}…”): type Calmet's translation from the scan",
                     where=dict(section="verses", index=vi, field="french"))
    # the end of a verse, a footnote; italics opened and never closed (or the reverse) within a field
    tail = lambda s: re.sub(r"(\s*(\^\{[^}]*\}|[_*»”\"')\]]))+\s*$", "", s.rstrip())
    for vol, n, d in pages:
        for vi, v in enumerate(d.get("verses") or []):
            for k in ("latin", "french"):
                end = tail(v.get(k) or "")
                if end and not end.endswith((".", ",", ";", ":", "!", "?", "…")):
                    item("verse_no_punct", vol, int(n[5:9]),
                         f"Verse {v.get('chapter')}:{v.get('verse_number')}: {k} does not end with punctuation: “…{end[-50:]}” "
                         "(a word lost, or the verse runs on overleaf?)", where=dict(section="verses", index=vi, field=k))
        for fi, f in enumerate(d.get("footnotes") or []):
            end = tail(str(f.get("text") or ""))
            # Hebrew and Greek are printed without a stop after them
            if end and not end.endswith((".", "!", "?", "…")) and not re.search(r"[\u0370-\u03FF\u1F00-\u1FFF\u0590-\u05FF\uFB1D-\uFB4F]\W*$", end) \
                    and not re.search(r"\[UNCERTAIN [A-Z]+\]?$", end):
                item("footnote_no_period", vol, int(n[5:9]),
                     f"Footnote {f.get('marker')} does not end with a full stop: “…{end[-60:]}”",
                     where=dict(section="footnotes", index=fi, field="text"))
        cs = d.get("commentary") or []
        fields = [("verses", vi, v, k) for vi, v in enumerate(d.get("verses") or []) for k in ("latin", "french", "annotations")]
        fields += [("commentary", j, c, k) for j, c in enumerate(cs) for k in ("latin_quote", "french_translation", "french_commentary")]
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
            item("stray_underscore", vol, int(n[5:9]),
                 f"Italics in {k} ({sec} {i + 1}): {why}: “{text[max(0, at - 40):at + 25]}”",
                 where=dict(section=sec, index=i, field=k))
    r["empty_commentary"], r["caps_in_commentary"], r["broken_markers"] = empty_notes, caps_runs, odd_marks

    # ---------- assembled chapters & notes (from normalized/) ----------
    if not pages:
        r["published"] = False
        return r
    r["published"] = published
    chapters, summaries, _ = verses_by_chapter(key)
    vul = {c["chapter"]: {v["verse"] for v in c["verses"]}
           for c in json.loads((VUL / f"{info['vul']}.json").read_text())["chapters"]}
    r["chapters_site"], r["chapters_vulgate"] = len(chapters), len(vul)
    r["chapters_missing"] = sorted(set(vul) - set(chapters))
    verse_issues, empty_verse = [], []
    fr_hits, fr_words, la_hits = Counter(), 0, Counter()
    note_hits, note_words = Counter(), 0
    site_text = []
    orphan_notes, missing_fn = [], 0
    total_verses = 0
    for ch in sorted(chapters):
        vs = chapters[ch]
        total_verses += len(vs)
        nums = [v.get("verse_number") for v in vs if isinstance(v.get("verse_number"), int)]
        have = set(nums)
        top = max(have) if have else 0
        expect = max(vul.get(ch, {0}))
        missing = [n for n in range(1, min(top, expect) + 1) if n not in have] if key != "psalms" and ch in vul else []
        dups = sorted({n for n in nums if nums.count(n) > 1})
        tail = list(range(top + 1, expect + 1)) if key != "psalms" and ch in vul else []
        if missing or dups or tail:
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
                vol = pg and vol_of(f"page_{pg:04d}.json")
                if vol:
                    msg = f"{info['fr']} {ch}:{n} is missing (page shown holds the nearest verse)"
                    uid = hashlib.md5(msg.encode()).hexdigest()[:8]
                    if f"{vol}/{pg:04d}/missing_verse/{uid}" in FP_IDS:
                        continue
                    item("missing_verse", vol, pg, msg)
                (kept_missing if n in missing else kept_tail).append(n)
            missing, tail = kept_missing, kept_tail
            for n in dups:
                for k, pg in located:
                    if k == n and vol_of(pg):
                        item("duplicate_verse", vol_of(pg), int(pg[5:9]), f"{info['fr']} {ch}:{n} appears more than once")
            if missing or dups or tail:
                verse_issues.append(dict(chapter=ch, missing=missing, duplicated=dups,
                                         missing_tail=tail, vulgate_count=expect))
        for v in vs:
            if not (v.get("french") or "").strip() or not (v.get("latin") or "").strip():
                empty_verse.append(f"{ch}:{v.get('verse_number')}")
            fr_hits += archaic_hits(v.get("french")); fr_words += words(v.get("french"))
            for name, rx in LATIN_OLD:
                la_hits[name] += len(rx.findall(v.get("latin") or ""))
        if summaries.get(ch):
            fr_hits += archaic_hits(summaries[ch]); fr_words += words(summaries[ch])
        if not published:
            continue
        try:
            c = calmet_notes(key, ch, 1, 999)
        except Exception:
            verse_issues.append(dict(chapter=ch, notes_file_missing=True))
            continue
        missing_fn += len(c.get("missing_footnotes") or [])
        for k in c.get("missing_footnotes") or []:
            m = re.match(r"page_(\d+)-(\w)", k)
            vol = m and vol_of(f"page_{m.group(1)}.json")
            if vol:
                item("missing_footnote", vol, int(m.group(1)),
                     f"Footnote marker ({m.group(2)}) has no footnote text on this page")
        for note in c.get("notes") or []:
            txt = " ".join(str(note.get(k) or "") for k in ("lemma", "text"))
            site_text.append(flat(txt))
            note_hits += archaic_hits(txt); note_words += words(txt)
            for name, rx in LATIN_OLD:
                la_hits[name] += len(rx.findall(note.get("latin_lemma") or ""))
            if note.get("verse") not in have:
                orphan_notes.append(f"{ch}:{note.get('verse')}")
    r["verses_site"] = total_verses
    r["verse_issues"] = verse_issues
    r["verses_missing_count"] = sum(len(i.get("missing", [])) + len(i.get("missing_tail", [])) for i in verse_issues)
    r["verses_duplicated_count"] = sum(len(i.get("duplicated", [])) for i in verse_issues)
    r["verses_empty_text"] = empty_verse
    r["notes_without_verse"] = sorted(set(orphan_notes), key=lambda s: [int(x) if x.isdigit() else 0 for x in s.split(":")])
    r["missing_footnotes"] = missing_fn
    r["french_verse_archaic"] = dict(fr_hits); r["french_verse_words"] = fr_words
    r["notes_archaic"] = dict(note_hits); r["notes_words"] = note_words
    r["latin_old_spelling"] = dict(la_hits)
    # commentary blocks in the source that never reach the site
    blob = "".join(site_text)
    dropped, checked = [], 0
    for vol, n, d in (pages if published else []):
        for b in d.get("commentary") or []:
            t = flat(b.get("french_commentary"))
            if len(t) < 80:
                continue
            checked += 1
            probes = [t[int(len(t) * q) - 12: int(len(t) * q) + 12] for q in (0.25, 0.5, 0.75)]
            if not any(p in blob for p in probes):
                dropped.append(dict(page=f"{vol}/{n}", verse_ref=b.get("verse_ref"),
                                    chars=len(b.get("french_commentary") or ""),
                                    start=(b.get("french_commentary") or "")[:70]))
    for x in dropped:
        vol, n = x["page"].split("/")
        item("dropped_commentary", vol, int(n[5:9]),
             f"Commentary block never reaches the site (verse ref: {x['verse_ref'] or 'none'}): "
             f"“{x['start'][:60].strip()}…” Usually a missing or unreadable verse_ref: set it from the scan")
    r["commentary_blocks_checked"] = checked
    r["commentary_blocks_not_on_site"] = dropped
    r["commentary_chars_not_on_site"] = sum(x["chars"] for x in dropped)
    return r


# Left out of the audit and the review queue
EXCLUDED = set()


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
        if info["number"] > 46:  # page_audit.recheck_book skips the same books
            continue
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
        queue = [q for q in queue if not (q["book_dir"] in read and q["kind"] in ("possible_gap", "seam_artifact"))]
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
        queue = [q for q in queue if q["id"] not in FP_IDS]
        filtered = before_len - len(queue)
        if filtered:
            print(f"filtered out {filtered} permanently resolved false positive(s)")
    qpath = out.with_name("review_queue.json")
    qpath.write_text(json.dumps(queue, ensure_ascii=False, indent=1))
    print(f"wrote {qpath} ({len(queue)} items, {sum(not q['optional'] for q in queue)} required)")


if __name__ == "__main__":
    main()
