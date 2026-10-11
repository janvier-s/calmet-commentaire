"""Export books from normalized/ to the dom-calmet-web data files.

  raw/<site>/chapter_NN.json           the verses (Latin, French, summary)
  calmet/<site>/calmet_chapter_NN.json the commentary notes, sewn across pages (calmet.py)

Usage: python3 export.py genesis job          (keys of books.json)
       python3 export.py --published          (every book already on the site)
Then, in dom-calmet-web: npm run build, commit, npm run deploy.
"""
import json
import re
import sys
from collections import defaultdict

from calmet import notes
from paths import BOOKS, WEB, load, pages

ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def roman(s):
    total = prev = 0
    for ch in reversed(s):
        if ch not in ROMAN:
            return None
        v = ROMAN[ch]
        total += -v if v < prev else v
        prev = max(prev, v)
    return total


def chapter_of(page):
    """The chapter a page opens, from chapter_number or a title like "CHAPITRE XII."."""
    if page.get("chapter_number"):
        return page["chapter_number"]
    title = page.get("chapter_title") or ""
    # Psalms are titled "PSEAUME LX." ("SUR LE PSEAUME LX." is only a running head)
    m = re.search(r"CHAPITRE\s+([A-Z]+)", title) or re.match(r"\s*PSE?AUME\s+([A-Z]+)", title)
    if not m:
        return None
    return 1 if m.group(1) == "PREMIER" else roman(m.group(1))


def num(v):
    m = re.search(r"\d+", str(v.get("verse_number", "")))
    return int(m.group()) if m else 0


def join(left, right):
    left, right = (left or "").strip(), (right or "").strip()
    if re.search(r"\w-$", left) and right[:1].islower():  # word hyphenated at the page break
        return left[:-1] + right
    return " ".join(filter(None, [left, right]))


def verses_by_chapter(key):
    chapters, summaries, current = defaultdict(list), {}, None
    for volume in BOOKS[key]["studium"]:
        for p in pages(volume):
            try:
                page = load(p)
            except json.JSONDecodeError:
                print(f"  skipped malformed {volume}/{p.name}")
                continue
            ch = chapter_of(page)
            page_verses = page.get("verses") or []
            for v in page_verses:
                v["source_pages"] = [p.name]
            if ch and ch != current and current:
                # New chapter starting mid-page: leading verses that continue the
                # previous chapter's numbering stay with it.
                last = max((num(v) for v in chapters[current]), default=0)
                carried = 0
                for v in (page_verses if last else []):
                    if not isinstance(v.get("verse_number"), int) or num(v) < last:
                        break
                    chapters[current].append(v)
                    last = num(v)
                    carried += 1
                page_verses = page_verses[carried:]
            if ch:
                current = ch
            if not current:
                continue
            if page.get("chapter_summary") and current not in summaries:
                summaries[current] = page["chapter_summary"]
            chapters[current].extend(page_verses)

    for ch, verses in chapters.items():
        verses.sort(key=num)
        # A verse split across pages (or followed by one of Jerome's rubrics) is
        # stored as two entries with the same number: join them.
        merged = []
        for v in verses:
            if merged and num(v) == num(merged[-1]):
                last = merged[-1]
                for k in ("latin", "french"):
                    last[k] = join(last.get(k), v.get(k))
                a, b = last.get("annotations"), v.get("annotations")
                last["annotations"] = a + b if isinstance(a, list) and isinstance(b, list) else (
                    " ".join(str(x) for x in (a, b) if x) or None)
                last["source_pages"] += [s for s in v["source_pages"] if s not in last["source_pages"]]
            else:
                merged.append(v)
        chapters[ch] = merged
    return chapters, summaries


def export(key):
    book = BOOKS[key]
    raw_dir, cal_dir = WEB / "raw" / book["site"], WEB / "calmet" / book["site"]
    raw_dir.mkdir(parents=True, exist_ok=True)
    cal_dir.mkdir(parents=True, exist_ok=True)
    chapters, summaries = verses_by_chapter(key)
    for ch, verses in sorted(chapters.items()):
        out = dict(book=book["fr"], chapter=ch, chapter_summary=summaries.get(ch), verses=verses)
        (raw_dir / f"chapter_{ch:02d}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    failed = []
    for ch in range(1, max(chapters, default=0) + 1):
        try:
            out = notes(key, ch, 1, 999)
            out.pop("decisions", None)  # the Lectio review log; the site doesn't use it
        except Exception as e:
            failed.append(f"{ch}: {e}")
            continue
        (cal_dir / f"calmet_chapter_{ch:02d}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{key} -> {book['site']}: {len(chapters)} chapters" + (f", notes failed for {failed}" if failed else ""))


if __name__ == "__main__":
    args = sys.argv[1:]
    if args == ["--published"]:
        args = [k for k, b in BOOKS.items() if (WEB / "calmet" / b["site"]).is_dir()]
    if not args:
        sys.exit(__doc__)
    for key in args:
        export(key)
