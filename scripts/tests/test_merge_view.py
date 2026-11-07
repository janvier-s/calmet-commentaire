import json

import good_units
import merge_view
from review_store import Store

P194_PARTS = [{"page": 194, "path": f"commentary/1/{f}"}
              for f in ("latin_quote", "french_translation", "french_commentary")]
OLD_17_2 = good_units._text(" ".join(["SERVUS SAPIENS DOMINABITUR FILIIS STULTIS.",
                                       "Le serviteur sage dominera les enfants insensés.",
                                       "Un esclave qui a de la sagesse ^{(a)}."]))
GOOD_17_2 = ("SERVUS SAPIENS DOMINABITUR FILIIS STULTIS Le serviteur dominera les enfants insenses "
             "Un esclave prudent qui a de la sagese")


def _change(**kw):
    c = {"id": "c1", "kind": "insert", "class": "substantive", "origin": "only_good", "vol": "22_proverbes",
         "page": 194, "path": "commentary/1/french_commentary", "at": 11, "old": "", "good_raw": "prudent",
         "good_modern": "prudent", "words": 1, "old_words": 0, "pieces": 1, "before": "Un esclave",
         "after": "qui a de la", "good_before": "Un esclave", "good_after": "qui a de",
         "good": [{"pdf": "X", "pdf_page": 9, "boxes": [[5, 6, 7, 8]]}], "gap_in_normalized": False,
         "moved_with": None}
    c.update(kw)
    return c


def make_units(data_dir):
    """data/22_proverbes/good_units.json over conftest's data_dir; returns its path."""
    units = [
        {"uid": "commentary:17:2:0", "type": "commentary", "chapter": 17, "verse": "2",
         "lemma": "SERVUS SAPIENS DOMINABITUR FILIIS STULTIS.", "parts": P194_PARTS, "notes": [],
         "status": "substantive", "old": OLD_17_2, "good": GOOD_17_2, "good_words": 19,
         "good_where": [{"pdf": "X", "pdf_page": 9, "printed": None, "crop": "x.png", "boxes": [[1, 2, 3, 4]]}],
         "changes": [
             _change(),
             _change(id="c2", **{"class": "cosmetic"}, kind="replace", old="sagesse", good_raw="sagese",
                     good_modern="sagese", before="qui a de la", after="", good_before="qui a de la",
                     good_after="", at=26, words=1, old_words=1),
             _change(id="c3", kind="replace", old="nowhere words", good_raw="ailleurs", good_modern="ailleurs",
                     before="zzz", after="yyy", good_before="zzz", good_after="yyy", at=30),
         ]},
        {"uid": "verse:17:4:0", "type": "verse", "chapter": 17, "verse": "4", "lemma": None,
         "parts": [{"page": 195, "path": "verses/0/french"}], "notes": [], "status": "only_old",
         "old": "Le méchant obéit à la langue injuste.", "good": "", "good_words": 0, "good_where": [],
         "changes": []},
        {"uid": "good:17:5:0", "type": "commentary", "chapter": 17, "verse": "5", "lemma": None, "parts": [],
         "notes": [], "after": "verse:17:4:0", "status": "only_good", "old": "",
         "good": "Y 5 QUI DESPICIT PAUPEREM", "good_words": 5,
         "good_where": [{"pdf": "X", "pdf_page": 10, "printed": None, "crop": "y.png", "boxes": []}],
         "changes": []},
        {"uid": "commentary:17:3:0", "type": "commentary", "chapter": 17, "verse": "3", "lemma": None,
         "parts": [], "notes": [], "status": "identical", "old": "Texte pareil.", "good": "Texte pareil",
         "good_words": 2, "good_where": [], "changes": []},
    ]
    doc = {"vol": "22_proverbes", "chapters": [17], "unattached": {"16,17": 1},
           "summary": {"substantive": 1, "only_old": 1, "only_good": 1, "identical": 1, "unattached": 1},
           "units": units}
    path = data_dir / "22_proverbes" / "good_units.json"
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return path


def view(data_dir, uid):
    doc = json.loads((make_units(data_dir)).read_text())
    return merge_view.unit_view(doc, uid)


def test_columns_reassemble(data_dir):
    v = view(data_dir, "commentary:17:2:0")
    doc = json.loads((data_dir / "22_proverbes" / "good_units.json").read_text())
    assert "".join(s["t"] for s in v["old"]) == doc["units"][0]["old"]
    assert "".join(s["t"] for s in v["good_printed"]).split() == doc["units"][0]["good"].split()


def test_changes_placed_both_sides(data_dir):
    v = view(data_dir, "commentary:17:2:0")
    ch = {s["id"]: s for s in v["good"] if s["kind"] == "change"}
    assert ch["c1"]["t"].strip() == "prudent" and ch["c1"]["cls"] == "substantive"
    assert [s for s in v["old"] if s.get("id") == "c1"][0]["t"] == ""        # insert: empty on old side
    assert ch["c2"]["t"].strip() == "sagese"                                  # highlight shows the record, not old's punctuation
    assert v["unplaced"] == ["c3"]
    assert {c["id"]: c["placed"] for c in v["changes"]} == {"c1": True, "c2": True, "c3": False}


def test_unrecorded_difference(data_dir):
    v = view(data_dir, "commentary:17:2:0")
    un = [s for s in v["old"] if s["kind"] == "unrecorded"]
    assert [s["t"].strip() for s in un] == ["sage"]
    assert v["counts"]["unrecorded"] == 1


def test_punctuation_carried_outside_changes(data_dir):
    v = view(data_dir, "commentary:17:2:0")
    good = "".join(s["t"] for s in v["good"])
    assert "STULTIS. Le serviteur" in good and "insensés. Un esclave" in good
    assert "insenses" not in good                                             # agreeing run shows old's surface
    assert "insenses" in "".join(s["t"] for s in v["good_printed"])          # as printed keeps Kraken's


def test_one_side_empty(data_dir):
    a = view(data_dir, "verse:17:4:0")
    assert a["good"] == [] and a["empty"]["good"] == "Good has no text paired here"
    b = view(data_dir, "good:17:5:0")
    assert b["old"] == [] and b["empty"]["old"] == "Good-only text; follows verse:17:4:0"
    assert view(data_dir, "nope") is None


def test_duplicate_ids_kept_apart(data_dir):
    """good_variants' ids hash the words, not the place: the same change twice in a unit shares an id."""
    doc = json.loads(make_units(data_dir).read_text())
    doc["units"][0]["changes"].append(_change(
        id="c2", kind="only_normalized", old="sage", good_raw="", good_modern=None, before="Le serviteur",
        after="dominera les enfants", path="commentary/1/french_translation", at=13, words=0, old_words=1,
        good_before=None, good_after=None))
    for k in ("good_before", "good_after"):
        del doc["units"][0]["changes"][-1][k]
    v = merge_view.unit_view(doc, "commentary:17:2:0")
    assert sorted(c["key"] for c in v["changes"] if c["placed"]) == ["c1", "c2", "c2~2"]
    assert [s["id"] for s in v["old"] if s["kind"] == "change"] == ["c2~2", "c1", "c2"]
    assert v["counts"]["substantive"] == 2 and v["counts"]["cosmetic"] == 1 and v["counts"]["unrecorded"] == 0
