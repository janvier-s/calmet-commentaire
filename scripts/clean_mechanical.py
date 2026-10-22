"""Mechanical cleanups for common OCR and formatting artifacts.

1. Spaced letters: "J E S U S", "C H R I S T", "J E S U S - C H R I S T" -> "Jésus", "Christ", "Jésus-Christ"
2. Disentangle lemmata and translations merged into french_commentary when latin_quote is missing.
3. Fix leading footnote calls inside fields.

Usage: python3 clean_mechanical.py [--dry-run] [volume ...]
"""
import json
import re
import sys
from pathlib import Path

from paths import DATA, pages

JC_RE = re.compile(r"J\s+E\s+S\s+U\s+S(?:\s*-\s*|\s+)C\s+H\s+R\s+I\s+S\s+T")
J_RE = re.compile(r"\bJ\s+E\s+S\s+U\s+S\b")
C_RE = re.compile(r"\bC\s+H\s+R\s+I\s+S\s+T\b")

HEADER_PREFIX = re.compile(r"^\s*(?:COMMENTAIRE|ARGUMENT)\s*\.?\s*\n+", re.I)
FORBIDDEN_LEMMAS = {"COMMENTAIRE.", "ARGUMENT.", "PREFACE.", "AVERTISSEMENT.", "DISCOURS."}

# Regex to detect Latin lemmata at start of french_commentary
# e.g., "FILII DAVID, FILII ABRAHAM. Fils de David, fils d'Abraham. L'Evangéliste..."
# or "⁼⁾. 23. ECCE VIRGO IN UTERO HABEBIT, etc. Une Vierge concevra... "
PREFIX_JUNK = re.compile(r"^\s*(?:[⁼⁾ⁱ∗∬\u200b†*℣]\s*\.?\s*|\d+\.\s*)+")
LEMMA_PATTERN = re.compile(
    r"^([A-ZÆŒ\s,;:'’\-]{4,}(?:ETC\.?|etc\.?)?)\.\s+([A-ZÀ-Ÿ][^.\n]+[.:?!])\s+(.+)$",
    re.DOTALL
)


def fix_spaced_letters(s):
    if not s:
        return s
    s = JC_RE.sub("Jésus-Christ", s)
    s = J_RE.sub("Jésus", s)
    s = C_RE.sub("Christ", s)
    return s


def fix_spelling(s):
    if not s or not isinstance(s, str):
        return s
    # 1. Moyse -> Moïse (French fields)
    s = re.sub(r"\bMoyse\b", "Moïse", s)
    # 2. A la lettre -> À la lettre
    s = re.sub(r"\bA\s+la\s+lettre\b", "À la lettre", s)
    # 3. a la lettre -> à la lettre
    s = re.sub(r"\ba\s+la\s+lettre\b", "à la lettre", s)
    # 4. Pseaume(s) -> Psaume(s)
    s = re.sub(r"\bPseaumes\b", "Psaumes", s)
    s = re.sub(r"\bPseaume\b", "Psaume", s)
    s = re.sub(r"\bpseaumes\b", "psaumes", s)
    s = re.sub(r"\bpseaume\b", "psaume", s)
    # 5. Noë -> Noé
    s = re.sub(r"\bNoë\b", "Noé", s)
    # 6. Leading preposition A -> À
    s = re.sub(r"\bA\s+l'égard\b", "À l'égard", s)
    s = re.sub(r"\bA\s+cause\b", "À cause", s)
    s = re.sub(r"\bA\s+peine\b", "À peine", s)
    s = re.sub(r"\bA\s+peu\s+près\b", "À peu près", s)
    s = re.sub(r"\bA\s+moins\b", "À moins", s)
    s = re.sub(r"\bA\s+la\s+naissance\b", "À la naissance", s)
    s = re.sub(r"\ba\s+la\s+naissance\b", "à la naissance", s)

    # 7. corrompuë(s) -> corrompue(s)
    s = re.sub(r"\bcorrompuë(s?)\b", r"corrompue\1", s)
    s = re.sub(r"\bCorrompuë(s?)\b", r"Corrompue\1", s)

    # 8. Loix / loix -> Lois / lois
    s = re.sub(r"\bLoix\b", "Lois", s)
    s = re.sub(r"\bloix\b", "lois", s)

    # 9. foux -> fous
    s = re.sub(r"\bfoux\b", "fous", s)
    s = re.sub(r"\bFoux\b", "Fous", s)

    # 10. rouë(s) -> roue(s)
    s = re.sub(r"\brouë(s?)\b", r"roue\1", s)
    s = re.sub(r"\bRouë(s?)\b", r"Roue\1", s)

    # 11. foye(s) -> foie(s)
    s = re.sub(r"\bfoye(s?)\b", r"foie\1", s)
    s = re.sub(r"\bFoye(s?)\b", r"Foie\1", s)

    # 12. possede / possedent -> possède / possèdent
    s = re.sub(r"\bpossede\b", "possède", s)
    s = re.sub(r"\bpossedent\b", "possèdent", s)
    s = re.sub(r"\bPossede\b", "Possède", s)
    s = re.sub(r"\bPossedent\b", "Possèdent", s)

    # 13. deüil(s) -> deuil(s)
    s = re.sub(r"\bdeüil(s?)\b", r"deuil\1", s)
    s = re.sub(r"\bDeüil(s?)\b", r"Deuil\1", s)

    # 14. sévrait / sévraient / sévrer -> sevrait / sevraient / sevrer
    s = re.sub(r"\bsévrait\b", "sevrait", s)
    s = re.sub(r"\bsévraient\b", "sevraient", s)
    s = re.sub(r"\bsévrer\b", "sevrer", s)

    # 15. obséques -> obsèques
    s = re.sub(r"\bobséques\b", "obsèques", s)
    s = re.sub(r"\bObséques\b", "Obsèques", s)

    # 16. haye(s) -> haie(s) [lowercase only, preserving 'de la Haye', 'La Haye']
    s = re.sub(r"\bhaye\b", "haie", s)
    s = re.sub(r"\bhayes\b", "haies", s)

    # 17. ruës / ruë -> rues / rue
    s = re.sub(r"\bruës\b", "rues", s)
    s = re.sub(r"\bruë\b", "rue", s)
    s = re.sub(r"\bRuës\b", "Rues", s)
    s = re.sub(r"\bRuë\b", "Rue", s)

    # 18. péchez (noun) -> péchés
    s = re.sub(
        r"\b(de|d\'|des|les|ses|mes|tes|nos|vos|leurs|ces|quelques|plusieurs|grands|petits|autres|anciens|nouveaux|premiers|moindres|propres|certains|mille|sans|pour)\s+péchez\b",
        r"\1 péchés",
        s,
        flags=re.I,
    )
    s = re.sub(
        r"\bpéchez\s+(sur\s+péchez|en\s+péchez|spirituels|véniels|d\'ignorance)\b",
        lambda m: "péchés " + m.group(1).replace("péchez", "péchés"),
        s,
    )

    # 19. entraînez (participle) -> entraînés
    s = re.sub(r"\b(ou|a|ont|avaient|étaient|sont|furent|seront|aye|ayant|avez|ai)\s+entraînez\b", r"\1 entraînés", s)
    s = re.sub(r"\bentraînez\s+(par|en\s+captivité|les\s+chaînes)\b", r"entraînés \1", s)

    # 20. fortifiez (participle) -> fortifiés
    s = re.sub(r"\b(sont|étaient|s\'étaient|se\s+sont|lieux)\s+fortifiez\b", r"\1 fortifiés", s)

    # 21. laissez (participle) -> laissés
    s = re.sub(r"\b(ont|avaient|étaient|sont|furent|auront|saient|s\'étaient|se\s+sont|été|habits)\s+laissez\b", r"\1 laissés", s)
    s = re.sub(r"\b(nous\s+a|vous\s+a|l\'a)\s+laissez\b", r"\1 laissés", s)

    # 22. traitez (participle / noun) -> traités
    s = re.sub(r"\b(les|vos|des)\s+traitez\b", r"\1 traités", s)
    s = re.sub(
        r"\b(sont|seront|étaient|furent|ont\s+été|avaient|ont|a|ai|aye|aurai|soient|soyons|serons|être|d\'être|mieux|bien)\s+(?:infailliblement\s+|indignement\s+|assez\s+doucement\s+|cruellement\s+|durement\s+|fort\s+bien\s+|mieux\s+|bien\s+)?traitez\b",
        lambda m: m.group(0).replace("traitez", "traités"),
        s,
    )
    s = re.sub(r"\b(méchants|impies|esclaves)\s+traitez\b", r"\1 traités", s)

    # 23. jouës / jouë -> joues / joue
    s = re.sub(r"\b([Jj])ouë", r"\1oue", s)

    # 24. coù / coû -> cou
    s = re.sub(r"\bco[ùû]\b", "cou", s)
    s = re.sub(r"\bCo[ùû]\b", "Cou", s)
    s = re.sub(r"\bco[ùû]-tume\b", "coutume", s)

    # 25. yvoire(s) -> ivoire(s)
    s = re.sub(r"\byvoire(s?)\b", r"ivoire\1", s)
    s = re.sub(r"\bYvoire(s?)\b", r"Ivoire\1", s)

    # 26. particuliérement -> particulièrement
    s = re.sub(r"\bparticuliérement\b", "particulièrement", s)
    s = re.sub(r"\bParticuliérement\b", "Particulièrement", s)

    # 27. Epouse(s) -> Épouse(s)
    s = re.sub(r"\bEpouse(s?)\b", r"Épouse\1", s)

    # 28. Epoux -> Époux
    s = re.sub(r"\bEpoux\b", "Époux", s)

    # 29. Eglise(s) -> Église(s)
    s = re.sub(r"\bEglise(s?)\b", r"Église\1", s)

    # 30. sçû / sçu -> su
    s = re.sub(r"\bsç[ûu]\b", "su", s)
    s = re.sub(r"\bSç[ûu]\b", "Su", s)
    s = re.sub(r"\bsç[ûu]ë\b", "sue", s)

    # 31. enflammez -> enflammés
    s = re.sub(r"\benflammez\b", "enflammés", s)
    s = re.sub(r"\bEnflammez\b", "Enflammés", s)

    # 32. Doćtrine / ćt -> Doctrine / ct
    s = re.sub(r"\bDoćtrine(s?)\b", r"Doctrine\1", s)
    s = re.sub(r"\bdoćtrine(s?)\b", r"doctrine\1", s)
    s = s.replace("ćt", "ct").replace("Ćt", "Ct")

    # 33. mammelle(s) -> mamelle(s)
    s = re.sub(r"\b([Mm])ammelle(s?)\b", r"\1amelle\2", s)

    # 34. Ecriture(s) -> Écriture(s)
    s = re.sub(r"\bEcriture(s?)\b", r"Écriture\1", s)

    # 35. Evangile(s), Evangiliste(s) -> Évangile(s), Évangéliste(s)
    s = re.sub(r"\bEvangile(s?)\b", r"Évangile\1", s)
    s = re.sub(r"\bEvangiliste(s?)\b", r"Évangéliste\1", s)

    # 36. Egypte, Egyptien(s), Egyptienne(s) -> Égypte, Égyptien(s), Égyptienne(s)
    s = re.sub(r"\bEgypte\b", "Égypte", s)
    s = re.sub(r"\bEgyptien(s?)\b", r"Égyptien\1", s)
    s = re.sub(r"\bEgyptienne(s?)\b", r"Égyptienne\1", s)

    # 37. nôce(s) -> noce(s)
    s = re.sub(r"\b([Nn])ôce(s?)\b", r"\1oce\2", s)

    # 38. éleve / élevent -> élève / élèvent
    s = re.sub(r"\b([Éé])leve\b", r"\1lève", s)
    s = re.sub(r"\b([Éé])levent\b", r"\1lèvent", s)

    # 39. societé(s) -> société(s)
    s = re.sub(r"\b([Ss])ocieté(s?)\b", r"\1ociété\2", s)

    # 40. ajoût* -> ajout*
    s = re.sub(r"\b([Aa])joût", r"\1jout", s)

    # 41. colomne(s) -> colonne(s)
    s = re.sub(r"\b([Cc])olomne(s?)\b", r"\1olonne\2", s)

    # 42. fidelle(s), infidelle(s) -> fidèle(s), infidèle(s)
    s = re.sub(r"\b([Ff])idelle(s?)\b", r"\1idèle\2", s)
    s = re.sub(r"\b([Ii]n[Ff])idelle(s?)\b", r"\1idèle\2", s)

    # 43. régle(s) -> règle(s)
    s = re.sub(r"\b([Rr])égle(s?)\b", r"\1ègle\2", s)

    # 44. chevreüil(s) -> chevreuil(s)
    s = re.sub(r"\b([Cc])hevreüil(s?)\b", r"\1hevreuil\2", s)

    # 45. printems -> printemps
    s = re.sub(r"\b([Pp])rintems\b", r"\1rintemps", s)

    # 46. bonne-chere -> bonne chère
    s = re.sub(r"\bbonne-chere\b", "bonne chère", s)

    # 47. misere(s) -> misère(s)
    s = re.sub(r"\b([Mm])isere(s?)\b", r"\1isère\2", s)

    # 48. maniere(s) -> manière(s)
    s = re.sub(r"\b([Mm])aniere(s?)\b", r"\1anière\2", s)

    # 49. lumiere(s) -> lumière(s)
    s = re.sub(r"\b([Ll])umiere(s?)\b", r"\1umière\2", s)

    # 50. premiere(s) -> première(s)
    s = re.sub(r"\b([Pp])remiere(s?)\b", r"\1remière\2", s)

    # 51. derniere(s) -> dernière(s)
    s = re.sub(r"\b([Dd])erniere(s?)\b", r"\1ernière\2", s)

    # 52. colere(s) -> colère(s)
    s = re.sub(r"\b([Cc])olere(s?)\b", r"\1olère\2", s)

    # 53. priere(s) -> prière(s)
    s = re.sub(r"\b([Pp])riere(s?)\b", r"\1rière\2", s)

    # 54. matiere(s) -> matière(s)
    s = re.sub(r"\b([Mm])atiere(s?)\b", r"\1atière\2", s)

    # 55. remede(s) -> remède(s)
    s = re.sub(r"\b([Rr])emede(s?)\b", r"\1emède\2", s)

    # 56. mystere(s) -> mystère(s), mystérieux
    s = re.sub(r"(?<![A-Za-zÀ-ÿ])([Mm])yst[eé]re(s?)(?![A-Za-zÀ-ÿ])", r"\1ystère\2", s)
    s = re.sub(r"(?<![A-Za-zÀ-ÿ])([Mm])ysterieux\b", r"\1ystérieux", s)
    s = re.sub(r"(?<![A-Za-zÀ-ÿ])([Mm])ysterieuse(s?)\b", r"\1ystérieuse\2", s)
    s = re.sub(r"(?<![A-Za-zÀ-ÿ])([Mm])ysterieusement\b", r"\1ystérieusement", s)

    # 57. statuë(s) -> statue(s)
    s = re.sub(r"\b([Ss])tatuë(s?)\b", r"\1tatue\2", s)

    # 58. bouë(s) -> boue(s)
    s = re.sub(r"\b([Bb])ouë(s?)\b", r"\1oue\2", s)

    # 59. excez -> excès
    s = re.sub(r"\b([Ee])xcez\b", r"\1xcès", s)

    # 60. Ezéchias -> Ézéchias
    s = re.sub(r"\bEzéchias\b", "Ézéchias", s)

    # 61. Elie -> Élie
    s = re.sub(r"\bElie\b", "Élie", s)

    # 62. Elisée -> Élisée
    s = re.sub(r"\bElisée\b", "Élisée", s)

    # 63. Hebreux -> Hébreux (French form)
    s = re.sub(r"\bHebreux\b", "Hébreux", s)

    # 64. Edit(s) -> Édit(s)
    s = re.sub(r"\bEdit(s?)\b", r"Édit\1", s)

    # 65. Elûs -> Élus
    s = re.sub(r"\bElûs\b", "Élus", s)

    # 66. ECCLESIASTIQUE -> ECCLÉSIASTIQUE
    s = re.sub(r"\bECCLESIASTIQUE\b", "ECCLÉSIASTIQUE", s)

    # 67. verité(s) -> vérité(s)
    s = re.sub(r"\b([Vv])erité(s?)\b", r"\1érité\2", s)

    # 68. impieté(s) -> impiété(s)
    s = re.sub(r"\b([Ii])mpieté(s?)\b", r"\1mpiété\2", s)

    # 69. posterité(s) -> postérité(s)
    s = re.sub(r"\b([Pp])osterité(s?)\b", r"\1ostérité\2", s)

    # 70. adultere(s) -> adultère(s)
    s = re.sub(r"\b([Aa])dultere(s?)\b", r"\1dultère\2", s)

    # 71. Ephraïm -> Éphraïm
    s = re.sub(r"\bEphraïm\b", "Éphraïm", s)

    # 72. Ezéchiel -> Ézéchiel
    s = re.sub(r"\bEzéchiel\b", "Ézéchiel", s)

    # 73. Ethiopie, Ethiopien(s), Ethiopienne(s) -> Éthiopie, Éthiopien(s), Éthiopienne(s)
    s = re.sub(r"\bEthiopie\b", "Éthiopie", s)
    s = re.sub(r"\bEthiopien(s?)\b", r"Éthiopien\1", s)
    s = re.sub(r"\bEthiopienne(s?)\b", r"Éthiopienne\1", s)

    # 74. Eliacim -> Éliacim
    s = re.sub(r"\bEliacim\b", "Éliacim", s)

    # 75. ISAIE -> ISAÏE (in headings)
    s = re.sub(r"\bISAIE\b", "ISAÏE", s)

    # 76. entiérement -> entièrement
    s = re.sub(r"\b([Ee])ntiérement\b", r"\1ntièrement", s)

    # 77. aîle(s) -> aile(s)
    s = re.sub(r"\b([Aa])île(s?)\b", r"\1ile\2", s)

    # 78. élevera / éleveront -> élèvera / élèveront
    s = re.sub(r"\b([Éé])levera\b", r"\1lèvera", s)
    s = re.sub(r"\b([Éé])leveront\b", r"\1lèveront", s)

    # 79. rejetté(e)(s) -> rejeté(e)(s)
    s = re.sub(r"\b([Rr])ejetté(e?s?)\b", r"\1ejeté\2", s)

    # 80. Tremas on mute e / archaic feminines
    s = re.sub(r"\b([Dd])evenuë(s?)\b", r"\1evenue\2", s)
    s = re.sub(r"\b([Ii])nconnuë(s?)\b", r"\1nconnue\2", s)
    s = re.sub(r"\b([Nn])uë(s?)\b", r"\1ue\2", s)
    s = re.sub(r"\b([Ll])ieuë(s?)\b", r"\1ieue\2", s)
    s = re.sub(r"\b([Vv])uë(s?)\b", r"\1ue\2", s)
    s = re.sub(r"\b([Aa])battuë(s?)\b", r"\1battue\2", s)
    s = re.sub(r"\b([Rr])enduë(s?)\b", r"\1endue\2", s)
    s = re.sub(r"\b([Cc])onfonduë(s?)\b", r"\1onfondue\2", s)
    s = re.sub(r"\b([Ee])ntenduë(s?)\b", r"\1ntendue\2", s)
    s = re.sub(r"\b([Tt])enuë(s?)\b", r"\1enue\2", s)
    s = re.sub(r"\b([Vv])êtuë(s?)\b", r"\1êtue\2", s)
    s = re.sub(r"\b([Ee])uë(s?)\b", r"\1ue\2", s)
    s = re.sub(r"\b([Ff])enduë(s?)\b", r"\1endue\2", s)
    s = re.sub(r"\b([Bb])attuë(s?)\b", r"\1attue\2", s)
    s = re.sub(r"\b([Aa])pperçuë(s?)\b", r"\1perçue\2", s)
    s = re.sub(r"\b([Rr])é?panduë(s?)\b", r"\1épandue\2", s)
    s = re.sub(r"\b([Ff])eüille(s?)\b", r"\1euille\2", s)
    s = re.sub(r"\b([Ff])eüillage(s?)\b", r"\1euillage\2", s)
    s = re.sub(r"\b([Oo])rguëil\b", r"\1rgueil", s)
    s = re.sub(r"\b([Qq])ueuë(s?)\b", r"\1ueue\2", s)
    s = re.sub(r"\b([Pp])oële(s?)\b", r"\1oêle\2", s)
    s = re.sub(r"\b([Ii])nsinuë\b", r"\1nsinue", s)
    s = re.sub(r"\b([Cc])ontinuënt\b", r"\1ontinuent", s)
    s = re.sub(r"\b([Dd])iminuënt\b", r"\1iminuent", s)
    s = re.sub(r"\b([Rr])éüssi([a-z]*)\b", r"\1éussi\2", s)
    s = re.sub(r"\b([Vv])eüille(s?)\b", r"\1euille\2", s)

    # 81. ménace(s), ménacer, etc. -> menace(s), menacer
    s = re.sub(r"\b([Mm])énace(s?)\b", r"\1enace\2", s)
    s = re.sub(r"\b([Mm])énacé(e?s?)\b", r"\1enacé\2", s)
    s = re.sub(r"\b([Mm])énacer([a-zà-ÿ]*)\b", r"\1enacer\2", s)

    # 82. Prophête(s) -> Prophète(s)
    s = re.sub(r"\b([Pp])rophête(s?)\b", r"\1rophète\2", s)

    # 83. regna, etc. -> régna, etc.
    s = re.sub(r"\b([Rr])egna\b", r"\1égna", s)
    s = re.sub(r"\b([Rr])egnait\b", r"\1égnait", s)
    s = re.sub(r"\b([Rr])egnaient\b", r"\1égnaient", s)
    s = re.sub(r"\b([Rr])egnera\b", r"\1égnera", s)
    s = re.sub(r"\b([Rr])egnérent\b", r"\1égnèrent", s)

    # 84. brébis -> brebis
    s = re.sub(r"\b([Bb])rébis\b", r"\1rebis", s)

    # 85. premiérement -> premièrement
    s = re.sub(r"\b([Pp])remiérement\b", r"\1remièrement", s)

    # 86. auprés -> auprès
    s = re.sub(r"\b([Aa])uprés\b", r"\1uprès", s)

    # 87. plutot -> plutôt
    s = re.sub(r"\b([Pp])lutot\b", r"\1lutôt", s)

    # 88. prédecesseur(s) -> prédécesseur(s)
    s = re.sub(r"\b([Pp])rédecesseur(s?)\b", r"\1rédécesseur\2", s)

    # 89. soûmis -> soumis, soûtiennent -> soutiennent
    s = re.sub(r"\b([Ss])oûmi(s|se|ses)\b", r"\1oumi\2", s)
    s = re.sub(r"\b([Ss])oûtien(s|t|nent)\b", r"\1outien\2", s)

    # 90. jetté, jetta, etc. -> jeté, jeta, etc.
    s = re.sub(r"\b([Jj])etté(e?s?)\b", r"\1eté\2", s)
    s = re.sub(r"\b([Jj])etta\b", r"\1eta", s)
    s = re.sub(r"\b([Jj])ettait\b", r"\1etait", s)
    s = re.sub(r"\b([Jj])ettaient\b", r"\1etaient", s)
    s = re.sub(r"\b([Jj])ettant\b", r"\1etant", s)
    s = re.sub(r"\b([Jj])ettérent\b", r"\1etèrent", s)

    # 91. rejetton(s), etc. -> rejeton(s), etc.
    s = re.sub(r"\b([Rr])ejetton(s?)\b", r"\1ejeton\2", s)
    s = re.sub(r"\b([Rr])ejetta\b", r"\1ejeta", s)
    s = re.sub(r"\b([Rr])ejettant\b", r"\1ejetant", s)
    s = re.sub(r"\b([Rr])ejettérent\b", r"\1ejetèrent", s)

    # 92. auxquels
    s = re.sub(r"\b([Aa])usquels\b", r"\1uxquels", s)

    # 93. cachetté -> cacheté
    s = re.sub(r"\b([Cc])achetté(e?s?)\b", r"\1acheté\2", s)

    # 94. cuirrasse -> cuirasse
    s = re.sub(r"\b([Cc])uirrasse(s?)\b", r"\1uirasse\2", s)

    # 95. allarme -> alarme
    s = re.sub(r"\b([Aa])llarme(s?)\b", r"\1larme\2", s)

    # 96. courier -> courrier
    s = re.sub(r"\b([Cc])ourier(s?)\b", r"\1ourrier\2", s)

    # 97. rappeller -> rappeler
    s = re.sub(r"\b([Rr])appeller\b", r"\1appeler", s)

    # 98. retraitte -> retraite
    s = re.sub(r"\b([Rr])etraitte(s?)\b", r"\1etraite\2", s)

    # 99. vuide -> vide
    s = re.sub(r"\b([Vv])uide(s?)\b", r"\1ide\2", s)

    # 100. asne -> âne
    s = re.sub(r"\bAsne(s?)\b", r"Âne\1", s)
    s = re.sub(r"\basne(s?)\b", r"âne\1", s)

    # 101. Ecoutez -> Écoutez
    s = re.sub(r"\bEcoutez\b", "Écoutez", s)

    # 102. Etat / Etats -> État / États
    s = re.sub(r"\bEtat(s?)\b", r"État\1", s)

    # 103. Edition(s) -> Édition(s)
    s = re.sub(r"\bEdition(s?)\b", r"Édition\1", s)

    # 104. Ecrit(s) -> Écrit(s)
    s = re.sub(r"\bEcrit(s?)\b", r"Écrit\1", s)

    # 105. Ecrivez -> Écrivez
    s = re.sub(r"\bEcrivez\b", "Écrivez", s)

    # 106. Elevez -> Élevez
    s = re.sub(r"\bElevez\b", "Élevez", s)

    # 107. Epiphane(s) -> Épiphane(s)
    s = re.sub(r"\bEpiphane(s?)\b", r"Épiphane\1", s)

    # 108. Secretaire(s) -> Secrétaire(s)
    s = re.sub(r"\b([Ss])ecretaire(s?)\b", r"\1ecrétaire\2", s)

    # 109. OCR long-s artifacts (f -> s)
    s = re.sub(r"\b([Cc])irconcifion(s?)\b", r"\1irconcision\2", s)
    s = re.sub(r"\b([Ii])ncirconcife(s?)\b", r"\1ncirconcise\2", s)
    s = re.sub(r"\b([Ee])nfeveli(s|r|rent)\b", r"\1nseveli\2", s)
    s = re.sub(r"\b([Pp])rophétif([a-zà-ÿ]+)\b", r"\1rophétis\2", s)
    s = re.sub(r"\b([Cc])onfume(z?|nt)?\b", r"\1onsume\2", s)
    s = re.sub(r"\b([Ii])nfinue([a-zà-ÿ]*)\b", r"\1nsinue\2", s)
    s = re.sub(r"\b([Ff])ignifie\b", "signifie", s)
    s = re.sub(r"\b([Bb])ienféance(s?)\b", r"\1ienséance\2", s)
    s = re.sub(r"\b([Cc])onfidér([a-zà-ÿ]+)\b", r"\1onsidér\2", s)
    s = re.sub(r"\b([Ff])errurier(s?)\b", r"serrurier\2", s)
    s = re.sub(r"\b([Ff])upplice(s?)\b", r"supplice\2", s)
    s = re.sub(r"\b([Mm])enfonge(s?)\b", r"\1ensonge\2", s)
    s = re.sub(r"\b([Tt])réfors\b", r"\1résors", s)
    s = re.sub(r"\b([Ff])ourdent\b", "sourdent", s)
    s = re.sub(r"\b([Aa])bufe(z|r|nt|s)?\b", r"\1buse\2", s)
    s = re.sub(r"\b([Aa])bufé(e?s?)\b", r"\1busé\2", s)
    s = re.sub(r"\b([Aa])ccroiffement(s?)\b", r"\1ccroissement\2", s)

    # 110. Past historic 3rd pl: -érent -> -èrent
    s = re.sub(r"\b([Ee])mmenérent\b", r"\1mmenèrent", s)
    s = re.sub(r"\b([Ee])ntrérent\b", r"\1ntrèrent", s)
    s = re.sub(r"\b([Ss])auvérent\b", r"\1auvèrent", s)
    return s


def clean_page(d):
    changed = False

    # Top-level string fields
    for k in (
        "book_title",
        "chapter_title",
        "chapter_intro",
        "chapter_summary",
        "chapter_argument",
        "chapter_preface",
    ):
        v = d.get(k)
        if v and isinstance(v, str):
            v2 = fix_spelling(v)
            if v2 != v:
                d[k] = v2
                changed = True

    # Verses
    for v in d.get("verses", []):
        s = v.get("french")
        if s and isinstance(s, str):
            s2 = fix_spelling(s)
            if s2 != s:
                v["french"] = s2
                changed = True

    # Footnotes
    for fn in d.get("footnotes", []):
        t = fn.get("text")
        if t and isinstance(t, str):
            t2 = fix_spelling(t)
            if t2 != t:
                fn["text"] = t2
                changed = True

    for c in d.get("commentary", []):
        # 1. Spaced letters and spelling
        for k in ("french_translation", "french_commentary"):
            s = c.get(k)
            if s:
                s2 = fix_spaced_letters(s)
                s2 = fix_spelling(s2)
                if s2 != s:
                    c[k] = s2
                    changed = True

        # Strip OCR headers like "COMMENTAIRE.\n" or "ARGUMENT.\n"
        fc = c.get("french_commentary")
        if fc:
            fc_clean = HEADER_PREFIX.sub("", fc)
            if fc_clean != fc:
                c["french_commentary"] = fc_clean
                changed = True

        # 2. Extract missing lemma/translation if merged into french_commentary
        # Note: block 1 legitimately continues the note from previous page without a lemma
        if c.get("commentary_id") != 1 and not c.get("latin_quote") and c.get("french_commentary"):
            raw_fc = c["french_commentary"].strip()
            # Strip junk prefixes like "⁼⁾. 23." or "ⁱ. 12."
            stripped = PREFIX_JUNK.sub("", raw_fc).strip()
            m = LEMMA_PATTERN.match(stripped)
            if m:
                cand_lemma, cand_trans, rest_comm = m.group(1).strip() + ".", m.group(2).strip(), m.group(3).strip()
                if cand_lemma not in FORBIDDEN_LEMMAS and len(cand_lemma) >= 5 and re.search(r"[A-Z]{3,}", cand_lemma):
                    c["latin_quote"] = cand_lemma
                    if not c.get("french_translation"):
                        c["french_translation"] = cand_trans
                    c["french_commentary"] = rest_comm
                    changed = True

        # 3. Leading call in latin_quote or french_commentary
        fc = c.get("french_commentary")
        if fc:
            m = re.match(r"^\s*(\^\{[^}]+\})\s*", fc)
            if m:
                # If french_translation exists, move it to end of french_translation
                call_str = m.group(1)
                c["french_commentary"] = fc[m.end():]
                tr = c.get("french_translation")
                if tr and call_str not in tr:
                    c["french_translation"] = tr.rstrip() + " " + call_str
                changed = True

    return changed


def main(argv):
    dry = "--dry-run" in argv
    vols = [a for a in argv if not a.startswith("--")] or sorted(
        p.name for p in DATA.iterdir() if (p / "normalized").is_dir()
    )

    total_changed = 0
    for vol in vols:
        vol_changed = 0
        for p in pages(vol):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if clean_page(d):
                vol_changed += 1
                if not dry:
                    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        total_changed += vol_changed
        print(f"{vol}: {vol_changed} pages updated{' (dry run)' if dry else ''}")

    print(f"Total: {total_changed} pages updated")


if __name__ == "__main__":
    main(sys.argv[1:])
