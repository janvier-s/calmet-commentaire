// The batch table: every issue of one type, each with its context and proposal; tick, then accept.
import { S, api, ask, nav, toast } from "./app.js";
import { save, setDirty } from "./edit.js";
import { icon } from "./icons.js";
import { diffLine } from "./proposal.js";
import { filters, openItem, recheck, refreshCounts, renderIssues, setStatus } from "./queue.js";
import { T, closeTurn } from "./turn.js";

const $ = (id) => document.getElementById(id);
const el = (tag, props = {}, ...kids) => {
  const e = Object.assign(document.createElement(tag), props);
  e.append(...kids.filter((k) => k != null));
  return e;
};
const DONE = new Set(["resolved", "false_positive"]);
const B = { open: false, rows: [] };

function show(on) {
  B.open = on;
  $("batch").hidden = !on;
  $("cols").hidden = on || T.open;
  document.body.classList.toggle("batch-open", on);
}

function context(r) {
  const c = r.context;
  if (c && typeof c === "object") {  // a page turn: the joined text, the join marked
    return el("div", {}, "…", c.tail.slice(-120), el("span", { className: "join-mark", title: "page turn" }), c.head.slice(0, 120), "…");
  }
  return el("div", {}, c == null ? "" : String(c));
}

function countTicks() {
  const n = $("batch").querySelectorAll("tbody input:checked").length;
  $("batch-accept").textContent = `Accept ${n} ticked`;
  $("batch-accept").disabled = !n;
}

function render() {
  const f = filters();
  const label = S.config.labels[f.kind] || f.kind;
  const rows = B.rows.map((r) => {
    const done = DONE.has(r.status);
    const box = el("input", { type: "checkbox", disabled: !r.proposal || done, onchange: countTicks });
    const tr = el("tr", { className: done ? "done" : "" },
      el("td", {}, box),
      el("td", { className: "pg", textContent: `${r.book_dir === f.book ? "" : r.book_dir + " "}p.${r.page}` }),
      el("td", { className: "bctx", title: "Open this issue", onclick: () => go(r) }, context(r),
         // a write-out's message only repeats the note and the proposal
         ["footnote_writeout", "ref_candidate"].includes(r.kind) ? null : el("div", { className: "msg", textContent: r.msg })),
      el("td", {}, ...(r.proposal ? r.proposal.options[0].changes.map(diffLine) : [el("span", { className: "muted small", textContent: "no proposal" })])),
      el("td", { className: "st", textContent: r.status ? r.status.replace("_", " ") : "" }));
    tr.dataset.id = r.id;
    tr.dataset.page = r.page;
    r.tr = tr;
    return tr;
  });
  $("batch").replaceChildren(
    el("div", { className: "batch-head" }, icon("table", 15), el("b", { textContent: ` ${label}` }),
       el("span", { className: "muted", textContent: ` ${B.rows.length} issues · ${B.rows.filter((r) => r.proposal).length} with a proposal` }),
       el("span", { className: "grow" }),
       el("button", { id: "batch-all", textContent: "Tick all with a proposal", onclick: tickAll }),
       el("button", { id: "batch-accept", className: "ok", disabled: true, onclick: acceptTicked }, "Accept 0 ticked"),
       el("button", { title: "Back to the page (Esc)", onclick: closeBatch }, icon("back", 13), " Page")),
    el("table", {}, el("thead", {}, el("tr", {}, ...["", "Page", "Context", "Proposed fix", "Status"].map((h) => el("th", { textContent: h })))),
       el("tbody", {}, ...rows)));
}

function tickAll() {
  for (const box of $("batch").querySelectorAll("tbody input")) if (!box.disabled) box.checked = true;
  countTicks();
}

async function acceptTicked() {
  const ids = [...$("batch").querySelectorAll("tbody input:checked")].map((b) => b.closest("tr").dataset.id);
  if (!ids.length) return;
  if (await ask(`Accept the ${ids.length} ticked proposals? Each page is written and its issue resolved.`,
                [["cancel", "Cancel"], ["yes", `Accept ${ids.length}`, "ok"]]) !== "yes") return;
  const r = await api("/api/batch/accept", { ids });
  if (r.status !== 200) { toast(r.body.error || "Failed"); return; }
  const byId = new Map(B.rows.map((x) => [x.id, x]));
  for (const id of r.body.done) {
    const row = byId.get(id);
    row.status = "resolved";
    setStatus(id, "resolved");
    row.tr.className = "done";
    row.tr.querySelector("td.st").textContent = "resolved";
    const box = row.tr.querySelector("input");
    box.checked = false;
    box.disabled = true;
  }
  for (const f of r.body.failed) {
    const row = byId.get(f.id);
    row.tr.className = "failed";
    row.tr.querySelector("td.st").textContent = f.error;
    row.tr.querySelector("input").checked = false;
  }
  countTicks();
  toast(`${r.body.done.length} accepted` + (r.body.failed.length ? `, ${r.body.failed.length} failed` : ""));
  // the audit runs again on each book touched
  const books = [...new Map(r.body.done.map((id) => byId.get(id)).map((x) => [x.book_dir, x.page])).entries()];
  for (const [vol, page] of books) await recheck(vol, page);
  await refreshCounts();
}

async function go(r) {
  closeBatch();
  if (!(await openItem(r.id))) toast("This issue is not in the current list");
}

export async function openBatch() {
  const f = filters();
  if (!f.kind) {
    await ask("Choose a type of issue in the filters first: the batch table shows one type at a time.", [["ok", "OK", "ok"]]);
    return;
  }
  if (T.open && !(await closeTurn())) return;
  if (S.dirty) {
    const choice = await ask(`Save your changes to ${S.vol} p.${S.page} first?`,
                             [["cancel", "Cancel"], ["discard", "Don't save"], ["save", "Save", "ok"]]);
    if (choice === "save") { if (!(await save({ redraw: false }))) return; }
    else if (choice !== "discard") return;
    else setDirty(false);
  }
  const q = new URLSearchParams({ status: f.status, kind: f.kind });
  if (f.cat) q.set("cat", f.cat);
  if (f.book) q.set("book", f.book);
  $("batch-btn").disabled = true;
  const r = await api(`/api/batch?${q}`);
  $("batch-btn").disabled = false;
  if (r.status !== 200) { toast(r.body.error || "Could not load the table"); return; }
  B.rows = r.body.rows;
  show(true);
  render();
  $("batch").scrollTop = 0;
}

export function closeBatch() {
  if (!B.open) return;
  show(false);
  renderIssues();
}

const innerGo = nav.go;
nav.go = (vol, page) => { closeBatch(); return innerGo(vol, page); };

$("batch-btn").onclick = () => (B.open ? closeBatch() : openBatch());
document.addEventListener("keydown", (e) => {
  if (B.open && e.key === "Escape" && !$("dialog").open) { e.preventDefault(); closeBatch(); }
});
