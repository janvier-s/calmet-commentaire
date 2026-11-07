"""The /merge decisions store (docs/good_merge/<vol>.json): keys, re-attach, reopen, done state, gold export."""
import json

import pytest

import merge_decisions as md

VOL = "22_proverbes"


def ch(**kw):
    c = {"id": "c1", "kind": "insert", "class": "substantive", "page": 194, "path": "commentary/1/french_commentary",
         "at": 11, "old": "", "good_raw": "prudent", "good_modern": "prudent",
         "good": [{"pdf": "X", "pdf_page": 9, "printed": 12, "boxes": [[5, 6, 7, 8]]}]}
    c.update(kw)
    return c


def unit(changes, status="substantive", uid="commentary:17:2:0", chapter="17"):
    return {"uid": uid, "chapter": chapter, "status": status, "changes": changes}


@pytest.fixture
def docs(tmp_path):
    return tmp_path / "docs"


def test_same_id_two_keys(docs):
    a, b = ch(at=11), ch(at=40)
    assert md.change_key(a) != md.change_key(b)
    u = unit([a, b])
    md.decide(docs, VOL, u["uid"], a, "good")
    doc = md.load(docs, VOL)
    assert md.lookup(doc, u["uid"], a, u["changes"])[1] == "current"
    assert md.lookup(doc, u["uid"], b, u["changes"])[1] == "none"
    assert md.unit_progress(doc, u) == {"done": False, "decided": 1, "todo": 1, "reopened": 0}


def test_reattach_when_at_shifts(docs):
    a = ch(at=11)
    md.decide(docs, VOL, "u", a, "old")
    moved = ch(at=19)
    rec, state = md.lookup(md.load(docs, VOL), "u", moved, [moved])
    assert state == "reattached" and rec["choice"] == "old"


def test_no_reattach_when_id_repeats_in_unit(docs):
    md.decide(docs, VOL, "u", ch(at=11), "old")
    a, b = ch(at=19), ch(at=50)
    assert md.lookup(md.load(docs, VOL), "u", a, [a, b])[1] == "none"


def test_reopen_when_text_changes(docs):
    md.decide(docs, VOL, "u", ch(), "good")
    changed = ch(good_raw="prudents")
    rec, state = md.lookup(md.load(docs, VOL), "u", changed, [changed])
    assert state == "reopened" and rec["good_raw"] == "prudent"
    u = unit([changed], uid="u")
    assert md.unit_progress(md.load(docs, VOL), u) == {"done": False, "decided": 0, "todo": 1, "reopened": 1}


def test_mark_noise_removes_need(docs):
    a = ch()
    u = unit([a])
    md.mark(docs, VOL, u["uid"], a, "noise")
    assert md.unit_progress(md.load(docs, VOL), u)["done"] is True


def test_mark_real_promotes_noise(docs):
    n = ch(**{"class": "noise"})
    u = unit([n], status="cosmetic")
    assert md.unit_progress(md.load(docs, VOL), u)["done"] is True
    md.mark(docs, VOL, u["uid"], n, "real")
    assert md.unit_progress(md.load(docs, VOL), u)["done"] is False
    md.decide(docs, VOL, u["uid"], n, "both")
    assert md.unit_progress(md.load(docs, VOL), u)["done"] is True


def test_done_rules_for_changeless_units(docs):
    doc = md.load(docs, VOL)
    assert md.unit_progress(doc, unit([], status="identical"))["done"] is True
    lone = unit([], status="only_old", uid="verse:17:4:0")
    assert md.unit_progress(doc, lone) == {"done": False, "decided": 0, "todo": 1, "reopened": 0}
    md.decide(docs, VOL, lone["uid"], None, "keep")
    assert md.unit_progress(md.load(docs, VOL), lone)["done"] is True


def test_bad_choices(docs):
    with pytest.raises(ValueError):
        md.decide(docs, VOL, "u", ch(), "edit")
    with pytest.raises(ValueError):
        md.decide(docs, VOL, "u", ch(), "keep")
    with pytest.raises(ValueError):
        md.decide(docs, VOL, "u", None, "good")
    with pytest.raises(ValueError):
        md.mark(docs, VOL, "u", ch(), "maybe")


def test_clearing_and_file_roundtrip(docs):
    a = ch()
    md.decide(docs, VOL, "u", a, "edit", "prudent et sage")
    md.mark(docs, VOL, "u", a, "real")
    on_disk = json.loads((docs / "good_merge" / f"{VOL}.json").read_text(encoding="utf-8"))
    rec = on_disk["decisions"][md.change_key(a)]
    assert (rec["choice"], rec["text"], rec["mark"], rec["uid"]) == ("edit", "prudent et sage", "real", "u")
    md.decide(docs, VOL, "u", a, None)
    md.mark(docs, VOL, "u", a, None)
    assert md.load(docs, VOL)["decisions"] == {}


def test_export_gold(docs, tmp_path):
    import good_variants_eval as ev
    data = tmp_path / "data"
    a, b = ch(), ch(id="c2", at=40, kind="replace", old="sagesse", good_raw="sagese", **{"class": "cosmetic"})
    units = {"vol": VOL, "units": [unit([a, b])]}
    md.mark(docs, VOL, "commentary:17:2:0", a, "real", data=data, units_doc=units)
    md.mark(docs, VOL, "commentary:17:2:0", b, "noise", data=data, units_doc=units)
    f = data / "good_variants_gold" / f"{VOL}_merge.json"
    ref = json.loads(f.read_text(encoding="utf-8"))
    assert ref["vol"] == VOL and ref["chapters"] == [17] and ref["missed"] == []
    assert [(i["label"], i["kind"], i["old"], i["good"]) for i in ref["items"]] == \
        [("real", "insert", "", "prudent"), ("noise", "replace", "sagesse", "sagese")]
    assert ref["items"][0]["good_page"] == [["X", 9, 12]] and ref["items"][0]["note"] == "merge commentary:17:2:0 substantive"
    assert ev.same({**a, "good_raw": a["good_raw"]}, ref["items"][0])
    md.mark(docs, VOL, "commentary:17:2:0", a, None, data=data, units_doc=units)
    assert [i["label"] for i in json.loads(f.read_text(encoding="utf-8"))["items"]] == ["noise"]


def test_reattached_decision_can_be_marked_and_cleared(docs):
    md.decide(docs, VOL, "u", ch(at=11), "good")
    moved = ch(at=19)
    md.mark(docs, VOL, "u", moved, "real", unit_changes=[moved])
    rec, state = md.lookup(md.load(docs, VOL), "u", moved, [moved])
    assert state == "current" and (rec["choice"], rec["mark"]) == ("good", "real")
    assert len(md.load(docs, VOL)["decisions"]) == 1
    md.decide(docs, VOL, "u", moved, None, unit_changes=[moved])
    md.mark(docs, VOL, "u", moved, None, unit_changes=[moved])
    assert md.lookup(md.load(docs, VOL), "u", moved, [moved]) == (None, "none")


def test_new_id_at_the_same_place_reopens(docs):
    md.decide(docs, VOL, "u", ch(id="c1", old="sage", good_raw="sages", at=11), "good")
    now = ch(id="c9", old="sage", good_raw="prudent", at=11)   # the texts changed: good_variants gave a new id
    rec, state = md.lookup(md.load(docs, VOL), "u", now, [now])
    assert state == "reopened" and rec["good_raw"] == "sages"
    md.decide(docs, VOL, "u", now, "old", unit_changes=[now])
    doc = md.load(docs, VOL)
    assert list(doc["decisions"]) == [md.change_key(now)] and md.lookup(doc, "u", now, [now])[1] == "current"


def test_an_orphan_reopens_one_change_only(docs):
    md.decide(docs, VOL, "u", ch(id="c1", at=11), "good")
    a, b = ch(id="c8", good_raw="x", at=11), ch(id="c9", good_raw="y", at=11)
    doc = md.load(docs, VOL)
    assert [md.lookup(doc, "u", c, [a, b])[1] for c in (a, b)] == ["reopened", "none"]


def test_marks_from_two_threads_keep_the_gold_file_whole(docs, tmp_path):
    import threading
    data = tmp_path / "data"
    cs = [ch(id=f"c{i}", at=i * 10) for i in range(40)]
    units = {"vol": VOL, "units": [unit(cs)]}
    errors = []

    def run(part):
        try:
            for c in part:
                md.mark(docs, VOL, "commentary:17:2:0", c, "noise", data=data, units_doc=units, unit_changes=cs)
        except Exception as e:  # os.replace of a temp file another thread already moved
            errors.append(e)
    ts = [threading.Thread(target=run, args=(cs[k::2],)) for k in range(2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert errors == []
    ref = json.loads((data / "good_variants_gold" / f"{VOL}_merge.json").read_text(encoding="utf-8"))
    assert len(ref["items"]) == 40


# --- free edits: typed in the merged text, keyed by place ---

P = "commentary/1/french_commentary"


def test_free_edit_stored_and_replaced(docs):
    md.free_edit(docs, VOL, "u1", 194, P, 10, "le Monde", "la Terre")
    md.free_edit(docs, VOL, "u1", 194, P, 13, "Monde et", "Terre ici")
    edits = md.free_edits(md.load(docs, VOL), "u1")
    assert [(e["at"], e["old"], e["text"]) for e in edits] == [(13, "Monde et", "Terre ici")]
    assert edits[0]["key"] == md.edit_key("u1", 194, P, 13) == f"edit@u1:194:{P}:13"


def test_free_edit_back_to_old_removes(docs):
    md.free_edit(docs, VOL, "u1", 194, P, 10, "le Monde", "la Terre")
    assert md.free_edit(docs, VOL, "u1", 194, P, 10, "le Monde", "le Monde") is None
    assert md.free_edits(md.load(docs, VOL), "u1") == []


def test_locate_edit_current_reattached_reopened():
    rec = {"at": 2, "old": "b"}
    assert md.locate_edit(rec, "a b c") == ((2, 3), "current")
    assert md.locate_edit(rec, "x a b c") == ((4, 5), "reattached")
    assert md.locate_edit(rec, "a B c") == (None, "reopened")
    assert md.locate_edit(rec, "b a b") == (None, "reopened")  # twice elsewhere: no telling which


def test_edit_records_not_orphans(docs):
    a = ch(at=11)
    u = unit([a])
    md.free_edit(docs, VOL, u["uid"], 194, P, 11, "x", "y")
    doc = md.load(docs, VOL)
    assert md.lookup(doc, u["uid"], a, u["changes"]) == (None, "none")
    assert md.unit_progress(doc, u)["todo"] == 1


def test_edit_to_empty_text_allowed(docs):
    rec = md.decide(docs, VOL, "u1", ch(), "edit", "")
    assert rec["choice"] == "edit" and rec["text"] == ""
    with pytest.raises(ValueError):
        md.decide(docs, VOL, "u1", ch(), "edit", None)
