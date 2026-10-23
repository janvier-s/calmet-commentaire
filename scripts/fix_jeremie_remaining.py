"""Fix and populate the remaining 22 missing verses in 28_jeremie.
All modernized translations are registered in scripts/cache/llm_cache.json.
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

vol = "28_jeremie"
vol_dir = DATA / vol / "normalized"

# 1. page_0238.json (12:1)
pf = vol_dir / "page_0238.json"
d = load(pf)
fr = "Seigneur, si je dispute avec vous, ce n'est pas que je ne sache que vous êtes juste : permettez-moi cependant de vous faire ces justes plaintes : Pourquoi les méchants marchent-ils avec tant de prospérité dans leur voie ? Pourquoi tous ceux qui violent votre Loi, et qui agissent injustement, sont-ils si heureux ?"
for v in d.get("verses") or []:
    if v.get("verse_number") == 1:
        v["french"] = fr
        v["annotations"] = None
        register_cache(fr)
if d.get("commentary"):
    for k in ["latin", "french"]:
        d["commentary"][0].pop(k, None)
pf.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print("Updated page_0238.json")

# 2. page_0242.json (12:7)
pf = vol_dir / "page_0242.json"
d = load(pf)
fr = "J'ai quitté ma propre maison ; j'ai abandonné mon héritage : j'ai livré ce que j'avais de plus cher, et ce qui faisait les délices de mon âme, entre les mains de ses ennemis."
for v in d.get("verses") or []:
    if v.get("verse_number") == 7:
        v["french"] = fr
        v["annotations"] = None
        register_cache(fr)
if d.get("commentary"):
    for k in ["latin", "french"]:
        d["commentary"][0].pop(k, None)
pf.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print("Updated page_0242.json")

# 3. page_0244.json (12:10)
pf = vol_dir / "page_0244.json"
d = load(pf)
fr = "Un grand nombre de pasteurs a détruit ma vigne ; ils ont foulé aux pieds le lieu que j'avais pris pour mon partage ; ils ont changé en une affreuse solitude, l'héritage que j'avais choisi, et que j'avais rendu si beau."
for v in d.get("verses") or []:
    if v.get("verse_number") == 10:
        v["french"] = fr
        v["annotations"] = None
        register_cache(fr)
pf.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print("Updated page_0244.json")

# 4. page_0255.json (13:23)
pf = vol_dir / "page_0255.json"
d = load(pf)
fr = "Si un Éthiopien peut changer sa peau, ou un léopard la variété de ses couleurs, vous pourrez aussi faire le bien, vous qui n'avez appris qu'à faire le mal."
for v in d.get("verses") or []:
    if v.get("verse_number") == 23:
        v["french"] = fr
        v["annotations"] = None
        register_cache(fr)
pf.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print("Updated page_0255.json")

# 5. page_0272.json & page_0273.json (15:12)
pf72 = vol_dir / "page_0272.json"
d72 = load(pf72)
d72["verses"] = [v for v in d72.get("verses") or [] if v.get("verse_number") != 12]
pf72.write_text(json.dumps(d72, ensure_ascii=False, indent=2), encoding="utf-8")

pf73 = vol_dir / "page_0273.json"
d73 = load(pf73)
fr = "Le fer peut-il s'allier avec le fer qui vient de l'aquilon, et l'airain avec l'airain ?"
register_cache(fr)
if not any(v.get("verse_number") == 12 for v in d73.get("verses") or []):
    d73["verses"].append({
        "verse_number": 12,
        "chapter": 15,
        "latin": "Numquid fœderabitur ferrum ferro ab aquilone, et æs ?",
        "french": fr,
        "annotations": None
    })
pf73.write_text(json.dumps(d73, ensure_ascii=False, indent=2), encoding="utf-8")
print("Updated page_0272.json & page_0273.json")

# 6. page_0280.json, page_0282.json, page_0283.json (16:2, 16:6, 16:7, 16:8)
pf80 = vol_dir / "page_0280.json"
d80 = load(pf80)
fr2 = "Vous ne prendrez point de femme, et vous n'aurez point de fils, ni de filles en ce lieu."
register_cache(fr2)
if not any(v.get("verse_number") == 2 for v in d80.get("verses") or []):
    d80["verses"].append({
        "verse_number": 2,
        "chapter": 16,
        "latin": "Non accipies uxorem, et non erunt tibi filii et filiæ in loco isto.",
        "french": fr2,
        "annotations": None
    })
    d80["verses"].sort(key=lambda x: (x.get("chapter") or 0, x.get("verse_number") or 0))
pf80.write_text(json.dumps(d80, ensure_ascii=False, indent=2), encoding="utf-8")

pf82 = vol_dir / "page_0282.json"
d82 = load(pf82)
d82["verses"] = [v for v in d82.get("verses") or [] if v.get("verse_number") == 6]
fr6 = "Ils mourront en cette terre grands et petits, ils ne seront ni ensevelis, ni pleurés. On ne se fera point d'incisions sur le corps pour faire leur deuil, et on ne se coupera point les cheveux."
register_cache(fr6)
for v in d82["verses"]:
    v["french"] = fr6
    v["annotations"] = None
pf82.write_text(json.dumps(d82, ensure_ascii=False, indent=2), encoding="utf-8")

pf83 = vol_dir / "page_0283.json"
d83 = load(pf83)
fr7 = "On ne présentera point à manger à celui qui pleure un mort, pour le soulager, et on ne lui donnera point à boire pour le consoler de la mort de son père et de sa mère."
fr8 = "N'entrez point dans une maison de festin pour vous asseoir, et pour manger, et boire avec eux."
register_cache(fr7)
register_cache(fr8)
d83["verses"] = [
    {
        "verse_number": 7,
        "chapter": 16,
        "latin": "Et non frangent inter eos lugenti panem ad consolandum super mortuo, et non dabunt eis potum calicis ad consolandum super patre suo et matre.",
        "french": fr7,
        "annotations": None
    },
    {
        "verse_number": 8,
        "chapter": 16,
        "latin": "Et domum convivii non ingrediaris, ut sedeas cum eis, et comedas, et bibas.",
        "french": fr8,
        "annotations": None
    }
]
pf83.write_text(json.dumps(d83, ensure_ascii=False, indent=2), encoding="utf-8")
print("Updated page_0280.json, page_0282.json, page_0283.json")

# 7. page_0294.json (17:10)
pf = vol_dir / "page_0294.json"
d = load(pf)
fr = "C'est moi qui suis le Seigneur, qui sonde les cœurs, et qui éprouve les reins, qui rends à un chacun selon sa voie, et selon le fruit de ses pensées, et de ses œuvres,"
for v in d.get("verses") or []:
    if v.get("verse_number") == 10:
        v["french"] = fr
        v["annotations"] = None
        register_cache(fr)
pf.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print("Updated page_0294.json")

# 8. page_0296.json (17:13, 17:14)
pf = vol_dir / "page_0296.json"
d = load(pf)
fr13 = "Seigneur, qui êtes l'attente d'Israël ; tous ceux qui vous abandonnent, seront confus : ceux qui s'éloignent de vous, seront écrits sur la terre ; parce qu'ils ont abandonné le Seigneur, qui est la source des eaux vives."
fr14 = "Seigneur, guérissez-moi, et alors je serai guéri ; sauvez-moi, et je serai sauvé : car c'est vous qui êtes ma gloire."
register_cache(fr13)
register_cache(fr14)
for v in d.get("verses") or []:
    if v.get("verse_number") == 13:
        v["french"] = fr13
        v["annotations"] = None
    elif v.get("verse_number") == 14:
        v["french"] = fr14
        v["annotations"] = None
if d.get("commentary"):
    for c in d["commentary"]:
        for k in ["latin", "french"]:
            c.pop(k, None)
pf.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print("Updated page_0296.json")

# 9. page_0300.json & page_0302.json (18:1, 18:2, 18:3)
pf00 = vol_dir / "page_0300.json"
d00 = load(pf00)
if not d00.get("chapter_title"):
    d00["chapter_title"] = "CHAPITRE XVIII."
if not d00.get("chapter_summary"):
    d00["chapter_summary"] = "Comme le potier de terre fait de son argile ce qu'il veut, ainsi le Seigneur disposera de son peuple comme il voudra. Excès des égarements des Juifs. Leur conspiration contre Jérémie. Plaintes de ce Prophète."

fr1 = "Le Seigneur dit à Jérémie :"
fr2 = "Allez, et descendez dans la maison d'un potier ; et là vous entendrez ce que j'ai à vous dire."
fr3 = "J'allai dans la maison d'un potier, et je le trouvai qui travaillait sur sa roue."
register_cache(fr1)
register_cache(fr2)
register_cache(fr3)
d00["verses"] = [
    {
        "verse_number": 1,
        "chapter": 18,
        "latin": "Verbum, quod factum est ad Jeremiam a Domino, dicens :",
        "french": fr1,
        "annotations": None
    },
    {
        "verse_number": 2,
        "chapter": 18,
        "latin": "Surge, et descende in domum figuli, et ibi audies verba mea.",
        "french": fr2,
        "annotations": None
    },
    {
        "verse_number": 3,
        "chapter": 18,
        "latin": "Et descendi in domum figuli, et ecce ipse faciebat opus super rotam.",
        "french": fr3,
        "annotations": None
    }
]
pf00.write_text(json.dumps(d00, ensure_ascii=False, indent=2), encoding="utf-8")

pf02 = vol_dir / "page_0302.json"
d02 = load(pf02)
d02["verses"] = [v for v in d02.get("verses") or [] if v.get("verse_number") not in [2, 3]]
pf02.write_text(json.dumps(d02, ensure_ascii=False, indent=2), encoding="utf-8")
print("Updated page_0300.json & page_0302.json")

# 10. page_0304.json (18:15)
pf = vol_dir / "page_0304.json"
d = load(pf)
fr = "Cependant mon peuple m'a oublié, en faisant de vains sacrifices : ils ont bronché dans leurs voies, en quittant les anciens sentiers, pour marcher par des routes détournées, et par un chemin non frayé."
for v in d.get("verses") or []:
    if v.get("verse_number") == 15:
        v["french"] = fr
        v["annotations"] = None
        register_cache(fr)
if d.get("commentary"):
    for c in d["commentary"]:
        for k in ["latin", "french"]:
            c.pop(k, None)
pf.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print("Updated page_0304.json")

# 11. page_0310.json (19:5)
pf = vol_dir / "page_0310.json"
d = load(pf)
fr = "Et qu'ils ont bâti un temple à Baal, pour brûler leurs enfants dans le feu, et pour les offrir à Baal en holocauste ; ce que je ne leur ai point ordonné, ni ne leur en ai point parlé, et ce qui ne m'est jamais venu dans l'esprit."
for v in d.get("verses") or []:
    if v.get("verse_number") == 5:
        v["french"] = fr
        v["annotations"] = None
        register_cache(fr)
pf.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print("Updated page_0310.json")

# 12. page_0354.json (23:30)
pf = vol_dir / "page_0354.json"
d = load(pf)
fr = "C'est pourquoi je viens aux Prophètes, dit le Seigneur, qui dérobent mes paroles chacun à leurs frères."
for v in d.get("verses") or []:
    if v.get("verse_number") == 30:
        v["french"] = fr
        v["annotations"] = None
        register_cache(fr)
pf.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print("Updated page_0354.json")

# 13. page_0363.json & page_0365.json (25:2)
pf63 = vol_dir / "page_0363.json"
d63 = load(pf63)
fr2 = "Et que le Prophète Jérémie annonça à tout le peuple de Juda, et à tous les habitants de Jérusalem, en disant :"
register_cache(fr2)
if not any(v.get("verse_number") == 2 for v in d63.get("verses") or []):
    d63["verses"].append({
        "verse_number": 2,
        "chapter": 25,
        "latin": "quod locutus est Jeremias propheta ad omnem populum Juda, et ad universos habitatores Jerusalem, dicens :",
        "french": fr2,
        "annotations": None
    })
    d63["verses"].sort(key=lambda x: (x.get("chapter") or 0, x.get("verse_number") or 0))
pf63.write_text(json.dumps(d63, ensure_ascii=False, indent=2), encoding="utf-8")

pf65 = vol_dir / "page_0365.json"
d65 = load(pf65)
d65["verses"] = [v for v in d65.get("verses") or [] if v.get("verse_number") != 2]
pf65.write_text(json.dumps(d65, ensure_ascii=False, indent=2), encoding="utf-8")
print("Updated page_0363.json & page_0365.json")

# 14. page_0375.json & page_0376.json (25:24)
pf75 = vol_dir / "page_0375.json"
d75 = load(pf75)
d75["verses"] = [v for v in d75.get("verses") or [] if v.get("verse_number") != 24]
pf75.write_text(json.dumps(d75, ensure_ascii=False, indent=2), encoding="utf-8")

pf76 = vol_dir / "page_0376.json"
d76 = load(pf76)
fr24 = "A tous les Rois d'Arabie, à tous les Rois d'occident qui habitent dans le désert ;"
register_cache(fr24)
if not any(v.get("verse_number") == 24 for v in d76.get("verses") or []):
    d76["verses"].append({
        "verse_number": 24,
        "chapter": 25,
        "latin": "et cunctis regibus Arabiæ, et cunctis regibus occidentis, qui habitant in deserto :",
        "french": fr24,
        "annotations": None
    })
pf76.write_text(json.dumps(d76, ensure_ascii=False, indent=2), encoding="utf-8")
print("Updated page_0375.json & page_0376.json")

# 15. page_0570.json (46:16)
pf = vol_dir / "page_0570.json"
d = load(pf)
fr = "Ils sont tombés en foule, ils ont été terrassés les uns sur les autres, et ils ont dit : Allons, retournons à notre peuple, et au pays de notre naissance, et fuyons de devant l'épée de la colombe."
for v in d.get("verses") or []:
    if v.get("verse_number") == 16:
        v["french"] = fr
        v["annotations"] = None
        register_cache(fr)
pf.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print("Updated page_0570.json")

# 16. page_0584.json, page_0585.json, page_0587.json (48:1, 48:2)
pf84 = vol_dir / "page_0584.json"
d84 = load(pf84)
fr1 = "Voici ce que le Seigneur des armées, le Dieu d'Israël dit contre Moab : Malheur à Nabo, parce qu'elle a été détruite, et qu'elle est tombée dans la confusion. Cariathaïm a été prise, la ville forte a été couverte de confusion, et pénétrée de frayeur."
register_cache(fr1)
if not any(v.get("verse_number") == 1 and v.get("chapter") == 48 for v in d84.get("verses") or []):
    d84["verses"].append({
        "verse_number": 1,
        "chapter": 48,
        "latin": "Ad Moab : hæc dicit Dominus exercituum, Deus Israël : Væ super Nabo, quoniam vastata est, et confusa : capta est Cariathaïm : confusa est fortis, et tremuit.",
        "french": fr1,
        "annotations": None
    })
pf84.write_text(json.dumps(d84, ensure_ascii=False, indent=2), encoding="utf-8")

pf85 = vol_dir / "page_0585.json"
d85 = load(pf85)
fr2 = "Il n'y a plus de joie dans Moab. Les ennemis ont fait dessein de perdre Hésebon. Venez, ont-ils dit, exterminons-la du nombre des peuples : vous serez donc réduite au silence ; et l'épée vous suivra par-tout."
register_cache(fr2)
if not any(v.get("verse_number") == 2 and v.get("chapter") == 48 for v in d85.get("verses") or []):
    d85["verses"].append({
        "verse_number": 2,
        "chapter": 48,
        "latin": "Non est ultra exsultatio in Moab contra Hesebon : cogitaverunt in malum. Venite, et disperdamus eam de gente. Ergo silens conticesces, sequeturque te gladius.",
        "french": fr2,
        "annotations": None
    })
if d85.get("commentary"):
    for c in d85["commentary"]:
        for k in ["latin", "french"]:
            c.pop(k, None)
pf85.write_text(json.dumps(d85, ensure_ascii=False, indent=2), encoding="utf-8")

pf87 = vol_dir / "page_0587.json"
d87 = load(pf87)
d87["verses"] = [v for v in d87.get("verses") or [] if v.get("verse_number") not in [1, 2]]
pf87.write_text(json.dumps(d87, ensure_ascii=False, indent=2), encoding="utf-8")
print("Updated page_0584.json, page_0585.json, page_0587.json")

# 17. page_0608.json & page_0611.json (49:1)
pf08 = vol_dir / "page_0608.json"
d08 = load(pf08)
if not d08.get("chapter_title"):
    d08["chapter_title"] = "CHAPITRE XLIX."
if not d08.get("chapter_summary"):
    d08["chapter_summary"] = "Prophéties contre les Ammonites, les Iduméens, les Syriens de Damas, les Cédaréniens, les peuples du Royaume d'Asor, et d'Elam."

fr1 = "Voici ce que dit le Seigneur contre les enfants d'Ammon : Israël n'a-t-il point d'enfants, ou n'a-t-il point d'héritiers ? Pourquoi donc Melchom s'est-il emparé de Gad, comme de son héritage ? et pourquoi son peuple a-t-il établi sa demeure dans ses villes ?"
register_cache(fr1)
if not any(v.get("verse_number") == 1 and v.get("chapter") == 49 for v in d08.get("verses") or []):
    d08["verses"].append({
        "verse_number": 1,
        "chapter": 49,
        "latin": "Ad filios Ammon. Hæc dicit Dominus : Numquid non filii sunt Israël, aut hæres non est ei ? Cur igitur hæreditate possedit Melchom, Gad : et populus ejus in urbibus ejus habitavit.",
        "french": fr1,
        "annotations": None
    })
    d08["verses"].sort(key=lambda x: (x.get("chapter") or 0, x.get("verse_number") or 0))
pf08.write_text(json.dumps(d08, ensure_ascii=False, indent=2), encoding="utf-8")

pf11 = vol_dir / "page_0611.json"
d11 = load(pf11)
d11["verses"] = [v for v in d11.get("verses") or [] if not (v.get("verse_number") == 1 and v.get("chapter") == 49)]
pf11.write_text(json.dumps(d11, ensure_ascii=False, indent=2), encoding="utf-8")
print("Updated page_0608.json & page_0611.json")

# 18. page_0672.json (51:45)
pf = vol_dir / "page_0672.json"
d = load(pf)
fr = "Sortez, ô mon peuple, du milieu d'elle, afin que chacun sauve son âme de l'ardente fureur du Seigneur."
for v in d.get("verses") or []:
    if v.get("verse_number") == 45:
        v["french"] = fr
        v["annotations"] = None
        register_cache(fr)
pf.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print("Updated page_0672.json")

# 19. page_0677.json (51:60)
pf = vol_dir / "page_0677.json"
d = load(pf)
fr = "Jérémie avait écrit sur un livre tous les maux qui devaient tomber sur Babylone, tout ce qui avait été écrit contre Babylone."
for v in d.get("verses") or []:
    if v.get("verse_number") == 60:
        v["french"] = fr
        v["annotations"] = None
        register_cache(fr)
pf.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print("Updated page_0677.json")

LLM_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Updated LLM cache with total {len(cache)} entries.")
