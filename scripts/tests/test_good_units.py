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
