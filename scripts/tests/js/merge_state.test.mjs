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
  const rows = [
    { status: "substantive", progress: { done: true } }, { status: "substantive", progress: { done: false } },
    { status: "cosmetic", progress: { done: true } }, { status: "identical", progress: { done: true } },
    { status: "only_old", progress: { done: false } }];
  assert.equal(counter("01_genese", rows), "Genèse: 3 of 5 done · 1 substantive left");
  assert.equal(counter("01_genese", [{ status: "substantive" }]), "Genèse: 0 of 1 done · 1 substantive left");
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

test("progress filter and its hash", () => {
  const rows = [{ uid: "a", type: "verse", status: "substantive", progress: { done: true } },
    { uid: "b", type: "verse", status: "substantive", progress: { done: false } }];
  const f = { types: null, statuses: new Set(["substantive"]), chapter: null };
  assert.deepEqual(filterRows(rows, { ...f, progress: "todo" }).map((r) => r.uid), ["b"]);
  assert.deepEqual(filterRows(rows, { ...f, progress: "done" }).map((r) => r.uid), ["a"]);
  assert.deepEqual(filterRows(rows, { ...f, progress: null }).map((r) => r.uid), ["a", "b"]);
  assert.equal(parseHash(toHash({ ...parseHash(""), progress: "todo" })).progress, "todo");
  assert.equal(parseHash("").progress, null);
});

test("undecided: noise needs nothing unless marked real; a reopened choice counts as undecided", async () => {
  const { undecided } = await import("../../review_web/merge_state.js");
  const dec = (d) => ({ state: "current", choice: null, mark: null, ...d });
  assert.equal(undecided({ class: "substantive", decision: dec({}) }), true);
  assert.equal(undecided({ class: "substantive", decision: dec({ choice: "good" }) }), false);
  assert.equal(undecided({ class: "noise", decision: dec({}) }), false);
  assert.equal(undecided({ class: "noise", decision: dec({ mark: "real" }) }), true);
  assert.equal(undecided({ class: "cosmetic", decision: dec({ mark: "noise" }) }), false);
  assert.equal(undecided({ class: "cosmetic", decision: dec({ choice: "old", state: "reopened" }) }), true);
  assert.equal(undecided({ class: "cosmetic" }), true);
});
