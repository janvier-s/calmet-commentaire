import json, re, sys, difflib
from pathlib import Path

# Usage: python3 fix_psalm_verses.py 21a_psaumes
# 1. Verse whose text opens with a different number ("12. Embrassez...") -> relabel, strip prefix.
# 2. Same verse repeated on the next page with near-identical Latin -> drop the repeat.
from paths import DATA

DIR = DATA / sys.argv[1] / "normalized"
norm = lambda s: re.sub(r'[^a-z]', '', (s or '').lower().replace('ſ', 's'))
PREFIX = re.compile(r'^(\s*_?)(\d+)\s*\.\s*')
# One-off mislabels found by hand: (page, latin starts with) -> verse number
MANUAL = {("page_0611.json", "Ipſi videntes"): 5}

pages = sorted(DIR.glob("page_[0-9][0-9][0-9][0-9].json"))
data = {p: json.loads(p.read_text()) for p in pages}
changed = set()

flat = [(p, v) for p in pages for v in data[p].get("verses") or []]
for i, (p, v) in enumerate(flat):
    for (page, start), n in MANUAL.items():
        if p.name == page and (v.get("latin") or "").startswith(start) and v.get("verse_number") != n:
            print(f"{p.name}: relabel v{v.get('verse_number')} -> {n} (manual)")
            v["verse_number"] = n
            changed.add(p)
    # Superscription ("In finem, Psalmus David") labelled 1 while the psalm's verse 1 follows
    if v.get("verse_number") == 1 and re.match(r'[\W_]*(In finem|Pſalmus|Psalmus)', v.get("latin") or "") \
            and i + 1 < len(flat) and flat[i + 1][1].get("verse_number") == 1:
        print(f"{p.name}: superscription labelled v1 -> None")
        v["verse_number"] = None
        changed.add(p)
    nums = {PREFIX.match(v.get(k) or "") and int(PREFIX.match(v[k]).group(2)) for k in ("french", "latin")} - {None}
    if len(nums) != 1:
        continue
    n = nums.pop()
    for k in ("french", "latin"):
        if v.get(k):
            v[k] = PREFIX.sub(r"\1", v[k], count=1)
    changed.add(p)
    label = v.get("verse_number")
    if n == label:
        continue
    # The prefix may itself be an OCR slip ("39." for 29): trust it only when it,
    # and not the label, fits between the neighbouring verses.
    prv = flat[i - 1][1].get("verse_number") if i else None
    nxt = flat[i + 1][1].get("verse_number") if i + 1 < len(flat) else None
    fits = lambda x: isinstance(x, int) and isinstance(prv, int) and x == prv + 1 and (not isinstance(nxt, int) or nxt in (x + 1, 1))
    if fits(n) and not fits(label):
        print(f"{p.name}: relabel v{label} -> {n}")
        v["verse_number"] = n

for prev, cur in zip(pages, pages[1:]):
    before = {v.get("verse_number"): v for v in data[prev].get("verses") or [] if v.get("verse_number") is not None}
    keep = []
    for v in data[cur].get("verses") or []:
        twin = before.get(v.get("verse_number"))
        if twin and difflib.SequenceMatcher(None, norm(twin.get("latin")), norm(v.get("latin"))).ratio() > 0.9:
            print(f"{cur.name}: drop repeat of v{v['verse_number']} (also on {prev.name})")
            changed.add(cur)
            continue
        keep.append(v)
    if data[cur].get("verses"):
        data[cur]["verses"] = keep

# 3. Latin-less copies (a separate French paraphrase) and capitalised commentary lemmas
#    ("ET PERMANEBIT CUM SOLE, &c.") extracted as verses, when a proper copy exists nearby.
def proper(v):
    lat = v.get("latin") or ""
    return bool(lat) and not (sum(c.isupper() for c in lat) > 0.6 * sum(c.isalpha() for c in lat))
psalm, cur = {}, 0
for p in pages:
    if re.match(r'\s*PSE?AUME\s', data[p].get("chapter_title") or ""):
        cur += 1
    psalm[p] = cur
for p in pages:
    vs = data[p].get("verses") or []
    near = [v for q in pages if q != p and psalm[q] == psalm[p] for v in data[q].get("verses") or []]
    keep = []
    for v in vs:
        if v.get("verse_number") is not None and not proper(v) and any(
                w.get("verse_number") == v["verse_number"] and proper(w) for w in near):
            print(f"{p.name}: drop non-verse copy of v{v['verse_number']} ({(v.get('latin') or 'no latin')[:30]})")
            changed.add(p)
            continue
        keep.append(v)
    if vs:
        data[p]["verses"] = keep

for p in changed:
    p.write_text(json.dumps(data[p], ensure_ascii=False, indent=2))
print(f"{len(changed)} pages updated")
