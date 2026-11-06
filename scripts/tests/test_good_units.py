"""good_units.py: the units both editions are compared by, Good's text on them, their changes and status."""
import good_units as gu


def page(commentary=(), verses=(), footnotes=(), **head):
    d = {"book_title": None, "chapter_title": None, "chapter_summary": None, "chapter_intro": None,
         "chapter_number": None, "verses": list(verses), "commentary": list(commentary), "footnotes": list(footnotes)}
    d.update(head)
    return d


def note(ch, v, fc, lq=None, ft=None):
    return {"chapter": ch, "verse_ref": v, "latin_quote": lq, "french_translation": ft, "french_commentary": fc}


def verse(ch, n, fr):
    return {"chapter": ch, "verse_number": n, "latin": "Lat.", "french": fr, "annotations": None}


def test_continuation_joins_across_pages():
    data = {10: page([note(1, 1, "Il a créé le monde", lq="In principio")]),
            11: page([note(1, None, "est créé.")])}
    units = [u for u in gu.old_units(data) if u["type"] == "commentary"]
    assert len(units) == 1
    u = units[0]
    assert len(u["parts"]) == 3
    assert {p["page"] for p in u["parts"]} == {10, 11}
    assert u["old"].endswith("le monde est créé.")
    assert u["lemma"] == "In principio"


def test_two_lemmas_same_verse():
    data = {5: page([note(1, 3, "Premier.", lq="DIXIT"), note(1, 3, "Second.", lq="FIAT LUX")])}
    uids = [u["uid"] for u in gu.old_units(data) if u["type"] == "commentary"]
    assert uids == ["commentary:1:3:0", "commentary:1:3:1"]


def test_notes_before_chapter_title_keep_chapter():
    data = {7: page([note(3, 24, "Fin du chapitre.", lq="ET COLLOCAVIT"), note(4, 1, "Début.", lq="ADAM VERO")],
                    verses=[verse(4, 1, "Adam connut Ève.")], chapter_title="CHAPITRE IV.", chapter_number=4)}
    units = {u["uid"]: u for u in gu.old_units(data)}
    assert units["commentary:3:24:0"]["chapter"] == 3
    assert units["commentary:4:1:0"]["chapter"] == 4
    assert units["title:4:None:0"]["chapter"] == 4


def test_verse_latin_excluded():
    data = {7: page(verses=[verse(4, 1, "Adam connut Ève."), verse(4, 2, "Elle enfanta.")])}
    units = gu.old_units(data)
    assert [u["uid"] for u in units] == ["verse:4:1:0", "verse:4:2:0"]
    assert all(not p["path"].endswith(("/latin", "/annotations")) for u in units for p in u["parts"])
    assert units[0]["parts"] == [{"page": 7, "path": "verses/0/french"}]


def test_notes_follow_marker():
    data = {8: page([note(2, 2, "Il se reposa^{(a)} le septième jour.", lq="REQUIEVIT")],
                    footnotes=[{"marker": "(a)", "text": "Hébreux 4:4."}, {"marker": "(b)", "text": "Autre."}])}
    u = gu.old_units(data)[0]
    assert u["notes"] == [{"page": 8, "path": "footnotes/0"}]
    assert "^{" not in u["old"] and "(a)" not in u["old"]


def test_heads_and_index():
    data = {3: page(chapter_intro="Argument du chapitre.", chapter_summary="Création.", chapter_number=1)}
    units = gu.old_units(data)
    assert [(u["type"], u["chapter"]) for u in units] == [("summary", 1), ("intro", 1)]
    idx = gu.unit_index(units)
    assert idx[(3, "chapter_intro")] == "intro:1:None:0"
    assert gu.type_of("commentary/2/french_commentary") == "commentary"
    assert gu.type_of("verses/0/french") == "verse"
    assert gu.type_of("chapter_argument") == "summary"


def test_uids_unique_when_verse_ref_types_mix():
    data = {5: page([note(3, 14, "Un.", lq="AIT"), note(3, "14", "Deux.", lq="SUPER PECTUS")])}
    uids = [u["uid"] for u in gu.old_units(data)]
    assert uids == ["commentary:3:14:0", "commentary:3:14:1"]


# Good's side: a hand-made alignment of two notes on page 5 (A: commentary/0, B: commentary/1)
A, B = "commentary/0/french_commentary", "commentary/1/french_commentary"


def units_ab():
    return gu.old_units({5: page([note(1, 6, "alpha beta gamma", lq="FIAT"), note(1, 8, "delta epsilon", lq="VIDIT")])})


def ctx_of(words):
    """words: (text, path or None, s) in Good's order; a path links the word to a JSON word of that field."""
    jt, stream = [], []
    for t, path, s in words:
        j = None
        if path:
            j = len(jt)
            jt.append({"t": t, "k": t.lower(), "page": 5, "path": path, "a": 0, "b": len(t)})
        stream.append({"t": t, "k": t.lower(), "s": s or ("match" if path else "gap"), "j": j, "pdf": "P",
                       "pdf_page": 9, "printed": 12, "boxes": [[0, 0, 1, 1]], "wc": 0.9})
    return {"jt": jt, "stream": stream}


def good_of(units, uid):
    return next(u for u in units if u["uid"] == uid)["good"]


def test_match_words_go_to_their_unit():
    units = units_ab()
    gu.project(units, ctx_of([("alpha", A, None), ("gamma", A, None), ("delta", B, None)]))
    assert good_of(units, "commentary:1:6:0") == "alpha gamma"
    assert good_of(units, "commentary:1:8:0") == "delta"
    u = units[0]
    assert u["good_words"] == 2
    assert u["good_where"] == [{"pdf": "P", "pdf_page": 9, "printed": 12, "crop": "data/good_calmet/P/page_0009.png",
                                "boxes": [[0, 0, 1, 1], [0, 0, 1, 1]]}]


def test_gap_inside_unit_stays():
    units = units_ab()
    gu.project(units, ctx_of([("alpha", A, None), ("nouveau", None, None), ("gamma", A, None), ("delta", B, None)]))
    assert good_of(units, "commentary:1:6:0") == "alpha nouveau gamma"


def test_gap_between_units_goes_to_earlier():
    units = units_ab()
    gu.project(units, ctx_of([("alpha", A, None), ("ajout", None, None), ("delta", B, None)]))
    assert good_of(units, "commentary:1:6:0") == "alpha ajout"
    assert good_of(units, "commentary:1:8:0") == "delta"


def test_lemma_start_makes_good_only_unit():
    units = units_ab()
    new = gu.project(units, ctx_of([("alpha", A, None), ("fin", None, None), ("ŷ.", None, None), ("7.", None, None),
                                    ("ET", None, None), ("DIXIT", None, None), ("DEUS", None, None),
                                    ("texte", None, None), ("delta", B, None)]))
    assert good_of(units, "commentary:1:6:0") == "alpha fin"
    assert len(new) == 1
    n = new[0]
    assert n["uid"] == "good:1:7:0"
    assert n["good"].startswith("ŷ. 7. ET DIXIT")
    assert (n["type"], n["chapter"], n["verse"], n["parts"], n["old"], n["after"]) == \
        ("commentary", 1, 7, [], "", "commentary:1:6:0")


def test_skip_words_ignored():
    units = units_ab()
    gu.project(units, ctx_of([("alpha", A, None), ("(b)", None, "skip"), ("gamma", A, None), ("delta", B, None)]))
    assert all("(b)" not in u["good"] for u in units)


def test_words_linked_outside_units_dropped():
    units = units_ab()
    gu.project(units, ctx_of([("alpha", A, None), ("Hebr.", "footnotes/0/text", None), ("Lux", "verses/0/latin", None),
                              ("gamma", A, None), ("delta", B, None)]))
    assert good_of(units, "commentary:1:6:0") == "alpha gamma"


def rec(**kw):
    r = {"id": "x", "kind": "insert", "origin": "only_good", "page": 5, "path": A, "old": "", "good_raw": "",
         "good_modern": "", "words": 0, "old_words": 0, "confidence": "high", "good": []}
    r.update(kw)
    return r


def test_classify_rules():
    assert gu.classify(rec(confidence="low", words=5)) == "noise"
    assert gu.classify(rec(split=True, words=1)) == "noise"
    assert gu.classify(rec(kind="moved", words=12)) == "moved"
    assert gu.classify(rec(kind="replace", old="vos", good_raw="vous", good_modern="vous", words=1, old_words=1)) == "cosmetic"
    long_old = "les anciens Juifs croyaient que le serpent avait des pieds"
    assert gu.classify(rec(kind="replace", old=long_old, good_modern=long_old + "s", good_raw=long_old + "s",
                           words=10, old_words=10)) == "cosmetic"
    new = "Philon dit que ce livre fut écrit par Adam lui-même avant le déluge"
    assert gu.classify(rec(kind="insert", good_raw=new, good_modern=new, words=12)) == "substantive"


def test_status_order():
    u = units_ab()[0]
    u.update(good="alpha", good_words=1, changes=[dict(rec(), **{"class": "noise"}), dict(rec(), **{"class": "cosmetic"})])
    assert gu.status(u, {5}) == "cosmetic"
    u["changes"].append(dict(rec(), **{"class": "substantive"}))
    assert gu.status(u, {5}) == "substantive"
    u["changes"] = []
    assert gu.status(u, {5}) == "identical"


def test_uncovered_not_only_old():
    u = units_ab()[0]
    u.update(good="", good_words=0, changes=[])
    assert gu.status(u, {9}) == "uncovered"
    assert gu.status(u, {5}) == "only_old"


def test_partial_cover_is_paired():
    data = {10: page([note(1, 1, "Il a créé le monde", lq="In principio")]), 11: page([note(1, None, "est créé.")])}
    u = gu.old_units(data)[0]
    u.update(good="In principio créa", good_words=3, changes=[])
    assert gu.status(u, {10}) == "identical"
    assert gu.status({"uid": "good:1:7:0", "parts": [], "changes": []}, {10}) == "only_good"


def test_moved_links_both_units():
    units = units_ab()
    moved = "les eaux supérieures sont séparées des inférieures par le firmament"
    units[0].update(good="alpha", good_words=1)
    units[1].update(good="delta " + moved, good_words=11)
    gu.attach(units, [rec(kind="moved", path=A, old=moved, old_words=10, words=0)], covered={5})
    c = units[0]["changes"][0]
    assert c["class"] == "moved" and c["moved_with"] == "commentary:1:8:0"
    assert c["gap_in_normalized"] is False


def test_footnote_record_unattached():
    units = units_ab()
    for u in units:
        u.update(good="alpha a b c", good_words=4)
    summary = gu.attach(units, [rec(path="footnotes/0/text", words=3), rec(origin="both_scans", words=3, good_raw="a b c")],
                        covered={5})
    assert summary["unattached"] == 1
    assert units[0]["changes"][0]["gap_in_normalized"] is True
    assert units[0]["status"] == "substantive"


def test_build_merges_chapters(tmp_path, monkeypatch):
    def fake_build(vol, chs):
        units = [{"uid": f"verse:{c}:1:0", "type": "verse", "chapter": c, "status": "identical", "v": len(chs)}
                 for c in sorted(chs)]
        return {"vol": vol, "chapters": sorted(chs), "units": units, "summary": {"unattached": 0}}
    monkeypatch.setattr(gu, "build", fake_build)
    out = tmp_path / "good_units.json"
    gu.write("01_genese", {1, 2}, out)
    res = gu.write("01_genese", {3}, out)
    assert res["chapters"] == [1, 2, 3]
    assert [u["uid"] for u in res["units"]] == ["verse:1:1:0", "verse:2:1:0", "verse:3:1:0"]
    assert [u["v"] for u in res["units"]] == [2, 2, 1]  # chapters 1-2 as written by the first run
    assert res["summary"] == {"identical": 3, "unattached": 0}


def test_unlinked_heading_goes_to_its_unit():
    units = gu.old_units({5: page([note(1, 31, "alpha beta", lq="VIDIT")], chapter_summary="Création du monde, repos de Dieu.",
                                  chapter_number=2),
                          6: page([note(2, 1, "delta epsilon", lq="IGITUR")])})
    ctx = ctx_of([("alpha", A, None), ("CHAPITRE", None, None), ("II", None, None), ("Création", None, None),
                  ("du", None, None), ("monde", None, None), ("repos", None, None), ("de", None, None),
                  ("Dieu", None, None), ("Ajouté", None, None)])
    ctx["jt"].append({"t": "delta", "k": "delta", "page": 6, "path": A, "a": 0, "b": 5})
    ctx["stream"].append(dict(ctx["stream"][0], t="delta", k="delta", j=len(ctx["jt"]) - 1))
    for w in ctx["stream"]:
        w["src_page"] = 5
    gu.project(units, ctx)
    by = {u["uid"]: u for u in units}
    assert by["summary:2:None:0"]["good"] == "CHAPITRE II Création du monde repos de Dieu"
    assert by["commentary:1:31:0"]["good"] == "alpha"
    assert by["commentary:2:1:0"]["good"] == "Ajouté delta"


def test_unlinked_verse_read_inside_another():
    V1, V2 = "verses/0/french", "verses/1/french"
    units = gu.old_units({5: page(verses=[verse(49, 1, "Jacob appela ses enfants"),
                                          verse(49, 2, "Assemblez-vous et écoutez enfants de Jacob")])})
    ctx = ctx_of([("Jacob", V1, None), ("appela", V1, None), ("Assemblez-vous", None, None), ("et", None, None),
                  ("écoutez", None, None), ("enfants", None, None), ("de", None, None), ("Jacob", None, None),
                  ("ses", V1, None), ("enfants", V1, None)])
    for w in ctx["stream"]:
        w["src_page"] = 5
    gu.project(units, ctx)
    by = {u["uid"]: u for u in units}
    assert by["verse:49:2:0"]["good"] == "Assemblez-vous et écoutez enfants de Jacob"
    assert by["verse:49:1:0"]["good"] == "Jacob appela ses enfants"


# the whole-branch review's findings
LONG = ("les notes sur les versets huit à douze que le Commentaire place ici après le verset dix-neuf parlent de "
        "Nemrod le puissant chasseur devant le Seigneur et des villes de Babylone Arach Achad et Chalanne dans la "
        "terre de Sennaar puis de Ninive et de Chalé et de Résen la grande ville entre Ninive et Chalé dont "
        "Moïse rapporte la fondation par Assur sorti de ce pays selon la plupart des interprètes anciens et modernes")


def test_long_unaligned_run_not_given_to_neighbour():
    units = gu.old_units({5: page([note(10, 19, "alpha beta", lq="FACTIQUE"), note(10, 20, "delta epsilon", lq="HI FILII")]),
                          6: page([note(10, 8, LONG, lq="PORRO CHUS")])})
    words = [("alpha", A, None)] + [(t, None, None) for t in LONG.split()] + [("delta", B, None)]
    new = gu.project(units, ctx_of(words))
    assert good_of(units, "commentary:10:19:0") == "alpha"
    assert [(n["uid"], n["type"], n["after"]) for n in new] == [("unaligned:10:0", "unaligned", "commentary:10:19:0")]
    assert new[0]["good_words"] == len(LONG.split())
    assert gu.status(new[0], {5}) == "unaligned"


def test_covered_pages_are_linked_pages():
    ctx = ctx_of([("alpha", A, None), ("orphan", None, None)])
    for w in ctx["stream"]:
        w["src_page"] = 7
    assert gu.covered_pages(ctx) == {5}


def test_page_with_stray_links_not_covered():
    ctx = ctx_of([("alpha", A, None)])
    ctx["jt"] += [{"t": f"w{n}", "k": f"w{n}", "page": 5, "path": A, "a": 0, "b": 2} for n in range(9)]
    assert gu.covered_pages(ctx) == set()  # 1 word of 10 linked: the page was not aligned


def test_long_run_next_to_footnote_link_kept():
    units = gu.old_units({5: page([note(10, 19, "alpha beta", lq="FACTIQUE"), note(10, 20, "delta epsilon", lq="HI FILII")]),
                          6: page([note(10, 8, LONG, lq="PORRO CHUS")])})
    words = [("alpha", A, None), ("Hebr", "footnotes/0/text", None)] + [(t, None, None) for t in LONG.split()] + \
        [("delta", B, None)]
    new = gu.project(units, ctx_of(words))
    assert [n["type"] for n in new] == ["unaligned"]


def test_footnote_linked_word_is_a_barrier():
    units = units_ab()
    gu.project(units, ctx_of([("alpha", A, None), ("Joseph", None, None), ("Hebr", "footnotes/0/text", None),
                              ("lib", None, None), ("delta", B, None)]))
    assert good_of(units, "commentary:1:6:0") == "alpha"
    assert good_of(units, "commentary:1:8:0") == "delta"


def test_lemma_after_heading_still_found():
    units = gu.old_units({5: page([note(1, 31, "alpha beta", lq="VIDIT")], chapter_summary="Création du monde, repos de Dieu.",
                                  chapter_number=2),
                          6: page([note(2, 2, "delta epsilon", lq="COMPLEVIT")])})
    ctx = ctx_of([("alpha", A, None)] + [(t, None, None) for t in
                  "CHAPITRE II Création du monde repos de Dieu ŷ. 1. IGITUR PERFECTI SUNT texte".split()])
    ctx["jt"].append({"t": "delta", "k": "delta", "page": 6, "path": A, "a": 0, "b": 5})
    ctx["stream"].append(dict(ctx["stream"][0], t="delta", k="delta", j=len(ctx["jt"]) - 1))
    for w in ctx["stream"]:
        w["src_page"] = 5
    new = gu.project(units, ctx)
    by = {u["uid"]: u for u in units}
    assert by["summary:2:None:0"]["good"] == "CHAPITRE II Création du monde repos de Dieu"
    assert [n["uid"] for n in new] == ["good:2:1:0"]
    assert new[0]["good"].startswith("ŷ. 1. IGITUR")


def test_heading_window_needs_three_words():
    units = gu.old_units({5: page([note(1, 31, "alpha beta", lq="VIDIT"), note(1, 32, "delta", lq="FIAT")],
                                  chapter_title="Chapitre II.", chapter_number=2)})
    ctx = ctx_of([("alpha", A, None), ("Chapitre", None, None), ("II", None, None), ("delta", B, None)])
    for w in ctx["stream"]:
        w["src_page"] = 5
    gu.project(units, ctx)
    assert next(u for u in units if u["type"] == "title")["good"] == ""
