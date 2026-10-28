import copy
import json
import shutil
import threading
import time
import urllib.request

import pytest

from conftest import QUEUE, reviews
from paths import DATA as REAL_DATA
from review_store import AUDIT_KINDS, Progress, Store, merge_recheck
from review_web import make_server

VOL = "22_proverbes"


@pytest.fixture
def progress(data_dir):
    return Progress(data_dir)


def test_audit_kinds():
    assert "lowercase_lemma" in AUDIT_KINDS and "hyphen_cut" in AUDIT_KINDS
    for k in ("reported", "psalm_number", "hebrew_recheck", "latin_long_s", "seam_missing", "chapter_vulgate"):
        assert k not in AUDIT_KINDS


def test_merge_fixed_and_added(progress):
    items = copy.deepcopy(QUEUE)
    new = [dict(QUEUE[0], where={"section": "commentary", "index": 1, "field": "latin_quote"}),
           {"id": "22_proverbes/0195/lowercase_lemma/eeee", "book_dir": VOL, "page": 195, "kind": "lowercase_lemma",
            "msg": "lower case", "optional": False}]
    r = merge_recheck(items, progress, [VOL], new)
    assert sorted(r["fixed"]) == sorted(it["id"] for it in QUEUE[1:])
    assert r["added"] == ["22_proverbes/0195/lowercase_lemma/eeee"]
    assert all(progress.status(i) == "resolved" for i in r["fixed"])
    assert [it.get("fixed") for it in items[:4]] == [None, True, True, True]
    assert items[0]["where"]["field"] == "latin_quote"  # refreshed
    assert items[-1]["kind"] == "lowercase_lemma"


def test_merge_keeps_marked(progress):
    items = copy.deepcopy(QUEUE)
    progress.set(QUEUE[1]["id"], "false_positive", {})
    progress.set(QUEUE[0]["id"], "skipped")
    r = merge_recheck(items, progress, [VOL], [QUEUE[0]])
    assert QUEUE[1]["id"] not in r["fixed"]
    assert progress.status(QUEUE[1]["id"]) == "false_positive"
    assert progress.status(QUEUE[0]["id"]) == "skipped"


def test_merge_reopens_what_comes_back(progress):
    items = copy.deepcopy(QUEUE)
    merge_recheck(items, progress, [VOL], [])
    assert progress.status(QUEUE[0]["id"]) == "resolved"
    merge_recheck(items, progress, [VOL], [QUEUE[0]])
    assert progress.status(QUEUE[0]["id"]) is None and not items[0].get("fixed")


def test_merge_skips_optional_when_asked(progress):
    items = []
    r = merge_recheck(items, progress, [VOL], [QUEUE[2]], include_optional=False)
    assert r["added"] == [] and items == []


def test_merge_only_this_book(progress):
    other = {"id": "01_genese/0010/hyphen_cut/ffff", "book_dir": "01_genese", "page": 10, "kind": "hyphen_cut",
             "msg": "x", "optional": False}
    items = copy.deepcopy(QUEUE) + [other]
    r = merge_recheck(items, progress, [VOL], [])
    assert other["id"] not in r["fixed"] and progress.status(other["id"]) is None


def test_merge_leaves_other_kinds(progress):
    reported = {"id": "22_proverbes/0194/reported/gggg", "book_dir": VOL, "page": 194, "kind": "reported",
                "msg": "by hand", "optional": False}
    items = copy.deepcopy(QUEUE) + [reported]
    assert reported["id"] not in merge_recheck(items, progress, [VOL], [])["fixed"]


def server(data_dir, recheck):
    docs = data_dir.parent / "docs"
    srv, token = make_server(Store(data_dir, docs), docs / "review_queue.json", port=0, recheck=recheck)
    threading.Thread(target=srv.serve_forever, args=(0.02,), daemon=True).start()

    def post(path, body):
        req = urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}{path}", data=json.dumps(body).encode(),
                                     headers={"X-Token": token, "Content-Type": "application/json"})
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    return srv, post


def test_recheck_endpoint(data_dir):
    srv, post = server(data_dir, lambda vol: [q for q in QUEUE if q["kind"] != "missing_footnote"])
    try:
        r = post("/api/recheck", {"vol": VOL, "page": 194})
        # missing_footnote goes; the optional seam_artifact stays out (the server was started without --all)
        assert r["fixed"] == 1 and r["added"] == 0
        on_page = {i["kind"]: i for i in r["issues"]}
        assert on_page["missing_footnote"]["fixed"] is True
        assert reviews(data_dir)["22_proverbes/0194/missing_footnote/bbbb"] == "resolved"
    finally:
        srv.shutdown()


def test_recheck_serialized(data_dir):
    running, overlap = [0], [False]

    def slow(vol):
        running[0] += 1
        overlap[0] |= running[0] > 1
        time.sleep(0.2)
        running[0] -= 1
        return list(QUEUE)
    srv, post = server(data_dir, slow)
    try:
        ts = [threading.Thread(target=post, args=("/api/recheck", {"vol": VOL, "page": 194})) for _ in range(2)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        assert not overlap[0]
    finally:
        srv.shutdown()


@pytest.mark.skipif(not (REAL_DATA / VOL / "normalized").is_dir(), reason="no real data")
def test_recheck_sees_fresh_page(tmp_path, monkeypatch):
    import audit_integrity
    import paths
    from page_audit import recheck_book
    shutil.copytree(REAL_DATA / VOL / "normalized", tmp_path / VOL / "normalized")
    monkeypatch.setattr(paths, "DATA", tmp_path)
    monkeypatch.setattr(audit_integrity, "STUDIUM", tmp_path)
    recheck_book(VOL)
    for f in sorted((tmp_path / VOL / "normalized").glob("page_*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        lemma = next((c for c in d.get("commentary") or [] if (c.get("latin_quote") or "").strip()), None)
        if lemma:
            lemma["latin_quote"] = "ZZQ fresh test " + lemma["latin_quote"]
            f.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
            page = int(f.stem[5:9])
            break
    after = recheck_book(VOL)
    assert any(i["kind"] == "lowercase_lemma" and i["page"] == page and "ZZQ fresh test" in i["msg"] for i in after)


# --- from the branch review ---

def test_merge_optional_still_produced_is_not_fixed(progress):
    item = dict(QUEUE[2], optional=False)  # an optional kind, loaded from the false positives as required
    items = [item]
    r = merge_recheck(items, progress, [VOL], [QUEUE[2]], include_optional=False)
    assert r["fixed"] == [] and progress.status(item["id"]) is None


def test_merge_leaves_unreadable_pages_alone(progress):
    items = copy.deepcopy(QUEUE)
    malformed = {"id": "22_proverbes/0194/malformed_page/hhhh", "book_dir": VOL, "page": 194, "kind": "malformed_page",
                 "msg": "malformed", "optional": False}
    r = merge_recheck(items, progress, [VOL], [malformed])
    assert not any(i.startswith("22_proverbes/0194/hyphen_cut") or i.startswith("22_proverbes/0194/missing_footnote")
                   for i in r["fixed"])
    assert progress.status("22_proverbes/0194/hyphen_cut/aaaa") is None


def test_progress_update_writes_once_and_atomically(progress, data_dir, monkeypatch):
    writes = []
    import review_store
    real = review_store.os.replace
    monkeypatch.setattr(review_store.os, "replace", lambda a, b: (writes.append(str(b)), real(a, b)))
    a, b, c = (f"{VOL}/0194/hyphen_cut/{x}" for x in "abc")
    progress.update({a: "resolved", b: "resolved", c: None})
    assert sum(w.endswith("review.json") for w in writes) == 1
    assert reviews(data_dir) == {a: "resolved", b: "resolved"}


def test_mark_does_not_wait_for_a_running_audit(data_dir):
    """The audit runs outside the lock marks take; its merge, under the lock, respects what was marked meanwhile."""
    order = []

    def slow(vol):
        order.append("audit start")
        time.sleep(0.3)
        order.append("audit end")
        return [q for q in QUEUE if q["id"] != QUEUE[1]["id"]]  # the audit no longer finds the second issue
    srv, post = server(data_dir, slow)
    try:
        t = threading.Thread(target=post, args=("/api/recheck", {"vol": VOL, "page": 194}))
        t.start()
        time.sleep(0.1)
        post("/api/mark", {"id": QUEUE[0]["id"], "status": "resolved"})
        post("/api/mark", {"id": QUEUE[1]["id"], "status": "false_positive"})
        order.append("marked")
        t.join()
        assert order == ["audit start", "marked", "audit end"]
        assert reviews(data_dir)[QUEUE[0]["id"]] == "resolved"
        assert reviews(data_dir)[QUEUE[1]["id"]] == "false_positive"  # not turned into "fixed" by the merge
    finally:
        srv.shutdown()


def test_recheck_not_audited_changes_nothing(data_dir):
    srv, post = server(data_dir, lambda vol: None)  # a book the full audit leaves out
    try:
        r = post("/api/recheck", {"vol": VOL, "page": 194})
        assert r["fixed"] == 0 and r["added"] == 0
        assert "resolved" not in reviews(data_dir).values()
    finally:
        srv.shutdown()


@pytest.mark.skipif(not (REAL_DATA / "47_matthieu" / "normalized").is_dir(), reason="no real data")
def test_recheck_book_covers_every_book():
    from page_audit import recheck_book
    assert isinstance(recheck_book("47_matthieu"), list)


@pytest.mark.skipif(not (REAL_DATA / VOL / "normalized").is_dir(), reason="no real data")
def test_recheck_reloads_false_positives(tmp_path, monkeypatch):
    import audit_integrity
    import paths
    from page_audit import recheck_book
    shutil.copytree(REAL_DATA / VOL / "normalized", tmp_path / VOL / "normalized")
    monkeypatch.setattr(paths, "DATA", tmp_path)
    monkeypatch.setattr(audit_integrity, "STUDIUM", tmp_path)
    monkeypatch.setattr(audit_integrity, "FP_IDS", {"stale"})
    monkeypatch.setattr(audit_integrity, "load_false_positives", lambda: {"fresh"})
    recheck_book(VOL)
    assert audit_integrity.FP_IDS == {"fresh"}


def test_recheck_returns_the_other_page_of_a_turn(data_dir):
    srv, post = server(data_dir, lambda vol: list(QUEUE))
    try:
        r = post("/api/recheck", {"vol": VOL, "page": 193, "also": [194]})
        assert {i["page"] for i in r["issues"]} == {194}
        assert r["around"]["next"] == 194
    finally:
        srv.shutdown()
