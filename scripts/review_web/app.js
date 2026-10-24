// The review editor's page: one module, state in S, the server in review_web.py.
import { render, ITALIC_FIELDS } from "./field.js";
import { parseRef } from "./text.js";

const $ = (id) => document.getElementById(id);
const el = (tag, props = {}, ...kids) => {
  const e = Object.assign(document.createElement(tag), props);
  e.append(...kids.filter((k) => k != null));
  return e;
};

export const S = {
  config: null, vol: null, page: null, pages: [], data: null, version: null,
  ctx: null, issues: [], around: null, section: "all",
  zoom: 1, dim: 10,
};

// --- server ---
export async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const ct = r.headers.get("Content-Type") || "";
  return { status: r.status, body: ct.includes("json") ? await r.json() : await r.text() };
}

export function toast(msg) {
  const t = el("div", { className: "toast", textContent: msg });
  document.body.append(t);
  setTimeout(() => t.remove(), 2600);
}

// --- pages ---
export async function loadPage(vol, page) {
  const r = await api(`/api/page?vol=${encodeURIComponent(vol)}&page=${page ?? ""}`);
  if (r.status === 404 && r.body.missing) return { missing: true, ...r.body };
  if (r.status !== 200) { toast(r.body.error || "Could not load the page"); return null; }
  page = r.body.page;
  Object.assign(S, { vol, page, data: r.body.data, version: r.body.version, ctx: r.body.context,
                     pages: r.body.pages, issues: r.body.issues, around: r.body.around });
  api("/api/state", { vol, page });
  showScan(r.body.scan);
  renderPage();
  updateTop();
  $("text-pane").scrollTop = 0;
  return S;
}

function updateTop() {
  $("vol").value = S.vol;
  $("page-num").value = S.page;
  document.title = `${S.vol} p.${S.page} · Calmet Review`;
}

// --- the scan ---
const ZOOM_STEPS = [0.5, 0.65, 0.8, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0];

function showScan(has) {
  const img = $("scan-img");
  $("no-scan").hidden = has;
  img.hidden = !has;
  $("scan-dim").hidden = !has;
  if (has) {
    img.onload = () => layoutScan();
    img.src = `/scan/${encodeURIComponent(S.vol)}/${S.page}`;
  }
}

function layoutScan(focus) {
  const view = $("scan-view"), img = $("scan-img");
  if (!img.naturalWidth) return;
  const before = { w: img.width || 1, x: view.scrollLeft, y: view.scrollTop };
  const w = Math.round((view.clientWidth - 2) * S.zoom);
  img.style.width = `${w}px`;
  const dim = $("scan-dim");
  Object.assign(dim.style, { width: `${img.width}px`, height: `${img.height}px`, opacity: S.dim / 100 });
  $("zoom-label").textContent = `${Math.round(S.zoom * 100)}%`;
  if (focus) {  // keep the point under the pointer still
    const k = w / before.w;
    view.scrollLeft = (before.x + focus.x) * k - focus.x;
    view.scrollTop = (before.y + focus.y) * k - focus.y;
  }
}

function zoomStep(dir, focus) {
  const i = ZOOM_STEPS.findIndex((z) => z >= S.zoom - 1e-6);
  const j = Math.max(0, Math.min(ZOOM_STEPS.length - 1, (i < 0 ? ZOOM_STEPS.length - 1 : i) + dir));
  S.zoom = ZOOM_STEPS[j];
  layoutScan(focus);
}

function setupScan() {
  const view = $("scan-view");
  $("zoom-in").onclick = () => zoomStep(1);
  $("zoom-out").onclick = () => zoomStep(-1);
  $("zoom-fit").onclick = () => { S.zoom = 1; layoutScan(); };
  $("zoom-1").onclick = () => {
    const img = $("scan-img");
    if (img.naturalWidth) S.zoom = Math.min(5, Math.max(0.5, img.naturalWidth / (view.clientWidth - 2)));
    layoutScan();
  };
  $("dim").oninput = (e) => { S.dim = +e.target.value; layoutScan(); };
  view.addEventListener("wheel", (e) => {
    if (!(e.metaKey || e.ctrlKey)) return;
    e.preventDefault();
    const r = view.getBoundingClientRect();
    zoomStep(e.deltaY < 0 ? 1 : -1, { x: e.clientX - r.left, y: e.clientY - r.top });
  }, { passive: false });
  let drag = null;
  view.addEventListener("pointerdown", (e) => {
    drag = { x: e.clientX, y: e.clientY, l: view.scrollLeft, t: view.scrollTop };
    view.setPointerCapture(e.pointerId);
    view.classList.add("dragging");
  });
  view.addEventListener("pointermove", (e) => {
    if (!drag) return;
    view.scrollLeft = drag.l - (e.clientX - drag.x);
    view.scrollTop = drag.t - (e.clientY - drag.y);
  });
  const stop = () => { drag = null; view.classList.remove("dragging"); };
  view.addEventListener("pointerup", stop);
  view.addEventListener("pointercancel", stop);
  view.addEventListener("dblclick", (e) => {
    const r = view.getBoundingClientRect();
    zoomStep(e.altKey ? -1 : 1, { x: e.clientX - r.left, y: e.clientY - r.top });
  });
  new ResizeObserver(() => layoutScan()).observe(view);
  // the divider between scan and text
  const cols = $("cols");
  $("divider").addEventListener("pointerdown", (e) => {
    const left = $("left").getBoundingClientRect().width;
    const move = (ev) => cols.style.setProperty("--scan-w", `${Math.max(200, ev.clientX - left)}px`);
    const up = () => { removeEventListener("pointermove", move); removeEventListener("pointerup", up); };
    addEventListener("pointermove", move);
    addEventListener("pointerup", up);
    e.preventDefault();
  });
}

// --- the page's text ---
const HEAD_FIELDS = ["book_title", "chapter_number", "chapter_title", "chapter_summary", "chapter_intro", "book_end_marker"];
const VERSE_FIELDS = ["chapter", "verse_number", "latin", "french", "annotations"];
const NOTE_FIELDS = ["commentary_id", "chapter", "verse_ref", "latin_quote", "french_translation", "french_commentary"];
const SHORT = new Set(["chapter", "verse_number", "commentary_id", "verse_ref", "chapter_number", "marker"]);

/** One labelled field; `makeField` turns it into an editor (set by the editing module). */
export const hooks = { makeField: null, afterRender: [] };

function fieldRow(name, value, path) {
  const f = el("div", { className: "f" + (SHORT.has(name) ? " short" : "") });
  f.dataset.name = name;
  if (ITALIC_FIELDS.has(name)) f.dataset.italic = "";
  if (hooks.makeField) hooks.makeField(f, name, value, path);
  else if (value === null || value === undefined) { f.textContent = "null"; f.classList.add("null"); }
  else render(f, String(value));
  return el("div", { className: "row" }, el("label", { textContent: name }), f);
}

function ref(ch, v) {
  return [ch, v].filter((x) => x !== null && x !== undefined).join(":") || "?";
}

function prevStrip() {
  const p = S.ctx && S.ctx.prev;
  if (!p) return null;
  const verse = p.verse != null ? `ch.${p.chapter ?? "?"} v.${p.verse}` : "no verse";
  const note = p.verse_ref != null || p.commentary_chapter != null ? ` · note on ${ref(p.commentary_chapter, p.verse_ref)}` : "";
  return el("div", { className: "ctx" }, el("b", { textContent: `◀ p.${p.page} ends: ` }),
            `${verse}${note}`, p.tail ? ` “${p.tail}”` : "");
}

function nextStrip() {
  const n = S.ctx && S.ctx.next;
  if (!n) return null;
  const verse = n.verse != null ? `ch.${n.chapter ?? "?"} v.${n.verse}` : "";
  return el("div", { className: "ctx" }, el("b", { textContent: `▶ p.${n.page} starts: ` }),
            n.continuation ? el("span", { className: "cont", textContent: "CONTINUATION " }) : null,
            [verse, n.verse_ref != null ? `note on v.${n.verse_ref}` : ""].filter(Boolean).join(" · "),
            n.head ? ` “${n.head}”` : "");
}

export function blockHead(title, section, i) {
  return el("div", { className: "block-head" }, el("span", { className: "title", textContent: title }));
}

export function renderPage() {
  const root = $("page-text");
  root.textContent = "";
  const d = S.data;
  if (!d) return;
  const sec = S.section;
  if (sec === "all") {
    const head = HEAD_FIELDS.filter((k) => k in d || k === "chapter_title");
    root.append(el("div", { className: "block" }, el("div", { className: "block-head" },
      el("span", { className: "title", textContent: "Page heading" })), ...head.map((k) => fieldRow(k, d[k] ?? null, [k]))));
  }
  if (sec === "all" || sec === "verses") {
    root.append(el("div", { className: "h2", textContent: `Verses (${(d.verses || []).length})` }));
    (d.verses || []).forEach((v, i) => root.append(el("div", { className: "block" },
      blockHead(`Verse ${v.verse_number ?? "?"}`, "verses", i),
      ...VERSE_FIELDS.filter((k) => k in v).map((k) => fieldRow(k, v[k], ["verses", i, k])))));
  }
  if (sec === "all" || sec === "commentary") {
    root.append(el("div", { className: "h2", textContent: `Commentary (${(d.commentary || []).length})` }));
    root.append(prevStrip() || "");
    (d.commentary || []).forEach((c, i) => root.append(el("div", { className: "block" },
      blockHead(`${c.commentary_id ?? "?"} · ℣ ${ref(c.chapter, c.verse_ref)}`, "commentary", i),
      ...NOTE_FIELDS.filter((k) => k in c).map((k) => fieldRow(k, c[k], ["commentary", i, k])))));
    root.append(nextStrip() || "");
  }
  if (sec === "all" || sec === "footnotes") {
    root.append(el("div", { className: "h2", textContent: `Footnotes (${(d.footnotes || []).length})` }));
    (d.footnotes || []).forEach((n, i) => root.append(el("div", { className: "block" },
      blockHead(n.marker || "?", "footnotes", i),
      ...["marker", "text"].filter((k) => k in n).map((k) => fieldRow(k, n[k], ["footnotes", i, k])))));
  }
  for (const f of hooks.afterRender) f(root);
}

// --- top bar basics ---
function setTheme(t) {
  document.documentElement.dataset.theme = t;
  $("theme").value = t;
  try { localStorage.setItem("rw-theme", t); } catch (e) {}
}

export function pageStep(dir) {
  const i = S.pages.indexOf(S.page);
  const j = i + dir;
  if (i >= 0 && j >= 0 && j < S.pages.length) return go(S.vol, S.pages[j]);
}

/** Go to a page; the editing and queue modules wrap this to save and to handle missing pages. */
export const nav = { go: (vol, page) => loadPage(vol, page) };
export const go = (vol, page) => nav.go(vol, page);

async function jump() {
  const r = parseRef($("jump").value);
  $("jump-msg").textContent = "";
  if (!r) { $("jump-msg").textContent = "type 17:2, 17 or p194"; return; }
  if (r.page) return go(S.vol, r.page);
  const res = await api(`/api/locate?vol=${encodeURIComponent(S.vol)}&ref=${encodeURIComponent($("jump").value)}`);
  if (res.status === 200) return go(S.vol, res.body.page);
  $("jump-msg").textContent = `${$("jump").value} not found in ${S.vol}`;
}

function setupTop() {
  for (const v of S.config.volumes) $("vol").append(el("option", { value: v, textContent: v }));
  $("vol").onchange = async () => {
    const vol = $("vol").value;
    go(vol, null);
  };
  $("page-num").onkeydown = (e) => { if (e.key === "Enter") go(S.vol, parseInt($("page-num").value, 10)); };
  $("page-prev").onclick = () => pageStep(-1);
  $("page-next").onclick = () => pageStep(1);
  $("jump").onkeydown = (e) => { if (e.key === "Enter") jump(); };
  $("theme").onchange = (e) => setTheme(e.target.value);
  $("theme").value = document.documentElement.dataset.theme;
  $("menu-btn").onclick = () => { $("menu").hidden = !$("menu").hidden; };
  document.addEventListener("click", (e) => { if (!e.target.closest(".menu")) $("menu").hidden = true; });
  for (const b of document.querySelectorAll("#sections button")) {
    b.onclick = () => {
      S.section = b.dataset.sec;
      document.querySelectorAll("#sections button").forEach((x) => x.classList.toggle("on", x === b));
      renderPage();
    };
  }
  document.addEventListener("keydown", (e) => {
    const typing = e.target.closest("input, select, textarea, [contenteditable]");
    if (!typing && !e.metaKey && !e.ctrlKey && (e.key === "ArrowLeft" || e.key === "ArrowRight")) {
      pageStep(e.key === "ArrowLeft" ? -1 : 1);
      e.preventDefault();
    }
  });
}

export const ready = (async () => {
  S.config = (await api("/api/config")).body;
  setupTop();
  setupScan();
  return S;
})();

// The editing and queue modules load after this one and decide the first page.
const mods = await Promise.all([import("./edit.js").catch(() => null), import("./queue.js").catch(() => null)]);
await ready;
if (!mods[1]) {
  const st = (await api("/api/state")).body;
  const start = S.config.start;
  const vol = start.vol || st.vol || S.config.volumes[0];
  go(vol, start.page || (vol === st.vol ? st.page : null));
}
