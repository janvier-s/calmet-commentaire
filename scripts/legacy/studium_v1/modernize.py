#!/usr/bin/env python3
"""
Modernize 17th-century French and Latin orthography in biblical commentary JSON files.

Directory structure per book:
- Source:  {BOOK}/raw_json/commentaire
- Staging: {BOOK}/21st_claude_staging/commentaire
- Final:   {BOOK}/21st_claude/commentaire

Two-phase process:
1. Preprocessing (this script): Mechanical transformations (~80%)
2. LLM Review: Contextual intelligence for edge cases (~20%)

Usage:
    python3 modernize.py <book_name>
    python3 modernize.py 09_1_rois
"""

import json
import os
import sys
import re
import unicodedata
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional


# =============================================================================
# BASE PATH
# =============================================================================

BASE_PATH = "/Users/Janvier/Library/Mobile Documents/com~apple~CloudDocs/for-the-kingdom/STUDIUM/data"


# =============================================================================
# COMPILED REGEX PATTERNS
# =============================================================================

# Capitalization fixes (FRENCH ONLY)
RE_DOUBLE_CAPITAL = re.compile(
    r"\b([A-ZÀÂÄÆÇÉÈÊËÏÎÔŒÙÛÜ]{2})([a-zàâäæçéèêëïîôœùûü]+)", flags=re.UNICODE
)
RE_APOSTROPHE_CAPITAL = re.compile(
    r"\b([A-ZÀÂÄÆÇÉÈÊËÏÎÔŒÙÛÜ])'([A-ZÀÂÄÆÇÉÈÊËÏÎÔŒÙÛÜ])([a-zàâäæçéèêëïîôœùûü]*)",
    flags=re.UNICODE,
)

# Word ending: éme → ème (même, extrême, etc.) - safe with word boundary
RE_WORD_ENDING_EME = re.compile(r"([^é])éme\b", flags=re.UNICODE)


# =============================================================================
# OCR ERROR CORRECTIONS: f → s
# =============================================================================
# OCR often misreads ſ (long s) as f. These are CURATED words only.
# We use word boundaries to avoid false positives.

OCR_F_TO_S_WORDS: Dict[str, str] = {
    # --- Double-f patterns (very reliable - "ff" for "ss" was common OCR error) ---
    "auffi": "aussi",
    "affez": "assez",
    "auffitôt": "aussitôt",
    "auffi-tôt": "aussitôt",
    "néceffaire": "nécessaire",
    "néceffité": "nécessité",
    "profeffion": "profession",
    "profeffeur": "professeur",
    "poffeder": "posséder",
    "poffédé": "possédé",
    "poffeffion": "possession",
    "expreffion": "expression",
    "impreffion": "impression",
    "paffage": "passage",
    "paffer": "passer",
    "paffé": "passé",
    "paffoit": "passait",
    "paffoient": "passaient",
    "pouffé": "poussé",
    "pouffer": "pousser",
    "laiffé": "laissé",
    "laiffer": "laisser",
    "laiffoit": "laissait",
    "laiffoient": "laissaient",
    "confeffer": "confesser",
    "confeffion": "confession",
    "meffage": "message",
    "meffager": "messager",
    "promeffe": "promesse",
    "fageffe": "sagesse",
    "foibleffe": "faiblesse",
    "richeffe": "richesse",
    "jufteffe": "justesse",
    "princeffe": "princesse",
    "déeffe": "déesse",
    # --- Medial f→s (high confidence words only) ---
    "ainfi": "ainsi",
    "feul": "seul",
    "feule": "seule",
    "feuls": "seuls",
    "feules": "seules",
    "feulement": "seulement",
    "felon": "selon",
    "fens": "sens",
    "fentir": "sentir",
    "fentoit": "sentait",
    "fentoient": "sentaient",
    "fentiment": "sentiment",
    "fentimens": "sentiments",
    "fervir": "servir",
    "fervoit": "servait",
    "fervoient": "servaient",
    "fervice": "service",
    "ferviteur": "serviteur",
    "ferviteurs": "serviteurs",
    "fecret": "secret",
    "fecrets": "secrets",
    "fecrète": "secrète",
    "fiecle": "siècle",
    "fiecles": "siècles",
    "fociété": "société",
    "fouvent": "souvent",
    "fujet": "sujet",
    "fujets": "sujets",
    "fuivre": "suivre",
    "fuivoit": "suivait",
    "fuivoient": "suivaient",
    "fuivi": "suivi",
    "fuite": "suite",
    "fuppofé": "supposé",
    "fuppofer": "supposer",
    "fuppofoit": "supposait",
    "fuffifant": "suffisant",
    "fuffifamment": "suffisamment",
    "efprit": "esprit",
    "efprits": "esprits",
    "efpérer": "espérer",
    "efpéroit": "espérait",
    "efpérance": "espérance",
    "efpece": "espèce",
    "efpeces": "espèces",
    "enfuite": "ensuite",
    "defir": "désir",
    "defirs": "désirs",
    "defirer": "désirer",
    "defiroit": "désirait",
    "réfolu": "résolu",
    "réfoudre": "résoudre",
    "réfolution": "résolution",
    "vifage": "visage",
    "vifages": "visages",
    "vifible": "visible",
    "vifion": "vision",
    "maifon": "maison",
    "maifons": "maisons",
    "faifon": "saison",
    "faifons": "saisons",
    "raifon": "raison",
    "raifonnable": "raisonnable",
    "occafion": "occasion",
    "occafions": "occasions",
    "prifon": "prison",
    "prifonnier": "prisonnier",
    "poifon": "poison",
    "chofe": "chose",
    "chofes": "choses",
    "caufe": "cause",
    "caufes": "causes",
    "caufer": "causer",
    "paufe": "pause",
    "claufe": "clause",
    "ufage": "usage",
    "ufages": "usages",
    "ufé": "usé",
    "ufer": "user",
    "refufer": "refuser",
    "refufé": "refusé",
    "refufoit": "refusait",
    "accufer": "accuser",
    "accufé": "accusé",
    "accufation": "accusation",
    "excufer": "excuser",
    "excufe": "excuse",
    # --- Proper nouns (very safe) ---
    "Ifraël": "Israël",
    "Ifraëlites": "Israélites",
    "Jéfus": "Jésus",
    "Jefus": "Jésus",
    "Moïfe": "Moïse",
    "Moyfe": "Moïse",
    "Moyse": "Moïse",  # Non-OCR archaic spelling
    "Jofué": "Josué",
    "Jofeph": "Joseph",
    "Ifaïe": "Isaïe",
    "Ifaac": "Isaac",
    "Jérufalem": "Jérusalem",
    "Jerufalem": "Jérusalem",
    "Samüel": "Samuel",
    "Salömon": "Salomon",
}


# =============================================================================
# VERB CONJUGATIONS: -oit → -ait (IMPERFECT TENSE)
# =============================================================================
# Only explicit verbs - no suffix patterns (too risky: reçoit, prévoit, Benoit)

VERBS_OIT_TO_AIT: Dict[str, str] = {
    # --- être, avoir, faire, pouvoir, vouloir, devoir, savoir ---
    "avoit": "avait",
    "avoient": "avaient",
    "étoit": "était",
    "étoient": "étaient",
    "faisoit": "faisait",
    "faisoient": "faisaient",
    "pouvoit": "pouvait",
    "pouvoient": "pouvaient",
    "vouloit": "voulait",
    "vouloient": "voulaient",
    "devoit": "devait",
    "devoient": "devaient",
    "savoit": "savait",
    "savoient": "savaient",
    # --- Common motion/state verbs ---
    "venoit": "venait",
    "venoient": "venaient",
    "alloit": "allait",
    "alloient": "allaient",
    "restoit": "restait",
    "restoient": "restaient",
    "entroit": "entrait",
    "entroient": "entraient",
    "sortoit": "sortait",
    "sortoient": "sortaient",
    "passoit": "passait",
    "passoient": "passaient",
    "arrivoit": "arrivait",
    "arrivoient": "arrivaient",
    "retournoit": "retournait",
    "retournoient": "retournaient",
    "demeuroit": "demeurait",
    "demeuroient": "demeuraient",
    # --- Communication verbs ---
    "disoit": "disait",
    "disoient": "disaient",
    "parloit": "parlait",
    "parloient": "parlaient",
    "répondoit": "répondait",
    "répondoient": "répondaient",
    "demandoit": "demandait",
    "demandoient": "demandaient",
    "appeloit": "appelait",
    "appeloient": "appelaient",
    "appelloit": "appelait",  # Double-l variant
    "appelloient": "appelaient",
    "crioit": "criait",
    "crioient": "criaient",
    "prioit": "priait",
    "prioient": "priaient",
    # --- Perception/cognition verbs ---
    "voyoit": "voyait",
    "voyoient": "voyaient",
    "croyoit": "croyait",
    "croyoient": "croyaient",
    "pensoit": "pensait",
    "pensoient": "pensaient",
    "trouvoit": "trouvait",
    "trouvoient": "trouvaient",
    "connoissoit": "connaissait",
    "connoissoient": "connaissaient",
    "paroissoit": "paraissait",
    "paroissoient": "paraissaient",
    "sembloit": "semblait",
    "sembloient": "semblaient",
    "entendoit": "entendait",
    "entendoient": "entendaient",
    "sentoit": "sentait",
    "sentoient": "sentaient",
    # --- Action verbs ---
    "donnoit": "donnait",
    "donnoient": "donnaient",
    "prenoit": "prenait",
    "prenoient": "prenaient",
    "mettoit": "mettait",
    "mettoient": "mettaient",
    "rendoit": "rendait",
    "rendoient": "rendaient",
    "tenoit": "tenait",
    "tenoient": "tenaient",
    "recevoit": "recevait",
    "recevoient": "recevaient",
    "portoit": "portait",
    "portoient": "portaient",
    "laissoit": "laissait",
    "laissoient": "laissaient",
    "cherchoit": "cherchait",
    "cherchoient": "cherchaient",
    "regardoit": "regardait",
    "regardoient": "regardaient",
    "montroit": "montrait",
    "montroient": "montraient",
    "suivoit": "suivait",
    "suivoient": "suivaient",
    "servoit": "servait",
    "servoient": "servaient",
    "vivoit": "vivait",
    "vivoient": "vivaient",
    "écrivoit": "écrivait",
    "écrivoient": "écrivaient",
    "lisoit": "lisait",
    "lisoient": "lisaient",
    "envoyoit": "envoyait",
    "envoyoient": "envoyaient",
    "employoit": "employait",
    "employoient": "employaient",
    # --- State change verbs ---
    "devenoit": "devenait",
    "devenoient": "devenaient",
    "commençoit": "commençait",
    "commençoient": "commençaient",
    "finissoit": "finissait",
    "finissoient": "finissaient",
    "remplissoit": "remplissait",
    "remplissoient": "remplissaient",
    "obéissoit": "obéissait",
    "obéissoient": "obéissaient",
    "établissoit": "établissait",
    "établissoient": "établissaient",
    # --- Other common verbs ---
    "falloit": "fallait",
    "plaisoit": "plaisait",
    "plaisoient": "plaisaient",
    "convenoit": "convenait",
    "convenoient": "convenaient",
    "appartenoit": "appartenait",
    "appartenoient": "appartenaient",
    "soutenoit": "soutenait",
    "soutenoient": "soutenaient",
    "contenoit": "contenait",
    "contenoient": "contenaient",
    "retenoit": "retenait",
    "retenoient": "retenaient",
    "présentoit": "présentait",
    "présentoient": "présentaient",
    "représentoit": "représentait",
    "représentoient": "représentaient",
}


# =============================================================================
# COMMON WORD REPLACEMENTS
# =============================================================================

COMMON_REPLACEMENTS: Dict[str, str] = {
    # Archaic spellings with ſ (long s) - these have ſ in source
    "auſſi": "aussi",
    "eſt": "est",
    "eſſe": "esse",
    "maiſon": "maison",
    "choſe": "chose",
    "ſeul": "seul",
    "ſouvent": "souvent",
    "paſſage": "passage",
    "meſure": "mesure",
    "connoiſſance": "connaissance",
    # Circumflex modernizations
    "plûtôt": "plutôt",
    "plûpart": "plupart",
    "coûtume": "coutume",
    "toûjours": "toujours",
    # Spelling modernizations
    "enfans": "enfants",
    "tems": "temps",
    "long-tems": "longtemps",
    "connoître": "connaître",
    "paroître": "paraître",
    "reconnoître": "reconnaître",
    # Archaic expressions
    "cy aprés": "ci-après",
    "cy après": "ci-après",
    "cy devant": "ci-devant",
    "cy dessus": "ci-dessus",
    "cy dessous": "ci-dessous",
    "midy": "midi",
    # Archaic plurals
    "sentimens": "sentiments",
    "fondemens": "fondements",
    "argumens": "arguments",
    "monumens": "monuments",
    "instrumens": "instruments",
    "sacremens": "sacrements",
    "ornemens": "ornements",
    "réglemens": "règlements",
    "tremblemens": "tremblements",
    "mouvemens": "mouvements",
    "changemens": "changements",
    "commencemens": "commencements",
    "événemens": "événements",
    "sentimens": "sentiments",
}


# =============================================================================
# BIBLE BOOK ABBREVIATIONS
# =============================================================================

BIBLE_BOOK_ABBREVS: Dict[str, str] = {
    # Old Testament
    "Gen.": "Genèse",
    "Genes.": "Genèse",
    "Genef.": "Genèse",
    "Exod.": "Exode",
    "Exode.": "Exode",
    "Lev.": "Lévitique",
    "Levit.": "Lévitique",
    "Num.": "Nombres",
    "Nomb.": "Nombres",
    "Deut.": "Deutéronome",
    "Deuteron.": "Deutéronome",
    "Josue.": "Josué",
    "Jofue.": "Josué",
    "Jofué.": "Josué",
    "Josue": "Josué",
    "Jofue": "Josué",  # Without trailing period
    "Jud.": "Juges",
    "Judic.": "Juges",
    "Ruth.": "Ruth",
    "1. Reg.": "1 Samuel",
    "I. Reg.": "1 Samuel",
    "1. Sam.": "1 Samuel",
    "2. Reg.": "2 Samuel",
    "II. Reg.": "2 Samuel",
    "2. Sam.": "2 Samuel",
    "3. Reg.": "1 Rois",
    "III. Reg.": "1 Rois",
    "1. Rois.": "1 Rois",
    "4. Reg.": "2 Rois",
    "IV. Reg.": "2 Rois",
    "2. Rois.": "2 Rois",
    "1. Par.": "1 Chroniques",
    "I. Par.": "1 Chroniques",
    "1. Chron.": "1 Chroniques",
    "2. Par.": "2 Chroniques",
    "II. Par.": "2 Chroniques",
    "2. Chron.": "2 Chroniques",
    "Esdr.": "Esdras",
    "1. Esdr.": "Esdras",
    "Neh.": "Néhémie",
    "Nehem.": "Néhémie",
    "2. Esdr.": "Néhémie",
    "Tob.": "Tobie",
    "Judith.": "Judith",
    "Esth.": "Esther",
    "Job.": "Job",
    "Ps.": "Psaume",
    "Pf.": "Psaume",
    "Pſ.": "Psaume",
    "Pfal.": "Psaume",
    "Pſal.": "Psaume",
    "Pſeaume.": "Psaume",
    "Prov.": "Proverbes",
    "Eccl.": "Ecclésiaste",
    "Eccle.": "Ecclésiaste",
    "Cant.": "Cantique",
    "Sap.": "Sagesse",
    "Eccli.": "Ecclésiastique",
    "Ecclus.": "Ecclésiastique",
    "Is.": "Isaïe",
    "Isa.": "Isaïe",
    "Ifaïe.": "Isaïe",
    "Jer.": "Jérémie",
    "Jerem.": "Jérémie",
    "Lam.": "Lamentations",
    "Bar.": "Baruch",
    "Ez.": "Ézéchiel",
    "Ezech.": "Ézéchiel",
    "Dan.": "Daniel",
    "Os.": "Osée",
    "Osee.": "Osée",
    "Joel.": "Joël",
    "Am.": "Amos",
    "Abd.": "Abdias",
    "Jon.": "Jonas",
    "Mich.": "Michée",
    "Nah.": "Nahum",
    "Hab.": "Habacuc",
    "Soph.": "Sophonie",
    "Agg.": "Aggée",
    "Zach.": "Zacharie",
    "Mal.": "Malachie",
    "1. Mac.": "1 Maccabées",
    "I. Mac.": "1 Maccabées",
    "2. Mac.": "2 Maccabées",
    "II. Mac.": "2 Maccabées",
    # New Testament
    "Mat.": "Matthieu",
    "Matth.": "Matthieu",
    "Matt.": "Matthieu",
    "Marc.": "Marc",
    "Luc.": "Luc",
    "Joan.": "Jean",
    "Jo.": "Jean",
    "Act.": "Actes",
    "Rom.": "Romains",
    "1. Cor.": "1 Corinthiens",
    "I. Cor.": "1 Corinthiens",
    "2. Cor.": "2 Corinthiens",
    "II. Cor.": "2 Corinthiens",
    "Gal.": "Galates",
    "Eph.": "Éphésiens",
    "Ephef.": "Éphésiens",
    "Phil.": "Philippiens",
    "Col.": "Colossiens",
    "1. Thess.": "1 Thessaloniciens",
    "I. Thess.": "1 Thessaloniciens",
    "2. Thess.": "2 Thessaloniciens",
    "II. Thess.": "2 Thessaloniciens",
    "1. Tim.": "1 Timothée",
    "I. Tim.": "1 Timothée",
    "2. Tim.": "2 Timothée",
    "II. Tim.": "2 Timothée",
    "Tit.": "Tite",
    "Philem.": "Philémon",
    "Heb.": "Hébreux",
    "Hebr.": "Hébreux",
    "Jac.": "Jacques",
    "1. Pet.": "1 Pierre",
    "I. Pet.": "1 Pierre",
    "2. Pet.": "2 Pierre",
    "II. Pet.": "2 Pierre",
    "1. Joan.": "1 Jean",
    "I. Joan.": "1 Jean",
    "2. Joan.": "2 Jean",
    "II. Joan.": "2 Jean",
    "3. Joan.": "3 Jean",
    "III. Joan.": "3 Jean",
    "Jud.": "Jude",
    "Apoc.": "Apocalypse",
    "Apocal.": "Apocalypse",
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def roman_to_arabic(roman: str) -> int:
    """Convert Roman numeral to Arabic number."""
    roman = roman.upper()
    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    result = 0
    prev = 0
    for char in reversed(roman):
        curr = values.get(char, 0)
        if curr < prev:
            result -= curr
        else:
            result += curr
        prev = curr
    return result


def normalize_bible_reference(text: str) -> str:
    """
    Normalize bible references to modern format.

    Examples:
    - "Genes. x. 15. 16. 17." → "Genèse 10:15-17"
    - "Josue x. 25." → "Josué 10:25"
    - "Ps. LXXVII. 12. 43." → "Psaume 77:12, 43"
    """
    if not text:
        return text

    # Replace book abbreviations (with word boundaries to avoid false positives)
    for abbrev, full in BIBLE_BOOK_ABBREVS.items():
        # Use word boundary at start to avoid matching "Joseph." → "Jos." + "eph."
        pattern = re.compile(r"\b" + re.escape(abbrev), re.IGNORECASE)
        text = pattern.sub(full, text)

    # Pattern for chapter in Roman numerals followed by verses
    # Matches: "Genèse x. 15. 16. 17." or "Psaume LXXVII. 12."
    def replace_chapter_verse(match):
        full = match.group(0)
        book = match.group(1)
        roman_chapter = match.group(2)
        verses_str = match.group(3)

        # Convert Roman chapter to Arabic
        try:
            chapter = roman_to_arabic(roman_chapter)
        except:
            return full  # If conversion fails, leave unchanged

        # Extract verse numbers
        verse_numbers = re.findall(r"(\d+)\.?", verses_str)
        if not verse_numbers:
            return f"{book} {chapter}"

        # Convert to integers and format
        verses = [int(v) for v in verse_numbers]

        if len(verses) == 1:
            return f"{book} {chapter}:{verses[0]}"

        # Check if consecutive for range
        if verses == list(range(verses[0], verses[-1] + 1)):
            return f"{book} {chapter}:{verses[0]}-{verses[-1]}"
        else:
            return f"{book} {chapter}:{', '.join(str(v) for v in verses)}"

    # Pattern: Book name + Roman numeral + verse numbers
    # Matches things like "Genèse x. 15. 16." or "Psaume LXXVII. 12. 43."
    pattern = re.compile(
        r"(\b(?:Genèse|Exode|Lévitique|Nombres|Deutéronome|Josué|Juges|Ruth|"
        r"1 Samuel|2 Samuel|1 Rois|2 Rois|1 Chroniques|2 Chroniques|"
        r"Esdras|Néhémie|Tobie|Judith|Esther|Job|Psaume|Proverbes|"
        r"Ecclésiaste|Cantique|Sagesse|Ecclésiastique|Isaïe|Jérémie|"
        r"Lamentations|Baruch|Ézéchiel|Daniel|Osée|Joël|Amos|Abdias|"
        r"Jonas|Michée|Nahum|Habacuc|Sophonie|Aggée|Zacharie|Malachie|"
        r"1 Maccabées|2 Maccabées|Matthieu|Marc|Luc|Jean|Actes|Romains|"
        r"1 Corinthiens|2 Corinthiens|Galates|Éphésiens|Philippiens|"
        r"Colossiens|1 Thessaloniciens|2 Thessaloniciens|1 Timothée|"
        r"2 Timothée|Tite|Philémon|Hébreux|Jacques|1 Pierre|2 Pierre|"
        r"1 Jean|2 Jean|3 Jean|Jude|Apocalypse)\b)"
        r"\s+([IVXLCDMivxlcdm]+)\.\s*"
        r"((?:\d+\.?\s*)+)",
        re.UNICODE,
    )

    text = pattern.sub(replace_chapter_verse, text)

    return text


def replace_word_preserving_case(text: str, old_word: str, new_word: str) -> str:
    """
    Replace a word while preserving the original case.

    - lowercase → lowercase
    - Capitalized → Capitalized
    - UPPERCASE → UPPERCASE

    Note: Uses custom word boundaries that treat _ as a boundary
    (for italics markers like _text_).
    """

    def replacer(match):
        original = match.group(1)
        if original.isupper():
            return new_word.upper()
        if original[0].isupper():
            return new_word.capitalize()
        return new_word

    # Custom boundary: start of string, whitespace, punctuation, or underscore
    # This handles _Moyse_ italics markers correctly
    pattern = re.compile(
        r'(?:^|(?<=[\s\.,;:!?\'"()«»\[\]_]))('
        + re.escape(old_word)
        + r')(?=[\s\.,;:!?\'"()«»\[\]_]|$)',
        re.IGNORECASE,
    )
    return pattern.sub(replacer, text)


# =============================================================================
# MAIN MODERNIZATION FUNCTIONS
# =============================================================================


def modernize_french(text: str) -> str:
    """Apply French orthography modernization rules."""
    if not text or not isinstance(text, str):
        return text

    # Unicode normalization (consistent character representation)
    text = unicodedata.normalize("NFC", text)

    # --- CHARACTER REPLACEMENTS ---

    # Long s replacement (most important)
    text = text.replace("ſ", "s")

    # Ampersand to "et" in French context (with spaces)
    text = re.sub(r"\s&\s", " et ", text)
    text = re.sub(r"\s&\n", " et\n", text)

    # --- OCR ERROR CORRECTIONS (f → s) ---
    for old, new in OCR_F_TO_S_WORDS.items():
        text = replace_word_preserving_case(text, old, new)

    # --- VERB CONJUGATIONS (-oit → -ait) ---
    for old, new in VERBS_OIT_TO_AIT.items():
        text = replace_word_preserving_case(text, old, new)

    # --- COMMON WORD REPLACEMENTS ---
    for old, new in COMMON_REPLACEMENTS.items():
        text = replace_word_preserving_case(text, old, new)

    # --- ACCENT ADDITIONS ---
    # Common words missing accents
    text = replace_word_preserving_case(text, "pere", "père")
    text = replace_word_preserving_case(text, "mere", "mère")
    text = replace_word_preserving_case(text, "frere", "frère")
    text = replace_word_preserving_case(text, "etre", "être")

    # Word ending: éme → ème (même, extrême, suprême, etc.)
    text = RE_WORD_ENDING_EME.sub(r"\1ème", text)

    # --- ARCHAIC CHARACTER COMBINATIONS ---
    text = text.replace("sç", "s")  # sçavoir → savoir
    text = text.replace("Sç", "S")  # Sçavoir → Savoir
    text = text.replace("üi", "ui")  # archaic umlaut
    text = text.replace("éü", "éu")  # archaic umlaut
    text = text.replace("üe", "ue")  # archaic umlaut
    text = text.replace("oü", "ou")  # archaic umlaut
    text = text.replace("Oü", "Ou")
    text = text.replace("tres-", "très ")  # tres-humble → très humble
    text = text.replace("Tres-", "Très ")
    text = text.replace("entr'", "entre ")  # entr'eux → entre eux
    text = text.replace("Entr'", "Entre ")

    # --- COMPOUND WORDS ---
    text = text.replace("long-temps", "longtemps")
    text = text.replace("Long-temps", "Longtemps")
    text = text.replace("bien-tôt", "bientôt")
    text = text.replace("Bien-tôt", "Bientôt")
    text = text.replace("aussi-tôt", "aussitôt")
    text = text.replace("Aussi-tôt", "Aussitôt")
    text = text.replace("par-tout", "partout")
    text = text.replace("Par-tout", "Partout")
    text = text.replace("sur-tout", "surtout")
    text = text.replace("Sur-tout", "Surtout")

    # --- PUNCTUATION CLEANUP ---
    text = text.replace("...", "…")  # ellipsis
    text = text.replace(" ,", ",")  # space before comma
    text = text.replace(" .", ".")  # space before period
    text = text.replace("( ", "(")  # space after open paren
    text = text.replace(" )", ")")  # space before close paren
    text = text.replace("[ ", "[")  # space after open bracket
    text = text.replace(" ]", "]")  # space before close bracket
    text = text.replace("  ", " ")  # double space
    text = text.replace(" et et ", " et ")  # duplicate "et"

    # French guillemets with spaces are OCR errors - remove them
    text = re.sub(r"« ", "", text)  # opening guillemet + space
    text = re.sub(r" »", "", text)  # space + closing guillemet
    text = re.sub(r"«", "", text)  # any remaining opening
    text = re.sub(r"»", "", text)  # any remaining closing

    # Non-breaking space before French punctuation
    text = re.sub(r" ([?!;:])", "\u00a0\\1", text)  # space → non-breaking space

    # Saint abbreviations
    text = re.sub(r"\bS\. Paul\b", "Saint Paul", text)
    text = re.sub(r"\bS\. Jean\b", "Saint Jean", text)
    text = re.sub(r"\bS\. Pierre\b", "Saint Pierre", text)
    text = re.sub(r"\bS\. Jacques\b", "Saint Jacques", text)
    text = re.sub(r"\bS\. Matthieu\b", "Saint Matthieu", text)
    text = re.sub(r"\bS\. Marc\b", "Saint Marc", text)
    text = re.sub(r"\bS\. Luc\b", "Saint Luc", text)

    # Footnote marker cleanup
    text = re.sub(r" \^", "^", text)  # remove space before footnote marker
    text = text.replace("^{ᵃ}", "^{a}")  # normalize superscript
    text = text.replace("^{ᵇ}", "^{b}")
    text = text.replace("^{ᶜ}", "^{c}")
    text = text.replace("^{ᵈ}", "^{d}")

    # --- CAPITALIZATION FIXES ---
    # LOrsque → Lorsque (double capital at word start)
    text = RE_DOUBLE_CAPITAL.sub(
        lambda m: m.group(1)[0] + m.group(1)[1:].lower() + m.group(2), text
    )
    # S'Il → S'il, D'Un → D'un (apostrophe capital)
    text = RE_APOSTROPHE_CAPITAL.sub(
        lambda m: f"{m.group(1)}'{m.group(2).lower()}{m.group(3)}", text
    )

    # --- BIBLE REFERENCE NORMALIZATION ---
    text = normalize_bible_reference(text)

    # --- VERSE MARKER NORMALIZATION ---
    # ℣. 10. jusqu'au 16. → versets 10-16
    # ℣. 5. → verset 5
    # ℣. suivant → verset suivant
    text = re.sub(r"℣\.\s*(\d+)\.\s*jusqu\'au\s*(\d+)\.?", r"versets \1-\2", text)
    text = re.sub(r"℣\.\s*(\d+)\.\s*et\s*(\d+)\.?", r"versets \1 et \2", text)
    text = re.sub(r"℣\.\s*(\d+)\.", r"verset \1", text)
    text = re.sub(r"℣\.", "verset", text)  # Fallback for ℣. without number

    # chapitre xv. 17. 18. → chapitre 15:17-18
    def normalize_chapitre(match):
        roman = match.group(1)
        verses_str = match.group(2)
        try:
            chapter = roman_to_arabic(roman)
        except:
            return match.group(0)
        verse_numbers = re.findall(r"(\d+)\.?", verses_str)
        if not verse_numbers:
            return f"chapitre {chapter}"
        verses = [int(v) for v in verse_numbers]
        if len(verses) == 1:
            return f"chapitre {chapter}:{verses[0]}"
        if verses == list(range(verses[0], verses[-1] + 1)):
            return f"chapitre {chapter}:{verses[0]}-{verses[-1]}"
        return f"chapitre {chapter}:{', '.join(str(v) for v in verses)}"

    text = re.sub(
        r"\bchapitre\s+([IVXLCDMivxlcdm]+)\.\s*((?:\d+\.?\s*)+)",
        normalize_chapitre,
        text,
        flags=re.IGNORECASE,
    )

    return text


def modernize_latin(text: str) -> str:
    """
    Apply Latin orthography modernization rules.

    Classical Latin has NO accents (except ligatures æ, œ which are preserved).
    Accents in Latin text are OCR errors or 17th-century printing conventions.
    """
    if not text or not isinstance(text, str):
        return text

    # Unicode normalization
    text = unicodedata.normalize("NFC", text)

    # Long s replacement
    text = text.replace("ſ", "s")

    # Ampersand to "et" (Latin conjunction)
    text = re.sub(r"\s&\s", " et ", text)
    text = re.sub(r"\s&$", " et", text)
    text = re.sub(r"^&\s", "et ", text)

    # OCR f→s corrections for Latin proper nouns
    latin_f_to_s = {
        "Ifrael": "Israel",
        "Jerufalem": "Jerusalem",
        "Jofue": "Josue",
        "Jofeph": "Joseph",
        "Moyfes": "Moyses",
        "Ifaac": "Isaac",
        "Ifaias": "Isaias",
    }
    for old, new in latin_f_to_s.items():
        text = replace_word_preserving_case(text, old, new)

    # Remove erroneous accents (classical Latin has none)
    accent_map = {
        # Lowercase
        "é": "e",
        "è": "e",
        "ê": "e",
        "ë": "e",
        "á": "a",
        "à": "a",
        "â": "a",
        "ä": "a",
        "ú": "u",
        "ù": "u",
        "û": "u",
        "ü": "u",
        "í": "i",
        "ì": "i",
        "î": "i",
        "ï": "i",
        "ó": "o",
        "ò": "o",
        "ô": "o",
        "ö": "o",
        # Uppercase
        "É": "E",
        "È": "E",
        "Ê": "E",
        "Ë": "E",
        "Á": "A",
        "À": "A",
        "Â": "A",
        "Ä": "A",
        "Ú": "U",
        "Ù": "U",
        "Û": "U",
        "Ü": "U",
        "Í": "I",
        "Ì": "I",
        "Î": "I",
        "Ï": "I",
        "Ó": "O",
        "Ò": "O",
        "Ô": "O",
        "Ö": "O",
    }
    for accented, plain in accent_map.items():
        text = text.replace(accented, plain)

    # Preserve ligatures æ, œ (these ARE correct classical Latin)
    return text


# =============================================================================
# JSON PROCESSING
# =============================================================================


def validate_json_output(data: dict, source_data: dict) -> bool:
    """
    Validate output JSON before writing.

    Raises ValueError if validation fails.
    """
    # Check JSON is serializable
    try:
        json.dumps(data, ensure_ascii=False)
    except (TypeError, ValueError) as e:
        raise ValueError(f"Output not JSON serializable: {e}")

    # Check required fields weren't removed
    required = ["verses", "commentary"]
    for field in required:
        if field in source_data and field not in data:
            raise ValueError(f"Required field '{field}' missing from output")

    # Sanity check: didn't lose too much content
    source_len = len(json.dumps(source_data, ensure_ascii=False))
    output_len = len(json.dumps(data, ensure_ascii=False))
    if output_len < source_len * 0.5:
        raise ValueError(
            f"Output suspiciously small: {output_len} vs {source_len} bytes"
        )

    return True


def modernize_json_file(data: dict) -> dict:
    """Apply modernization to appropriate fields in JSON structure."""

    # Modernize verses
    if "verses" in data and isinstance(data["verses"], list):
        for verse in data["verses"]:
            if "french" in verse:
                verse["french"] = modernize_french(verse["french"])
            if "latin" in verse:
                verse["latin"] = modernize_latin(verse["latin"])

    # Modernize commentary
    if "commentary" in data and isinstance(data["commentary"], list):
        for comment in data["commentary"]:
            if "french_translation" in comment:
                comment["french_translation"] = modernize_french(
                    comment["french_translation"]
                )
            if "french_commentary" in comment:
                comment["french_commentary"] = modernize_french(
                    comment["french_commentary"]
                )
            if "latin_quote" in comment:
                comment["latin_quote"] = modernize_latin(comment["latin_quote"])

    # Modernize chapter_summary if present
    if "chapter_summary" in data and data["chapter_summary"]:
        data["chapter_summary"] = modernize_french(data["chapter_summary"])

    # Modernize footnotes
    if "footnotes" in data and isinstance(data["footnotes"], list):
        for footnote in data["footnotes"]:
            if "text" in footnote:
                text = footnote["text"]

                # Translate Latin reference phrases to French (no abbreviations)
                text = re.sub(r"\bVide\s+ad\b", "Voir", text, flags=re.IGNORECASE)
                text = re.sub(r"\bVideatur\b", "Voir", text, flags=re.IGNORECASE)
                text = re.sub(r"\bVidè\b", "Voir", text)
                text = re.sub(r"\bConfer\b", "Voir aussi", text, flags=re.IGNORECASE)
                text = re.sub(r"\bCf\.\s*ad\b", "Voir aussi", text, flags=re.IGNORECASE)
                text = re.sub(
                    r"\bCf\.\b", "Voir aussi", text
                )  # Existing Cf. abbreviations

                # Apply French modernization (includes bible reference normalization)
                footnote["text"] = modernize_french(text)

    return data


# =============================================================================
# PROGRESS LOGGING
# =============================================================================


def log_progress(base_dir: Path, filename: str, status: str) -> None:
    """
    Log processing progress to a JSON file.

    Args:
        base_dir: The base directory (Janvier)
        filename: The file being processed
        status: "staged" or "reviewed"
    """
    progress_file = base_dir / "modernize_progress.json"

    # Load existing progress
    if progress_file.exists():
        try:
            with open(progress_file, "r", encoding="utf-8") as f:
                progress = json.load(f)
        except (json.JSONDecodeError, IOError):
            progress = {"files": {}, "last_updated": None}
    else:
        progress = {"files": {}, "last_updated": None}

    # Update
    progress["files"][filename] = {
        "status": status,
        "timestamp": datetime.now().isoformat(),
    }
    progress["last_updated"] = datetime.now().isoformat()

    # Save
    with open(progress_file, "w", encoding="utf-8") as f:
        json.dump(progress, f, indent=2, ensure_ascii=False)


# =============================================================================
# PATH UTILITIES
# =============================================================================


def get_staging_path(source_path: Path) -> Path:
    """Convert source path to staging path (raw_json → 21st_claude_staging)."""
    source_path_str = str(source_path)
    if "raw_json" in source_path_str:
        output_path_str = source_path_str.replace("raw_json", "21st_claude_staging")
        return Path(output_path_str)
    else:
        raise ValueError(f"Source path must contain 'raw_json': {source_path}")


def get_final_path(source_path: Path) -> Path:
    """Convert source path to final path (raw_json → 21st_claude)."""
    source_path_str = str(source_path)
    if "raw_json" in source_path_str:
        output_path_str = source_path_str.replace("raw_json", "21st_claude")
        return Path(output_path_str)
    else:
        raise ValueError(f"Source path must contain 'raw_json': {source_path}")


def get_book_dir(source_path: Path) -> Path:
    """Get the book directory from a source path."""
    # Go up from .../book/raw_json/commentaire to .../book
    return source_path.parent.parent


# =============================================================================
# MAIN PROCESSING
# =============================================================================


def process_directory(source_dir: str) -> None:
    """
    Process all JSON files in source directory.

    Writes preprocessed files to STAGING directory (21st_claude_staging/commentaire).
    Skips files that already exist in FINAL directory (21st_claude/commentaire) to protect reviewed work.

    Args:
        source_dir: Path to raw_json/commentaire directory, or book name (e.g., "09_1_rois")
    """
    # Handle book name vs full path
    if "/" not in source_dir and not source_dir.startswith("/"):
        # Book name provided
        source_dir = Path(BASE_PATH) / source_dir / "raw_json" / "commentaire"
    else:
        source_dir = Path(source_dir)

    if not source_dir.exists():
        print(f"Error: Source directory does not exist: {source_dir}")
        return

    # Find all JSON files
    json_files = sorted(source_dir.glob("page_*.json"))

    if not json_files:
        print(f"No JSON files found in: {source_dir}")
        return

    print(f"Found {len(json_files)} JSON files in source directory")

    # Determine directories
    try:
        sample_staging = get_staging_path(json_files[0])
        sample_final = get_final_path(json_files[0])
        staging_dir = sample_staging.parent
        final_dir = sample_final.parent
        book_dir = get_book_dir(source_dir)
    except ValueError as e:
        print(f"Error: {e}")
        return

    # Create staging directory if needed
    staging_dir.mkdir(parents=True, exist_ok=True)
    print(f"Staging directory: {staging_dir}")
    print(f"Final directory: {final_dir}")

    processed = 0
    skipped_final = 0
    skipped_staging = 0
    errors = 0

    for source_file in json_files:
        try:
            staging_file = get_staging_path(source_file)
            final_file = get_final_path(source_file)

            # PROTECTION: Skip if already in FINAL (reviewed work)
            if final_file.exists():
                skipped_final += 1
                continue

            # Skip if already in STAGING (already preprocessed)
            if staging_file.exists():
                skipped_staging += 1
                continue

            # Read source JSON
            with open(source_file, "r", encoding="utf-8") as f:
                source_data = json.load(f)

            # Apply modernization
            modernized_data = modernize_json_file(source_data)

            # Validate output
            validate_json_output(modernized_data, source_data)

            # Write to STAGING (not final!)
            with open(staging_file, "w", encoding="utf-8") as f:
                json.dump(modernized_data, f, ensure_ascii=False, indent=2)

            # Log progress
            log_progress(book_dir, source_file.name, "staged")

            processed += 1

            # Progress report every 10 files
            if processed % 10 == 0:
                print(f"Preprocessed {processed} files to staging...")

        except json.JSONDecodeError as e:
            print(f"JSON error in {source_file.name}: {e}")
            errors += 1
        except ValueError as e:
            print(f"Validation error in {source_file.name}: {e}")
            errors += 1
        except Exception as e:
            print(f"Error processing {source_file.name}: {e}")
            errors += 1

    # Summary
    print("\n" + "=" * 60)
    print("PREPROCESSING SUMMARY")
    print("=" * 60)
    print(f"Total source files: {len(json_files)}")
    print(f"Preprocessed to staging: {processed}")
    print(f"Skipped (already in final - reviewed): {skipped_final}")
    print(f"Skipped (already in staging): {skipped_staging}")
    print(f"Errors: {errors}")
    print(f"\nFiles needing LLM review: {processed + skipped_staging}")
    print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python modernize.py <book_name_or_path>")
        print("Example: python modernize.py 09_1_rois")
        print(f"         python modernize.py /path/to/raw_json/commentaire")
        sys.exit(1)

    process_directory(sys.argv[1])
