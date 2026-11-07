// The scan panels' zoom: the steps, one step in or out, and Fit ↕ (the review editor's scan pane and the
// /merge side-by-side scans share them).

export const ZOOM_STEPS = [0.5, 0.65, 0.8, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0];

/** One step in (dir 1) or out (-1) from `zoom`; never out from below the smallest step. */
export function nextZoom(zoom, dir) {
  if (dir < 0 && zoom < ZOOM_STEPS[0] - 1e-6) return zoom;
  const i = ZOOM_STEPS.findIndex((z) => z >= zoom - 1e-6);
  return ZOOM_STEPS[Math.max(0, Math.min(ZOOM_STEPS.length - 1, (i < 0 ? ZOOM_STEPS.length - 1 : i) + dir))];
}

/** The zoom (a share of the pane's width) at which the whole page's height fits the pane. */
export function fitHeight(paneH, paneW, imgW, imgH) {
  if (!imgW || !imgH) return 1;
  return Math.max(0.1, ((paneH - 2) * imgW) / imgH / (paneW - 2));
}
