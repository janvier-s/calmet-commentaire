"""good_links.py (the hand links' file) and good_notes.pair_linked (pairing that keeps them)."""
import good_links as gl
import good_notes as gn


def note(text, mark, page, pdf=None, n=0, index=0):
    """A note as compare() builds it: a Good one when `pdf` is given, else a normalized one."""
    d = {"text": text, "mark": mark, "nums": gn.numbers(text), "aw": gn.abbr_words(text), "script": gn.script(text)}
    if pdf:
        return dict(d, pdf=pdf, page=n + 10, n=n, src_page=page, words=[], junk=0.0)
    return dict(d, page=page, index=index, marker=mark)


GOODS = [note("Aug. de Genes. ad litt. l. 11. c. 39.", "(a)", 5, "P", 0),
         note("Hieron. quaest. Hebr. in Genes. c. 31.", "(b)", 5, "P", 1),
         note("Joseph. antiq. l. 1. c. 19.", "(c)", 5, "P", 2)]
JSONS = [note("Saint Augustin, De la Genèse à la lettre, livre 11, chapitre 39.", "(a)", 5, index=0),
         note("Saint Jérôme, Questions hébraïques sur la Genèse, chapitre 31.", "(b)", 5, index=1),
         note("Josèphe, Antiquités, livre 1, chapitre 19.", "(c)", 5, index=2)]


def plain_pairs(pairs):
    return {(g, j) for g, j, _ in pairs}


def test_load_missing_and_round_trip(tmp_path):
    assert gl.load("01_genese", tmp_path) == []
    links, e = gl.link([], [GOODS[0]], [JSONS[0]], by="test")
    assert e["kind"] == "same" and e["good"] == {"pdf": "P", "pdf_page": 10, "mark": "(a)", "n": 0}
    assert e["json"] == {"page": 5, "marker": "(a)", "index": 0}
    gl.save("01_genese", links, tmp_path)
    assert gl.load("01_genese", tmp_path) == links
    assert (tmp_path / "good_notes_links" / "01_genese.json").exists()


def test_link_kinds_and_replacing():
    links, e = gl.link([], [GOODS[0]], [JSONS[0], JSONS[1]])
    assert e["kind"] == "merged" and len(e["json"]) == 2
    links, e = gl.link(links, [GOODS[1], GOODS[2]], [JSONS[2]])
    assert e["kind"] == "split"
    links, e = gl.link(links, [], [JSONS[1]])  # J1 had no counterpart after all: the merge goes
    assert e["kind"] == "none" and e["good"] is None and len(links) == 2
    assert gl.unlink(links, jsons=[JSONS[2]]) == [links[1]]


def test_resolve_by_index_then_marker():
    links = [{"json": {"page": 5, "marker": "(c)", "index": 2}, "good": {"pdf": "P", "pdf_page": 12, "mark": "(c)", "n": 2},
              "kind": "same"}]
    fixed, stale = gl.resolve(links, GOODS, JSONS)
    assert [(g, j) for g, j, _ in fixed] == [((2,), (2,))] and not stale
    # a note inserted before it: the index moved, the marker finds it
    moved = [JSONS[0], dict(JSONS[1], index=1), dict(JSONS[2], index=3)]
    fixed, _ = gl.resolve(links, GOODS, moved)
    assert [(g, j) for g, j, _ in fixed] == [((2,), (2,))]
    # its Good note gone: stale, not applied
    fixed, stale = gl.resolve(links, GOODS[:2], JSONS)
    assert not fixed and stale == links


def test_no_links_is_the_plain_pairing():
    pairs, sim, linked = gn.pair_linked(GOODS, JSONS)
    plain, _ = gn.pair(GOODS, JSONS)
    assert plain_pairs(pairs) == plain_pairs(gn.rescue(plain, sim, GOODS, JSONS)) and not linked


def test_pinned_pair_fills_in_around_it():
    pairs, _, linked = gn.pair_linked(GOODS, JSONS, [((1,), (1,))])
    assert linked == {(1, 1)}
    assert {(0, 0), (1, 1), (2, 2)} <= plain_pairs(pairs)
    # a pin against the likeness holds, and nothing else takes its notes
    pairs, _, linked = gn.pair_linked(GOODS, JSONS, [((0,), (2,))])
    assert (0, 2) in linked
    assert all(not ((g == 0 and j != 2) or (j == 2 and g != 0)) for g, j in plain_pairs(pairs))


def test_none_stays_single():
    pairs, _, linked = gn.pair_linked(GOODS, JSONS, [((1,), ())])
    assert (1, None) in linked
    assert [p for p in plain_pairs(pairs) if p[0] == 1] == [(1, None)]
    assert (0, 0) in plain_pairs(pairs) and (2, 2) in plain_pairs(pairs)


def test_merge_link():
    pairs, _, linked = gn.pair_linked(GOODS, JSONS, [((0,), (0, 1))])
    assert (0, (0, 1)) in linked and (2, 2) in plain_pairs(pairs)
    j = gn.pick(JSONS, (0, 1), False)
    assert [x["index"] for x in j["parts"]] == [0, 1] and "Jérôme" in j["text"]


def test_compare_reports_linked(monkeypatch):
    """compare() marks the pairs the links made, and records the notes of each difference."""
    import good_variants as gv
    monkeypatch.setattr(gv, "chapter_pages", lambda vol, chs: [5])
    monkeypatch.setattr(gv, "lexicon", lambda: set())
    monkeypatch.setattr(gv, "norm", lambda vol, p: {"footnotes": [{"marker": j["mark"], "text": j["text"]} for j in JSONS]})
    monkeypatch.setattr(gv, "printed_page", lambda pdf, page: page)
    monkeypatch.setattr(gn.gk, "crops", lambda: [{"vol": "v", "source": "page_0005", "pdf": "P", "pdf_page": 10}])
    monkeypatch.setattr(gn.gk, "cache_path", lambda pdf, page: type("F", (), {"exists": lambda self: True})())
    monkeypatch.setattr(gn, "agy_notes", lambda pdf, page, o=None: [dict(g, agy=True) for g in GOODS] if pdf == "P" else None)
    monkeypatch.setattr(gn.scan_ocr, "ocr", lambda vol, p, run=False: None)
    links = [{"good": {"pdf": "P", "pdf_page": 11, "mark": "(b)", "n": 1}, "json": None, "kind": "none"}]
    out, _ = gn.compare("v", {1}, links)
    added = [r for r in out if r["kind"] == "note_added"]
    assert len(added) == 1 and added[0]["linked"] and added[0]["notes"]["good"][0]["mark"] == "(b)"
    dropped = [r for r in out if r["kind"] == "note_dropped"]
    assert [r["notes"]["json"][0]["index"] for r in dropped] == [1] and not dropped[0].get("linked")
