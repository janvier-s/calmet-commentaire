// The scan panels' zoom steps, shared by the review editor and the /merge side-by-side scans.
import { test } from "node:test";
import assert from "node:assert/strict";
import { ZOOM_STEPS, fitHeight, nextZoom } from "../../review_web/scan_zoom.js";

test("zoom steps up and down, and stops at the ends", () => {
  assert.equal(nextZoom(1, 1), 1.25);
  assert.equal(nextZoom(1, -1), 0.8);
  assert.equal(nextZoom(4, 1), 4);
  assert.equal(nextZoom(0.5, -1), 0.5);
  assert.equal(nextZoom(0.3, -1), 0.3);  // already smaller than the smallest step (Fit ↕ on a tall page)
  assert.equal(nextZoom(0.3, 1), 0.65);
  assert.equal(nextZoom(1.1, 1), 1.5);  // between steps: the step above, then one more
  assert.equal(ZOOM_STEPS[0], 0.5);
});

test("Fit ↕: the page's height in the pane, as a share of the pane's width", () => {
  assert.equal(fitHeight(600, 500, 1000, 1500), (598 * 1000) / 1500 / 498);
  assert.equal(fitHeight(600, 500, 0, 0), 1);
});
