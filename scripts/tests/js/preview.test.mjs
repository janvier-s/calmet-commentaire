import { test } from "node:test";
import assert from "node:assert/strict";
import { previewRuns } from "../../review_web/preview.js";

const show = ({ runs }) => runs.map((r) => (r.mark ? "[" : "") + (r.italic ? `<${r.t}>` : r.t) + (r.mark ? "]" : "")).join("");

test("the italics put in, as italics, the changed words marked", () => {
  const r = previewRuns({ old: "les airs à la gloire du nom", new: "les airs à _la gloire du_ nom" });
  assert.equal(show(r), "les airs à [<la gloire du>] nom");
});

test("italics already there stay italics, the window cut at spaces", () => {
  const old = "a ".repeat(60) + "il dit _Dieu_ et puis la terre de Sual ou" + " b".repeat(60);
  const r = previewRuns({ old, new: old.replace("la terre de Sual", "_la terre de Sual_") }, 30);
  assert.deepEqual(r.cut, [true, true]);
  assert.match(show(r), /<Dieu> et puis \[<la terre de Sual>\] ou/);
});

test("made roman: the words marked, upright", () => {
  const r = previewRuns({ old: "dit _Avant qu'il fût oint, ne se_ lit", new: "dit Avant qu'il fût oint, _ne se_ lit" });
  assert.equal(show(r), "dit [Avant qu'il fût oint, ]<ne se> lit");
});

test("a note's mark shows as its letter", () => {
  const r = previewRuns({ old: "ainsi : ^{(e)} Je me dégagerai d'eux", new: "ainsi : ^{(e)} _Je me dégagerai d'eux_" });
  assert.equal(show(r), "ainsi : (e) [<Je me dégagerai d'eux>]");
});
