import numpy as np
import pytest

pytest.importorskip("PIL")
from margin_crop import GOOGLE, text_block  # noqa: E402


def page(w=1000, h=1400, paper=240):
    return np.full((h, w), paper, dtype=np.int16)


def lines(g, x0, x1, y0, y1, step=30, ink=20):
    for y in range(y0, y1, step):
        for x in range(x0, x1, 12):  # words: 9 px of ink, 3 px of space
            g[y:y + 12, x:x + 9] = ink


def test_block_with_margin_note_signature_and_dust():
    g = page()
    lines(g, 200, 800, 100, 1200)            # the column
    lines(g, 120, 180, 400, 440)             # a margin note 2 % of the width away
    g[1260:1280, 650:700] = 20               # the signature mark, below the last line
    for y, x in [(1330, 300), (1360, 520), (60, 900)]:
        g[y:y + 3, x:x + 3] = 20             # dust
    x0, y0, x1, y1 = text_block(g)
    assert x0 <= 120 and x1 >= 796  # last word: 788-796
    assert y0 <= 100 and 1279 <= y1 < 1330


def test_text_after_a_blank_band_is_kept():
    g = page()
    lines(g, 200, 800, 100, 500)
    lines(g, 200, 800, 900, 960)             # text after a wide blank (end of a book)
    assert text_block(g)[3] >= 941  # the last line: 930-941


def test_shadow_column_and_google_mark_ignored():
    g = page()
    lines(g, 200, 800, 100, 1200)
    g[:, 960:975] = 30                       # a dark full-height fold or edge
    lines(g, int(GOOGLE[0] * 1000) + 20, 950, int(GOOGLE[1] * 1400) + 5, 1395, step=20)
    x0, y0, x1, y1 = text_block(g, edge_x=0.005, edge_y=0.005, mask=GOOGLE)
    assert x1 < 900 and y1 < 1250


def test_dull_scan_show_through_is_not_ink():
    g = page(paper=200)
    g[50:1350, 60:940] = 150                 # grey show-through over the whole page
    lines(g, 200, 800, 100, 1200, ink=30)
    x0, y0, x1, y1 = text_block(g)
    assert x0 >= 150 and x1 <= 850
