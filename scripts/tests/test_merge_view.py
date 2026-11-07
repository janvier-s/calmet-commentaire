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


def test_rows(data_dir):
    make_units(data_dir)
    st = Store(data_dir, data_dir.parent / "docs")
    r = merge_view.rows(merge_view.load(data_dir, "22_proverbes"), st)
    assert [x["uid"] for x in r] == ["commentary:17:2:0", "verse:17:4:0", "good:17:5:0", "commentary:17:3:0"]
    assert r[0]["n"] == 3 and r[0]["stale"] is False and r[0]["lemma"].startswith("SERVUS")
    assert r[3]["first"] == "Texte pareil." and r[2]["after"] == "verse:17:4:0"


def test_stale_after_hand_fix(data_dir):
    make_units(data_dir)
    st = Store(data_dir, data_dir.parent / "docs")
    p = st.path("22_proverbes", 194); d = json.loads(p.read_text())
    d["commentary"][1]["french_commentary"] = "Un esclave sage qui a de la sagesse ^{(a)}."
    p.write_text(json.dumps(d))
    doc = merge_view.load(data_dir, "22_proverbes")
    assert merge_view.rows(doc, st)[0]["stale"] is True
    assert merge_view.unit_view(doc, "commentary:17:2:0", st)["stale"] is True


def test_reload_on_rewrite(data_dir):
    path = make_units(data_dir)
    assert len(merge_view.load(data_dir, "22_proverbes")["units"]) == 4
    doc = json.loads(path.read_text()); doc["units"] = doc["units"][:1]
    path.write_text(json.dumps(doc))
    assert len(merge_view.load(data_dir, "22_proverbes")["units"]) == 1


def test_vols_and_notes(data_dir):
    make_units(data_dir)
    assert merge_view.merge_vols(data_dir) == ["22_proverbes"]
    assert merge_view.load(data_dir, "01_nothing") is None
    assert "interleaved" in merge_view.notes("01_genese")["only_old"]


def test_seams_mark_page_turns(data_dir):
    st = Store(data_dir, data_dir.parent / "docs")
    parts = [{"page": 193, "path": "commentary/0/french_commentary"},
             {"page": 194, "path": "commentary/0/french_commentary"}]
    old = good_units._text("Il vaut mieux vivre en paix\nque la maison pleine de victimes. suite du commentaire.")
    doc = {"vol": "22_proverbes", "units": [{"uid": "commentary:17:1:0", "type": "commentary", "status": "identical", "parts": parts,
                      "old": old, "good": old, "changes": []}]}
    v = merge_view.unit_view(doc, "commentary:17:1:0", st)
    assert v["stale"] is False and v["seams"] == [{"page": 194, "at": old.index("suite")}]
    seam = [k for k, s in enumerate(v["old"]) if s["kind"] == "seam"]
    assert len(seam) == 1 and v["old"][seam[0]]["page"] == 194
    assert v["old"][seam[0] + 1]["t"].lstrip().startswith("suite")
    assert "".join(s["t"] for s in v["old"]) == old


def test_scan_boxes_no_scan(data_dir):
    st = Store(data_dir, data_dir.parent / "docs")
    assert merge_view.scan_boxes(st, "22_proverbes", 193, "commentary/0/french_commentary", 0, 2) == {"boxes": [], "reason": "no scan"}


def test_scan_boxes_never_runs_kraken(data_dir, monkeypatch):
    st = Store(data_dir, data_dir.parent / "docs")
    seen = []
    monkeypatch.setattr(merge_view.scan_ocr, "ocr", lambda vol, page, run=True, scan=None: seen.append(run))
    assert merge_view.scan_boxes(st, "22_proverbes", 194, "commentary/1/french_commentary", 0, 2)["reason"] == "no cached OCR"
    assert seen == [False]


def test_scan_boxes_found(data_dir, monkeypatch):
    st = Store(data_dir, data_dir.parent / "docs")
    monkeypatch.setattr(merge_view.scan_ocr, "ocr", lambda *a, **k: {"fake": 1})
    words = [{"t": "Un", "boxes": [[1, 1, 2, 2]], "path": "commentary/1/french_commentary", "a": 0, "b": 2},
             {"t": "esclave", "boxes": [[4, 1, 6, 2]], "path": "commentary/1/french_commentary", "a": 3, "b": 10},
             {"t": "qui", "boxes": [[11, 1, 3, 2]], "path": "commentary/1/french_commentary", "a": 11, "b": 14}]
    monkeypatch.setattr(merge_view.scan_ocr, "align", lambda o, d, fix=False: {"size": [100, 200], "words": words})
    assert merge_view.scan_boxes(st, "22_proverbes", 194, "commentary/1/french_commentary", 3, 2) == {
        "boxes": [[4, 1, 6, 2], [11, 1, 3, 2]], "size": [100, 200], "crop": None}


def test_scan_boxes_carry_the_margin_crop(data_dir, monkeypatch):
    """/scan/ serves the margin crop when there is one; the boxes stay in the scan's pixels, so the crop's
    place in the scan comes with them."""
    st = Store(data_dir, data_dir.parent / "docs")
    monkeypatch.setattr(merge_view.scan_ocr, "ocr", lambda *a, **k: {"fake": 1})
    words = [{"t": "Un", "boxes": [[50, 60, 2, 2]], "path": "commentary/1/french_commentary", "a": 0, "b": 2}]
    monkeypatch.setattr(merge_view.scan_ocr, "align", lambda o, d, fix=False: {"size": [100, 200], "words": words})
    monkeypatch.setattr(st, "scan_crop", lambda vol, page: ("crop.png", [10, 20, 90, 180]))
    assert merge_view.scan_boxes(st, "22_proverbes", 194, "commentary/1/french_commentary", 0, 1)["crop"] == [10, 20, 90, 180]
    monkeypatch.setattr(st, "scan_crop", lambda vol, page: (None, None))
    assert merge_view.scan_boxes(st, "22_proverbes", 194, "commentary/1/french_commentary", 0, 1)["crop"] is None


def test_segments_pair_up_across_columns(data_dir):
    """Each old segment and the Good segment(s) it stands against share `k`, so the browser can cut both
    columns into rows at the same places; a seam takes the k of the text after it."""
    v = view(data_dir, "commentary:17:2:0")
    ks = [s["k"] for s in v["good"]]
    assert ks == list(range(len(ks))) and [s["k"] for s in v["good_printed"]] == ks
    assert sorted({s["k"] for s in v["old"]}) == ks
    by_k = {s["k"]: s for s in v["good"] if s["kind"] == "change"}
    assert {s["k"]: s["id"] for s in v["old"] if s["kind"] == "change"} == {k: s["id"] for k, s in by_k.items()}


def test_good_position_of_placed_changes(data_dir):
    """A placed change knows its Good word index (a cut's Good crop is drawn around it); unplaced ones don't."""
    v = view(data_dir, "commentary:17:2:0")
    at = {c["key"]: c["good_at"] for c in v["changes"]}
    assert at == {"c1": 13, "c2": 18, "c3": None}
    assert v["good_tokens"] == 19


def test_overlapping_and_crossing_changes_go_unplaced(data_dir):
    """A change whose span overlaps one already placed, or whose Good order crosses the old order, is listed in
    `unplaced`, never drawn: the columns would no longer reassemble."""
    doc = json.loads(make_units(data_dir).read_text())
    doc["units"][0]["changes"] += [
        _change(id="c5", kind="replace", old="de la sagesse", good_raw="de la sagese", good_modern="de la sagese",
                before="qui a", after="", good_before="qui a", good_after="", at=40),       # overlaps c2
        _change(id="c6", kind="replace", old="serviteur", good_raw="qui", good_modern="qui", before="STULTIS Le",
                after="sage dominera", good_before="esclave prudent", good_after="a de la", at=41),  # crosses c1
    ]
    v = merge_view.unit_view(doc, "commentary:17:2:0")
    assert v["unplaced"] == ["c3", "c5", "c6"]
    assert "".join(s["t"] for s in v["old"]) == doc["units"][0]["old"]
    assert "".join(s["t"] for s in v["good_printed"]).split() == doc["units"][0]["good"].split()
