import good_italics as gi


def _ws(*pairs):
    return [{"t": t, "sl": s} for t, s in pairs]


def test_runs_by_slant_with_neighbours_for_the_unsure():
    ws = _ws(("la", 0), ("Terre", 1), ("in", 15), ("illo", 6), ("tempore,", 18), ("fut", 0), ("de", 12), ("et", 2))
    assert gi.runs(ws) == [[2, 4]]  # illo (6) between two italic words is italic; a lone "de" is not a run


def test_apply_keeps_punctuation_outside_and_follows_modernization():
    raw = "Dieu créoit & in principio, puis"
    ws = _ws(("Dieu", 1), ("créoit", 2), ("&", 2), ("in", 15), ("principio,", 17), ("puis", 0))
    final = "Dieu créait et in principio, puis"
    assert gi.apply(final, raw, gi.runs(ws)) == "Dieu créait et _in principio_, puis"


def test_shift_moves_flags_past_underscores():
    assert gi.shift([{"a": 3, "b": 7}], "la _Terre_ ou") == [{"a": 4, "b": 8}]
