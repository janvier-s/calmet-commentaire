"""The web review editor's core: pages, their context, entry operations, the queue and its progress.

No Tk and no HTTP here; review_web.py serves it.
"""
import copy
import hashlib
import json
import os
import re
import time
from pathlib import Path

from continuations import carry_refs
from page_text import LRM, find_source_image, trim
from punctuation import clean_page

EMPTY_PAGE = {"book_title": None, "chapter_title": None, "chapter_summary": None, "chapter_intro": None,
              "verses": [], "commentary": [], "footnotes": []}
INT_FIELDS = {"verse_number", "commentary_id", "verse_ref", "chapter_number", "chapter"}
PAGE_FILE = re.compile(r"page_(\d{4})\.json")


class Conflict(Exception):
    """The page changed on disk since it was read."""

    def __init__(self, disk, version):
        super().__init__("page changed on disk")
        self.disk, self.version = disk, version


def form_values(o, key=None):
    """Values as typed in the editor, as the Tk editors stored them: no display marks, integers
    in the number fields, `null` (or an emptied null) as None, anything else kept as typed."""
    if isinstance(o, dict):
        return {k: form_values(v, k) for k, v in o.items()}
    if isinstance(o, list):
        return [form_values(v, key) for v in o]
    if isinstance(o, str):
        o = o.replace(LRM, "")
        if key in INT_FIELDS:
            s = o.strip()
            if s in ("", "null"):
                return None
            return int(s) if s.isdigit() else o
        return None if o.strip() == "null" else o
    return o


def dumps(d):
    return json.dumps(d, ensure_ascii=False, indent=2)


class Store:
    def __init__(self, data: Path, docs: Path):
        self.data, self.docs = Path(data), Path(docs)
        self._index = {}  # volume -> chapter:verse index, see locate()
        self._chapters = {}  # volume -> [{"chapter": n, "pages": [...]}], see chapters()

    def volumes(self):
        return sorted(p.name for p in self.data.iterdir() if (p / "normalized").is_dir())

    def path(self, vol, page):
        return self.data / vol / "normalized" / f"page_{page:04d}.json"

    def pages(self, vol):
        return sorted(int(m.group(1)) for f in (self.data / vol / "normalized").iterdir()
                      if (m := PAGE_FILE.fullmatch(f.name)))

    def chapters(self, vol):
        """Every chapter with its pages: a page that ends one chapter and starts the next counts in
        both; a page with no verse or note goes with the chapter it opens (a title page), else with
        the chapter before it."""
        if vol in self._chapters:
            return self._chapters[vol]
        seq = []
        for p in self.pages(vol):
            d = self._load(vol, p) or {}
            chapters = []
            for e in (d.get("verses") or []) + (d.get("commentary") or []):
                ch = e.get("chapter")
                if isinstance(ch, int) and ch not in chapters:
                    chapters.append(ch)
            if not chapters and isinstance(d.get("chapter_number"), int):
                chapters.append(d["chapter_number"])
            titled = bool((d.get("chapter_title") or "").strip() or (d.get("chapter_summary") or "").strip())
            seq.append((p, chapters, titled))
        known = [i for i, (_, chapters, _) in enumerate(seq) if chapters]
        for i, (p, chapters, titled) in enumerate(seq):
            if chapters:
                continue
            before = next((seq[j][1] for j in reversed(known) if j < i), None)
            after = next((seq[j][1] for j in known if j > i), None)
            seq[i] = (p, after if titled and after else before or after or [], titled)
        by = {}
        for p, chapters, _ in seq:
            for ch in chapters:
                by.setdefault(ch, []).append(p)
        out = [dict(chapter=ch, pages=pages) for ch, pages in sorted(by.items())]
        self._chapters[vol] = out
        return out

    @staticmethod
    def _version(p):
        st = p.stat()
        return f"{st.st_mtime_ns}-{st.st_size}"

    def read(self, vol, page):
        p = self.path(vol, page)
        return json.loads(p.read_text(encoding="utf-8")), self._version(p)

    def _write(self, p, d):
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(dumps(d), encoding="utf-8")
        os.replace(tmp, p)
        return self._version(p)

    def save(self, vol, page, data, version, force=False):
        p = self.path(vol, page)
        if not p.exists():  # only create() makes a page
            raise FileNotFoundError(p)
        if not force and version is not None and self._version(p) != version:
            disk, v = self.read(vol, page)
            raise Conflict(disk, v)
        d = trim(clean_page(form_values(data)))
        v = self._write(p, d)
        self.changed(vol)
        return d, v

    def create(self, vol, page):
        p = self.path(vol, page)
        if p.exists():
            raise FileExistsError(p)
        d = copy.deepcopy(EMPTY_PAGE)
        v = self._write(p, d)
        self.changed(vol)
        return d, v

    def changed(self, vol):
        """Drop what was built from the volume's pages."""
        self._index.pop(vol, None)
        self._chapters.pop(vol, None)

    def scan(self, vol, page):
        return find_source_image(self.data / vol, page)

    # --- Where a page sits ---
    PREV_REACH = 20

    def _load(self, vol, page):
        try:
            return self.read(vol, page)[0]
        except (OSError, ValueError):
            return None

    def context(self, vol, page):
        """Where the text before this page ends (walking back over pages with neither verse nor
        commentary) and where the next page starts."""
        pages = self.pages(vol)
        i = pages.index(page) if page in pages else next((k for k, p in enumerate(pages) if p > page), len(pages))
        prev = None
        for p in reversed(pages[max(0, i - self.PREV_REACH):i]):
            d = self._load(vol, p)
            if d and (d.get("verses") or d.get("commentary")):
                v = (d.get("verses") or [{}])[-1]
                c = (d.get("commentary") or [{}])[-1]
                words = ((c.get("french_commentary") or "").strip().split("\n") or [""])[-1].split()
                prev = {"page": p, "chapter": v.get("chapter"), "verse": v.get("verse_number"),
                        "commentary_chapter": c.get("chapter"), "verse_ref": c.get("verse_ref"),
                        "tail": "…" + " ".join(words[-7:]) if words else ""}
                break
        nxt = None
        later = [p for p in pages if p > page]
        if later and (d := self._load(vol, later[0])) is not None:
            v = (d.get("verses") or [{}])[0]
            c = (d.get("commentary") or [None])[0]
            fc = (c or {}).get("french_commentary") or ""
            nxt = {"page": later[0], "chapter": v.get("chapter"), "verse": v.get("verse_number"),
                   "verse_ref": (c or {}).get("verse_ref"),
                   "head": fc[:250] + ("…" if len(fc) > 250 else ""),
                   "continuation": bool(c) and not (c.get("verse_ref") or c.get("latin_quote")
                                                    or c.get("french_translation"))}
        return {"prev": prev, "next": nxt}

    # --- Chapter and verse ---
    def _build_index(self, vol):
        verses, notes, chapters = {}, {}, {}
        for p in self.pages(vol):
            d = self._load(vol, p) or {}
            for v in d.get("verses") or []:
                ch, n = v.get("chapter"), v.get("verse_number")
                if isinstance(ch, int):
                    chapters.setdefault(ch, p)
                    if isinstance(n, int):
                        verses.setdefault((ch, n), p)
            for c in d.get("commentary") or []:
                ch, r = c.get("chapter"), c.get("verse_ref")
                if isinstance(ch, int):
                    chapters.setdefault(ch, p)
                    if isinstance(r, int):
                        notes.setdefault((ch, r), p)
        return verses, notes, chapters

    def locate(self, vol, chapter, verse=None):
        """The page with that verse's text, else the first note on it; without a verse, the first
        page of the chapter."""
        if vol not in self._index:
            self._index[vol] = self._build_index(vol)
        verses, notes, chapters = self._index[vol]
        if verse is None:
            return chapters.get(chapter)
        return verses.get((chapter, verse)) or notes.get((chapter, verse))


# --- Entries (pure: a new page dict back, nothing written) ---
def _renumber(page):
    for k, c in enumerate(page.get("commentary") or [], 1):
        c["commentary_id"] = k


def _neighbour_chapter(entries, pos):
    """The chapter of the entry before position `pos` (or after it): a new entry's default."""
    for e in list(reversed(entries[:pos])) + entries[pos:]:
        if isinstance(e.get("chapter"), int):
            return e["chapter"]
    return None


def add_verse(page, n):
    """After the last lower-numbered verse before the numbering restarts (a page can end one
    chapter and start the next)."""
    page = copy.deepcopy(page)
    verses = page.setdefault("verses", [])
    pos, prev = 0, None
    for i, v in enumerate(verses):
        k = v.get("verse_number")
        if isinstance(k, int):
            if prev is not None and k < prev:
                break
            prev = k
            if k < n:
                pos = i + 1
    verses.insert(pos, {"chapter": _neighbour_chapter(verses, pos), "verse_number": n,
                        "latin": "", "french": "", "annotations": None})
    return page


def add_commentary(page, after, prev_page):
    """A block at the top (`after` None), continuing the previous page's last note, or below
    block `after`, on the same verse."""
    page = copy.deepcopy(page)
    comms = page.setdefault("commentary", [])
    if after is None:
        src = ((prev_page or {}).get("commentary") or [{}])[-1]
        pos = 0
    else:
        src, pos = comms[after], after + 1
    comms.insert(pos, {"commentary_id": None, "verse_ref": src.get("verse_ref"), "chapter": src.get("chapter"),
                       "latin_quote": None, "french_translation": None, "french_commentary": ""})
    _renumber(page)
    return page


def add_footnote(page, marker):
    page = copy.deepcopy(page)
    page.setdefault("footnotes", []).append({"marker": f"({marker.strip('() ')})", "text": ""})
    return page


def delete_entry(page, section, i):
    page = copy.deepcopy(page)
    del page[section][i]
    if section == "commentary":
        _renumber(page)
    return page


def move_entry(page, section, i, j, renumber=True):
    page = copy.deepcopy(page)
    items = page[section]
    items.insert(j, items.pop(i))
    if section == "commentary" and renumber:
        _renumber(page)
    return page


def apply_op(page, op, prev_page):
    kind = op["op"]
    if kind == "add_verse":
        return add_verse(page, int(op["n"]))
    if kind == "add_commentary":
        return add_commentary(page, op.get("after"), prev_page)
    if kind == "add_footnote":
        return add_footnote(page, op["marker"])
    if kind == "delete":
        return delete_entry(page, op["section"], int(op["index"]))
    if kind == "move":
        return move_entry(page, op["section"], int(op["from"]), int(op["to"]), op.get("renumber", True))
    raise ValueError(f"unknown operation: {kind}")


# --- The queue (docs/review_queue.json, written by audit_integrity.py) ---
KIND_LABELS = {
    "todo": "TO-DO",
    "duplicate_page": "PAGE COPIED FROM ANOTHER",
    "malformed_page": "MALFORMED PAGE",
    "missing_page": "MISSING PAGE",
    "missing_verse": "MISSING VERSE",
    "psalm_missing_verse": "PSALM VERSE MISSING (from the Vulgate text)",
    "psalm_missing_title": "PSALM TITLE MISSING",
    "missing_french": "VERSE WITHOUT FRENCH",
    "vulgate_filled": "VERSE FILLED FROM THE VULGATE: TYPE THE FRENCH",
    "psalm_number": "PSALM VERSE NUMBER OUT OF STEP",
    "psalm_wrong_psalm": "VERSE UNDER THE WRONG PSALM",
    "psalm_unmatched": "VERSE NOT FOUND IN THE VULGATE",
    "duplicate_verse": "DUPLICATE VERSE",
    "latin_long_s": "LATIN: f READ FOR s? (check the word against the scan)",
    "chapter_field": "CHAPTER FIELD OUT OF STEP",
    "empty_summary": "CHAPTER SUMMARY EMPTY",
    "chapter_vulgate": "CHAPTER SET FROM THE VULGATE: CHECK THE VERSE NUMBER",
    "chapter_heading": "CHAPTER HEADING TO CHECK",
    "dropped_commentary": "COMMENTARY NOT ON SITE",
    "seam_missing": "TEXT MISSING AT PAGE BREAK",
    "seam_repeat": "TEXT REPEATED AT PAGE BREAK",
    "seam_unclear": "PAGE BREAK TO CHECK",
    "ref_order": "VERSE REFERENCE OUT OF ORDER",
    "no_verse_ref": "NOTE WITHOUT VERSE_REF",
    "no_lemma": "NOTE WITHOUT LATIN_QUOTE",
    "missing_start": "COMMENT OPENS MID-SENTENCE, NO COMMENT BEFORE IT: START MISSING?",
    "first_no_lemma": "FIRST NOTE WITHOUT LATIN AND FRENCH: A NEW NOTE?",
    "spaced_letters": "L E T T E R - S P A C E D WORD",
    "leading_punctuation": "COMMENT STARTS WITH PUNCTUATION",
    "leading_call": "FIELD STARTS WITH A FOOTNOTE CALL",
    "italic_seam": "ITALICS BROKEN AT PAGE TURN",
    "period_seam": "FULL STOP AT PAGE END, LOWER CASE OVERLEAF",
    "etc_for_et": "“ETC.” WHERE “&” (ET) WAS MEANT?",
    "hyphen_cut": "LEMMA / TRANSLATION CUT AT PAGE TURN (hyphen or no full stop)",
    "long_translation": "TRANSLATION MUCH LONGER THAN THE LEMMA",
    "no_translation": "LEMMA WITHOUT FRENCH_TRANSLATION",
    "verse_no_punct": "VERSE NOT ENDING WITH PUNCTUATION",
    "footnote_no_period": "FOOTNOTE NOT ENDING WITH A FULL STOP",
    "stray_underscore": "STRAY _ (ITALICS WITHOUT ITS PAIR)",
    "hebrew_in_translation": "COMMENTARY OR VARIANT IN THE TRANSLATION",
    "hebrew_recheck": "FOOTNOTE HEBREW UNCERTAIN: CHECK AGAINST THE SCAN",
    "lemma_verse": "LATIN_QUOTE FILLED IN BY HAND: RIGHT VERSE NUMBER?",
    "verse_mismatch": "LATIN_QUOTE FITS ANOTHER VERSE: WRONG VERSE NUMBER?",
    "chapter_ref": "CHAPTER REFERENCE NOT WRITTEN OUT (WHICH BOOK? WHICH NUMBERS?)",
    "guessed_ref": "BIBLE REFERENCE GUESSED (*) OR AS PRINTED: CHECK ON THE SCAN",
    "footnote_asterisk": "FOOTNOTE WITH GUESSED WORDS (*): CHECK AGAINST THE SCAN",
    "lowercase_lemma": "LOWER CASE IN THE LATIN LEMMA",
    "lemma_no_punct": "LATIN LEMMA NOT ENDING WITH PUNCTUATION",
    "translation_no_punct": "TRANSLATION NOT ENDING WITH PUNCTUATION",
    "lowercase_translation": "MISSING CAPITAL IN FRENCH TRANSLATION",
    "lemma_unknown_word": "LEMMA WORD NOT IN THE VULGATE (name? misreading?)",
    "extra_footnotes": "MORE FOOTNOTES THAN CALLS",
    "empty_commentary": "NOTE WITHOUT COMMENTARY",
    "caps_in_commentary": "CAPITALS IN COMMENTARY",
    "broken_marker": "BROKEN FOOTNOTE CALL",
    "possible_gap": "POSSIBLE GAP",
    "missing_footnote": "MISSING FOOTNOTE",
    "empty_page": "EMPTY PAGE",
    "seam_artifact": "PAGE-TURN GLITCH",
    # proposals from the scripts' reports (review_proposals.py)
    "footnote_writeout": "FOOTNOTE WRITE-OUT TO CHECK",
    "ref_candidate": "VERSE REFERENCE TO CHECK",
}

VERSE_KINDS = {
    "missing_verse", "psalm_missing_verse", "duplicate_verse", "missing_french",
    "vulgate_filled", "psalm_wrong_psalm", "psalm_unmatched", "psalm_number",
    "psalm_missing_title", "chapter_field", "chapter_vulgate", "chapter_heading",
    "empty_summary", "latin_long_s", "verse_no_punct",
}

FOOTNOTE_KINDS = {
    "missing_footnote", "broken_marker", "extra_footnotes", "hebrew_recheck",
    "footnote_asterisk", "footnote_writeout", "footnote_no_period",
}

# The type menu's groups, in the order shown (the book's structure outwards, to-dos last); within a group, the order of the list. Every kind of
# KIND_LABELS belongs to exactly one (tests/test_queue.py); a kind left out would fall under "Other".
KIND_THEMES = [
    ("Pages", ["duplicate_page", "malformed_page", "missing_page", "empty_page"]),
    ("Chapters", ["chapter_field", "empty_summary", "chapter_vulgate", "chapter_heading"]),
    ("Verses", ["missing_verse", "duplicate_verse", "missing_french", "vulgate_filled", "latin_long_s",
                "verse_no_punct"]),
    ("Psalms", ["psalm_missing_verse", "psalm_missing_title", "psalm_number", "psalm_wrong_psalm",
                "psalm_unmatched"]),
    ("Page turns", ["seam_missing", "seam_repeat", "seam_unclear", "seam_artifact", "hyphen_cut",
                    "italic_seam", "period_seam", "possible_gap", "missing_start"]),
    ("Notes: structure", ["dropped_commentary", "empty_commentary", "no_lemma", "first_no_lemma"]),
    ("Notes: lemma and translation", ["no_translation", "long_translation", "lowercase_lemma", "lemma_no_punct",
                                      "lemma_unknown_word", "lowercase_translation", "translation_no_punct",
                                      "hebrew_in_translation"]),
    ("Verse numbers and references", ["no_verse_ref", "ref_order", "lemma_verse", "verse_mismatch", "chapter_ref",
                                      "guessed_ref", "ref_candidate"]),
    ("Footnotes", ["missing_footnote", "extra_footnotes", "broken_marker", "footnote_no_period",
                   "footnote_asterisk", "footnote_writeout", "hebrew_recheck"]),
    ("Typography", ["spaced_letters", "leading_punctuation", "leading_call", "etc_for_et", "stray_underscore",
                    "caps_in_commentary"]),
    ("To-dos", ["todo"]),
]


def kind_category(k):
    if k in VERSE_KINDS:
        return "verses"
    if k in FOOTNOTE_KINDS:
        return "footnotes"
    return "commentary"


STATUSES = ("open", "on_hold", "false_positive", "skipped", "resolved", "all")
CATEGORIES = ("verses", "commentary", "footnotes")


def _atomic_write(path, text):
    tmp = Path(path).with_name(Path(path).name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


REVIEW_SECTIONS = ("commentary", "verses", "footnotes")  # read through separately
REVIEW_FILE = "review.json"  # data/<book>/review.json: one book's review, so that volunteers' commits don't collide


class Progress:
    """The review of every book, one file per book (data/<book>/review.json): each item's status
    (resolved, false_positive, skipped, on_hold), the false positives with what they said (they outlive the
    queue), the page to-dos, and the pages read through by section ("reviewed": independent of the issues)."""

    def __init__(self, data_dir: Path):
        self.dir = Path(data_dir)
        self.data, self.fps, self.todos, self.reviewed = {}, {}, {}, {}
        for f in sorted(self.dir.glob(f"*/{REVIEW_FILE}")):
            d = self._read(f.parent.name)
            self.reviewed[f.parent.name] = {k: set(v) for k, v in d["reviewed"].items()}
            self.data.update(d["status"])
            self.fps.update(d["false_positives"])
            self.todos[f.parent.name] = d["todos"]
        for k in self.fps:
            self.data[k] = "false_positive"

    def _read(self, vol):
        try:
            d = json.loads((self.dir / vol / REVIEW_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            d = {}
        return {"status": d.get("status") or {}, "false_positives": d.get("false_positives") or {},
                "todos": d.get("todos") or [], "reviewed": {k: sorted(set((d.get("reviewed") or {}).get(k) or [])) for k in REVIEW_SECTIONS}}

    def _write(self, vol, d):
        _atomic_write(self.dir / vol / REVIEW_FILE, json.dumps(d, ensure_ascii=False, indent=1, sort_keys=True) + "\n")

    def book_of(self, item_id):
        """The book an id belongs to: its first part that is a book ("proposal:seam/<book>/…" too)."""
        for part in item_id.removeprefix("proposal:").split("/"):
            if (self.dir / part).is_dir():
                return part
        raise ValueError(f"no book in {item_id}")

    def status(self, item_id):
        return self.data.get(item_id)

    def set(self, item_id, status, info=None):
        self.update({item_id: status}, {item_id: info} if info else None)

    def update(self, changes, infos=None):
        """Several statuses at once (None clears one), each book's file written once, atomically."""
        by_book = {}
        for item_id, status in changes.items():
            by_book.setdefault(self.book_of(item_id), {})[item_id] = status
        for vol, ch in by_book.items():
            d = self._read(vol)
            for item_id, status in ch.items():
                if status:
                    self.data[item_id] = d["status"][item_id] = status
                else:
                    self.data.pop(item_id, None)
                    d["status"].pop(item_id, None)
                if status == "false_positive":
                    self.fps[item_id] = d["false_positives"][item_id] = (infos or {}).get(item_id) or True
                else:
                    self.fps.pop(item_id, None)
                    d["false_positives"].pop(item_id, None)
            self._write(vol, d)

    def set_reviewed(self, vol, section, pages, on=True):
        """Pages of one section (commentary, verses, footnotes) read through, or taken back; the book's file
        written once; returns the section's reviewed pages."""
        d = self._read(vol)
        have = set(d["reviewed"][section])
        have = have | set(pages) if on else have - set(pages)
        d["reviewed"][section] = sorted(have)
        self._write(vol, d)
        self.reviewed[vol] = {k: set(v) for k, v in d["reviewed"].items()}
        return d["reviewed"]

    def add_todo(self, vol, page, msg, where=None, holds=None):
        """A page to-do (something to do that no check finds: a rescan, an abbreviation…); `holds`: the
        issue it puts on hold until it is done."""
        d = self._read(vol)
        stamp = f"{msg}\n{where}\n{len(d['todos'])}\n{time.time()}"
        td = {"id": f"{vol}/{page:04d}/todo/{hashlib.md5(stamp.encode()).hexdigest()[:8]}", "page": page,
              "msg": msg, "where": where or None, **({"holds": holds} if holds else {})}
        d["todos"].append(td)
        self._write(vol, d)
        self.todos.setdefault(vol, []).append(td)
        return td

    def delete_todo(self, todo_id):
        vol = self.book_of(todo_id)
        d = self._read(vol)
        d["todos"] = [td for td in d["todos"] if td["id"] != todo_id]
        d["status"].pop(todo_id, None)
        self._write(vol, d)
        self.todos[vol] = [td for td in self.todos.get(vol, []) if td["id"] != todo_id]
        self.data.pop(todo_id, None)


def absorb_legacy(data_dir, docs_dir):
    """Fold the review files of before the split (data/.review_queue_progress.json,
    docs/false_positives.json, docs/manual_issues.json, which an editor started earlier may still
    write) into each book's review.json, then remove them. Their statuses win: they are the newer."""
    data_dir, docs_dir = Path(data_dir), Path(docs_dir)
    files = [data_dir / ".review_queue_progress.json", docs_dir / "false_positives.json", docs_dir / "manual_issues.json"]
    if not any(f.exists() for f in files):
        return 0
    read = lambda f, empty: json.loads(f.read_text(encoding="utf-8")) if f.exists() else empty
    status, fps, manual = read(files[0], {}), read(files[1], {}), read(files[2], [])
    p = Progress(data_dir)
    books = {}
    def book(k):
        vol = p.book_of(k)
        return books.setdefault(vol, p._read(vol))
    for m in manual:  # issues reported by hand: the page's to-dos
        h = hashlib.md5(m["msg"].encode()).hexdigest()[:8]
        tid, old = f"{m['book_dir']}/{m['page']:04d}/todo/{h}", f"{m['book_dir']}/{m['page']:04d}/reported/{h}"
        d = book(tid)
        if all(td["id"] != tid for td in d["todos"]):
            d["todos"].append({"id": tid, "page": m["page"], "msg": m["msg"], "where": None})
        if old in status:
            status[tid] = status.pop(old)
    for k, v in status.items():
        book(k)["status"][k] = v
    for k, v in fps.items():
        book(k)["false_positives"][k] = v
    for vol, d in books.items():
        p._write(vol, d)
    for f in files:
        f.unlink(missing_ok=True)
    return len(status) + len(fps) + len(manual)


def todo_item(vol, td):
    """A page to-do as a queue item."""
    return dict({"id": td["id"], "book_dir": vol, "page": td["page"], "kind": "todo", "msg": td["msg"],
                 "optional": False}, **({"where": td["where"]} if td.get("where") else {}),
                **({"holds": td["holds"]} if td.get("holds") else {}))


def load_queue(queue_path, progress, include_optional=False):
    """The queue, plus the false positives it no longer lists (so they stay visible)."""
    items = json.loads(Path(queue_path).read_text(encoding="utf-8"))
    known = {it["id"] for it in items}
    for fp_id, val in progress.fps.items():
        if fp_id in known:
            continue
        parts = fp_id.split("/")
        val = val if isinstance(val, dict) else {}
        items.append({"id": fp_id, "book_dir": val.get("book_dir", parts[0]),
                      "page": val.get("page", int(parts[1])), "kind": val.get("kind", parts[2]),
                      "msg": val.get("msg", "Marked false positive"), "optional": False})
    for vol, todos in progress.todos.items():  # the page to-dos added in the editor
        items += [todo_item(vol, td) for td in todos if td["id"] not in known]
    return items if include_optional else [it for it in items if not it.get("optional")]


def in_status(item, progress, status):
    s = progress.status(item["id"])
    if status == "open":
        return s not in ("resolved", "false_positive", "skipped", "on_hold")
    return status == "all" or s == status


def _match(it, progress, status, cat, kind, book):
    return ((status is None or in_status(it, progress, status))
            and (cat is None or kind_category(it["kind"]) == cat)
            and (kind is None or it["kind"] == kind)
            and (book is None or it["book_dir"] == book))


def select(items, progress, status, cat=None, kind=None, book=None):
    return [it for it in items if _match(it, progress, status, cat, kind, book)]


def counts(items, progress, status, cat, kind, book):
    """Each filter's choices with how many items each leaves, the other filters applied."""
    def tally(key, **f):
        out = {}
        for it in select(items, progress, **f):
            out[key(it)] = out.get(key(it), 0) + 1
        return out
    by_status = {s: len(select(items, progress, s, cat, kind, book)) for s in STATUSES}
    by_cat = {"all": len(select(items, progress, status, None, kind, book))}
    by_cat.update({c: len(select(items, progress, status, c, kind, book)) for c in CATEGORIES})
    return {"status": by_status, "cat": by_cat,
            "kind": tally(lambda it: it["kind"], status=status, cat=cat, kind=None, book=book),
            "book": tally(lambda it: it["book_dir"], status=status, cat=cat, kind=kind, book=None)}


def page_issues(items, progress, vol, page):
    return [dict(it, status=progress.status(it["id"])) for it in items
            if it["book_dir"] == vol and it["page"] == page]


def neighbour_issue_pages(items, progress, vol, page):
    open_pages = sorted({it["page"] for it in items
                         if it["book_dir"] == vol and in_status(it, progress, "open")})
    return {"prev": max((p for p in open_pages if p < page), default=None),
            "next": min((p for p in open_pages if p > page), default=None),
            "open_in_book": sum(1 for it in items if it["book_dir"] == vol and in_status(it, progress, "open"))}


# --- Re-check on save ---
# Kinds audit_integrity.audit_book produces; the others come from other scripts and are left alone.
# duplicate_verse is also psalms_check.py's, so a re-check never closes it.
AUDIT_KINDS = frozenset(KIND_LABELS) - {
    "todo", "psalm_missing_verse", "psalm_missing_title", "psalm_number", "psalm_wrong_psalm",
    "psalm_unmatched", "chapter_vulgate", "chapter_heading", "hebrew_recheck", "latin_long_s",
    "seam_missing", "seam_repeat", "seam_unclear", "duplicate_verse", "footnote_writeout", "ref_candidate"}


def book_volumes(vol):
    from paths import BOOKS, BY_VOLUME
    return BOOKS[BY_VOLUME[vol]]["studium"] if vol in BY_VOLUME else [vol]


def merge_recheck(items, progress, vols, new_items, include_optional=True):
    """Fold a fresh audit of the volumes `vols` into `items` (in place). Open items it no longer
    finds are resolved and kept with fixed=True; ones fixed this way that come back are reopened;
    items marked by hand keep their status; new ones are appended."""
    produced = {q["id"]: q for q in new_items}
    # a page the audit could not read (malformed, gone) says nothing about its issues
    unreadable = {(q["book_dir"], q["page"]) for q in new_items if q["kind"] in ("malformed_page", "missing_page")}
    fixed, added, changes = [], [], {}
    known = set()
    for it in items:
        known.add(it["id"])
        if it["book_dir"] not in vols or it["kind"] not in AUDIT_KINDS:
            continue
        q = produced.get(it["id"])
        if q:
            it.update(msg=q["msg"], **({"where": q["where"]} if "where" in q else {}))
            if it.pop("fixed", False) and progress.status(it["id"]) == "resolved":
                changes[it["id"]] = None
        elif (it["book_dir"], it["page"]) not in unreadable and in_status(it, progress, "open"):
            changes[it["id"]] = "resolved"
            it["fixed"] = True
            fixed.append(it["id"])
    for qid, q in produced.items():
        if qid not in known and (include_optional or not q.get("optional")):
            items.append(dict(q))
            added.append(qid)
    if changes:
        progress.update(changes)
    return {"fixed": fixed, "added": added}


# --- the notes file: words picked in the editor, added under a heading ---
NOTES_SECTIONS = ("SPELLING", "VERSE FIXES")


def add_note(path, section, text):
    """Append `text` (one line, italics marks dropped) to the end of `## <section>` in the notes file, as a
    markdown line break; a heading not there yet is added at the end. Returns False when the line is already
    in the section."""
    path = Path(path)
    text = " ".join(text.replace("_", "").split())
    if not text:
        raise ValueError("nothing selected")
    lines = path.read_text(encoding="utf-8").split("\n") if path.exists() else []
    head = f"## {section}"
    if head in lines:
        start = lines.index(head) + 1
        end = next((i for i in range(start, len(lines)) if lines[i].startswith("## ")), len(lines))
        if any(l.strip().strip("*") == text for l in lines[start:end]):
            return False
        at = end
        while at > start and not lines[at - 1].strip():
            at -= 1
        lines.insert(at, text + "  ")
        if at == start:  # an empty section: a blank line after the heading
            lines.insert(start, "")
    else:
        while lines and not lines[-1].strip():
            lines.pop()
        lines += ["", head, "", text + "  ", ""]
    _atomic_write(path, "\n".join(lines))
    return True
