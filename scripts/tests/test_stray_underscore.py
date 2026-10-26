"""audit_integrity.stray_underscore: the "_" out of place, not just an odd count."""
from audit_integrity import stray_underscore as s


def test_balanced_italics_pass():
    assert s("L'Hébreu : _Il passera._ Les Septante : ^{(f)} _Il viendra_, dit-il.") is None
    assert s("…_Jam natus adequat_ te.") is None
    assert s("Ita _saint Jérôme._ Et _Ponens in thesauris_ ; Jérémie.") is None


def test_the_stray_one_is_found():
    t = "Les Septante : _Sameda (_ou _Samaa) de Mzecca._"
    i, why = s(t)
    assert t[i:i + 3] == "_ou" and "while they are open" in why  # an even count, still wrong
    i, why = s("L'Hébreu porte :_ Le chandelier pur.")
    assert "not opened" in why
    i, why = s("Il dit : _ou, un songe qui avait dit")
    assert i == 9 and "never closed" in why
