import json
from pathlib import Path
import hashlib

def get_hash(text: str) -> str:
    return hashlib.md5(text.encode('utf-8')).hexdigest()

cache_path = Path("booklet/llm_cache.json")
if cache_path.exists():
    cache = json.loads(cache_path.read_text())
else:
    cache = {}

base_dir = Path("/Users/Janvier/Library/Mobile Documents/com~apple~CloudDocs/for-the-kingdom/STUDIUM/data")
restored = 0

for book_dir in base_dir.glob("*"):
    norm_dir = book_dir / "normalized"
    if not norm_dir.exists(): continue
    
    for json_file in norm_dir.glob("*.json"):
        try:
            data = json.loads(json_file.read_text())
        except: continue
        
        def add_to_cache(text):
            global restored
            if not text or not text.strip(): return
            h = get_hash(text)
            if h not in cache:
                cache[h] = text
                restored += 1
                
        if data.get("chapter_summary"): add_to_cache(data["chapter_summary"])
        if "verses" in data:
            for v in data["verses"]:
                if v.get("french"): add_to_cache(v["french"])
        if "commentary" in data:
            for c in data["commentary"]:
                if c.get("french_translation"): add_to_cache(c["french_translation"])
                if c.get("french_commentary"): add_to_cache(c["french_commentary"])

cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2))
print(f"Restored {restored} entries to cache! Total cache size: {len(cache)}")
