// The same cases as tests/test_page_text.py: the JS port must match page_text.py.
import { test } from "node:test";
import assert from "node:assert/strict";
import { italicRuns, toggleItalics, toUpper, parseRef, snippets, findSpans, wordDiff } from "../../review_web/text.js";

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

test("wordDiff one word changed", () => {
  assert.deepEqual(wordDiff("a b c", "a x c"), [["=", "a "], ["-", "b"], ["+", "x"], ["=", " c"]]);
});

test("wordDiff identical and from empty", () => {
  assert.deepEqual(wordDiff("même texte", "même texte"), [["=", "même texte"]]);
  assert.deepEqual(wordDiff("", "nouveau"), [["+", "nouveau"]]);
  assert.deepEqual(wordDiff(null, "nouveau"), [["+", "nouveau"]]);
});

test("wordDiff gives back both texts", () => {
  const pairs = [
    ["Vide Basil. Homil. in init. Proverb.", "Voyez saint Basile, Homélie au commencement des Proverbes."],
    ["terité. Adam signifie roux ou vermeil.", "Adam signifie roux ou vermeil."],
    ["Ambr. Hilar. lib. 2.", "Saint Ambroise ; saint Hilaire, livre 2."],
  ];
  for (const [a, b] of pairs) {
    const d = wordDiff(a, b);
    assert.equal(d.filter(([op]) => op !== "+").map(([, t]) => t).join(""), a);
    assert.equal(d.filter(([op]) => op !== "-").map(([, t]) => t).join(""), b);
  }
});

test("snippets: a lemma without translation marks the comment up to its first full stop", () => {
  const msg = "Note 2 (℣ 9): latin_quote “MELIUS EST SEDERE IN ANGULO DOMATIS.” has no french_translation; " +
    "the comment starts “Il vaudrait mieux habiter dans un coin. Sur le haut de la mai…”: the translation run into the commentary?";
  assert.deepEqual(snippets(msg, "no_translation"), ["MELIUS EST SEDERE IN ANGULO DOMATIS.", "Il vaudrait mieux habiter dans un coin."]);
  // no full stop in the quotation: all of it, as before
  assert.deepEqual(snippets("latin_quote “AB CD EF.” … starts “Le peuple demeura à Cadés, et…”: x", "no_translation"),
                   ["AB CD EF.", "Le peuple demeura à Cadés, et"]);
});

test("toUpper converts selection to uppercase", () => {
  assert.deepEqual(toUpper("in principio erat", 3, 12), { text: "in PRINCIPIO erat", start: 3, end: 12 });
  assert.deepEqual(toUpper("créé la lumière", 0, 4), { text: "CRÉÉ la lumière", start: 0, end: 4 });
  assert.deepEqual(toUpper("un _mot_ ici", 3, 8), { text: "un _MOT_ ici", start: 3, end: 8 });
  assert.deepEqual(toUpper("cœur", 0, 4), { text: "CŒUR", start: 0, end: 4 });
  assert.deepEqual(toUpper("œuvres", 0, 6), { text: "ŒUVRES", start: 0, end: 6 });
});

test("toUpper returns null when empty, invalid, or already uppercase", () => {
  assert.equal(toUpper("ALREADY UPPER", 0, 13), null);
  assert.equal(toUpper("hello", 2, 2), null);
  assert.equal(toUpper("hello", 3, 1), null);
  assert.equal(toUpper("hello", null, 3), null);
  assert.equal(toUpper("hello", 0, null), null);
});
