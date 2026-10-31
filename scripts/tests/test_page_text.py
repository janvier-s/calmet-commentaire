import pytest

from page_text import LRM, find_source_image, isolate_hebrew, italic_runs, load_state, save_state, toggle_italics

# Expected values recorded from page_editor.toggle_italics before the move
TOGGLE_CASES = [
    (("a b c", 2, 3), ("a _b_ c", 3, 4)),
    (("_a b c_", 3, 4), ("_a_ b _c_", 3, 6)),
    (("a  b", 1, 3), None),
    (("un mot ici", 3, 6), ("un _mot_ ici", 4, 7)),
    (("_tout_", 1, 5), ("tout", 0, 4)),
    (("un mot ; ici", 3, 6), ("un _mot ;_ ici", 4, 9)),
    (("un mot : ici", 3, 6), ("un _mot :_ ici", 4, 9)),
    (("un mot ? ici", 3, 6), ("un _mot ?_ ici", 4, 9)),
    (("un mot ! ici", 3, 6), ("un _mot !_ ici", 4, 9)),
    (("_un mot ;_ ici", 1, 7), ("un mot ; ici", 0, 9)),
    (("_un mot._ ici", 1, 7), ("un mot. ici", 0, 8)),
]


@pytest.mark.parametrize("args,expected", TOGGLE_CASES)
def test_toggle_italics_cases(args, expected):
    assert toggle_italics(*args) == expected


def test_italic_runs_open_edge():
    assert italic_runs("fin_ suite") == ([(0, 3)], [3], "start")


def test_isolate_hebrew():
    s = isolate_hebrew("voir שלום עליכם ici")
    assert s == f"voir {LRM}שלום עליכם{LRM} ici"
    assert isolate_hebrew(s) == s


def test_find_source_image(data_dir):
    book = data_dir / "22_proverbes"
    assert find_source_image(book, 194) == book / "source_images" / "commentaire" / "page_0194.png"
    assert find_source_image(book, 193) is None


def test_state_roundtrip(tmp_path):
    f = tmp_path / "state.json"
    assert load_state(f) == (None, None)
    save_state("22_proverbes", 194, f)
    assert load_state(f) == ("22_proverbes", 194)
