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


def test_merge_edit_drop(web):
    base = {"vol": "22_proverbes", "uid": UID}
    web("/api/merge/edit", {**base, "page": 194, "path": T2, "a": 16, "b": 22, "text": " de toute la"})
    f = web.data.parent / "docs" / "good_merge" / "22_proverbes.json"
    key = next(k for k in json.loads(f.read_text())["decisions"] if k.startswith("edit@"))
    code, r = web("/api/merge/edit", {**base, "drop": key})
    assert code == 200 and not any(k.startswith("edit@") for k in json.loads(f.read_text())["decisions"])
    merged = json.loads((web.data / "22_proverbes" / "merged" / "page_0194.json").read_text())
    assert merged["commentary"][1]["french_commentary"] == "Un esclave qui a de la sagesse ^{(a)}."
    assert web("/api/merge/edit", {**base, "drop": "edit@other:1:x:0"})[0] == 404


def test_merge_edit_reverting_a_segment_removes_its_edit(web):
    base = {"vol": "22_proverbes", "uid": UID}
    web("/api/merge/edit", {**base, "page": 194, "path": T2, "a": 10, "b": 22, "text": " lequel a de la"})
    f = web.data.parent / "docs" / "good_merge" / "22_proverbes.json"
    assert any(k.startswith("edit@") for k in json.loads(f.read_text())["decisions"])
    code, _ = web("/api/merge/edit", {**base, "page": 194, "path": T2, "a": 10, "b": 22, "text": " qui a de la"})
    assert code == 200 and not any(k.startswith("edit@") for k in json.loads(f.read_text())["decisions"])


# --- final review fixes ---

def test_second_edit_beside_a_free_edit_keeps_it(web):  # C1
    base = {"vol": "22_proverbes", "uid": UID}
    _, r = web("/api/merge/edit", {**base, "page": 194, "path": T2, "a": 10, "b": 22, "text": " lequel a de la"})
    after = next(s for s in r["view"]["merged"] if s["kind"] == "same" and s["path"] == T2 and s["t"] == " a de la")
    assert (after["a"], after["b"]) == (14, 22)
    edit = next(s for s in r["view"]["merged"] if s["kind"] == "edit")
    assert (edit["a"], edit["b"]) == (11, 14)
    code, r = web("/api/merge/edit", {**base, "page": 194, "path": T2, "a": 14, "b": 22, "text": " a de toute la"})
    assert code == 200
    merged = json.loads((web.data / "22_proverbes" / "merged" / "page_0194.json").read_text())
    assert merged["commentary"][1]["french_commentary"] == "Un esclave lequel a de toute la sagesse ^{(a)}."


def test_edit_refused_when_the_field_changed_since_the_view(web):  # I1
    base = {"vol": "22_proverbes", "uid": UID}
    _, v = web(f"/api/merge/unit?vol=22_proverbes&uid={UID}")
    h = v["fields"][f"194:{T2}"]
    p = web.data / "22_proverbes" / "normalized" / "page_0194.json"
    d = json.loads(p.read_text())
    d["commentary"][1]["french_commentary"] = "Un ^{(b)} esclave qui a de la sagesse ^{(a)}."
    p.write_text(json.dumps(d))
    code, _ = web("/api/merge/edit", {**base, "page": 194, "path": T2, "a": 0, "b": 10, "text": "Un serviteur", "h": h})
    assert code == 409


def test_edit_accepted_with_the_fields_hash(web):
    base = {"vol": "22_proverbes", "uid": UID}
    _, v = web(f"/api/merge/unit?vol=22_proverbes&uid={UID}")
    code, _ = web("/api/merge/edit", {**base, "page": 194, "path": T2, "a": 10, "b": 22, "text": " lequel a de la",
                                      "h": v["fields"][f"194:{T2}"]})
    assert code == 200


def test_cleanup_lists_records_and_undo_takes_one_back(web):
    import good_normalized as gn
    rec = {"i": 0, "before": "sagese", "after": "sagesse", "rule": "spelling"}
    gn.store_path(web.data, "22_proverbes").write_text(json.dumps(
        {"changes": {"c2": {"src": gn.src_hash("sagese"), "records": [rec]}}}), encoding="utf-8")
    k = keys(web)
    _, u = web(f"/api/merge/unit?vol=22_proverbes&uid={UID}")
    c2 = next(c for c in u["changes"] if c["id"] == "c2")
    assert c2["good_normalized"] == "sagesse" and c2["good_records"][0]["undone"] is False
    st, r = web("/api/merge/cleanup", {"vol": "22_proverbes", "uid": UID, "key": k["c2"], "record": gn.key(rec)})
    c2 = next(c for c in r["view"]["changes"] if c["id"] == "c2")
    assert st == 200 and "good_normalized" not in c2 and c2["good_records"][0]["undone"] is True
    st, r = web("/api/merge/cleanup", {"vol": "22_proverbes", "uid": UID, "key": k["c2"], "record": gn.key(rec), "undo": False})
    assert next(c for c in r["view"]["changes"] if c["id"] == "c2")["good_normalized"] == "sagesse"
    assert web("/api/merge/cleanup", {"vol": "22_proverbes", "uid": UID, "key": k["c2"], "record": "x => y"})[0] == 400


def merged_page(web, page=194):
    return json.loads((web.data / "22_proverbes" / "merged" / f"page_{page:04d}.json").read_text())


def test_merged_view_edit_kept_flagged_and_undone(web):
    k = keys(web)
    web("/api/merge/decide", {"vol": "22_proverbes", "uid": UID, "key": k["c1"], "choice": "good"})
    code, m = web("/api/merged?vol=22_proverbes&page=194")
    assert code == 200 and m["hand"] == {}
    shown = m["data"]["commentary"][1]["french_commentary"]
    body = {"vol": "22_proverbes", "page": 194, "fields": {T2: "Tapé à la main."}, "was": {T2: "stale"}}
    assert web("/api/merged/save", body)[0] == 409
    code, m = web("/api/merged/save", {**body, "was": {T2: shown}})
    assert code == 200 and m["hand"][T2]["edited"] and not m["hand"][T2]["conflict"]
    assert T2 not in m["marks"] and merged_page(web)["commentary"][1]["french_commentary"] == "Tapé à la main."
    # normalized saved in the editor: merged rebuilt at once, the hand edit kept and flagged
    _, p = web("/api/page?vol=22_proverbes&page=194")
    p["data"]["commentary"][1]["french_commentary"] = p["data"]["commentary"][1]["french_commentary"].replace("esclave", "serf")
    p["data"]["commentary"][0]["french_commentary"] = "Changé dans normalized."
    code, r = web("/api/page", {"vol": "22_proverbes", "page": 194, "data": p["data"], "version": p["version"]})
    assert code == 200 and r["merged_flags"] == 1
    mp = merged_page(web)
    assert mp["commentary"][1]["french_commentary"] == "Tapé à la main."
    assert mp["commentary"][0]["french_commentary"] == "Changé dans normalized."
    _, f = web("/api/merged/flags?vol=22_proverbes")
    assert [(x["page"], x["path"], x["why"]) for x in f["flags"]] == [(194, T2, "changed")] and "serf" in f["flags"][0]["built"]
    # take the rebuilt text, then undo that
    code, m = web("/api/merged/resolve", {"vol": "22_proverbes", "page": 194, "path": T2, "choice": "theirs"})
    assert code == 200 and "serf" in merged_page(web)["commentary"][1]["french_commentary"] and not m["hand"][T2]["edited"]
    code, m = web("/api/merged/restore", {"vol": "22_proverbes", "page": 194, "path": T2})
    assert code == 200 and merged_page(web)["commentary"][1]["french_commentary"] == "Tapé à la main."
    assert m["hand"][T2]["conflict"]["why"] == "changed"
    code, m = web("/api/merged/resolve", {"vol": "22_proverbes", "page": 194, "path": T2, "choice": "mine"})
    assert code == 200 and not m["hand"][T2]["conflict"]
    assert web("/api/merged/flags?vol=22_proverbes")[1]["flags"] == []


def test_merged_errors(web):
    assert web("/api/merged/save", {"vol": "22_proverbes", "page": 194, "fields": {}})[0] == 404  # no merged/ yet
    web("/api/merge/decide", {"vol": "22_proverbes", "uid": UID, "key": keys(web)["c1"], "choice": "good"})
    assert web("/api/merged/save", {"vol": "22_proverbes", "page": 194, "fields": {"nope/0/x": "a"}, "was": {}})[0] == 400
    assert web("/api/merged/save", {"vol": "22_proverbes", "page": 194, "fields": "x"})[0] == 400
    assert web("/api/merged/resolve", {"vol": "22_proverbes", "page": 194, "path": T2, "choice": "mine"})[0] == 404
    assert web("/api/merged/restore", {"vol": "22_proverbes", "page": 194, "path": T2})[0] == 404


def test_merged_rebuilt_when_a_script_wrote_normalized(web):
    import os
    web("/api/merge/decide", {"vol": "22_proverbes", "uid": UID, "key": keys(web)["c1"], "choice": "good"})
    other = Store(web.data, web.data.parent / "docs")  # a script's store: no listener
    d, v = other.read("22_proverbes", 194)
    d["commentary"][0]["french_commentary"] = "Écrit par un script."
    other.save("22_proverbes", 194, d, v)
    mf = web.data / "22_proverbes" / "merged" / "page_0194.json"
    os.utime(mf, ns=(1, 1))  # older than normalized
    _, m = web("/api/merged?vol=22_proverbes&page=194")
    assert m["data"]["commentary"][0]["french_commentary"] == "Écrit par un script."


def test_page_says_merged_edited_and_good_italics():
    import merge_build
    assert merge_build.good_italics("il dit mot ici", "il dit _mot ici_ là") == [(8, 15)]
    assert merge_build.good_italics("il _dit_ mot", "il _dit_ _mot_") == [(10, 13)]
    assert merge_build.good_italics("a b", "a b") == []
    assert merge_build.page_italics({"t": ["x y", "a"]}, {"t": ["_x_ y", "a"]}) == {"t/0": [(1, 2)]}


def test_merged_edited_flag(web):
    _, p = web("/api/page?vol=22_proverbes&page=194")
    assert p["merged_edited"] is False and p["good_keys"] == []
    web("/api/merge/decide", {"vol": "22_proverbes", "uid": UID, "key": keys(web)["c1"], "choice": "good"})
    _, p = web("/api/page?vol=22_proverbes&page=194")
    assert p["merged_edited"] is True
    code, m = web("/api/merged?vol=22_proverbes&page=194")
    assert code == 200 and "italics" in m
    assert web("/api/good_step?vol=22_proverbes&key=nope&dir=1")[0] == 404
