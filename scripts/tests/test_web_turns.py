import json
import threading
import urllib.error
import urllib.request

import pytest

from conftest import QUEUE, dump
from review_store import Store
from review_web import make_server

VOL = "22_proverbes"
NOTE = {"page": "page_0194", "marker": "(a)", "text": "Prov. 17. 2.", "proposed": "Proverbes 17:2.",
        "why": ["abbreviations written out"], "flags": ["uncertain"]}


def put(data_dir, page, fn):
    p = data_dir / VOL / "normalized" / f"page_{page:04d}.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    fn(d)
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def web(data_dir):
    docs = data_dir.parent / "docs"
    put(data_dir, 193, lambda d: d.update(footnotes=[{"marker": "(a)", "text": "Gen. 1. 1."}]))
    dump(docs / "footnotes" / f"{VOL}.json", {"summary": {}, "notes": [
        dict(NOTE, id="0194(a)"),
        dict(NOTE, id="0193(a)", page="page_0193", text="Gen. 1. 1.", proposed="Genèse 1:1.")]})
    queue = QUEUE + [{"id": f"{VOL}/0195/seam_artifact/eeee", "book_dir": VOL, "page": 195,
                      "kind": "seam_artifact", "msg": "glitch", "optional": False}]
    dump(docs / "review_queue.json", queue)
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


def footnote_item(web, page):
    code, q = web(f"/api/queue?kind=footnote_writeout&status=all")
    return next(i for i in q["items"] if i["page"] == page)


def progress(web):
    p = web.data / ".review_queue_progress.json"
    return json.loads(p.read_text()) if p.exists() else {}


def test_config_turn_kinds(web):
    assert "hyphen_cut" in web("/api/config")[1]["turn_kinds"]


def test_turn_route(web):
    code, t = web(f"/api/turn?vol={VOL}&a=194")
    assert code == 200 and t["a"]["page"] == 194 and t["b"]["page"] == 195
    assert {i["kind"] for i in t["issues"]} == {"hyphen_cut", "seam_artifact"}
    assert t["around"] == {"prev": None, "next": None}
    code, t = web(f"/api/turn?vol={VOL}&a=193")
    assert code == 200 and t["around"]["next"] == 194
    assert web(f"/api/turn?vol={VOL}&a=999")[0] == 404


def test_turn_route_by_item(web):
    code, t = web(f"/api/turn?id={VOL}/0195/seam_artifact/eeee")
    assert code == 200 and (t["a"]["page"], t["b"]["page"]) == (194, 195)
    assert web(f"/api/turn?id={VOL}/0194/missing_footnote/bbbb")[0] == 404


def test_queue_items_carry_no_proposal(web):
    it = footnote_item(web, 194)
    assert "proposal" not in it and it["kind"] == "footnote_writeout"


def test_proposal_accept_marks_resolved(web):
    it = footnote_item(web, 194)
    code, r = web(f"/api/proposal?id={it['id']}")
    p = r["proposal"]
    assert code == 200 and p["options"][0]["changes"][0]["new"] == "Proverbes 17:2."
    code, r = web("/api/proposal/accept", {"id": it["id"], "proposal_id": p["id"], "option": 0})
    assert code == 200 and r["pages"]["194"]["data"]["footnotes"][0]["text"] == "Proverbes 17:2."
    assert progress(web)[it["id"]] == "resolved"


def test_proposal_accept_conflict_409(web):
    it = footnote_item(web, 194)
    p = web(f"/api/proposal?id={it['id']}")[1]["proposal"]
    put(web.data, 194, lambda d: d["footnotes"][0].update(text="Typed by hand."))
    code, r = web("/api/proposal/accept", {"id": it["id"], "proposal_id": p["id"], "option": 0})
    assert code == 409 and it["id"] not in progress(web)


def test_proposal_accept_stale_id_409(web):
    it = footnote_item(web, 194)
    code, _ = web("/api/proposal/accept", {"id": it["id"], "proposal_id": "something else", "option": 0})
    assert code == 409


def test_reject_generated_is_false_positive(web):
    it = footnote_item(web, 194)
    p = web(f"/api/proposal?id={it['id']}")[1]["proposal"]
    assert web("/api/proposal/reject", {"id": it["id"], "proposal_id": p["id"]})[0] == 200
    assert progress(web)[it["id"]] == "false_positive"
    fps = json.loads((web.data.parent / "docs" / "false_positives.json").read_text())
    assert it["id"] in fps


def test_reject_seam_hides_proposal(web):
    put(web.data, 194, lambda d: d["commentary"][-1].update(french_commentary="Le nom de toute sa posterité."))
    put(web.data, 195, lambda d: d.update(commentary=[{"commentary_id": 1, "verse_ref": None, "chapter": 17,
                                                      "latin_quote": None, "french_translation": None,
                                                      "french_commentary": "terité. Adam signifie roux."}]))
    iid = f"{VOL}/0195/seam_artifact/eeee"
    p = web(f"/api/proposal?id={iid}")[1]["proposal"]
    assert p and p["id"].startswith("seam/")
    assert web("/api/proposal/reject", {"id": iid, "proposal_id": p["id"]})[0] == 200
    assert web(f"/api/proposal?id={iid}")[1]["proposal"] is None
    assert progress(web).get(iid) is None


def test_batch_rows(web):
    code, r = web(f"/api/batch?kind=footnote_writeout&book={VOL}")
    assert code == 200 and [row["page"] for row in r["rows"]] == [193, 194]
    assert r["rows"][0]["proposal"]["options"][0]["changes"][0]["new"] == "Genèse 1:1."
    assert r["rows"][0]["context"] == "Gen. 1. 1."
    code, r = web(f"/api/batch?kind=hyphen_cut&book={VOL}")
    assert r["rows"][0]["context"] is None  # 195 has no commentary: nothing to join
    code, r = web(f"/api/batch?kind=seam_artifact&book={VOL}")
    assert r["rows"][0]["context"] is None


def test_batch_accept_partial(web):
    a, b = footnote_item(web, 193), footnote_item(web, 194)
    put(web.data, 194, lambda d: d["footnotes"][0].update(text="Typed by hand."))
    code, r = web("/api/batch/accept", {"ids": [a["id"], b["id"]]})
    assert code == 200 and r["done"] == [a["id"]]
    assert [f["id"] for f in r["failed"]] == [b["id"]]
    pr = progress(web)
    assert pr[a["id"]] == "resolved" and b["id"] not in pr


def test_batch_accept_refuses_a_proposal_changed_since_shown(web):
    put(web.data, 194, lambda d: d["commentary"][-1].update(french_commentary="Le nom de toute sa posterité."))
    put(web.data, 195, lambda d: d.update(commentary=[{"commentary_id": 1, "verse_ref": None, "chapter": 17,
                                                      "latin_quote": None, "french_translation": None,
                                                      "french_commentary": "terité. Adam signifie roux."}]))
    iid = f"{VOL}/0195/seam_artifact/eeee"
    shown = web(f"/api/proposal?id={iid}")[1]["proposal"]
    put(web.data, 195, lambda d: d["commentary"][0].update(french_commentary="terité. Adam signifie roux et vermeil."))
    code, r = web("/api/batch/accept", {"ids": [{"id": iid, "proposal_id": shown["id"]}]})
    assert code == 200 and r["done"] == [] and [f["id"] for f in r["failed"]] == [iid]
    assert "vermeil" in json.loads((web.data / VOL / "normalized" / "page_0195.json").read_text())["commentary"][0]["french_commentary"]


def test_batch_accept_reports_unexpected_errors(web):
    a, b = footnote_item(web, 193), footnote_item(web, 194)
    (web.data / VOL / "normalized" / "page_0193.json").unlink()
    code, r = web("/api/batch/accept", {"ids": [{"id": a["id"]}, {"id": b["id"]}]})
    assert code == 200 and r["done"] == [b["id"]] and [f["id"] for f in r["failed"]] == [a["id"]]
