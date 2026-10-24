import copy

from conftest import P193, P194
from review_store import add_commentary, add_footnote, add_verse, apply_op, delete_entry, move_entry


def verse(ch, n):
    return {"chapter": ch, "verse_number": n, "latin": "", "french": "", "annotations": None}


def test_add_verse_keeps_order_across_chapters():
    page = {"verses": [verse(17, 29), verse(17, 30), verse(18, 1)]}
    out = add_verse(page, 31)
    assert [(v["chapter"], v["verse_number"]) for v in out["verses"]] == [(17, 29), (17, 30), (17, 31), (18, 1)]
    assert page["verses"][2]["verse_number"] == 1  # input untouched


def test_add_verse_on_empty_page():
    assert add_verse({"verses": []}, 5)["verses"] == [verse(None, 5)]


def test_add_commentary_top_inherits_prev():
    out = add_commentary(P194, None, P193)
    first = out["commentary"][0]
    assert (first["chapter"], first["verse_ref"]) == (17, 1)
    assert first["latin_quote"] is None and first["french_translation"] is None
    assert first["french_commentary"] == ""
    assert [c["commentary_id"] for c in out["commentary"]] == [1, 2, 3]


def test_add_commentary_top_no_prev():
    first = add_commentary(P194, None, None)["commentary"][0]
    assert (first["chapter"], first["verse_ref"]) == (None, None)


def test_add_commentary_below():
    out = add_commentary(P194, 1, P193)
    assert len(out["commentary"]) == 3
    new = out["commentary"][2]
    assert (new["chapter"], new["verse_ref"], new["commentary_id"]) == (17, 2, 3)


def test_add_footnote_marker_forms():
    for m in ("b", "(b)", " b "):
        assert add_footnote(P194, m)["footnotes"][-1] == {"marker": "(b)", "text": ""}


def test_delete_renumbers():
    out = delete_entry(P194, "commentary", 0)
    assert [c["commentary_id"] for c in out["commentary"]] == [1]
    assert out["commentary"][0]["verse_ref"] == 2
    assert delete_entry(P194, "footnotes", 0)["footnotes"] == []


def test_move_renumbers():
    out = move_entry(P194, "commentary", 1, 0)
    assert [c["verse_ref"] for c in out["commentary"]] == [2, None]
    assert [c["commentary_id"] for c in out["commentary"]] == [1, 2]


def test_move_keep_ids():
    out = move_entry(P194, "commentary", 1, 0, renumber=False)
    assert [c["commentary_id"] for c in out["commentary"]] == [2, 1]


def test_apply_op_dispatch():
    before = copy.deepcopy(P194)
    assert apply_op(P194, {"op": "add_commentary", "after": None}, P193)["commentary"][0]["verse_ref"] == 1
    assert apply_op(P194, {"op": "add_footnote", "marker": "c"}, None)["footnotes"][-1]["marker"] == "(c)"
    assert apply_op(P194, {"op": "delete", "section": "footnotes", "index": 0}, None)["footnotes"] == []
    assert apply_op(P194, {"op": "move", "section": "commentary", "from": 1, "to": 0}, None)["commentary"][0]["verse_ref"] == 2
    assert apply_op({"verses": []}, {"op": "add_verse", "n": 3}, None)["verses"][0]["verse_number"] == 3
    assert P194 == before
