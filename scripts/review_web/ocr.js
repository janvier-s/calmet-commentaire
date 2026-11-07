// The scan's OCR (Kraken) drawn over it: every word the JSON lacks in red, a different word in amber,
// a near one (a slip, or old spelling the key misses) outlined. Click a box: its place in the text;
// the caret in a field: its word on the scan. Shift-drag on the scan (or "Box" then drag) draws a
// region and adds a to-do for it; a page's region to-dos are drawn whenever it is open. Words printed in
// italics where the text has roman, or the other way (their slant on the scan), are outlined in green.
// Words the JSON has in italics already get a wavy green underline ("JSON italics"), and the commentary's
// french_translation a wavy purple one, lower ("Translation"): where its italics need checking by hand.
// The OCR is only a witness for the review, never a source of text.
import { S, api, hooks, toast } from "./app.js";
import { refreshCounts, renderIssues, setStatus } from "./queue.js";
import { typedData } from "./edit.js";
import { todoPrompt, whereOf } from "./todo.js";

const $ = (id) => document.getElementById(id);
const SVG = "http://www.w3.org/2000/svg";
const svgEl = (tag, attrs = {}) => {
  const e = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
};
const FLAGS = ["missing", "diff", "near", "both"];
const TYPES = [
  ["missing", "missing", "Red: in the scan, not in the JSON (space shown red in the text)"],
  ["extra", "not on scan", "Red in the text: in the JSON, not on the scan"],
  ["diff", "diff", "Orange: a different word"],
  ["both", "both OCRs", "Orange: Kraken and Tesseract both read this word, the JSON has another"],
  ["near", "near", "Orange dashed: nearly the same word"],
  ["italics", "italics", "Green: italic on the scan and roman in the text, or the other way"],
  ["jsonit", "JSON italics", "Wavy green underline: words already in italics in the JSON (italics on the scan without it still need marking); red where the scan prints them roman"],
  ["ftr", "Translation", "Wavy purple underline: the commentary's french_translation, whose italics need checking by hand"],
];

let on = false;
try { on = localStorage.getItem("rw-ocr") === "1"; } catch (e) {}
let active = new Set(TYPES.map(([k]) => k));
try {
  const saved = JSON.parse(localStorage.getItem("rw-ocr-filters"));
  if (Array.isArray(saved)) {
    active = new Set(saved.filter((k) => TYPES.some(([t]) => t === k)));
    if (localStorage.getItem("rw-ocr-both") !== "1" && !saved.includes("both") && (active.has("diff") || active.has("near")))
      active.add("both");  // saved before "both" was: once (saved below), so "both" turned off stays off
  }
} catch (e) {}
try {
  if (localStorage.getItem("rw-ocr-jsonit") !== "1" && localStorage.getItem("rw-ocr-filters")) {
    active.add("jsonit");  // saved before "JSON italics" was: shown once, so turned off stays off
    localStorage.setItem("rw-ocr-filters", JSON.stringify([...active]));
  }
  localStorage.setItem("rw-ocr-jsonit", "1");
  if (localStorage.getItem("rw-ocr-ftr") !== "1" && localStorage.getItem("rw-ocr-filters")) {
    active.add("ftr");  // saved before "Translation" was: shown once, so turned off stays off
    localStorage.setItem("rw-ocr-filters", JSON.stringify([...active]));
  }
  localStorage.setItem("rw-ocr-ftr", "1");
} catch (e) {}
const saveFilters = () => { try { localStorage.setItem("rw-ocr-filters", JSON.stringify([...active])); } catch (e) {} };
try {
  if (localStorage.getItem("rw-ocr-both") !== "1") { saveFilters(); localStorage.setItem("rw-ocr-both", "1"); }
} catch (e) {}

let res = null;       // the alignment of the page shown: {size, words, extra}
let shownFor = null;  // "vol/page" it is for
let cur = -1;         // the word linked to the caret, or the last one clicked
let flagAt = -1;      // the last flag gone to with the counter

const view = $("scan-view"), img = $("scan-img");
const svg = svgEl("svg", { id: "ocr-layer", preserveAspectRatio: "none" });
view.append(svg);

// --- the tools ---
const box = Object.assign(document.createElement("label"), { className: "muted", title: "The OCR's words over the scan: red, missing from the JSON; orange, a different word; green, italics" });
const check = Object.assign(document.createElement("input"), { type: "checkbox", checked: on });
box.append(check, " OCR");
const filterBar = Object.assign(document.createElement("span"), { id: "ocr-filters", className: "group", hidden: true });
const filterBtns = Object.fromEntries(TYPES.map(([k, label, desc]) => {
  const b = Object.assign(document.createElement("button"), {
    className: `ocr-f f-${k}` + (active.has(k) ? " on" : ""),
    textContent: label,
    title: `${desc}\nClick: show/hide · ⌥-click: only this type`,
    onclick: (e) => {
      if (e.altKey || e.metaKey) {
        active = active.size === 1 && active.has(k) ? new Set(TYPES.map(([t]) => t)) : new Set([k]);
      } else if (active.has(k)) active.delete(k);
      else active.add(k);
      saveFilters();
      draw();
    },
  });
  filterBar.append(b);
  return [k, b];
}));
const phase = (label, keys, title) => Object.assign(document.createElement("button"), {
  textContent: label, title, className: "ocr-phase",
  onclick: () => { active = new Set(keys); saveFilters(); draw(); },
});
filterBar.prepend(
  phase("Phase 1", ["missing", "extra", "italics", "jsonit", "ftr"], "Show only red (missing, not on scan), green (italics, and the JSON's italics underlined) and purple (french_translation underlined)"),
  phase("Phase 2", ["both"], "Show only the words both OCRs read and the JSON has otherwise"));
const count = Object.assign(document.createElement("button"), { className: "link small", id: "ocr-count", hidden: true,
                                                                title: "Go to the next flagged word among the active filters" });
const run = Object.assign(document.createElement("button"), { textContent: "Read the scan", hidden: true,
                                                              title: "OCR this page with Kraken (about 15 s)" });
const tessBtn = Object.assign(document.createElement("button"), { textContent: "Tesseract", hidden: true, className: "small",
                                                                 title: "Read this page with Tesseract too (a few seconds), to settle the red words" });
const region = Object.assign(document.createElement("button"), { textContent: "Box", title: "Drag a region on the scan for a to-do (or Shift-drag)" });
$("scan-tools").querySelector(".grow").before(filterBar);  // the chips show with the OCR on; everything else is in the menu
$("scan-menu").append(box, count, tessBtn, run, region, ...filterBar.querySelectorAll(".ocr-phase"));
$("scan-menu-btn").onclick = (e) => { e.stopPropagation(); $("scan-menu").hidden = !$("scan-menu").hidden; };
document.addEventListener("click", (e) => { if (!e.target.closest("#scan-tools .menu")) $("scan-menu").hidden = true; });
check.onchange = () => {
  on = check.checked;
  try { localStorage.setItem("rw-ocr", on ? "1" : "0"); } catch (e) {}
  shownFor = null;
  refresh();
};
run.onclick = () => refresh(true);
tessBtn.onclick = () => refresh(false, true);
region.onclick = () => region.classList.toggle("on");
function activeFlags() {
  if (!res) return [];
  return [...new Set([
    ...res.words.flatMap((w, i) => (FLAGS.includes(w.s) && active.has(w.s) ? [i] : [])),
    ...(active.has("italics") ? res.italics.map((r) => r.words[0]) : []),
  ])].sort((a, b) => a - b);
}
count.onclick = () => {
  const flags = activeFlags();
  if (!flags.length) return;
  flagAt = flags.find((i) => i > flagAt) ?? flags[0];
  goToText(flagAt);
};

// --- fetching and drawing ---
let pending = 0;
async function refresh(runOcr = false, runTess = false) {
  const at = `${S.vol}/${S.page}`;
  if (!on || !S.vol) { res = null; draw(); return; }
  const n = ++pending;
  if (runOcr) { run.disabled = true; run.textContent = "Reading… (15 s)"; }
  if (runTess) { tessBtn.disabled = true; tessBtn.textContent = "Reading…"; }
  const r = await api("/api/ocr", { vol: S.vol, page: S.page, data: S.fields.length ? typedData() : S.data, run: runOcr, tess_run: runTess });
  tessBtn.disabled = false;
  tessBtn.textContent = "Tesseract";
  run.disabled = false;
  run.textContent = "Read the scan";
  if (n !== pending || at !== `${S.vol}/${S.page}`) return;  // a later page or edit came meanwhile
  if (r.status !== 200) { toast(r.body.error || "No OCR"); res = null; }
  else {
    res = r.body.ocr;
    if (r.body.tess_error) toast(r.body.tess_error);  // the overlay stays, without Tesseract
  }
  if (shownFor !== at) { cur = -1; flagAt = -1; }
  shownFor = at;
  draw();
}

function mergeLineBoxes(boxes) {
  const out = [];
  for (const b of boxes) {
    const last = out[out.length - 1];
    if (last && b[0] >= last[0] && b[0] - (last[0] + last[2]) < 120 &&
        Math.abs((b[1] + b[3] / 2) - (last[1] + last[3] / 2)) < Math.max(b[3], last[3]) * 0.8) {
      const x1 = Math.min(last[0], b[0]), y1 = Math.min(last[1], b[1]);
      const x2 = Math.max(last[0] + last[2], b[0] + b[2]), y2 = Math.max(last[1] + last[3], b[1] + b[3]);
      out[out.length - 1] = [x1, y1, x2 - x1, y2 - y1];
    } else {
      out.push([...b]);
    }
  }
  return out;
}

/** The part of the scan the image shows, in the scan's pixels: [x, y, w, h]. The editor shows the
 * margin crop (S.scanCrop: [x0, y0, x1, y1]); every box (OCR, to-dos) stays in the scan's pixels. */
function frame() {
  const c = S.scanCrop;
  if (c) return [c[0], c[1], c[2] - c[0], c[3] - c[1]];
  const size = (res && res.size) || (img.naturalWidth ? [img.naturalWidth, img.naturalHeight] : null);
  return size && [0, 0, size[0], size[1]];
}

/** A wavy line under box [x, y, w, h], scaled to its height (the scan's own pixels). */
function wavy([x, y, bw, bh], cls = "ojit", lower = 0) {
  // tight under the word: green in the box's own descender band, purple just under the box, so neither
  // reaches the line below
  const amp = Math.max(1.5, bh * 0.05), half = Math.max(4, bh * 0.18);
  const n = Math.max(1, Math.round(bw / (2 * half))), step = bw / (2 * n);
  let d = `M${x},${lower ? y + bh + amp * 0.3 : y + bh - amp}`;
  for (let k = 0; k < 2 * n; k++) d += ` q${step / 2},${k % 2 ? amp * 2 : -amp * 2} ${step},0`;
  return svgEl("path", { d, class: cls });
}

/** The page's italics issue for an entry of res.italics (same field and way, the words overlapping), or null. */
function issueOf(r) {
  return (S.issues || []).find((it) => /^ocr_italic/.test(it.kind) && it.proposal && it.proposal.scan
    && it.proposal.scan.path === r.path && it.proposal.scan.to === r.to && it.proposal.scan.a < r.b && r.a < it.proposal.scan.b) || null;
}
/** Tagged false positive: the scan's reading set aside, so not drawn as a mismatch (Accept all leaves it too). */
const dismissed = (r) => { const it = issueOf(r); return !!it && it.status === "false_positive"; };

/** Runs [first, last + 1) of the words of a french_translation, one per field; a word the JSON lacks
 *  (no path) between two of the same field stays in. */
const isFtr = (w) => !!w.path && /(^|\/)french_translation$/.test(w.path);
function ftrRuns(words) {
  const runs = [];
  for (let i = 0; i < words.length;) {
    if (!isFtr(words[i])) { i++; continue; }
    let j = i + 1, last = i;
    while (j < words.length && (words[j].path === words[i].path || !words[j].path)) { if (words[j].path) last = j; j++; }
    runs.push([i, last + 1]);
    i = last + 1;
  }
  return runs;
}

function draw() {
  svg.replaceChildren();
  const todos = (S.issues || []).filter((it) => it.kind === "todo" && it.box);
  const fr = frame();
  run.hidden = !on || res !== null || img.hidden;
  filterBar.hidden = !on || !res;
  count.hidden = !on || !res;
  tessBtn.hidden = !on || !res || res.tess !== false;
  svg.hidden = img.hidden || !fr;
  if (svg.hidden) return;
  svg.setAttribute("viewBox", fr.join(" "));
  if (on && res) {
    const counts = {
      missing: res.words.filter((w) => w.s === "missing").length,
      extra: res.extra.length,
      diff: res.words.filter((w) => w.s === "diff").length,
      near: res.words.filter((w) => w.s === "near").length,
      both: res.words.filter((w) => w.s === "both").length,
      italics: res.italics.length,
      jsonit: res.words.filter((w) => w.it).length,
      ftr: ftrRuns(res.words).length,
    };
    for (const [k, label] of TYPES) {
      const b = filterBtns[k];
      b.textContent = `${counts[k]} ${label}`;
      b.classList.toggle("on", active.has(k));
      b.classList.toggle("zero", !counts[k]);
    }
    const flags = activeFlags();
    count.textContent = flags.length ? "Next ›" : Object.entries(counts).some(([k, n]) => n && k !== "jsonit" && k !== "ftr") ? "" : "all match";
    count.disabled = !flags.length;
    res.words.forEach((w, i) => {
      for (const [x, y, bw, bh] of w.boxes) {
        const r = svgEl("rect", { x, y, width: bw, height: bh, class: `ow${i === cur ? " cur" : ""}` });
        r.dataset.i = i;
        r.append(svgEl("title"));
        r.lastChild.textContent = (w.s === "missing" ? `${w.t}: not in the JSON`
          : w.path ? `${w.by === "tess" || w.tt ? `Kraken «${w.t}»` + (w.tt ? ` · Tesseract «${w.tt}»` : "") : w.t} → ${S.data && textAt(w)} (${w.path})` : w.t)
          + (w.sl == null ? "" : `\nSlant ${w.sl}° (${w.sl >= 9 ? "italic" : w.sl <= 4 ? "roman" : "unsure"})`);
        svg.append(r);
      }
    });
    for (let i = 0; i < res.words.length;) {
      const st = res.words[i].s;
      if (!FLAGS.includes(st) || !active.has(st)) { i++; continue; }
      let j = i + 1;
      while (j < res.words.length && res.words[j].s === st) j++;
      const boxes = mergeLineBoxes(res.words.slice(i, j).flatMap((w) => w.boxes));
      for (const [x, y, bw, bh] of boxes) {
        svg.append(svgEl("rect", { x: x - 10, y: y - 2, width: bw + 20, height: bh + 4, class: `ow-flag s-${st}` }));
      }
      i = j;
    }
    if (active.has("jsonit")) {
      // red where the scan prints roman and the JSON has italics: italic that should not be
      const roman = new Set(res.italics.filter((r) => r.to === "roman" && !dismissed(r))
                                       .flatMap((r) => Array.from({ length: r.words[1] - r.words[0] + 1 }, (_, k) => r.words[0] + k)));
      for (let i = 0; i < res.words.length;) {
        if (!res.words[i].it) { i++; continue; }
        const wrong = roman.has(i);
        let j = i + 1;
        while (j < res.words.length && res.words[j].it && roman.has(j) === wrong) j++;
        for (const b of mergeLineBoxes(res.words.slice(i, j).flatMap((w) => w.boxes))) svg.append(wavy(b, wrong ? "ojit wrong" : "ojit"));
        i = j;
      }
    }
    if (active.has("ftr")) {
      for (const [i, j] of ftrRuns(res.words))
        for (const b of mergeLineBoxes(res.words.slice(i, j).flatMap((w) => w.boxes))) svg.append(wavy(b, "oftr", 1));
    }
    if (active.has("italics")) {
      for (const it of res.italics) {
        if (dismissed(it)) continue;
        const ws = res.words.slice(it.words[0], it.words[1] + 1);
        if (it.to === "roman" && active.has("jsonit") && ws.every((w) => w.it)) continue;  // the red underline says it
        const boxes = mergeLineBoxes(res.words.slice(it.words[0], it.words[1] + 1).flatMap((w) => w.boxes));
        for (const [x, y, bw, bh] of boxes) {
          svg.append(svgEl("rect", { x: x - 12, y: y - 3, width: bw + 24, height: bh + 6, class: "oit" }));
        }
      }
    }
  }
  for (const it of todos) {
    const [x, y, bw, bh] = it.box;
    const r = svgEl("rect", { x, y, width: bw, height: bh, class: "otodo" + (it.status === "resolved" ? " done" : "") });
    r.append(svgEl("title"));
    r.lastChild.textContent = `To-do: ${it.msg}`;
    svg.append(r);
  }
  if (drag && drag.rect) svg.append(drag.rect);
  markExtra();
}

const fieldOf = (path) => (S.fields || []).find((x) => x.path.join("/") === path);
function textAt(w) {
  const f = fieldOf(w.path);
  return f ? (f.field.text || "").slice(w.a, w.b) : "";
}

new ResizeObserver(() => {
  svg.style.width = `${img.width}px`;
  svg.style.height = `${img.height}px`;
}).observe(img);
img.addEventListener("load", () => draw());

// Locate where a missing word (or run of missing words) belongs in the JSON text
function placeWord(i, j) {
  let prev = null, nxt = null;
  for (let k = i - 1; k >= 0; k--) if (res.words[k].path) { prev = res.words[k]; break; }
  for (let k = j + 1; k < res.words.length; k++) if (res.words[k].path) { nxt = res.words[k]; break; }

  if (prev && nxt && prev.path === nxt.path) {
    const f = fieldOf(prev.path);
    if (!f) return null;
    const s = f.field.text || "";
    let pos = prev.b;
    while (pos < nxt.a && s[pos] !== " ") pos++;
    if (pos < nxt.a && s[pos] === " ") {
      let end = pos + 1;
      while (end < nxt.a && s[end] === " ") end++;
      return { path: prev.path, start: pos, end };
    }
    if (prev.b < nxt.a) return { path: prev.path, start: prev.b, end: nxt.a };
    if (prev.b < s.length && s[prev.b] === " ") return { path: prev.path, start: prev.b, end: prev.b + 1 };
    if (prev.b > 0 && s[prev.b - 1] === " ") return { path: prev.path, start: prev.b - 1, end: prev.b };
    return { path: prev.path, start: Math.min(s.length, prev.b), end: Math.min(s.length, prev.b + 1) };
  }

  if (prev) {
    const f = fieldOf(prev.path);
    if (!f) return null;
    const s = f.field.text || "";
    let pos = prev.b;
    while (pos < s.length && ",.;:!?)»_}".includes(s[pos])) pos++;
    if (pos < s.length && s[pos] === " ") {
      let end = pos + 1;
      while (end < s.length && s[end] === " ") end++;
      return { path: prev.path, start: pos, end };
    }
    if (pos > 0 && s[pos - 1] === " ") return { path: prev.path, start: pos - 1, end: pos };
    return { path: prev.path, start: Math.max(0, Math.min(s.length - 1, prev.b)), end: Math.min(s.length, prev.b + 1) };
  }

  if (nxt) {
    const f = fieldOf(nxt.path);
    if (!f) return null;
    const s = f.field.text || "";
    let pos = nxt.a;
    if (pos > 0 && s[pos - 1] === " ") {
      let start = pos - 1;
      while (start > 0 && s[start - 1] === " ") start--;
      return { path: nxt.path, start, end: pos };
    }
    if (pos < s.length && s[pos] === " ") return { path: nxt.path, start: pos, end: pos + 1 };
    return { path: nxt.path, start: Math.max(0, Math.min(s.length - 1, nxt.a)), end: Math.min(s.length, nxt.a + 1) };
  }

  return null;
}

function findMissingSpaces() {
  if (!res || !active.has("missing")) return [];
  const ranges = [], seen = new Set();
  for (let i = 0; i < res.words.length; i++) {
    const w = res.words[i];
    if (w.s !== "missing") continue;
    let j = i;
    while (j + 1 < res.words.length && res.words[j + 1].s === "missing") j++;
    const loc = placeWord(i, j);
    if (loc && loc.start < loc.end) {
      const key = `${loc.path}:${loc.start}-${loc.end}`;
      if (!seen.has(key)) {
        seen.add(key);
        const r = rangeIn(loc.path, loc.start, loc.end);
        if (r) ranges.push(r);
      }
    }
    i = j;
  }
  return ranges;
}

// --- the JSON's words the scan lacks, underlined in the text (CSS highlights: the DOM is left alone) ---
function markExtra() {
  if (!globalThis.CSS || !CSS.highlights) return;
  const extra = [], here = [], italic = [], wrong = [], missing = [];
  if (on && res) {
    if (active.has("extra")) for (const w of res.extra) { const r = rangeIn(w.path, w.a, w.b); if (r) extra.push(r); }
    // italic in the JSON, roman on the scan: red, as on the scan; the other way: green
    if (active.has("italics")) for (const it of res.italics) { if (dismissed(it)) continue; const r = rangeIn(it.path, it.a, it.b); if (r) (it.to === "roman" ? wrong : italic).push(r); }
    if (active.has("missing")) for (const r of findMissingSpaces()) missing.push(r);
    const w = res.words[cur];
    if (w && w.path) { const r = rangeIn(w.path, w.a, w.b); if (r) here.push(r); }
    else if (w && w.s === "missing") {
      const loc = placeWord(cur, cur);
      if (loc) { const r = rangeIn(loc.path, loc.start, loc.end); if (r) here.push(r); }
    }
  }
  CSS.highlights.set("ocr-extra", new Highlight(...extra));
  CSS.highlights.set("ocr-missing", new Highlight(...missing));
  CSS.highlights.set("ocr-here", new Highlight(...here));
  CSS.highlights.set("ocr-italic", new Highlight(...italic));
  CSS.highlights.set("ocr-italic-wrong", new Highlight(...wrong));
}

function rangeIn(path, a, b) {
  const f = fieldOf(path);
  if (!f) return null;
  const walk = document.createTreeWalker(f.field.el, NodeFilter.SHOW_TEXT);
  const r = document.createRange();
  let n = 0, started = false;
  while (walk.nextNode()) {
    const t = walk.currentNode, len = t.length;
    if (!started && a <= n + len) { r.setStart(t, a - n); started = true; }
    if (started && b <= n + len) { r.setEnd(t, b - n); return r; }
    n += len;
  }
  return null;
}

// --- scan → text ---
function goToText(i) {
  const w = res.words[i];
  cur = i;
  draw();
  scrollScanTo(w);
  if (!w.path) {
    const loc = placeWord(i, i);
    if (loc) {
      const f = fieldOf(loc.path);
      if (f) {
        f.field.el.focus({ preventScroll: true });
        f.field.select(loc.start, loc.end);
        f.field.el.scrollIntoView({ block: "nearest" });
        const sel = getSelection();
        if (sel.rangeCount) sel.getRangeAt(0).startContainer.parentElement?.scrollIntoView({ block: "center" });
      }
    }
    toast(`“${w.t}” is not in the JSON`);
    return;
  }
  const f = fieldOf(w.path);
  if (!f) { toast(`“${w.t}” is in ${w.path}, not shown (the section filter?)`); return; }
  f.field.el.focus({ preventScroll: true });
  f.field.select(w.a, w.b);
  f.field.el.scrollIntoView({ block: "nearest" });
  const sel = getSelection();
  if (sel.rangeCount) sel.getRangeAt(0).startContainer.parentElement?.scrollIntoView({ block: "center" });
}

function scrollScanTo(w) {
  const [x, y, bw, bh] = w.boxes[0];
  const [fx, fy, fw] = frame();
  const k = img.width / fw;
  const left = (x - fx) * k, top = (y - fy) * k;
  if (left < view.scrollLeft || left + bw * k > view.scrollLeft + view.clientWidth) view.scrollLeft = left - view.clientWidth / 3;
  if (top < view.scrollTop || top + bh * k > view.scrollTop + view.clientHeight) view.scrollTop = top - view.clientHeight / 3;
}

/** A pointer's place on the scan, in the image's pixels. */
function scanPoint(e) {
  const r = img.getBoundingClientRect();
  const [fx, fy, fw, fh] = frame();
  return [fx + (e.clientX - r.left) * fw / r.width, fy + (e.clientY - r.top) * fh / r.height];
}

let down = null;
view.addEventListener("pointerdown", (e) => { down = [e.clientX, e.clientY]; });
view.addEventListener("click", (e) => {
  if (!on || !res || !down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4) return;  // a pan, not a click
  const [px, py] = scanPoint(e);
  const i = res.words.findIndex((w) => w.boxes.some(([x, y, bw, bh]) => px >= x && px <= x + bw && py >= y && py <= y + bh));
  if (i >= 0) { goToText(i); showActions(i, e.clientX, e.clientY); }
  else pop.hidden = true;
});

// --- a clicked word's actions: insert it, take the scan's reading, toggle its italics ---
const pop = Object.assign(document.createElement("div"), { id: "ocr-pop", hidden: true });
document.body.append(pop);
pop.addEventListener("mousedown", (e) => e.preventDefault());  // the field keeps its selection
document.addEventListener("keydown", (e) => { if (e.key === "Escape") pop.hidden = true; });
document.addEventListener("pointerdown", (e) => { if (!pop.contains(e.target) && !view.contains(e.target)) pop.hidden = true; });
let popAt = 0;  // when the menu opened: the scroll its own click starts (the word brought into view) leaves it open
$("scan-view").addEventListener("scroll", () => { if (performance.now() - popAt > 400) pop.hidden = true; });

const EDGE = /^[^\p{L}\p{N}]*|[^\p{L}\p{N}]*$/gu;  // a word's punctuation and _ around its letters
const core = (t) => t.replace(EDGE, "");

/** The run of words of the same status around i (the missing words read together). */
function runOf(i) {
  let a = i, b = i;
  const st = res.words[i].s;
  while (a > 0 && res.words[a - 1].s === st) a--;
  while (b + 1 < res.words.length && res.words[b + 1].s === st) b++;
  return [a, b];
}

/** The text's red words (not on the scan) where the scan's missing run i..j belongs: [{a, b}] in loc.path, or []. */
function extrasAt(i, j, loc) {
  let prev = null, nxt = null;
  for (let k = i - 1; k >= 0 && !prev; k--) if (res.words[k].path) prev = res.words[k];
  for (let k = j + 1; k < res.words.length && !nxt; k++) if (res.words[k].path) nxt = res.words[k];
  const f = fieldOf(loc.path)?.field;
  if (!f) return [];
  const s = f.text, ex = res.extra.filter((x) => x.path === loc.path).sort((x, y) => x.a - y.a);
  const gap = (a, b) => a <= b && !/[\p{L}\p{N}]/u.test(s.slice(a, b));  // nothing but spaces and punctuation
  const out = [];
  if (prev && prev.path === loc.path) {  // the red words right after the previous word, up to the next one
    let at = prev.b;
    const end = nxt && nxt.path === loc.path ? nxt.a : s.length;
    for (const x of ex) if (x.a >= at && x.b <= end && gap(at, x.a)) { out.push(x); at = x.b; }
  } else if (nxt && nxt.path === loc.path) {  // or right before the next word
    let at = nxt.a;
    for (const x of [...ex].reverse()) if (x.b <= at && gap(x.b, at)) { out.unshift(x); at = x.a; }
  }
  return out;
}

/** The scan's words i..j as modern text with their printed punctuation (server side: the modernization is
 * Python's), the marks to check said in a toast; the bare words when the server can't. */
async function printedWords(i, j) {
  const ws = res.words.slice(i, j + 1);
  const r = await api("/api/printed", { words: ws.map((w) => ({ pt: w.pt || w.t, wc: w.wc })) });
  if (r.status !== 200) return ws.map((w) => w.t).join(" ");
  const { text, flags } = r.body, WHY = { stop_lower: "stop then lowercase", inner: "mark inside a word",
    doubled: "two marks", low_conf: "mark read unsure", no_end: "no closing mark" };
  if (flags.length) toast("Check: " + flags.map((g) => `«${text.slice(Math.max(0, g.a - 8), g.b + 6)}» (${WHY[g.why] || g.why})`).join("; "));
  return text;
}

/** Put the scan's words i..j into the text where they belong: over the text's red words there, if any
 * (when i..j is the whole missing run), else between the words around. */
async function insertWords(i, j) {
  if (!placeWord(i, j)) { toast("No place found in the text for it"); return; }
  const t = await printedWords(i, j);
  const loc = placeWord(i, j), f = loc && fieldOf(loc.path)?.field;  // placed again: the text may have moved meanwhile
  if (!f) { toast("No place found in the text for it"); return; }
  const s = f.text;
  const [ra, rb] = runOf(i), ex = ra === i && rb === j ? extrasAt(i, j, loc) : [];
  if (ex.length) {  // the text's own marks around the red words stay, unless the scan prints its own there
    const a = ex[0].a, b = ex[ex.length - 1].b, old = s.slice(a, b);
    const lead = t.match(/^[^\p{L}\p{N}]*/u)[0] ? "" : old.match(/^[^\p{L}\p{N}]*/u)[0];
    const trail = t.match(/[^\p{L}\p{N}]*$/u)[0] ? "" : old.match(/[^\p{L}\p{N}]*$/u)[0];
    f.edit(a, b, lead + t + trail);
    return;
  }
  if (/^\s+$/.test(s.slice(loc.start, loc.end))) {
    f.edit(loc.start, loc.end, (loc.start > 0 ? " " : "") + t + (loc.end < s.length ? " " : ""));
  } else {
    const at = loc.start, before = at > 0 && !/\s/.test(s[at - 1]);
    f.edit(at, at, before ? ` ${t}` : `${t} `);
  }
}

/** The text's word i replaced by the scan's reading, its punctuation and italics marks kept. */
function useScan(w) {
  const f = fieldOf(w.path)?.field;
  if (!f) return;
  const old = f.text.slice(w.a, w.b), lead = old.match(/^[^\p{L}\p{N}]*/u)[0], trail = old.match(/[^\p{L}\p{N}]*$/u)[0];
  f.edit(w.a, w.b, lead + core(w.t) + trail);
}

function toggleItalic(path, a, b) {
  const f = fieldOf(path)?.field;
  if (!f) return;
  f.select(a, b);
  f.toggleItalic();
}

function showActions(i, x, y) {
  const w = res.words[i], acts = [];
  if (w.s === "missing") {
    const [a, b] = runOf(i), loc = placeWord(a, b), f = loc && fieldOf(loc.path)?.field;
    const ex = f ? extrasAt(a, b, loc) : [], words = res.words.slice(a, b + 1).map((x) => x.t).join(" ");
    const old = ex.length ? `“${f.text.slice(ex[0].a, ex[ex.length - 1].b)}”` : "";
    if (old) acts.push([`Replace ${old} with “${words}”`, () => insertWords(a, b)]);
    if (b > a || !old) acts.push([`Insert “${w.t}”`, () => insertWords(i, i)]);
    if (b > a && !old) acts.push([`Insert all ${b - a + 1}: “${words}”`, () => insertWords(a, b)]);
  } else if (w.path) {
    const now = textAt(w);
    if ((w.s === "diff" || w.s === "near" || w.s === "both") && core(w.t) && core(w.t) !== core(now)) acts.push([`Use the scan’s “${core(w.t)}”`, () => useScan(w)]);
    const it = res.italics.find((r) => r.words[0] <= i && i <= r.words[1]);
    if (it) {
      const n = it.words[1] - it.words[0] + 1;
      acts.push([`Make ${n > 1 ? `these ${n} words` : "it"} ${it.to} (scan)`, () => toggleItalic(it.path, it.a, it.b)]);
      const iss = issueOf(it);
      if (iss && iss.status === "false_positive") acts.push(["Not a false positive: reopen", () => tagFalsePositive(iss, false)]);
      else if (iss && !iss.status) acts.push([`False positive: keep ${n > 1 ? "them" : "it"} ${it.to === "roman" ? "italic" : "roman"}`, () => tagFalsePositive(iss, true)]);
    }
    acts.push([`Italic / roman${w.sl == null ? "" : ` (slant ${w.sl}°)`}`, () => toggleItalic(w.path, w.a, w.b)]);
  }
  if (!acts.length) { pop.hidden = true; return; }
  pop.replaceChildren(...acts.map(([label, act]) => Object.assign(document.createElement("button"), {
    textContent: label, onclick: () => { pop.hidden = true; act(); },
  })));
  pop.hidden = false;
  popAt = performance.now();
  pop.style.left = `${Math.min(innerWidth - pop.offsetWidth - 4, Math.max(4, x - pop.offsetWidth / 2))}px`;
  pop.style.top = `${y + 14 + pop.offsetHeight > innerHeight ? y - pop.offsetHeight - 10 : y + 14}px`;
}

/** Tag an italics issue false positive (or open it again) without leaving the page: Accept all on page
 *  then leaves it, and the scan stops flagging it. */
async function tagFalsePositive(iss, on_) {
  const r = on_ ? await api("/api/proposal/reject", { id: iss.id, proposal_id: iss.proposal.id })
                : await api("/api/mark", { id: iss.id, status: null });
  if (r.status !== 200) { toast(r.body.error || "Could not tag it"); return; }
  if (on_) {
    const w = (iss.proposal.word || "").trim();
    api("/api/note", { section: "FALSE POSITIVE ITALICS", text: w ? `${w} (${iss.book_dir} p.${iss.page})` : `${iss.book_dir} p.${iss.page}` });
  }
  setStatus(iss.id, on_ ? "false_positive" : null);
  toast(on_ ? "Tagged false positive" : "Open again", "ok");
  draw();
  renderIssues();
  refreshCounts();
}

// --- text → scan ---
document.addEventListener("selectionchange", () => {
  if (!on || !res) return;
  const s = getSelection();
  if (!s.rangeCount) return;
  const f = (S.fields || []).find((x) => x.field.el.contains(s.anchorNode));
  if (!f) return;
  const path = f.path.join("/"), sel = f.field.selection();
  if (!sel) return;
  const k = sel[0];
  const i = res.words.findIndex((w) => w.path === path && w.a <= k && k <= w.b);
  if (i < 0 || i === cur) return;
  cur = i;
  draw();
  scrollScanTo(res.words[i]);
});

// --- a region to-do: Shift-drag, or "Box" then drag (before the scan's own pan sees the pointer) ---
let drag = null;
$("scan-pane").addEventListener("pointerdown", (e) => {
  if (!view.contains(e.target) || img.hidden || !(e.shiftKey || region.classList.contains("on"))) return;
  e.stopPropagation();
  e.preventDefault();
  const [x, y] = scanPoint(e);
  down = null;  // not a click
  drag = { x, y, rect: svgEl("rect", { x, y, width: 0, height: 0, class: "otodo drawing" }) };
  svg.append(drag.rect);
  view.setPointerCapture(e.pointerId);
}, true);
view.addEventListener("pointermove", (e) => {
  if (!drag) return;
  e.stopImmediatePropagation();
  const [x, y] = scanPoint(e);
  Object.entries({ x: Math.min(x, drag.x), y: Math.min(y, drag.y), width: Math.abs(x - drag.x), height: Math.abs(y - drag.y) })
    .forEach(([k, v]) => drag.rect.setAttribute(k, v));
});
view.addEventListener("pointerup", async () => {
  if (!drag) return;
  const b = ["x", "y", "width", "height"].map((k) => Math.round(+drag.rect.getAttribute(k)));
  drag = null;
  region.classList.remove("on");
  if (b[2] < 8 || b[3] < 8) { draw(); return; }
  const words = res ? res.words.filter((w) => w.boxes.some(([x, y, bw, bh]) => x < b[0] + b[2] && x + bw > b[0] && y < b[1] + b[3] && y + bh > b[1])) : [];
  const said = words.map((w) => w.t).join(" ");
  const linked = words.find((w) => w.path);
  draw();
  await todoPrompt(linked ? whereOf(linked.path) : null, b, said ? `the region “${said.length > 60 ? said.slice(0, 60) + "…" : said}”` : "this region");
  draw();
});

// --- when to fetch again: a page drawn, saved, or edited (the alignment then follows the typed text) ---
hooks.afterRender.push(() => {
  if (`${S.vol}/${S.page}` !== shownFor) refresh();
  else draw();
});
const prevSave = hooks.afterSave;
hooks.afterSave = () => { refresh(); return prevSave && prevSave(); };
let edits = 0;  // the fields edit their string (no input events): look at the count of edits
setInterval(() => {
  if (S.edits === edits) return;
  edits = S.edits;
  if (on && res) refresh();
}, 1000);
