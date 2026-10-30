import json

import pytest

from review_store import Store
from review_turns import seam_proposal, turn, turn_of

VOL = "22_proverbes"


@pytest.fixture
def store(data_dir):
    return Store(data_dir, data_dir.parent / "docs")


def item(kind, page, where=None, suffix="aaaa"):
    it = {"id": f"{VOL}/{page:04d}/{kind}/{suffix}", "book_dir": VOL, "page": page, "kind": kind, "msg": "", "optional": False}
    if where:
        it["where"] = where
    return it


def edit(store, page, fn):
    d, _ = store.read(VOL, page)
    fn(d)
    store.path(VOL, page).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def test_turn_of_foot_and_head(store):
    last = {"section": "commentary", "index": 1, "field": "french_translation"}
    assert turn_of(store, item("hyphen_cut", 194, last)) == (VOL, 194, 195)
    assert turn_of(store, item("hyphen_cut", 194, dict(last, index=0))) is None
    assert turn_of(store, item("seam_artifact", 195)) == (VOL, 194, 195)
    assert turn_of(store, item("seam_missing", 195, suffix="0193")) == (VOL, 193, 195)
    assert turn_of(store, item("missing_footnote", 194)) is None


def test_turn_payload(store):
    t = turn(store, VOL, 193, 194)
    assert t["a"]["page"] == 193 and t["b"]["page"] == 194
    assert (t["a"]["note"], t["b"]["note"], t["a"]["verse"], t["b"]["verse"]) == (0, 0, 0, None)
    assert t["a"]["version"] == store.read(VOL, 193)[1]
    assert t["join"]["tail"].endswith("victimes.")
    assert t["join"]["head"] == "suite du commentaire."
    assert t["join"]["mode"] == "mend"
    assert "victimes suite du commentaire." in t["join"]["joined"]
    assert t["join"]["joined"][t["join"]["at"]:] == "suite du commentaire."


def test_join_point_after_a_cut_word():
    from review_turns import join_preview
    j = join_preview({"french_commentary": "toute sa posterité."}, {"french_commentary": "terité. Adam est roux."})
    assert j["mode"] == "hyphen" and j["joined"][j["at"]:] == "Adam est roux."


def test_turn_without_commentary(store):
    t = turn(store, VOL, 194, 195)
    assert t["b"]["note"] is None and t["join"] is None and t["proposal"] is None
    t = turn(store, VOL, 195, 196)
    assert t["b"] is None and t["join"] is None and t["proposal"] is None


def test_seam_proposal_repeat(store):
    edit(store, 193, lambda d: d["commentary"][0].update(french_commentary="Le nom de toute sa posterité."))
    edit(store, 194, lambda d: d["commentary"][0].update(french_commentary="terité. Adam signifie roux."))
    p = seam_proposal(store, VOL, 193, 194)
    assert p["id"].startswith("seam/22_proverbes/0193>0194/")
    assert p["sure"] is True
    assert p["options"][0]["changes"] == [
        {"vol": VOL, "page": 194, "path": ["commentary", 0, "french_commentary"],
         "old": "terité. Adam signifie roux.", "new": "Adam signifie roux."}]
    assert turn(store, VOL, 193, 194)["proposal"]["id"] == p["id"]


def test_repeat_gone(store):
    from review_turns import repeat_gone
    it = item("seam_repeat", 194, suffix="0193")
    assert repeat_gone(store, it) is True  # "…victimes." ‖ "suite du commentaire."
    edit(store, 194, lambda d: d["commentary"][0].update(french_commentary="de victimes. Et la suite."))
    assert repeat_gone(store, it) is False  # the last words come again overleaf
    edit(store, 194, lambda d: d["commentary"][0].update(french_commentary="times. Et la suite."))
    assert repeat_gone(store, it) is False  # the end of a word comes again
    assert repeat_gone(store, item("seam_missing", 194, suffix="0193")) is False  # only repeats are judged


def test_compound_joins():
    from calmet import infer_join, join_seam
    cases = [
        ("peut-", "on le faire ?", "peut-on le faire ?"),
        ("peut-", "être aussi", "peut-être aussi"),
        ("au-", "dessus de tout", "au-dessus de tout"),
        ("par-", "dessous la table", "par-dessous la table"),
        ("ci-", "après au chapitre", "ci-après au chapitre"),
        ("ci-", "devant mentionné", "ci-devant mentionné"),
        ("au-", "delà du fleuve", "au-delà du fleuve"),
        ("par-", "dedans la maison", "par-dedans la maison"),
        ("consolez-_", "_vous de sa mort_", "consolez-vous de sa mort_"),
    ]
    for tail, head, expected in cases:
        mode, stub = infer_join(tail, head)
        assert mode == "keep", f"Expected keep for {tail} + {head}, got {mode}"
        assert join_seam(tail, head, mode, stub) == expected
