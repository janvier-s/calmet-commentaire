import json

import pytest

from review_store import (KIND_LABELS, Progress, counts, in_status, kind_category, load_queue,
                          neighbour_issue_pages, page_issues, select)

VOL = "22_proverbes"


@pytest.fixture
def docs(data_dir):
    return data_dir.parent / "docs"


@pytest.fixture
def progress(data_dir, docs):
    return Progress(data_dir / ".review_queue_progress.json", docs / "false_positives.json")


def items(docs, optional=False):
    return load_queue(docs / "review_queue.json", docs / "false_positives.json", include_optional=optional)


def test_labels_and_categories():
    assert KIND_LABELS["hyphen_cut"].startswith("LEMMA / TRANSLATION CUT")
    assert kind_category("missing_footnote") == "footnotes"
    assert kind_category("missing_verse") == "verses"
    assert kind_category("hyphen_cut") == "commentary"


def test_load_queue_optional(docs):
    assert len(items(docs)) == 3
    assert len(items(docs, True)) == 4


def test_fp_added_back(docs):
    (docs / "false_positives.json").write_text(json.dumps(
        {"22_proverbes/0190/caps_in_commentary/eeee": {"book_dir": VOL, "page": 190, "kind": "caps_in_commentary",
                                                       "msg": "old"}}), encoding="utf-8")
    added = [i for i in items(docs) if i["page"] == 190]
    assert added and added[0]["kind"] == "caps_in_commentary" and added[0]["msg"] == "old"


def test_progress_fp_sync(progress, docs, data_dir):
    fp = docs / "false_positives.json"
    i = "22_proverbes/0194/hyphen_cut/aaaa"
    progress.set(i, "false_positive", {"book_dir": VOL, "page": 194, "kind": "hyphen_cut", "msg": "m"})
    assert i in json.loads(fp.read_text(encoding="utf-8"))
    assert json.loads((data_dir / ".review_queue_progress.json").read_text())[i] == "false_positive"
    progress.set(i, None)
    assert i not in json.loads(fp.read_text(encoding="utf-8"))
    assert progress.status(i) is None
    # a later Progress picks up false positives from the file
    progress.set(i, "false_positive", {})
    assert Progress(data_dir / "other.json", fp).status(i) == "false_positive"


def test_select_open_excludes_skipped(docs, progress):
    its = items(docs)
    progress.set(its[0]["id"], "skipped")
    assert [i["id"] for i in select(its, progress, "open")] == [its[1]["id"], its[2]["id"]]
    assert [i["id"] for i in select(its, progress, "skipped")] == [its[0]["id"]]
    assert len(select(its, progress, "all")) == 3
    assert [i["kind"] for i in select(its, progress, "open", cat="footnotes")] == ["missing_footnote"]
    assert not in_status(its[0], progress, "open")


def test_counts_facets(docs, progress):
    its = items(docs)
    progress.set(its[0]["id"], "resolved")
    c = counts(its, progress, "open", None, None, None)
    assert c["status"] == {"open": 2, "false_positive": 0, "skipped": 0, "resolved": 1, "all": 3}
    assert c["cat"] == {"all": 2, "verses": 0, "commentary": 1, "footnotes": 1}
    assert c["kind"] == {"missing_footnote": 1, "missing_page": 1}
    assert c["book"] == {VOL: 2}
    # the other facets' filters apply: status counts within the footnotes category
    assert counts(its, progress, "open", "footnotes", None, None)["status"]["open"] == 1


def test_page_issues_status(docs, progress):
    its = items(docs)
    progress.set(its[0]["id"], "resolved")
    on = page_issues(its, progress, VOL, 194)
    assert [(i["kind"], i["status"]) for i in on] == [("hyphen_cut", "resolved"), ("missing_footnote", None)]


def test_neighbour_issue_pages(docs, progress):
    its = items(docs, True)
    assert neighbour_issue_pages(its, progress, VOL, 195) == {"prev": 194, "next": 196, "open_in_book": 4}
    progress.set(its[3]["id"], "resolved")
    assert neighbour_issue_pages(its, progress, VOL, 195)["next"] is None
