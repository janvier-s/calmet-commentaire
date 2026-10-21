"""Write a `chapter` field on every verse and commentary block (after verse_number / verse_ref).

Calmet prints the chapter heading only on the page where a chapter opens, and the end of
the previous chapter's commentary often runs on after it. Each entry is assigned as
export.py always did for verses: when a heading opens chapter N+1, entries that keep
rising in chapter N's numbering stay in chapter N (on that page and the next ones) until a
number drops back. Pages before a book's first heading get chapter null.

A verse whose Latin is plainly the same-numbered verse of the chapter before or after
(in the Vulgate) goes to that chapter. For commentary, two more rules:
  - a block with no lemma (no Latin, no French translation) continues the block before it,
    so it keeps that block's chapter whatever its verse_ref says;
  - while a chapter is changing, a block's Latin lemma is matched against the Vulgate text
    of both chapters, and a clear match decides (verse_refs are sometimes wrong there).

Places to check against the scan go to docs/chapter_check.json:
  - split:    a page shared by two chapters (where the split falls)
  - vulgate:  the Vulgate placed a block in the other chapter than its verse_ref suggested
              (its verse_ref is probably wrong)
  - vulgate_verse: a verse is plainly verse n of the neighbouring chapter in the Vulgate,
              so it goes there (a heading in the wrong place, usually)
  - restart:  numbers drop back to 1-3 inside a chapter with no heading (heading missed?)
  - jump:     a heading that doesn't follow on from the previous one

Usage: python3 assign_chapters.py [--dry-run] [book key ...]   (default: every book)
"""
import functools
import json
import re
import sys

from export import chapter_of
from paths import BOOKS, DATA, DOCS, VUL, load, pages
from psalms_check import sim, words

CLEAR, MARGIN = 0.6, 0.25  # a Vulgate match decides when this good and this much better


def num(x):
    """The (first) verse number of a verse_number / verse_ref: 7, "7", "7-9"."""
    if isinstance(x, int):
        return x
    m = re.match(r"\s*(\d+)", str(x or ""))
    return int(m.group(1)) if m else None


@functools.lru_cache(maxsize=None)
def vulgate(key):
    path = VUL / f"{BOOKS[key]['vul']}.json"
    if not path.exists():
        return {}
    return {c["chapter"]: [words(v["text"]) for v in c["verses"]]
            for c in json.loads(path.read_text())["chapters"]}


def vul_score(key, ch, quote):
    lw = words(quote)
    if len(lw) < 3:
        return None
    return max((sim(lw, vw) for vw in vulgate(key).get(ch, [])), default=0)


def with_chapter(entry, after, ch):
    """The entry with `chapter` placed right after its number field."""
    out = {}
    for k, v in entry.items():
        if k == "chapter":
            continue
        out[k] = v
        if k == after:
            out["chapter"] = ch
    if "chapter" not in out:
        out["chapter"] = ch
    return out


class Track:
    """The chapter of one section (verses or commentary), entry by entry."""

    def __init__(self, key, section, field, report):
        self.key, self.section, self.field, self.report = key, section, field, report
        self.chapter, self.last, self.pending = None, 0, None
        self.transition = None  # (old, new) while a chapter change is being settled
        self.overruled = False  # the Vulgate overruled this entry's verse_ref

    def heading(self, ch):
        if self.chapter is None:
            self.chapter, self.last = ch, 0
        elif ch != self.chapter:
            self.pending, self.transition = ch, (self.chapter, ch)

    def switch(self, n):
        self.chapter, self.last, self.pending = self.pending, n or 0, None

    def next(self, entry, where):
        n = num(entry.get(self.field))
        if self.section == "commentary":
            lemma = (entry.get("latin_quote") or "").strip() or (entry.get("french_translation") or "").strip()
            if not lemma and self.chapter is not None:
                return self.chapter  # continuation of the block before
        if self.pending is not None:
            unnumbered_verse = n is None and self.section == "verses"
            switch_now = (n is not None and n < self.last) or unnumbered_verse
            if not switch_now and not self.last:
                if self.section == "verses":
                    lat = entry.get("latin") or ""
                    so = vul_score(self.key, self.chapter, lat)
                    sn = vul_score(self.key, self.pending, lat)
                    switch_now = not (so is not None and sn is not None and so > sn)
                else:
                    switch_now = True
            if switch_now:
                self.switch(n)
        elif n is not None and n <= 3 and self.last >= 10 and self.chapter:
            self.report.append(dict(kind="restart", page=where,
                                    msg=f"{self.section}: {self.field} {n} after {self.last} in chapter {self.chapter}, "
                                        f"no chapter heading (heading missed, or a misread number?)"))
        if self.section == "commentary" and self.transition:
            self.vulgate_check(entry, n, where)
        if n is not None and not self.overruled:
            self.last = n
        self.overruled = False
        # not the Psalms: Calmet numbers them apart from the Vulgate (title unnumbered)
        if self.section == "verses" and n and self.chapter and self.key != "psalms":
            return self.verse_vulgate(entry, n, where)
        return self.chapter

    def verse_vulgate(self, entry, n, where):
        """A verse whose text is plainly verse n of the chapter before or after goes there."""
        lw = words(entry.get("latin"))
        if len(lw) < 4:
            return self.chapter
        vul = vulgate(self.key)

        def score(ch):
            vs = vul.get(ch) or []
            return sim(lw, vs[n - 1]) if 0 < n <= len(vs) else 0
        here = score(self.chapter)
        for other in (self.chapter - 1, self.chapter + 1):
            if score(other) >= 0.8 and score(other) - here >= MARGIN:
                self.report.append(dict(kind="vulgate_verse", page=where,
                                        msg=f"verse {n} “{(entry.get('latin') or '')[:40]}” is {other}:{n} in the Vulgate, "
                                            f"but follows chapter {self.chapter}'s heading (misplaced heading?)"))
                return other
        return self.chapter

    def vulgate_check(self, entry, n, where):
        old, new = self.transition
        quote = entry.get("latin_quote") or ""
        so, sn = vul_score(self.key, old, quote), vul_score(self.key, new, quote)
        if so is None or sn is None:
            return
        if self.pending is not None and sn >= CLEAR and sn - so >= MARGIN:
            self.switch(None)  # its verse_ref belongs to the old numbering: don't count from it
            self.overruled = True
            self.report.append(dict(kind="vulgate", page=where,
                                    msg=f"“{quote[:40]}” is chapter {new} in the Vulgate; verse_ref {entry.get('verse_ref')} "
                                        f"continued chapter {old}'s numbering (wrong verse_ref?)"))
        elif self.pending is None and self.chapter == new and so >= CLEAR and so - sn >= MARGIN:
            self.chapter, self.pending = old, new
            self.report.append(dict(kind="vulgate", page=where,
                                    msg=f"“{quote[:40]}” is chapter {old} in the Vulgate; verse_ref {entry.get('verse_ref')} "
                                        f"looked like chapter {new} (wrong verse_ref?)"))

    def end_page(self):
        if self.pending is None:
            self.transition = None


def assign(key, dry, report):
    tracks = {"verses": Track(key, "verses", "verse_number", report),
              "commentary": Track(key, "commentary", "verse_ref", report)}
    current = None
    for volume in BOOKS[key]["studium"]:
        if not (DATA / volume / "normalized").is_dir():
            continue  # not transcribed yet (Psalms 21b, 21c)
        for p in pages(volume):
            try:
                page = load(p)
            except json.JSONDecodeError:
                continue
            where = f"{volume}/{p.stem}"
            opens = chapter_of(page)
            if opens and current and opens not in (current, current + 1):  # repeated: the heading over
                # the commentary (often with the chapter's introduction) and again over the text
                report.append(dict(kind="jump", page=where, msg=f"chapter heading {opens} after {current}"))
            changed = False
            for section, t in tracks.items():
                if opens:
                    t.heading(opens)
                items = page.get(section) or []
                chs = [t.next(it, where) for it in items]
                if len(set(chs)) > 1 or (t.pending is not None and items):
                    parts = ", ".join(f"{chs.count(c)} in chapter {c}" for c in dict.fromkeys(chs))
                    report.append(dict(kind="split", page=where,
                                       msg=f"{section}: {parts}" + ("" if t.pending is None else
                                                                    f" (chapter {t.pending} not started yet)")))
                t.end_page()
                new = [with_chapter(it, t.field, c) for it, c in zip(items, chs)]
                if new != items or [list(a) for a in new] != [list(a) for a in items]:
                    page[section], changed = new, True
            if opens:
                current = opens
            if changed and not dry:
                p.write_text(json.dumps(page, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv):
    dry = "--dry-run" in argv
    keys = [a for a in argv if not a.startswith("--")] or list(BOOKS)
    report = []
    for key in keys:
        if not any((DATA / v / "normalized").is_dir() for v in BOOKS[key]["studium"]):
            continue
        before = len(report)
        assign(key, dry, report)
        for r in report[before:]:
            r["book"] = key
    from collections import Counter
    print(dict(Counter(r["kind"] for r in report)))
    out = DOCS / "chapter_check.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{'(dry run) ' if dry else ''}-> {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
