"""Word search over the pages: accents, case, long s and runs of spaces ignored; each hit is given
by its field and its place in the field's own text. "tag:fathers" (or "tag:none", for the
footnotes left without a tag) gives the footnotes with that tag, "tag:fathers Basile" those of
them with the words."""
import re
import unicodedata

LIGATURES = {"ſ": "s", "æ": "ae", "œ": "oe", "ß": "ss"}
CONTEXT = 50


def fold(text):
    """(folded text, for each folded character the index of the character it came from)."""
    out, at = [], []
    space = False
    for i, ch in enumerate(text):
        if ch.isspace():
            if not space:
                out.append(" ")
                at.append(i)
            space = True
            continue
        space = False
        low = ch.lower()
        low = LIGATURES.get(low, low)
        for c in unicodedata.normalize("NFD", low):
            if not unicodedata.combining(c):
                out.append(c)
                at.append(i)
    return "".join(out), at


def entries(page):
    """(path, text) of every text field of a page, in reading order."""
    for k, v in page.items():
        if isinstance(v, str) and v.strip():
            yield [k], v
    for section in ("verses", "commentary", "footnotes"):
        for i, block in enumerate(page.get(section) or []):
            if isinstance(block, dict):
                for k, v in block.items():
                    if isinstance(v, str) and v.strip():
                        yield [section, i, k], v


class Searcher:
    """Keeps each page's folded fields until the file changes."""

    def __init__(self, store):
        self.store = store
        self._pages = {}  # (vol, page) -> (version, [(path, text, folded, at)])

    def _fields(self, vol, page):
        p = self.store.path(vol, page)
        try:
            version = self.store._version(p)
        except OSError:
            return [], {}
        hit = self._pages.get((vol, page))
        if hit and hit[0] == version:
            return hit[1]
        data = self.store._load(vol, page)
        fields = [(path, text, *fold(text)) for path, text in entries(data)] if isinstance(data, dict) else []
        tags = {i: set(fn.get("tags") or []) for i, fn in enumerate(data.get("footnotes") or [])
                if isinstance(fn, dict) and "tags" in fn} if isinstance(data, dict) else {}
        self._pages[(vol, page)] = (version, (fields, tags))
        return fields, tags

    def warm(self, vols):
        """Read every page once (in the background at start: the first search over every book
        would otherwise take seconds)."""
        for vol in vols:
            for page in self.store.pages(vol):
                self._fields(vol, page)

    def search(self, q, vols, limit=500, min_len=2):
        m = re.match(r"\s*tag:(\S+)\s*", q)
        tag = m and m.group(1).lower()
        needle = fold(q[m.end():] if m else q.strip())[0].strip()
        if len(needle) < min_len and not tag:
            return {"hits": [], "total": 0}
        hits, total = [], 0
        for vol in vols:
            for page in self.store.pages(vol):
                fields, tags = self._fields(vol, page)
                for path, text, folded, at in fields:
                    if tag:
                        if path[0] != "footnotes" or path[2] != "text" or path[1] not in tags:
                            continue
                        if tag not in tags[path[1]] and not (tag == "none" and not tags[path[1]]):
                            continue
                        if not needle:  # the tag alone: the note's opening words
                            total += 1
                            if len(hits) < limit:
                                hits.append({"vol": vol, "page": page, "path": path, "start": 0, "end": min(len(text), CONTEXT),
                                             "before": "", "match": text[:CONTEXT], "after": text[CONTEXT:2 * CONTEXT]})
                            continue
                    k = folded.find(needle)
                    while k >= 0:
                        total += 1
                        if len(hits) < limit:
                            a, b = at[k], at[k + len(needle) - 1] + 1
                            hits.append({"vol": vol, "page": page, "path": path, "start": a, "end": b,
                                         "before": text[max(0, a - CONTEXT):a], "match": text[a:b],
                                         "after": text[b:b + CONTEXT]})
                        k = folded.find(needle, k + len(needle))
        return {"hits": hits, "total": total}
