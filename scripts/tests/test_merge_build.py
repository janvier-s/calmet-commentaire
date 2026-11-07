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


# --- the merged pages ---

from review_store import Store  # noqa: E402

VOL = "22_proverbes"


def _setup(data_dir):
    doc = json.loads(make_units(data_dir).read_text())
    return doc, data_dir.parent / "docs", Store(data_dir, data_dir.parent / "docs")


def test_build_pages_writes_merged_not_normalized(data_dir):
    doc, docs, st = _setup(data_dir)
    u = doc["units"][0]
    before = st.path(VOL, 194).read_bytes()
    md.decide(docs, VOL, u["uid"], u["changes"][0], "good")
    r = merge_build.build_pages(st, VOL, doc, md.load(docs, VOL))
    assert r["written"] == [193, 194, 195]
    assert st.path(VOL, 194).read_bytes() == before
    out = json.loads((merge_build.merged_dir(data_dir, VOL) / "page_0194.json").read_text())
    assert out["commentary"][1]["french_commentary"] == "Un esclave prudent qui a de la sagesse ^{(a)}."
    assert json.loads((merge_build.merged_dir(data_dir, VOL) / "page_0193.json").read_text()) == \
        json.loads(st.path(VOL, 193).read_text())


def test_build_keeps_marker_and_footnote(data_dir):
    doc, docs, st = _setup(data_dir)
    u = doc["units"][0]
    u["changes"][2].update(old="la sagesse", at=20, good_raw="le savoir", good_modern="le savoir")
    md.decide(docs, VOL, u["uid"], u["changes"][2], "good")
    merge_build.build_pages(st, VOL, doc, md.load(docs, VOL), pages={194})
    out = json.loads((merge_build.merged_dir(data_dir, VOL) / "page_0194.json").read_text())
    assert out["commentary"][1]["french_commentary"] == "Un esclave qui a de le savoir ^{(a)}."
    assert out["footnotes"] == [{"marker": "(a)", "text": "Prov. 17. 2."}]


def test_build_drops_note_whose_marker_an_edit_removed(data_dir):
    doc, docs, st = _setup(data_dir)
    u = doc["units"][0]
    md.decide(docs, VOL, u["uid"], u["changes"][1], "edit", "sagesse.")  # its span runs to the field's end
    merge_build.build_pages(st, VOL, doc, md.load(docs, VOL), pages={194})
    out = json.loads((merge_build.merged_dir(data_dir, VOL) / "page_0194.json").read_text())
    assert out["commentary"][1]["french_commentary"] == "Un esclave qui a de la sagesse."
    assert out["footnotes"] == []


def test_build_reports_reopened(data_dir):
    doc, docs, st = _setup(data_dir)
    u = doc["units"][0]
    md.decide(docs, VOL, u["uid"], u["changes"][1], "good")
    u["changes"][1]["good_raw"] = "sagesses"  # good_units re-ran and read it otherwise
    r = merge_build.build_pages(st, VOL, doc, md.load(docs, VOL), pages={194})
    assert r["reopened"] == 1
    out = json.loads((merge_build.merged_dir(data_dir, VOL) / "page_0194.json").read_text())
    assert out["commentary"][1]["french_commentary"] == FIELDS[("194", T2)]


def test_apply_cli_dry_run_writes_nothing(data_dir, monkeypatch, capsys):
    import good_merge_apply
    doc, docs, st = _setup(data_dir)
    u = doc["units"][0]
    md.decide(docs, VOL, u["uid"], u["changes"][0], "good")
    monkeypatch.setattr(good_merge_apply, "DATA", data_dir)
    monkeypatch.setattr(good_merge_apply, "DOCS", docs)
    good_merge_apply.main([VOL, "--dry-run"])
    out = capsys.readouterr().out
    assert not merge_build.merged_dir(data_dir, VOL).exists()
    assert "--- normalized/page_0194.json" in out and "+++ merged/page_0194.json" in out and "prudent" in out
    good_merge_apply.main([VOL])
    assert (merge_build.merged_dir(data_dir, VOL) / "page_0194.json").exists()


def test_narrow_to_the_words_that_differ():
    f = "Un esclave qui a de la sagesse"
    assert merge_build.narrow(f, 16, 22, " de toute la") == (17, "de", "de toute")
    assert merge_build.narrow(f, 0, len(f), "Un esclave qui a la sagesse") == (17, "de", "")
    assert merge_build.narrow(f, 0, 10, "Un esclave") == (3, "esclave", "esclave")


def test_take_good_keeps_marker_before_closing_punctuation():  # I4
    assert merge_build.change_text({"good_raw": "sagese"}, "sagesse ^{(a)}.", "good", None) == "sagese ^{(a)}."


def test_unit_drop_cuts_its_fields_keep_leaves_them(data_dir):  # I3
    doc, docs, st = _setup(data_dir)
    md.decide(docs, VOL, "verse:17:4:0", None, "drop")
    md.decide(docs, VOL, "good:17:5:0", None, "keep")
    r = merge_build.build_pages(st, VOL, doc, md.load(docs, VOL))
    out = json.loads((merge_build.merged_dir(data_dir, VOL) / "page_0195.json").read_text())
    assert out["verses"][0]["french"] == ""
    assert {"uid": "good:17:5:0", "key": "unit@good:17:5:0", "why": "no place in normalized"} in r["skipped"]
    md.decide(docs, VOL, "verse:17:4:0", None, "keep")
    merge_build.build_pages(st, VOL, doc, md.load(docs, VOL), pages={195})
    out = json.loads((merge_build.merged_dir(data_dir, VOL) / "page_0195.json").read_text())
    assert out["verses"][0]["french"] == "Le méchant obéit à la langue injuste."


def test_token_span_reattaches_moved_words():
    c = {"old": "de la sagesse", "at": 10, "before": "qui a", "after": "et"}
    assert merge_build._token_span("Un homme qui a de la sagesse et", c) == (15, 28)  # moved by 5: found again
    assert merge_build._token_span("de la sagesse, qui a de la sagesse et", c) == (21, 34)  # the one in context
    assert merge_build._token_span("de la sagesse ou de la sagesse", c) is None  # two, neither in context
    assert merge_build._token_span("Ici de la sagesse", c) is None  # one, but out of its context
    assert merge_build._token_span("rien ici", c) is None


def test_token_span_insert_placed_by_its_context():
    c = {"old": "", "at": 13, "before": "ces paroles in principio", "after": "le Fils"}
    f = "par ces paroles, _in principio_, le Fils"
    c["at"] = f.index("principio") + len("principio")
    k = c["at"] + 2  # after "_," as pieces() puts it
    assert merge_build._token_span(f, c) == (k, k)  # where it was
    g = "Changé. " + f
    assert merge_build._token_span(g, c) == (k + 8, k + 8)  # moved: found again by its words
    assert merge_build._token_span("in principio, et in principio", c) is None  # two places
    assert merge_build._token_span("rien à voir ici du tout", c) is None
    assert merge_build._token_span("abc", {"old": "", "at": 1}) == (1, 1)  # no context: as stored
