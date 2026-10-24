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
  });
  return null;
}

let typingTimer = null;
hooks.makeField = (f, name, value, path) => {
  const field = new Field(f, {
    name, value, latinCase: (t, redraw) => {
      clearTimeout(typingTimer);
      if (cased.has(t)) return cased.get(t);
      typingTimer = setTimeout(() => latinCase(t, redraw), 300);
      return null;
    },
    onChange: () => setDirty(true),
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

// leaving a page saves it first; a failed save stays
const plainGo = nav.go;
nav.go = async (vol, page) => {
  if (S.dirty && !(await save({ redraw: false }))) return null;
  setDirty(false);
  return plainGo(vol, page);
};

$("save").onclick = () => save();
$("italic").onmousedown = (e) => e.preventDefault();  // keep the selection in the field
$("italic").onclick = () => lastField && lastField.toggleItalic();
$("show-marks").onchange = (e) => document.querySelectorAll(".f").forEach((f) => f.classList.toggle("hide-marks", !e.target.checked));
document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") { e.preventDefault(); save(); }
});
addEventListener("beforeunload", (e) => { if (S.dirty) e.preventDefault(); });
