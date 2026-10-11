import json
from pathlib import Path

import sys
from paths import WEB

DIR = WEB / "raw" / (sys.argv[1] if len(sys.argv) > 1 else "job")
issues = 0
for p in sorted(DIR.glob("chapter_*.json")):
    data = json.loads(p.read_text())
    verses = data.get("verses", [])
    if not verses:
        print(f"{p.name} has NO verses!")
        issues += 1
        continue
    
    last_v = 0
    duplicates = 0
    missing = 0
    for v in verses:
        v_num = str(v.get("verse_number", ""))
        import re
        m = re.search(r"(\d+)", v_num)
        if m:
            num = int(m.group(1))
            if num == last_v:
                duplicates += 1
            elif num > last_v + 1 and last_v != 0:
                missing += (num - last_v - 1)
            last_v = num
    
    if duplicates > 0 or missing > 0:
        print(f"{p.name}: {len(verses)} verses. Duplicates: {duplicates}, Missing: {missing}")
        issues += 1

if issues == 0:
    print("No structural defects found in verse flow!")
