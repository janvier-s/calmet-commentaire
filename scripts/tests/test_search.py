import json
import os

from review_search import Searcher, fold
from review_store import Store

VOL = "22_proverbes"


def test_fold_drops_accents_and_case_and_keeps_offsets():
    f, at = fold("Père ſage, Œuvre")
    assert f == "pere sage, oeuvre"
    # each folded character points back to the character it came from
    assert at[f.index("sage")] == 5 and at[f.index("oeuvre")] == 11 and at[f.index("euvre")] == 11


def test_fold_collapses_spaces():
    f, at = fold("pain\n  sec")
    assert f == "pain sec" and at[f.index("sec")] == 7


def hits(data_dir, q, vols=(VOL,)):
    return Searcher(Store(data_dir, data_dir.parent / "docs")).search(q, list(vols))


def test_finds_accented_word_without_accent(data_dir):
    r = hits(data_dir, "mechant")
    assert r["total"] == 1
    h = r["hits"][0]
    assert (h["vol"], h["page"], h["path"]) == (VOL, 195, ["verses", 0, "french"])
    text = "Le méchant obéit à la langue injuste."
    assert text[h["start"]:h["end"]] == "méchant"
    assert h["before"].endswith("Le ") and h["after"].startswith(" obéit")


def test_case_and_phrase_across_a_line_break(data_dir):
    r = hits(data_dir, "PAIX QUE la")
    assert [(h["page"], h["path"][2]) for h in r["hits"]] == [(193, "french_commentary")]


def test_every_hit_in_page_order(data_dir):
    r = hits(data_dir, "un morceau")
    assert [(h["page"], h["path"]) for h in r["hits"]] == [
        (193, ["verses", 0, "french"]), (193, ["commentary", 0, "french_translation"])]


def test_footnotes_searched(data_dir):
    assert [h["path"] for h in hits(data_dir, "prov. 17")["hits"]] == [["footnotes", 0, "text"]]


def test_short_query_finds_nothing(data_dir):
    assert hits(data_dir, " a ")["total"] == 0


def test_limit_keeps_the_total(data_dir):
    r = Searcher(Store(data_dir, data_dir.parent / "docs")).search("e", [VOL], limit=2, min_len=1)
    assert len(r["hits"]) == 2 and r["total"] > 2


def test_sees_a_page_saved_since(data_dir):
    s = Searcher(Store(data_dir, data_dir.parent / "docs"))
    assert s.search("zorglub", [VOL])["total"] == 0
    p = data_dir / VOL / "normalized" / "page_0194.json"
    d = json.loads(p.read_text())
    d["commentary"][0]["french_commentary"] = "Zorglub"
    p.write_text(json.dumps(d, ensure_ascii=False))
    st = p.stat()
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
    assert s.search("zorglub", [VOL])["total"] == 1


def tag_page(data_dir, notes):
    p = data_dir / VOL / "normalized" / "page_0194.json"
    d = json.loads(p.read_text())
    d["footnotes"] = notes
    p.write_text(json.dumps(d, ensure_ascii=False))


def test_tag_alone_lists_the_footnotes_with_it(data_dir):
    tag_page(data_dir, [{"marker": "(a)", "text": "Saint Basile, Homélie 6.", "tags": ["fathers"]},
                        {"marker": "(b)", "text": "Pline, livre 2.", "tags": ["classical"]},
                        {"marker": "(c)", "text": "Ibid.", "tags": []},
                        {"marker": "(d)", "text": "Saint Jérôme.", "tags": ["fathers"]}])
    r = hits(data_dir, "tag:fathers")
    assert [h["path"][1] for h in r["hits"]] == [0, 3]
    assert r["hits"][0]["match"] == "Saint Basile, Homélie 6."
    assert [h["path"][1] for h in hits(data_dir, "tag:none")["hits"]] == [2]


def test_tag_with_words(data_dir):
    tag_page(data_dir, [{"marker": "(a)", "text": "Saint Basile, Homélie 6.", "tags": ["fathers"]},
                        {"marker": "(b)", "text": "Saint Jérôme, homélie 2.", "tags": ["fathers"]},
                        {"marker": "(c)", "text": "Pline, homélie.", "tags": ["classical"]}])
    r = hits(data_dir, "tag:fathers homelie")
    assert [h["path"][1] for h in r["hits"]] == [0, 1] and r["hits"][1]["match"] == "homélie"


def test_untagged_footnotes_are_not_tag_none(data_dir):
    # no "tags" key at all: not tagged yet, so neither found by a tag nor by tag:none
    assert hits(data_dir, "tag:none")["total"] == 0


def test_save_keeps_tags(data_dir):
    s = Store(data_dir, data_dir.parent / "docs")
    d, v = s.read(VOL, 194)
    d["footnotes"][0]["tags"] = ["verse", "fathers"]
    saved, _ = s.save(VOL, 194, d, v)
    assert saved["footnotes"][0]["tags"] == ["verse", "fathers"]
