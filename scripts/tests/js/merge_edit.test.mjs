// The /merge merged column's pure helpers: raw text <-> nodes, the segments edited, undo, the Ctrl+Z gate.
import { test } from "node:test";
import assert from "node:assert/strict";
import { Undo, cellTexts, diffClass, inverse, segmentEdits, toNodes, toRaw, undoKey } from "../../review_web/merge_edit.js";

test("raw text round-trips through nodes, markers atomic, italics marked", () => {
  const raw = "Son Verbe ^{(a)} et _sa_ sagesse.";
  const nodes = toNodes(raw);
  assert.deepEqual(nodes, [
    { kind: "text", t: "Son Verbe " }, { kind: "marker", t: "^{(a)}" }, { kind: "text", t: " et " },
    { kind: "italic", t: "sa" }, { kind: "text", t: " sagesse." }]);
  assert.equal(toRaw(nodes), raw);
  for (const s of ["", "plain", "^{(b)}", "_tout_", "a_b", "x ^{(c)}."]) assert.equal(toRaw(toNodes(s)), s);
});

test("segmentEdits: only the segments whose text changed, with their place", () => {
  const before = [
    { t: " Un esclave", page: 194, path: "p", a: 0, b: 10, key: null },
    { t: " qui", page: 194, path: "p", a: 10, b: 14, key: "c1@194:p:11" },
  ];
  assert.deepEqual(segmentEdits(before, [" Un esclave", " lequel"]),
    [{ page: 194, path: "p", a: 10, b: 14, text: " lequel", key: "c1@194:p:11", before: " qui" }]);
  assert.deepEqual(segmentEdits(before, [" Un esclave", " qui"]), []);
});

test("undo: last in, first out; the inverse restores what was before", () => {
  const u = new Undo();
  assert.equal(u.pop(), null);
  const d = { kind: "decide", vol: "v", uid: "u", key: "k", before: { choice: null, text: null }, after: { choice: "good" } };
  const e = { kind: "edit", vol: "v", uid: "u", page: 1, path: "p", a: 3, b: 7, before: " mot", after: " mots" };
  u.push(d); u.push(e);
  assert.equal(u.pop(), e);
  assert.equal(u.pop(), d);
  assert.deepEqual(inverse(d), { kind: "decide", vol: "v", uid: "u", key: "k", choice: null, text: null });
  assert.deepEqual(inverse(e), { kind: "edit", vol: "v", uid: "u", page: 1, path: "p", a: 3, b: 7, text: " mot" });
});

test("Ctrl/Cmd+Z undoes a decision only outside the text being typed", () => {
  const body = { tagName: "BODY", isContentEditable: false };
  assert.equal(undoKey({ key: "z", ctrlKey: true, target: body }), true);
  assert.equal(undoKey({ key: "z", metaKey: true, target: body }), true);
  assert.equal(undoKey({ key: "z", target: body }), false);
  assert.equal(undoKey({ key: "z", ctrlKey: true, shiftKey: true, target: body }), false);
  assert.equal(undoKey({ key: "z", ctrlKey: true, target: { tagName: "DIV", isContentEditable: true } }), false);
  assert.equal(undoKey({ key: "z", ctrlKey: true, target: { tagName: "TEXTAREA", isContentEditable: false } }), false);
});

test("diffClass: colour by kind, strength by class, decided faded", () => {
  assert.equal(diffClass({ kind: "insert", class: "substantive" }, false), "mg-k-add mg-s-sub");
  assert.equal(diffClass({ kind: "only_normalized", class: "cosmetic" }, false), "mg-k-cut mg-s-cos");
  assert.equal(diffClass({ kind: "replace", class: "noise" }, true), "mg-k-swap mg-s-noise mg-decided");
  assert.equal(diffClass({ kind: "unclear", class: "substantive" }, false), "mg-k-swap mg-s-sub");
  assert.equal(diffClass({ kind: "replace", class: "moved" }, false), "mg-k-move mg-s-sub");
  assert.equal(diffClass({ kind: "moved", class: "cosmetic" }, false), "mg-k-move mg-s-cos");
});

test("cellTexts: a segment deleted whole is empty; loose text goes to the segment before it", () => {  // I2
  const kids = [{ kind: "seg", i: 3, text: " Un" }, { kind: "skip" }, { kind: "loose", text: " mot" }, { kind: "seg", i: 5, text: " fin" }];
  assert.deepEqual(cellTexts(kids, [3, 4, 5]), { 3: " Un mot", 4: "", 5: " fin" });
  assert.deepEqual(cellTexts([{ kind: "loose", text: "Avant " }, { kind: "seg", i: 0, text: "tout" }], [0]), { 0: "Avant tout" });
});
