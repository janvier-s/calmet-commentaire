// The /merge list's pure state: filters, order, the URL hash, the counter, prev/next.
import { test } from "node:test";
import assert from "node:assert/strict";
import { STATUS_ORDER, filterRows, sortRows, parseHash, toHash, counter, neighbours } from "../../review_web/merge_state.js";

const R = [
  { uid: "a", type: "verse", chapter: 1, status: "identical", i: 0 },
  { uid: "b", type: "commentary", chapter: 1, status: "cosmetic", i: 1 },
  { uid: "c", type: "commentary", chapter: 2, status: "substantive", i: 2 },
  { uid: "d", type: "unaligned", chapter: 2, status: "unaligned", i: 3 },
];
test("default filter hides identical, substantive first", () => {
  const s = parseHash("");
  assert.deepEqual(sortRows(filterRows(R, s)).map((r) => r.uid), ["c", "d", "b"]);
});
test("type and chapter filters", () => {
  assert.deepEqual(filterRows(R, { types: new Set(["commentary"]), statuses: new Set(STATUS_ORDER), chapter: 2 }).map((r) => r.uid), ["c"]);
});
test("hash round-trip", () => {
  const s = { ...parseHash(""), vol: "01_genese", uid: "commentary:1:2:2", chapter: 3, noise: true, open: "178fe50f08" };
  assert.deepEqual(parseHash(toHash(s)), s);
});
test("hash round-trip with filters and a repeated change key", () => {
  const s = { ...parseHash(""), vol: "01_genese", types: new Set(["verse", "summary"]), statuses: new Set(["identical"]), printed: true, open: "e7c9c13a6d~2" };
  assert.deepEqual(parseHash(toHash(s)), s);
});
test("counter", () => {
  assert.equal(counter("01_genese", new Array(2958), { substantive: 672 }), "Genèse: 0 of 2,958 reviewed · 672 substantive left");
});
test("neighbours", () => {
  assert.deepEqual(neighbours(sortRows(filterRows(R, parseHash(""))), "d"), { prev: "c", next: "b" });
});
test("a unit's own scans: one source band per normalized page, its Good pages", async () => {
  const { unitScans } = await import("../../review_web/merge_state.js");
  const view = { unit: { parts: [{ page: 235, path: "verses/1/french" }, { page: 235, path: "verses/1/latin" }, { page: 236, path: "verses/0/french" }],
    good_where: [{ pdf: "X", pdf_page: 9, boxes: [[1, 2, 3, 4]] }] } };
  assert.deepEqual(unitScans(view), {
    sources: [{ page: 235, path: "verses/1/french", at: 0, n: 12 }, { page: 236, path: "verses/0/french", at: 0, n: 12 }],
    good: [{ pdf: "X", pdf_page: 9, boxes: [[1, 2, 3, 4]] }] });
  assert.deepEqual(unitScans({ unit: { parts: [], good_where: [] } }), { sources: [], good: [] });
});
