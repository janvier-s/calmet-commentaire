import json

import pytest

from page_text import LRM, trim
from punctuation import clean_page
from review_store import EMPTY_PAGE, Conflict, Store, form_values


@pytest.fixture
def store(data_dir):
    return Store(data_dir, data_dir.parent / "docs")


def path(store, page):
    return store.data / "22_proverbes" / "normalized" / f"page_{page:04d}.json"


def test_pages_ignore_conflict_copies(store):
    assert store.pages("22_proverbes") == [193, 194, 195]
    assert store.volumes() == ["22_proverbes"]


def test_read_save_roundtrip(store):
    d, v = store.read("22_proverbes", 194)
    saved, v2 = store.save("22_proverbes", 194, d, v)
    expected = trim(clean_page(json.loads(path(store, 194).read_text(encoding="utf-8"))))
    assert path(store, 194).read_text(encoding="utf-8") == json.dumps(expected, ensure_ascii=False, indent=2)
    assert saved == expected and v2 != ""


def test_save_conflict(store):
    d, v = store.read("22_proverbes", 194)
    other = json.loads(path(store, 194).read_text(encoding="utf-8"))
    other["footnotes"][0]["text"] = "changed by a script, a longer text"
    path(store, 194).write_text(json.dumps(other, ensure_ascii=False, indent=2), encoding="utf-8")
    d["commentary"][1]["french_commentary"] = "mine"
    with pytest.raises(Conflict) as e:
        store.save("22_proverbes", 194, d, v)
    assert e.value.disk["footnotes"][0]["text"] == "changed by a script, a longer text"
    assert e.value.version
    store.save("22_proverbes", 194, d, v, force=True)
    assert "mine" in path(store, 194).read_text(encoding="utf-8")


def test_save_strips_lrm(store):
    d, v = store.read("22_proverbes", 194)
    d["commentary"][1]["french_commentary"] = f"voir {LRM}שלום{LRM} ici"
    store.save("22_proverbes", 194, d, v)
    assert LRM not in path(store, 194).read_text(encoding="utf-8")


def test_form_values():
    d = {"verses": [{"verse_number": "7", "chapter": "null", "latin": "x"}],
         "commentary": [{"verse_ref": "7-8", "commentary_id": " 2 ", "chapter": ""}],
         "chapter_number": None}
    out = form_values(d)
    assert out["verses"][0]["verse_number"] == 7
    assert out["verses"][0]["chapter"] is None
    assert out["commentary"][0]["verse_ref"] == "7-8"
    assert out["commentary"][0]["commentary_id"] == 2
    assert out["commentary"][0]["chapter"] is None
    assert out["chapter_number"] is None


def test_create_page(store):
    d, v = store.create("22_proverbes", 196)
    assert d == EMPTY_PAGE and v
    assert 196 in store.pages("22_proverbes")
    with pytest.raises(FileExistsError):
        store.create("22_proverbes", 196)


def test_scan(store):
    assert store.scan("22_proverbes", 194).name == "page_0194.png"
    assert store.scan("22_proverbes", 193) is None
