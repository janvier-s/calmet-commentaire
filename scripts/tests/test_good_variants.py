"""good_variants: where an `unclear` Good-only run (its anchors out of order or far apart) is placed."""
import good_variants as gv


def _jt(fields):
    return [{"page": p, "path": path, "k": f"w{j}", "t": f"w{j}", "a": j * 3, "b": j * 3 + 2}
            for j, (p, path) in enumerate(fields)]


def _stream(js):
    """Good words: an int is a word matched to jt[j], None a Good-only word."""
    return [{"s": "match", "j": j, "k": "x", "t": "x"} if j is not None else {"s": "gap", "j": None, "k": "y", "t": "y"}
            for j in js]


def test_unclear_run_goes_where_most_neighbours_are():
    verse, note = (99, "verses/0/french"), (100, "commentary/0/french_commentary")
    jt = _jt([verse] * 10 + [note] * 80)
    # Good: note words 40..44, then four words mismatched to the verse's 5..8, the Good-only run, note 70..73
    stream = _stream([40, 41, 42, 43, 44, 5, 6, 7, 8, None, None, None, 70, 71, 72, 73])
    assert gv.unclear_anchor(stream, [9, 10, 11], 12, jt) == 45  # after the last note word before the run


def test_unclear_run_keeps_its_left_anchor_when_that_is_the_neighbourhood():
    note = (100, "commentary/0/french_commentary")
    jt = _jt([note] * 90)
    stream = _stream([10, 11, 12, 13, None, None, 80, 81])
    assert gv.unclear_anchor(stream, [4, 5], 6, jt) == 14
