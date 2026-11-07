// "Merged": the page as /merge built it (data/<vol>/merged), read-only, the words taken from Good
// underlined blue and wavy. The editor's own text is normalized; this only shows what the merge makes of it.
import { S, api, hooks, renderPage, showScan, toast } from "./app.js";
import { render } from "./field.js";

const $ = (id) => document.getElementById(id);

let on = false;
try { on = localStorage.getItem("rw-merged") === "1"; } catch (e) {}
const cache = new Map();  // "vol:page" -> {data, marks} | "loading"

const btn = document.createElement("button");
Object.assign(btn, { id: "merged-btn", textContent: "Merged", className: on ? "on" : "",
  title: "Show the page as /merge built it (read-only); the words taken from Good are underlined in blue; the scan switches to Good_Calmet" });
$("sections").insertBefore(btn, $("sections").querySelector(".grow"));
btn.onclick = () => {
  on = !on;
  btn.classList.toggle("on", on);
  try { localStorage.setItem("rw-merged", on ? "1" : "0"); } catch (e) {}
  if (hooks.collect) hooks.collect();
  const top = $("text-pane").scrollTop;
  scanTo(on);  // the scan of Good_Calmet beside its text
  cache.delete(`${S.vol}:${S.page}`);  // fresh: a decision may have been made since
  renderPage();
  $("text-pane").scrollTop = top;
};

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

function at(data, path) {
  let x = data;
  for (const p of path.split("/")) { if (x == null) return undefined; x = x[p]; }
  return x;
}

hooks.afterRender.push((root) => {
  document.body.classList.toggle("merged-view", on);
  if (!on) { shown = null; drawScan(); return; }
  scanTo(true);
  const k = `${S.vol}:${S.page}`;
  const hit = cache.get(k);
  if (!hit) {
    cache.set(k, "loading");
    api(`/api/merged?vol=${encodeURIComponent(S.vol)}&page=${S.page}`).then((r) => {
      cache.set(k, r.status === 200 ? r.body : { data: null, marks: {} });
      if (on && k === `${S.vol}:${S.page}`) renderPage();
    });
    return;
  }
  if (hit === "loading") return;
  shown = hit;
  drawScan();
  if (!hit.data) { toast("No merged text for this page: nothing was decided in /merge here"); return; }
  for (const f of root.querySelectorAll(".f[data-path]")) {
    const v = at(hit.data, f.dataset.path);
    if (typeof v !== "string") continue;
    f.contentEditable = "false";
    f.classList.add("mv");
    render(f, v, null, hit.marks[f.dataset.path] || null);
  }
});
