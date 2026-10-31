// The batch table: every issue of one type, each with its context and proposal; tick, then accept.
import { S, api, ask, loadPage, nav, toast } from "./app.js";
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

const tickedRows = () => [...$("batch").querySelectorAll("tbody input:checked")].map((b) => B.rows.find((r) => r.id === b.closest("tr").dataset.id));
const edited = (r) => r.box && r.field && r.field.value !== r.text;  // typed in the row, not saved yet
const editedRows = () => B.rows.filter((r) => edited(r) && !DONE.has(r.status));

function countTicks() {
  const ticked = tickedRows();
  const n = ticked.filter((r) => r.proposal && !edited(r)).length, e = editedRows().length;
  $("batch-accept").textContent = `Accept ${n} ticked`;
  $("batch-accept").disabled = !n;
  $("batch-resolve").textContent = `Resolve ${ticked.length} ticked`;
  $("batch-resolve").disabled = !ticked.length;
  $("batch-fp").textContent = `False positive ${ticked.length}`;
  $("batch-fp").disabled = !ticked.length;
  $("batch-save").textContent = `Save ${e} edits`;
  $("batch-save").disabled = !e;
}

/** The context cell: the field the issue points at as a text box, or the text/join read-only. */
function contextCell(r, done) {
  if (r.editable && typeof r.context === "string" && !done) {
    r.text = r.context;
    r.field = el("textarea", { value: r.text, rows: Math.min(8, Math.max(2, Math.ceil(r.text.length / 70))), spellcheck: false,
                               className: "bedit", oninput: () => { r.tr.classList.toggle("edited", edited(r)); countTicks(); } });
    return el("td", { className: "bctx" }, r.field, r.proposal ? null : el("div", { className: "msg", textContent: r.msg }));
  }
  return el("td", { className: "bctx", title: "Open this issue", onclick: () => go(r) }, context(r),
            // a write-out's message only repeats the note and the proposal
            ["footnote_writeout", "ref_candidate", "ocr_gap"].includes(r.kind) ? null : el("div", { className: "msg", textContent: r.msg }));
}

function render() {
  const f = filters();
  const label = S.config.labels[f.kind] || f.kind;
  const rows = B.rows.map((r) => {
    const done = DONE.has(r.status);
    r.box = el("input", { type: "checkbox", disabled: done, onchange: countTicks });
    const ctx = contextCell(r, done);
    const tr = el("tr", { className: done ? "done" : "" },
      el("td", {}, r.box),
      el("td", { className: "pg", title: "Open this issue", onclick: () => go(r), textContent: `${r.book_dir === f.book ? "" : r.book_dir + " "}p.${r.page}` }),
      ctx,
      el("td", {}, ...(r.proposal ? r.proposal.options[0].changes.map(diffLine) : [el("span", { className: "muted small", textContent: "no proposal" })])),
      el("td", { className: "st", textContent: r.status ? r.status.replace("_", " ") : "" }));
    tr.dataset.id = r.id;
    tr.dataset.page = r.page;
    r.tr = tr;
    return tr;
  });
  $("batch").replaceChildren(
    el("div", { className: "batch-head" }, icon("table", 15), el("b", { textContent: ` ${label}` }),
       el("span", { className: "muted", textContent: ` ${B.rows.length} issues · ${B.rows.filter((r) => r.proposal).length} with a proposal · ${B.rows.filter((r) => r.field).length} editable` }),
       el("span", { className: "grow" }),
       el("button", { id: "batch-all", textContent: "Tick all", title: "Every row not done yet", onclick: tickAll }),
       el("button", { id: "batch-save", disabled: true, title: "Write the text you typed in the rows", onclick: () => saveEdits(editedRows()) }, "Save 0 edits"),
       el("button", { id: "batch-accept", className: "ok", disabled: true, title: "Apply the proposals of the ticked rows", onclick: acceptTicked }, "Accept 0 ticked"),
       el("button", { id: "batch-resolve", className: "ok", disabled: true, title: "Mark the ticked rows resolved (an edit typed in a ticked row is saved first)", onclick: () => markTicked("resolved") }, "Resolve 0 ticked"),
       el("button", { id: "batch-fp", disabled: true, onclick: () => markTicked("false_positive") }, "False positive 0"),
       el("button", { title: "Back to the page (Esc)", onclick: closeBatch }, icon("back", 13), " Page")),
    el("table", {}, el("thead", {}, el("tr", {}, ...["", "Page", "Context", "Proposed fix", "Status"].map((h) => el("th", { textContent: h })))),
       el("tbody", {}, ...rows)));
  countTicks();
}

function tickAll() {
  for (const box of $("batch").querySelectorAll("tbody input")) if (!box.disabled) box.checked = true;
  countTicks();
}

/** Write the rows' typed text (the audit runs again on the books touched); the rows saved are ticked, ready to validate. */
async function saveEdits(rows) {
  if (!rows.length) return [];
  const r = await api("/api/batch/edit", { edits: rows.map((x) => ({ id: x.id, was: x.text, text: x.field.value })) });
  if (r.status !== 200) { toast(r.body.error || "Failed"); return []; }
  const byId = new Map(rows.map((x) => [x.id, x]));
  for (const id of r.body.done) {
    const row = byId.get(id);
    row.text = r.body.texts[id] ?? row.field.value;  // as saved: the punctuation rules may have changed it
    row.field.value = row.text;
    row.tr.classList.remove("edited");
    row.box.checked = true;
  }
  for (const f of r.body.failed) {
    const row = byId.get(f.id);
    if (!row) continue;
    row.tr.className = "failed";
    row.tr.querySelector("td.st").textContent = f.error;
    row.box.checked = false;
  }
  countTicks();
  toast(`${r.body.done.length} saved` + (r.body.failed.length ? `, ${r.body.failed.length} failed` : ""));
  const books = [...new Map(r.body.done.map((id) => byId.get(id)).map((x) => [x.book_dir, x.page])).entries()];
  for (const [vol, page] of books) await recheck(vol, page);
  return r.body.done;
}

/** Mark the ticked rows without touching a page; a ticked row with typed text has it saved first. */
async function markTicked(status) {
  let rows = tickedRows();
  if (!rows.length) return;
  const label = status === "resolved" ? "resolved" : "false positives";
  const typed = rows.filter(edited);
  if (typed.length && status === "resolved") {
    const saved = new Set(await saveEdits(typed));
    rows = rows.filter((x) => !edited(x) || saved.has(x.id));
  } else if (typed.length) {  // false positive: the typed text is not wanted
    if (await ask(`${typed.length} ticked rows have typed text; marking them false positives drops it. Go on?`,
                  [["cancel", "Cancel"], ["yes", "Mark them", "warn"]]) !== "yes") return;
  }
  if (!rows.length) return;
  if (await ask(`Mark the ${rows.length} ticked issues ${label}?`, [["cancel", "Cancel"], ["yes", `Mark ${rows.length}`, "ok"]]) !== "yes") return;
  const r = await api("/api/batch/mark", { ids: rows.map((x) => x.id), status });
  if (r.status !== 200) { toast(r.body.error || "Failed"); return; }
  const byId = new Map(rows.map((x) => [x.id, x]));
  for (const id of r.body.done) {
    const row = byId.get(id);
    row.status = status;
    setStatus(id, status);
    row.tr.className = "done";
    row.tr.querySelector("td.st").textContent = status.replace("_", " ");
    row.box.checked = false;
    row.box.disabled = true;
    if (row.field) row.field.disabled = true;
  }
  countTicks();
  toast(`${r.body.done.length} marked ${label}`);
  await refreshCounts();
}

async function acceptTicked() {
  const ids = tickedRows().filter((x) => x.proposal && !edited(x)).map((x) => x.id);  // a proposal is for the text as it was
  const byId = new Map(B.rows.map((x) => [x.id, x]));
  if (!ids.length) return;
  if (await ask(`Accept the ${ids.length} ticked proposals? Each page is written and its issue resolved.`,
                [["cancel", "Cancel"], ["yes", `Accept ${ids.length}`, "ok"]]) !== "yes") return;
  // each with the proposal it shows: one that changed since is refused, not applied unseen
  const r = await api("/api/batch/accept", { ids: ids.map((id) => ({ id, proposal_id: byId.get(id).proposal.id })) });
  if (r.status !== 200) { toast(r.body.error || "Failed"); return; }
  for (const id of r.body.done) {
    const row = byId.get(id);
    row.status = "resolved";
    setStatus(id, "resolved");
    row.tr.className = "done";
    row.tr.querySelector("td.st").textContent = "resolved";
    row.box.checked = false;
    row.box.disabled = true;
    if (row.field) row.field.disabled = true;
  }
  for (const f of r.body.failed) {
    const row = byId.get(f.id);
    row.tr.className = "failed";
    row.tr.querySelector("td.st").textContent = f.error;
    row.box.checked = false;
  }
  countTicks();
  toast(`${r.body.done.length} accepted` + (r.body.failed.length ? `, ${r.body.failed.length} failed` : ""));
  // the audit runs again on each book touched
  const books = [...new Map(r.body.done.map((id) => byId.get(id)).map((x) => [x.book_dir, x.page])).entries()];
  for (const [vol, page] of books) await recheck(vol, page);
  await refreshCounts();
}

async function go(r) {
  if ((await closeBatch(false)) === false) return;
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
    else { setDirty(false); await loadPage(S.vol, S.page); }  // the dropped edits leave the fields too
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

/** Back to the page, reloaded unless a page change follows (a batch may have written it). */
export async function closeBatch(reload = true) {
  if (!B.open) return;
  const typed = editedRows().length;
  if (typed && await ask(`${typed} rows have text you typed and did not save. Leave the table and drop it?`,
                         [["cancel", "Cancel"], ["yes", "Leave", "warn"]]) !== "yes") return false;
  show(false);
  if (reload && S.vol && S.data) await loadPage(S.vol, S.page);
  renderIssues();
}

const innerGo = nav.go;
nav.go = async (vol, page) => { await closeBatch(false); return innerGo(vol, page); };

$("batch-btn").onclick = () => (B.open ? closeBatch() : openBatch());
document.addEventListener("keydown", (e) => {
  if (B.open && e.key === "Escape" && !$("dialog").open) { e.preventDefault(); closeBatch(); }
});
