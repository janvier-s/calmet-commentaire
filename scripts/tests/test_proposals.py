import json

import pytest

from conftest import dump
from review_proposals import apply, generated_items, proposal_for
from review_store import AUDIT_KINDS, Conflict, Progress, Store, merge_recheck

VOL = "22_proverbes"


@pytest.fixture
def store(data_dir):
    docs = data_dir.parent / "docs"
    dump(docs / "footnotes" / f"{VOL}.json", {"summary": {}, "notes": [
        {"id": "0194(a)", "page": "page_0194", "marker": "(a)", "text": "Prov. 17. 2.",
         "proposed": "Proverbes 17:2.", "why": ["abbreviations written out"], "flags": ["uncertain"]},
        {"id": "0193(a)", "page": "page_0193", "marker": "(a)", "text": "Gone. 1.",
         "proposed": "Genèse 1.", "why": [], "flags": []},
        {"id": "0194(b)", "page": "page_0194", "marker": "(b)", "text": "Same.", "proposed": "Same.",
         "why": [], "flags": ["greek"]}]})
    dump(docs / "ref_check.json", {"stats": {}, "items": [
        {"where": f"{VOL}/page_0194", "field": "commentary[0].french_commentary", "kind": "missing",
         "ref": "x", "written": "commentaire", "context": "suite du commentaire.", "quote": "", "vulgate": "",
         "candidates": [["texte", "", None], ["propos", "", None]], "fix": None}]})
    return Store(data_dir, docs)


@pytest.fixture
def progress(data_dir):
    return Progress(data_dir / ".review_queue_progress.json", data_dir.parent / "docs" / "false_positives.json")


def by_kind(items, kind):
    return [it for it in items if it["kind"] == kind]


def test_footnote_items(store):
    items = by_kind(generated_items(store), "footnote_writeout")
    assert len(items) == 1
    it = items[0]
    assert it["page"] == 194 and it["book_dir"] == VOL and it["id"].startswith(f"{VOL}/0194/footnote_writeout/")
    p = it["proposal"]
    assert p["item"] == it["id"] and p["flags"] == ["uncertain"]
    assert p["options"][0]["changes"] == [{"vol": VOL, "page": 194, "path": ["footnotes", 0, "text"],
                                           "old": "Prov. 17. 2.", "new": "Proverbes 17:2."}]


def test_ref_candidate_items(store):
    [it] = by_kind(generated_items(store), "ref_candidate")
    opts = it["proposal"]["options"]
    assert [o["label"] for o in opts] == ["texte", "propos"]
    assert opts[0]["changes"][0]["new"] == "suite du texte."
    assert opts[0]["changes"][0]["path"] == ["commentary", 0, "french_commentary"]


def test_apply_writes_and_versions(store):
    [it] = by_kind(generated_items(store), "footnote_writeout")
    r = apply(store, it["proposal"])
    data, version = store.read(VOL, 194)
    assert data["footnotes"][0]["text"] == "Proverbes 17:2."
    assert r["pages"][194]["version"] == version


def test_apply_refuses_changed_text(store):
    [it] = by_kind(generated_items(store), "footnote_writeout")
    d, _ = store.read(VOL, 194)
    d["footnotes"][0]["text"] = "Typed by hand."
    store.path(VOL, 194).write_text(json.dumps(d), encoding="utf-8")
    before = store.path(VOL, 194).read_text(encoding="utf-8")
    with pytest.raises(Conflict):
        apply(store, it["proposal"])
    assert store.path(VOL, 194).read_text(encoding="utf-8") == before


def test_apply_edited(store):
    [it] = by_kind(generated_items(store), "footnote_writeout")
    apply(store, it["proposal"], edited=["Proverbes 17:2 et suiv."])
    assert store.read(VOL, 194)[0]["footnotes"][0]["text"] == "Proverbes 17:2 et suiv."


def test_apply_second_option(store):
    [it] = by_kind(generated_items(store), "ref_candidate")
    apply(store, it["proposal"], option=1)
    assert store.read(VOL, 194)[0]["commentary"][0]["french_commentary"] == "suite du propos."


def test_rejected_seam_proposal_hidden(store, progress):
    def put(page, text):
        d, _ = store.read(VOL, page)
        d["commentary"][0]["french_commentary"] = text
        store.path(VOL, page).write_text(json.dumps(d), encoding="utf-8")
    put(193, "Le nom de toute sa posterité.")
    put(194, "terité. Adam signifie roux.")
    it = {"id": f"{VOL}/0194/seam_artifact/x", "book_dir": VOL, "page": 194, "kind": "seam_artifact", "msg": ""}
    p = proposal_for(store, progress, it)
    assert p and p["item"] == it["id"]
    progress.set("proposal:" + p["id"], "rejected")
    assert proposal_for(store, progress, it) is None


def test_generated_kinds_not_audit_kinds(store, progress):
    assert "footnote_writeout" not in AUDIT_KINDS and "ref_candidate" not in AUDIT_KINDS
    items = generated_items(store)
    merge_recheck(items, progress, [VOL], [])
    assert all(progress.status(it["id"]) is None for it in items)


def test_footnote_without_marker_and_malformed_page(store):
    d, _ = store.read(VOL, 194)
    d["footnotes"][0]["marker"] = None
    store.path(VOL, 194).write_text(json.dumps(d), encoding="utf-8")
    store.path(VOL, 193).write_text("{ not json", encoding="utf-8")
    report = store.docs / "footnotes" / f"{VOL}.json"
    r = json.loads(report.read_text(encoding="utf-8"))
    r["notes"][0]["marker"] = None
    r["notes"][1]["text"] = "x"  # page 193 is now unreadable
    report.write_text(json.dumps(r), encoding="utf-8")
    [it] = by_kind(generated_items(store), "footnote_writeout")
    assert it["page"] == 194
