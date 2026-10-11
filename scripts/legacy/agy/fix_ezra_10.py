import json
p132 = json.loads(open("/Users/Janvier/Library/Mobile Documents/com~apple~CloudDocs/for-the-kingdom/STUDIUM/data/15_esdras/normalized/page_0132.json").read())
p132["verses"] = [v for v in p132.get("verses", []) if v.get("verse_number") != 44]
open("/Users/Janvier/Library/Mobile Documents/com~apple~CloudDocs/for-the-kingdom/STUDIUM/data/15_esdras/normalized/page_0132.json", "w").write(json.dumps(p132, ensure_ascii=False, indent=2))
