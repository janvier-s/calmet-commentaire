import json

import pytest

import good_normalized as gn
import good_spell as gs
import good_spell_agent as ga


@pytest.fixture(autouse=True)
def hunspell(monkeypatch):
    """No hunspell: the words it would flag, with its suggestions (None: a known word)."""
    flagged = {"chatiment": "châtiment, chatiments", "avancerent": "avancèrent, avancent", "prefque": "presque, prefaçue",
               "extraordimaire": "extraordinaire", "envoïé": "envoie, envoyé", "posson": "poisson, passion",
               "tres": "très", "ridieule": "ridicule", "inconnu": "", "avancèrent": None}
    monkeypatch.setattr(gs, "_known", {w: v for w, v in flagged.items() if v is not None} | {"avancèrent": None})
    monkeypatch.setattr(gs.spellcheck, "check", lambda ws: {w: flagged[w] for w in ws if flagged.get(w)})
    monkeypatch.setattr(gs.spellcheck, "known_names", lambda: set())
    monkeypatch.setattr(gs.spellcheck, "french_words", lambda: frozenset({"presque", "extraordinaire", "ridicule", "poisson"}))
    monkeypatch.setattr(gs, "vulgate_words", lambda: {"tres"})


def test_accent_erent_and_slips_are_mended():
    assert gs.fix("le chatiment, ils avancerent, prefque ridieule extraordimaire") == \
        "le châtiment, ils avancèrent, presque ridicule extraordinaire"


def test_what_is_not_sure_stays():
    assert gs.fix("envoïé inconnu tres posson _chatiment_") == "envoïé inconnu tres posson _chatiment_"


def test_doubled_function_words_only():
    assert gs.fix("la la Terre de de Dieu nous nous") == "la Terre de Dieu nous nous"


def test_a_lost_capital_after_an_apostrophe_is_not_a_slip():
    assert gs.fix("l'prefque") == "l'prefque"


def test_agent_import_checks_then_stores_records(tmp_path, monkeypatch):
    monkeypatch.setattr(ga, "DATA", tmp_path)
    monkeypatch.setattr(gn, "DATA", tmp_path)
    (tmp_path / "v").mkdir()
    text = "As commencement Dieu _créa_ le ciel^{(a)} ov la Terre"
    doc = {"units": [{"uid": "u", "changes": [{"id": "c1", "good_punct": text}]}]}
    (tmp_path / "v" / "good_units.json").write_text(json.dumps(doc))
    ans = [{"id": "c1", "changes": [
        {"before": "As", "after": "Au", "ctx": ""},
        {"before": "ov", "after": "ou", "ctx": "ciel^{(a)}"},
        {"before": "créa", "after": "crea", "ctx": "Dieu"},                 # not found (the underscores)
        {"before": "Dieu _créa_", "after": "Dieu créa", "ctx": "commencement"},  # marks lost
        {"before": "la", "after": "la 2", "ctx": "ov"}]}]                    # a digit
    f = tmp_path / "ans.json"
    f.write_text(json.dumps(ans))
    ga.import_("v", ans, dry=False)
    st = json.loads(gn.store_path(tmp_path, "v").read_text())
    assert [r["after"] for r in st["changes"]["c1"]["agent"]] == ["Au", "ou"]
    gn.overlay(doc, st, {})
    assert doc["units"][0]["changes"][0]["good_normalized"] == "Au commencement Dieu _créa_ le ciel^{(a)} ou la Terre"
    undone = {"c1": ["ov => ou"]}
    gn.overlay(doc, st, undone)
    assert doc["units"][0]["changes"][0]["good_normalized"].endswith("ov la Terre")
    assert gn.compute(doc, st["changes"])["changes"]["c1"]["agent"]  # a recompute keeps the agent records
