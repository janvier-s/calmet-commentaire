import pytest
from latin_italics import apply_spans, find_latin_spans, load_vocabularies

@pytest.fixture(scope="module")
def vocabs():
    return load_vocabularies()


def test_verse_quote_italicized(vocabs):
    vul, props, pure, french_words, fn_names = vocabs
    text = "Dieu prend les voies propres à dessécher ces eaux. Adduxit spiritum super terram, et imminutæ sunt aquæ. Il fit lever un grand vent..."
    spans = find_latin_spans(text, vul, props, pure, french_words, fn_names)
    assert len(spans) == 1
    assert spans[0][2] == "Adduxit spiritum super terram, et imminutæ sunt aquæ"
    out = apply_spans(text, spans)
    assert "_Adduxit spiritum super terram, et imminutæ sunt aquæ_." in out


def test_quote_with_etc(vocabs):
    vul, props, pure, french_words, fn_names = vocabs
    text = "On l'enseigne ici aux étoiles seules, posuit eas, etc."
    spans = find_latin_spans(text, vul, props, pure, french_words, fn_names)
    assert len(spans) == 1
    assert "posuit eas, etc." in spans[0][2]
    out = apply_spans(text, spans)
    assert "_posuit eas, etc._" in out


def test_locution_continuation(vocabs):
    vul, props, pure, french_words, fn_names = vocabs
    text = "il dit qu'il a été porté _ad extrema montium descendi ;_ retro versus. C'est ce qui est aussi..."
    spans = find_latin_spans(text, vul, props, pure, french_words, fn_names)
    assert any("retro versus" in s[2] for s in spans)
    out = apply_spans(text, spans)
    assert "_ad extrema montium descendi ; retro versus_." in out


def test_quoted_single_word(vocabs):
    vul, props, pure, french_words, fn_names = vocabs
    text = "La Vulgate a voulu exprimer par Poenituit eum. Dieu n'est pas capable de se repentir..."
    spans = find_latin_spans(text, vul, props, pure, french_words, fn_names)
    assert len(spans) == 1
    assert spans[0][2] == "Poenituit eum"
    out = apply_spans(text, spans)
    assert "_Poenituit eum_." in out


def test_french_homographs_not_italicized(vocabs):
    vul, props, pure, french_words, fn_names = vocabs
    text = "une consistance plus forte et plus solide que les eaux supérieures"
    spans = find_latin_spans(text, vul, props, pure, french_words, fn_names)
    assert spans == []

    text2 = "Tertullien et saint Augustin considèrent Enoch, et Élie comme les gages..."
    spans2 = find_latin_spans(text2, vul, props, pure, french_words, fn_names)
    assert spans2 == []

    text3 = "du côté septentrional du mont Taurus, et qu'il coule d'abord vers l'Occident..."
    spans3 = find_latin_spans(text3, vul, props, pure, french_words, fn_names)
    assert spans3 == []


def test_existing_italics_not_broken(vocabs):
    vul, props, pure, french_words, fn_names = vocabs
    text = "Balaam disait : ^{(e)} _Sta Balac et ausculta, audi fili Beor._ Moïse et Josué..."
    spans = find_latin_spans(text, vul, props, pure, french_words, fn_names)
    assert spans == []
    out = apply_spans(text, spans)
    assert out == text
