"""A note's chapter and verse_ref carry to the blocks that go on from it, and the script that mends old ones."""
import copy

import continuations as C


def block(i, ch, ref, fc, lemma=None, tr=None):
    return {"commentary_id": i, "chapter": ch, "verse_ref": ref, "latin_quote": lemma, "french_translation": tr,
            "french_commentary": fc}


def page(*blocks):
    return {"commentary": list(blocks)}


OLD = page(block(1, 3, "4", "la suite du texte"), block(2, 3, "4", "Texte", "UBI EST ADAM", "Où est-il"),
           block(3, 3, "4", "et la fin,"), block(4, 3, "4", "et encore"))


def test_continuations_follow_their_note_on_the_page():
    new = copy.deepcopy(OLD)
    new["commentary"][1]["verse_ref"] = "5"
    page_, nxt = C.carry_refs(new, OLD)
    assert [b["verse_ref"] for b in page_["commentary"]] == ["4", "5", "5", "5"]
    assert nxt is None


def test_a_block_with_its_own_lemma_stops_the_chain():
    old = page(block(1, 1, "1", "a", "L", "t"), block(2, 1, "1", "b"), block(3, 1, "1", "c", "M", "u"), block(4, 1, "1", "d"))
    new = copy.deepcopy(old)
    new["commentary"][0]["verse_ref"] = "2"
    got, _ = C.carry_refs(new, old)
    assert [b["verse_ref"] for b in got["commentary"]] == ["2", "2", "1", "1"]


def test_a_block_changed_on_its_own_is_left():
    new = copy.deepcopy(OLD)
    new["commentary"][1]["verse_ref"] = "5"
    new["commentary"][2]["verse_ref"] = "9"
    got, _ = C.carry_refs(new, OLD)
    assert [b["verse_ref"] for b in got["commentary"]] == ["4", "5", "9", "9"]


def test_chapter_follows_too():
    new = copy.deepcopy(OLD)
    new["commentary"][1]["chapter"] = 4
    got, _ = C.carry_refs(new, OLD)
    assert [b["chapter"] for b in got["commentary"]] == [3, 4, 4, 4]


def test_the_next_page_follows_from_the_last_note():
    nxt = page(block(1, 3, "4", "et c'est pourquoi"), block(2, 3, "4", "elle a dit"), block(3, 3, "5", "NOUVEAU", "X", "y"))
    new = copy.deepcopy(OLD)
    new["commentary"][1]["verse_ref"] = "5"
    _, n = C.carry_refs(new, OLD, nxt)
    assert [b["verse_ref"] for b in n["commentary"]] == ["5", "5", "5"]  # the third has a lemma of its own: untouched
    assert nxt["commentary"][0]["verse_ref"] == "4"  # the input is not changed


def test_a_new_sentence_after_a_full_stop_is_left_to_a_reader():
    old = page(block(1, 1, "1", "Fin de la note."))
    new = copy.deepcopy(old)
    new["commentary"][0]["verse_ref"] = "2"
    nxt = page(block(1, 1, "1", "Si l'on veut"))
    _, n = C.carry_refs(new, old, nxt)
    assert n is None


def test_nothing_carried_when_blocks_were_added_or_removed():
    new = copy.deepcopy(OLD)
    new["commentary"][1]["verse_ref"] = "5"
    del new["commentary"][3]
    got, n = C.carry_refs(new, OLD, page(block(1, 3, "4", "suite")))
    assert [b["verse_ref"] for b in got["commentary"]] == ["4", "5", "4"] and n is None


def test_nothing_changed_nothing_carried():
    got, n = C.carry_refs(copy.deepcopy(OLD), OLD, page(block(1, 9, "9", "suite")))
    assert got == OLD and n is None


def test_empty_values_do_not_erase():
    b = block(2, 1, "7", "suite")
    C.copy_refs(b, {"chapter": None, "verse_ref": ""})
    assert (b["chapter"], b["verse_ref"]) == (1, "7")


def test_start_missing_after_a_lemma_with_no_comment():
    last = block(5, 1, "3", "", "LEMME.", "Traduction.")
    assert C.start_missing(last, block(1, 1, "3", "et la suite de la phrase"))
    assert C.start_missing(last, block(1, 1, "3", "_et_ la suite"))
    assert C.start_missing(None, block(1, 1, "3", "et la suite"))  # the page before has no notes


def test_start_missing_not_when_there_is_something_to_go_on_from():
    assert not C.start_missing(block(5, 1, "3", "Un début de phrase"), block(1, 1, "3", "et la suite"))
    assert not C.start_missing(block(5, 1, "3", "", "LEMME.", "Traduction."), block(1, 1, "3", "Une phrase neuve"))
    assert not C.start_missing(block(5, 1, "3", "", "LEMME.", "Traduction."), block(1, 1, "3", "et", "NOUVEAU.", "Neuf."))
    assert not C.start_missing(block(5, 1, "3", "", "LEMME.", "Traduction coupée-"), block(1, 1, "3", "et la suite"))
    assert not C.start_missing(block(5, 1, "3", "", "LEMME.", "Traduction cut"), block(1, 1, "3", "et la suite"))
