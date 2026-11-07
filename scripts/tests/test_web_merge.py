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
    assert code == 200 and [k.split("@")[0] for k in u["unplaced"]] == ["c3"]


def test_merge_errors(web):
    assert web("/api/merge/list?vol=nope")[0] == 404
    assert web("/api/merge/unit?vol=22_proverbes&uid=nope")[0] == 404
    assert web("/api/merge/scanwords?vol=22_proverbes&page=x&path=a&at=0&n=1")[0] == 400


def test_merge_vols(web):
    assert web("/api/merge/vols")[1]["vols"][0]["vol"] == "22_proverbes"


def test_api_printed(web):
    st, r = web("/api/printed", {"words": [{"pt": "l’"}, {"pt": "Homme"}, {"pt": "&"}, {"pt": "Terre."}]})
    assert st == 200 and r == {"text": "l'Homme et Terre.", "flags": []}
    assert web("/api/printed", {"words": []}, token=None)[0] == 403
    assert web("/api/printed", {"words": "x"})[0] == 400
    assert web("/api/printed", {"words": [{"pt": "Deus"}, {"pt": "&"}], "latin": True})[1]["text"] == "Deus &"


UID = "commentary:17:2:0"


def keys(web):
    _, u = web(f"/api/merge/unit?vol=22_proverbes&uid={UID}")
    return {c["id"]: c["key"] for c in u["changes"]}


def test_decide_then_unit_shows_it(web):
    k = keys(web)
    st, r = web("/api/merge/decide", {"vol": "22_proverbes", "uid": UID, "key": k["c1"], "choice": "good"})
    assert st == 200 and r["decision"]["choice"] == "good" and r["progress"]["todo"] == 2
    _, u = web(f"/api/merge/unit?vol=22_proverbes&uid={UID}")
    assert {c["id"]: c["decision"]["choice"] for c in u["changes"]} == {"c1": "good", "c2": None, "c3": None}
    assert u["progress"]["decided"] == 1
    assert (web.data.parent / "docs" / "good_merge" / "22_proverbes.json").exists()


def test_marks_finish_a_unit_and_export_gold(web):
    k = keys(web)
    web("/api/merge/decide", {"vol": "22_proverbes", "uid": UID, "key": k["c1"], "choice": "edit", "text": "prudent."})
    web("/api/merge/mark", {"vol": "22_proverbes", "uid": UID, "key": k["c2"], "label": "noise"})
    st, r = web("/api/merge/mark", {"vol": "22_proverbes", "uid": UID, "key": k["c3"], "label": "noise"})
    assert st == 200 and r["progress"]["done"] is True
    _, l = web("/api/merge/list?vol=22_proverbes")
    assert l["rows"][0]["progress"]["done"] is True
    gold = json.loads((web.data / "good_variants_gold" / "22_proverbes_merge.json").read_text(encoding="utf-8"))
    assert [i["label"] for i in gold["items"]] == ["noise", "noise"]


def test_unit_decision_for_a_one_sided_unit(web):
    st, r = web("/api/merge/decide", {"vol": "22_proverbes", "uid": "verse:17:4:0", "key": None, "choice": "keep"})
    assert st == 200 and r["progress"]["done"] is True
    _, u = web("/api/merge/unit?vol=22_proverbes&uid=verse:17:4:0")
    assert u["unit_decision"] == "keep"


def test_decide_errors(web):
    k = keys(web)
    base = {"vol": "22_proverbes", "uid": UID}
    assert web("/api/merge/decide", {**base, "key": k["c1"], "choice": "maybe"})[0] == 400
    assert web("/api/merge/decide", {**base, "key": k["c1"], "choice": "edit"})[0] == 400
    assert web("/api/merge/decide", {**base, "key": "nope@1:x:0", "choice": "good"})[0] == 404
    assert web("/api/merge/decide", {**base, "uid": "nope", "key": k["c1"], "choice": "good"})[0] == 404
    assert web("/api/merge/mark", {**base, "key": k["c1"], "label": "maybe"})[0] == 400
    assert web("/api/merge/decide", {**base, "key": k["c1"], "choice": "good"}, token=None)[0] == 403


T2 = "commentary/1/french_commentary"


def test_merge_edit_free_and_on_change(web):
    base = {"vol": "22_proverbes", "uid": UID}
    # plain text: "de la" (17..22) -> "de toute la"
    code, r = web("/api/merge/edit", {**base, "page": 194, "path": T2, "a": 16, "b": 22, "text": " de toute la"})
    assert code == 200, r
    dec = json.loads((web.data.parent / "docs" / "good_merge" / "22_proverbes.json").read_text())["decisions"]
    rec = next(v for k, v in dec.items() if k.startswith("edit@"))
    assert (rec["old"], rec["text"]) == ("de", "de toute")
    merged = json.loads((web.data / "22_proverbes" / "merged" / "page_0194.json").read_text())
    assert merged["commentary"][1]["french_commentary"] == "Un esclave qui a de toute la sagesse ^{(a)}."
    assert any(s["kind"] == "edit" for s in r["view"]["merged"])
    # inside the change on "sagesse": an edit decision on it
    seg = next(s for s in r["view"]["merged"] if s.get("id", "").startswith("c2@"))
    code, r = web("/api/merge/edit", {**base, "page": 194, "path": T2, "a": seg["a"], "b": seg["b"],
                              "text": " savoir ^{(a)}."})
    assert code == 200, r
    seg = next(s for s in r["view"]["merged"] if s.get("id", "").startswith("c2@"))
    assert seg["choice"] == "edit" and seg["t"] == " savoir ^{(a)}."
    merged = json.loads((web.data / "22_proverbes" / "merged" / "page_0194.json").read_text())
    assert merged["commentary"][1]["french_commentary"] == "Un esclave qui a de toute la savoir ^{(a)}."


def test_merge_edit_errors(web):
    base = {"vol": "22_proverbes", "uid": UID}
    assert web("/api/merge/edit", {**base, "page": 194, "path": T2, "a": 5, "b": 2, "text": "x"})[0] == 400
    assert web("/api/merge/edit", {**base, "page": 999, "path": T2, "a": 0, "b": 1, "text": "x"})[0] == 400


def test_merge_decide_rebuilds_page(web):
    k = keys(web)
    code, _ = web("/api/merge/decide", {"vol": "22_proverbes", "uid": UID, "key": k["c1"], "choice": "good"})
    assert code == 200
    merged = json.loads((web.data / "22_proverbes" / "merged" / "page_0194.json").read_text())
    assert "prudent" in merged["commentary"][1]["french_commentary"]
