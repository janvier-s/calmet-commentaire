"""review_store: a Good_Calmet crop trimmed after its display copy and its OCR (good_calmet_tighten*.py)."""
import json
import os

from PIL import Image

import good_calmet_kraken as gk
from review_store import Store


def _setup(data_dir, tmp_path, monkeypatch, trimmed=True):
    good = data_dir / "good_calmet"
    crop = good / "P" / "page_0005.png"
    crop.parent.mkdir(parents=True)
    Image.new("L", (80, 90) if trimmed else (100, 120), 255).save(crop)
    rec = {"pdf": "P", "pdf_page": 5, "source": "page_0194", "vol": "22_proverbes", "box": [0, 0, 80, 90]}
    if trimmed:
        rec.update(tightened=[20, 10], tightened_x=[15, 5])
    (good / "crops.json").write_text(json.dumps({"P/page_0005": rec}))
    shown = data_dir / "good_calmet_display" / "P" / "page_0005.png"
    shown.parent.mkdir(parents=True)
    Image.new("L", (100, 120), 0).save(shown)  # made before the trim
    os.utime(shown, (1, 1))
    ocr = tmp_path / "ocr" / "P" / "page_0005.json"
    ocr.parent.mkdir(parents=True)
    ocr.write_text(json.dumps({"size": [100, 120], "lines": []}))  # read before the trim
    monkeypatch.setattr(gk, "cache_path", gk.cache_in(tmp_path / "ocr"))
    return Store(data_dir, data_dir.parent / "docs"), crop, shown


def test_stale_display_copy_made_again_from_the_trimmed_crop(data_dir, tmp_path, monkeypatch):
    st, crop, shown = _setup(data_dir, tmp_path, monkeypatch)
    assert st.good_pages("22_proverbes", 194) == [crop]
    assert st.good_shown(crop) == shown
    assert Image.open(shown).size == (80, 90)


def test_boxes_offset_by_the_trim_made_after_the_ocr(data_dir, tmp_path, monkeypatch):
    st, crop, _ = _setup(data_dir, tmp_path, monkeypatch)
    assert st.good_offset(crop) == (15, 20)


def test_no_offset_when_the_ocr_read_the_crop_as_it_is(data_dir, tmp_path, monkeypatch):
    st, crop, _ = _setup(data_dir, tmp_path, monkeypatch, trimmed=False)
    assert st.good_offset(crop) == (0, 0)
    assert st.good_offset(data_dir / "elsewhere.png") == (0, 0)
