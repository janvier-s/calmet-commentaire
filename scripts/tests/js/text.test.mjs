// The same cases as tests/test_page_text.py: the JS port must match page_text.py.
import { test } from "node:test";
import assert from "node:assert/strict";
import { italicRuns, toggleItalics, parseRef } from "../../review_web/text.js";

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
