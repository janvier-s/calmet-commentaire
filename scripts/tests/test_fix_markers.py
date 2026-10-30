"""Tests for footnote marker normalization and clean-up in fix_markers.py."""
from collections import Counter
import fix_markers as F


def test_fix_footnotes_marker_restoration():
    stats = Counter()
    # 1. Alternative marker key (ref -> marker)
    page = {
        "commentary": [{"french_commentary": "Note ^{(a)} ici."}],
        "footnotes": [{"ref": "a", "text": "Saint Augustin."}],
    }
    F.fix_footnotes(page, stats)
    assert page["footnotes"] == [{"marker": "(a)", "text": "Saint Augustin.", "tags": []}]

    # 2. Text prefix extraction
    stats.clear()
    page = {
        "commentary": [{"french_commentary": "Note ^{(b)} ici."}],
        "footnotes": [{"footnote_id": 2, "footnote_text": "^{(b)} Pline, livre 2."}],
    }
    F.fix_footnotes(page, stats)
    assert page["footnotes"] == [{"marker": "(b)", "text": "Pline, livre 2.", "tags": []}]

    # 3. Bare marker normalization
    stats.clear()
    page = {
        "commentary": [{"french_commentary": "Note ^{(c)} ici."}],
        "footnotes": [{"marker": "c", "text": "Cicéron.", "tags": ["classical"]}],
    }
    F.fix_footnotes(page, stats)
    assert page["footnotes"] == [{"marker": "(c)", "text": "Cicéron.", "tags": ["classical"]}]

    # 4. Numeric footnote_id mapping via page calls
    stats.clear()
    page = {
        "commentary": [{"french_commentary": "Note ^{(a)} et ^{(b)}."}],
        "footnotes": [
            {"footnote_id": 1, "text": "Note une."},
            {"footnote_id": 2, "text": "Note deux."},
        ],
    }
    F.fix_footnotes(page, stats)
    assert [fn["marker"] for fn in page["footnotes"]] == ["(a)", "(b)"]

    # 5. Empty dictionary removal
    stats.clear()
    page = {
        "commentary": [{"french_commentary": "Sans note."}],
        "footnotes": [{}],
    }
    F.fix_footnotes(page, stats)
    assert page["footnotes"] == []

    # 6. Alphabetical ordering of footnotes
    stats.clear()
    page = {
        "commentary": [{"french_commentary": "Note ^{(a)} puis ^{(b)} puis ^{(c)}."}],
        "footnotes": [
            {"marker": "(c)", "text": "Troisième."},
            {"marker": "(a)", "text": "Première."},
            {"marker": "(b)", "text": "Deuxième."},
        ],
    }
    F.fix_footnotes(page, stats)
    assert [fn["marker"] for fn in page["footnotes"]] == ["(a)", "(b)", "(c)"]
    assert stats["footnotes sorted"] == 1
