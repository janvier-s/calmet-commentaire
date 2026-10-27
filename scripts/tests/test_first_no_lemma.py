"""The first note of a page with no lemma: the lemma lost, or the next sentence of the note before."""
import pytest

import audit_integrity as A

@pytest.fixture(autouse=True)
def counts(monkeypatch):
    c = {"ézéchiel": [0, 40], "si": [900, 5], "on": [900, 5], "l": [900, 0], "il": [900, 5]}
    monkeypatch.setattr(A, "word_case_counts", lambda: c)


def check(tail, fc):
    return A.first_note_without_lemma(tail, fc)


def test_lemma_in_capitals_at_the_start():
    assert check("et c'est tout.", "BATHUEL, c'est apparemment Béthul, ou Béthulie.") == "lemma"


def test_new_sentence_after_a_full_stop():
    assert check("la fin du récit.", "Si l'on pouvait faire fond sur ce récit,") == "sentence"
    assert check("la fin du récit. ^{(a)}", "L'Homme fut créé ; et quand") == "sentence"


def test_goes_on_from_the_page_before():
    assert check("la fin du récit.", "et les autres Interprètes") is None  # lower case
    assert check("dans le lieu où", "L'Homme fut créé") is None  # sentence not finished
    assert check("selon _Moïse._", "Si l'on veut") == "sentence"
    assert check("selon _Moïse", "Si l'on veut") is None  # italics still open


def test_abbreviation_is_not_a_full_stop():
    assert check("voyez le v.", "Si l'on veut") is None


def test_names_are_left_out():
    assert check("la fin du récit.", "Ézéchiel nous détermine encore") is None


def test_hyphen_cut_is_not_ours():
    assert check("appliquées à JÉSUS-", "CHRIST, elles se prennent à la rigueur") is None


def test_proper_noun_start_reads_the_first_word_only():
    assert A.proper_noun_start("Ézéchiel nous détermine")
    assert not A.proper_noun_start("Si l'on pouvait")
    assert not A.proper_noun_start("L'Ézéchiel de")  # "L'" is the article
    assert not A.proper_noun_start("")
