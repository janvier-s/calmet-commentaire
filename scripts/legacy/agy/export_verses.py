import sys
import json
import re
from pathlib import Path
from collections import defaultdict

if len(sys.argv) < 3:
    print("Usage: python3 dump_verses.py <book_folder> <book_name>")
    print("Example: python3 dump_verses.py 01_genese Genèse")
    sys.exit(1)

book_folder = sys.argv[1]
book_name = sys.argv[2]

STUDIUM = Path(f"/Users/Janvier/Library/Mobile Documents/com~apple~CloudDocs/for-the-kingdom/STUDIUM/data/{book_folder}/normalized")
slug = sys.argv[3] if len(sys.argv) > 3 else book_folder.split('_')[1]  # e.g. 09_1_rois -> 1-samuel
RAW_DIR = Path(f"/Users/Janvier/Documents/Bible n stuff/Websites/dom-calmet-web/src/lib/data/raw/{slug}")
RAW_DIR.mkdir(parents=True, exist_ok=True)

chapters = defaultdict(list)
chapter_summaries = {}

current_chapter = None

# Group verses by chapter_number
for p in sorted(STUDIUM.glob("page_[0-9][0-9][0-9][0-9].json")):
    try:
        page = json.loads(p.read_text(encoding="utf-8"))
        ch = page.get("chapter_number")
        if not ch:
            title = page.get("chapter_title", "")
            if title:
                import re
                # Psalms are titled "PSEAUME LX." ("SUR LE PSEAUME LX." is only a running head)
                m = re.search(r"CHAPITRE\s+([A-Z]+)", title) or re.match(r"\s*PSE?AUME\s+([A-Z]+)", title)
                if m:
                    roman = m.group(1)
                    if roman == "PREMIER":
                        ch = 1
                    else:
                        roman_map = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
                        val = 0
                        i = 0
                        valid = True
                        while i < len(roman):
                            if roman[i] not in roman_map:
                                valid = False
                                break
                            if i + 1 < len(roman) and roman[i+1] in roman_map and roman_map[roman[i]] < roman_map[roman[i+1]]:
                                val += roman_map[roman[i+1]] - roman_map[roman[i]]
                                i += 2
                            else:
                                val += roman_map[roman[i]]
                                i += 1
                        if valid:
                            ch = val

        page_verses = page.get("verses") or []
        for v in page_verses:
            v["source_pages"] = [p.name]

        if ch and ch != current_chapter and current_chapter:
            # New chapter starting mid-page: leading verses that continue the
            # previous chapter's numbering (before a superscription or verse 1) stay with it.
            prev_nums = [n for n in (v.get("verse_number") for v in chapters[current_chapter]) if isinstance(n, int)]
            last = max(prev_nums, default=0)
            carried = 0
            for v in (page_verses if last else []):
                n = v.get("verse_number")
                if not isinstance(n, int) or n < last:
                    break
                chapters[current_chapter].append(v)
                last = n
                carried += 1
            page_verses = page_verses[carried:]

        if ch:
            current_chapter = ch

        if not current_chapter:
            continue

        if page.get("chapter_summary") and current_chapter not in chapter_summaries:
            chapter_summaries[current_chapter] = page.get("chapter_summary")

        for v in page_verses:
            chapters[current_chapter].append(v)
    except json.JSONDecodeError:
        pass

for ch, verses in chapters.items():
    # Sort verses just in case, though they should be sequential
    # Sometimes verse_number is a string like "24." or int
    def v_num(v):
        import re
        m = re.search(r"(\d+)", str(v.get("verse_number", "")))
        return int(m.group(1)) if m else 0
        
    verses.sort(key=v_num)
    # A verse split across pages (or followed by one of Jerome's rubrics) is stored
    # as two entries with the same number: join them.
    import re
    merged = []
    for v in verses:
        if merged and v_num(v) == v_num(merged[-1]):
            last = merged[-1]
            for k in ("latin", "french"):
                left, right = (last.get(k) or "").strip(), (v.get(k) or "").strip()
                if re.search(r"\w-$", left) and right[:1].islower():  # word hyphenated at the page break
                    last[k] = left[:-1] + right
                else:
                    last[k] = " ".join(filter(None, [left, right]))
            a, b = last.get("annotations"), v.get("annotations")
            last["annotations"] = a + b if isinstance(a, list) and isinstance(b, list) else (
                " ".join(str(x) for x in (a, b) if x) or None)
            last["source_pages"] = last["source_pages"] + [p for p in v["source_pages"] if p not in last["source_pages"]]
        else:
            merged.append(v)
    verses = merged
    
    out = {
        "book": book_name,
        "chapter": ch,
        "chapter_summary": chapter_summaries.get(ch),
        "verses": verses
    }
    
    out_file = RAW_DIR / f"chapter_{ch:02d}.json"
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

print("Done exporting verses from normalized.")
