import json
p99 = json.loads(open("/Users/Janvier/Library/Mobile Documents/com~apple~CloudDocs/for-the-kingdom/STUDIUM/data/15_esdras/normalized/page_0099.json").read())
p100 = json.loads(open("/Users/Janvier/Library/Mobile Documents/com~apple~CloudDocs/for-the-kingdom/STUDIUM/data/15_esdras/normalized/page_0100.json").read())

v22 = None
for i, v in enumerate(p100["verses"]):
    if v["verse_number"] == 22:
        v22 = v
        del p100["verses"][i]
        break

if v22:
    p99["verses"].append(v22)
    open("/Users/Janvier/Library/Mobile Documents/com~apple~CloudDocs/for-the-kingdom/STUDIUM/data/15_esdras/normalized/page_0099.json", "w").write(json.dumps(p99, ensure_ascii=False, indent=2))
    open("/Users/Janvier/Library/Mobile Documents/com~apple~CloudDocs/for-the-kingdom/STUDIUM/data/15_esdras/normalized/page_0100.json", "w").write(json.dumps(p100, ensure_ascii=False, indent=2))
    print("Fixed!")
else:
    print("Not found")
