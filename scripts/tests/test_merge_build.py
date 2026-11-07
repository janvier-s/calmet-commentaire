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
