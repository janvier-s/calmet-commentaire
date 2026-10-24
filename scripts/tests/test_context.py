import pytest

from review_store import Store


@pytest.fixture
def store(data_dir):
    return Store(data_dir, data_dir.parent / "docs")


def test_prev_context(store):
    prev = store.context("22_proverbes", 194)["prev"]
    assert prev["page"] == 193
    assert (prev["chapter"], prev["verse"]) == (17, 1)
    assert (prev["commentary_chapter"], prev["verse_ref"]) == (17, 1)
    assert prev["tail"] == "…que la maison pleine de victimes."


def test_prev_walks_back(store):
    d, v = store.read("22_proverbes", 194)
    d["commentary"], d["footnotes"] = [], []
    store.save("22_proverbes", 194, d, v)
    assert store.context("22_proverbes", 195)["prev"]["page"] == 193


def test_prev_none_on_first_page(store):
    assert store.context("22_proverbes", 193)["prev"] is None


def test_next_context_continuation(store):
    nxt = store.context("22_proverbes", 193)["next"]
    assert nxt["page"] == 194
    assert nxt["continuation"] is True
    assert nxt["head"] == "suite du commentaire."
    assert store.context("22_proverbes", 195)["next"] is None


def test_next_first_verse(store):
    nxt = store.context("22_proverbes", 194)["next"]
    assert (nxt["chapter"], nxt["verse"]) == (17, 4)


def test_locate(store):
    assert store.locate("22_proverbes", 17, 2) == 194
    assert store.locate("22_proverbes", 17, 4) == 195
    assert store.locate("22_proverbes", 17, None) == 193
    assert store.locate("22_proverbes", 99, 1) is None


def test_locate_after_save(store):
    assert store.locate("22_proverbes", 17, 4) == 195
    d, v = store.read("22_proverbes", 194)
    d["verses"] = [{"chapter": 17, "verse_number": 4, "latin": "x", "french": "y", "annotations": None}]
    store.save("22_proverbes", 194, d, v)
    assert store.locate("22_proverbes", 17, 4) == 194
