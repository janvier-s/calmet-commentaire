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
