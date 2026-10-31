// The scan's OCR (Kraken) drawn over it: every word the JSON lacks in red, a different word in amber,
// a near one (a slip, or old spelling the key misses) outlined. Click a box: its place in the text;
// the caret in a field: its word on the scan. Shift-drag on the scan (or "Box" then drag) draws a
// region and adds a to-do for it; a page's region to-dos are drawn whenever it is open.
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

let on = false;
try { on = localStorage.getItem("rw-ocr") === "1"; } catch (e) {}
let res = null;       // the alignment of the page shown: {size, words, extra}
let shownFor = null;  // "vol/page" it is for
let cur = -1;         // the word linked to the caret, or the last one clicked
let flagAt = -1;      // the last flag gone to with the counter

const view = $("scan-view"), img = $("scan-img");
const svg = svgEl("svg", { id: "ocr-layer", preserveAspectRatio: "none" });
view.append(svg);

// --- the tools ---
const box = Object.assign(document.createElement("label"), { className: "muted", title: "The OCR's words over the scan: red, missing from the JSON; amber, a different word" });
const check = Object.assign(document.createElement("input"), { type: "checkbox", checked: on });
box.append(check, " OCR");
const count = Object.assign(document.createElement("button"), { className: "link small", id: "ocr-count", hidden: true,
                                                                title: "Go to the next flagged word" });
const run = Object.assign(document.createElement("button"), { textContent: "Read the scan", hidden: true,
                                                              title: "OCR this page with Kraken (about 30 s)" });
const region = Object.assign(document.createElement("button"), { textContent: "Box", title: "Drag a region on the scan for a to-do (or Shift-drag)" });
$("scan-tools").querySelector(".grow").before(box, count, run, region);
check.onchange = () => {
  on = check.checked;
  try { localStorage.setItem("rw-ocr", on ? "1" : "0"); } catch (e) {}
  shownFor = null;
  refresh();
};
run.onclick = () => refresh(true);
region.onclick = () => region.classList.toggle("on");
count.onclick = () => {
  const flags = res ? res.words.map((w, i) => [w, i]).filter(([w]) => FLAGS.includes(w.s)) : [];
  if (!flags.length) return;
  const next = flags.find(([, i]) => i > flagAt) || flags[0];
  flagAt = next[1];
  goToText(next[1]);
};

// --- fetching and drawing ---
let pending = 0;
async function refresh(runOcr = false) {
  const at = `${S.vol}/${S.page}`;
  if (!on || !S.vol) { res = null; draw(); return; }
  const n = ++pending;
  if (runOcr) { run.disabled = true; run.textContent = "Reading… (30 s)"; }
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

function draw() {
  svg.replaceChildren();
  const todos = (S.issues || []).filter((it) => it.kind === "todo" && it.box);
  const size = (res && res.size) || (img.naturalWidth ? [img.naturalWidth, img.naturalHeight] : null);
  run.hidden = !on || res !== null || img.hidden;
  count.hidden = !on || !res;
  svg.hidden = img.hidden || !size;
  if (svg.hidden) return;
  svg.setAttribute("viewBox", `0 0 ${size[0]} ${size[1]}`);
  if (on && res) {
    const n = Object.fromEntries(FLAGS.map((s) => [s, res.words.filter((w) => w.s === s).length]));
    const parts = [[n.missing, "missing"], [n.diff, "diff"], [n.near, "near"], [res.extra.length, "not on scan"]].filter(([k]) => k);
    count.textContent = parts.length ? parts.map(([k, s]) => `${k} ${s}`).join(" · ") : "all match";
    count.title = "Red: in the scan, not in the JSON; amber: a different word; dashed: nearly the same; "
      + "“not on scan”: JSON words underlined in red in the text. Click: the next flagged word.";
    res.words.forEach((w, i) => {
      for (const [x, y, bw, bh] of w.boxes) {
        const r = svgEl("rect", { x, y, width: bw, height: bh, class: `ow s-${w.s}${i === cur ? " cur" : ""}` });
        r.dataset.i = i;
        r.append(svgEl("title"));
        r.lastChild.textContent = w.s === "missing" ? `${w.t}: not in the JSON`
          : w.path ? `${w.t} → ${S.data && textAt(w)} (${w.path})` : w.t;
        svg.append(r);
      }
    });
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

// --- the JSON's words the scan lacks, underlined in the text (CSS highlights: the DOM is left alone) ---
function markExtra() {
  if (!globalThis.CSS || !CSS.highlights) return;
  const extra = [], here = [];
  if (on && res) {
    for (const w of res.extra) { const r = rangeIn(w.path, w.a, w.b); if (r) extra.push(r); }
    const w = res.words[cur];
    if (w && w.path) { const r = rangeIn(w.path, w.a, w.b); if (r) here.push(r); }
  }
  CSS.highlights.set("ocr-extra", new Highlight(...extra));
  CSS.highlights.set("ocr-here", new Highlight(...here));
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
  if (!w.path) { toast(`“${w.t}” is not in the JSON`); return; }
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
