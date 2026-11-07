// "Merged": the page as /merge built it (data/<vol>/merged), editable. The words taken from Good are underlined
// blue and wavy; what is typed here is kept apart from the build (docs/good_merge/<vol>.hand.json) and laid over
// it at every rebuild. When normalized, Good or a decision changes a hand-edited field underneath, the field is
// flagged: keep yours or take the rebuilt text. Every state is kept: ↶ brings the previous one back.
import { S, api, hooks, renderPage, showScan, toast } from "./app.js";
import { Field, render } from "./field.js";
import { save, setDirty, wireField } from "./edit.js";

const $ = (id) => document.getElementById(id);

let on = false;
try { on = localStorage.getItem("rw-merged") === "1"; } catch (e) {}
const cache = new Map();  // "vol:page" -> {data, marks, scan, hand} | "loading"
let mfields = [];  // [{path, field, was}] of the merged text drawn
const ck = () => `${S.vol}:${S.page}`;

const btn = document.createElement("button");
Object.assign(btn, { id: "merged-btn", textContent: "Merged", className: on ? "on" : "",
  title: "Edit the page as /merge built it; the words taken from Good are underlined in blue; the scan switches to Good_Calmet. Your typing here is kept over every rebuild." });
$("sections").insertBefore(btn, $("sections").querySelector(".grow"));
btn.onclick = async () => {
  if (S.dirty && !(await save({ redraw: false }))) return;  // the text of the view being left first
  on = !on;
  hooks.saveMerged = on ? saveMerged : null;
  btn.classList.toggle("on", on);
  try { localStorage.setItem("rw-merged", on ? "1" : "0"); } catch (e) {}
  if (hooks.collect) hooks.collect();
  const top = $("text-pane").scrollTop;
  scanTo(on);  // the scan of Good_Calmet beside its text
  cache.delete(ck());  // fresh: a decision may have been made since
  renderPage();
  $("text-pane").scrollTop = top;
};
hooks.saveMerged = on ? saveMerged : null;

const prevAfterSave = hooks.afterSave;
hooks.afterSave = () => { cache.delete(ck()); return prevAfterSave && prevAfterSave(); };  // normalized saved: merged rebuilt

// --- the fields: merged's text, typed apart from normalized (S.fields stays empty, so S.data is untouched) ---
const plainMake = hooks.makeField;
hooks.makeField = (f, name, value, path) => {
  if (!on) return plainMake(f, name, value, path);
  const hit = cache.get(ck());
  const k = path.join("/");
  const v = hit && hit !== "loading" && hit.data ? at(hit.data, k) : undefined;
  if (typeof v !== "string") {  // loading, no merged page, or not a text: shown, not editable
    f.classList.add("mv", "mv-ro");
    if (value === null || value === undefined) { f.textContent = "null"; f.classList.add("null"); }
    else render(f, String(value));
    return;
  }
  const h = hit.hand[k] || {};
  const field = new Field(f, { name, value: v, onChange: () => { S.edits++; setDirty(true); } });
  f.classList.add("mv");
  f.classList.toggle("mv-hand", !!h.edited);
  if (h.conflict) { f.contentEditable = "false"; f.classList.add("mv-ro", "mv-conflict"); }
  else wireField(field, name, () => mfields.map((x) => x.field));
  if (hit.marks[k]) field.setMarks(hit.marks[k]);
  mfields.push({ path: k, field, was: v });
};
const plainBefore = hooks.beforeRender;
hooks.beforeRender = () => { mfields = []; if (plainBefore) plainBefore(); };

async function saveMerged({ redraw = true } = {}) {
  const fields = {}, was = {};
  for (const x of mfields) {
    const t = x.field.value ?? "";
    if (t !== x.was) { fields[x.path] = t; was[x.path] = x.was; }
  }
  if (!Object.keys(fields).length) { setDirty(false); return true; }
  const edits = S.edits;
  const r = await api("/api/merged/save", { vol: S.vol, page: S.page, fields, was });
  if (r.status === 409) {
    toast("The merged text changed since the page loaded (a decision or a save): reload the page, your typing is not saved");
    return false;
  }
  if (r.status !== 200) { toast(r.body.error || "Save failed"); return false; }
  cache.set(ck(), r.body);
  if (S.edits !== edits) return true;  // typed during the save: still unsaved
  setDirty(false);
  $("dirty").textContent = "saved";
  setTimeout(() => { if (!S.dirty) $("dirty").textContent = ""; }, 1500);
  if (redraw) redrawKeep();
  return true;
}

function redrawKeep() {
  const top = $("text-pane").scrollTop;
  renderPage();
  $("text-pane").scrollTop = top;
}

/** A flagged or hand-edited field's bar: what changed underneath, keep mine / take rebuilt, undo. */
function bar(path, h) {
  const b = document.createElement("div");
  b.className = "mv-bar";
  const act = async (url, body, done) => {
    if (S.dirty && !(await saveMerged({ redraw: false }))) return;
    const r = await api(url, { vol: S.vol, page: S.page, path, ...body });
    if (r.status !== 200) { toast(r.body.error || "Failed"); return; }
    cache.set(ck(), r.body);
    redrawKeep();
    if (done) toast(done);
  };
  const button = (text, title, fn, cls = "") => {
    const x = document.createElement("button");
    Object.assign(x, { textContent: text, title, className: cls, onclick: fn });
    return x;
  };
  if (h.conflict) {
    const msg = document.createElement("span");
    msg.className = "mv-msg";
    msg.textContent = h.conflict.why === "gone"
      ? "⚠ This field is no longer on the rebuilt page; your text is kept here."
      : "⚠ The text under your edit changed (normalized, Good or a decision). Your text is kept; choose:";
    b.append(msg);
    if (h.conflict.why !== "gone") {
      const diff = document.createElement("div");
      diff.className = "mv-diff";
      diff.hidden = true;
      const line = (label, t) => {
        const d = document.createElement("div");
        const l = document.createElement("b");
        l.textContent = label;
        d.append(l, " ", t ?? "");
        return d;
      };
      diff.append(line("Built when you typed:", h.was), line("Built now:", h.conflict.built));
      b.append(button("What changed", "Show the built text then and now", () => { diff.hidden = !diff.hidden; }),
        button("Keep mine", "Keep your text; the flag goes", () => act("/api/merged/resolve", { choice: "mine" }, "Kept yours")),
        button("Take rebuilt", "Your text is replaced by the rebuilt one (↶ brings it back)",
          () => act("/api/merged/resolve", { choice: "theirs" }, "Rebuilt text taken: ↶ brings yours back"), "warn"),
        diff);
    }
  }
  if (h.versions) b.append(button("↶", "Undo: the field's previous version back", () => act("/api/merged/restore", {})));
  return b;
}

function at(data, path) {
  let x = data;
  for (const p of path.split("/")) { if (x == null) return undefined; x = x[p]; }
  return x;
}

let plain = true;  // the ordinary scan existed when Good_Calmet was put on by this toggle
function scanTo(good) {
  if (!S.good) return;
  if (good && !S.goodOn) { plain = !$("no-scan").hidden; S.goodOn = true; showScan(true); }
  else if (!good && S.goodOn) { S.goodOn = false; S.goodIdx = 0; showScan(plain); }
}

// --- the words taken from Good, wavy blue on the Good scan ---
const NS = "http://www.w3.org/2000/svg";
const layer = document.createElementNS(NS, "svg");
layer.id = "merged-scan";
layer.setAttribute("preserveAspectRatio", "none");
$("scan-view").append(layer);
let shown = null;  // {scan} of the page on screen

function lines(boxes) {
  const out = [];
  for (const b of boxes) {
    const l = out[out.length - 1];
    if (l && b[0] >= l[0] && b[0] - (l[0] + l[2]) < 120 && Math.abs((b[1] + b[3] / 2) - (l[1] + l[3] / 2)) < Math.max(b[3], l[3]) * 0.8) {
      const x2 = Math.max(l[0] + l[2], b[0] + b[2]), y2 = Math.max(l[1] + l[3], b[1] + b[3]);
      out[out.length - 1] = [l[0], Math.min(l[1], b[1]), x2 - l[0], y2 - Math.min(l[1], b[1])];
    } else out.push([...b]);
  }
  return out;
}

function drawScan() {
  const img = $("scan-img");
  layer.replaceChildren();
  const boxes = on && S.goodOn && shown && shown.scan[String(S.goodIdx || 0)];
  if (!boxes || !img.naturalWidth) { layer.style.display = "none"; return; }
  layer.style.display = "";
  layer.setAttribute("viewBox", `0 0 ${img.naturalWidth} ${img.naturalHeight}`);
  Object.assign(layer.style, { width: `${img.width}px`, height: `${img.height}px` });
  for (const [x, y, w, h] of lines(boxes)) {
    const amp = Math.max(1.5, h * 0.05), half = Math.max(4, h * 0.18);
    const n = Math.max(1, Math.round(w / (2 * half))), step = w / (2 * n);
    let d = `M${x},${y + h - amp}`;
    for (let k = 0; k < 2 * n; k++) d += ` q${step / 2},${k % 2 ? amp * 2 : -amp * 2} ${step},0`;
    const p = document.createElementNS(NS, "path");
    p.setAttribute("d", d);
    layer.append(p);
  }
}
$("scan-img").addEventListener("load", drawScan);
new ResizeObserver(drawScan).observe($("scan-img"));

hooks.afterRender.push((root) => {
  document.body.classList.toggle("merged-view", on);
  if (!on) { shown = null; drawScan(); return; }
  scanTo(true);
  const k = `${S.vol}:${S.page}`;
  const hit = cache.get(k);
  if (!hit) {
    cache.set(k, "loading");
    api(`/api/merged?vol=${encodeURIComponent(S.vol)}&page=${S.page}`).then((r) => {
      cache.set(k, r.status === 200 ? r.body : { data: null, marks: {}, hand: {} });
      if (on && k === `${S.vol}:${S.page}`) renderPage();
    });
    return;
  }
  if (hit === "loading") return;
  shown = hit;
  drawScan();
  if (!hit.data) { toast("No merged text for this page: nothing was decided in /merge here"); return; }
  for (const f of root.querySelectorAll(".f.mv[data-path]")) {
    const h = hit.hand[f.dataset.path];
    if (h && (h.conflict || h.versions) && !f.closest(".inl")) f.after(bar(f.dataset.path, h));
  }
});
