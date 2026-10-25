// A proposed fix: what it changes, word by word, with Accept / Edit / Reject.
import { S, api, hooks, loadPage, toast } from "./app.js";
import { save } from "./edit.js";
import { icon } from "./icons.js";
import { currentItem, refreshCounts, recheck, renderIssues, setStatus, step } from "./queue.js";
import { T, dirty as turnDirty, refresh as refreshTurn, saveTurn } from "./turn.js";
import { wordDiff } from "./text.js";

const el = (tag, props = {}, ...kids) => {
  const e = Object.assign(document.createElement(tag), props);
  e.append(...kids.filter((k) => k != null));
  return e;
};

const cache = new Map();  // item id -> proposal (or null), until something changes
const generated = (p) => /\/(footnote_writeout|ref_candidate)\//.test(p.item || "");

/** The diff of one change: red struck words removed, green ones added. */
export function diffLine(c) {
  const where = `p.${c.page} · ${c.path[2].replace(/_/g, " ")}`;
  return el("div", { className: "diff" }, el("span", { className: "where", textContent: where }),
    el("span", { className: "dt" }, ...wordDiff(c.old, c.new).map(([op, t]) =>
      op === "=" ? t : el(op === "-" ? "del" : "ins", { textContent: t }))));
}

/** The card; `inTurn` when drawn in the page-turn view. */
export function proposalCard(p, inTurn = false) {
  const opts = p.options.map((o, k) => el("div", { className: "option" },
    p.options.length > 1 ? el("div", { className: "muted small", textContent: `Option ${k + 1}: ${o.label}` }) : null,
    ...o.changes.map(diffLine),
    el("div", { className: "acts" },
      el("button", { className: "ok", title: "Accept: write it and mark the issue resolved", disabled: !p.item,
                     onclick: () => accept(p, k, inTurn) },
         icon("check", 13), " Accept"),
      el("button", { title: "Edit: put it in the fields, unsaved, to adjust", onclick: () => edit(p, k, inTurn) },
         icon("pencil", 13), " Edit"),
      k === 0 ? el("button", { title: generated(p) ? "Reject: keep the text as it is (the issue becomes a false positive)"
                                                   : "Reject: hide this proposal, fix it by hand",
                               disabled: !p.item, onclick: () => reject(p, inTurn) }, icon("x", 13), " Reject") : null)));
  return el("div", { className: "proposal" },
    el("div", { className: "ptitle" }, el("b", { textContent: "Proposed fix" }), ` · ${p.title}`,
       p.sure ? el("span", { className: "tagpill ok-pill", textContent: "sure" }) : null,
       ...p.flags.map((f) => el("span", { className: "tagpill", textContent: f.replace(/-/g, " ") })),
       ...p.why.map((w) => el("span", { className: "muted small", textContent: ` ${w}` }))),
    ...opts);
}

async function accept(p, option, inTurn) {
  if (inTurn ? turnDirty() && !(await saveTurn()) : S.dirty && !(await save({ redraw: false }))) return;
  const r = await api("/api/proposal/accept", { id: p.item, proposal_id: p.id, option });
  if (r.status !== 200) { toast(r.body.error || "Could not apply the proposal"); return; }
  cache.clear();
  setStatus(p.item, "resolved");
  toast("Accepted and saved");
  if (inTurn) await refreshTurn();
  else { await loadPage(S.vol, S.page); await recheck(); }
  await refreshCounts();
  renderIssues();
  step(1);
}

/** Write the proposal into the fields, unsaved. */
function edit(p, option, inTurn) {
  let missing = 0;
  for (const c of p.options[option].changes) {
    const key = c.path.join("/");
    const list = inTurn ? [T.a, T.b].filter((s) => s && s.page === c.page).flatMap((s) => s.fields)
      : (c.page === S.page ? S.fields : []);
    const x = list.find((y) => y.path.join("/") === key);
    if (!x) { missing++; continue; }
    x.field.edit(0, x.field.text.length, c.new ?? "");
    const b = x.field.el.closest(".block");
    if (b) { b.classList.remove("flash"); void b.offsetWidth; b.classList.add("flash"); }
  }
  if (missing) toast("Some fields are not shown: choose All in the section tabs");
}

async function reject(p, inTurn) {
  const r = await api("/api/proposal/reject", { id: p.item, proposal_id: p.id });
  if (r.status !== 200) { toast(r.body.error || "Could not reject"); return; }
  cache.clear();
  if (generated(p)) {
    setStatus(p.item, "false_positive");
    await refreshCounts();
    renderIssues();
    step(1);
  } else if (inTurn) {
    T.proposal = null;
    document.getElementById("turn-proposal").replaceChildren();
  } else renderIssues();
}

// in the page-turn view
// in the page-turn view: accepting marks the issue the view was opened for, else the turn's first open one
hooks.renderProposal = (box, p) => {
  if (!p) return box.replaceChildren();
  const open = T.issues.find((i) => !i.status && !i.fixed);
  box.replaceChildren(proposalCard({ ...p, item: p.item || T.itemId || (open && open.id) }, true));
};

// under the current issue in the issue bar (page-turn issues have theirs in the turn view)
hooks.afterIssues = async (cur, here) => {
  if (!cur || !here || S.config.turn_kinds.includes(cur.kind)) return;
  let p = cache.get(cur.id);
  if (p === undefined) {
    const r = await api(`/api/proposal?id=${encodeURIComponent(cur.id)}`);
    p = r.status === 200 ? r.body.proposal : null;
    cache.set(cur.id, p);
  }
  const now = currentItem();
  if (!now || now.id !== cur.id) return;  // moved on while it was asked for
  const box = document.getElementById("current");
  box.querySelectorAll(".proposal").forEach((x) => x.remove());
  if (p) box.append(proposalCard(p));
};
const afterSave = hooks.afterSave;
hooks.afterSave = () => { cache.clear(); return afterSave(); };
