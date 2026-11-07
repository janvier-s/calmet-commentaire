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


# --- Good's margin (the chronology, references) is not Good's text ---

def _ln(box, words):
    """A Kraken line; words as (text, x, width) on the line's y."""
    return {"box": box, "words": [{"t": t, "box": [x, box[1], w, box[3]], "wc": 1.0} for t, x, w in words]}


P153 = [  # Good 01_Genèse_1-2 p.153 (size 779 x 1122), the first note of Genèse 1 and its margin
    _ln([692, 705, 68, 21], [("Monde", 692, 40), ("I.", 740, 12)]),
    _ln([691, 721, 78, 25], [("avant", 691, 35), ("J.C.", 735, 30)]),
    _ln([692, 740, 77, 21], [("4000", 692, 25), ("de", 722, 12), ("la", 740, 12)]),
    _ln([693, 758, 76, 23], [("Periode", 693, 45), ("Ju¬", 745, 20)]),
    _ln([692, 775, 61, 19], [("lien", 692, 25), ("710.", 722, 25)]),
    _ln([235, 784, 534, 34], [("N", 235, 30), ("PRINCIPIO,", 267, 115), ("tems", 653, 34), ("Acos", 700, 24),
                              ("avant", 737, 29)]),
    _ln([696, 807, 73, 22], [("l'Ere", 696, 40), ("vul¬", 740, 25)]),
    _ln([235, 812, 502, 33], [("Dieu", 235, 50), ("l'être", 621, 36), ("&", 675, 0), ("gaire¬", 700, 36)]),
    _ln([235, 840, 456, 24], [("le", 235, 20), ("visibles", 600, 80), ("&", 686, 5)]),
    _ln([235, 860, 456, 28], [("invisibles.", 235, 100), ("rien", 650, 41)]),
    _ln([234, 883, 455, 32], [("produit", 234, 70), ("(bi", 660, 29)]),
]


def test_margin_chronology_skipped():
    got = gv.margin_words(P153, [779, 1122])
    texts = sorted(P153[li]["words"][wi]["t"] for li, wi in got)
    assert texts == sorted(["Monde", "I.", "J.C.", "4000", "de", "la", "Periode", "Ju¬", "lien", "710.", "Acos",
                            "avant", "avant", "l'Ere", "vul¬", "gaire¬"])
    assert (9, 1) not in got and (8, 2) not in got  # body words ending at the column's edge stay


def test_without_margin_drops_the_words_and_empty_lines():
    o = {"size": [779, 1122], "lines": P153}
    out = gv.without_margin(o)
    assert len(out["lines"]) == 5
    assert [w["t"] for w in out["lines"][0]["words"]] == ["N", "PRINCIPIO,", "tems"]
    assert len(o["lines"]) == 11  # the cached OCR itself untouched


def _w(j, path, page=154):
    return {"s": "match" if j is not None else "gap", "j": j, "path": path, "pdf_page": page, "t": "x", "k": "x"}


def test_strays_between_neighbouring_body_words_made_gaps():
    """Genèse 1:1: Good's own sentence ("la Terre. Mais ces explications ... la langue Hebraïque.") between
    "créé" (j 289) and "Aquila" (j 291): its words paired with the verse's "la Terre" and a note's words."""
    body, verse, fn = "commentary/0/french_commentary", "verses/0/french", "footnotes/1/text"
    gap = lambda n: [_w(None, None) for _ in range(n)]
    s = [_w(289, body), *gap(2), _w(74, verse), _w(75, verse), *gap(12), _w(1121, fn), _w(1122, fn), _w(638, fn),
         *gap(12), _w(641, fn), _w(291, body)]
    gv.strays(s)
    assert [w["s"] for w in s] == ["match"] + ["gap"] * (len(s) - 2) + ["match"]


def test_a_page_s_notes_between_body_words_across_pages_kept():
    body, fn = "commentary/0/french_commentary", "footnotes/0/text"
    s = [_w(289, body, 153), _w(900, fn, 153), _w(901, fn, 153), _w(290, body, 154)]
    gv.strays(s)
    assert [w["s"] for w in s] == ["match"] * 4


def test_a_long_run_elsewhere_kept():
    body, verse = "commentary/0/french_commentary", "verses/1/french"
    s = [_w(289, body)] + [_w(80 + k, verse) for k in range(gv.STRAY_MAX + 1)] + [_w(290, body)]
    gv.strays(s)
    assert all(w["s"] == "match" for w in s)


def test_a_verse_set_between_commentary_lines_kept():
    """Genèse 1:23, "Et du soir & du matin se fit le", between two neighbouring commentary words: mostly linked."""
    body, verse = "commentary/0/french_commentary", "verses/22/french"
    s = [_w(500, body)] + [_w(80 + k, verse) for k in range(6)] + [_w(None, None), _w(501, body)]
    gv.strays(s)
    assert all(w["s"] == "match" for w in s if w["j"] is not None)


def test_the_french_column_read_between_the_latin_s_words_kept():
    """Genèse 34:1: "Egressa est autem Dina | A Lors Dina fille de Lia fartit | ut videret": the French verse,
    6 matches in 13 words but in the JSON's order."""
    lat, verse = "commentary/1/latin_quote", "verses/0/french"
    gap = lambda n: [_w(None, None) for _ in range(n)]
    s = [_w(1150, lat), *gap(6), _w(1024, verse), _w(1024, verse), _w(1025, verse), _w(1026, verse),
         _w(1027, verse), _w(1028, verse), *gap(1), _w(1151, lat)]
    gv.strays(s)
    assert all(w["s"] == "match" for w in s if w["j"] is not None)
