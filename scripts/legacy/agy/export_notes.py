import sys
import json
from pathlib import Path
from booklet.calmet import notes

if len(sys.argv) < 3:
    print("Usage: python3 -m booklet.dump_all <book_key> <num_chapters> <out_folder>")
    print("Example: python3 -m booklet.dump_all genesis 50 genese")
    sys.exit(1)

book_key = sys.argv[1]
num_chapters = int(sys.argv[2])
out_folder = sys.argv[3]

OUTPUT_DIR = Path(f"/Users/Janvier/Documents/Bible n stuff/Websites/dom-calmet-web/src/lib/data/calmet/{out_folder}")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

for chapter in range(1, num_chapters + 1):
    print(f"Processing chapter {chapter}...")
    try:
        out = notes(book_key, chapter, 1, 999)
        out_file = OUTPUT_DIR / f"calmet_chapter_{chapter:02d}.json"
        with open(out_file, 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error processing chapter {chapter}: {e}")

print("Done exporting all chapters.")
