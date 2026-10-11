import json
p92 = json.loads(open("/Users/Janvier/Library/Mobile Documents/com~apple~CloudDocs/for-the-kingdom/STUDIUM/data/18_judith/normalized/page_0092.json").read())
p93 = json.loads(open("/Users/Janvier/Library/Mobile Documents/com~apple~CloudDocs/for-the-kingdom/STUDIUM/data/18_judith/normalized/page_0093.json").read())

verses_to_move = []
for v in list(p93.get("verses", [])):
    if v["verse_number"] in [24, 25]:
        verses_to_move.append(v)
        p93["verses"].remove(v)

if verses_to_move:
    p92["verses"].extend(verses_to_move)
    open("/Users/Janvier/Library/Mobile Documents/com~apple~CloudDocs/for-the-kingdom/STUDIUM/data/18_judith/normalized/page_0092.json", "w").write(json.dumps(p92, ensure_ascii=False, indent=2))
    open("/Users/Janvier/Library/Mobile Documents/com~apple~CloudDocs/for-the-kingdom/STUDIUM/data/18_judith/normalized/page_0093.json", "w").write(json.dumps(p93, ensure_ascii=False, indent=2))
    print("Moved!")
else:
    print("Not found")
