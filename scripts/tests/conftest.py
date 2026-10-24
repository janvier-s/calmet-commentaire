import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

P193 = {"book_title": None, "chapter_title": None, "chapter_summary": None, "chapter_intro": None,
        "verses": [{"chapter": 17, "verse_number": 1, "latin": "Melior est buccella sicca.",
                    "french": "Un morceau de pain sec vaut mieux.", "annotations": None}],
        "commentary": [{"commentary_id": 1, "verse_ref": 1, "chapter": 17,
                        "latin_quote": "MELIOR EST BUCCELLA.", "french_translation": "Un morceau de pain.",
                        "french_commentary": "Il vaut mieux vivre en paix\nque la maison pleine de victimes."}],
        "footnotes": []}
P194 = {"book_title": None, "chapter_title": None, "chapter_summary": None, "chapter_intro": None,
        "verses": [],
        "commentary": [{"commentary_id": 1, "verse_ref": None, "chapter": 17, "latin_quote": None,
                        "french_translation": None, "french_commentary": "suite du commentaire."},
                       {"commentary_id": 2, "verse_ref": 2, "chapter": 17,
                        "latin_quote": "SERVUS SAPIENS DOMINABITUR FILIIS STULTIS.",
                        "french_translation": "Le serviteur sage dominera les enfants insensés.",
                        "french_commentary": "Un esclave qui a de la sagesse ^{(a)}."}],
        "footnotes": [{"marker": "(a)", "text": "Prov. 17. 2."}]}
P195 = {"book_title": None, "chapter_title": None, "chapter_summary": None, "chapter_intro": None,
        "verses": [{"chapter": 17, "verse_number": 4, "latin": "Malus obedit linguae iniquae.",
                    "french": "Le méchant obéit à la langue injuste.", "annotations": None}],
        "commentary": [], "footnotes": []}
QUEUE = [
    {"id": "22_proverbes/0194/hyphen_cut/aaaa", "book_dir": "22_proverbes", "page": 194,
     "kind": "hyphen_cut", "msg": "17:2 cut at the turn", "optional": False},
    {"id": "22_proverbes/0194/missing_footnote/bbbb", "book_dir": "22_proverbes", "page": 194,
     "kind": "missing_footnote", "msg": "call (b) has no note", "optional": False},
    {"id": "22_proverbes/0195/seam_artifact/cccc", "book_dir": "22_proverbes", "page": 195,
     "kind": "seam_artifact", "msg": "glitch", "optional": True},
    {"id": "22_proverbes/0196/missing_page/dddd", "book_dir": "22_proverbes", "page": 196,
     "kind": "missing_page", "msg": "no JSON", "optional": False},
]


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.fixture
def data_dir(tmp_path):
    """A small data/ (Proverbes pages 193-195, a scan for 194 and 196, a conflict copy) and docs/."""
    data = tmp_path / "data"
    norm = data / "22_proverbes" / "normalized"
    for n, page in ((193, P193), (194, P194), (195, P195)):
        dump(norm / f"page_{n:04d}.json", page)
    dump(norm / "page_0194 2.json", P194)
    scans = data / "22_proverbes" / "source_images" / "commentaire"
    scans.mkdir(parents=True)
    for n in (194, 196):
        (scans / f"page_{n:04d}.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    docs = tmp_path / "docs"
    dump(docs / "review_queue.json", QUEUE)
    dump(docs / "false_positives.json", {})
    dump(docs / "manual_issues.json", [])
    return data
