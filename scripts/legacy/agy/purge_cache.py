import json

cache_path = "booklet/llm_cache.json"
cache = json.loads(open(cache_path).read())
initial_len = len(cache)

to_delete = []
for k, v in cache.items():
    if "ſ" in v or "étoit" in v or "avoit" in v or "faiſoit" in v:
        to_delete.append(k)

for k in to_delete:
    del cache[k]

with open(cache_path, "w") as f:
    json.dump(cache, f, ensure_ascii=False, indent=2)

print(f"Purged {len(to_delete)} entries from cache. {len(cache)} remain.")
