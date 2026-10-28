"""Removing what a page turn repeated without leaving an italics mark behind."""
from seam_join import unrepeat


def test_repeat_wrapped_in_italics_loses_the_dangling_mark():
    assert unrepeat("la fin du monde", "_monde_ est proche") == ("la fin du monde", "est proche", "repeat")


def test_a_stray_closing_mark_is_dropped():
    assert unrepeat("la fin du monde", "monde_ est proche") == ("la fin du monde", "est proche", "repeat")


def test_italics_opening_after_the_repeat_are_kept():
    assert unrepeat("la fin du monde", "monde _est proche_") == ("la fin du monde", "_est proche_", "repeat")


def test_a_closing_mark_for_italics_open_before_the_turn_is_kept():
    assert unrepeat("il reste _quelque", "quelque_ chose") == ("il reste _quelque", "_ chose", "repeat")
