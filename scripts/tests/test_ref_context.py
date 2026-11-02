import ref_check as C
import ref_context as R
import bible_refs as B


def test_rewrite_keeps_calmets_label_and_punctuation():
    assert R.rewrite("Psaume 11:7", "Psaumes 9:28") == "Psaume 9:28"
    assert R.rewrite("1 Rois 11:1-3", "3 Rois 11:1-3") == "3 Rois 11:1-3"
    assert R.rewrite("; 49:33.", "Jérémie 49:32", "Jérémie 49:33") == "; 49:32."


def test_rewrite_bare_reference_names_the_book_only_when_it_changes():
    assert R.rewrite("et 12:10", "4 Rois 12:10", "Psaumes 12:10") == "et 4 Rois 12:10"
    assert R.rewrite("12:10", "Psaumes 12:11", "Psaumes 12:10") == "12:11"


def test_book_numbers_offers_the_other_numbers():
    r = B.find_refs("Voyez 1 Rois 11:1-3 .")[0]
    assert {x.book for x in C.book_numbers(r)} == {"2 Rois", "3 Rois", "4 Rois"}


def test_arbitrate_takes_the_verse_that_has_the_quoted_words():
    v = dict(verdict="unsure", written="Amos 6:9", fix="",
             first=dict(fix="Amos 7:9", why="et demolientur excelsa idoli, et sanctificationes Israel desolabuntur"),
             second=dict(fix="Amos 7:2", why="et demolientur excelsa idoli, et sanctificationes Israel desolabuntur"))
    assert R.arbitrate(v) == "Amos 7:9"
    assert R.arbitrate(dict(v, verdict="wrong")) is None
