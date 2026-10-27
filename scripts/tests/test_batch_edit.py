"""Batch mode without proposals: mark many issues at once, and write text typed in the rows."""
import json
import threading
import urllib.error
import urllib.request

import pytest

from conftest import dump, reviews
from review_store import Store
from review_web import make_server

VOL = "22_proverbes"


def where(page, index, field, section="commentary"):
    return {"section": section, "index": index, "field": field}


QUEUE = [
    {"id": f"{VOL}/0193/lowercase_lemma/aa", "book_dir": VOL, "page": 193, "kind": "lowercase_lemma", "msg": "a",
     "optional": False, "where": where(193, 0, "latin_quote")},
    {"id": f"{VOL}/0193/long_translation/bb", "book_dir": VOL, "page": 193, "kind": "long_translation", "msg": "b",
     "optional": False, "where": where(193, 0, "french_translation")},
    {"id": f"{VOL}/0194/lowercase_lemma/cc", "book_dir": VOL, "page": 194, "kind": "lowercase_lemma", "msg": "c",
     "optional": False, "where": where(194, 1, "latin_quote")},
    {"id": f"{VOL}/0194/missing_footnote/dd", "book_dir": VOL, "page": 194, "kind": "missing_footnote", "msg": "d",
     "optional": False},
]


@pytest.fixture
def web(data_dir):
    docs = data_dir.parent / "docs"
    dump(docs / "review_queue.json", QUEUE)
    server, token = make_server(Store(data_dir, docs), docs / "review_queue.json", port=0)
    threading.Thread(target=server.serve_forever, args=(0.02,), daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def call(path, body=None):
        req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                     headers={"X-Token": token, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    call.data = data_dir
    yield call
    server.shutdown()


def page(web, n):
    return json.loads((web.data / VOL / "normalized" / f"page_{n:04d}.json").read_text(encoding="utf-8"))


def test_rows_say_which_are_editable(web):
    code, r = web(f"/api/batch?kind=lowercase_lemma&book={VOL}")
    assert code == 200 and [(x["page"], x["editable"], x["context"]) for x in r["rows"]] == [
        (193, True, "MELIOR EST BUCCELLA."), (194, True, "SERVUS SAPIENS DOMINABITUR FILIIS STULTIS.")]
    code, r = web(f"/api/batch?kind=missing_footnote&book={VOL}")
    assert r["rows"][0]["editable"] is False  # no field to point at


def test_mark_many_without_a_proposal(web):
    ids = [x["id"] for x in QUEUE[:3]]
    code, r = web("/api/batch/mark", {"ids": ids + ["nope"], "status": "resolved"})
    assert code == 200 and r["done"] == ids
    assert {i: reviews(web.data)[i] for i in ids} == {i: "resolved" for i in ids}
    code, r = web("/api/batch/mark", {"ids": ids[:1], "status": "false_positive"})
    assert reviews(web.data)[ids[0]] == "false_positive"
    assert web("/api/batch/mark", {"ids": ids, "status": "bogus"})[0] == 400
    assert page(web, 193)["commentary"][0]["latin_quote"] == "MELIOR EST BUCCELLA."  # no page touched


def test_edit_many_one_write_per_page(web):
    edits = [{"id": QUEUE[0]["id"], "was": "MELIOR EST BUCCELLA.", "text": "MELIOR EST BUCCELLA SICCA."},
             {"id": QUEUE[1]["id"], "was": "Un morceau de pain.", "text": "Un morceau de pain sec."},
             {"id": QUEUE[2]["id"], "was": "SERVUS SAPIENS DOMINABITUR FILIIS STULTIS.", "text": "SERVUS SAPIENS."}]
    code, r = web("/api/batch/edit", {"edits": edits})
    assert code == 200 and r["done"] == [e["id"] for e in edits] and r["failed"] == []
    assert r["texts"][QUEUE[1]["id"]] == "Un morceau de pain sec."
    c = page(web, 193)["commentary"][0]
    assert (c["latin_quote"], c["french_translation"]) == ("MELIOR EST BUCCELLA SICCA.", "Un morceau de pain sec.")
    assert page(web, 194)["commentary"][1]["latin_quote"] == "SERVUS SAPIENS."
    assert reviews(web.data) == {}  # editing does not validate: that is the next click


def test_edit_refuses_a_field_changed_since_the_table(web):
    edits = [{"id": QUEUE[0]["id"], "was": "something else", "text": "X."},
             {"id": QUEUE[2]["id"], "was": "SERVUS SAPIENS DOMINABITUR FILIIS STULTIS.", "text": "OK."}]
    code, r = web("/api/batch/edit", {"edits": edits})
    assert r["done"] == [QUEUE[2]["id"]] and [f["id"] for f in r["failed"]] == [QUEUE[0]["id"]]
    assert page(web, 193)["commentary"][0]["latin_quote"] == "MELIOR EST BUCCELLA."


def test_edit_refuses_an_issue_with_no_field(web):
    code, r = web("/api/batch/edit", {"edits": [{"id": QUEUE[3]["id"], "was": "", "text": "x"}]})
    assert r["done"] == [] and [f["id"] for f in r["failed"]] == [QUEUE[3]["id"]]
