import sys
import json
from booklet.calmet import notes

# book '01_genese' might be mapped differently in BOOKS. Let's check `books.json` or just try '01_genese'.
# Actually, the key is usually just the book name or the directory. 
# Let's read books.json to see what key is used for Genesis.
out = notes("genesis", 1, 1, 31)

with open('/Users/Janvier/Documents/Bible n stuff/Websites/dom-calmet-web/src/lib/data/calmet_chapter_01.json', 'w') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print("Exported clean notes to dom-calmet-web/src/lib/data/calmet_chapter_01.json")
