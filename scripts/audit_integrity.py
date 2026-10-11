"""Integrity audit of the Calmet commentary: source pages (STUDIUM normalized) and
what the website actually serves (dom-calmet-web raw + calmet JSON).

Usage: python3 audit_integrity.py [out.json]
Read-only: writes nothing but the JSON result.
"""
import hashlib, json, re, sys, statistics
from collections import Counter, defaultdict
from pathlib import Path

from export import chapter_of
from paths import BOOKS, DATA as STUDIUM, DOCS, VUL, WEB as SITE

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
        sizes.append(c + v)
        if not (d.get("commentary") or d.get("verses")):
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

    def item(kind, vol, page, msg, optional=False):
        # Stable across runs, so review progress survives a re-audit
        uid = hashlib.md5(msg.encode()).hexdigest()[:8]
        queue.append(dict(id=f"{vol}/{page:04d}/{kind}/{uid}", book_dir=vol, page=page,
                          kind=kind, msg=msg, optional=optional))

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

    # verse_ref must run in order through a chapter. A drop is fine where a chapter
    # begins (to verse 1-3, or the first drop on or just after a page opening a chapter).
    refs = []
    for i, (vol, n, d) in enumerate(pages):
        if chapter_of(d):
            refs.append(("chapter", i))
        for c in d.get("commentary") or []:
            m = re.match(r"(\d+)", str(c.get("verse_ref") or ""))
            if m:
                refs.append((vol, n, i, int(m.group(1))))
    prev, allow_until, out_of_order = None, -1, []
    nums = [x for x in refs if x[0] != "chapter"]
    j = 0
    for x in refs:
        if x[0] == "chapter":
            allow_until = x[1] + 2
            continue
        vol, n, i, ref = x
        if prev is not None and ref < prev:
            if ref <= 3 or i <= allow_until:
                allow_until = -1
            else:
                ctx = ", ".join(str(y[3]) for y in nums[max(0, j - 3):j + 2])
                out_of_order.append(f"{vol}/{n}")
                item("ref_order", vol, int(n[5:9]),
                     f"verse_ref goes back from {prev} to {ref} (… {ctx} …): misread number, or Calmet returning to a verse?")
        prev, j = ref, j + 1
    r["ref_out_of_order"] = out_of_order

    # Notes with no commentary. Fine when the comment opens the next page, or when
    # Calmet gives only the translation; suspicious when nothing follows the lemma.
    CAPS = re.compile(r"\b[A-ZÀ-ÝŒÆ]{2,}(?:[\s,;:'’.-]+[A-ZÀ-ÝŒÆ]{2,})+\b")
    ODD_MARK = re.compile(r"\^[^{]|\^\{(?!\([a-z]\)\})[^}]*\}")
    empty_notes = caps_runs = odd_marks = 0
    for i, (vol, n, d) in enumerate(pages):
        cs = d.get("commentary") or []
        nxt_page = pages[i + 1][2] if i + 1 < len(pages) and pages[i + 1][0] == vol else None
        notes_here = {re.sub(r"\W", "", str(fn.get("marker") or "")) for fn in d.get("footnotes") or []}
        for j, c in enumerate(cs):
            lemma = (c.get("latin_quote") or "").strip()
            tr = (c.get("french_translation") or "").strip()
            fc = c.get("french_commentary") or ""
            if not fc.strip():
                if j == len(cs) - 1:
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
                    item("empty_commentary", vol, int(n[5:9]), f"Note “{lemma[:40]}” (℣ {c.get('verse_ref')}) {problem}")
            for m in CAPS.finditer(fc):
                if re.fullmatch(r"[IVXLC.\s,et]+", m.group()):
                    continue
                caps_runs += 1
                where = "starts the comment" if m.start() < 3 else "inside the comment"
                item("caps_in_commentary", vol, int(n[5:9]),
                     f"Capitals {where}: “…{fc[max(0, m.start() - 25):m.end() + 15]}…”: a lemma that should start its own note, or a word to put in lower case?")
            for k in ("latin_quote", "french_translation", "french_commentary"):
                t = c.get(k) or ""
                bad = [m.group() for m in ODD_MARK.finditer(t)]
                bad += [m.group() for m in re.finditer(r"(?<![\^{\w])\(\s?([a-z])\s?\)(?!\})", t) if m.group(1) not in notes_here]
                for b in bad:
                    odd_marks += 1
                    pos = t.find(b)
                    item("broken_marker", vol, int(n[5:9]),
                         f"Footnote call “{b}” in {k}: “…{t[max(0, pos - 30):pos + len(b) + 10]}…”")
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
    r["empty_commentary"], r["caps_in_commentary"], r["broken_markers"] = empty_notes, caps_runs, odd_marks

    # ---------- what the site serves ----------
    if not slug:
        r["published"] = False
        return r
    r["published"] = published
    raw_dir, cal_dir = SITE / "raw" / slug, SITE / "calmet" / slug
    vul = {c["chapter"]: {v["verse"] for v in c["verses"]}
           for c in json.loads((VUL / f"{info['vul']}.json").read_text())["chapters"]}
    chap_files = sorted(raw_dir.glob("chapter_*.json"))
    r["chapters_site"], r["chapters_vulgate"] = len(chap_files), len(vul)
    r["chapters_missing"] = sorted(set(vul) - {int(f.stem[8:]) for f in chap_files})
    verse_issues, empty_verse = [], []
    fr_hits, fr_words, la_hits = Counter(), 0, Counter()
    note_hits, note_words = Counter(), 0
    site_text = []
    orphan_notes, missing_fn = [], 0
    total_verses = 0
    for f in chap_files:
        ch = int(f.stem[8:])
        d = json.loads(f.read_text())
        vs = d["verses"]
        total_verses += len(vs)
        nums = [v.get("verse_number") for v in vs if isinstance(v.get("verse_number"), int)]
        have = set(nums)
        top = max(have) if have else 0
        expect = max(vul.get(ch, {0}))
        missing = [n for n in range(1, top + 1) if n not in have]
        dups = sorted({n for n in nums if nums.count(n) > 1})
        tail = list(range(top + 1, expect + 1)) if key != "psalms" else []
        if missing or dups or tail:
            verse_issues.append(dict(chapter=ch, missing=missing, duplicated=dups,
                                     missing_tail=tail, vulgate_count=expect))
            located = [(v["verse_number"], v.get("source_pages", [None])[0]) for v in vs
                       if isinstance(v.get("verse_number"), int) and v.get("source_pages")]

            def page_of(n):
                before = [pg for k, pg in located if k < n]
                after = [pg for k, pg in located if k > n]
                pg = before[-1] if before else (after[0] if after else None)
                return int(pg[5:9]) if pg else None

            for n in missing + tail:
                pg = page_of(n)
                vol = pg and vol_of(f"page_{pg:04d}.json")
                if vol:
                    item("missing_verse", vol, pg, f"{info['fr']} {ch}:{n} is missing (page shown holds the nearest verse)")
            for n in dups:
                for k, pg in located:
                    if k == n and vol_of(pg):
                        item("duplicate_verse", vol_of(pg), int(pg[5:9]), f"{info['fr']} {ch}:{n} appears more than once")
        for v in vs:
            if not (v.get("french") or "").strip() or not (v.get("latin") or "").strip():
                empty_verse.append(f"{ch}:{v.get('verse_number')}")
            fr_hits += archaic_hits(v.get("french")); fr_words += words(v.get("french"))
            for name, rx in LATIN_OLD:
                la_hits[name] += len(rx.findall(v.get("latin") or ""))
        if d.get("chapter_summary"):
            fr_hits += archaic_hits(d["chapter_summary"]); fr_words += words(d["chapter_summary"])
        if not published:
            continue
        cf = cal_dir / f"calmet_chapter_{ch:02d}.json"
        if not cf.exists():
            verse_issues.append(dict(chapter=ch, notes_file_missing=True))
            continue
        c = json.loads(cf.read_text())
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


# Left out of the audit and the review queue for now (Psalms: verse structure to redo first)
EXCLUDED = {"psalms"}
# Problems reported by hand: [{book_dir, page, msg}], kept in the queue on every rebuild
MANUAL = DOCS / "manual_issues.json"


def main():
    slugs = site_slugs()
    results = []
    for key, info in BOOKS.items():
        if info["number"] > 21:
            continue
        if key in EXCLUDED:
            continue
        r = audit_book(key, info, slugs.get(info["fr"]))
        results.append(r)
        print(f"{info['number']:>2} {info['fr']:<14} pages={r['pages']:<4} "
              f"vmiss={r.get('verses_missing_count','-')} vdup={r.get('verses_duplicated_count','-')} "
              f"gaps={len(r['page_number_gaps'])} empty={len(r['empty_pages'])} "
              f"seams={len(r['suspicious_seams'])} dropped={len(r.get('commentary_blocks_not_on_site', []))}"
              f"/{r.get('commentary_blocks_checked','-')}", flush=True)
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("integrity_audit.json")
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1))
    print("wrote", out)
    # Worklist for review_editor.py, most serious kinds first, then in page order
    order = ["reported", "duplicate_page", "malformed_page", "missing_page", "missing_verse", "duplicate_verse", "dropped_commentary", "seam_missing", "seam_repeat", "seam_unclear", "ref_order", "empty_commentary", "caps_in_commentary", "broken_marker", "possible_gap",
             "missing_footnote", "empty_page", "seam_artifact"]
    queue = [q for r in results for q in r.get("queue", [])]
    if MANUAL.exists():
        for m in json.loads(MANUAL.read_text()):
            queue.append(dict(id=f"{m['book_dir']}/{m['page']:04d}/reported/{hashlib.md5(m['msg'].encode()).hexdigest()[:8]}",
                              book_dir=m["book_dir"], page=m["page"], kind="reported", msg=m["msg"], optional=False))
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
    qpath = out.with_name("review_queue.json")
    qpath.write_text(json.dumps(queue, ensure_ascii=False, indent=1))
    print(f"wrote {qpath} ({len(queue)} items, {sum(not q['optional'] for q in queue)} required)")


if __name__ == "__main__":
    main()
