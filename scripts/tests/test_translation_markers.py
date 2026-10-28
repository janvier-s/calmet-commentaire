"""The audit's commentary / variant markers in a french_translation."""
import audit_integrity as A


def test_hebrew_letter_and_septante():
    assert A.translation_markers("L'Hébreu : _Il marcha._") == ["L'Hébreu"]
    assert A.translation_markers("L’hébreu à la lettre : _Il marcha._") == ["L’hébreu", "à la lettre"]
    assert A.translation_markers("Les Septante : _Il marcha._") == ["Septante"]


def test_ou_is_a_standalone_word():
    assert A.translation_markers("Vous ou moi.") == ["ou"]
    assert A.translation_markers("Où êtes-vous ?") == []
    assert A.translation_markers("Il a beaucoup marché.") == []


def test_markers_are_in_reading_order_without_repeats():
    assert A.translation_markers("Ou, selon l'hébreu, ou selon les Septante.") == ["Ou", "l'hébreu", "Septante"]
