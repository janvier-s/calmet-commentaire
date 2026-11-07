"""The Good_Calmet page mapping: stray matches (good_calmet_match.bracket_strays) and passages the edition
moved (good_calmet_kraken.moved, good_notes.good_order)."""
import good_calmet_match as gm


def row(page, src, ooo=False, pdf="01_Genèse_1-2"):
    r = {"pdf": pdf, "pdf_page": page, "type": "commentary"}
    if src:
        r.update(source=f"page_{src:04d}", sim=0.5)
    if ooo:
        r["out_of_order"] = True
    return r


def test_stray_takes_the_sources_around_it():
    # Good 284 (an added passage on Gen 2:2) matched source 103 weakly, between 136 and 137
    rows = [row(280, 135), row(282, 136), row(283, None), row(284, 103, True), row(285, 137)]
    changed = gm.bracket_strays(rows)
    assert [r["pdf_page"] for r in changed] == [284]
    r = rows[3]
    assert (r["source"], r["also"], r["stray"]["source"]) == ("page_0136", "page_0137", "page_0103")
    assert "out_of_order" not in r


def test_a_run_out_of_order_is_a_moved_passage_kept():
    rows = [row(136, 360), row(137, 361), row(138, 380, True), row(139, 381, True), row(140, 381, True),
            row(147, 362)]
    assert gm.bracket_strays(rows) == []
    assert rows[2]["source"] == "page_0380"


def test_a_near_jitter_is_kept():
    rows = [row(254, 597), row(255, 598), row(256, 600, True), row(257, 598), row(258, 600)]
    assert gm.bracket_strays(rows) == []


def test_good_order_puts_a_moved_passage_after_its_good_page():
    import good_notes as gn
    recs = [{"source": "page_0102", "moved": ["page_0105", "page_0106"]}, {"source": "page_0104"}]
    assert gn.good_order(list(range(101, 109)), recs) == [101, 102, 105, 106, 103, 104, 107, 108]
    # a moved page outside the chapter is left out; nothing moved: the pages as they are
    assert gn.good_order([102, 103], recs) == [102, 103]
    assert gn.good_order([1, 2, 3], [{"source": "page_0002"}]) == [1, 2, 3]


def test_sources_and_moved_file(tmp_path, monkeypatch):
    import json
    import good_calmet_kraken as gk
    (tmp_path / "crops.json").write_text(json.dumps({
        "P/page_0159": {"pdf": "P", "pdf_page": 159, "source": "page_0102"},
        "P/page_0160": {"pdf": "P", "pdf_page": 160, "source": "page_0104"}}))
    (tmp_path / "moved.json").write_text(json.dumps({"_doc": "x", "P/page_0159": {"moved": ["page_0105"], "why": "y"}}))
    monkeypatch.setattr(gk, "GOOD", tmp_path)
    recs = {r["pdf_page"]: r for r in gk.crops()}
    assert gk.sources(recs[159]) == [102, 105] and gk.sources(recs[160]) == [104]
    assert "moved" not in recs[160]


def test_editor_shows_a_good_page_on_its_moved_pages(tmp_path):
    import json
    import review_store
    g = tmp_path / "good_calmet"
    (g / "P").mkdir(parents=True)
    (g / "P" / "page_0159.png").write_bytes(b"")
    (g / "crops.json").write_text(json.dumps({"P/page_0159": {"pdf": "P", "pdf_page": 159, "source": "page_0102"}}))
    (g / "moved.json").write_text(json.dumps({"P/page_0159": {"moved": ["page_0105"]}}))
    st = review_store.Store.__new__(review_store.Store)
    st.data = tmp_path
    assert [p.name for p in st.good_pages("01_genese", 105)] == ["page_0159.png"]
    assert [p.name for p in st.good_pages("01_genese", 102)] == ["page_0159.png"]
    assert st.good_pages("01_genese", 104) == []
