"""The script-side page-break repeat detector, and which seam results may replace the older guesses."""
from seam_check import plain, repetition


def test_three_or_more_words_repeated():
    assert repetition("nous lisons dans ce livre la fin du monde",
                      "la fin du monde est proche") == "la fin du monde"


def test_one_content_word_repeated_mid_sentence():
    # Isaïe pp. 188-189: "je suis moi-même un homme ‖ homme dont la langue…"
    assert repetition("je suis moi-même un homme", "homme dont la langue est souillée") == "homme"


def test_two_content_words_repeated_mid_sentence():
    assert repetition("il parla à cet homme sage", "homme sage et prudent") == "homme sage"


def test_one_word_repeat_after_a_full_stop_is_not_a_page_break_repeat():
    assert repetition("cela ne fut pas vain.", "vain disait le prophète") is None


def test_short_particles_are_not_repeats():
    assert repetition("il y en a un peu", "peu de gens le savent") is None
    assert repetition("ils sont à", "à peine arrivés") is None


def test_a_word_split_across_the_break_is_not_a_repeat():
    assert repetition("la gran-", "deur du mystère") is None
    assert repetition("le com-", "mencement de l'histoire") is None


def test_hyphenated_word_reprinted_is_still_a_repeat():
    # "au-jourd'hui ‖ jourd'hui" is the same word printed twice, not a split word
    assert repetition("on dit qu'au-jourd'hui", "jourd'hui en Hollande") == "jourd hui"


def test_italics_on_one_side_do_not_hide_a_repeat():
    # 06_josue p. 129: the quotation is italic on one page, roman on the next
    assert repetition("Il vit un homme _devant_", "devant lui") == "devant"
    assert repetition("Il vit un homme devant", "_devant_ lui") == "devant"


def test_the_model_sees_the_words_without_italics_marks():
    assert plain("_Il vit_ un homme") == "Il vit un homme"
    assert plain(None) == ""


def test_partial_seam_results_do_not_replace_the_older_gap_checks():
    from audit_integrity import seam_fully_read
    read = {"01_genese": {"unread": 0, "flagged": []},
            "27_isaie": {"unread": 714, "flagged": []},
            "47_matthieu": {"unread": 0, "flagged": []}}
    assert seam_fully_read(read) == {"01_genese", "47_matthieu"}
