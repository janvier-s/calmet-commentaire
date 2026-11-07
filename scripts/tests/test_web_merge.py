import json
import threading
import urllib.error
import urllib.request

import pytest

from review_store import Store
from review_web import make_server
from test_merge_view import make_units


@pytest.fixture
def web(data_dir):
    make_units(data_dir)
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


def test_merge_requires_key(web):
    assert web("/api/merge/list?vol=22_proverbes", token=None)[0] == 403
    assert web("/merge", token=None, raw=True)[0] == 403


def test_merge_page(web):
    code, body = web("/merge", raw=True)
    assert code == 200 and b"merge_main.js" in body


def test_merge_list_and_unit(web):
    code, l = web("/api/merge/list?vol=22_proverbes")
    assert code == 200 and l["unattached"] == 1 and l["status_order"][0] == "substantive"
    assert [r["uid"] for r in l["rows"]][0] == "commentary:17:2:0"
    code, u = web("/api/merge/unit?vol=22_proverbes&uid=commentary:17:2:0")
    assert code == 200 and u["unplaced"] == ["c3"]


def test_merge_errors(web):
    assert web("/api/merge/list?vol=nope")[0] == 404
    assert web("/api/merge/unit?vol=22_proverbes&uid=nope")[0] == 404
    assert web("/api/merge/scanwords?vol=22_proverbes&page=x&path=a&at=0&n=1")[0] == 400


def test_merge_vols(web):
    assert web("/api/merge/vols")[1]["vols"][0]["vol"] == "22_proverbes"
