// Editing: the fields, saving (with the on-disk check), Tab between fields, unsaved changes.
import { S, api, ask, hooks, nav, renderPage, toast, loadPage } from "./app.js";
import { Field } from "./field.js";

const $ = (id) => document.getElementById(id);
const INT_FIELDS = new Set(["verse_number", "commentary_id", "verse_ref", "chapter_number", "chapter"]);

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

S.edits = 0;  // counts every edit, so a save knows whether typing went on meanwhile
hooks.makeField = (f, name, value, path) => {
  let timer = null;  // per field: each lemma gets its small caps
  const field = new Field(f, {
    name, value, latinCase: (t, redraw) => {
      clearTimeout(timer);
      if (cased.has(t)) return cased.get(t);
      timer = setTimeout(() => latinCase(t, redraw), 300);
      return null;
    },
    onChange: () => { S.edits++; setDirty(true); },
  });
  f.classList.toggle("hide-marks", !$("show-marks").checked);
  if (name === "french_commentary" && !field.text.trim()) f.style.minHeight = "6em";
  f.addEventListener("focus", () => { lastField = field; });
  f.addEventListener("keydown", (e) => {
    if (e.key !== "Tab") return;
    e.preventDefault();
    const all = S.fields.map((x) => x.field);
    const next = all[(all.indexOf(field) + (e.shiftKey ? -1 : 1) + all.length) % all.length];
    next.el.focus();
    next.select(0, next.text.length);
    next.el.scrollIntoView({ block: "nearest" });
  });
  S.fields.push({ path, field });
};
hooks.beforeRender = () => { S.fields = []; lastField = null; };
hooks.collect = () => { if (S.fields.length) S.data = typedData(); };  // keep typed text over a redraw

export function setDirty(on) {
  S.dirty = on;
  const d = $("dirty");
  d.textContent = on ? "● unsaved changes" : "";
  d.classList.toggle("unsaved", on);
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
  let r = await api("/api/page", { vol: S.vol, page: S.page, data, version: S.version });
  if (r.status === 409) {
    const choice = await ask(
      "This page was changed on disk since you opened it (a script, or another editor).\n\n" +
      "Reload theirs: your unsaved changes on this page are dropped.\nKeep mine: overwrite the file with what you see.",
      [["cancel", "Cancel"], ["theirs", "Reload theirs"], ["mine", "Keep mine", "warn"]]);
    if (choice === "theirs") { setDirty(false); await loadPage(S.vol, S.page); return false; }
    if (choice !== "mine") return false;
    r = await api("/api/page", { vol: S.vol, page: S.page, data, version: S.version, force: true });
  }
  if (r.status !== 200) { toast(r.body.error || "Save failed"); return false; }
  const changed = JSON.stringify(r.body.data) !== JSON.stringify(data);
  S.data = r.body.data;
  S.version = r.body.version;
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
  return true;
}

// leaving a page with unsaved changes asks first; a failed save stays
const plainGo = nav.go;
nav.go = async (vol, page) => {
  if (S.dirty && S.data) {
    const choice = await ask(`Save your changes to ${S.vol} p.${S.page} before leaving?`,
                             [["cancel", "Cancel"], ["discard", "Don't save"], ["save", "Save", "ok"]]);
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
  }
  setDirty(false);
  const top = $("text-pane").scrollTop;
  renderPage();
  $("text-pane").scrollTop = top;
  toast("Page put back as you opened it");
}
$("undo-all").onclick = undoAll;

$("save").onclick = () => save();
$("italic").onmousedown = (e) => e.preventDefault();  // keep the selection in the field
$("italic").onclick = () => lastField && lastField.toggleItalic();
$("show-marks").onchange = (e) => document.querySelectorAll(".f").forEach((f) => f.classList.toggle("hide-marks", !e.target.checked));
document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") { e.preventDefault(); save(); }
});
addEventListener("beforeunload", (e) => { if (S.dirty) e.preventDefault(); });

// --- a little italics button over a selection in a field ---
const floatBtn = Object.assign(document.createElement("button"), { id: "float-italic", title: "Italics (⌘I)", hidden: true });
floatBtn.innerHTML = "<i>I</i>";
document.body.append(floatBtn);
const fieldAt = (node) => (S.fields.find((x) => x.field.el.contains(node)) || {}).field || null;
floatBtn.addEventListener("mousedown", (e) => e.preventDefault());  // keep the selection
floatBtn.onclick = () => {
  const s = getSelection();
  const f = s.rangeCount ? fieldAt(s.anchorNode) : null;
  if (f) f.toggleItalic();
};
document.addEventListener("selectionchange", () => {
  const s = getSelection();
  const f = !s.isCollapsed && s.rangeCount ? fieldAt(s.anchorNode) : null;
  if (!f || !f.el.contains(s.focusNode)) { floatBtn.hidden = true; return; }
  const r = s.getRangeAt(0).getBoundingClientRect();
  floatBtn.hidden = false;
  floatBtn.style.left = `${Math.max(4, r.left + r.width / 2 - 14)}px`;
  floatBtn.style.top = `${Math.max(4, r.top - 34)}px`;
});
document.getElementById("text-pane").addEventListener("scroll", () => { floatBtn.hidden = true; });

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
