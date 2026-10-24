import json
import threading
import urllib.error
import urllib.request

import pytest

from review_store import Store
from review_web import make_server

VOL = "22_proverbes"


@pytest.fixture
def web(data_dir):
    docs = data_dir.parent / "docs"
    server, token = make_server(Store(data_dir, docs), docs / "review_queue.json", port=0)
    threading.Thread(target=server.serve_forever, args=(0.02,), daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def call(path, body=None, token=token, raw=False):
        req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                     headers={"X-Token": token, "Content-Type": "application/json"} if token else {})
        try:
            with urllib.request.urlopen(req) as r:
                data = r.read()
                return r.status, (data if raw else json.loads(data))
        except urllib.error.HTTPError as e:
            data = e.read()
            return e.code, (data if raw else (json.loads(data) if data.startswith(b"{") else data))

    call.data = data_dir
    yield call
    server.shutdown()


def test_token_required(web):
    assert web("/api/config", token=None)[0] == 403
    assert web("/api/config", token="wrong")[0] == 403
    assert web(f"/scan/{VOL}/194", token=None, raw=True)[0] == 403


def test_config(web):
    code, c = web("/api/config")
    assert code == 200 and c["volumes"] == [VOL] and "hyphen_cut" in c["labels"]


def test_get_page(web):
    code, p = web(f"/api/page?vol={VOL}&page=194")
    assert code == 200
    assert p["context"]["prev"]["page"] == 193 and p["scan"] is True
    assert [i["kind"] for i in p["issues"]] == ["hyphen_cut", "missing_footnote"]
    assert p["around"]["open_in_book"] == 3 and p["pages"] == [193, 194, 195]


def test_missing_page_then_create(web):
    code, p = web(f"/api/page?vol={VOL}&page=196")
    assert code == 404 and p["missing"] is True and p["scan"] is True
    code, p = web("/api/page/create", {"vol": VOL, "page": 196})
    assert code == 200 and p["data"]["verses"] == []


def test_save_and_conflict(web):
    _, p = web(f"/api/page?vol={VOL}&page=194")
    p["data"]["footnotes"][0]["text"] = "Prov. 17. 2. corrigé"
    code, saved = web("/api/page", {"vol": VOL, "page": 194, "data": p["data"], "version": p["version"]})
    assert code == 200 and saved["data"]["footnotes"][0]["text"] == "Prov. 17. 2. corrigé"
    code, c = web("/api/page", {"vol": VOL, "page": 194, "data": p["data"], "version": p["version"]})
    assert code == 409 and c["disk"]["footnotes"][0]["text"] == "Prov. 17. 2. corrigé" and c["version"] == saved["version"]


def test_op_add_commentary_top(web):
    _, p = web(f"/api/page?vol={VOL}&page=194")
    code, out = web("/api/op", {"vol": VOL, "page": 194, "data": p["data"], "version": p["version"],
                                "op": {"op": "add_commentary", "after": None}})
    assert code == 200
    first = out["data"]["commentary"][0]
    assert (first["chapter"], first["verse_ref"], first["commentary_id"]) == (17, 1, 1)
    assert len(out["data"]["commentary"]) == 3


def test_locate(web):
    assert web(f"/api/locate?vol={VOL}&ref=17:2") == (200, {"page": 194})
    assert web(f"/api/locate?vol={VOL}&ref=17") == (200, {"page": 193})
    assert web(f"/api/locate?vol={VOL}&ref=40:1")[0] == 404


def test_queue_counts(web):
    code, q = web("/api/queue?status=open")
    assert code == 200 and len(q["items"]) == 3
    assert q["counts"]["status"]["open"] == 3
    code, q = web(f"/api/queue?status=open&cat=footnotes&book={VOL}")
    assert [i["kind"] for i in q["items"]] == ["missing_footnote"]


def test_mark_does_not_save_page(web):
    f = web.data / VOL / "normalized" / "page_0194.json"
    before = f.stat().st_mtime_ns
    assert web("/api/mark", {"id": "22_proverbes/0194/hyphen_cut/aaaa", "status": "resolved"})[0] == 200
    assert f.stat().st_mtime_ns == before
    _, q = web("/api/queue?status=resolved")
    assert [i["id"] for i in q["items"]] == ["22_proverbes/0194/hyphen_cut/aaaa"]


def test_italics(web):
    assert web("/api/italics", {"text": "un mot ici", "start": 3, "end": 6}) == (
        200, {"text": "un _mot_ ici", "start": 4, "end": 7})


def test_scan(web):
    code, body = web(f"/scan/{VOL}/194", raw=True)
    assert code == 200 and body.startswith(b"\x89PNG")
    assert web(f"/scan/{VOL}/193", raw=True)[0] == 404


def test_path_traversal(web):
    assert web("/scan/../x/1", raw=True)[0] == 404
    assert web("/static/../review_store.py", raw=True)[0] == 404
    assert web("/static/%2e%2e/review_store.py", raw=True)[0] == 404


def test_flag(web):
    code, r = web("/api/flag", {"vol": VOL, "page": 194})
    assert code == 200 and (web.data / VOL / "modernization_error" / "page_0194.png").exists()


def test_state(web):
    assert web("/api/state", {"vol": VOL, "page": 195})[0] == 200
    assert web("/api/state")[1] == {"vol": VOL, "page": 195}


def test_page_defaults_to_first(web):
    code, p = web(f"/api/page?vol={VOL}")
    assert code == 200 and p["page"] == 193


def test_save_and_op_on_missing_page_refused(web):
    _, p = web(f"/api/page?vol={VOL}&page=193")
    body = {"vol": VOL, "page": 196, "data": p["data"], "version": p["version"]}
    assert web("/api/page", body)[0] == 404
    assert web("/api/op", dict(body, op={"op": "add_footnote", "marker": "z"}))[0] == 404
    assert not (web.data / VOL / "normalized" / "page_0196.json").exists()


def test_post_needs_a_page(web):
    _, p = web(f"/api/page?vol={VOL}&page=193")
    assert web("/api/page", {"vol": VOL, "data": p["data"], "version": p["version"]})[0] == 400
    assert web("/api/page", {"vol": VOL, "page": -1, "data": p["data"], "version": p["version"]})[0] == 400
