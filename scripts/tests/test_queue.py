import json

import pytest

from review_store import (KIND_LABELS, Progress, counts, in_status, kind_category, load_queue,
                          neighbour_issue_pages, page_issues, select)

VOL = "22_proverbes"


@pytest.fixture
def docs(data_dir):
    return data_dir.parent / "docs"


@pytest.fixture
def progress(data_dir):
    return Progress(data_dir)


def items(docs, optional=False):
    return load_queue(docs / "review_queue.json", Progress(docs.parent / "data"), include_optional=optional)


def test_labels_and_categories():
    assert KIND_LABELS["hyphen_cut"].startswith("LEMMA / TRANSLATION CUT")
    assert kind_category("missing_footnote") == "footnotes"
    assert kind_category("missing_verse") == "verses"
    assert kind_category("hyphen_cut") == "commentary"


def test_load_queue_optional(docs):
    assert len(items(docs)) == 3
    assert len(items(docs, True)) == 4


def test_fp_added_back(docs):
    (docs.parent / "data" / VOL / "review.json").write_text(json.dumps({"false_positives":
        {"22_proverbes/0190/caps_in_commentary/eeee": {"book_dir": VOL, "page": 190, "kind": "caps_in_commentary",
                                                       "msg": "old"}}}), encoding="utf-8")
    added = [i for i in items(docs) if i["page"] == 190]
    assert added and added[0]["kind"] == "caps_in_commentary" and added[0]["msg"] == "old"


def test_progress_fp_sync(progress, data_dir):
    book = lambda: json.loads((data_dir / VOL / "review.json").read_text(encoding="utf-8"))
    i = "22_proverbes/0194/hyphen_cut/aaaa"
    progress.set(i, "false_positive", {"book_dir": VOL, "page": 194, "kind": "hyphen_cut", "msg": "m"})
    assert i in book()["false_positives"] and book()["status"][i] == "false_positive"
    progress.set(i, None)
    assert i not in book()["false_positives"] and progress.status(i) is None
    # a later Progress picks up false positives from the file
    progress.set(i, "false_positive", {})
    assert Progress(data_dir).status(i) == "false_positive"


def test_statuses_go_to_their_book(progress, data_dir):
    (data_dir / "27_isaie").mkdir()
    progress.update({f"{VOL}/0194/hyphen_cut/aaaa": "resolved", "27_isaie/0010/caps_in_commentary/bbbb": "skipped",
                     f"proposal:seam/{VOL}/0193>0194/cccc": "rejected"})
    mine = json.loads((data_dir / VOL / "review.json").read_text())["status"]
    assert set(mine) == {f"{VOL}/0194/hyphen_cut/aaaa", f"proposal:seam/{VOL}/0193>0194/cccc"}
    assert json.loads((data_dir / "27_isaie" / "review.json").read_text())["status"] == {
        "27_isaie/0010/caps_in_commentary/bbbb": "skipped"}


def test_todos_join_the_queue(docs, data_dir):
    td = {"id": f"{VOL}/0194/todo/dddd", "page": 194, "msg": "needs rescan", "where": None}
    (data_dir / VOL / "review.json").write_text(json.dumps({"todos": [td]}), encoding="utf-8")
    t = [i for i in items(docs) if i["kind"] == "todo"]
    assert t == [{"id": td["id"], "book_dir": VOL, "page": 194, "kind": "todo", "msg": "needs rescan", "optional": False}]


def test_absorb_legacy(data_dir, docs):
    from review_store import absorb_legacy
    (data_dir / ".review_queue_progress.json").write_text(json.dumps(
        {f"{VOL}/0194/hyphen_cut/aaaa": "resolved", f"{VOL}/0193/reported/5d41402a": "resolved"}))
    (docs / "false_positives.json").write_text(json.dumps({f"{VOL}/0195/caps_in_commentary/eeee": True}))
    (docs / "manual_issues.json").write_text(json.dumps([{"book_dir": VOL, "page": 193, "msg": "hello"}]))
    assert absorb_legacy(data_dir, docs)
    p = Progress(data_dir)
    assert p.status(f"{VOL}/0194/hyphen_cut/aaaa") == "resolved"
    assert p.status(f"{VOL}/0195/caps_in_commentary/eeee") == "false_positive"
    assert p.todos[VOL][0]["msg"] == "hello" and p.status(f"{VOL}/0193/todo/5d41402a") == "resolved"
    assert not (data_dir / ".review_queue_progress.json").exists() and not (docs / "manual_issues.json").exists()


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
    assert c["status"] == {"open": 2, "on_hold": 0, "false_positive": 0, "skipped": 0, "resolved": 1, "all": 3}
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


def test_every_kind_is_in_exactly_one_theme():
    from review_store import KIND_LABELS, KIND_THEMES
    listed = [k for _, kinds in KIND_THEMES for k in kinds]
    assert sorted(listed) == sorted(KIND_LABELS), (set(KIND_LABELS) ^ set(listed), [k for k in listed if listed.count(k) > 1])
