// The page-turn view: the foot of page A over the head of page B, both editable, the text as the site
// joins it, and the fix a script proposes there.
import { S, ZOOM_STEPS, api, ask, copyRef, hooks, loadPage, nav, toast } from "./app.js";
import { INT_FIELDS, extra, latinCaseFor, save, setDirty, wireField } from "./edit.js";
import { Field, ITALIC_FIELDS } from "./field.js";
import { icon } from "./icons.js";
import { currentItem, recheck } from "./queue.js";

const $ = (id) => document.getElementById(id);
const el = (tag, props = {}, ...kids) => {
  const e = Object.assign(document.createElement(tag), props);
  e.append(...kids.filter((k) => k != null));
  return e;
};

/** The view's state: `a` and `b` are {page, data, version, scan, verse, note, fields, dirty}. */
export const T = { open: false, vol: null, a: null, b: null, join: null, proposal: null, issues: [], around: {} };

let scans = true;
try { scans = localStorage.getItem("rw-turn-scans") !== "0"; } catch (e) {}

const sides = () => [T.a, T.b].filter(Boolean);
export const dirty = () => sides().some((s) => s.dirty);
const allFields = () => sides().flatMap((s) => s.fields.map((x) => x.field));

function showDirty() {
  const d = $("dirty");
  d.textContent = dirty() ? "● unsaved changes" : "";
  d.classList.toggle("unsaved", dirty());
}

/** A side's page as typed. */
function typed(side) {
  const d = structuredClone(side.data);
  for (const { path, field } of side.fields) {
    let o = d;
    for (const k of path.slice(0, -1)) o = o[k];
    let v = field.value;
    if (v !== null && INT_FIELDS.has(path[path.length - 1]) && /^\s*\d+\s*$/.test(v)) v = parseInt(v, 10);
    o[path[path.length - 1]] = v;
  }
  return d;
}

// --- drawing ---
const TAGS = { chapter: "ch", verse_number: "v", commentary_id: "#", verse_ref: "℣" };

function field(side, name, path) {
  const value = path.reduce((o, k) => (o == null ? o : o[k]), side.data);
  const f = el("div", { className: "f" + (name in TAGS ? " short" : "") });
  f.dataset.name = name;
  f.dataset.path = `${side.page}/${path.join("/")}`;
  if (ITALIC_FIELDS.has(name)) f.dataset.italic = "";
  const fld = new Field(f, { name, value, latinCase: latinCaseFor(), onChange: () => { side.dirty = true; showDirty(); } });
  wireField(fld, name, allFields);
  side.fields.push({ path, field: fld });
  if (name in TAGS) return el("span", { className: "inl" }, el("span", { className: "tag", textContent: TAGS[name] }), f);
  const copy = el("button", { className: "copy", title: "Copy this field's location and text (for an AI chat)",
                              onclick: () => copyRef(path, refAt(side)) }, icon("copy", 12));
  return el("div", { className: "fw" }, el("span", { className: "fl", textContent: name.replace(/_/g, " ") }), copy, f);
}

/** A side's page for copyRef: its text as typed. */
function refAt(side) {
  return { vol: T.vol, page: side.page, data: side.data, valueAt: (p) => {
    const x = side.fields.find((y) => y.path.join("/") === p.join("/"));
    return x ? x.field.value : undefined;
  } };
}

function copyEntry(side, section, i) {
  return el("button", { className: "link tool", title: "Copy this entry's location and text (for an AI chat)",
                        onclick: () => copyRef([section, i], refAt(side)) }, icon("copy", 14));
}

function noteBlock(side, title) {
  const i = side.note;
  const p = (k) => field(side, k, ["commentary", i, k]);
  return el("div", { className: "block k-note" },
    el("div", { className: "block-head" }, icon("commentary", 13), el("span", { className: "title", textContent: title }),
       p("commentary_id"), p("chapter"), p("verse_ref"), el("span", { className: "grow" }), copyEntry(side, "commentary", i)),
    el("div", { className: "pair" }, p("latin_quote"), p("french_translation")), p("french_commentary"));
}

function verseBlock(side, title) {
  const i = side.verse;
  const p = (k) => field(side, k, ["verses", i, k]);
  return el("div", { className: "block k-verse" },
    el("div", { className: "block-head" }, icon("verses", 13), el("span", { className: "title", textContent: title }),
       p("chapter"), p("verse_number"), el("span", { className: "grow" }), copyEntry(side, "verses", i)),
    el("div", { className: "pair" }, p("latin"), p("french")));
}

function verseLine(side) {
  const v = side.data.verses[side.verse];
  return el("div", { className: "ctx" }, icon("verses", 13), el("b", { textContent: ` p.${side.page} · last verse ` }),
            `${v.chapter ?? "?"}:${v.verse_number ?? "?"}`, v.french ? ` “${v.french.slice(0, 70)}${v.french.length > 70 ? "…" : ""}”` : "");
}

// both scans share one zoom (1 = the width of the column), kept from one turn to the next
let zoom = 1;

/** Size both scans to the zoom; `at` = {box, x, y}: that point of that box stays still, the other
 *  scan keeps its centre. */
function layoutCrops(at) {
  for (const box of document.querySelectorAll("#turn .turn-scan")) {
    const img = box.querySelector("img");
    if (!img.naturalWidth) continue;  // not loaded yet: its onload sizes it
    const focus = at && at.box === box ? at : { x: box.clientWidth / 2, y: box.clientHeight / 2 };
    const before = img.width || 1;
    img.style.width = `${Math.round((box.clientWidth - 2) * zoom)}px`;
    const k = img.width / before;
    box.scrollLeft = (box.scrollLeft + focus.x) * k - focus.x;
    box.scrollTop = (box.scrollTop + focus.y) * k - focus.y;
  }
  const label = $("turn-zoom");
  if (label) label.textContent = `${Math.round(zoom * 100)}%`;
}

function zoomCrops(dir, at) {
  const i = ZOOM_STEPS.findIndex((z) => z >= zoom - 1e-6);
  zoom = dir === 0 ? 1 : ZOOM_STEPS[Math.max(0, Math.min(ZOOM_STEPS.length - 1, (i < 0 ? ZOOM_STEPS.length - 1 : i) + dir))];
  layoutCrops(at);
}

const cropBoxes = new Map();  // "vol/page/end" -> its scan box, kept over redraws (zoom and scroll stay)

function scanCrop(side, end) {
  if (!scans || !side || !side.scan) return null;
  const kept = cropBoxes.get(`${T.vol}/${side.page}/${end}`);
  if (kept) { kept.classList.toggle("no-invert", !localStorageInvert()); return kept; }
  const img = el("img", { src: `/scan/${encodeURIComponent(T.vol)}/${side.page}`, alt: "", draggable: false });
  const box = el("div", { className: "turn-scan" + (localStorageInvert() ? "" : " no-invert") }, img);
  img.onload = () => {
    img.style.width = `${Math.round((box.clientWidth - 2) * zoom)}px`;
    if (end) box.scrollTop = box.scrollHeight;  // the foot of page A
  };
  const point = (e) => { const r = box.getBoundingClientRect(); return { box, x: e.clientX - r.left, y: e.clientY - r.top }; };
  box.addEventListener("wheel", (e) => {
    if (!(e.metaKey || e.ctrlKey)) return;
    e.preventDefault();
    zoomCrops(e.deltaY < 0 ? 1 : -1, point(e));
  }, { passive: false });
  box.addEventListener("dblclick", (e) => zoomCrops(e.altKey ? -1 : 1, point(e)));
  let drag = null;
  box.addEventListener("pointerdown", (e) => {
    drag = { x: e.clientX, y: e.clientY, l: box.scrollLeft, t: box.scrollTop };
    box.setPointerCapture(e.pointerId);
    box.classList.add("dragging");
  });
  box.addEventListener("pointermove", (e) => {
    if (!drag) return;
    box.scrollLeft = drag.l - (e.clientX - drag.x);
    box.scrollTop = drag.t - (e.clientY - drag.y);
  });
  const stop = () => { drag = null; box.classList.remove("dragging"); };
  box.addEventListener("pointerup", stop);
  box.addEventListener("pointercancel", stop);
  cropBoxes.set(`${T.vol}/${side.page}/${end}`, box);
  return box;
}

function zoomTools() {
  return el("span", { className: "turn-zoom" },
    el("button", { title: "Zoom the scans out", onclick: () => zoomCrops(-1) }, "−"),
    el("span", { id: "turn-zoom", textContent: `${Math.round(zoom * 100)}%` }),
    el("button", { title: "Zoom the scans in (or double-click a scan; ⌘ scroll; drag to pan)", onclick: () => zoomCrops(1) }, "+"),
    el("button", { title: "Fit the scans to the column", onclick: () => zoomCrops(0) }, "Fit"));
}

/** The same switch as the main scan's Invert: both follow it. */
function setInvert(on) {
  const main = $("invert");
  main.checked = on;
  main.dispatchEvent(new Event("change"));  // stores it and redraws the main scan
  for (const box of document.querySelectorAll("#turn .turn-scan")) box.classList.toggle("no-invert", !on);
}

function localStorageInvert() {
  try { return localStorage.getItem("rw-invert") !== "0"; } catch (e) { return true; }
}

function joinLine() {
  const j = T.join;
  if (!j) return null;
  return el("div", { className: "turn-join" },
    el("div", { className: "muted small", textContent: `As the site will print it (${j.mode})` }),
    el("div", { className: "joined" }, "…", j.joined.slice(0, j.at), el("span", { className: "join-mark", title: "page turn" }),
       j.joined.slice(j.at), "…"));
}

function issueList() {
  const cur = currentItem();
  return el("div", { className: "turn-issues" }, ...T.issues.map((it) => el("div", {
    className: "issue" + (it.id === (cur && cur.id) ? " cur" : "") + (["resolved", "false_positive"].includes(it.status) || it.fixed ? " done" : ""),
  }, el("small", {}, S.config.labels[it.kind] || it.kind), el("span", { className: "msg", textContent: it.msg }))));
}

function render() {
  const root = $("turn");
  for (const s of sides()) s.fields = [];
  const { a, b } = T;
  const head = el("div", { className: "turn-head" },
    el("button", { className: "pagebtn", title: "Previous page turn with an open issue (←)", disabled: T.around.prev == null,
                   onclick: () => stepTurn(-1) }, icon("prev", 14)),
    el("b", { textContent: `${T.vol} · p.${a ? a.page : "?"} → p.${b ? b.page : "?"}` }),
    el("button", { className: "pagebtn", title: "Next page turn with an open issue (→)", disabled: T.around.next == null,
                   onclick: () => stepTurn(1) }, icon("next", 14)),
    el("span", { className: "grow" }),
    scans ? zoomTools() : null,
    scans ? el("label", { className: "muted small dark-only", title: "Show the scans light-on-dark in the dark theme" },
               el("input", { type: "checkbox", checked: localStorageInvert(), onchange: (e) => setInvert(e.target.checked) }),
               " Invert") : null,
    el("label", { className: "muted small" },
       el("input", { type: "checkbox", checked: scans, onchange: (e) => setScans(e.target.checked) }), " Scans"),
    el("button", { title: "Back to the page (Esc)", onclick: () => closeTurn() }, icon("back", 13), " Page"));
  const text = el("div", { className: "turn-text" },
    a && a.verse != null ? verseLine(a) : null,
    a && a.note != null ? noteBlock(a, `p.${a.page} · last note`) : el("p", { className: "muted", textContent: a ? `p.${a.page} has no commentary` : "No page before" }),
    el("div", { className: "turn-rule" }, el("span", { textContent: "page turn" })),
    b ? addTop(b) : null,
    b && b.note != null ? noteBlock(b, `p.${b.page} · first note`) : el("p", { className: "muted", textContent: b ? `p.${b.page} has no commentary` : "The next page has no JSON" }),
    b && b.verse != null ? verseBlock(b, `p.${b.page} · first verse`) : null);
  const crops = scans ? el("div", { className: "turn-scans" }, scanCrop(a, true), scanCrop(b, false)) : null;
  root.replaceChildren(head, el("div", { className: "turn-body" + (scans ? "" : " no-scans") }, text, crops),
                       joinLine(), el("div", { id: "turn-proposal" }), issueList());
  layoutCrops();  // a scan box kept from before may have missed a zoom
  if (hooks.renderProposal) hooks.renderProposal($("turn-proposal"), T.proposal, { turn: true });
  showDirty();
}

/** "+ add block at top" of page B: a commentary block continuing page A's last note. */
function addTop(side) {
  const last = T.a && T.a.note != null ? typed(T.a).commentary[T.a.note] : null;
  const ref = last ? [last.chapter, last.verse_ref].filter((x) => x != null).join(":") : "";
  const where = ref ? ` (continues ${ref} from p.${T.a.page})` : "";
  return el("button", { className: "add", textContent: `+ add block at top of p.${side.page}${where}`,
                        onclick: () => addBlockTop(side) });
}

async function addBlockTop(side) {
  const r = await api("/api/op", { vol: T.vol, page: side.page, data: typed(side), version: side.version,
                                   op: { op: "add_commentary", after: null } });
  if (r.status === 409) { toast(`p.${side.page} was changed on disk: save or reopen the page turn first`); return; }
  if (r.status !== 200) { toast(r.body.error || "Failed"); return; }
  Object.assign(side, { data: r.body.data, version: r.body.version, dirty: false, note: 0 });
  if (dirty()) {  // the other page has unsaved edits: kept, the turn drawn again without reloading it
    for (const s of sides()) if (s !== side) s.data = typed(s);  // (side's fields are the old page)
    await recheck(T.vol, side.page);
    render();
  } else await refresh();
  const f = T.b && T.b.fields.find((x) => x.path.join("/") === "commentary/0/french_commentary");
  if (f) f.field.el.focus();
}

function setScans(on) {
  scans = on;
  try { localStorage.setItem("rw-turn-scans", on ? "1" : "0"); } catch (e) {}
  const typedNow = sides().map((s) => [s, typed(s)]);
  for (const [s, d] of typedNow) s.data = d;  // keep what was typed over the redraw
  render();
}

// --- opening, saving, leaving ---
async function fetchTurn(q) {
  const r = await api(`/api/turn?${new URLSearchParams(q)}`);
  if (r.status !== 200) { toast(r.body.error || "No page turn here"); return false; }
  const t = r.body;
  Object.assign(T, { vol: t.vol, join: t.join, proposal: t.proposal, issues: t.issues, around: t.around,
                     a: t.a && { ...t.a, fields: [], dirty: false }, b: t.b && { ...t.b, fields: [], dirty: false } });
  return true;
}

/** Save, drop or keep the view's unsaved edits; false when the person cancels. */
async function settle() {
  if (!dirty()) return true;
  const pages = sides().filter((s) => s.dirty).map((s) => `p.${s.page}`).join(" and ");
  const choice = await ask(`Save your changes to ${T.vol} ${pages} before leaving the page turn?`,
                           [["cancel", "Cancel"], ["discard", "Don't save"], ["save", "Save", "ok"]]);
  if (choice === "save") return saveTurn();
  if (choice !== "discard") return false;
  for (const s of sides()) s.dirty = false;
  showDirty();
  return true;
}

function show(on) {
  T.open = on;
  $("turn").hidden = !on;
  $("cols").hidden = on;
  document.body.classList.toggle("turn-open", on);
  extra.list = on ? allFields : null;
  hooks.saveActive = on ? saveTurn : null;
  if (!on) showDirty();
}

/** Open the turn after page `a` ({vol, a}) or of an issue ({id}). */
export async function openTurn(q) {
  if (S.dirty) {
    const choice = await ask(`Save your changes to ${S.vol} p.${S.page} first?`,
                             [["cancel", "Cancel"], ["discard", "Don't save"], ["save", "Save", "ok"]]);
    if (choice === "save") { if (!(await save({ redraw: false }))) return false; }
    else if (choice !== "discard") return false;
    else { setDirty(false); await loadPage(S.vol, S.page); }  // the dropped edits leave the fields too
  }
  if (T.open && !(await settle())) return false;
  if (!(await fetchTurn(q))) return false;
  T.itemId = q.id || null;
  show(true);
  render();
  $("turn").scrollTop = 0;
  return true;
}

/** Back to the page, reloaded (it may be one of the two just saved). */
export async function closeTurn() {
  if (!T.open || !(await settle())) return false;
  show(false);
  if (S.vol && S.data) await loadPage(S.vol, S.page);
  return true;
}

async function stepTurn(dir) {
  const a = dir < 0 ? T.around.prev : T.around.next;
  if (a == null) return;
  if (await settle()) openTurn({ vol: T.vol, a });
}

/** Write each changed side; true when everything is saved. */
export async function saveTurn() {
  let wrote = false;
  for (const s of sides().filter((x) => x.dirty)) {
    const data = typed(s);
    let r = await api("/api/page", { vol: T.vol, page: s.page, data, version: s.version });
    if (r.status === 409) {
      const choice = await ask(
        `p.${s.page} was changed on disk since the page turn was opened.\n\n` +
        "Reload theirs: your unsaved changes to it are dropped.\nKeep mine: overwrite the file with what you see.",
        [["cancel", "Cancel"], ["theirs", "Reload theirs"], ["mine", "Keep mine", "warn"]]);
      if (choice === "theirs") { s.dirty = false; continue; }
      if (choice !== "mine") return false;
      r = await api("/api/page", { vol: T.vol, page: s.page, data, version: s.version, force: true });
    }
    if (r.status !== 200) { toast(r.body.error || "Save failed"); return false; }
    Object.assign(s, { data: r.body.data, version: r.body.version, dirty: false });
    wrote = true;
  }
  await refresh(wrote);
  return true;
}

/** Load the turn again (after a save or an accepted proposal), re-checking the book first. */
export async function refresh(recheckFirst = true) {
  const a = T.a ? T.a.page : null;
  if (recheckFirst && a != null) await recheck(T.vol, a, T.b ? [T.b.page] : []);
  if (a != null && (await fetchTurn({ vol: T.vol, a }))) render();
  $("dirty").textContent = "saved";
  setTimeout(() => { if (!dirty()) showDirty(); }, 1500);
}

/** Pages of the turn changed on disk: load them again. Unsaved edits on the other page stay. */
export async function reloadFromDisk(pages) {
  const keep = sides().filter((s) => s.dirty && !pages.includes(s.page))
    .map((s) => ({ page: s.page, data: typed(s), version: s.version, dirty: true }));
  const a = T.a ? T.a.page : null;
  if (a == null) return;
  const at = [...document.querySelectorAll("#turn .turn-scan")].map((b) => [b, b.scrollLeft, b.scrollTop]);
  const top = $("turn").scrollTop;
  if (!(await fetchTurn({ vol: T.vol, a }))) return;
  for (const k of keep) {
    const s = sides().find((x) => x.page === k.page);
    if (s) Object.assign(s, k);
  }
  render();
  for (const [b, l, t] of at) { b.scrollLeft = l; b.scrollTop = t; }
  $("turn").scrollTop = top;
  showDirty();
  await recheck(T.vol, a, T.b ? [T.b.page] : []);
}

// --- wiring ---
hooks.showTurn = async (it) => {
  if (S.config.turn_kinds.includes(it.kind)) return openTurn({ id: it.id });
  if (T.open) return closeTurn();
};
hooks.beforeMark = async () => !T.open || !dirty() || saveTurn();

// going to another page (or issue) leaves the view; the issue's own turn opens again after
const innerGo = nav.go;
nav.go = async (vol, page) => {
  if (T.open) {
    if (!(await settle())) return null;
    show(false);
  }
  return innerGo(vol, page);
};

addEventListener("beforeunload", (e) => { if (T.open && dirty()) e.preventDefault(); });
addEventListener("resize", () => { if (T.open) layoutCrops(); });

document.addEventListener("keydown", (e) => {
  const typing = e.target.closest("input, select, textarea, [contenteditable]");
  if (typing || e.metaKey || e.ctrlKey || e.altKey || $("dialog").open) return;
  if (T.open && (e.key === "ArrowLeft" || e.key === "ArrowRight")) {
    e.preventDefault();
    e.stopImmediatePropagation();  // not the page's ← →
    stepTurn(e.key === "ArrowLeft" ? -1 : 1);
  } else if (T.open && e.key === "Escape") {
    e.preventDefault();
    closeTurn();
  } else if (!T.open && e.key.toLowerCase() === "t" && S.data) {
    e.preventDefault();
    openTurn({ vol: S.vol, a: S.page });
  }
}, true);
$("turn-btn").onclick = () => (T.open ? closeTurn() : S.data && openTurn({ vol: S.vol, a: S.page }));
