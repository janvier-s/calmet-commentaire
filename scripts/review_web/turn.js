// The page-turn view: the foot of page A over the head of page B, both editable, the text as the site
// joins it, and the fix a script proposes there.
import { S, api, ask, hooks, loadPage, nav, toast } from "./app.js";
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
  return el("div", { className: "fw" }, el("span", { className: "fl", textContent: name.replace(/_/g, " ") }), f);
}

function noteBlock(side, title) {
  const i = side.note;
  const p = (k) => field(side, k, ["commentary", i, k]);
  return el("div", { className: "block k-note" },
    el("div", { className: "block-head" }, icon("commentary", 13), el("span", { className: "title", textContent: title }),
       p("commentary_id"), p("chapter"), p("verse_ref")),
    el("div", { className: "pair" }, p("latin_quote"), p("french_translation")), p("french_commentary"));
}

function verseBlock(side, title) {
  const i = side.verse;
  const p = (k) => field(side, k, ["verses", i, k]);
  return el("div", { className: "block k-verse" },
    el("div", { className: "block-head" }, icon("verses", 13), el("span", { className: "title", textContent: title }),
       p("chapter"), p("verse_number")),
    el("div", { className: "pair" }, p("latin"), p("french")));
}

function verseLine(side) {
  const v = side.data.verses[side.verse];
  return el("div", { className: "ctx" }, icon("verses", 13), el("b", { textContent: ` p.${side.page} · last verse ` }),
            `${v.chapter ?? "?"}:${v.verse_number ?? "?"}`, v.french ? ` “${v.french.slice(0, 70)}${v.french.length > 70 ? "…" : ""}”` : "");
}

function scanCrop(side, end) {
  if (!scans || !side || !side.scan) return null;
  const img = el("img", { src: `/scan/${encodeURIComponent(T.vol)}/${side.page}`, alt: "", draggable: false });
  const box = el("div", { className: "turn-scan" + (localStorageInvert() ? "" : " no-invert") }, img);
  if (end) img.onload = () => { box.scrollTop = box.scrollHeight; };  // the foot of page A
  return box;
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
    el("label", { className: "muted small" },
       el("input", { type: "checkbox", checked: scans, onchange: (e) => setScans(e.target.checked) }), " Scans"),
    el("button", { title: "Back to the page (Esc)", onclick: () => closeTurn() }, icon("back", 13), " Page"));
  const text = el("div", { className: "turn-text" },
    a && a.verse != null ? verseLine(a) : null,
    a && a.note != null ? noteBlock(a, `p.${a.page} · last note`) : el("p", { className: "muted", textContent: a ? `p.${a.page} has no commentary` : "No page before" }),
    el("div", { className: "turn-rule" }, el("span", { textContent: "page turn" })),
    b && b.note != null ? noteBlock(b, `p.${b.page} · first note`) : el("p", { className: "muted", textContent: b ? `p.${b.page} has no commentary` : "The next page has no JSON" }),
    b && b.verse != null ? verseBlock(b, `p.${b.page} · first verse`) : null);
  const crops = scans ? el("div", { className: "turn-scans" }, scanCrop(a, true), scanCrop(b, false)) : null;
  root.replaceChildren(head, el("div", { className: "turn-body" + (scans ? "" : " no-scans") }, text, crops),
                       joinLine(), el("div", { id: "turn-proposal" }), issueList());
  if (hooks.renderProposal) hooks.renderProposal($("turn-proposal"), T.proposal, { turn: true });
  showDirty();
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
