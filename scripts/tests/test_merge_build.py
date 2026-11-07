"""merge_build: a unit's decided changes as operations on normalized's fields; the merged pages."""
import good_units
import merge_build


def test_text_map_matches_good_units():
    texts = ["Son Verbe ^{(a)} et", "  sa  sagesse"]
    joined, idx = merge_build.text_map(texts)
    assert joined == good_units._text(" ".join(texts)) == "Son Verbe et sa sagesse"
    assert len(idx) == len(joined)
    assert idx[joined.index("et")] == (0, texts[0].index("et"))
    assert idx[joined.index("sa ")] == (1, 2)
    assert idx[joined.index(" sa")] == (1, -1)


def test_take_good_keeps_marker():
    c = {"good_punct": "sa sagesse", "good_raw": "sa sagese"}
    assert merge_build.change_text(c, "son Verbe ^{(a)}", "good", None) == "sa sagesse ^{(a)}"


def test_cut_keeps_marker_at_point():
    assert merge_build.change_text({"good_raw": ""}, "mot ^{(b)}", "good", None) == "^{(b)}"


def test_both_and_edit():
    c = {"good_modern": "Dieu tout-puissant"}
    assert merge_build.change_text(c, "Dieu", "both", None) == "Dieu Dieu tout-puissant"
    assert merge_build.change_text(c, "Dieu", "edit", "Le Dieu") == "Le Dieu"
    assert merge_build.change_text(c, "Dieu", "old", None) == "Dieu"


def test_glued_punctuation_kept():
    assert merge_build.change_text({"good_punct": "la Terre"}, "le Monde,", "good", None) == "la Terre,"
    assert merge_build.change_text({"good_punct": "la Terre;"}, "le Monde,", "good", None) == "la Terre;"


def test_apply_ops_right_to_left_and_insert_spacing():
    t = "Au commencement Dieu crée le Ciel"
    ops = [{"a": 16, "b": 20, "new": "le Seigneur"}, {"a": 33, "b": 33, "new": "et la Terre"}]
    assert merge_build.apply_ops(t, ops) == "Au commencement le Seigneur crée le Ciel et la Terre"


def test_apply_ops_insert_between_words_and_cut():
    t = "Dieu crée le Ciel"
    assert merge_build.apply_ops(t, [{"a": 5, "b": 5, "new": "alors"}]) == "Dieu alors crée le Ciel"
    assert merge_build.apply_ops(t, [{"a": 4, "b": 4, "new": "alors"}]) == "Dieu alors crée le Ciel"
    assert merge_build.apply_ops(t, [{"a": 5, "b": 10, "new": ""}]) == "Dieu le Ciel"
    assert merge_build.apply_ops(t, [{"a": 0, "b": 0, "new": "Et"}]) == "Et Dieu crée le Ciel"


def test_renumber_after_marker_dropped():
    before = {"commentary": [{"french_commentary": "x ^{(a)} y ^{(b)} z ^{(c)}"}],
              "footnotes": [{"marker": "(a)", "text": "A"}, {"marker": "(b)", "text": "B"},
                            {"marker": "(c)", "text": "C"}]}
    page = {"commentary": [{"french_commentary": "x ^{(a)} y z ^{(c)}"}], "footnotes": before["footnotes"]}
    out = merge_build.renumber(page, before)
    assert out["commentary"][0]["french_commentary"] == "x ^{(a)} y z ^{(b)}"
    assert [(f["marker"], f["text"]) for f in out["footnotes"]] == [("(a)", "A"), ("(b)", "C")]
    assert before["footnotes"][1]["marker"] == "(b)"  # normalized's own page untouched


def test_renumber_untouched_when_markers_same():
    p = {"commentary": [{"french_commentary": "x ^{(b)}"}],
         "footnotes": [{"marker": "(a)", "text": "prev page"}, {"marker": "(b)", "text": "B"}]}
    assert merge_build.renumber(p, p) == p


# --- unit_ops: the unit's decisions as operations on its fields ---

import json  # noqa: E402

import merge_decisions as md  # noqa: E402
from test_merge_view import FIELDS, T2, make_units  # noqa: E402

TEXTS = list(FIELDS.values())


def _unit(data_dir, c3=None):
    doc = json.loads(make_units(data_dir).read_text())
    u = doc["units"][0]
    if c3:
        u["changes"][2].update(c3)
    return u


def test_unit_ops_unplaced_decided_change_by_tokens(data_dir):
    docs = data_dir.parent / "docs"
    u = _unit(data_dir, {"old": "a de", "at": 15, "good_raw": "avec", "good_modern": "avec"})
    md.decide(docs, "22_proverbes", u["uid"], u["changes"][2], "good")
    r = merge_build.unit_ops(u, TEXTS, md.load(docs, "22_proverbes"))
    ops = r["ops"][(194, T2)]
    assert [(o["a"], o["b"], o["new"]) for o in ops] == [(15, 19, "avec")]
    md.decide(docs, "22_proverbes", u["uid"], u["changes"][2], None)
    u["changes"][2]["at"] = 30
    md.decide(docs, "22_proverbes", u["uid"], u["changes"][2], "good")
    r = merge_build.unit_ops(u, TEXTS, md.load(docs, "22_proverbes"))
    assert r["ops"].get((194, T2), []) == [] and [s["why"] for s in r["skipped"]] == ["not found"]


def test_unit_ops_overlap_skipped(data_dir):
    docs = data_dir.parent / "docs"
    u = _unit(data_dir, {"old": "de la sagesse", "at": 17, "good_raw": "du savoir", "good_modern": "du savoir"})
    md.decide(docs, "22_proverbes", u["uid"], u["changes"][1], "good")
    md.decide(docs, "22_proverbes", u["uid"], u["changes"][2], "good")
    r = merge_build.unit_ops(u, TEXTS, md.load(docs, "22_proverbes"))
    assert [o["key"].split("@")[0] for o in r["ops"][(194, T2)]] == ["c2"]
    assert [(s["key"].split("@")[0], s["why"]) for s in r["skipped"]] == [("c3", "overlap")]


def test_spans_cut_then_insert_at_its_end():
    t = "les mots coupés suivis"
    ops = [{"a": 0, "b": 15, "new": ""}, {"a": 15, "b": 15, "new": "Nouveau texte"}]
    assert merge_build.apply_ops(t, ops) == "Nouveau texte suivis"


def test_spans_two_cuts_at_a_field_start():
    t = "pître aux Éphésiens nous a"
    assert merge_build.apply_ops(t, [{"a": 0, "b": 5, "new": ""}, {"a": 6, "b": 19, "new": ""}]) == "nous a"
