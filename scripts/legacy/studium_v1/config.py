"""
Configuration for Bible commentary JSON validation and transformation.
Dom Calmet's Commentaire littéral - 17th century French Catholic commentary.
"""

# Book name mappings (directory name -> display name)
# Based on actual directory structure (Vulgate naming convention)
BOOK_MAPPINGS = {
    "01_genese": "Genèse",
    "02_exode": "Exode",
    "03_levitique": "Lévitique",
    "04_nombres": "Nombres",
    "05_deuteronome": "Deutéronome",
    "06_josue": "Josué",
    "07_juges": "Juges",
    "08_ruth": "Ruth",
    "09_1_rois": "1 Rois",      # 1 Samuel in modern naming
    "10_2_rois": "2 Rois",      # 2 Samuel in modern naming
    "11_3_rois": "3 Rois",      # 1 Kings in modern naming
    "12_4_rois": "4 Rois",      # 2 Kings in modern naming
    "13_1_chroniques": "1 Chroniques",
    "14_2_chroniques": "2 Chroniques",
    "15_esdras": "Esdras",
    "16_nehemie": "Néhémie",
    "17_tobie": "Tobie",
    "18_judith": "Judith",
    "19_esther": "Esther",
    "20_job": "Job",
    "21a_psaumes": "Psaumes (Partie 1)",
    "21b_psaumes": "Psaumes (Partie 2)",
    "21c_psaumes": "Psaumes (Partie 3)",
    "22_proverbes": "Proverbes",
    "23_ecclesiaste": "Ecclésiaste",
    "24_cantique": "Cantique des Cantiques",
    "25_sagesse": "Sagesse",
    "26_ecclesiastique": "Ecclésiastique (Siracide)",
    "27_isaie": "Isaïe",
    "28_jeremie": "Jérémie",
    "29_lamentations": "Lamentations",
    "30_baruch": "Baruch",
    "31_ezechiel": "Ézéchiel",
    "32_daniel": "Daniel",
    "33_osee": "Osée",
    "34_joel": "Joël",
    "35_amos": "Amos",
    "36_abdias": "Abdias",
    "37_jonas": "Jonas",
    "38_michee": "Michée",
    "39_nahum": "Nahum",
    "40_habacuc": "Habacuc",
    "41_sophonie": "Sophonie",
    "42_aggee": "Aggée",
    "43_zacharie": "Zacharie",
    "44_malachie": "Malachie",
    "45_1_maccabees": "1 Maccabées",
    "46_2_maccabees": "2 Maccabées",
    "47_matthieu": "Matthieu",
    "48_marc": "Marc",
    "49_luc": "Luc",
    "50_jean": "Jean",
    "51_actes": "Actes des Apôtres",
    "52_romains": "Romains",
    "53_1_corinthiens": "1 Corinthiens",
    "54_2_corinthiens": "2 Corinthiens",
    "55_galates": "Galates",
    "56_ephesiens": "Éphésiens",
    "57_philippiens": "Philippiens",
    "58_colossiens": "Colossiens",
    "59_1_thessaloniciens": "1 Thessaloniciens",
    "60_2_thessaloniciens": "2 Thessaloniciens",
    "61_1_timothee": "1 Timothée",
    "62_2_timothee": "2 Timothée",
    "63_tite": "Tite",
    "64_philemon": "Philémon",
    "65_hebreux": "Hébreux",
    "66_jacques": "Jacques",
    "67_1_pierre": "1 Pierre",
    "68_2_pierre": "2 Pierre",
    "69_1_jean": "1 Jean",
    "70_2_jean": "2 Jean",
    "71_3_jean": "3 Jean",
    "72_jude": "Jude",
    "73_apocalypse": "Apocalypse",
    "74_3_maccabees": "3 Maccabées",
    "75_4_maccabees": "4 Maccabées",
}

# Expected JSON fields at top level
EXPECTED_TOP_LEVEL_FIELDS = {
    "book_title",
    "chapter_title",     # Old field name (source files)
    "chapter_number",    # New field name (normalized files)
    "chapter_summary",
    "chapter_argument",  # Psalms only
    "verses",
    "commentary",
    "footnotes",
    "book_end_marker",
}

# Expected fields in verses array
EXPECTED_VERSE_FIELDS = {
    "verse_number",
    "latin",
    "french",
    "annotations",
}

# Expected fields in commentary array
EXPECTED_COMMENTARY_FIELDS = {
    "commentary_id",
    "verse_ref",
    "latin_quote",
    "french_translation",
    "french_commentary",
}

# Expected fields in footnotes array
EXPECTED_FOOTNOTE_FIELDS = {
    "marker",
    "text",
}

# Patterns indicating OCR errors in footnote text
OCR_ERROR_PATTERNS = [
    r'\*{3,}',           # *** or more
    r'□+',               # Box characters
    r'~{3,}',            # ~~~ or more
    r'_{5,}',            # _____ or more
    r'\.{5,}',           # ..... or more
    r'[#@$%]{2,}',       # Multiple special chars
    r'[\x00-\x08\x0b\x0c\x0e-\x1f]',  # Control characters
]

# Markers indicating uncertain/illegible text
UNCERTAIN_MARKERS = [
    "[UNCERTAIN HEBREW]",
    "[UNCERTAIN GREEK]",
    "[ILLEGIBLE]",
    "[ILLEGIBLE TEXT]",
]

# Verse number patterns to normalize
# Pattern -> description
VERSE_NUMBER_PATTERNS = {
    r'^℣\.\s*(\d+)\.$': 'versicle symbol prefix',
    r'^℣\.\s*(\d+)$': 'versicle symbol prefix (no trailing dot)',
    r'^(\d+)\.$': 'number with trailing dot',
    r'^(\d+)$': 'plain number',
}

# Work ID for this commentary
WORK_ID = "calmet"
