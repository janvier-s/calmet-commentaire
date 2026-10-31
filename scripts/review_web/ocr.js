// The scan's OCR (Kraken) drawn over it: every word the JSON lacks in red, a different word in amber,
// a near one (a slip, or old spelling the key misses) outlined. Click a box: its place in the text;
// the caret in a field: its word on the scan. Shift-drag on the scan (or "Box" then drag) draws a
// region and adds a to-do for it; a page's region to-dos are drawn whenever it is open. Words printed in
// italics where the text has roman, or the other way (their slant on the scan), are outlined in green.
// The OCR is only a witness for the review, never a source of text.
import { S, api, hooks, toast } from "./app.js";
import { typedData } from "./edit.js";
import { todoPrompt, whereOf } from "./todo.js";

const $ = (id) => document.getElementById(id);
const SVG = "http://www.w3.org/2000/svg";
const svgEl = (tag, attrs = {}) => {
  const e = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
};
const FLAGS = ["missing", "diff", "near"];
const TYPES = [
  ["missing", "missing", "Red: in the scan, not in the JSON (space shown red in the text)"],
  ["extra", "not on scan", "Red in the text: in the JSON, not on the scan"],
  ["diff", "diff", "Orange: a different word"],
  ["near", "near", "Orange dashed: nearly the same word"],
  ["italics", "italics", "Green: italic on the scan and roman in the text, or the other way"],
];

let on = false;
try { on = localStorage.getItem("rw-ocr") === "1"; } catch (e) {}
let active = new Set(TYPES.map(([k]) => k));
try {
  const saved = JSON.parse(localStorage.getItem("rw-ocr-filters"));
  if (Array.isArray(saved)) active = new Set(saved.filter((k) => TYPES.some(([t]) => t === k)));
} catch (e) {}
const saveFilters = () => { try { localStorage.setItem("rw-ocr-filters", JSON.stringify([...active])); } catch (e) {} };

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
const count = Object.assign(document.createElement("button"), { className: "link small", id: "ocr-count", hidden: true,
                                                                title: "Go to the next flagged word among the active filters" });
const run = Object.assign(document.createElement("button"), { textContent: "Read the scan", hidden: true,
                                                              title: "OCR this page with Kraken (about 15 s)" });
const region = Object.assign(document.createElement("button"), { textContent: "Box", title: "Drag a region on the scan for a to-do (or Shift-drag)" });
$("scan-tools").querySelector(".grow").before(box, filterBar, count, run, region);
check.onchange = () => {
  on = check.checked;
  try { localStorage.setItem("rw-ocr", on ? "1" : "0"); } catch (e) {}
  shownFor = null;
  refresh();
};
run.onclick = () => refresh(true);
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
async function refresh(runOcr = false) {
  const at = `${S.vol}/${S.page}`;
  if (!on || !S.vol) { res = null; draw(); return; }
  const n = ++pending;
  if (runOcr) { run.disabled = true; run.textContent = "Reading… (15 s)"; }
  const r = await api("/api/ocr", { vol: S.vol, page: S.page, data: S.fields.length ? typedData() : S.data, run: runOcr });
  run.disabled = false;
  run.textContent = "Read the scan";
  if (n !== pending || at !== `${S.vol}/${S.page}`) return;  // a later page or edit came meanwhile
  if (r.status !== 200) { toast(r.body.error || "No OCR"); res = null; }
  else res = r.body.ocr;
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

function draw() {
  svg.replaceChildren();
  const todos = (S.issues || []).filter((it) => it.kind === "todo" && it.box);
  const size = (res && res.size) || (img.naturalWidth ? [img.naturalWidth, img.naturalHeight] : null);
  run.hidden = !on || res !== null || img.hidden;
  filterBar.hidden = !on || !res;
  count.hidden = !on || !res;
  svg.hidden = img.hidden || !size;
  if (svg.hidden) return;
  svg.setAttribute("viewBox", `0 0 ${size[0]} ${size[1]}`);
  if (on && res) {
    const counts = {
      missing: res.words.filter((w) => w.s === "missing").length,
      extra: res.extra.length,
      diff: res.words.filter((w) => w.s === "diff").length,
      near: res.words.filter((w) => w.s === "near").length,
      italics: res.italics.length,
    };
    for (const [k, label] of TYPES) {
      const b = filterBtns[k];
      b.textContent = `${counts[k]} ${label}`;
      b.classList.toggle("on", active.has(k));
      b.classList.toggle("zero", !counts[k]);
    }
    const flags = activeFlags();
    count.textContent = flags.length ? "Next ›" : Object.values(counts).some(Boolean) ? "" : "all match";
    count.disabled = !flags.length;
    res.words.forEach((w, i) => {
      for (const [x, y, bw, bh] of w.boxes) {
        const r = svgEl("rect", { x, y, width: bw, height: bh, class: `ow${i === cur ? " cur" : ""}` });
        r.dataset.i = i;
        r.append(svgEl("title"));
        r.lastChild.textContent = w.s === "missing" ? `${w.t}: not in the JSON`
          : w.path ? `${w.t} → ${S.data && textAt(w)} (${w.path})` : w.t;
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
    if (active.has("italics")) {
      for (const it of res.italics) {
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
  const extra = [], here = [], italic = [], missing = [];
  if (on && res) {
    if (active.has("extra")) for (const w of res.extra) { const r = rangeIn(w.path, w.a, w.b); if (r) extra.push(r); }
    if (active.has("italics")) for (const it of res.italics) { const r = rangeIn(it.path, it.a, it.b); if (r) italic.push(r); }
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
  const k = img.width / ((res && res.size[0]) || img.naturalWidth);
  const left = x * k, top = y * k;
  if (left < view.scrollLeft || left + bw * k > view.scrollLeft + view.clientWidth) view.scrollLeft = left - view.clientWidth / 3;
  if (top < view.scrollTop || top + bh * k > view.scrollTop + view.clientHeight) view.scrollTop = top - view.clientHeight / 3;
}

/** A pointer's place on the scan, in the image's pixels. */
function scanPoint(e) {
  const r = img.getBoundingClientRect();
  const size = (res && res.size) || [img.naturalWidth, img.naturalHeight];
  return [(e.clientX - r.left) * size[0] / r.width, (e.clientY - r.top) * size[1] / r.height];
}

let down = null;
view.addEventListener("pointerdown", (e) => { down = [e.clientX, e.clientY]; });
view.addEventListener("click", (e) => {
  if (!on || !res || !down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4) return;  // a pan, not a click
  const [px, py] = scanPoint(e);
  const i = res.words.findIndex((w) => w.boxes.some(([x, y, bw, bh]) => px >= x && px <= x + bw && py >= y && py <= y + bh));
  if (i >= 0) goToText(i);
});

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
