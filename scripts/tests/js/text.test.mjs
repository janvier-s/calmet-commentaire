// The same cases as tests/test_page_text.py: the JS port must match page_text.py.
import { test } from "node:test";
import assert from "node:assert/strict";
import { italicRuns, toggleItalics, parseRef, snippets, findSpans } from "../../review_web/text.js";

const TOGGLE = [
  [["a b c", 2, 3], { text: "a _b_ c", start: 3, end: 4 }],
  [["_a b c_", 3, 4], { text: "_a_ b _c_", start: 3, end: 6 }],
  [["a  b", 1, 3], null],
  [["un mot ici", 3, 6], { text: "un _mot_ ici", start: 4, end: 7 }],
  [["_tout_", 1, 5], { text: "tout", start: 0, end: 4 }],
];

for (const [args, expected] of TOGGLE) {
  test(`toggleItalics ${JSON.stringify(args)}`, () => {
    assert.deepEqual(toggleItalics(...args), expected);
  });
}

test("italicRuns open at the start", () => {
  assert.deepEqual(italicRuns("fin_ suite"), { runs: [[0, 3]], marks: [3], openAt: "start" });
});

test("italicRuns plain and paired", () => {
  assert.deepEqual(italicRuns("rien"), { runs: [], marks: [], openAt: null });
  assert.deepEqual(italicRuns("a _b_ c"), { runs: [[3, 4]], marks: [2, 4], openAt: null });
});

test("parseRef", () => {
  assert.deepEqual(parseRef("17:2"), { chapter: 17, verse: 2 });
  assert.deepEqual(parseRef(" 17 "), { chapter: 17, verse: null });
  assert.deepEqual(parseRef("p194"), { page: 194 });
  assert.deepEqual(parseRef("194p"), { page: 194 });
  assert.equal(parseRef("abc"), null);
});

test("snippets: quotations, split at the ellipsis", () => {
  assert.deepEqual(snippets("Capitals inside the comment: “…entre les FRÈRES insensés…”: a lemma…", "caps_in_commentary"),
                   ["entre les FRÈRES insensés"]);
  assert.deepEqual(snippets("Full stop at the foot of the page (“…aujourd'hui.”) but the next page goes on in lower case (“d'hui dans le Grec…”)", "period_seam"),
                   ["aujourd'hui.", "d'hui dans le Grec"]);
  assert.deepEqual(snippets("no quotation here", "ref_order"), []);
});

test("snippets: footnote calls", () => {
  assert.deepEqual(snippets("Footnote marker (b) has no footnote text on this page", "missing_footnote"), ["^{(b)}"]);
  assert.deepEqual(snippets("Footnote call “(c)” in french_commentary: “…dit saint (c) Ambroise…”", "broken_marker"),
                   ["(c)", "dit saint (c) Ambroise"]);
});

test("findSpans", () => {
  assert.deepEqual(findSpans("le serviteur  sage dominera", ["serviteur sage"]), [[3, 18]]);
  assert.deepEqual(findSpans("abc", ["zzz"]), []);
  assert.deepEqual(findSpans("un deux trois quatre", ["deux trois", "trois quatre"]), [[3, 20]]);
  assert.deepEqual(findSpans("voir ^{(b)} et ^{(b)}", ["^{(b)}"]), [[5, 11], [15, 21]]);
  // a quote the audit cut mid-word and that no longer matches whole: its longest whole-word part
  assert.deepEqual(findSpans("Le serviteur sage dominera les enfants", ["xur sage dominera les enfants insensés"]), [[13, 38]]);
});
