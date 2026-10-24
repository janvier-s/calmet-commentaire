"""The web review editor's core: pages, their context, entry operations, the queue and its progress.

No Tk and no HTTP here; review_web.py serves it.
"""
import copy
import json
import os
import re
from pathlib import Path

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

    def volumes(self):
        return sorted(p.name for p in self.data.iterdir() if (p / "normalized").is_dir())

    def path(self, vol, page):
        return self.data / vol / "normalized" / f"page_{page:04d}.json"

    def pages(self, vol):
        return sorted(int(m.group(1)) for f in (self.data / vol / "normalized").iterdir()
                      if (m := PAGE_FILE.fullmatch(f.name)))

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
        if not force and version is not None and p.exists() and self._version(p) != version:
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
