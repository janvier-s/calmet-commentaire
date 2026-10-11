import json
from collections import defaultdict
from pathlib import Path

DIR = Path("/Users/Janvier/Library/Mobile Documents/com~apple~CloudDocs/for-the-kingdom/STUDIUM/data/11_3_rois/normalized")
verse_pages = defaultdict(list)
for p in sorted(DIR.glob("page_*.json")):
    data = json.loads(p.read_text())
    ch = data.get("chapter_number")
    for v in data.get("verses", []):
        v_num = v.get("verse_number", "")
        verse_pages[f"{ch}:{v_num}"].append(p.name)

dups = {k: v for k, v in verse_pages.items() if len(v) > 1}
if dups:
    print(f"Found {len(dups)} duplicate verses across pages!")
    for k, v in list(dups.items())[:10]:
        print(f"Verse {k} found in pages {v}")
else:
    print("No duplicate verses across pages.")
