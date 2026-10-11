import json
p138 = json.loads(open("/Users/Janvier/Library/Mobile Documents/com~apple~CloudDocs/for-the-kingdom/STUDIUM/data/18_judith/normalized/page_0138.json").read())
p139 = json.loads(open("/Users/Janvier/Library/Mobile Documents/com~apple~CloudDocs/for-the-kingdom/STUDIUM/data/18_judith/normalized/page_0139.json").read())

verses_to_move = []
for v in list(p139.get("verses", [])):
    if v["verse_number"] in [29, 30, 31]:
        verses_to_move.append(v)
        p139["verses"].remove(v)

if verses_to_move:
    p138["verses"].extend(verses_to_move)
    open("/Users/Janvier/Library/Mobile Documents/com~apple~CloudDocs/for-the-kingdom/STUDIUM/data/18_judith/normalized/page_0138.json", "w").write(json.dumps(p138, ensure_ascii=False, indent=2))
    open("/Users/Janvier/Library/Mobile Documents/com~apple~CloudDocs/for-the-kingdom/STUDIUM/data/18_judith/normalized/page_0139.json", "w").write(json.dumps(p139, ensure_ascii=False, indent=2))
    print("Moved!")
else:
    print("Not found")
