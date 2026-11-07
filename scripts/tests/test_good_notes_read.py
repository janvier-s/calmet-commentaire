"""good_notes_read: the crop Flash reads a Good page's notes on."""
import asyncio

import good_notes_read as gr


def run_page(monkeypatch, tmp_path, answers, kraken=False):
    """_read_page with agy answering `answers` in turn; returns (result, the crop tops asked)."""
    monkeypatch.setattr(gr, "CACHE", tmp_path)
    (tmp_path / "01_Genèse_1-2").mkdir()
    tops = []

    def crop(pdf, page, top):
        tops.append(top)
        return tmp_path / f"crop{len(tops)}.png"
    monkeypatch.setattr(gr, "make_crop", crop)
    monkeypatch.setattr(gr, "prepare", lambda pdf, page: (crop(pdf, page, 700 if not kraken else 500), tops[-1], kraken))
    monkeypatch.setattr(gr, "page_height", lambda pdf, page: 1000)
    monkeypatch.setattr(gr, "enlarge", lambda c: c)
    it = iter(answers)

    async def agy(c, prompt=None):
        return next(it), None
    monkeypatch.setattr(gr, "agy", agy)
    return asyncio.run(gr._read_page("01_Genèse_1-2", 281, 6)), tops


def test_none_on_a_70_percent_crop_asks_again_from_45_percent(monkeypatch, tmp_path):
    # Good 281: a chapter's end, its notes at 55% and a vignette below; the 70% crop missed them
    d, tops = run_page(monkeypatch, tmp_path, ["NONE", "(a) L. XI. p. 528."])
    assert tops == [700, 450]
    assert d["top_from"] == "45%" and d["notes"][0]["mark"] == "a"


def test_none_on_both_crops_is_kept(monkeypatch, tmp_path):
    d, tops = run_page(monkeypatch, tmp_path, ["NONE", "NONE"])
    assert tops == [700, 450] and d["notes"] == [] and d["top_from"] == "45%"


def test_a_crop_from_kraken_marks_is_not_moved(monkeypatch, tmp_path):
    d, tops = run_page(monkeypatch, tmp_path, ["(a) Exod. XXXII. 25."], kraken=True)
    assert tops == [500] and d["top_from"] == "kraken"
