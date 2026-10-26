// Page to-dos: what remains to do on a page that no check finds (a rescan, an abbreviation…).
// "+ To-do" in the issue bar adds one for the page; with "To-do" on, every field has its own "+".
// They are issues of the type To-do: Resolved ticks one off, ✕ on its card deletes it.
import { S, api, ask, hooks, toast } from "./app.js";
import { icon } from "./icons.js";
import { listAdd, listRemove, refreshCounts, renderIssues } from "./queue.js";

const $ = (id) => document.getElementById(id);
const el = (tag, props = {}, ...kids) => {
  const e = Object.assign(document.createElement(tag), props);
  e.append(...kids.filter((k) => k != null));
  return e;
};

/** A field's place as an issue's `where` (data-path "commentary/3/french_commentary"). */
function whereOf(path) {
  const p = path.split("/");
  return p.length === 3 ? { section: p[0], index: +p[1], field: p[2] } : { section: "heading", index: 0, field: p[0] };
}

async function add(msg, where) {
  const r = await api("/api/todo", { vol: S.vol, page: S.page, msg, where });
  if (r.status !== 200) { toast(r.body.error || "Could not add the to-do"); return; }
  S.issues = r.body.issues;
  listAdd(r.body.item);
  renderIssues();
  await refreshCounts();
  toast(`To-do added: ${msg}`);
}

/** The presets as buttons, then a line for anything else. */
async function prompt(where) {
  const input = el("input", { placeholder: "Or type a to-do…" });
  let chosen = null;
  const presets = el("div", { className: "todo-presets" }, ...(S.config.todo_presets || []).map((p) =>
    el("button", { type: "button", textContent: p, onclick: () => { chosen = p; $("dialog").close("add"); } })));
  const body = el("div", {}, presets, input);
  input.onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); $("dialog").close("add"); } };
  const what = where ? `${where.field.replace(/_/g, " ")}${where.section !== "heading" ? ` (${where.section} ${where.index + 1})` : ""}` : "this page";
  const r = await ask(`To-do for ${what}, p.${S.page}:`, [["cancel", "Cancel"], ["add", "Add", "ok"]], body);
  const msg = (chosen || input.value).trim();
  if (r === "add" && msg) await add(chosen ? (where ? `${chosen} (${what})` : chosen) : msg, where);
}

hooks.deleteTodo = async (it) => {
  if (await ask(`Delete this to-do?\n\n${it.msg}`, [["cancel", "Cancel"], ["yes", "Delete", "warn"]]) !== "yes") return;
  const r = await api("/api/todo/delete", { id: it.id });
  if (r.status !== 200) { toast(r.body.error || "Could not delete the to-do"); return; }
  if (it.book_dir === S.vol && it.page === S.page) S.issues = r.body.issues;
  listRemove(it.id);
  renderIssues();
  await refreshCounts();
};

// "+ To-do" for the page, beside the page's issues
const pageBtn = el("button", { id: "todo-page", className: "link", title: "Add a to-do for this page (something no check finds)",
                               onclick: () => prompt(null) }, icon("plus", 12), "To-do");
$("pageinfo").append(pageBtn);

// "To-do": a "+" on every field, for a to-do about that field
let on = false;
try { on = localStorage.getItem("rw-todo") === "1"; } catch (e) {}
const btn = el("button", { id: "todo-btn", textContent: "To-do", title: "A “+” on every field, to note a to-do about it" });
const show = (v) => {
  on = v;
  btn.classList.toggle("on", on);
  document.body.classList.toggle("todo-on", on);
  try { localStorage.setItem("rw-todo", on ? "1" : "0"); } catch (e) {}
};
$("sections").insertBefore(btn, $("sections").querySelector(".grow"));
btn.onclick = () => show(!on);
show(on);
hooks.afterRender.push((root) => {
  for (const f of root.querySelectorAll(".f[data-path]")) {
    const b = el("button", { className: "todo-add", title: "Add a to-do about this field",
                             onclick: (e) => { e.stopPropagation(); prompt(whereOf(f.dataset.path)); } }, icon("plus", 11));
    b.addEventListener("mousedown", (e) => e.preventDefault());
    f.parentElement.insertBefore(b, f);
  }
});
