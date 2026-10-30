"""Mechanical cleanups for common OCR and formatting artifacts.

1. Spaced letters: "J E S U S", "C H R I S T", "J E S U S - C H R I S T" -> "Jésus", "Christ", "Jésus-Christ"
2. Disentangle lemmata and translations merged into french_commentary when latin_quote is missing.
3. Fix leading footnote calls inside fields.

Usage: python3 clean_mechanical.py [--dry-run] [volume ...]
"""
import difflib
import json
import re
import re._constants as _c
import re._parser as _parser
import sys
import unicodedata
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
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


@lru_cache(maxsize=None)
def _rx(pattern, flags=0):
    return re.compile(pattern, flags)


def _literal(pattern, flags=0):
    """The longest run of plain characters every match of pattern contains ("" if none)."""
    parsed = _parser.parse(pattern, flags)
    if parsed.state.flags & re.I:                          # flags=re.I or an inline (?i)
        return ""
    best, run = "", []

    def walk(items):
        nonlocal best, run
        for op, av in items:
            if op is _c.LITERAL:
                run.append(chr(av))
                continue
            if op in (_c.AT, _c.ASSERT, _c.ASSERT_NOT):
                continue                                   # zero-width: the text around it is adjacent
            if op is _c.SUBPATTERN and not av[1] & _c.SRE_FLAG_IGNORECASE:
                walk(av[3])                                # a plain group is just more sequence
                continue
            if len(run) > len(best):
                best = "".join(run)
            run = []

    walk(parsed)
    return max(best, "".join(run), key=len)


@lru_cache(maxsize=None)
def _rule(pattern, flags=0):
    return _rx(pattern, flags), _literal(pattern, flags)


def _sub(pattern, repl, s, flags=0):
    # fix_spelling has more patterns than re's internal cache (512) holds, so plain
    # re.sub would recompile every one of them on every call. Most rules are one word
    # that cleaned text no longer has; a substring test skips those without the regex.
    rx, lit = _rule(pattern, flags)
    if lit and lit not in s:
        return s
    return rx.sub(repl, s)


def _word_table():
    """spelling_words.txt as {old: modern}, with a capitalized entry for each lower-case one."""
    table = {}
    for line in (Path(__file__).parent / "spelling_words.txt").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            old, new = line.split()
            table[old] = new
            table.setdefault(old[:1].upper() + old[1:], new[:1].upper() + new[1:])
    return table


WORD_TABLE = _word_table()
TABLE_WORD = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿœŒæÆ]+")


# Text the French rules must leave as printed:
#   * a page that opens mid-word starts its first verse or commentary block with the second half
#     of a word broken on the page before ("vaient" of "de-vaient", "lâtrie" of "ido-lâtrie");
#     read as a word of its own, a rule rewrites it (voient, latrie);
#   * a field that ends in a hyphen ends with the first half of a word finished overleaf
#     ("vallée forti-", not "sorti-");
#   * Latin quoted in italics (`_Consultatorem Dei fortis._`), where `fortis` is no misread
#     `sortis`. A span counts as Latin when at least two of its words are (LATIN_WORD).
FRAGMENT = re.compile(r"[a-zà-öø-ÿœæ][^\s.,;:!?«»()]*")
TOKEN = re.compile(r"[^\s.,;:!?«»()]*")
TRAILING = re.compile(r"\S+-\s*$")
ITALIC = re.compile(r"_[^_\n]+_")
LATIN_WORD = re.compile(
    r"(?i)(?<![\wÀ-ÿ])(?:ad|apud|contra|cum|super|quod|quae|eum|ejus|eius|dei|domini|dominus|deus|"
    r"sunt|esse|ut|ex|per|sicut|enim|autem|vel|nec|quia|meus|mea|tuus|hoc|quoniam|atque|ego|"
    r"eos|eorum|illorum|populus|populi|populum|anni|annos|annis|quinque|"
    r"\w+(?:orum|arum|ibus|untur|tur|unt|orem|ionem|itatem|avit|ivit|erunt|abit|ebit|ibit))"
    r"(?![\wÀ-ÿ])")
HOLD = 0xE000   # private-use characters no rule matches, one per held Latin span


def keep_printed(fn, s, lead=False):
    """fn(s) (fn returns the new text), with the text above left as printed; `lead` when the
    field may open with the end of a word broken on the page before.

    Latin spans are held out by placeholders. The fragments at either end are put back after
    the rules ran on the whole text, so the words around them keep their context."""
    if not isinstance(s, str) or not s:
        return fn(s)
    spans = []

    def hold(m):
        if len(LATIN_WORD.findall(m.group())) < 2:
            return m.group()
        spans.append(m.group())
        return chr(HOLD + len(spans) - 1)
    held = ITALIC.sub(hold, s) if "_" in s else s
    out = fn(held)
    for k, span in enumerate(spans):
        if out.count(chr(HOLD + k)) != 1:
            return s                      # a rule moved a placeholder: change nothing
        out = out.replace(chr(HOLD + k), span)
    first = FRAGMENT.match(s) if lead else None
    if first:
        out = first.group() + out[TOKEN.match(out).end():]
    last = TRAILING.search(s)
    if last:
        now = TRAILING.search(out)
        if now and now.group() != last.group():
            out = out[:now.start()] + last.group()
    return in_latin_as_printed(s, out) if out != s else out


WORD = re.compile(r"[\wÀ-ÿœæŒÆ']+|[^\wÀ-ÿœæŒÆ']+")


def in_latin_as_printed(before, after):
    """Put back any word the rules changed among Latin quoted without italics
    (`super Jerusalem, etc. Stilla ad`): at least two Latin words within three on either side."""
    a, b = WORD.findall(before), WORD.findall(after)
    words = [i for i, t in enumerate(a) if t[0].isalnum() or t[0] in "À-ÿ"]
    latin = {i for i in words if LATIN_WORD.fullmatch(a[i])}
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "replace" and i2 - i1 == j2 - j1 == 1:
            k = words.index(i1) if i1 in words else None
            near = words[max(0, k - 3):k] + words[k + 1:k + 4] if k is not None else []
            if sum(1 for i in near if i in latin) >= 2:
                out.extend(a[i1:i2])
                continue
        out.extend(b[j1:j2])
    return "".join(out)


def fix_spelling(s):
    if not s or not isinstance(s, str):
        return s
    # 1. Moyse -> Moïse (French fields)
    s = _sub(r"\bMoyse\b", "Moïse", s)
    # 2. A la lettre -> À la lettre
    s = _sub(r"\bA\s+la\s+lettre\b", "À la lettre", s)
    # 3. a la lettre -> à la lettre
    s = _sub(r"\ba\s+la\s+lettre\b", "à la lettre", s)
    # 4. Pseaume(s) -> Psaume(s)
    s = _sub(r"\bPseaumes\b", "Psaumes", s)
    s = _sub(r"\bPseaume\b", "Psaume", s)
    s = _sub(r"\bpseaumes\b", "psaumes", s)
    s = _sub(r"\bpseaume\b", "psaume", s)
    # 5. Noë -> Noé
    s = _sub(r"\bNoë\b", "Noé", s)
    # 6. Leading preposition A -> À
    s = _sub(r"\bA\s+l'égard\b", "À l'égard", s)
    s = _sub(r"\bA\s+cause\b", "À cause", s)
    s = _sub(r"\bA\s+peine\b", "À peine", s)
    s = _sub(r"\bA\s+peu\s+près\b", "À peu près", s)
    s = _sub(r"\bA\s+moins\b", "À moins", s)
    s = _sub(r"\bA\s+la\s+naissance\b", "À la naissance", s)
    s = _sub(r"\ba\s+la\s+naissance\b", "à la naissance", s)

    # 7. corrompuë(s) -> corrompue(s)
    s = _sub(r"\bcorrompuë(s?)\b", r"corrompue\1", s)
    s = _sub(r"\bCorrompuë(s?)\b", r"Corrompue\1", s)

    # 8. Loix / loix -> Lois / lois
    s = _sub(r"\bLoix\b", "Lois", s)
    s = _sub(r"\bloix\b", "lois", s)

    # 9. foux -> fous
    s = _sub(r"\bfoux\b", "fous", s)
    s = _sub(r"\bFoux\b", "Fous", s)

    # 10. rouë(s) -> roue(s)
    s = _sub(r"\brouë(s?)\b", r"roue\1", s)
    s = _sub(r"\bRouë(s?)\b", r"Roue\1", s)

    # 11. foye(s) -> foie(s)
    s = _sub(r"\bfoye(s?)\b", r"foie\1", s)
    s = _sub(r"\bFoye(s?)\b", r"Foie\1", s)

    # 12. possede / possedent -> possède / possèdent
    s = _sub(r"\bpossede\b", "possède", s)
    s = _sub(r"\bpossedent\b", "possèdent", s)
    s = _sub(r"\bPossede\b", "Possède", s)
    s = _sub(r"\bPossedent\b", "Possèdent", s)

    # 13. deüil(s) -> deuil(s)
    s = _sub(r"\bdeüil(s?)\b", r"deuil\1", s)
    s = _sub(r"\bDeüil(s?)\b", r"Deuil\1", s)

    # 14. sévrait / sévraient / sévrer -> sevrait / sevraient / sevrer
    s = _sub(r"\bsévrait\b", "sevrait", s)
    s = _sub(r"\bsévraient\b", "sevraient", s)
    s = _sub(r"\bsévrer\b", "sevrer", s)

    # 15. obséques -> obsèques
    s = _sub(r"\bobséques\b", "obsèques", s)
    s = _sub(r"\bObséques\b", "Obsèques", s)

    # 16. haye(s) -> haie(s) [lowercase only, preserving 'de la Haye', 'La Haye']
    s = _sub(r"\bhaye\b", "haie", s)
    s = _sub(r"\bhayes\b", "haies", s)

    # 17. ruës / ruë -> rues / rue
    s = _sub(r"\bruës\b", "rues", s)
    s = _sub(r"\bruë\b", "rue", s)
    s = _sub(r"\bRuës\b", "Rues", s)
    s = _sub(r"\bRuë\b", "Rue", s)

    # 18. péchez (noun) -> péchés
    s = _sub(
        r"\b(de|d\'|des|les|ses|mes|tes|nos|vos|leurs|ces|quelques|plusieurs|grands|petits|autres|anciens|nouveaux|premiers|moindres|propres|certains|mille|sans|pour)\s+péchez\b",
        r"\1 péchés",
        s,
        flags=re.I,
    )
    s = _sub(
        r"\bpéchez\s+(sur\s+péchez|en\s+péchez|spirituels|véniels|d\'ignorance)\b",
        lambda m: "péchés " + m.group(1).replace("péchez", "péchés"),
        s,
    )

    # 19. entraînez (participle) -> entraînés
    s = _sub(r"\b(ou|a|ont|avaient|étaient|sont|furent|seront|aye|ayant|avez|ai)\s+entraînez\b", r"\1 entraînés", s)
    s = _sub(r"\bentraînez\s+(par|en\s+captivité|les\s+chaînes)\b", r"entraînés \1", s)

    # 20. fortifiez (participle) -> fortifiés
    s = _sub(r"\b(sont|étaient|s\'étaient|se\s+sont|lieux)\s+fortifiez\b", r"\1 fortifiés", s)

    # 21. laissez (participle) -> laissés
    s = _sub(r"\b(ont|avaient|étaient|sont|furent|auront|saient|s\'étaient|se\s+sont|été|habits)\s+laissez\b", r"\1 laissés", s)
    s = _sub(r"\b(nous\s+a|vous\s+a|l\'a)\s+laissez\b", r"\1 laissés", s)

    # 22. traitez (participle / noun) -> traités
    s = _sub(r"\b(les|vos|des)\s+traitez\b", r"\1 traités", s)
    s = _sub(
        r"\b(sont|seront|étaient|furent|ont\s+été|avaient|ont|a|ai|aye|aurai|soient|soyons|serons|être|d\'être|mieux|bien)\s+(?:infailliblement\s+|indignement\s+|assez\s+doucement\s+|cruellement\s+|durement\s+|fort\s+bien\s+|mieux\s+|bien\s+)?traitez\b",
        lambda m: m.group(0).replace("traitez", "traités"),
        s,
    )
    s = _sub(r"\b(méchants|impies|esclaves)\s+traitez\b", r"\1 traités", s)

    # 23. jouës / jouë -> joues / joue
    s = _sub(r"\b([Jj])ouë", r"\1oue", s)

    # 24. coù / coû -> cou
    s = _sub(r"\bco[ùû]\b", "cou", s)
    s = _sub(r"\bCo[ùû]\b", "Cou", s)
    s = _sub(r"\bco[ùû]-tume\b", "coutume", s)

    # 25. yvoire(s) -> ivoire(s)
    s = _sub(r"\byvoire(s?)\b", r"ivoire\1", s)
    s = _sub(r"\bYvoire(s?)\b", r"Ivoire\1", s)

    # 26. particuliérement -> particulièrement
    s = _sub(r"\bparticuliérement\b", "particulièrement", s)
    s = _sub(r"\bParticuliérement\b", "Particulièrement", s)

    # 27. Epouse(s) -> Épouse(s)
    s = _sub(r"\bEpouse(s?)\b", r"Épouse\1", s)

    # 28. Epoux -> Époux
    s = _sub(r"\bEpoux\b", "Époux", s)

    # 30. sçû / sçu -> su
    s = _sub(r"\bsç[ûu]\b", "su", s)
    s = _sub(r"\bSç[ûu]\b", "Su", s)
    s = _sub(r"\bsç[ûu]ë\b", "sue", s)

    # 31. enflammez -> enflammés
    s = _sub(r"\benflammez\b", "enflammés", s)
    s = _sub(r"\bEnflammez\b", "Enflammés", s)

    # 32. Doćtrine / ćt -> Doctrine / ct
    s = _sub(r"\bDoćtrine(s?)\b", r"Doctrine\1", s)
    s = _sub(r"\bdoćtrine(s?)\b", r"doctrine\1", s)
    s = s.replace("ćt", "ct").replace("Ćt", "Ct")

    # 33. mammelle(s) -> mamelle(s)
    s = _sub(r"\b([Mm])ammelle(s?)\b", r"\1amelle\2", s)

    # 34. Ecriture(s) -> Écriture(s)
    s = _sub(r"\bEcriture(s?)\b", r"Écriture\1", s)

    # 35. Evangile(s), Evangiliste(s) -> Évangile(s), Évangéliste(s)
    s = _sub(r"\bEvangile(s?)\b", r"Évangile\1", s)
    s = _sub(r"\bEvangiliste(s?)\b", r"Évangéliste\1", s)

    # 36. Egypte, Egyptien(s), Egyptienne(s) -> Égypte, Égyptien(s), Égyptienne(s)
    s = _sub(r"\bEgyptien(s?)\b", r"Égyptien\1", s)
    s = _sub(r"\bEgyptienne(s?)\b", r"Égyptienne\1", s)

    # 37. nôce(s) -> noce(s)
    s = _sub(r"\b([Nn])ôce(s?)\b", r"\1oce\2", s)

    # 38. éleve / élevent -> élève / élèvent
    s = _sub(r"\b([Éé])leve\b", r"\1lève", s)
    s = _sub(r"\b([Éé])levent\b", r"\1lèvent", s)

    # 39. societé(s) -> société(s)
    s = _sub(r"\b([Ss])ocieté(s?)\b", r"\1ociété\2", s)

    # 40. ajoût* -> ajout*
    s = _sub(r"\b([Aa])joût", r"\1jout", s)

    # 41. colomne(s) -> colonne(s)
    s = _sub(r"\b([Cc])olomne(s?)\b", r"\1olonne\2", s)

    # 42. fidelle(s), infidelle(s) -> fidèle(s), infidèle(s)
    s = _sub(r"\b([Ff])idelle(s?)\b", r"\1idèle\2", s)
    s = _sub(r"\b([Ii]n[Ff])idelle(s?)\b", r"\1idèle\2", s)

    # 43. régle(s) -> règle(s)
    s = _sub(r"\b([Rr])égle(s?)\b", r"\1ègle\2", s)

    # 44. chevreüil(s) -> chevreuil(s)
    s = _sub(r"\b([Cc])hevreüil(s?)\b", r"\1hevreuil\2", s)

    # 45. printems -> printemps
    s = _sub(r"\b([Pp])rintems\b", r"\1rintemps", s)

    # 46. bonne-chere -> bonne chère
    s = _sub(r"\bbonne-chere\b", "bonne chère", s)

    # 47. misere(s) -> misère(s)
    s = _sub(r"\b([Mm])isere(s?)\b", r"\1isère\2", s)

    # 48. maniere(s) -> manière(s)
    s = _sub(r"\b([Mm])aniere(s?)\b", r"\1anière\2", s)

    # 49. lumiere(s) -> lumière(s)
    s = _sub(r"\b([Ll])umiere(s?)\b", r"\1umière\2", s)

    # 50. premiere(s) -> première(s)
    s = _sub(r"\b([Pp])remiere(s?)\b", r"\1remière\2", s)

    # 51. derniere(s) -> dernière(s)
    s = _sub(r"\b([Dd])erniere(s?)\b", r"\1ernière\2", s)

    # 52. colere(s) -> colère(s)
    s = _sub(r"\b([Cc])olere(s?)\b", r"\1olère\2", s)

    # 53. priere(s) -> prière(s)
    s = _sub(r"\b([Pp])riere(s?)\b", r"\1rière\2", s)

    # 54. matiere(s) -> matière(s)
    s = _sub(r"\b([Mm])atiere(s?)\b", r"\1atière\2", s)

    # 55. remede(s) -> remède(s)
    s = _sub(r"\b([Rr])emede(s?)\b", r"\1emède\2", s)

    # 56. mystere(s) -> mystère(s), mystérieux
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Mm])yst[eé]re(s?)(?![A-Za-zÀ-ÿ])", r"\1ystère\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Mm])ysterieux\b", r"\1ystérieux", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Mm])ysterieuse(s?)\b", r"\1ystérieuse\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Mm])ysterieusement\b", r"\1ystérieusement", s)

    # 57. statuë(s) -> statue(s)
    s = _sub(r"\b([Ss])tatuë(s?)\b", r"\1tatue\2", s)

    # 58. bouë(s) -> boue(s)
    s = _sub(r"\b([Bb])ouë(s?)\b", r"\1oue\2", s)

    # 59. excez -> excès
    s = _sub(r"\b([Ee])xcez\b", r"\1xcès", s)

    # 60. Ezéchias -> Ézéchias
    s = _sub(r"\bEzéchias\b", "Ézéchias", s)

    # 61. Elie -> Élie
    s = _sub(r"\bElie\b", "Élie", s)

    # 62. Elisée -> Élisée
    s = _sub(r"\bElisée\b", "Élisée", s)

    # 63. Hebreux -> Hébreux (French form)
    s = _sub(r"\bHebreux\b", "Hébreux", s)

    # 65. Elûs -> Élus
    s = _sub(r"\bElûs\b", "Élus", s)

    # 66. ECCLESIASTIQUE -> ECCLÉSIASTIQUE
    s = _sub(r"\bECCLESIASTIQUE\b", "ECCLÉSIASTIQUE", s)

    # 67. verité(s) -> vérité(s)
    s = _sub(r"\b([Vv])erité(s?)\b", r"\1érité\2", s)

    # 68. impieté(s) -> impiété(s)
    s = _sub(r"\b([Ii])mpieté(s?)\b", r"\1mpiété\2", s)

    # 69. posterité(s) -> postérité(s)
    s = _sub(r"\b([Pp])osterité(s?)\b", r"\1ostérité\2", s)

    # 70. adultere(s) -> adultère(s)
    s = _sub(r"\b([Aa])dultere(s?)\b", r"\1dultère\2", s)

    # 72. Ezéchiel -> Ézéchiel
    s = _sub(r"\bEzéchiel\b", "Ézéchiel", s)

    # 73. Ethiopie, Ethiopien(s), Ethiopienne(s) -> Éthiopie, Éthiopien(s), Éthiopienne(s)
    s = _sub(r"\bEthiopie\b", "Éthiopie", s)
    s = _sub(r"\bEthiopien(s?)\b", r"Éthiopien\1", s)
    s = _sub(r"\bEthiopienne(s?)\b", r"Éthiopienne\1", s)

    # 74. Eliacim -> Éliacim
    s = _sub(r"\bEliacim\b", "Éliacim", s)

    # 75. ISAIE -> ISAÏE (in headings)
    s = _sub(r"\bISAIE\b", "ISAÏE", s)

    # 77. aîle(s) -> aile(s)
    s = _sub(r"\b([Aa])île(s?)\b", r"\1ile\2", s)

    # 78. élevera / éleveront -> élèvera / élèveront
    s = _sub(r"\b([Éé])levera\b", r"\1lèvera", s)
    s = _sub(r"\b([Éé])leveront\b", r"\1lèveront", s)

    # 79. rejetté(e)(s) -> rejeté(e)(s)
    s = _sub(r"\b([Rr])ejetté(e?s?)\b", r"\1ejeté\2", s)

    # 80. Tremas on mute e / archaic feminines
    s = _sub(r"\b([Dd])evenuë(s?)\b", r"\1evenue\2", s)
    s = _sub(r"\b([Ii])nconnuë(s?)\b", r"\1nconnue\2", s)
    s = _sub(r"\b([Nn])uë(s?)\b", r"\1ue\2", s)
    s = _sub(r"\b([Ll])ieuë(s?)\b", r"\1ieue\2", s)
    s = _sub(r"\b([Vv])uë(s?)\b", r"\1ue\2", s)
    s = _sub(r"\b([Aa])battuë(s?)\b", r"\1battue\2", s)
    s = _sub(r"\b([Rr])enduë(s?)\b", r"\1endue\2", s)
    s = _sub(r"\b([Cc])onfonduë(s?)\b", r"\1onfondue\2", s)
    s = _sub(r"\b([Ee])ntenduë(s?)\b", r"\1ntendue\2", s)
    s = _sub(r"\b([Tt])enuë(s?)\b", r"\1enue\2", s)
    s = _sub(r"\b([Vv])êtuë(s?)\b", r"\1êtue\2", s)
    s = _sub(r"\b([Ee])uë(s?)\b", r"\1ue\2", s)
    s = _sub(r"\b([Ff])enduë(s?)\b", r"\1endue\2", s)
    s = _sub(r"\b([Bb])attuë(s?)\b", r"\1attue\2", s)
    s = _sub(r"\b([Aa])pperçuë(s?)\b", r"\1perçue\2", s)
    s = _sub(r"\b([Rr])é?panduë(s?)\b", r"\1épandue\2", s)
    s = _sub(r"\b([Ff])eüille(s?)\b", r"\1euille\2", s)
    s = _sub(r"\b([Ff])eüillage(s?)\b", r"\1euillage\2", s)
    s = _sub(r"\b([Oo])rguëil\b", r"\1rgueil", s)
    s = _sub(r"\b([Qq])ueuë(s?)\b", r"\1ueue\2", s)
    s = _sub(r"\b([Pp])oële(s?)\b", r"\1oêle\2", s)
    s = _sub(r"\b([Ii])nsinuë\b", r"\1nsinue", s)
    s = _sub(r"\b([Cc])ontinuënt\b", r"\1ontinuent", s)
    s = _sub(r"\b([Dd])iminuënt\b", r"\1iminuent", s)
    s = _sub(r"\b([Rr])éüssi([a-z]*)\b", r"\1éussi\2", s)
    s = _sub(r"\b([Vv])eüille(s?)\b", r"\1euille\2", s)

    # 81. ménace(s), ménacer, etc. -> menace(s), menacer
    s = _sub(r"\b([Mm])énace(s?)\b", r"\1enace\2", s)
    s = _sub(r"\b([Mm])énacé(e?s?)\b", r"\1enacé\2", s)
    s = _sub(r"\b([Mm])énacer([a-zà-ÿ]*)\b", r"\1enacer\2", s)

    # 82. Prophête(s) -> Prophète(s)
    s = _sub(r"\b([Pp])rophête(s?)\b", r"\1rophète\2", s)

    # 83. regna, etc. -> régna, etc.
    s = _sub(r"\b([Rr])egna\b", r"\1égna", s)
    s = _sub(r"\b([Rr])egnait\b", r"\1égnait", s)
    s = _sub(r"\b([Rr])egnaient\b", r"\1égnaient", s)
    s = _sub(r"\b([Rr])egnera\b", r"\1égnera", s)
    s = _sub(r"\b([Rr])egnérent\b", r"\1égnèrent", s)

    # 84. brébis -> brebis
    s = _sub(r"\b([Bb])rébis\b", r"\1rebis", s)

    # 85. premiérement -> premièrement
    s = _sub(r"\b([Pp])remiérement\b", r"\1remièrement", s)

    # 86. auprés -> auprès
    s = _sub(r"\b([Aa])uprés\b", r"\1uprès", s)

    # 87. plutot -> plutôt
    s = _sub(r"\b([Pp])lutot\b", r"\1lutôt", s)

    # 88. prédecesseur(s) -> prédécesseur(s)
    s = _sub(r"\b([Pp])rédecesseur(s?)\b", r"\1rédécesseur\2", s)

    # 89. soûmis -> soumis, soûtiennent -> soutiennent
    s = _sub(r"\b([Ss])oûmi(s|se|ses)\b", r"\1oumi\2", s)
    s = _sub(r"\b([Ss])oûtien(s|t|nent)\b", r"\1outien\2", s)

    # 90. jetté, jetta, etc. -> jeté, jeta, etc.
    s = _sub(r"\b([Jj])etté(e?s?)\b", r"\1eté\2", s)
    s = _sub(r"\b([Jj])etta\b", r"\1eta", s)
    s = _sub(r"\b([Jj])ettait\b", r"\1etait", s)
    s = _sub(r"\b([Jj])ettaient\b", r"\1etaient", s)
    s = _sub(r"\b([Jj])ettant\b", r"\1etant", s)
    s = _sub(r"\b([Jj])ettérent\b", r"\1etèrent", s)

    # 91. rejetton(s), etc. -> rejeton(s), etc.
    s = _sub(r"\b([Rr])ejetton(s?)\b", r"\1ejeton\2", s)
    s = _sub(r"\b([Rr])ejetta\b", r"\1ejeta", s)
    s = _sub(r"\b([Rr])ejettant\b", r"\1ejetant", s)
    s = _sub(r"\b([Rr])ejettérent\b", r"\1ejetèrent", s)

    # 92. auxquels
    s = _sub(r"\b([Aa])usquels\b", r"\1uxquels", s)

    # 93. cachetté -> cacheté
    s = _sub(r"\b([Cc])achetté(e?s?)\b", r"\1acheté\2", s)

    # 94. cuirrasse -> cuirasse
    s = _sub(r"\b([Cc])uirrasse(s?)\b", r"\1uirasse\2", s)

    # 95. allarme -> alarme
    s = _sub(r"\b([Aa])llarme(s?)\b", r"\1larme\2", s)

    # 96. courier -> courrier
    s = _sub(r"\b([Cc])ourier(s?)\b", r"\1ourrier\2", s)

    # 97. rappeller -> rappeler
    s = _sub(r"\b([Rr])appeller\b", r"\1appeler", s)

    # 98. retraitte -> retraite
    s = _sub(r"\b([Rr])etraitte(s?)\b", r"\1etraite\2", s)

    # 99. vuide -> vide
    s = _sub(r"\b([Vv])uide(s?)\b", r"\1ide\2", s)

    # 100. asne -> âne
    s = _sub(r"\bAsne(s?)\b", r"Âne\1", s)
    s = _sub(r"\basne(s?)\b", r"âne\1", s)

    # 101. Ecoutez -> Écoutez
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Ecoutez(?![A-Za-zÀ-ÿ])", "Écoutez", s)

    # 102. Etat / Etats -> État / États
    s = _sub(r"\bEtat(s?)\b", r"État\1", s)

    # 103. Edition(s) -> Édition(s)
    s = _sub(r"\bEdition(s?)\b", r"Édition\1", s)

    # 104. Ecrit(s) -> Écrit(s)
    s = _sub(r"\bEcrit(s?)\b", r"Écrit\1", s)

    # 105. Ecrivez -> Écrivez
    s = _sub(r"\bEcrivez\b", "Écrivez", s)

    # 108. Secretaire(s) -> Secrétaire(s)
    s = _sub(r"\b([Ss])ecretaire(s?)\b", r"\1ecrétaire\2", s)

    # 109. OCR long-s artifacts (f -> s)
    s = _sub(r"\b([Cc])irconcifion(s?)\b", r"\1irconcision\2", s)
    s = _sub(r"\b([Ii])ncirconcife(s?)\b", r"\1ncirconcise\2", s)
    s = _sub(r"\b([Ee])nfeveli(s|r|rent)\b", r"\1nseveli\2", s)
    s = _sub(r"\b([Pp])rophétif([a-zà-ÿ]+)\b", r"\1rophétis\2", s)
    s = _sub(r"\b([Cc])onfume(z?|nt)?\b", r"\1onsume\2", s)
    s = _sub(r"\b([Ii])nfinue([a-zà-ÿ]*)\b", r"\1nsinue\2", s)
    s = _sub(r"\b([Ff])ignifie\b", "signifie", s)
    s = _sub(r"\b([Bb])ienféance(s?)\b", r"\1ienséance\2", s)
    s = _sub(r"\b([Cc])onfidér([a-zà-ÿ]+)\b", r"\1onsidér\2", s)
    s = _sub(r"\b([Ff])errurier(s?)\b", r"serrurier\2", s)
    s = _sub(r"\b([Ff])upplice(s?)\b", r"supplice\2", s)
    s = _sub(r"\b([Mm])enfonge(s?)\b", r"\1ensonge\2", s)
    s = _sub(r"\b([Tt])réfors\b", r"\1résors", s)
    s = _sub(r"\b([Ff])ourdent\b", "sourdent", s)
    s = _sub(r"\b([Aa])bufe(z|r|nt|s)?\b", r"\1buse\2", s)
    s = _sub(r"\b([Aa])bufé(e?s?)\b", r"\1busé\2", s)
    s = _sub(r"\b([Aa])ccroiffement(s?)\b", r"\1ccroissement\2", s)

    # 110. Past historic 3rd pl: -érent -> -èrent
    s = _sub(r"\b([Ee])mmenérent\b", r"\1mmenèrent", s)
    s = _sub(r"\b([Ee])ntrérent\b", r"\1ntrèrent", s)
    s = _sub(r"\b([Ss])auvérent\b", r"\1auvèrent", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Dd])onnérent(?![A-Za-zÀ-ÿ])", r"\1onnèrent", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Cc])ommencérent(?![A-Za-zÀ-ÿ])", r"\1ommencèrent", s)

    # 111. saient -> soient
    s = _sub(r"(?<![A-Za-zÀ-ÿ])saient(?![A-Za-zÀ-ÿ])", "soient", s)

    # 112. fang -> sang
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Fang(?![A-Za-zÀ-ÿ])", "Sang", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])fang(?![A-Za-zÀ-ÿ])", "sang", s)

    # 113. Juiss -> Juifs
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Juiss(?![A-Za-zÀ-ÿ])", "Juifs", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])juiss(?![A-Za-zÀ-ÿ])", "juifs", s)

    # 114. craître -> croître
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Cc])raître(?![A-Za-zÀ-ÿ])", r"\1roître", s)

    # 115. défert -> désert
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Dd])éfert(s?)(?![A-Za-zÀ-ÿ])", r"\1ésert\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Dd])éferte(s?)(?![A-Za-zÀ-ÿ])", r"\1éserte\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Dd])éferter(?![A-Za-zÀ-ÿ])", r"\1éserter", s)

    # 116. trenchant -> tranchant
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Tt])renchant(s?)(?![A-Za-zÀ-ÿ])", r"\1ranchant\2", s)

    # 117. Nabuchodonofor -> Nabuchodonosor
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Nabuchodonofor(?![A-Za-zÀ-ÿ])", "Nabuchodonosor", s)

    # 118. fouillure(s) -> souillure(s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])fouillure(s?)(?![A-Za-zÀ-ÿ])", r"souillure\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Fouillure(s?)(?![A-Za-zÀ-ÿ])", r"Souillure\1", s)

    # 119. cuiraffe(s) -> cuirasse(s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Cc])uiraffe(s?)(?![A-Za-zÀ-ÿ])", r"\1uirasse\2", s)

    # 120. couffinets -> coussinets
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Cc])ouffinets(?![A-Za-zÀ-ÿ])", r"\1oussinets", s)

    # 121. Long-s OCR artifacts
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ii])nfolente(s?)(?![A-Za-zÀ-ÿ])", r"\1nsolente\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])lorfque(?![A-Za-zÀ-ÿ])", "lorsque", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Rr])éfolu(e?s?)(?![A-Za-zÀ-ÿ])", r"\1ésolu\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Dd])éfolation(s?)(?![A-Za-zÀ-ÿ])", r"\1ésolation\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Efdras(?![A-Za-zÀ-ÿ])", "Esdras", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Ifaïe(?![A-Za-zÀ-ÿ])", "Isaïe", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Jofeph(?![A-Za-zÀ-ÿ])", "Joseph", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Jérufalem(?![A-Za-zÀ-ÿ])", "Jérusalem", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ll])ifez(?![A-Za-zÀ-ÿ])", r"\1isez", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Mm])anufcrit(s?)(?![A-Za-zÀ-ÿ])", r"\1anuscrit\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Verfets(?![A-Za-zÀ-ÿ])", "Versets", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Aa])baiffé(e?s?)(?![A-Za-zÀ-ÿ])", r"\1baissé\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Aa])ccompliffement(s?)(?![A-Za-zÀ-ÿ])", r"\1ccomplissement\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Aa])llufion(s?)(?![A-Za-zÀ-ÿ])", r"\1llusion\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Cc])ompofé(e?s?)(?![A-Za-zÀ-ÿ])", r"\1omposé\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Dd])eftiné(e?s?)(?![A-Za-zÀ-ÿ])", r"\1estiné\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Dd])eftinez(?![A-Za-zÀ-ÿ])", r"\1estinez", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Dd])ifcernement(?![A-Za-zÀ-ÿ])", r"\1iscernement", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Dd])ifperfion(?![A-Za-zÀ-ÿ])", r"\1ispersion", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Dd])isperfé(e?s?)(?![A-Za-zÀ-ÿ])", r"\1ispersé\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Dd])isperfez(?![A-Za-zÀ-ÿ])", r"\1ispersez", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ee])nfeveliront(?![A-Za-zÀ-ÿ])", r"\1nseveliront", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ee])xpreffion(s?)(?![A-Za-zÀ-ÿ])", r"\1xpression\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])fainte(s?)(?![A-Za-zÀ-ÿ])", r"sainte\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Fainte(s?)(?![A-Za-zÀ-ÿ])", r"Sainte\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])faisit(?![A-Za-zÀ-ÿ])", "saisit", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Faisit(?![A-Za-zÀ-ÿ])", "Saisit", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])faule(s?)(?![A-Za-zÀ-ÿ])", r"saule\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])fauverai(?![A-Za-zÀ-ÿ])", "sauverai", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])favons(?![A-Za-zÀ-ÿ])", "savons", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])femaine(s?)(?![A-Za-zÀ-ÿ])", r"semaine\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])fignal(?![A-Za-zÀ-ÿ])", "signal", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])floriffant(e?s?)(?![A-Za-zÀ-ÿ])", r"florissant\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])foldat(s?)(?![A-Za-zÀ-ÿ])", r"soldat\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])folitude(?![A-Za-zÀ-ÿ])", "solitude", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])forti(e?s?)(?![A-Za-zÀ-ÿ])", r"sorti\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])furvit(?![A-Za-zÀ-ÿ])", "survit", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])fécher(?![A-Za-zÀ-ÿ])", "sécher", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])fœur(s?)(?![A-Za-zÀ-ÿ])", r"sœur\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Fœur(s?)(?![A-Za-zÀ-ÿ])", r"Sœur\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])glorieufement(?![A-Za-zÀ-ÿ])", "glorieusement", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Hh])olocaufte(s?)(?![A-Za-zÀ-ÿ])", r"\1olocauste\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])indiffoluble(s?)(?![A-Za-zÀ-ÿ])", r"indissoluble\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])jaloufie(s?)(?![A-Za-zÀ-ÿ])", r"jalousie\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])jeuneffe(?![A-Za-zÀ-ÿ])", "jeunesse", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])mufique(?![A-Za-zÀ-ÿ])", "musique", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Mm])éprifé(e?s?)(?![A-Za-zÀ-ÿ])", r"\1éprisé\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])oifiveté(?![A-Za-zÀ-ÿ])", "oisiveté", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])perfécution(s?)(?![A-Za-zÀ-ÿ])", r"persécution\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])permiffion(?![A-Za-zÀ-ÿ])", "permission", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])promeffe(s?)(?![A-Za-zÀ-ÿ])", r"promesse\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])préfervent(?![A-Za-zÀ-ÿ])", "préservent", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])pétrifsait(?![A-Za-zÀ-ÿ])", "pétrissait", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])redreffé(e?s?)(?![A-Za-zÀ-ÿ])", r"redressé\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])redreffez(?![A-Za-zÀ-ÿ])", "redressez", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])refpect(?![A-Za-zÀ-ÿ])", "respect", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])épuifé(e?s?)(?![A-Za-zÀ-ÿ])", r"épuisé\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Épuifé(e?s?)(?![A-Za-zÀ-ÿ])", r"Épuisé\1", s)

    # 122. soye -> soie
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ss])oye(s?)(?![A-Za-zÀ-ÿ])", r"\1oie\2", s)

    # 123. degrez / dégrez -> degrés
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Dd])[eé]grez(?![A-Za-zÀ-ÿ])", r"\1egrés", s)

    # 124. chaudiere -> chaudière
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Cc])haudiere(s?)(?![A-Za-zÀ-ÿ])", r"\1haudière\2", s)

    # 125. ministere -> ministère
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Mm])inistere(s?)(?![A-Za-zÀ-ÿ])", r"\1inistère\2", s)

    # 126. derriere -> derrière
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Dd])erriere(?![A-Za-zÀ-ÿ])", r"\1errière", s)

    # 127. poussiere -> poussière
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Pp])oussiere(s?)(?![A-Za-zÀ-ÿ])", r"\1oussière\2", s)

    # 128. deshonor* -> déshonor*
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Dd])eshonor([a-zà-ÿ]*)(?![A-Za-zÀ-ÿ])", r"\1éshonor\2", s)

    # 129. felon -> félon
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ff])elon(s?)(?![A-Za-zÀ-ÿ])", r"\1élon\2", s)

    # 130. moëlle -> moelle
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Mm])oëlle(?![A-Za-zÀ-ÿ])", r"\1oelle", s)

    # 131. seüil -> seuil
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ss])eüil(s?)(?![A-Za-zÀ-ÿ])", r"\1euil\2", s)

    # 132. aïle -> aile
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Aa])ïle(s?)(?![A-Za-zÀ-ÿ])", r"\1ile\2", s)

    # 133. nud(s) -> nu(s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Nn])ud(s?)(?![A-Za-zÀ-ÿ])", r"\1u\2", s)

    # 134. coûtume -> coutume
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Cc])oûtume(s?)(?![A-Za-zÀ-ÿ])", r"\1outume\2", s)

    # 135. diadême -> diadème
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Dd])iadême(s?)(?![A-Za-zÀ-ÿ])", r"\1iadème\2", s)

    # 136. Paralipoménes -> Paralipomènes
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Paralipoménes(?![A-Za-zÀ-ÿ])", "Paralipomènes", s)

    # 137. déréglement -> dérèglement
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Dd])éréglement(s?)(?![A-Za-zÀ-ÿ])", r"\1érèglement\2", s)

    # 138. fauxbourg -> faubourg
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ff])auxbourg(s?)(?![A-Za-zÀ-ÿ])", r"\1aubourg\2", s)

    # 139. nostre / vostre -> notre / votre
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Nn])ostre(?![A-Za-zÀ-ÿ])", r"\1otre", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Vv])ostre(?![A-Za-zÀ-ÿ])", r"\1otre", s)

    # 140. machoires -> mâchoires
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Mm])achoire(s?)(?![A-Za-zÀ-ÿ])", r"\1âchoire\2", s)

    # 141. chrystal -> cristal
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Cc])hrystal(?![A-Za-zÀ-ÿ])", r"\1ristal", s)

    # 142. exemt -> exempt
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ee])xemt(s?)(?![A-Za-zÀ-ÿ])", r"\1xempt\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ee])xemte(s?)(?![A-Za-zÀ-ÿ])", r"\1xempte\2", s)

    # 143. differente -> différente
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Dd])ifferente(s?)(?![A-Za-zÀ-ÿ])", r"\1ifférente\2", s)

    # 144. fidélement -> fidèlement
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ff])idélement(?![A-Za-zÀ-ÿ])", r"\1idèlement", s)

    # 145. entierement / entiérement -> entièrement
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ee])ntierement(?![A-Za-zÀ-ÿ])", r"\1ntièrement", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ee])ntiérement(?![A-Za-zÀ-ÿ])", r"\1ntièrement", s)

    # 146. sepulture -> sépulture
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ss])epulture(s?)(?![A-Za-zÀ-ÿ])", r"\1épulture\2", s)

    # 147. solemnel -> solennel
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ss])olemnel(s?)(?![A-Za-zÀ-ÿ])", r"\1olennel\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ss])olemnelle(s?)(?![A-Za-zÀ-ÿ])", r"\1olennelle\2", s)

    # 148. monnoye -> monnaie
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Mm])onnoye(s?)(?![A-Za-zÀ-ÿ])", r"\1onnaie\2", s)

    # 149. promte -> prompte
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Pp])romte(s?)(?![A-Za-zÀ-ÿ])", r"\1rompte\2", s)

    # 150. estomach -> estomac
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ee])stomach(?![A-Za-zÀ-ÿ])", r"\1stomac", s)

    # 151. infideles -> infidèles
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ii])nfideles(?![A-Za-zÀ-ÿ])", r"\1nfidèles", s)

    # 152. carquais -> carquois
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Cc])arquais(?![A-Za-zÀ-ÿ])", r"\1arquois", s)

    # 153. extrémement -> extrêmement
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ee])xtrémement(?![A-Za-zÀ-ÿ])", r"\1xtrêmement", s)

    # 154. infame -> infâme
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ii])nfame(s?)(?![A-Za-zÀ-ÿ])", r"\1nfâme\2", s)

    # 155. verds -> verts
    s = _sub(r"(?<![A-Za-zÀ-ÿ])verds(?![A-Za-zÀ-ÿ])", "verts", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Verds(?![A-Za-zÀ-ÿ])", "Verts", s)

    # 156. aménerai / ramenerai -> amènerai / ramènerai
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Aa])ménerai(ent)?(?![A-Za-zÀ-ÿ])", r"\1mènerai\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Rr])amenerai(ent)?(?![A-Za-zÀ-ÿ])", r"\1amènerai\2", s)

    # 157. battans -> battants
    s = _sub(r"(?<![A-Za-zÀ-ÿ])battans(?![A-Za-zÀ-ÿ])", "battants", s)

    # 158. Interprêtes -> Interprètes
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Interprêtes(?![A-Za-zÀ-ÿ])", "Interprètes", s)

    # 159. LITTERAL -> LITTÉRAL
    s = _sub(r"(?<![A-Za-zÀ-ÿ])LITTERAL(?![A-Za-zÀ-ÿ])", "LITTÉRAL", s)

    # 160. demiseptier -> demi-setier
    s = _sub(r"(?<![A-Za-zÀ-ÿ])demiseptier(?![A-Za-zÀ-ÿ])", "demi-setier", s)

    # 161. ensorte que -> en sorte que
    s = _sub(r"(?<![A-Za-zÀ-ÿ])ensorte\s+que(?![A-Za-zÀ-ÿ])", "en sorte que", s)

    # 162. appellaient -> appelaient, appeller -> appeler
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Aa])ppellaient(?![A-Za-zÀ-ÿ])", r"\1ppelaient", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Aa])ppeller(?![A-Za-zÀ-ÿ])", r"\1ppeler", s)

    # 163. Feminine tremas / mute-e
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Pp])arvenuë(s?)(?![A-Za-zÀ-ÿ])", r"\1arvenue\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Pp])erduë(s?)(?![A-Za-zÀ-ÿ])", r"\1erdue\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Pp])enduë(s?)(?![A-Za-zÀ-ÿ])", r"\1endue\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Rr])evuë(s?)(?![A-Za-zÀ-ÿ])", r"\1evue\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Rr])uïne(s?)(?![A-Za-zÀ-ÿ])", r"\1uine\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ss])oûtenuë(s?)(?![A-Za-zÀ-ÿ])", r"\1outenue\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Rr])evenuës(?![A-Za-zÀ-ÿ])", r"\1evenues", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ss])ouvenuë(s?)(?![A-Za-zÀ-ÿ])", r"\1ouvenue\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Tt])uë(?![A-Za-zÀ-ÿ])", r"\1ue", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Tt])uëront(?![A-Za-zÀ-ÿ])", r"\1ueront", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])étendües(?![A-Za-zÀ-ÿ])", "étendues", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Aa])batuë(s?)(?![A-Za-zÀ-ÿ])", r"\1battue\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])assiduëment(?![A-Za-zÀ-ÿ])", "assidûment", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Cc])ercüeil(s?)(?![A-Za-zÀ-ÿ])", r"\1ercueil\2", s)

    # 164. Unaccented Capital E
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Epée(s?)(?![A-Za-zÀ-ÿ])", r"Épée\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Etant(?![A-Za-zÀ-ÿ])", "Étant", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Ecrivains(?![A-Za-zÀ-ÿ])", "Écrivains", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Etes(?![A-Za-zÀ-ÿ])", "Êtes", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Elevons(?![A-Za-zÀ-ÿ])", "Élevons", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Etienne(?![A-Za-zÀ-ÿ])", "Étienne", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Evangélique(s?)(?![A-Za-zÀ-ÿ])", r"Évangélique\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Ecartez(?![A-Za-zÀ-ÿ])", "Écartez", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Ecoute(?![A-Za-zÀ-ÿ])", "Écoute", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Ecoûtez(?![A-Za-zÀ-ÿ])", "Écoutez", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Eden(?![A-Za-zÀ-ÿ])", "Éden", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Edifice(s?)(?![A-Za-zÀ-ÿ])", r"Édifice\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Edit(s?)(?![A-Za-zÀ-ÿ])", r"Édit\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Eléphantine(?![A-Za-zÀ-ÿ])", "Éléphantine", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Enigme(s?)(?![A-Za-zÀ-ÿ])", r"Énigme\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Enée(?![A-Za-zÀ-ÿ])", "Énée", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Epicuriens(?![A-Za-zÀ-ÿ])", "Épicuriens", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Epitre(s?)(?![A-Za-zÀ-ÿ])", r"Épître\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Etait(?![A-Za-zÀ-ÿ])", "Était", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Etendez(?![A-Za-zÀ-ÿ])", "Étendez", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Etendre(?![A-Za-zÀ-ÿ])", "Étendre", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Eternel(?![A-Za-zÀ-ÿ])", "Éternel", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Jerusalem(?![A-Za-zÀ-ÿ])", "Jérusalem", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Jerôme(?![A-Za-zÀ-ÿ])", "Jérôme", s)

    # 165. Generalized past historic -érent -> -èrent
    if "érent" in s:
        s = _sub(
            r"(?<![A-Za-zÀ-ÿ])(?!(?:[Aa]ff|[Aa]dh|[Cc]oh|[Ii]ncoh|[Dd]éf|[Dd]iff|[Ii]ndiff|[Ii]ng|[Rr]éf)érent\b)([A-Za-zÀ-ÿ]+)érent(?![A-Za-zÀ-ÿ])",
            r"\1èrent",
            s
        )

    # 166. benissez / beniffez -> bénissez
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Bb])eni[sf]{2}ez(?![A-Za-zÀ-ÿ])", r"\1énissez", s)

    # 167. Susanne -> Suzanne
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Susanne(?![A-Za-zÀ-ÿ])", "Suzanne", s)

    # 168. Salmanafar -> Salmanasar
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Salmanafar(?![A-Za-zÀ-ÿ])", "Salmanasar", s)

    # 169. Antechrist -> Antéchrist
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Aa])ntechrist(?![A-Za-zÀ-ÿ])", r"\1ntéchrist", s)

    # 170. Evergétes -> Évergètes
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Evergétes(?![A-Za-zÀ-ÿ])", "Évergètes", s)

    # 171. Gabriël -> Gabriel
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Gabriël(?![A-Za-zÀ-ÿ])", "Gabriel", s)

    # 172. Cléopatre -> Cléopâtre
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Cléopatre(?![A-Za-zÀ-ÿ])", "Cléopâtre", s)

    # 173. Xercès -> Xerxès
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Xercès(?![A-Za-zÀ-ÿ])", "Xerxès", s)

    # 174. regné -> régné
    s = _sub(r"(?<![A-Za-zÀ-ÿ])regné(e?s?)(?![A-Za-zÀ-ÿ])", r"régné\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Regné(e?s?)(?![A-Za-zÀ-ÿ])", r"Régné\1", s)

    # 175. assûre -> assure
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Aa])ssûre(nt)?(?![A-Za-zÀ-ÿ])", r"\1ssure\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Aa])ssûré(e?s?)(?![A-Za-zÀ-ÿ])", r"\1ssuré\2", s)

    # 176. Osee / Ofée -> Osée
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Osee(?![A-Za-zÀ-ÿ])", "Osée", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Ofée(?![A-Za-zÀ-ÿ])", "Osée", s)

    # 177. Long-s OCR artifacts
    s = _sub(r"(?<![A-Za-zÀ-ÿ])refte(s?)(?![A-Za-zÀ-ÿ])", r"reste\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Ifraël(?![A-Za-zÀ-ÿ])", "Israël", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Perfe(s?)(?![A-Za-zÀ-ÿ])", r"Perse\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])fauterelle(s?)(?![A-Za-zÀ-ÿ])", r"sauterelle\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])femble(?![A-Za-zÀ-ÿ])", "semble", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])femblable(s?)(?![A-Za-zÀ-ÿ])", r"semblable\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])fortira(?![A-Za-zÀ-ÿ])", "sortira", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])jufte(s?)(?![A-Za-zÀ-ÿ])", r"juste\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])juftice(?![A-Za-zÀ-ÿ])", "justice", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])lifent(?![A-Za-zÀ-ÿ])", "lisent", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])meurtriffure(s?)(?![A-Za-zÀ-ÿ])", r"meurtrissure\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])miféricorde(?![A-Za-zÀ-ÿ])", "miséricorde", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])vifage(s?)(?![A-Za-zÀ-ÿ])", r"visage\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Efprit(?![A-Za-zÀ-ÿ])", "Esprit", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Philiftin(s?)(?![A-Za-zÀ-ÿ])", r"Philistin\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Rofée(s?)(?![A-Za-zÀ-ÿ])", r"Rosée\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])affemblée(s?)(?![A-Za-zÀ-ÿ])", r"assemblée\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])caufe(s?)(?![A-Za-zÀ-ÿ])", r"cause\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])caufé(e?s?)(?![A-Za-zÀ-ÿ])", r"causé\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])circonftance(s?)(?![A-Za-zÀ-ÿ])", r"circonstance\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])difcours(?![A-Za-zÀ-ÿ])", "discours", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])difent(?![A-Za-zÀ-ÿ])", "disent", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])divifion(s?)(?![A-Za-zÀ-ÿ])", r"division\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])domeftique(s?)(?![A-Za-zÀ-ÿ])", r"domestique\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])défignai(t|ent)(?![A-Za-zÀ-ÿ])", r"désignai\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])déteftation(?![A-Za-zÀ-ÿ])", "détestation", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])fauver(?![A-Za-zÀ-ÿ])", "sauver", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])fens(?![A-Za-zÀ-ÿ])", "sens", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])fentiment(s?)(?![A-Za-zÀ-ÿ])", r"sentiment\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])fervice(s?)(?![A-Za-zÀ-ÿ])", r"service\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])fervir(?![A-Za-zÀ-ÿ])", "servir", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])ferviteur(s?)(?![A-Za-zÀ-ÿ])", r"serviteur\1", s)

    # 178. Mute-e tremas & archaic feminines
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Aa])ttribuë(?![A-Za-zÀ-ÿ])", r"\1ttribue", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Aa])bsoluë(s?)(?![A-Za-zÀ-ÿ])", r"\1bsolue\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Aa])ccruë(s?)(?![A-Za-zÀ-ÿ])", r"\1ccrue\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Dd])éfenduë(s?)(?![A-Za-zÀ-ÿ])", r"\1éfendue\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Oo])béïssai(t|ent)(?![A-Za-zÀ-ÿ])", r"\1béissai\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Rr])etenuë(s?)(?![A-Za-zÀ-ÿ])", r"\1etenue\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Rr])ompuë(s?)(?![A-Za-zÀ-ÿ])", r"\1ompue\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Rr])éüni(e?s?)(?![A-Za-zÀ-ÿ])", r"\1éuni\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Rr])éünit(?![A-Za-zÀ-ÿ])", r"\1éunit", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ss])uspenduë(s?)(?![A-Za-zÀ-ÿ])", r"\1uspendue\2", s)

    # 179. Capital unaccented E
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Ephraïm(?![A-Za-zÀ-ÿ])", "Éphraïm", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Ephod(s?)(?![A-Za-zÀ-ÿ])", r"Éphod\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Eulée(?![A-Za-zÀ-ÿ])", "Éulée", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Eclairs(?![A-Za-zÀ-ÿ])", "Éclairs", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Eloignez(?![A-Za-zÀ-ÿ])", "Éloignez", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Epines(?![A-Za-zÀ-ÿ])", "Épines", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Epousez(?![A-Za-zÀ-ÿ])", "Épousez", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Eprouvez(?![A-Za-zÀ-ÿ])", "Éprouvez", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Etoiles(?![A-Za-zÀ-ÿ])", "Étoiles", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Eveillez(?![A-Za-zÀ-ÿ])", "Éveillez", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Evêques(?![A-Za-zÀ-ÿ])", "Évêques", s)

    # 180. Capital unaccented initial vowels & Edom
    s = _sub(r"(?<![A-Za-zÀ-ÿ])d'Edom(?![A-Za-zÀ-ÿ])", "d'Édom", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])qu'Edom(?![A-Za-zÀ-ÿ])", "qu'Édom", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])contre\s+Edom(?![A-Za-zÀ-ÿ])", "contre Édom", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Evangéliste(s?)(?![A-Za-zÀ-ÿ])", r"Évangéliste\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Ecole(s?)(?![A-Za-zÀ-ÿ])", r"École\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Edile(s?)(?![A-Za-zÀ-ÿ])", r"Édile\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Eglogue(s?)(?![A-Za-zÀ-ÿ])", r"Églogue\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Etablissement(s?)(?![A-Za-zÀ-ÿ])", r"Établissement\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Eternelle(s?)(?![A-Za-zÀ-ÿ])", r"Éternelle\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Etouffez(?![A-Za-zÀ-ÿ])", "Étouffez", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Etranger(s?)(?![A-Za-zÀ-ÿ])", r"Étranger\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Evêque(s?)(?![A-Za-zÀ-ÿ])", r"Évêque\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Epiphanie(?![A-Za-zÀ-ÿ])", "Épiphanie", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Epître(s?)(?![A-Za-zÀ-ÿ])", r"Épître\1", s)

    # 181. Archaic spellings & accents
    s = _sub(r"(?<![A-Za-zÀ-ÿ])avénement(s?)(?![A-Za-zÀ-ÿ])", r"avènement\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])paroîtr([a-zà-ÿ]*)(?![A-Za-zÀ-ÿ])", r"paraîtr\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])flatait(?![A-Za-zÀ-ÿ])", "flattait", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])flater(?![A-Za-zÀ-ÿ])", "flatter", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])flatez(?![A-Za-zÀ-ÿ])", "flattez", s)

    # 182. Mute-e tremas & archaic feminines
    s = _sub(r"(?<![A-Za-zÀ-ÿ])charruë(s?)(?![A-Za-zÀ-ÿ])", r"charrue\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])charuë(s?)(?![A-Za-zÀ-ÿ])", r"charrue\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])tuëra(nt)?(?![A-Za-zÀ-ÿ])", r"tuera\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])conçûë(s?)(?![A-Za-zÀ-ÿ])", r"conçue\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])muë(s?)(?![A-Za-zÀ-ÿ])", r"mue\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])obéï(e?s?)(?![A-Za-zÀ-ÿ])", r"obéi\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])obéïr([a-zà-ÿ]*)(?![A-Za-zÀ-ÿ])", r"obéir\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])réünir(?![A-Za-zÀ-ÿ])", "réunir", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])cruës(?![A-Za-zÀ-ÿ])", "crues", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])prostituëra(nt)?(?![A-Za-zÀ-ÿ])", r"prostituera\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])remuëra(nt)?(?![A-Za-zÀ-ÿ])", r"remuera\1", s)

    # 183. Long-s OCR artifacts
    s = _sub(r"(?<![A-Za-zÀ-ÿ])époufe(s?)(?![A-Za-zÀ-ÿ])", r"épouse\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])féparer(?![A-Za-zÀ-ÿ])", "séparer", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])perfonne(s?)(?![A-Za-zÀ-ÿ])", r"personne\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Baptifte(s?)(?![A-Za-zÀ-ÿ])", r"Baptiste\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Précurfeur(s?)(?![A-Za-zÀ-ÿ])", r"Précurseur\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ii])nfatiable(s?)(?![A-Za-zÀ-ÿ])", r"\1nsatiable\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])adreffe(s?)(?![A-Za-zÀ-ÿ])", r"adresse\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])abufant(?![A-Za-zÀ-ÿ])", "abusant", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])affujettiffement(?![A-Za-zÀ-ÿ])", "assujettissement", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])avantageufe(s?)(?![A-Za-zÀ-ÿ])", r"avantageuse\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])bâtiffeur(s?)(?![A-Za-zÀ-ÿ])", r"bâtisseur\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])diffolution(s?)(?![A-Za-zÀ-ÿ])", r"dissolution\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])défigne(nt)?(?![A-Za-zÀ-ÿ])", r"désigne\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])défigné(e?s?)(?![A-Za-zÀ-ÿ])", r"désigné\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])enfemble(?![A-Za-zÀ-ÿ])", "ensemble", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])enfuite(?![A-Za-zÀ-ÿ])", "ensuite", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])fanglante(s?)(?![A-Za-zÀ-ÿ])", r"sanglante\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])fecourir(?![A-Za-zÀ-ÿ])", "secourir", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])fert(?![A-Za-zÀ-ÿ])", "sert", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])fituation(s?)(?![A-Za-zÀ-ÿ])", r"situation\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])fomme(s?)(?![A-Za-zÀ-ÿ])", r"somme\1", s)

    # 184. païs -> pays
    s = _sub(r"(?<![A-Za-zÀ-ÿ])païs(?![A-Za-zÀ-ÿ])", "pays", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Païs(?![A-Za-zÀ-ÿ])", "Pays", s)

    # 185. sçait / sçavent -> sait / savent
    s = _sub(r"(?<![A-Za-zÀ-ÿ])sçait(?![A-Za-zÀ-ÿ])", "sait", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Sçait(?![A-Za-zÀ-ÿ])", "Sait", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])sçavent(?![A-Za-zÀ-ÿ])", "savent", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Sçavent(?![A-Za-zÀ-ÿ])", "Savent", s)

    # 186. Aléxandre -> Alexandre
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Aléxandre(?![A-Za-zÀ-ÿ])", "Alexandre", s)

    # 187. Ere -> Ère
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Ere(?![A-Za-zÀ-ÿ])", "Ère", s)

    # 188. Ptolomée / Ptolemée -> Ptolémée, Ptolemaïde -> Ptolémaïde
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Ptolomée(?![A-Za-zÀ-ÿ])", "Ptolémée", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Ptolemée(?![A-Za-zÀ-ÿ])", "Ptolémée", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Ptolemaïde(?![A-Za-zÀ-ÿ])", "Ptolémaïde", s)

    # 189. Mute-e tremas & archaic feminines
    s = _sub(r"(?<![A-Za-zÀ-ÿ])tuërent(?![A-Za-zÀ-ÿ])", "tuèrent", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])saluërent(?![A-Za-zÀ-ÿ])", "saluèrent", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Cc])oncluë(s?)(?![A-Za-zÀ-ÿ])", r"\1onclue\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ii])mprévûë(s?)(?![A-Za-zÀ-ÿ])", r"\1mprévue\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ss])uperfluë(s?)(?![A-Za-zÀ-ÿ])", r"\1uperflue\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ff])onduë(s?)(?![A-Za-zÀ-ÿ])", r"\1ondue\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Dd])ésobéïssance(?![A-Za-zÀ-ÿ])", r"\1ésobéissance", s)

    # 190. Long-s OCR
    s = _sub(r"(?<![A-Za-zÀ-ÿ])plufieurs(?![A-Za-zÀ-ÿ])", "plusieurs", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])ainfi(?![A-Za-zÀ-ÿ])", "ainsi", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Ainfi(?![A-Za-zÀ-ÿ])", "Ainsi", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])choifit(?![A-Za-zÀ-ÿ])", "choisit", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])feul(?![A-Za-zÀ-ÿ])", "seul", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])fouverain(s?)(?![A-Za-zÀ-ÿ])", r"souverain\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])furprise(s?)(?![A-Za-zÀ-ÿ])", r"surprise\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])promife(s?)(?![A-Za-zÀ-ÿ])", r"promise\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])propofition(s?)(?![A-Za-zÀ-ÿ])", r"proposition\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])accufa(?![A-Za-zÀ-ÿ])", "accusa", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])accufer(?![A-Za-zÀ-ÿ])", "accuser", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])accufèrent(?![A-Za-zÀ-ÿ])", "accusèrent", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])confeilla(?![A-Za-zÀ-ÿ])", "conseilla", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])confenti(?![A-Za-zÀ-ÿ])", "consenti", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])cuiraffier(s?)(?![A-Za-zÀ-ÿ])", r"cuirassier\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])arbriffeau(x?)(?![A-Za-zÀ-ÿ])", r"arbrisseau\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])difant(?![A-Za-zÀ-ÿ])", "disant", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])difpofition(s?)(?![A-Za-zÀ-ÿ])", r"disposition\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])fale(s?)(?![A-Za-zÀ-ÿ])", r"sale\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])fecours(?![A-Za-zÀ-ÿ])", "secours", s)

    # 191. Capital unaccented initial vowels
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Epiphane(s?)(?![A-Za-zÀ-ÿ])", r"Épiphane\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Epiphan(?![A-Za-zÀ-ÿ])", "Épiphane", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Epiph(?![A-Za-zÀ-ÿ])", "Épiphane", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Emile(?![A-Za-zÀ-ÿ])", "Émile", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Epitome(?![A-Za-zÀ-ÿ])", "Épitomé", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Epitom(?![A-Za-zÀ-ÿ])", "Épitomé", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Eglise(s?)(?![A-Za-zÀ-ÿ])", r"Église\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Elevant(?![A-Za-zÀ-ÿ])", "Élevant", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Elée(?![A-Za-zÀ-ÿ])", "Élée", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Ephese(?![A-Za-zÀ-ÿ])", "Éphèse", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Erasme(?![A-Za-zÀ-ÿ])", "Érasme", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Esaïe(?![A-Za-zÀ-ÿ])", "Ésaïe", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Egypte(?![A-Za-zÀ-ÿ])", "Égypte", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Egyte(?![A-Za-zÀ-ÿ])", "Égypte", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Epire(?![A-Za-zÀ-ÿ])", "Épire", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Ecuyer(?![A-Za-zÀ-ÿ])", "Écuyer", s)

    # === BATCH 5 (Matthieu findings) ===
    # 192. craient -> croient (OCR ligature error)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])craient(?![A-Za-zÀ-ÿ])", "croient", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Craient(?![A-Za-zÀ-ÿ])", "Croient", s)

    # 193. faient -> soient (long-s OCR error)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])faient(?![A-Za-zÀ-ÿ])", "soient", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Faient(?![A-Za-zÀ-ÿ])", "Soient", s)

    # 194. soüet -> fouet
    s = _sub(r"(?<![A-Za-zÀ-ÿ])soüet(s?)(?![A-Za-zÀ-ÿ])", r"fouet\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Soüet(s?)(?![A-Za-zÀ-ÿ])", r"Fouet\1", s)

    # 195. Long-s OCR artifacts
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Dd])i[fs]fertation(s?)(?![A-Za-zÀ-ÿ])", r"\1issertation\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Pp])harifien(s?)(?![A-Za-zÀ-ÿ])", r"\1harisien\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Mm])agiftrat(s?)(?![A-Za-zÀ-ÿ])", r"\1agistrat\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ss])candalife(r?z?)(?![A-Za-zÀ-ÿ])", r"\1candalise\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Aa])ssoupiffant(e?s?)(?![A-Za-zÀ-ÿ])", r"\1ssoupissant\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Aa])utorifer(?![A-Za-zÀ-ÿ])", r"\1utoriser", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Cc])irconfpection(?![A-Za-zÀ-ÿ])", r"\1irconspection", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Cc])onduifit(?![A-Za-zÀ-ÿ])", r"\1onduisit", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Dd])ifions(?![A-Za-zÀ-ÿ])", r"\1isions", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ee])nfeigne(r?z?)(?![A-Za-zÀ-ÿ])", r"\1nseigne\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])favaient(?![A-Za-zÀ-ÿ])", "savaient", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Favaient(?![A-Za-zÀ-ÿ])", "Savaient", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])fourd(s?)(?![A-Za-zÀ-ÿ])", r"sourd\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Fourd(s?)(?![A-Za-zÀ-ÿ])", r"Sourd\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])furnom(s?)(?![A-Za-zÀ-ÿ])", r"surnom\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Furnom(s?)(?![A-Za-zÀ-ÿ])", r"Surnom\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ii])nstruifait(?![A-Za-zÀ-ÿ])", r"\1nstruisait", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])pardeffus(?![A-Za-zÀ-ÿ])", "pardessus", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Pardeffus(?![A-Za-zÀ-ÿ])", "Pardessus", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])affermifsait(?![A-Za-zÀ-ÿ])", "affermissait", s)

    # 196. Archaic adverbs & accents
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Aa])venement(s?)(?![A-Za-zÀ-ÿ])", r"\1vènement\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Pp])romtement(?![A-Za-zÀ-ÿ])", r"\1romptement", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ss])ecrettement(?![A-Za-zÀ-ÿ])", r"\1ecrètement", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Vv])eritablement(?![A-Za-zÀ-ÿ])", r"\1éritablement", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ee])xpressement(?![A-Za-zÀ-ÿ])", r"\1xpressément", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Rr])éguliérement(?![A-Za-zÀ-ÿ])", r"\1égulièrement", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Aa])mérement(?![A-Za-zÀ-ÿ])", r"\1mèrement", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ff])amiliérement(?![A-Za-zÀ-ÿ])", r"\1amilièrement", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ii])ndifferemment(?![A-Za-zÀ-ÿ])", r"\1ndifféremment", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ll])égérement(?![A-Za-zÀ-ÿ])", r"\1égèrement", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Pp])remierement(?![A-Za-zÀ-ÿ])", r"\1remièrement", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ss])incérement(?![A-Za-zÀ-ÿ])", r"\1incèrement", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Vv])iolement(?![A-Za-zÀ-ÿ])", r"\1iolemment", s)

    # 197. Archaic imperfect / conditional endings (-oient -> -aient)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Cc])royoient(?![A-Za-zÀ-ÿ])", r"\1royaient", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Rr])essusciteroient(?![A-Za-zÀ-ÿ])", r"\1essusciteraient", s)

    # 198. Tremas & feminine endings
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Nn])uëe(s?)(?![A-Za-zÀ-ÿ])", r"\1uée\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ss])aluë(?![A-Za-zÀ-ÿ])", r"\1alue", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ss])alüez(?![A-Za-zÀ-ÿ])", r"\1aluez", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Aa])pparuë(s?)(?![A-Za-zÀ-ÿ])", r"\1pparue\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Rr])econnuë(s?)(?![A-Za-zÀ-ÿ])", r"\1econnue\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Cc])ombattuë(s?)(?![A-Za-zÀ-ÿ])", r"\1ombattue\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Cc])onvaincuë(s?)(?![A-Za-zÀ-ÿ])", r"\1onvaincue\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Jj])ouïssent(?![A-Za-zÀ-ÿ])", r"\1ouissent", s)

    # 199. Capital unaccented E
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Etre(?![A-Za-zÀ-ÿ])", "Être", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Epileptique(s?)(?![A-Za-zÀ-ÿ])", r"Épileptique\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Elisabeth(?![A-Za-zÀ-ÿ])", "Élisabeth", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Elû(s?)(?![A-Za-zÀ-ÿ])", r"Élu\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Etoile(s?)(?![A-Za-zÀ-ÿ])", r"Étoile\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Evitez(?![A-Za-zÀ-ÿ])", "Évitez", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Econome(s?)(?![A-Za-zÀ-ÿ])", r"Économe\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Eloge(s?)(?![A-Za-zÀ-ÿ])", r"Éloge\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Epargnez(?![A-Za-zÀ-ÿ])", "Épargnez", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Esope(?![A-Za-zÀ-ÿ])", "Ésope", s)

    # === BATCH 6 (21c_psaumes findings) ===
    # 200. Eusebe -> Eusèbe
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Eusebe(?![A-Za-zÀ-ÿ])", "Eusèbe", s)

    # 201. Origénes -> Origène
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Origénes(?![A-Za-zÀ-ÿ])", "Origène", s)

    # 202. systême(s) -> système(s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ss])ystême(s?)(?![A-Za-zÀ-ÿ])", r"\1ystème\2", s)

    # 203. Long-s OCR artifacts
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Pfalmiste(s?)(?![A-Za-zÀ-ÿ])", r"Psalmiste\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Dd])efcendre(?![A-Za-zÀ-ÿ])", r"\1escendre", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ii])mpofez(?![A-Za-zÀ-ÿ])", r"\1mposez", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Aa])ccufent(?![A-Za-zÀ-ÿ])", r"\1ccusent", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Cc])onfumer(?![A-Za-zÀ-ÿ])", r"\1onsumer", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Gg])uériffant(?![A-Za-zÀ-ÿ])", r"\1uérissant", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Tt])ranquillifez(?![A-Za-zÀ-ÿ])", r"\1ranquillisez", s)

    # 204. Mute-e & Tréma normalizations
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Pp])oëtique(s?)(?![A-Za-zÀ-ÿ])", r"\1oétique\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Tt])ortuë(s?)(?![A-Za-zÀ-ÿ])", r"\1ortue\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Gg])renouïlle(s?)(?![A-Za-zÀ-ÿ])", r"\1renouille\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Tt])ouffuë(s?)(?![A-Za-zÀ-ÿ])", r"\1ouffue\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Pp])ointuë(s?)(?![A-Za-zÀ-ÿ])", r"\1ointue\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ll])ouëz(?![A-Za-zÀ-ÿ])", r"\1ouez", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ll])ouëront(?![A-Za-zÀ-ÿ])", r"\1oueront", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ii])nsinuënt(?![A-Za-zÀ-ÿ])", r"\1nsinuent", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Aa])ttribüent(?![A-Za-zÀ-ÿ])", r"\1ttribuent", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Aa])ttribuënt(?![A-Za-zÀ-ÿ])", r"\1ttribuent", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ff])ondüë(s?)(?![A-Za-zÀ-ÿ])", r"\1ondue\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Rr])ompüe(s?)(?![A-Za-zÀ-ÿ])", r"\1ompue\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ss])outenuë(s?)(?![A-Za-zÀ-ÿ])", r"\1outenue\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Rr])éjouïsse(s?)(?![A-Za-zÀ-ÿ])", r"\1éjouisse\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Rr])éïtéré(e?s?)(?![A-Za-zÀ-ÿ])", r"\1éitéré\2", s)

    # 205. Archaic spelling & accents
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ss])olemnellement(?![A-Za-zÀ-ÿ])", r"\1olennellement", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ee])nlévement(s?)(?![A-Za-zÀ-ÿ])", r"\1nlèvement\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ss])oulévement(s?)(?![A-Za-zÀ-ÿ])", r"\1oulèvement\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ll])isoient(?![A-Za-zÀ-ÿ])", r"\1isaient", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Cc])ouvroient(?![A-Za-zÀ-ÿ])", r"\1ouvraient", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Aa])ssûrément(?![A-Za-zÀ-ÿ])", r"\1ssurément", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ii])mmediatement(?![A-Za-zÀ-ÿ])", r"\1mmédiatement", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Pp])articulierement(?![A-Za-zÀ-ÿ])", r"\1articulièrement", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Pp])erpetuellement(?![A-Za-zÀ-ÿ])", r"\1erpétuellement", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Pp])réferablement(?![A-Za-zÀ-ÿ])", r"\1référablement", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Rr])afraichissement(s?)(?![A-Za-zÀ-ÿ])", r"\1afraîchissement\2", s)

    # 206. Capital unaccented E
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Elevez(?![A-Za-zÀ-ÿ])", "Élevez", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Etablissez(?![A-Za-zÀ-ÿ])", "Établissez", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Etres(?![A-Za-zÀ-ÿ])", "Êtres", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Elément(s?)(?![A-Za-zÀ-ÿ])", r"Élément\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Elever(?![A-Za-zÀ-ÿ])", "Élever", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Epigramme(s?)(?![A-Za-zÀ-ÿ])", r"Épigramme\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Episcopat(s?)(?![A-Za-zÀ-ÿ])", r"Épiscopat\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Epithalame(s?)(?![A-Za-zÀ-ÿ])", r"Épithalame\1", s)

    # === BATCH 7 (21b_psaumes findings) ===
    # 207. fraïeur / bruïant / deüil / orgüeillex
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ff])raïeur(s?)(?![A-Za-zÀ-ÿ])", r"\1rayeur\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Bb])ruïant(e?s?)(?![A-Za-zÀ-ÿ])", r"\1ruyant\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Dd])eüil(s?)(?![A-Za-zÀ-ÿ])", r"\1euil\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Oo])rgüeillex(?![A-Za-zÀ-ÿ])", r"\1rgueilleux", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Oo])rgüeuillement(?![A-Za-zÀ-ÿ])", r"\1rgueilleusement", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])quatre-vingt-fix(?![A-Za-zÀ-ÿ])", "quatre-vingt-six", s)

    # 208. Archaic adverbs, accents & endings
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Cc])hérement(?![A-Za-zÀ-ÿ])", r"\1hèrement", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ff])iérement(?![A-Za-zÀ-ÿ])", r"\1ièrement", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ss])échement(?![A-Za-zÀ-ÿ])", r"\1èchement", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Éé])perdûment(?![A-Za-zÀ-ÿ])", r"\1perdument", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Dd])évoûment(s?)(?![A-Za-zÀ-ÿ])", r"\1évouement\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Aa])gréement(s?)(?![A-Za-zÀ-ÿ])", r"\1grément\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Pp])iquotement(s?)(?![A-Za-zÀ-ÿ])", r"\1icotement\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Pp])ourroit(?![A-Za-zÀ-ÿ])", r"\1ourrait", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Dd])evroit(?![A-Za-zÀ-ÿ])", r"\1evrait", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Pp])leuroit(?![A-Za-zÀ-ÿ])", r"\1leurait", s)

    # 209. Long-s OCR artifacts
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ff])ufpendu(e?s?)(?![A-Za-zÀ-ÿ])", r"suspendu\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])fuivrons(?![A-Za-zÀ-ÿ])", "suivrons", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Fuivrons(?![A-Za-zÀ-ÿ])", "Suivrons", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ff])éparément(?![A-Za-zÀ-ÿ])", r"séparément", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ff])épulture(s?)(?![A-Za-zÀ-ÿ])", r"sépulture\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Hh])iftoire(s?)(?![A-Za-zÀ-ÿ])", r"\1istoire\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])néceffaire(s?)(?![A-Za-zÀ-ÿ])", r"nécessaire\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Néceffaire(s?)(?![A-Za-zÀ-ÿ])", r"Nécessaire\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Pp])ompeufe(s?)(?![A-Za-zÀ-ÿ])", r"\1ompeuse\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])difais(?![A-Za-zÀ-ÿ])", "disais", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])favoir(?![A-Za-zÀ-ÿ])", "savoir", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])fentirons(?![A-Za-zÀ-ÿ])", "sentirons", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])fept(?![A-Za-zÀ-ÿ])", "sept", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])fortait(?![A-Za-zÀ-ÿ])", "sortait", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])foyez(?![A-Za-zÀ-ÿ])", "soyez", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Foyez(?![A-Za-zÀ-ÿ])", "Soyez", s)

    # 210. Capital unaccented E
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([LlDd]['’])Eté(?![A-Za-zÀ-ÿ])", r"\1Été", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Eclairez(?![A-Za-zÀ-ÿ])", "Éclairez", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Egyptien(s?)(?![A-Za-zÀ-ÿ])", r"Égyptien\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Ethiopien(s?)(?![A-Za-zÀ-ÿ])", r"Éthiopien\1", s)

    # === BATCH 8 (21a_psaumes findings) ===
    # 211. Mute-e & Tréma normalizations
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Dd])istribuë", r"\1istribue", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ss])ecouë", r"\1ecoue", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ll])ûë(s?)(?![A-Za-zÀ-ÿ])", r"\1ue\2", s)

    # 212. Archaic adverbs & accents
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ss])évérement(?![A-Za-zÀ-ÿ])", r"\1évèrement", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ff])idellement(?![A-Za-zÀ-ÿ])", r"\1idèlement", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Gg])rossiérement(?![A-Za-zÀ-ÿ])", r"\1rossièrement", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Aa])chopement(s?)(?![A-Za-zÀ-ÿ])", r"\1choppement\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ii])nterieurement(?![A-Za-zÀ-ÿ])", r"\1ntérieurement", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Tt])roisiémement(?![A-Za-zÀ-ÿ])", r"\1roisièmement", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Aa])ssujetissement(s?)(?![A-Za-zÀ-ÿ])", r"\1ssujettissement\2", s)

    # 213. Archaic verb endings (-oient -> -aient)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])étoient(?![A-Za-zÀ-ÿ])", "étaient", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Étoient(?![A-Za-zÀ-ÿ])", "Étaient", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Dd])emeuroient(?![A-Za-zÀ-ÿ])", r"\1emeuraient", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Pp])ortoient(?![A-Za-zÀ-ÿ])", r"\1ortaient", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ff])audroit(?![A-Za-zÀ-ÿ])", r"\1audrait", s)

    # 214. Long-s OCR artifacts
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ee])ftime(s?)(?![A-Za-zÀ-ÿ])", r"\1stime\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Cc])onfidér", r"\1onsidér", s)

    # 215. Capital unaccented E
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Element(s?)(?![A-Za-zÀ-ÿ])", r"Élément\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Eclairer(?![A-Za-zÀ-ÿ])", "Éclairer", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Elisa(?![A-Za-zÀ-ÿ])", "Élisa", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Eloï(?![A-Za-zÀ-ÿ])", "Éloi", s)

    # === BATCH 9 (20_job findings) ===
    # 216. Archaic verb endings (-oit / -oient -> -ait / -aient)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Aa])voit(?![A-Za-zÀ-ÿ])", r"\1vait", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Aa])voient(?![A-Za-zÀ-ÿ])", r"\1vaient", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ll])isoit(?![A-Za-zÀ-ÿ])", r"\1isait", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Dd])emeuroit(?![A-Za-zÀ-ÿ])", r"\1emeurait", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Mm])ontroit(?![A-Za-zÀ-ÿ])", r"\1ontrait", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Aa])ppelloit(?![A-Za-zÀ-ÿ])", r"\1ppelait", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Aa])ppelloient(?![A-Za-zÀ-ÿ])", r"\1ppelaient", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ss])ervoit(?![A-Za-zÀ-ÿ])", r"\1ervait", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Vv])ouloient(?![A-Za-zÀ-ÿ])", r"\1oulaient", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])étoit(?![A-Za-zÀ-ÿ])", "était", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Étoit(?![A-Za-zÀ-ÿ])", "Était", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ss])eroit(?![A-Za-zÀ-ÿ])", r"\1erait", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Pp])ortoit(?![A-Za-zÀ-ÿ])", r"\1ortait", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Vv])enoit(?![A-Za-zÀ-ÿ])", r"\1enait", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Vv])enoient(?![A-Za-zÀ-ÿ])", r"\1enaient", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Vv])oudroient(?![A-Za-zÀ-ÿ])", r"\1oudraient", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Rr])endoit(?![A-Za-zÀ-ÿ])", r"\1endait", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Vv])ivoient(?![A-Za-zÀ-ÿ])", r"\1ivaient", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Aa])uroit(?![A-Za-zÀ-ÿ])", r"\1urait", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Aa])lloit(?![A-Za-zÀ-ÿ])", r"\1llait", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Dd])onnoit(?![A-Za-zÀ-ÿ])", r"\1onnait", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ff])alloit(?![A-Za-zÀ-ÿ])", r"\1allait", s)

    # 217. Future forms of -lever (-lever* -> -lèver*)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ss])ouleveron([ts])(?![A-Za-zÀ-ÿ])", r"\1oulèveron\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ss])oulevera(?![A-Za-zÀ-ÿ])", r"\1oulèvera", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ee])nleveron([ts])(?![A-Za-zÀ-ÿ])", r"\1nlèveron\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ee])nlevera(?![A-Za-zÀ-ÿ])", r"\1nlèvera", s)

    # 218. Specific OCR & accent corrections
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Eugéne(?![A-Za-zÀ-ÿ])", "Eugène", s)

    # === BATCH 10 (spellcheck.py findings, Job to Matthieu) ===
    # 219. -oi- of the stem made -ai- by the -oit -> -ait modernization
    s = _sub(r"(?<![A-Za-zÀ-ÿ\-\xad])([Vv])aient(?![A-Za-zÀ-ÿ])", r"\1oient", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ\-\xad])([Ee])mplais(?![A-Za-zÀ-ÿ])", r"\1mplois", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ\-\xad])([Ee])mplaient(?![A-Za-zÀ-ÿ])", r"\1mploient", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ\-\xad])([Ee])nvaient(?![A-Za-zÀ-ÿ])", r"\1nvoient", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ\-\xad])bait(?![A-Za-zÀ-ÿ])", "boit", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ\-\xad])([Dd])étrait(?![A-Za-zÀ-ÿ])", r"\1étroit", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ\-\xad])conçais(?![A-Za-zÀ-ÿ])", "conçois", s)

    # 220. envoye / employe -> envoie / emploie; envoyerai -> enverrai
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ee])nvoye(nt|s?)(?![A-Za-zÀ-ÿ])", r"\1nvoie\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ee])mploye(nt|s?)(?![A-Za-zÀ-ÿ])", r"\1mploie\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ee])nvoyer(ai|as|a|ons|ez|ont|ais|ait|ions|iez|aient)(?![A-Za-zÀ-ÿ])", r"\1nverr\2", s)

    # 221. Long s: je sai / je ne fai -> je sais; fix -> six
    s = _sub(r"(?<![A-Za-zÀ-ÿ'’])sai(?![A-Za-zÀ-ÿ-])", "sais", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Jj]e|ne)\s+fai(?![A-Za-zÀ-ÿ-])", r"\1 sais", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])fix(?![A-Za-zÀ-ÿ])", "six", s)

    # 222. Old spellings and accents
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Bb])lasphême(s?)(?![A-Za-zÀ-ÿ])", r"\1lasphème\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Bb])lasphêm", r"\1lasphém", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ss])oût(en|ien)", r"\1out\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ii])nterêt(s?)(?![A-Za-zÀ-ÿ])", r"\1ntérêt\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Pp])articuliere(s?|ment)(?![A-Za-zÀ-ÿ])", r"\1articulière\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Pp])ossed(é|ée|és|ées|er|ait|aient|ant|ons|ez)(?![A-Za-zÀ-ÿ])", r"\1osséd\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Aa])usquel(le)?s(?![A-Za-zÀ-ÿ])", r"\1uxquel\2s", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ss])olemnité(s?)(?![A-Za-zÀ-ÿ])", r"\1olennité\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])plû(?![A-Za-zÀ-ÿ]|\s*ôt)", "plu", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])conçû(?![A-Za-zÀ-ÿ])", "conçu", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Pp])ourvû(?![A-Za-zÀ-ÿ])", r"\1ourvu", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ee])spece(s?)(?![A-Za-zÀ-ÿ])", r"\1spèce\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])plurier(?![A-Za-zÀ-ÿ])", "pluriel", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])(ils|elles)\s+different(?![A-Za-zÀ-ÿ])", r"\1 diffèrent", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Dd])ifferent(s?)(?![A-Za-zÀ-ÿ])", r"\1ifférent\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ_])méne(?![A-Za-zÀ-ÿ])", "mène", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Rr])améne(?![A-Za-zÀ-ÿ])", r"\1amène", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Rr])elévent(?![A-Za-zÀ-ÿ])", r"\1elèvent", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Rr])appell(é|ée|és|ées|er)(?![A-Za-zÀ-ÿ])", r"\1appel\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])descens(?![A-Za-zÀ-ÿ])", "descends", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])exprés(?![A-Za-zÀ-ÿ])", "exprès", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ss])çu(t|rent)(?![A-Za-zÀ-ÿ])", r"\1u\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Pp])anch(er|é|ée|e|es|ent|ait|aient|ant)(?![A-Za-zÀ-ÿ])", r"\1ench\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])asseyer(ai|as|a|ons|ez|ont|ais|ait|aient)(?![A-Za-zÀ-ÿ])", r"assiér\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Dd])ixme(s?)(?![A-Za-zÀ-ÿ])", r"\1îme\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Dd])ragme(s?)(?![A-Za-zÀ-ÿ])", r"\1rachme\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])deça(?![A-Za-zÀ-ÿ])", "deçà", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])grincemens(?![A-Za-zÀ-ÿ])", "grincements", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ll])uimême(?![A-Za-zÀ-ÿ])", r"\1ui-même", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Éé])tendart(s?)(?![A-Za-zÀ-ÿ])", r"\1tendard\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])lescive(?![A-Za-zÀ-ÿ])", "lessive", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Aa])vantur(e|es|ier|iers)(?![A-Za-zÀ-ÿ])", r"\1ventur\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ee])nsorte(?![A-Za-zÀ-ÿ])", r"\1n sorte", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Dd])'enhaut(?![A-Za-zÀ-ÿ])", r"\1'en haut", s)

    # === BATCH 11 (names, modern forms) ===
    # 223. Trémas the modern names do not have
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ii])sraëlite(s?)(?![A-Za-zÀ-ÿ])", r"\1sraélite\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ii])smaëlite(s?)(?![A-Za-zÀ-ÿ])", r"\1smaélite\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Samuël(?![A-Za-zÀ-ÿ])", "Samuel", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Emmanuël(?![A-Za-zÀ-ÿ])", "Emmanuel", s)

    # 224. Old forms of names; but the user keeps Calmet's Machabées, as footnotes.py and bible_refs
    # write it (the LLM pass modernizes it)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Maccabée(s?)(?![A-Za-zÀ-ÿ])", r"Machabée\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Balthasar(?![A-Za-zÀ-ÿ])", "Balthazar", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Caldée(?![A-Za-zÀ-ÿ])", "Chaldée", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Hircan(?![A-Za-zÀ-ÿ])", "Hyrcan", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Appion(?![A-Za-zÀ-ÿ])", "Apion", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Sathan(?![A-Za-zÀ-ÿ])", "Satan", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Moloc(?![A-Za-zÀ-ÿ])", "Moloch", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Troye(?![A-Za-zÀ-ÿ])", "Troie", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Lybie(ns?)?(?![A-Za-zÀ-ÿ])", r"Libye\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Cypre(?![A-Za-zÀ-ÿ])", "Chypre", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Sabbath(?![A-Za-zÀ-ÿ])", "Sabbat", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Nabathéen(s?)(?![A-Za-zÀ-ÿ])", r"Nabatéen\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Massorette(s?)(?![A-Za-zÀ-ÿ])", r"Massorète\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Carthaginais(?![A-Za-zÀ-ÿ])", "Carthaginois", s)

    # 225. Accents missing on capitals and names
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Hebreu(x?)(?![A-Za-zÀ-ÿ])", r"Hébreu\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Béde(?![A-Za-zÀ-ÿ])", "Bède", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Prophete(s?)(?![A-Za-zÀ-ÿ])", r"Prophète\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Genese(?![A-Za-zÀ-ÿ])", "Genèse", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Deuteronome(?![A-Za-zÀ-ÿ])", "Deutéronome", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Paralipomenes(?![A-Za-zÀ-ÿ])", "Paralipomènes", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Grece(?![A-Za-zÀ-ÿ])", "Grèce", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Homere(?![A-Za-zÀ-ÿ])", "Homère", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Séneque(?![A-Za-zÀ-ÿ])", "Sénèque", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Juvenal(?![A-Za-zÀ-ÿ])", "Juvénal", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Xenophon(?![A-Za-zÀ-ÿ])", "Xénophon", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Ciceron(?![A-Za-zÀ-ÿ])", "Cicéron", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Clement(?![A-Za-zÀ-ÿ])", "Clément", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Barthelemy(?![A-Za-zÀ-ÿ])", "Barthélemy", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Sanhedrin(?![A-Za-zÀ-ÿ])", "Sanhédrin", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Ecrivain(s?)(?![A-Za-zÀ-ÿ])", r"Écrivain\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Ecclesiastique(?![A-Za-zÀ-ÿ])", "Ecclésiastique", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Evangeliste(s?)(?![A-Za-zÀ-ÿ])", r"Évangéliste\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Jehovah(?![A-Za-zÀ-ÿ])", "Jéhovah", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Cyréne(?![A-Za-zÀ-ÿ])", "Cyrène", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Medes(?![A-Za-zÀ-ÿ])", "Mèdes", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Otez(?![A-Za-zÀ-ÿ])", "Ôtez", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])Eviter(?![A-Za-zÀ-ÿ])", "Éviter", s)

    # 226. Soft hyphens left from the printer's line breaks (de­venus): invisible, but they break search
    s = _sub("\xad", "", s)

    # === BATCH 12 ===
    # 227. sç -> s (sçavoir, sçachant, sçaura, insçu); the forms that change more first
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ss])çai(s?)(?![A-Za-zÀ-ÿ])", r"\1ais", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ss])çeu(t|rent)(?![A-Za-zÀ-ÿ])", r"\1u\2", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ss])çroit(?![A-Za-zÀ-ÿ])", r"\1aurait", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ss])çûss", r"\1uss", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ss])ç(?=[aeiouû])", r"\1", s)
    s = _sub(r"(?<![A-Za-zÀ-ÿ])([Ii])nsç[uû](e?s?)(?![A-Za-zÀ-ÿ])", r"\1nsu\2", s)

    # 228. An accent stored apart from its letter (d'Alphée as e + U+0301): made one character
    s = _sub(r"[aeiouyAEIOUY][̀-̃̈]|[cC]̧|[nN]̃", lambda m: unicodedata.normalize("NFC", m.group()), s)

    # 229. Old spellings word by word, from spelling_words.txt (vîte, élûs, continuëra): one pass
    # with a dictionary instead of a rule per word
    s = TABLE_WORD.sub(lambda m: WORD_TABLE.get(m.group(), m.group()), s)
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
        "book_end_marker",
    ):
        v = d.get(k)
        if v and isinstance(v, str):
            v2 = fix_spelling(v)
            if v2 != v:
                d[k] = v2
                changed = True

    # Verses
    for i, v in enumerate(d.get("verses", [])):
        s = v.get("french")
        if s and isinstance(s, str):
            s2 = keep_printed(fix_spelling, s, lead=i == 0)
            if s2 != s:
                v["french"] = s2
                changed = True

    # Footnotes
    for fn in d.get("footnotes", []):
        t = fn.get("text")
        if t and isinstance(t, str):
            t2 = keep_printed(fix_spelling, t)
            if t2 != t:
                fn["text"] = t2
                changed = True

    for i, c in enumerate(d.get("commentary", [])):
        # 1. Spaced letters and spelling
        for k in ("french_translation", "french_commentary"):
            s = c.get(k)
            if s:
                s2 = fix_spaced_letters(s)
                s2 = keep_printed(fix_spelling, s2, lead=i == 0)
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
            # With no translation to carry it, the call stays: at the top of a continuation it
            # belongs to the last word of the page before, and dropping it loses the note.
            if m and c.get("french_translation"):
                # If french_translation exists, move it to end of french_translation
                call_str = m.group(1)
                c["french_commentary"] = fc[m.end():]
                tr = c.get("french_translation")
                if tr and call_str not in tr:
                    c["french_translation"] = tr.rstrip() + " " + call_str
                changed = True

    return changed


def _clean_one_page(args):
    """Returns (changed, error message or None)."""
    path_str, dry = args
    try:
        p = Path(path_str)
        d = json.loads(p.read_text(encoding="utf-8"))
        if clean_page(d):
            if not dry:
                p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
            return 1, None
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"
    return 0, None


def main(argv):
    dry = "--dry-run" in argv
    vols = [a for a in argv if not a.startswith("--")] or sorted(
        p.name for p in DATA.iterdir() if (p / "normalized").is_dir()
    )

    total_changed = 0
    total_failed = 0
    with ProcessPoolExecutor() as executor:
        for vol in vols:
            vol_pages = [(str(p), dry) for p in pages(vol)]
            results = list(executor.map(_clean_one_page, vol_pages))
            vol_changed = sum(changed for changed, _ in results)
            total_changed += vol_changed
            for (path_str, _), (_, err) in zip(vol_pages, results):
                if err:
                    total_failed += 1
                    print(f"  ERROR {Path(path_str).relative_to(DATA)}: {err}", file=sys.stderr, flush=True)
            print(f"{vol}: {vol_changed} pages updated{' (dry run)' if dry else ''}", flush=True)

    print(f"Total: {total_changed} pages updated", flush=True)
    if total_failed:
        print(f"{total_failed} pages failed (see errors above)", file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
