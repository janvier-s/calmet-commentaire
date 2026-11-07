import json

import good_clean
import good_normalized as gn


def test_clean_uses_normalizeds_rules_and_leaves_latin_in_italics():
    out, recs = good_clean.clean_records("le long-temps et c. ici Israëlites _in principio erat_ très-dure,")
    assert out == "le longtemps etc. ici Israélites _in principio erat_ très dure,"
    assert ("très-dure,", "très dure,") in {(r["before"], r["after"]) for r in recs}
    assert any("longtemps etc." in r["after"] for r in recs)
    assert all(r["rule"] for r in recs)


def test_records_rebuild_the_text_and_undo_puts_a_word_back():
    text = "Israëlites et long-temps ici"
    out, recs = good_clean.clean_records(text)
    assert good_clean.apply_records(text, recs) == out
    k = next(k for k, r in enumerate(recs) if r["before"] == "long-temps")
    assert good_clean.apply_records(text, recs, {k}) == "Israélites et long-temps ici"


def test_remap_flags_follows_the_changed_text():
    flags = [{"a": 12, "b": 15, "why": "stop_lower"}]
    a, b = "Israëlites et ici", "Israélites et ici"
    assert good_clean.remap_flags(flags, a, b)[0]["a"] == 12


def _doc(text="Israëlites"):
    return {"units": [{"uid": "u", "changes": [{"id": "c1", "good_punct": text, "good_flags": []}]}]}


def test_overlay_cleans_lists_records_and_honours_undo():
    doc = _doc()
    st = gn.compute(doc)
    assert st["changes"]["c1"]["records"][0]["after"] == "Israélites"
    gn.overlay(doc, st, {})
    c = doc["units"][0]["changes"][0]
    assert c["good_normalized"] == "Israélites" and c["good_records"][0]["undone"] is False
    gn.overlay(doc, st, {"c1": [gn.key(c["good_records"][0])]})
    c = doc["units"][0]["changes"][0]
    assert "good_normalized" not in c and c["good_records"][0]["undone"] is True


def test_overlay_ignores_a_store_whose_source_text_moved_on():
    st = gn.compute(_doc())
    doc = _doc("Israëlites autres")
    gn.overlay(doc, st, {})
    assert "good_normalized" not in doc["units"][0]["changes"][0]


def test_agent_records_are_located_by_their_words_and_survive_a_recompute():
    doc = _doc("As commencement Dieu")
    st = {"changes": {"c1": {"src": gn.src_hash("As commencement Dieu"), "records": []}}}
    st["changes"]["c1"]["agent"] = [{"before": "As", "after": "Au", "ctx": "", "rule": "agent"}]
    st2 = gn.compute(doc, st["changes"])
    gn.overlay(doc, st2, {})
    assert doc["units"][0]["changes"][0]["good_normalized"] == "Au commencement Dieu"


def test_undo_store_round_trips(tmp_path):
    assert gn.save_undo(tmp_path, "v", "c1", "a => b") == ["a => b"]
    assert gn.save_undo(tmp_path, "v", "c1", "a => b", undo=False) == []
    assert json.loads(gn.undone_path(tmp_path, "v").read_text())["undone"] == {}
