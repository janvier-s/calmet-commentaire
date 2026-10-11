import json, re
from pathlib import Path

DIR = Path("/Users/Janvier/Library/Mobile Documents/com~apple~CloudDocs/for-the-kingdom/STUDIUM/data/20_job/normalized")
for p in DIR.glob("*.json"):
    changed = False
    data = json.loads(p.read_text())
    if "verses" in data:
        for v in data["verses"]:
            num = v.get("verse_number")
            if isinstance(num, str):
                cleaned = re.sub(r'[^0-9]', '', num)
                if cleaned:
                    v["verse_number"] = int(cleaned)
                    changed = True
    if changed:
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        print(f"Fixed {p.name}")
