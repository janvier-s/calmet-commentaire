"""Write old-style Bible references out as "Livre C:V" in french_commentary and footnotes.

"Pſal. CXXXVIII. 5. 6. 7." -> "Psaumes 138:5-7."   "3. Reg. IV. 9" -> "3 Rois 4:9"
"Jérém. xxv. 12" -> "Jérémie 25:12"            "Matthieu, XXVII. 34" -> "Matthieu 27:34"

Only references with an old tell (abbreviated or old-spelt book name, Roman chapter, "3." /
"I." before the name, "℣.") are touched; modern ones are left as they are. Every rewrite is
checked against the Clementine Vulgate (bible_refs.exists); what fails, or cannot be read with
certainty, goes to the review list instead of being changed. No model is called.

Usage: python3 modernize_refs.py [--apply] [book ...]   (default: dry run, every book)
  writes reports/modernize_refs_review.tsv (what is left to look at) and, on a dry run,
  reports/modernize_refs_changes.tsv (every planned rewrite).
"""
import json, re, sys

from bible_refs import _VS, ABBR, Ref, _verses, exists, find_refs, num, plain
from paths import DATA

FULL = re.compile(r"(?:[1-4] )?[A-ZÉ]\w+(?: des cantiques)? \d+(?::\d+(?:(?:-|, )\d+)*)?")
# a chapter with no book or "et" before it: "Genès. XXIV. 27. 49. XLVII. 29."
BARE = re.compile(rf"(?:\.\s*|\s+)(?:(?:et|&)\s+)?(?P<c>[IVXLC]+)\.\s*(?P<v>{_VS})")
ROMAN_CH = re.compile(r"\b[IVXLC]+\b|(?<![\w'’])[ivxlc]+\.")
# a book name in italics before its chapter: "_Genes._ XXI. 14." -> "Genes. XXI. 14."
DONE = re.compile(r"(?:\.\s*|\s+)(?:(?:et|&)\s+)?\d+:\d+(?:(?:-|,\s*)\d+)*")
ITALIC = re.compile(r"_((?:[1-4I]{1,3}(?:\.\s*|\s+))?([A-Za-zÀ-ÿſæœ]+)\.?)_(?=[\s.,]*(?:[IVXLCivxlc]+\b|\d))")


def unitalic(text):
    return ITALIC.sub(lambda m: m.group(1) if plain(m.group(2)) in ABBR else m.group(0), text)

# Settled by hand (reports/modernize_refs_review.tsv, 2026-10-19). A text: what the reference
# is: from the scan, or (with *, the guess convention) the verse that fits the context. None: Calmet's numbers do not match
# the Vulgate, but are written out as printed. "": not a reference, or unreadable; left alone.
MANUAL = {
    ('21a_psaumes/page_0233', 'Act. III. 29'): 'Actes 2:29*',  # David's tomb, in Peter's speech
    ('21a_psaumes/page_0687', 'Psal. x. 7. 14'): 'Psaumes 9:28, 35',  # labor (amal); Hebrew 10:7, 14
    ('02_exode/page_0573', 'Psal. 59. 5 et 59. 10'): 'Psaumes 59:5 et 59:10',
    ('10_2_rois/page_0118', '2. Reg. LII. 7'): '2 Rois 3:7',  # scan: III. 7
    ('10_2_rois/page_0262', 'I. Par. 37'): '1 Paralipomènes 11:37',  # Naarai filius Asbai
    ('11_3_rois/page_0179', '1. Par. XVIII. 27'): '1 Paralipomènes 28:17',  # scan: XXVIII. 17
    ('13_1_chroniques/page_0097', 'Iosue XVI. 20'): 'Josué 18:13*',
    ('13_1_chroniques/page_0107', 'Psalm. 77. ℣. 51. et 104. 23. 27'): 'Psaumes 77:51 et 104:23, 27',
    ('13_1_chroniques/page_0173', '2. Reg. XXXIII. 13'): '2 Rois 23:13*',  # the three going down to David
    ('14_2_chroniques/page_0056', 'I. Par. XXXI. 3'): '2 Paralipomènes 31:3*',  # holocausts for the feasts
    ('18_judith/page_0163', 'Judith III. 35'): 'Judith 3:15',  # scan: III. 15
    ('20_job/page_0065', 'Genes. XXVI. 14. 70'): 'Genèse 26:14. 70',  # 70 = the Septuagint
    ('20_job/page_0166', 'Malach. III. 22'): 'Malachie 3:2*',  # herba fullonum, beside Jérémie 2:22
    ('21a_psaumes/page_0523', 'Hebr. x. 5. et 70'): 'Hébreux 10:5 et 70',
    ('06_josue/page_0270', 'Num. XI. 35'): 'Nombres 11:34',  # Haseroth; 11:35 is the Hebrew numbering
    ('06_josue/page_0281', 'Num. XI. 35'): 'Nombres 11:34',
    ('06_josue/page_0392', '3. Reg. xiv. 38'): '3 Rois 14:30*',  # war between Roboam and Jeroboam
    ('06_josue/page_0394', 'VIII. 13. 14'): None,
    ('07_juges/page_0048', 'XIX. 38'): None,
    ('09_1_rois/page_0097', 'Psal. CXVI. 10'): 'Psaumes 115:10',  # Credidi, propter quod (ki); Hebrew 116:10
    ('09_1_rois/page_0441', 'Esther XX. 16'): 'Esther 15:16*',  # quasi angelum Dei, beside Genèse 33:10
    ('11_3_rois/page_0413', 'Isai. XXXIX. 12'): 'Isaïe 34:12*',  # nobiles (horim)
    ('12_4_rois/page_0257', 'Isaï. IX. 30'): None,
    ('12_4_rois/page_0283', 'Ezechiel XV. 12'): None,
    ('20_job/page_0106', 'Psal. VI.15'): 'Psaumes 7:15*',  # parturiit injustitiam
    ('20_job/page_0153', 'Psal. XXVII. 16'): 'Psaumes 17:16*',  # fundamenta orbis terrarum
    ('20_job/page_0252', 'Sap. XXIII. ℣. 21'): None,
    ('20_job/page_0264', 'Psaume XXVI. 35'): 'Psaumes 36:35*',  # non est inventus locus ejus
    ('20_job/page_0335', 'Psaume xxxv. 25'): 'Psaumes 36:25',  # the verse is quoted
    ('21a_psaumes/page_0334', 'XXXI. 24. 25'): None,
    ('21a_psaumes/page_0374', '1. Reg. XXI. 46'): None,
    ('21a_psaumes/page_0638', 'Psal. X. 10'): None,
    ('21a_psaumes/page_0664', 'Psaume XLIX. 15. 24'): 'Psaumes 49:14, 23*',  # sacrificium laudis
    ('21a_psaumes/page_0678', 'Jerem. II. 51'): 'Jérémie 51:51*',  # venerunt alieni
    ('21a_psaumes/page_0798', 'Psal. LX. 29'): 'Psaumes 9:28*',  # sub lingua, beside Cantique 4:11
    ('21a_psaumes/page_0856', 'Pseaume XXXIX. 23'): 'Psaumes 39:18',  # the verse is quoted
    ('21a_psaumes/page_0878', 'Isaïe XXIII. 21'): 'Isaïe 13:21*',  # tsiyim, the people of the waters
    ('17_tobie/page_0067', 'Genes. XXXI. 11. et 63'): 'Genèse 31:11 et 13*',  # the angel: Ego sum Deus Bethel
    ('21a_psaumes/page_0855', 'Levit. II. 9. 19'): 'Lévitique 2:9, 16*',  # in memoriam (azkara)
    ('01_genese/page_0533', 'Genèse. C'): '',
    ('03_levitique/page_0122', 'deuil. 3'): '',
    ('04_nombres/page_0256', 'ici verset 12'): '',
    ('04_nombres/page_0417', 'ici, verset 21 et 31'): '',
    ('06_josue/page_0130', 'Hébreux. C'): '',
    ('06_josue/page_0287', '3. Reg. XXX.315'): '',
    ('20_job/page_0087', 'Sophi. 70'): '',
    ('21a_psaumes/page_0837', 'Cantique. C'): '',
    ('21b_psaumes/page_0450', '1. Reg. IV. 25'): '3 Rois 4:25*',
    ('21b_psaumes/page_0471', 'Psal. I. 7'): 'Psaumes 2:8*',
    ('21b_psaumes/page_0521', 'Isaï. XXV. 14. et 19'): 'Isaïe 26:14 et 19*',
    ('21b_psaumes/page_0534', 'Ezech. LV. 3'): 'Isaïe 55:3*',
    ('21b_psaumes/page_0537', '2. Par. XIV. 17'): '1 Paralipomènes 14:17*',
    ('21b_psaumes/page_0538', 'Dan. XXI, 11'): 'Deutéronome 11:21*',
    ('21b_psaumes/page_0560', 'Num. VI. 29'): 'Nombres 6:25*',
    ('21c_psaumes/page_0015', 'Isai. LX. 31'): 'Isaïe 40:31*',
    ('21c_psaumes/page_0061', 'Exod. XLV. 28'): 'Exode 14:28*',
    ('21c_psaumes/page_0066', 'Judit. XXI. 15'): 'Juges 21:15*',
    ('21c_psaumes/page_0067', 'Deut. XXXXII. 41'): 'Deutéronome 32:41*',
    ('21c_psaumes/page_0072', 'Num. XXX. 19. 70'): 'Nombres 35:33. 70*',
    ('21c_psaumes/page_0083', 'Psalm. CXLVII. 18'): 'Psaumes 147:7*',
    ('21c_psaumes/page_0098', 'Psal. LXXVIII. 33'): 'Psaumes 77:33*',
    ('21c_psaumes/page_0110', 'Act. I. 34'): 'Actes 2:34*',
    ('21c_psaumes/page_0111', 'Matt. 42. 43'): 'Matthieu 22:42-43*',
    ('21c_psaumes/page_0115', 'Job. XXXVII. 28. 29'): 'Job 38:28-29*',
    ('21c_psaumes/page_0135', 'Isai. 11. 46'): None,
    ('21c_psaumes/page_0150', '2. Cor. IV. 13. 24'): '2 Corinthiens 4:13*',
    ('21c_psaumes/page_0171', 'Psal. CXXIII. 99. 100'): 'Psaumes 118:99-100*',
    ('21c_psaumes/page_0177', 'Pseaume CXXXVII. 9'): 'Psaume 137:8*',
    ('21c_psaumes/page_0257', 'Jerem. XLIX. 19. et 2. 44'): 'Jérémie 49:19 et 50:44*',
    ('21c_psaumes/page_0271', 'Malac. 11. 14'): 'Malachie 2:14*',
    ('21c_psaumes/page_0296', 'Psal. CXXVII. 68. 70'): 'Psaumes 77:68, 70*',
    ('21c_psaumes/page_0316', 'Psal. cxxxvii. 13'): 'Psaumes 138:13*',
    ('21c_psaumes/page_0351', 'Psal. x. 7. 14'): 'Psaumes 9:28, 35',
    ('21c_psaumes/page_0356', 'Num. XXXVIII. 4'): 'Nombres 28:4*',
    ('21c_psaumes/page_0388', '1. Esdr. XIII. 27'): '2 Esdras 13:27*',
    ('21c_psaumes/page_0402', 'Ezech. XXVIII. 28'): None,
    ('22_proverbes/page_0047', '1. Reg. X. 29'): '1 Rois 10:27*',
    ('22_proverbes/page_0106', '1. Reg. XXVII. 12. 13'): '1 Rois 27:12*',
    ('22_proverbes/page_0160', 'Matth. XXXV. 40'): 'Matthieu 25:40*',
    ('22_proverbes/page_0298', '1. Reg. IV. 32'): '3 Rois 4:32*',
    ('22_proverbes/page_0309', '2. Reg. XXV. 36'): '1 Rois 25:36*',
    ('22_proverbes/page_0313', 'Prov. 111. 31'): 'Proverbes 3:31*',
    ('22_proverbes/page_0396', 'Job. LIX. 19'): 'Job 29:13*',
    ('22_proverbes/page_0403', 'Exod. XXXVIII. 32'): 'Exode 28:32*',
    ('23_ecclesiaste/page_0015', 'Eccle. 11. 11'): 'Ecclésiaste 2:11*',
    ('23_ecclesiaste/page_0078', 'Luc. XXVI. 5'): 'Luc 6:25*',
    ('23_ecclesiaste/page_0115', 'Sap. VI. 1. 70'): '',
    ('24_cantique/page_0026', 'Tob. XXIV. 12'): 'Job 24:22*',
    ('24_cantique/page_0054', 'Thren. xv. 18'): 'Lamentations 5:18*',
    ('24_cantique/page_0059', 'Psal. cxxvii. 148'): 'Psaumes 118:148*',
    ('24_cantique/page_0063', 'Cant. 11. 7'): 'Cantique des cantiques 2:7*',
    ('24_cantique/page_0070', 'tit. 8'): '',
    ('24_cantique/page_0070', 'it. 8'): '',
    ('24_cantique/page_0072', '1. Timot. III. 18'): '1 Timothée 3:15*',
    ('24_cantique/page_0098', 'Josue. XI. 24'): 'Josué 12:24*',
    ('24_cantique/page_0107', 'Psal. XXII. 7'): 'Psaumes 22:5*',
    ('25_sagesse/page_0039', 'sagesse. C'): '',
    ('25_sagesse/page_0055', 'Eccl. XVI. 22'): 'Ecclésiastique 16:22*',
    ('25_sagesse/page_0061', '4. Reg. XXVI. 3'): '4 Rois 22:3*',
    ('25_sagesse/page_0126', 'Isai. LIII. 27'): 'Isaïe 43:27*',
    ('25_sagesse/page_0135', 'Exod. V. 1. 20. 24'): 'Exode 7:20, 24*',
    ('25_sagesse/page_0141', 'Matt. XXV. 52'): 'Matthieu 26:52*',
    ('25_sagesse/page_0189', 'Num. XII. 31'): 'Nombres 11:31*',
    ('26_ecclesiastique/page_0209', 'IX. 1'): 'Ecclésiastique 9:9*',
    ('26_ecclesiastique/page_0254', 'Tob. 11. 22'): 'Tobie 2:22*',
    ('26_ecclesiastique/page_0337', 'Prov. VIII. 70'): 'Proverbes 8. 70',
    ('26_ecclesiastique/page_0371', 'Psal. X. 5. 17'): 'Psaumes 9:26, 38',
    ('26_ecclesiastique/page_0423', 'Psal. CXLVII. 20'): 'Psaumes 147:9*',
    ('26_ecclesiastique/page_0434', 'Eccl. XVII 1. 31'): 'Ecclésiastique 17:1, 31*',
    ('26_ecclesiastique/page_0492', 'I. Reg. XXVI. 36'): '1 Rois 25:36*',
    ('26_ecclesiastique/page_0602', 'Num XVI. 21. 70'): 'Nombres 16:21. 70',
    ('26_ecclesiastique/page_0603', '4. Reg. 1. 24'): '4 Rois 2:24*',
    ('26_ecclesiastique/page_0638', 'Psal. CXLVII. 10'): 'Psaumes 147:9*',
    ('26_ecclesiastique/page_0644', 'Jerem. LXV. 11'): 'Isaïe 65:11*',
    ('26_ecclesiastique/page_0646', 'Psal. XCVIII. 91'): 'Psaumes 118:91*',
    ('26_ecclesiastique/page_0648', 'Pseaume CXLVII. 17'): 'Psaume 147:6*',
    ('26_ecclesiastique/page_0665', 'Num. XII. 23'): 'Nombres 13:23*',
    ('26_ecclesiastique/page_0699', '4. Reg. XVIII. 40. 41'): '3 Rois 18:40-41*',
    ('26_ecclesiastique/page_0710', 'XX. 37'): '2 Paralipomènes 20:37*',
    ('26_ecclesiastique/page_0710', '3. Reg. XIII. 43. 44'): '3 Rois 22:43-44*',
    ('26_ecclesiastique/page_0738', '1. Reg. IV. 29'): '3 Rois 4:29*',
    ('26_ecclesiastique/page_0738', '1. Reg. III. 9, 22'): '3 Rois 3:9, 22*',
    ('27_isaie/page_0134', 'Psal. XVIII. 45'): 'Psaumes 17:45*',
    ('27_isaie/page_0160', 'it. 13'): '',
    ('27_isaie/page_0168', 'it. 6'): '',
    ('27_isaie/page_0224', '2. Par. v. 26'): '1 Paralipomènes 5:26*',
    ('27_isaie/page_0257', 'Joan. XXXII. 33'): 'Jean 12:32, 33*',
    ('27_isaie/page_0275', 'Amòs X. 8'): 'Amos 5:8*',
    ('27_isaie/page_0280', 'Isai. XIV. 23. et 70'): 'Isaïe 14:23. 70',
    ('27_isaie/page_0280', 'Isaïe 14:23. 70'): '',
    ('27_isaie/page_0295', '2. Petr. v. 13'): '1 Pierre 5:13*',
    ('27_isaie/page_0309', '2. Reg. XXXIII. 20'): '2 Paralipomènes 33:20*',
    ('27_isaie/page_0327', 'Jerem. XLV. 9'): 'Jérémie 46:9*',
    ('27_isaie/page_0372', '4. Reg. XXII. 29'): '4 Rois 23:29*',
    ('27_isaie/page_0375', '4. Reg. XXIV. 26'): '4 Rois 25:26*',
    ('27_isaie/page_0394', '2. Par. XXXIX. 10'): '2 Paralipomènes 30:10*',
    ('27_isaie/page_0409', 'Sophon. 111. 13'): 'Sophonie 3:13*',
    ('27_isaie/page_0440', 'I. Reg. v. 20'): '2 Rois 5:20*',
    ('27_isaie/page_0505', 'Ezech. XXXII. 47'): 'Ézéchiel 32:7*',
    ('27_isaie/page_0532', 'Psal. LIV. 28'): 'Psaumes 54:24*',
    ('27_isaie/page_0619', 'Isai. 113. 17'): 'Isaïe 3:17*',
    ('27_isaie/page_0649', 'it 43'): '',
    ('27_isaie/page_0652', 'Matth. XVI. 67'): 'Matthieu 26:67*',
    ('27_isaie/page_0700', 'Is. 70. 1'): '',
    ('27_isaie/page_0706', 'Dan. 1. 31'): 'Daniel 11:31*',
    ('27_isaie/page_0711', 'Esaï. LVII. 70'): 'Isaïe 57. 70',
    ('27_isaie/page_0711', 'Isaïe 57. 70'): '',
    ('27_isaie/page_0741', 'Psal. XVIII. 27'): 'Psaumes 17:27*',
    ('27_isaie/page_0774', 'Psal. CXXXIII. 2. 3. 4'): 'Psaumes 133:2-3*',
    ('27_isaie/page_0780', 'Isai. LII. 11. 17'): 'Isaïe 51:17*',
    ('27_isaie/page_0810', 'Psal. LIV. 29'): 'Psaumes 68:29*',
    ('27_isaie/page_0823', 'Ps. CXXIX. 14'): 'Psaumes 138:14*',
    ('28_jeremie/page_0097', '1. Reg. XVI 1. 33'): '3 Rois 16:33*',
    ('28_jeremie/page_0107', 'I. Par. XVII. 29'): '1 Paralipomènes 27:29*',
    ('28_jeremie/page_0110', 'Pseaume XXII. 7. 8. 9'): 'Psaume 21:7-9*',
    ('28_jeremie/page_0126', 'Jerem. XXXVII. 300. 10'): 'Jérémie 37:10*',
    ('28_jeremie/page_0129', 'Prov. XXXIII. 27. 28'): 'Proverbes 23:27-28*',
    ('28_jeremie/page_0140', 'Osee X. 16'): 'Osée 10:6*',
    ('28_jeremie/page_0172', 'Jerem. 1. 13. 14. 15. et 111. 18'): 'Jérémie 1:13-15 et 3:18*',
    ('28_jeremie/page_0174', 'Abd. 5'): 'Abdias 1:5*',
    ('28_jeremie/page_0201', 'Osee IV. 31'): 'Osée 1:11*',
    ('28_jeremie/page_0224', 'Psal. CXX. 24'): 'Psaumes 108:24*',
    ('28_jeremie/page_0432', 'Judic. X. 34'): 'Juges 11:34*',
    ('28_jeremie/page_0470', 'Genes. XXV. 50'): 'Genèse 31:50*',
    ('28_jeremie/page_0572', 'Psal. LXXIV. 23'): 'Psaumes 73:23*',
    ('28_jeremie/page_0578', 'Sophon. 11. 4. 5'): 'Sophonie 2:4-5*',
    ('28_jeremie/page_0578', 'Isaï. xxv. 20'): None,
    ('28_jeremie/page_0581', 'Joël. III. 45'): 'Joël 3:4-5*',
    ('28_jeremie/page_0581', 'Ezech. XXVIII. 21. 28'): None,
    ('28_jeremie/page_0597', '2. Macc. V. 36'): '1 Machabées 5:36*',
    ('28_jeremie/page_0660', 'Joël. II.40'): 'Joël 2:30*',
    ('28_jeremie/page_0688', '4. Reg. xxiv. 27'): '4 Rois 25:27*',
    ('29_lamentations/page_0008', 'Abdias V. 11'): 'Abdias 1:11*',
    ('29_lamentations/page_0008', 'Abdias V. 10'): 'Abdias 1:10*',
    ('29_lamentations/page_0026', '4. Reg. XXIV. 21'): '4 Rois 25:21*',
    ('29_lamentations/page_0079', 'Jerem. LII. 11. 70'): 'Jérémie 52:11. 70',
    ('30_baruch/page_0009', 'Exod. XIII 43'): 'Exode 12:43*',
    ('30_baruch/page_0033', 'Psal. CXVI. 20'): 'Psaumes 118:20*',
    ('30_baruch/page_0033', 'Psal. CXVI. 142'): 'Psaumes 118:142*',
    ('31_ezechiel/page_0104', '2. Par. XXXIII. 45'): '2 Paralipomènes 33:7*',
    ('31_ezechiel/page_0112', 'Hebr. XVI. 29'): '',
    ('31_ezechiel/page_0137', 'XXXVIII. 18. 23'): 'Jérémie 38:18, 23*',
    ('31_ezechiel/page_0169', 'num. 60'): '',
    ('31_ezechiel/page_0184', 'Jerem. XLVIII. 48'): 'Jérémie 48:47*',
    ('31_ezechiel/page_0206', 'num. 40'): '',
    ('31_ezechiel/page_0227', 'XIII. 2'): 'Exode 13:2*',
    ('31_ezechiel/page_0256', '2. Esdr. XLIV. 20'): '2 Esdras 13:20*',
    ('31_ezechiel/page_0256', 'Jerem. XI. 28'): 'Jérémie 6:28*',
    ('31_ezechiel/page_0261', 'Genes. xxiii. 23'): 'Genèse 23:16*',
    ('31_ezechiel/page_0283', 'num. 48'): '',
    ('31_ezechiel/page_0327', 'Jerem. XIX. 18'): 'Jérémie 19:8*',
    ('31_ezechiel/page_0337', '4. Reg. XVI. 31'): '3 Rois 16:31*',
    ('31_ezechiel/page_0341', 'Psalm. LXXIV. 13'): 'Psaumes 73:13*',
    ('31_ezechiel/page_0348', 'Psal. VIII. 13'): None,
    ('31_ezechiel/page_0362', 'Psalm. XXVI. 55'): 'Psaumes 28:5*',
    ('31_ezechiel/page_0407', 'Ezech. XXII. 35'): 'Ézéchiel 23:35*',
    ('31_ezechiel/page_0419', 'Psal. LX. 10'): 'Psaumes 59:10*',
    ('31_ezechiel/page_0421', 'Psal. LXXXVI. 13'): 'Psaumes 85:13*',
    ('31_ezechiel/page_0473', 'Psal. cxxv. 13'): None,
    ('31_ezechiel/page_0479', 'I. Rois 6. 31'): '3 Rois 6:31*',
    ('31_ezechiel/page_0486', 'Exod. XXXIII. 42. 43'): 'Exode 28:42-43*',
    ('31_ezechiel/page_0497', '4. Reg. VIII. 64'): '3 Rois 8:64*',
    ('31_ezechiel/page_0517', 'VIII. 1'): '2 Esdras 8:1*',
    ('31_ezechiel/page_0537', 'Deut. III. 17. 19. 49'): 'Deutéronome 3:17 et 4:49*',
    ('31_ezechiel/page_0539', 'Isai. XXV. 44'): None,
    ('32_daniel/page_0114', 'col. 322'): '',
    ('32_daniel/page_0122', 'Psal. LXXIII. 24'): 'Psaumes 73:14*',
    ('32_daniel/page_0123', 'Genes. XL. 42'): 'Genèse 41:42*',
    ('32_daniel/page_0216', '2. Macc. I. 56'): '1 Machabées 1:56*',
    ('33_osee/page_0129', '1. Cor. V. 21'): '2 Corinthiens 5:21*',
    ('33_osee/page_0137', 'Jerem. XXVIII. 20. 22'): 'Jérémie 48:43-44*',
    ('33_osee/page_0145', 'Isai. XVII. 19'): None,
    ('33_osee/page_0188', '2. Reg. IV. 21. 22'): '3 Rois 4:21-22*',
    ('33_osee/page_0188', '2. Cor. XV. 32'): '1 Corinthiens 15:32*',
    ('33_osee/page_0215', 'Psal. LXXXVI. 13'): 'Psaumes 85:13*',
    ('34_joel/page_0025', 'Genes. XXVI. 27. 28. et 39'): 'Genèse 27:28 et 39*',
    ('35_amos/page_0006', 'x 70'): '',
    ('35_amos/page_0013', '4. Reg. XV. 29. 40'): '4 Rois 15:29*',
    ('35_amos/page_0080', 'Mich. 11. 6'): 'Michée 2:6*',
    ('35_amos/page_0089', 'Amos VI. 9. 16'): 'Amos 6:9-10*',
    ('37_jonas/page_0008', 'Psal. CXXXIII. 8. 9'): 'Psaumes 138:8-9*',
    ('38_michee/page_0021', '1. Esdr. IX. 17'): '2 Esdras 9:17*',
    ('40_habacuc/page_0023', 'Job xxvi. 16'): 'Job 26:12*',
    ('41_sophonie/page_0016', 'Joël V. 2'): 'Joël 2:5*',
    ('41_sophonie/page_0018', 'Sagesse XIII. 23. 24'): 'Sagesse 14:23-24*',
    ('41_sophonie/page_0026', '3. Reg. XIV. 38'): '1 Rois 14:38*',
    ('43_zacharie/page_0029', 'Isai. IV. 13'): 'Isaïe 4:1*',
    ('43_zacharie/page_0111', 'Psal. XVIII. 8. 16'): 'Psaumes 17:8, 16*',
    ('43_zacharie/page_0121', 'Exod. XIII. 48'): 'Exode 12:48*',
    ('44_malachie/page_0020', 'Malach. 112'): 'Malachie 1:12*',
    ('44_malachie/page_0033', 'Agg. 1. 7. 8. et 11. 20'): 'Aggée 1:7-8 et 2:20*',
    ('45_1_maccabees/page_0089', 'Ecclésiastique cxliv. 10'): 'Ecclésiastique 44:10*',
    ('45_1_maccabees/page_0093', 'Psal. CV. 111. 1'): 'Psaumes 118:1*',
    ('45_1_maccabees/page_0095', 'Job. XIX. 43'): 'Job 29:13*',
    ('45_1_maccabees/page_0191', 'Josue XVI. 30'): None,
    ('45_1_maccabees/page_0272', '1. Reg. IV, 25'): '3 Rois 4:25*',
    ('45_1_maccabees/page_0294', '1. Par. XIII. 26'): '2 Paralipomènes 13:12*',
    ('46_2_maccabees/page_0026', 'Joan. X. 48'): 'Jean 10:22*',
    ('46_2_maccabees/page_0032', '1. Macc. XVII. 32'): None,
    ('46_2_maccabees/page_0086', 'Jacob. 11. 12'): '',
    ('46_2_maccabees/page_0105', 'Dan. XI. 298'): 'Daniel 11:28*',
    ('46_2_maccabees/page_0171', '1. Macc. 11, 36'): '1 Machabées 2:36*',
}


def tell(src, book):
    """Why `src` is old style, or None if it is already written out."""
    s = src.strip(" .,;")
    if FULL.fullmatch(s):
        return None
    if ROMAN_CH.search(s):
        return "roman"
    if "℣" in s or re.match(r"[1-4IV]+\.\s", s):
        return "prefix"
    name = re.match(r"(?:[1-4IV]+\.?\s*)?([A-Za-zÀ-ÿſ]+)", s)
    if name and plain(name.group(1)) != plain(book.split()[-1] if book[0].isdigit() else book.split()[0]):
        return "abbr"
    return None


def risky(src, text, start, end):
    """Readings find_refs gets wrong: "deuil" (deu + il), "Lévitique 1, 2" (chapters or 1:2?)."""
    m = re.match(r"\s*(?:[1-4IV]+\.?\s*)?[A-Za-zÀ-ÿſ]+", src)  # None: a continuation (", XXI. 3.")
    after = src[m.end():m.end() + 1] if m else " "
    if not after or after not in " .,":  # "deuil" = deu + il, "exil", "collet"
        return "no break after name"
    if end < len(text) and text[end].isalpha():  # "Genèse. C|et"
        return "runs into a word"
    if start and text[start - 1].isalpha():
        return "inside a word"
    if not ROMAN_CH.search(src) and ":" not in src and re.search(r"\d+\s*,\s*\d+", src):
        return "C, V or two chapters?"
    return None


def refs(text):
    """find_refs, plus the bare chapters it leaves after a reference."""
    out = []
    for r in find_refs(text):
        out.append(r)
        end = r.end
        while True:
            k = BARE.match(text, end)
            if k and num(k.group("c")):
                out.append(Ref(k.start(), k.end(), r.book, r.name, num(k.group("c")), _verses(k.group("v")), k.group(0)))
            elif not (k := DONE.match(text, end)):  # "33:10." already written out: go on past it
                break
            end = k.end()
    return out


def rewrite(text, where, review, changes):
    out, pos = [], 0
    text = unitalic(text)
    for r in refs(text):
        if r.start < pos:
            continue
        why = tell(r.src, r.book)
        if not why or " " in r.book and text[:r.start].endswith(r.book.rsplit(" ", 1)[0] + " "):
            continue  # modern already, or the tail of "Cantique des cantiques 5:1"
        lead = len(r.src) - len(r.src.lstrip(" .,;&et"))  # continuation: keep its separator
        src = r.src[lead:]
        new = r.render(with_book=not lead)
        bad = risky(r.src, text, r.start, r.end)
        if new == src.rstrip(" ."):
            continue
        key = (where[0], " ".join(src.strip(" .,;").split()))
        if MANUAL.get(key) == "":
            continue
        if key in MANUAL:
            new, bad = MANUAL[key] or new, None
        elif not bad and exists(r) is False:
            if not BARE.fullmatch(r.src):  # in a list after a good reference: Calmet's misprint

                bad = "not in the Vulgate"
        if bad == "no break after name":  # a word, not a reference
            continue
        if bad:
            review.append((*where, bad, src, new, text[max(0, r.start - 40):r.end + 20]))
            continue
        trail = src[len(src.rstrip(" .")):]  # "IV. 9." -> keep the final full stop
        sep = r.src[:lead]
        sep = " ; " if ";" in sep else ", " if "," in sep else " et " if "et" in sep or "&" in sep else ". "
        if not lead and re.search(r"\b(?:le|du|au)\s+$", text[:r.start]):
            new = new.replace("Psaumes ", "Psaume ", 1)  # "le Psaume 36:25"
        out.append((r.start, r.end, (sep if lead else "") + new + ("." if trail.strip() else "")))
        changes.append((*where, src, new))
        pos = r.end
    for s, e, new in reversed(out):
        text = text[:s] + new + text[e:]
    return text


def main(argv):
    apply = "--apply" in argv
    books = [a for a in argv if not a.startswith("--")]
    review, changes, touched = [], [], 0
    for f in sorted(DATA.glob("*/normalized/page_*.json")):
        book = f.parent.parent.name
        if books and book not in books:
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        before = json.dumps(d, ensure_ascii=False)
        for c in d.get("commentary") or []:
            if isinstance(c.get("french_commentary"), str):
                c["french_commentary"] = rewrite(c["french_commentary"], (f"{book}/{f.stem}", "c"), review, changes)
        for n in d.get("footnotes") or []:
            if isinstance(n, dict) and isinstance(n.get("text"), str):
                n["text"] = rewrite(n["text"], (f"{book}/{f.stem}", n.get("marker", "f")), review, changes)
        if json.dumps(d, ensure_ascii=False) != before:
            touched += 1
            if apply:
                f.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    rep = DATA.parent / "reports"
    rep.mkdir(exist_ok=True)
    (rep / "modernize_refs_review.tsv").write_text(
        "".join("\t".join(map(str, x)).replace("\n", " ") + "\n" for x in review), encoding="utf-8")
    if not apply:
        (rep / "modernize_refs_changes.tsv").write_text(
            "".join("\t".join(x) + "\n" for x in changes), encoding="utf-8")
    print(f"{len(changes)} rewritten in {touched} pages{'' if apply else ' (dry run)'}; "
          f"{len(review)} to review -> reports/modernize_refs_review.tsv")


if __name__ == "__main__":
    main(sys.argv[1:])
