import json
import re

import pytest

from page_region import (
    _squash,
    commentary_band,
    find_heading,
    find_running_head,
    group_lines,
)


def tsv_row(block, par, line, text, top, left=0, width=100, height=30):
    return {
        "level": "5", "block_num": str(block), "par_num": str(par), "line_num": str(line),
        "text": text, "top": str(top), "left": str(left), "width": str(width), "height": str(height),
    }


def test_group_lines_joins_words_of_a_line():
    rows = [
        tsv_row(1, 1, 1, "COMMENTAIRE.", 500, left=600, width=300),
        tsv_row(1, 1, 2, "premier", 600, left=100, width=80),
        tsv_row(1, 1, 2, "mot", 600, left=190, width=50),
    ]
    lines = group_lines(rows)
    assert [ln["text"] for ln in lines] == ["COMMENTAIRE.", "premier mot"]
    assert lines[0]["width"] == 300
    assert lines[1]["bot"] == 630


def test_group_lines_skips_empty_and_non_word_levels():
    rows = [
        {"level": "4", "block_num": "1", "par_num": "1", "line_num": "1", "text": "", "top": "0",
         "left": "0", "width": "0", "height": "0"},
        tsv_row(1, 1, 1, "  ", 0),
        tsv_row(1, 1, 1, "mot", 10),
    ]
    assert [ln["text"] for ln in group_lines(rows)] == ["mot"]


@pytest.mark.parametrize("raw,expected", [
    ("COMMENTAIRE.", "COMMENTAIRE"),
    ("COMMENTAIRE,", "COMMENTAIRE"),
    ("C O M M E N T A I R E.", "COMMENTAIRE"),
    ("COMMENTAIRE “", "COMMENTAIRE"),
    ("COMMENTAIRE LITTERAL", "COMMENTAIRELITTERAL"),
])
def test_squash(raw, expected):
    assert _squash(raw) == expected


def test_find_heading_ignores_the_running_head():
    lines = [
        {"text": "COMMENTAIRE LITTERAL", "width": 900, "top": 60, "bot": 100},
        {"text": "COMMENTAIRE.", "width": 380, "top": 570, "bot": 600},
    ]
    assert find_heading(lines)["top"] == 570


def test_find_heading_accepts_letter_spaced_and_comma_forms():
    for text in ("C O M M E N T A I R E.", "COMMENTAIRE,", "COMMENTAIRE “"):
        lines = [{"text": text, "width": 400, "top": 500, "bot": 530}]
        assert find_heading(lines) is not None, text


def test_find_heading_none_on_a_continuation_page():
    lines = [{"text": "ſuite du commentaire.", "width": 900, "top": 200, "bot": 240}]
    assert find_heading(lines) is None


def test_find_running_head_needs_an_upper_case_line_in_the_top_band():
    upper = {"text": "SUR LES PROVERBES DE SALOMON. CHAP. XXV.", "top": 60, "bot": 100}
    lower = {"text": "ſuite du commentaire precedent", "top": 60, "bot": 100}
    assert find_running_head([upper], 1900) is not None
    assert find_running_head([lower], 1900) is None
    assert find_running_head([{**upper, "top": 400}], 1900) is None


def _band(png, tsv):
    return commentary_band(png, tsv=tsv)


def test_band_errors_without_a_rule(tmp_path):
    """A page with no footnote rule must fail loudly, not swallow the footnotes."""
    from PIL import Image

    png = tmp_path / "p.png"
    Image.new("L", (400, 1000), 255).save(png)
    tsv = tmp_path / "p.tsv"
    tsv.write_text(
        "level\tblock_num\tpar_num\tline_num\ttop\tleft\twidth\theight\ttext\n"
        "5\t1\t1\t1\t60\t100\t200\t30\tCOMMENTAIRE LITTERAL\n"
        "5\t1\t1\t2\t500\t100\t200\t30\tCOMMENTAIRE.\n"
        "5\t1\t1\t3\t600\t100\t300\t30\ttexte\n",
        encoding="utf-8",
    )
    band = _band(png, tsv)
    assert "error" in band
    assert band["layout"] == "heading"
    assert band["y0"] == 530


def test_band_finds_a_drawn_rule(tmp_path):
    from PIL import Image, ImageDraw

    png = tmp_path / "p.png"
    im = Image.new("L", (400, 1000), 255)
    ImageDraw.Draw(im).line([(40, 800), (360, 800)], fill=0, width=2)
    im.save(png)
    tsv = tmp_path / "p.tsv"
    tsv.write_text(
        "level\tblock_num\tpar_num\tline_num\ttop\tleft\twidth\theight\ttext\n"
        "5\t1\t1\t1\t60\t100\t200\t30\tCOMMENTAIRE LITTERAL\n"
        "5\t1\t1\t2\t500\t100\t200\t30\tCOMMENTAIRE.\n"
        "5\t1\t1\t3\t600\t100\t300\t30\ttexte\n"
        "5\t1\t1\t4\t900\t100\t300\t30\tnote\n",
        encoding="utf-8",
    )
    band = _band(png, tsv)
    assert "error" not in band
    assert band["layout"] == "heading"
    assert 795 <= band["y1"] <= 805


SCANS = [
    # page, layout, expected OCR word count in the band (Tesseract fra, psm 3)
    ("page_0305", "heading", 324),
    ("page_0318", "heading", 412),
    ("page_0308", "continuation", 426),
    ("page_0311", "continuation", 456),
]


def _scans_and_fra_available():
    import shutil
    import subprocess

    scan = __import__("paths").DATA / "22_proverbes" / "source_images" / "commentaire" / "page_0305.png"
    if not scan.exists() or not shutil.which("tesseract"):
        return False
    try:
        langs = subprocess.run(
            ["tesseract", "--list-langs"], capture_output=True, text=True
        ).stdout
    except OSError:
        return False
    return "fra" in langs.split()


@pytest.mark.skipif(
    not _scans_and_fra_available(),
    reason="scans or the fra.traineddata model are not available",
)
@pytest.mark.parametrize("page,layout,count", SCANS)
def test_band_on_real_scans(page, layout, count):
    from paths import DATA
    from page_region import load_tsv

    folder = DATA / "22_proverbes" / "source_images" / "commentaire"
    band = commentary_band(folder / f"{page}.png")
    assert band["layout"] == layout
    lines = group_lines(load_tsv(band["tsv"]))
    inside = [ln for ln in lines if band["y0"] <= ln["top"] <= band["y1"]]
    assert abs(sum(len(re.findall(r"\S+", ln["text"])) for ln in inside) - count) <= 2
