import json

import merge_build
import merge_decisions
import merged_hand as mh
from review_store import Store
from test_merge_view import make_units

VOL, T2 = "22_proverbes", "commentary/1/french_commentary"


def setup(data_dir):
    make_units(data_dir)
    docs = data_dir.parent / "docs"
    return Store(data_dir, docs), docs


def build(store, docs, pages=None):
    import merge_view
    doc = merge_view.load(store.data, VOL, docs)
    return merge_build.build_pages(store, VOL, doc, merge_decisions.load(docs, VOL), pages)


def merged(data_dir, page=194):
    return json.loads((data_dir / VOL / "merged" / f"page_{page:04d}.json").read_text())


def test_edit_kept_on_rebuild(data_dir):
    store, docs = setup(data_dir)
    build(store, docs)
    built = merged(data_dir)["commentary"][1]["french_commentary"]
    rec = mh.edit(docs, VOL, 194, T2, built, "Un serviteur sage.")
    assert rec["base"] == merge_build.field_hash(built) and rec["built"] == built
    r = build(store, docs)
    assert merged(data_dir)["commentary"][1]["french_commentary"] == "Un serviteur sage."
    assert r["conflicts"] == []


def test_back_to_built_drops_the_edit_but_keeps_its_version(data_dir):
    store, docs = setup(data_dir)
    build(store, docs)
    built = merged(data_dir)["commentary"][1]["french_commentary"]
    mh.edit(docs, VOL, 194, T2, built, "Un serviteur sage.")
    rec = mh.edit(docs, VOL, 194, T2, built, built)
    assert rec["text"] is None and rec["versions"][-1]["text"] == "Un serviteur sage."
    build(store, docs)
    assert merged(data_dir)["commentary"][1]["french_commentary"] == built


def test_normalized_changed_underneath_is_flagged_never_overwritten(data_dir):
    store, docs = setup(data_dir)
    build(store, docs)
    built = merged(data_dir)["commentary"][1]["french_commentary"]
    mh.edit(docs, VOL, 194, T2, built, "Un serviteur sage.")
    d, v = store.read(VOL, 194)
    d["commentary"][1]["french_commentary"] = d["commentary"][1]["french_commentary"].replace("esclave", "serf")
    store.save(VOL, 194, d, v)
    r = build(store, docs)
    assert merged(data_dir)["commentary"][1]["french_commentary"] == "Un serviteur sage."
    [c] = r["conflicts"]
    assert (c["page"], c["path"]) == (194, T2) and "serf" in c["built"] and c["was"] == built
    rec = mh.load(docs, VOL)["fields"][mh.key(194, T2)]
    assert rec["conflict"]["built"] == c["built"]
    # kept mine: no more conflict, the new built text is the base
    mh.resolve(docs, VOL, 194, T2, "mine", c["built"])
    r = build(store, docs)
    assert r["conflicts"] == [] and merged(data_dir)["commentary"][1]["french_commentary"] == "Un serviteur sage."


def test_resolve_theirs_takes_the_rebuilt_text_and_undo_brings_mine_back(data_dir):
    store, docs = setup(data_dir)
    build(store, docs)
    built = merged(data_dir)["commentary"][1]["french_commentary"]
    mh.edit(docs, VOL, 194, T2, built, "Un serviteur sage.")
    d, v = store.read(VOL, 194)
    d["commentary"][1]["french_commentary"] = d["commentary"][1]["french_commentary"].replace("esclave", "serf")
    store.save(VOL, 194, d, v)
    new = build(store, docs)["conflicts"][0]["built"]
    mh.resolve(docs, VOL, 194, T2, "theirs", new)
    build(store, docs)
    assert merged(data_dir)["commentary"][1]["french_commentary"] == new
    mh.restore(docs, VOL, 194, T2)  # undo: the last version back
    r = build(store, docs)
    assert merged(data_dir)["commentary"][1]["french_commentary"] == "Un serviteur sage."
    assert len(r["conflicts"]) == 1  # made on the old built text: flagged again


def test_versions_and_restore(data_dir):
    store, docs = setup(data_dir)
    build(store, docs)
    built = merged(data_dir)["commentary"][1]["french_commentary"]
    mh.edit(docs, VOL, 194, T2, built, "one")
    mh.edit(docs, VOL, 194, T2, built, "two")
    rec = mh.restore(docs, VOL, 194, T2)
    assert rec["text"] == "one"
    assert [x["text"] for x in rec["versions"]] == [None, "one", "two"]  # nothing is lost: undo is undoable
    rec = mh.restore(docs, VOL, 194, T2, 0)
    assert rec["text"] is None


def test_field_gone_is_flagged_and_kept(data_dir):
    store, docs = setup(data_dir)
    build(store, docs)
    mh.edit(docs, VOL, 194, "commentary/9/french_commentary", "x", "y")
    r = build(store, docs)
    assert r["conflicts"] == [{"page": 194, "path": "commentary/9/french_commentary", "why": "gone",
                               "built": None, "was": "x", "text": "y"}]
    assert mh.key(194, "commentary/9/french_commentary") in mh.load(docs, VOL)["fields"]


def test_rebuild_of_one_page_keeps_the_other_pages_flags(data_dir):
    store, docs = setup(data_dir)
    build(store, docs)
    mh.edit(docs, VOL, 194, "commentary/9/french_commentary", "x", "y")
    build(store, docs)
    build(store, docs, [195])
    assert mh.load(docs, VOL)["fields"][mh.key(194, "commentary/9/french_commentary")]["conflict"]


def test_typing_in_a_flagged_field_keeps_the_flag(data_dir):
    store, docs = setup(data_dir)
    build(store, docs)
    built = merged(data_dir)["commentary"][1]["french_commentary"]
    mh.edit(docs, VOL, 194, T2, built, "Un serviteur sage.")
    d, v = store.read(VOL, 194)
    d["commentary"][1]["french_commentary"] = "Autre."
    store.save(VOL, 194, d, v)
    new = build(store, docs)["conflicts"][0]["built"]
    rec = mh.edit(docs, VOL, 194, T2, new, "Un serviteur très sage.")
    assert rec["conflict"] and rec["built"] == built
    assert build(store, docs)["conflicts"][0]["text"] == "Un serviteur très sage."


def test_store_save_listeners(data_dir):
    store, docs = setup(data_dir)
    seen = []
    store.saved.append(lambda vol, page: seen.append((vol, page)))
    d, v = store.read(VOL, 194)
    store.save(VOL, 194, d, v)
    assert seen == [(VOL, 194)]
