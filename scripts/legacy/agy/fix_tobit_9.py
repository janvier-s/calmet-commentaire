import json
p95 = json.loads(open("/Users/Janvier/Library/Mobile Documents/com~apple~CloudDocs/for-the-kingdom/STUDIUM/data/17_tobie/normalized/page_0095.json").read())
p96 = json.loads(open("/Users/Janvier/Library/Mobile Documents/com~apple~CloudDocs/for-the-kingdom/STUDIUM/data/17_tobie/normalized/page_0096.json").read())

verses_to_move = []
for v in list(p96.get("verses", [])):
    if v["verse_number"] in [10, 11, 12]:
        verses_to_move.append(v)
        p96["verses"].remove(v)

if verses_to_move:
    p95["verses"].extend(verses_to_move)
    open("/Users/Janvier/Library/Mobile Documents/com~apple~CloudDocs/for-the-kingdom/STUDIUM/data/17_tobie/normalized/page_0095.json", "w").write(json.dumps(p95, ensure_ascii=False, indent=2))
    open("/Users/Janvier/Library/Mobile Documents/com~apple~CloudDocs/for-the-kingdom/STUDIUM/data/17_tobie/normalized/page_0096.json", "w").write(json.dumps(p96, ensure_ascii=False, indent=2))
    print("Moved!")
else:
    print("Not found")
