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
        """Hook for caches built from a volume's pages."""

    def scan(self, vol, page):
        return find_source_image(self.data / vol, page)
