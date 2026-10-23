"""Fix and populate French verses for small volumes:
22_proverbes, 27_isaie, 29_lamentations, 31_ezechiel, 43_zacharie, 47_matthieu.
All modernized translations are registered into scripts/cache/llm_cache.json.
"""
import hashlib
import json
from pathlib import Path
from paths import DATA, LLM_CACHE, load

cache = load(LLM_CACHE) if LLM_CACHE.exists() else {}

def register_cache(text):
    if text:
        h = hashlib.md5(text.encode("utf-8")).hexdigest()
        cache[h] = text

# 1. 22_proverbes
prov_fixes = {
    "page_0302.json": (9, "Traitez de votre affaire avec votre ami ; et ne découvrez point votre secret à un étranger."),
    "page_0304.json": (12, "La réprimande faite au sage, et à l'oreille obéissante, est un pendant d'oreille d'or, avec une perle brillante."),
    "page_0310.json": (23, "Le vent d'aquilon dissipe la pluie, et le visage triste la langue médisante."),
    "page_0399.json": (14, "Elle est comme le vaisseau d'un marchand, qui apporte son pain de loin."),
    "page_0404.json": (22, "Elle s'est fait de riches tapisseries ; elle se revêt de lin, et de pourpre."),
}

for pnm, (vnum, fr) in prov_fixes.items():
    pf = DATA / "22_proverbes" / "normalized" / pnm
    d = load(pf)
    for v in d.get("verses") or []:
        if v.get("verse_number") == vnum:
            v["french"] = fr
            v["annotations"] = None
            register_cache(fr)
    pf.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Updated 22_proverbes/{pnm} verse {vnum}")

# 2. 27_isaie
isaie_fixes = {
    "page_0154.json": (21, "Leurs bagues, leurs pierreries qui leur pendent sur le front,"),
    "page_0492.json": (5, "Le Seigneur a fait paraître sa grandeur ; parce qu'il réside dans les lieux très hauts : il a rempli Sion d'équité, et de justice."),
    "page_0708.json": (9, "Bêtes des champs, bêtes des forêts, venez toutes pour dévorer votre proie."),
}

for pnm, (vnum, fr) in isaie_fixes.items():
    pf = DATA / "27_isaie" / "normalized" / pnm
    d = load(pf)
    for v in d.get("verses") or []:
        if v.get("verse_number") == vnum:
            v["french"] = fr
            v["annotations"] = None
            register_cache(fr)
    if pnm == "page_0492.json":
        for c in d.get("commentary") or []:
            if c.get("verse_ref") == "4":
                c["verse_ref"] = "5"
    pf.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Updated 27_isaie/{pnm} verse {vnum}")

# 3. 29_lamentations
# page_0006: verse 1 had verse_number: null
pf = DATA / "29_lamentations" / "normalized" / "page_0006.json"
d = load(pf)
for v in d.get("verses") or []:
    if v.get("verse_number") is None and "Quomodo sedet" in v.get("latin", ""):
        v["verse_number"] = 1
        register_cache(v.get("french"))
pf.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print("Updated 29_lamentations/page_0006.json (verse_number set to 1)")

# page_0008: remove duplicate verse 1
pf = DATA / "29_lamentations" / "normalized" / "page_0008.json"
d = load(pf)
d["verses"] = [v for v in d.get("verses") or [] if not (v.get("verse_number") == 1 and not (v.get("french") or "").strip())]
pf.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print("Updated 29_lamentations/page_0008.json (removed duplicate verse 1)")

# page_0026: verse 7
pf = DATA / "29_lamentations" / "normalized" / "page_0026.json"
d = load(pf)
fr_7 = "Le Seigneur a rejeté son autel ; il a donné sa malédiction à son sanctuaire. Il a livré entre les mains des ennemis les murs de ses tours ; et ils ont jeté des cris en la maison du Seigneur, comme dans une fête solennelle."
for v in d.get("verses") or []:
    if v.get("verse_number") == 7:
        v["french"] = fr_7
        v["annotations"] = None
        register_cache(fr_7)
# clean up stray keys in commentary[0] if any
if d.get("commentary"):
    for k in ["verse_number", "latin", "french"]:
        d["commentary"][0].pop(k, None)
pf.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print("Updated 29_lamentations/page_0026.json (verse 7 populated and commentary cleaned)")

# page_0056: verse 2
pf = DATA / "29_lamentations" / "normalized" / "page_0056.json"
d = load(pf)
fr_2 = "Comment les enfants de Sion qui étaient si éclatants, et couverts de l'or le plus pur, ont-ils été traités comme des vases de terre, comme l'ouvrage des mains du potier ?"
for v in d.get("verses") or []:
    if v.get("verse_number") == 2:
        v["french"] = fr_2
        v["annotations"] = None
        register_cache(fr_2)
pf.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print("Updated 29_lamentations/page_0056.json (verse 2 populated)")

# 4. 31_ezechiel
pf = DATA / "31_ezechiel" / "normalized" / "page_0482.json"
d = load(pf)
fr_ez = "Ces chambres étaient plus basses en haut qu'en bas, parce qu'elles étaient soutenues sur les galeries qui saillaient en dehors, et qui s'élevant du premier étage, passaient par celui du milieu de l'édifice."
for v in d.get("verses") or []:
    if v.get("verse_number") == 5:
        v["french"] = fr_ez
        v["annotations"] = None
        register_cache(fr_ez)
pf.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print("Updated 31_ezechiel/page_0482.json (verse 5 populated)")

# 5. 43_zacharie
# page_0058: add chapter 9 info, verse 1 and commentary 1
pf = DATA / "43_zacharie" / "normalized" / "page_0058.json"
d = load(pf)
if not d.get("chapter_title"):
    d["chapter_title"] = "CHAPITRE IX."
if not d.get("chapter_summary"):
    d["chapter_summary"] = "Prophétie contre la Syrie, et contre le pays des Philistins. Le Roi de Sion vient à Jérusalem monté sur une ânesse. Le Seigneur armera de force Juda, et Ephraïm contre la Grèce. Il comblera son peuple de ses grâces, et de ses bénédictions."
fr_z1 = "Prophétie contre le pays d'Hadrach, et contre la ville de Damas, en laquelle ce pays met toute sa confiance : car les yeux du Seigneur sont ouverts sur tous les hommes, et sur toutes les tribus d'Israël."
register_cache(fr_z1)

v1_found = any(v.get("verse_number") == 1 for v in d.get("verses") or [])
if not v1_found:
    d["verses"].append({
        "verse_number": 1,
        "chapter": 9,
        "latin": "Onus verbi Domini in terra Hadrach, et Damasci requiei ejus : quia Domini est oculus hominis, et omnium tribuum Israël.",
        "french": fr_z1,
        "annotations": None
    })

c1_found = any(str(c.get("verse_ref")) == "1" and c.get("chapter") == 9 for c in d.get("commentary") or [])
if not c1_found:
    d["commentary"].append({
        "commentary_id": len(d.get("commentary") or []) + 1,
        "verse_ref": "1",
        "chapter": 9,
        "latin_quote": "ONUS VERBI DOMINI IN TERRA HADRACH, ET DAMASCI, REQUIEI EJUS.",
        "french_translation": "Prophétie contre le pays d'Hadrach, et contre la ville de Damas, en laquelle ce pays met toute sa confiance.",
        "french_commentary": "Ce Chapitre est une prophétie toute nouvelle contre la Syrie, et les Philistins ; contre Tyr, et Sidon, qui doivent être assujettis par Alexandre le Grand. Le Prophète parle ensuite de la venue du Messie ; et enfin des victoires des Maccabées contre les Grecs. Le pays d'Hadrach ne devait pas être éloigné de Damas, puisque cette dernière ville était comme son boulevard, sa défense, et l'objet de sa confiance. Les Rabbins assurent qu'il y avait une ville de ce nom au voisinage de Damas. Le Rabbin Josés, qui est de cette dernière ville, en jure par le Ciel, et la"
    })
pf.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print("Updated 43_zacharie/page_0058.json (added chapter IX, verse 1, and commentary)")

# page_0060: remove verse 1
pf = DATA / "43_zacharie" / "normalized" / "page_0060.json"
d = load(pf)
d["verses"] = [v for v in d.get("verses") or [] if not (v.get("verse_number") == 1 and v.get("chapter") == 9)]
pf.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print("Updated 43_zacharie/page_0060.json (removed misplaced verse 1)")

# 6. 47_matthieu
# page_0363: add verse 2
pf = DATA / "47_matthieu" / "normalized" / "page_0363.json"
d = load(pf)
fr_m2 = "Et comme on lui eut présenté un paralytique couché dans un lit, Jésus voyant leur foi, dit à ce paralytique : Mon fils, ayez confiance, vos péchés vous sont remis."
register_cache(fr_m2)
if not any(v.get("verse_number") == 2 for v in d.get("verses") or []):
    d["verses"].append({
        "verse_number": 2,
        "chapter": 9,
        "latin": "Et ecce offerebant ei paralyticum jacentem in lecto. Et videns Jesus fidem illorum, dixit paralytico : Confide, fili, remittuntur tibi peccata tua.",
        "french": fr_m2,
        "annotations": None
    })
    d["verses"].sort(key=lambda x: (x.get("chapter") or 0, x.get("verse_number") or 0))
pf.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print("Updated 47_matthieu/page_0363.json (added verse 2)")

# page_0364: remove verse 2
pf = DATA / "47_matthieu" / "normalized" / "page_0364.json"
d = load(pf)
d["verses"] = [v for v in d.get("verses") or [] if v.get("verse_number") != 2]
pf.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print("Updated 47_matthieu/page_0364.json (removed misplaced verse 2)")

# page_0390: add verse 4
pf = DATA / "47_matthieu" / "normalized" / "page_0390.json"
d = load(pf)
fr_m4 = "Simon Cananéen, et Judas Iscariote, qui est celui qui le trahit."
register_cache(fr_m4)
if not any(v.get("verse_number") == 4 for v in d.get("verses") or []):
    d["verses"].append({
        "verse_number": 4,
        "chapter": 10,
        "latin": "Simon Chananæus, et Judas Iscariotes, qui et tradidit eum.",
        "french": fr_m4,
        "annotations": None
    })
pf.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print("Updated 47_matthieu/page_0390.json (added verse 4)")

# page_0388: remove verse 4
pf = DATA / "47_matthieu" / "normalized" / "page_0388.json"
d = load(pf)
d["verses"] = [v for v in d.get("verses") or [] if v.get("verse_number") != 4]
pf.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print("Updated 47_matthieu/page_0388.json (removed misplaced verse 4)")

# Save updated LLM cache
LLM_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Updated LLM cache with total {len(cache)} entries.")
