// Editing: the fields, saving (with the on-disk check), Tab between fields, unsaved changes.
import { S, api, ask, hooks, nav, renderPage, toast, loadPage } from "./app.js";
import { Field } from "./field.js";
import { icon } from "./icons.js";

const $ = (id) => document.getElementById(id);
export const INT_FIELDS = new Set(["verse_number", "commentary_id", "verse_ref", "chapter_number", "chapter"]);

S.fields = [];      // [{path, field}] of the page drawn
S.dirty = false;
let lastField = null;

const cased = new Map();  // latin_quote text -> small-cap indexes (from calmet.latin_case)
function latinCase(text, redraw) {
  if (cased.has(text)) return cased.get(text);
  cased.set(text, null);
  api("/api/latin_case", { text }).then((r) => {
    const c = r.body.text || "";
    if (c.length !== text.length) return;
    const first = [...c].findIndex((ch) => /\p{L}/u.test(ch));
    const idx = [];
    for (let i = 0; i < c.length; i++) if (c[i] !== c[i].toUpperCase() && i !== first) idx.push(i);
    cased.set(text, idx);
    redraw();
  }).catch(() => cased.delete(text));
  return null;
}

/** Small caps for a lemma, asked of the server once the typing stops (one timer per field). */
export function latinCaseFor() {
  let timer = null;
  return (t, redraw) => {
    clearTimeout(timer);
    if (cased.has(t)) return cased.get(t);
    timer = setTimeout(() => latinCase(t, redraw), 300);
    return null;
  };
}

/** Fields drawn outside the page (the page-turn view): the italics button, the shelf and Tab see
 *  them too. `list()` gives them in order; set to null when that view closes. */
export const extra = { list: null };

/** What every field gets: marks shown or not, a taller empty comment, the last-focused field, Tab. */
export function wireField(field, name, list) {
  const f = field.el;
  f.classList.toggle("hide-marks", !$("show-marks").checked);
  if (name === "french_commentary" && !field.text.trim()) f.style.minHeight = "6em";
  f.addEventListener("focus", () => { lastField = field; });
  f.addEventListener("keydown", (e) => {
    if (e.key !== "Tab") return;
    e.preventDefault();
    const all = list();
    const next = all[(all.indexOf(field) + (e.shiftKey ? -1 : 1) + all.length) % all.length];
    next.el.focus();
    next.select(0, next.text.length);
    next.el.scrollIntoView({ block: "nearest" });
  });
}

S.edits = 0;  // counts every edit, so a save knows whether typing went on meanwhile
hooks.makeField = (f, name, value, path) => {
  const field = new Field(f, { name, value, latinCase: latinCaseFor(), onChange: () => { S.edits++; setDirty(true); } });
  wireField(field, name, () => S.fields.map((x) => x.field));
  S.fields.push({ path, field });
};
hooks.beforeRender = () => { S.fields = []; lastField = null; };
hooks.valueAt = (path) => {
  const k = path.join("/");
  const x = S.fields.find((y) => y.path.join("/") === k);
  return x ? x.field.value : undefined;
};
hooks.collect = () => { if (S.fields.length) S.data = typedData(); };  // keep typed text over a redraw

export function setDirty(on) {
  S.dirty = on;
  const d = $("dirty");
  d.textContent = on ? "● unsaved changes" : "";
  d.classList.toggle("unsaved", on);
  $("save").classList.toggle("unsaved", on);
}

/** The page as typed: S.data with every field's value written in. */
export function typedData() {
  const d = structuredClone(S.data);
  for (const { path, field } of S.fields) {
    let o = d;
    for (const k of path.slice(0, -1)) o = o[k];
    let v = field.value;
    if (v !== null && INT_FIELDS.has(path[path.length - 1]) && /^\s*\d+\s*$/.test(v)) v = parseInt(v, 10);
    o[path[path.length - 1]] = v;
  }
  return d;
}

/** Save the page; true when written. A page changed on disk is never overwritten unasked. */
export async function save({ redraw = true } = {}) {
  if (!S.data) return true;
  const data = typedData();
  const edits = S.edits;
  let r = await api("/api/page", { vol: S.vol, page: S.page, data, version: S.version, carry: true });
  if (r.status === 409) {
    const choice = await ask(
      "This page was changed on disk since you opened it (a script, or another editor).\n\n" +
      "Reload theirs: your unsaved changes on this page are dropped.\nKeep mine: overwrite the file with what you see.",
      [["cancel", "Cancel"], ["theirs", "Reload theirs"], ["mine", "Keep mine", "warn"]]);
    if (choice === "theirs") { setDirty(false); await loadPage(S.vol, S.page); return false; }
    if (choice !== "mine") return false;
    r = await api("/api/page", { vol: S.vol, page: S.page, data, version: S.version, force: true, carry: true });
  }
  if (r.status !== 200) { toast(r.body.error || "Save failed"); return false; }
  if (r.body.carried) toast(`Chapter and verse carried to the continuation on p.${r.body.carried}`);
  const changed = JSON.stringify(r.body.data) !== JSON.stringify(data);
  S.data = r.body.data;
  S.version = r.body.version;
  if (hooks.afterSave) hooks.afterSave();
  if (S.edits !== edits) return true;  // typed during the save: still unsaved, fields kept
  setDirty(false);
  $("dirty").textContent = "saved";
  setTimeout(() => { if (!S.dirty) $("dirty").textContent = ""; }, 1500);
  if (changed && redraw) {  // the punctuation rules changed something: show it
    const top = $("text-pane").scrollTop;
    renderPage();
    $("text-pane").scrollTop = top;
  }
  return true;
}

/** Run a page operation on the server (it saves the typed text first). */
export async function op(o) {
  const r = await api("/api/op", { vol: S.vol, page: S.page, data: typedData(), version: S.version, op: o });
  if (r.status === 409) { if (await save()) return op(o); return false; }
  if (r.status !== 200) { toast(r.body.error || "Failed"); return false; }
  S.data = r.body.data;
  S.version = r.body.version;
  setDirty(false);
  const top = $("text-pane").scrollTop;
  renderPage();
  $("text-pane").scrollTop = top;
  if (hooks.afterSave) hooks.afterSave();
  return true;
}

// leaving a page with unsaved changes asks first; a failed save stays
const plainGo = nav.go;
nav.go = async (vol, page) => {
  if (S.dirty && S.data) {
    const choice = await ask(`Save your changes to ${S.vol} p.${S.page} before leaving?`,
                             [["cancel", "Cancel"], ["discard", "Don't save"], ["save", "Save", "ok"]], null, "save");
    if (choice === "save") { if (!(await save({ redraw: false }))) return null; }
    else if (choice !== "discard") return null;
  }
  setDirty(false);
  return plainGo(vol, page);
};

/** Undo all: the page as it was when it was opened (unsaved edits dropped, saved ones written back). */
async function undoAll() {
  const o = S.opened;
  if (!o || o.vol !== S.vol || o.page !== S.page || !S.data) return;
  const savedSince = JSON.stringify(S.data) !== JSON.stringify(o.data);
  if (!S.dirty && !savedSince) { toast("Nothing to undo on this page"); return; }
  const msg = savedSince ? "Put the page back as it was when you opened it? Changes already saved to it are undone too."
                         : "Drop your unsaved changes to this page?";
  if (await ask(msg, [["cancel", "Cancel"], ["yes", "Undo all", "warn"]]) !== "yes") return;
  if (savedSince) {
    const r = await api("/api/page", { vol: S.vol, page: S.page, data: o.data, version: S.version });
    if (r.status !== 200) { toast(r.status === 409 ? "The page changed on disk: reload it first" : (r.body.error || "Failed")); return; }
    S.data = r.body.data;
    S.version = r.body.version;
    if (hooks.afterSave) hooks.afterSave();
  }
  setDirty(false);
  const top = $("text-pane").scrollTop;
  renderPage();
  $("text-pane").scrollTop = top;
  toast("Page put back as you opened it");
}
$("undo-all").onclick = undoAll;

// the page-turn view saves its own two pages (hooks.saveActive)
const saveActive = () => (hooks.saveActive ? hooks.saveActive() : save());
$("save").onclick = saveActive;
$("italic").onmousedown = (e) => e.preventDefault();  // keep the selection in the field
$("italic").onclick = () => lastField && lastField.toggleItalic();
$("show-marks").onchange = (e) => document.querySelectorAll(".f").forEach((f) => f.classList.toggle("hide-marks", !e.target.checked));
document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") { e.preventDefault(); saveActive(); }
});
addEventListener("beforeunload", (e) => { if (S.dirty) e.preventDefault(); });

// --- a little menu over a selection in a field: italics, copy, cut, paste ---
const selMenu = Object.assign(document.createElement("div"), { id: "sel-menu", hidden: true });
document.body.append(selMenu);
const fieldAt = (node) => (S.fields.find((x) => x.field.el.contains(node)) || {}).field
  || (extra.list ? extra.list().find((f) => f.el.contains(node)) : null) || null;
/** The field the selection is in, and the selection in it. */
const selected = () => {
  const s = getSelection();
  const f = s.rangeCount ? fieldAt(s.anchorNode) : null;
  const sel = f && f.selection();
  return sel ? [f, sel] : [null, null];
};
const copySel = async (f, [a, b]) => {
  try { await navigator.clipboard.writeText(f.text.slice(a, b)); return true; } catch (e) { toast("Could not copy"); return false; }
};
const SEL_TOOLS = [
  ["I", "Italics (⌘I)", (f) => f.toggleItalic(), "it-btn", null],
  ["Cut", "Cut the selection", async (f, sel) => { if (await copySel(f, sel)) f.edit(sel[0], sel[1], ""); }, "", "cut"],
  ["Copy", "Copy the selection", async (f, sel) => { if (await copySel(f, sel)) toast("Copied"); }, "", "copy"],
  ["Spelling", "Add the selection to the SPELLING list in the notes file", async (f, [a, b]) => {
    const r = await api("/api/note", { section: "SPELLING", text: f.text.slice(a, b) });
    if (r.status !== 200) toast(r.body.error || "Could not add it", "error");
    else toast(r.body.added ? "Added to SPELLING" : "Already in SPELLING", r.body.added ? "ok" : undefined);
  }, "", "flag"],
  // pasted over the selection, with a space after it unless one follows already
  ["Paste", "Paste over the selection, with a space after it", async (f, [a, b]) => {
    let t;
    try { t = await navigator.clipboard.readText(); } catch (e) { toast("Could not read the clipboard"); return; }
    if (!t) return;
    f.edit(a, b, /^\s/.test(f.text.slice(b)) || /\s$/.test(t) ? t : t + " ");
  }, "", "paste"],
];
for (const [text, title, act, cls, ic] of SEL_TOOLS) {
  const b = Object.assign(document.createElement("button"), { textContent: text, title, className: cls || "" });
  b.dataset.tool = text;
  if (ic) b.prepend(icon(ic, 13));
  b.addEventListener("mousedown", (e) => e.preventDefault());  // keep the selection
  b.onclick = () => { const [f, sel] = selected(); clicked = null; selMenu.hidden = true; if (f) act(f, sel); };
  selMenu.append(b);
}
/** Show the menu centred on x, above y; with no selection (a click in a field) only Paste. */
function showMenu(x, y, caret) {
  for (const b of selMenu.children) b.hidden = caret && b.dataset.tool !== "Paste";
  selMenu.hidden = false;
  const w = selMenu.offsetWidth;
  selMenu.style.left = `${Math.min(innerWidth - w - 4, Math.max(4, x - w / 2))}px`;
  selMenu.style.top = `${Math.max(4, y - 34)}px`;
}
// a selection: the whole menu over it; a click in a field: Paste where it was clicked (the cursor
// the click put there reports its change after the click, so the click, not that change, decides);
// the cursor moved by typing or the arrows: none
let clicked = null;  // where the last click in a field was, until a key is pressed
document.addEventListener("selectionchange", () => {
  const s = getSelection();
  const f = s.rangeCount ? fieldAt(s.anchorNode) : null;
  if (f && s.isCollapsed && clicked) { showMenu(clicked.x, clicked.y, true); return; }
  if (!f || s.isCollapsed || !f.el.contains(s.focusNode)) { selMenu.hidden = true; return; }
  const r = s.getRangeAt(0).getBoundingClientRect();
  showMenu(r.left + r.width / 2, r.top, false);
});
document.addEventListener("pointerdown", (e) => {
  if (!selMenu.contains(e.target)) clicked = fieldAt(e.target) ? { x: e.clientX, y: e.clientY - 6 } : null;
});
document.addEventListener("pointerup", () => {
  const s = getSelection();
  if (clicked && s.isCollapsed && s.rangeCount && fieldAt(s.anchorNode)) showMenu(clicked.x, clicked.y, true);
});
document.addEventListener("keydown", () => { clicked = null; selMenu.hidden = true; }, true);
document.getElementById("text-pane").addEventListener("scroll", () => { selMenu.hidden = true; });
document.getElementById("turn").addEventListener("scroll", () => { selMenu.hidden = true; }, true);

// --- the shelf: one click puts a symbol at the cursor (or copies it) ---
const SHELF = ["℣", "^{(a)}", "^{(b)}", "^{(c)}", "^{(d)}", "^{(e)}", "^{(f)}", "«", "»"];
for (const t of SHELF) {
  const b = Object.assign(document.createElement("button"), { className: "shelf-item", textContent: t, title: `Insert ${t}` });
  b.addEventListener("mousedown", (e) => e.preventDefault());  // the field keeps its cursor
  b.onclick = async () => {
    const s = getSelection();
    const f = s.rangeCount ? fieldAt(s.anchorNode) : null;
    const sel = f && f.selection();
    if (f && sel && document.activeElement === f.el) { f.edit(sel[0], sel[1], t); return; }
    try { await navigator.clipboard.writeText(t); toast(`Copied ${t}`); } catch (e) { toast("Could not copy"); }
  };
  $("shelf").append(b);
}

// italics underlined in the commentary (the menu's choice is kept)
{
  let on = true;
  try { on = localStorage.getItem("rw-underline") !== "0"; } catch (e) {}
  const box = $("underline-it");
  box.checked = on;
  document.body.classList.toggle("no-ul", !on);
  box.onchange = () => {
    document.body.classList.toggle("no-ul", !box.checked);
    try { localStorage.setItem("rw-underline", box.checked ? "1" : "0"); } catch (e) {}
  };
}
