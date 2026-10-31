"""footnote_expand: Calmet's citations written out in French, or left to Claude (None)."""
import pytest

import footnote_expand as X
from footnotes import ABBREV


@pytest.mark.parametrize("note, written", [
    ("Aug. l. XXII. contra Faust. cap. 84. Theodoret. quaest. 96. in Genes.",
     "Saint Augustin, Contre Fauste, livre 22, chapitre 84 ; Théodoret, Question 96 sur la Genèse."),
    ("Plin. l. 7:12.", "Pline, Histoire naturelle, livre 7, chapitre 12."),
    ("Plin. lib. 6. 28.", "Pline, Histoire naturelle, livre 6, chapitre 28."),
    ("Vide Genes. 3. 4.", "Voyez Genèse 3:4."),
    ("Ita Cornel.", "Ainsi Cornelius a Lapide."),
    ("Vid. si lubet, Bochart.", "Voyez, si l'on veut, Bochart."),
    ("Ovid. Metam. lib. 8. verset 749.", "Ovide, Métamorphoses, livre 8, vers 749."),
    ("Chrysost. homil. 3. in Hexaëmer.", "Saint Jean Chrysostome, Homélie 3 sur l'Hexaméron."),
    ("Clem. Alex. Strom. 5.", "Saint Clément d'Alexandrie, Stromates 5."),
    ("Aug. l. 4. Confess. c. 3. lib. 5. de Civit. c. 2.",
     "Saint Augustin, Confessions, livre 4, chapitre 3 ; La Cité de Dieu, livre 5, chapitre 2."),
    ("Hieron. in Isai. cap. 2. et alii.", "Saint Jérôme, sur Isaïe, chapitre 2 ; et d'autres."),
    ("Tertull. de Carne Christi, c. 5.", "Tertullien, De la chair du Christ, chapitre 5."),
    ("Aug. passim.", "Saint Augustin, passim."),
])
def test_written_out(note, written):
    assert X.expand(note, ABBREV) == written


@pytest.mark.parametrize("note, why", [
    ("Plin. 13. cap. 3.", "13"),             # a number left over before the place
    ("Æneid. VII. V. 176.", "176."),         # which number is which?
    ("Joseph. Antiq. l. 1. c. 7. edit. Paris. 1675.", "1675."),
])
def test_left_to_claude(note, why):
    assert X.expand(note, ABBREV) is None
    with pytest.raises(X.Unknown, match=why):
        X.parse(note)


def test_parse_groups_places_under_their_work():
    lead, cites = X.parse("Aug. l. 4. Confess. c. 3.")
    assert lead == ""
    assert cites == [{"lead": "", "author": "saint Augustin",
                      "groups": [[("place", ("livre 4", False)), ("work", "Confessions"), ("place", ("chapitre 3", False))]]}]


def test_not_expanded_with_brackets_or_lines():
    assert X.expand("Aug. l. 4. [UNCERTAIN WORD]", ABBREV) is None
    assert X.expand("Aug. l. 4.\nConfess. c. 3.", ABBREV) is None
