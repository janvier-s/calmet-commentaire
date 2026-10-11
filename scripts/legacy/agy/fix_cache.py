import json
from pathlib import Path
import hashlib

def get_hash(text: str) -> str:
    return hashlib.md5(text.encode('utf-8')).hexdigest()

cache_path = Path("booklet/llm_cache.json")
cache = json.loads(cache_path.read_text())

base_dir = Path("/Users/Janvier/Library/Mobile Documents/com~apple~CloudDocs/for-the-kingdom/STUDIUM/data")
removed = 0

# Books 12 onwards might not be fully modernized!
for book_dir in base_dir.glob("*"):
    # get book number
    try:
        num = int(book_dir.name.split('_')[0])
        if num < 12:
            continue
    except:
        continue
        
    norm_dir = book_dir / "normalized"
    if not norm_dir.exists(): continue
    
    for json_file in norm_dir.glob("*.json"):
        try:
            data = json.loads(json_file.read_text())
        except: continue
        
        def remove_from_cache(text):
            global removed
            if not text or not text.strip(): return
            h = get_hash(text)
            if h in cache and cache[h] == text:
                del cache[h]
                removed += 1
                
        if data.get("chapter_summary"): remove_from_cache(data["chapter_summary"])
        if "verses" in data:
            for v in data["verses"]:
                if v.get("french"): remove_from_cache(v["french"])
        if "commentary" in data:
            for c in data["commentary"]:
                if c.get("french_translation"): remove_from_cache(c["french_translation"])
                if c.get("french_commentary"): remove_from_cache(c["french_commentary"])

cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2))
print(f"Removed {removed} unprocessed entries from cache! Total cache size: {len(cache)}")
