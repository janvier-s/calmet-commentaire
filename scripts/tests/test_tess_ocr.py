"""Tesseract's reading: the TSV parsed, the words under a box (made-up readings; Tesseract is not run)."""
import tess_ocr as T

TSV = ("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
       "5\t1\t1\t1\t1\t1\t340\t300\t100\t30\t91.5\ttelles\n5\t1\t1\t1\t1\t2\t500\t300\t40\t30\t-1\t \n")


def test_parse_tsv_keeps_words_only():
    assert T.parse_tsv(TSV) == [{"t": "telles", "box": [340, 300, 100, 30], "conf": 91.5}]


def test_under_reads_the_words_beneath_the_boxes():
    t = {"words": T.parse_tsv(TSV)}
    assert T.under(t, [[345, 302, 90, 28]]) == "telles" and T.under(t, [[900, 300, 50, 30]]) == ""


def test_a_failed_run_says_why_and_is_not_cached(tmp_path, monkeypatch):
    import tess_ocr as T
    scan = tmp_path / "scan.png"
    scan.write_bytes(b"")
    monkeypatch.setattr(T, "TESS_CACHE", tmp_path / "tess")
    monkeypatch.setattr(T, "scan_path", lambda vol, page: scan)
    monkeypatch.setattr(T, "fetch_models", lambda: None)
    monkeypatch.setattr(T, "TESSERACT", str(tmp_path / "no-tesseract"))
    r = T.read("v", 1, run=True)
    assert r["words"] == [] and "tesseract not found" in r["error"]
    assert not T.cache_path("v", 1).exists()
