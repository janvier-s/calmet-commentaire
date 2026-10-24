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

/** A modal: message, optional body element, buttons [[value, label, className]]. Resolves to the
 *  value clicked, or null on Escape. */
export function ask(msg, buttons, body = null) {
  const d = $("dialog");
  $("dialog-msg").textContent = msg;
  $("dialog-body").replaceChildren(...(body ? [body] : []));
  $("dialog-buttons").replaceChildren(...buttons.map(([value, label, cls]) =>
    el("button", { value, textContent: label, className: cls || "" })));
  return new Promise((resolve) => {
    d.onclose = () => resolve(d.returnValue || null);
    d.returnValue = "";
    d.showModal();
    const first = body && body.querySelector("input");
    (first || d.querySelector("menu button")).focus();  // the first button is the safe one
  });
}

// --- pages ---
export async function loadPage(vol, page) {
  const r = await api(`/api/page?vol=${encodeURIComponent(vol)}&page=${page ?? ""}`);
  if (r.status === 404 && r.body.missing) return { missing: true, ...r.body };
  if (r.status !== 200) { toast(r.body.error || "Could not load the page"); return null; }
  page = r.body.page;
  S.reveal = new Set();
  Object.assign(S, { vol, page, data: r.body.data, version: r.body.version, ctx: r.body.context,
                     pages: r.body.pages, issues: r.body.issues, around: r.body.around });
  api("/api/state", { vol, page });
  showScan(r.body.scan);
  renderPage();
  updateTop();
  $("text-pane").scrollTop = 0;
  return S;
}

export function updateTop() {
  $("vol").value = S.vol;
  $("page-num").value = S.page;
  document.title = `${S.vol} p.${S.page} · Calmet Review`;
}

// --- the scan ---
const ZOOM_STEPS = [0.5, 0.65, 0.8, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0];

export function showScan(has) {
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
// short fields sit in the block's header line, with a short tag
const TAGS = { chapter: "ch", verse_number: "v", commentary_id: "#", verse_ref: "℣", chapter_number: "chapter", marker: "" };

/** `makeField` turns a field into an editor (set by the editing module). */
export const hooks = { makeField: null, beforeRender: null, collect: null, afterRender: [],
                       blockTools: null, addTop: null, addBelow: null, addEnd: null };

S.reveal = new Set();  // empty optional fields the user asked to see ("+ annotations")
const key = (path) => path.join("/");
const shown = (value, path) => !(value === null || value === undefined) || S.reveal.has(key(path));

/** A field with its name as a small tag on the border; short ones inline. */
function field(name, value, path) {
  const short = name in TAGS;
  const f = el("div", { className: "f" + (short ? " short" : "") });
  f.dataset.name = name;
  f.dataset.path = key(path);
  f.title = name;
  if (ITALIC_FIELDS.has(name)) f.dataset.italic = "";
  if (hooks.makeField) hooks.makeField(f, name, value, path);
  else if (value === null || value === undefined) { f.textContent = "null"; f.classList.add("null"); }
  else render(f, String(value));
  if (short) return el("span", { className: "inl" }, TAGS[name] ? el("span", { className: "tag", textContent: TAGS[name] }) : null, f);
  return el("div", { className: "fw" }, el("span", { className: "fl", textContent: name.replace(/_/g, " ") }), f);
}

/** "+ name" for an empty optional field: shows it, focused. */
function chip(name, path) {
  return el("button", { className: "chip", textContent: `+ ${name.replace(/_/g, " ")}`, title: `Add ${name}`,
    onclick: () => {
      if (hooks.collect) hooks.collect();
      S.reveal.add(key(path));
      renderPage();
      const f = document.querySelector(`.f[data-path="${key(path)}"]`);
      if (f) f.focus();
    } });
}

/** Fields of an entry: the ones present, the empty optional ones as chips. */
function fields(entry, names, path, optional) {
  const out = {}, chips = [];
  for (const k of names) {
    if (!(k in entry)) continue;
    const p = [...path, k];
    if (optional.has(k) && !shown(entry[k], p)) chips.push(chip(k, p));
    else out[k] = field(k, entry[k], p);
  }
  return { f: out, chips };
}

const pair = (...xs) => {
  const kids = xs.filter(Boolean);
  return kids.length ? el("div", { className: kids.length > 1 ? "pair" : "" }, ...kids) : null;
};

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

/** The header line of a block: its title, short fields, chips, then the move/delete tools. */
export function blockHead(title, section, i, ...inline) {
  return el("div", { className: "block-head" }, title ? el("span", { className: "title", textContent: title }) : null,
            ...inline.flat().filter(Boolean), el("span", { className: "grow" }),
            ...(hooks.blockTools ? hooks.blockTools(section, i) : []));
}

function block(section, i, head, ...body) {
  const b = el("div", { className: "block" }, head, ...body.filter(Boolean));
  b.dataset.section = section;
  b.dataset.index = i;
  return b;
}

const NONE = new Set();
const VERSE_OPT = new Set(["annotations"]);
const NOTE_OPT = new Set(["latin_quote", "french_translation"]);

function verseBlock(v, i) {
  const { f, chips } = fields(v, ["chapter", "verse_number", "latin", "french", "annotations"], ["verses", i], VERSE_OPT);
  return block("verses", i, blockHead("Verse", "verses", i, f.chapter, f.verse_number, chips),
               pair(f.latin, f.french), f.annotations);
}

function noteBlock(c, i) {
  // the first block of a page usually continues the previous note: no lemma, no translation
  const opt = i === 0 ? NOTE_OPT : NONE;
  const { f, chips } = fields(c, ["commentary_id", "chapter", "verse_ref", "latin_quote", "french_translation", "french_commentary"],
                              ["commentary", i], opt);
  return block("commentary", i, blockHead(null, "commentary", i, f.commentary_id, f.chapter, f.verse_ref, chips),
               pair(f.latin_quote, f.french_translation), f.french_commentary);
}

function footnoteBlock(n, i) {
  const { f } = fields(n, ["marker", "text"], ["footnotes", i], NONE);
  const b = block("footnotes", i, blockHead(null, "footnotes", i, f.marker, f.text));
  b.classList.add("fn");
  return b;
}

function headingBlock(d) {
  const names = HEAD_FIELDS.filter((k) => k in d || k === "chapter_title");
  const entry = Object.fromEntries(names.map((k) => [k, d[k] ?? null]));
  const { f, chips } = fields(entry, names, [], new Set(names));
  return block("heading", 0, blockHead("Page heading", "heading", 0, f.chapter_number, chips),
               pair(f.book_title, f.chapter_title), f.chapter_summary, f.chapter_intro, f.book_end_marker);
}

export function renderPage() {
  const root = $("page-text");
  root.textContent = "";
  if (hooks.beforeRender) hooks.beforeRender();
  const d = S.data;
  if (!d) return;
  const sec = S.section;
  if (sec === "all") root.append(headingBlock(d));
  if (sec === "all" || sec === "verses") {
    root.append(el("div", { className: "h2", textContent: `Verses (${(d.verses || []).length})` }));
    (d.verses || []).forEach((v, i) => root.append(verseBlock(v, i)));
    if (hooks.addEnd) root.append(hooks.addEnd("verses"));
  }
  if (sec === "all" || sec === "commentary") {
    root.append(el("div", { className: "h2", textContent: `Commentary (${(d.commentary || []).length})` }));
    root.append(prevStrip() || "");
    if (hooks.addTop) root.append(hooks.addTop());
    (d.commentary || []).forEach((c, i) => {
      root.append(noteBlock(c, i));
      if (hooks.addBelow) root.append(hooks.addBelow(i));
    });
    root.append(nextStrip() || "");
  }
  if (sec === "all" || sec === "footnotes") {
    root.append(el("div", { className: "h2", textContent: `Footnotes (${(d.footnotes || []).length})` }));
    (d.footnotes || []).forEach((n, i) => root.append(footnoteBlock(n, i)));
    if (hooks.addEnd) root.append(hooks.addEnd("footnotes"));
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
      if (hooks.collect) hooks.collect();
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

/** Open the first page: the start options, else where the last session stopped. The queue module
 *  replaces this with the first issue. */
export const boot = {
  async start() {
    const st = (await api("/api/state")).body;
    const start = S.config.start;
    const vol = start.vol || st.vol || S.config.volumes[0];
    return go(vol, start.page || (vol === st.vol ? st.page : null));
  },
};
