// The queue: filters with counts, the page's issues, issue to issue, Resolved / False positive / Skip.
import { S, api, ask, boot, go, hooks, nav, renderPage, showScan, toast, updateTop } from "./app.js";
import { save, setDirty } from "./edit.js";
import { icon } from "./icons.js";
import { point } from "./point.js";

const $ = (id) => document.getElementById(id);
const el = (tag, props = {}, ...kids) => {
  const e = Object.assign(document.createElement(tag), props);
  e.append(...kids.filter((k) => k != null));
  return e;
};
const DONE = new Set(["resolved", "false_positive"]);
const STATUS_LABELS = { open: "🟠 Open", false_positive: "🚩 False positives", skipped: "⏭️ Skipped", resolved: "✅ Resolved", all: "📋 All statuses" };
const CAT_LABELS = { all: "🗂️ All categories", verses: "📖 Verses", commentary: "💬 Commentary", footnotes: "📝 Footnotes" };
const CAT_EMOJI = { verses: "📖", commentary: "💬", footnotes: "📝" };

const KIND = { verses: "k-verse", commentary: "k-note", footnotes: "k-fn" };
let CAT_OF = {};  // kind -> category, from the server

const Q = { items: [], idx: 0, status: "open", cat: null, kind: null, book: null, counts: null, current: null };
const label = (k) => S.config.labels[k] || k;
const sentence = (t) => t.charAt(0) + t.slice(1).toLowerCase();  // "MISSING VERSE" -> "Missing verse"
const statusOf = (it) => it.status || null;
const isOpen = (it) => !statusOf(it) || !["resolved", "false_positive", "skipped"].includes(statusOf(it));

function query(f) {
  const q = new URLSearchParams({ status: f.status });
  for (const k of ["cat", "kind", "book"]) if (f[k]) q.set(k, f[k]);
  return api(`/api/queue?${q}`);
}

function fillFilters() {
  const c = Q.counts;
  const opt = (value, text) => el("option", { value: value ?? "", textContent: text });
  $("f-status").replaceChildren(...S.config.statuses.map((s) => opt(s, `${STATUS_LABELS[s]} (${c.status[s]})`)));
  $("f-cat").replaceChildren(...["all", ...S.config.categories].map((k) => opt(k === "all" ? "" : k, `${CAT_LABELS[k]} (${c.cat[k]})`)));
  const kinds = Object.keys(c.kind);
  if (Q.kind && !kinds.includes(Q.kind)) kinds.unshift(Q.kind);  // done to the last: on top, not at the bottom
  const kindTotal = Object.values(c.kind).reduce((a, b) => a + b, 0);
  $("f-kind").replaceChildren(opt("", `🔎 All types (${kindTotal})`),
    ...kinds.map((k) => opt(k, `${CAT_EMOJI[CAT_OF[k]] || "💬"} ${sentence(label(k))} (${c.kind[k] || 0})`)));
  // the book chosen at the top is the book filter: each book with how many issues it has of this list
  for (const o of $("vol").options) o.textContent = c.book[o.value] ? `${o.value} (${c.book[o.value]})` : o.value;
  $("f-status").value = Q.status;
  $("f-cat").value = Q.cat || "";
  $("f-kind").value = Q.kind || "";
}

async function refreshCounts() {
  const r = await query(Q);
  Q.counts = r.body.counts;
  fillFilters();
  updateCounter();
}

/** Apply new filters; an empty result keeps the old list. */
async function applyFilters(f) {
  const r = await query(f);
  if (!r.body.items.length) {
    toast("No issues matching these filters");
    fillFilters();
    return false;
  }
  Object.assign(Q, f, { items: r.body.items, counts: r.body.counts });
  fillFilters();
  return goItem(0);
}

function readFilters(reset) {
  const f = { status: $("f-status").value, cat: $("f-cat").value || null, kind: $("f-kind").value || null, book: Q.book };
  if (reset) f.kind = null;
  return f;
}

function updateCounter() {
  const c = Q.counts && Q.counts.status;
  $("counter").textContent = Q.items.length
    ? `${Q.idx + 1}/${Q.items.length}` + (c ? ` · ${c.open} open` : "") : "no issues";
  $("counter").title = c ? `${c.open} open · ${c.skipped} skipped · ${c.false_positive} false positives · ${c.resolved} resolved` : "";
}

async function goItem(i) {
  if (!Q.items.length) return;
  Q.idx = Math.max(0, Math.min(i, Q.items.length - 1));
  const it = Q.items[Q.idx];
  Q.current = it.id;
  updateCounter();
  const r = await go(it.book_dir, it.page);
  if (r) {
    point(it);
    if (hooks.showTurn) await hooks.showTurn(it);
  }
  return r;
}

/** The next issue of the list (past the last: the first again, and back from the first: the last). */
function step(dir) {
  const n = Q.items.length;
  for (let k = 1; k <= n; k++) {
    const i = (((Q.idx + dir * k) % n) + n) % n;
    if (Q.status === "open" && !isOpen(Q.items[i])) continue;  // marked during this session
    if (i === Q.idx) break;
    if ((dir > 0 && i < Q.idx) || (dir < 0 && i > Q.idx)) toast(dir > 0 ? "Back to the first issue" : "On to the last issue");
    return goItem(i);
  }
  toast(`No other issue (${STATUS_LABELS[Q.status]})`);
}

function currentItem() {
  return Q.items.find((it) => it.id === Q.current) || S.issues.find((it) => it.id === Q.current) || null;
}

const marked = [];  // issues marked during this session, the last one last: Reopen takes them back

async function mark(status) {
  const it = currentItem();
  if (!it) { toast("No issue selected: click one in the left column"); return; }
  if (S.dirty && !(await save({ redraw: false }))) return;  // a failed save stays put
  if (hooks.beforeMark && !(await hooks.beforeMark())) return;
  const r = await api("/api/mark", { id: it.id, status });
  if (r.status !== 200) { toast(r.body.error || "Could not mark the issue"); return; }
  for (const x of [...Q.items, ...S.issues]) if (x.id === it.id) x.status = status;
  if (status) marked.push(it);
  await refreshCounts();
  renderIssues();
  if (status) step(1);
}

/** Reopen: the issue last marked resolved, false positive or skipped is open again, and shown. */
async function reopen() {
  const it = marked.pop();
  if (!it) { toast("Nothing marked yet in this session"); return; }
  const r = await api("/api/mark", { id: it.id, status: null });
  if (r.status !== 200) { marked.push(it); toast(r.body.error || "Could not reopen the issue"); return; }
  for (const x of [...Q.items, ...S.issues]) if (x.id === it.id) x.status = null;
  await refreshCounts();
  const i = Q.items.findIndex((x) => x.id === it.id);
  if (i >= 0) await goItem(i);
  else if (await go(it.book_dir, it.page)) select(it);
  toast(`Reopened: ${sentence(label(it.kind))}`);
}

// --- the issue bar: the current issue, the page's issues as pills, all of them in a panel ---
let panelOpen = false;

function card(it, big) {
  const st = statusOf(it);
  const cat = CAT_OF[it.kind] || "commentary";
  const c = el("div", { className: `issue ${KIND[cat]}` + (DONE.has(st) || it.fixed ? " done" : "") + (it.id === Q.current ? " cur" : "") + (big ? " big" : "") },
    el("small", {}, icon(cat, 12), " ", label(it.kind),
       st || it.fixed ? el("span", { className: "st", textContent: it.fixed ? "fixed on save" : st.replace("_", " ") }) : null),
    el("span", { className: "msg", textContent: it.msg }));
  if (!big) c.onclick = () => select(it);
  return c;
}

/** The issue fits the category and type chosen in the filters. */
const inFilters = (it) => (!Q.cat || (CAT_OF[it.kind] || "commentary") === Q.cat) && (!Q.kind || it.kind === Q.kind);

/** Pages before and after this one with an issue of the list, and how many the book has. */
function around() {
  const mine = Q.items.filter((it) => it.book_dir === S.vol && (Q.status !== "open" || isOpen(it)));
  const before = mine.filter((it) => it.page < S.page).map((it) => it.page);
  const after = mine.filter((it) => it.page > S.page).map((it) => it.page);
  return { prev: before.length ? Math.max(...before) : null, next: after.length ? Math.min(...after) : null, n: mine.length };
}

function select(it) {
  Q.current = it.id;
  const i = Q.items.findIndex((x) => x.id === it.id);
  if (i >= 0) Q.idx = i;
  updateCounter();
  renderIssues();
  point(it);
  if (hooks.showTurn) hooks.showTurn(it);
}

function renderIssues() {
  const cur = currentItem();
  const here = cur && cur.book_dir === S.vol && cur.page === S.page;
  const away = cur && !here ? el("div", { className: "away" },
    `You have left this issue's page (${cur.book_dir} p.${cur.page}). `,
    el("button", { className: "link", textContent: "Back to it", onclick: () => go(cur.book_dir, cur.page) })) : null;
  $("current").replaceChildren(...(cur ? [card(cur, true)] : [el("div", { className: "muted", textContent: "No issue selected" })]),
                               ...(away ? [away] : []));
  if (hooks.afterIssues) hooks.afterIssues(cur, here);
  const here_ = S.issues.filter(inFilters), hidden = S.issues.length - here_.length;
  const n = here_.length;
  const pills = here_.map((it, k) => {
    const cat = CAT_OF[it.kind] || "commentary";
    const st = statusOf(it);
    const p = el("button", { className: `pill ${KIND[cat]}` + (DONE.has(st) || it.fixed ? " done" : "") + (it.id === Q.current ? " cur" : ""),
                             title: `${label(it.kind)}: ${it.msg}`, onclick: () => select(it) }, icon(cat, 11), String(k + 1));
    return p;
  });
  const toggle = el("button", { className: "link", textContent: n ? `${panelOpen ? "▴ hide" : "▾ show"} all ${n}` : "no issues on this page",
                                disabled: !n, onclick: () => { panelOpen = !panelOpen; renderIssues(); } });
  const other = hidden ? el("span", { className: "muted small", title: "Issues of this page the category or type filter leaves out",
                                       textContent: ` +${hidden} of other type${hidden > 1 ? "s" : ""}` }) : null;
  $("pills").replaceChildren(el("span", { className: "muted small", textContent: "This page: " }), ...pills, toggle, other);
  $("page-issues").hidden = !(panelOpen && n);
  $("page-issues").replaceChildren(...here_.map((it) => card(it, false)));
  const a = around();
  $("around").replaceChildren(...[
    a.prev != null ? el("button", { className: "link", onclick: () => go(S.vol, a.prev) }, icon("prev", 12), `p.${a.prev}`) : null,
    el("span", { className: "muted small", textContent: ` ${a.n} ${Q.status === "open" ? "open " : ""}in this book ` }),
    a.next != null ? el("button", { className: "link", onclick: () => go(S.vol, a.next) }, `p.${a.next}`, icon("next", 12)) : null,
  ].filter(Boolean));
}

// a page without JSON (scan only) can be created; every load redraws the column
const innerGo = nav.go;
nav.go = async (vol, page) => {
  let r = await innerGo(vol, page);
  if (r && r.missing) {
    const msg = `${vol} page ${page} has no JSON.\nCreate an empty page to transcribe from the scan?` +
      (r.scan ? "" : "\n\n(No scan was found for this page either.)");
    if (await ask(msg, [["no", "Cancel"], ["yes", "Create page", "ok"]]) !== "yes") {
      Object.assign(S, { vol, page, data: null, version: null, ctx: null, issues: r.issues || [] });
      setDirty(false);
      renderPage();
      document.getElementById("page-text").textContent = `Page ${page} has no JSON yet.`;
      updateTop();
      showScan(r.scan);
      renderIssues();
      return null;
    }
    const c = await api("/api/page/create", { vol, page });
    if (c.status !== 200) { toast(c.body.error || "Could not create the page"); return null; }
    setDirty(false);
    r = await innerGo(vol, page);
  }
  if (r) {
    if (!Q.current) {  // opened on a page, not an issue: its first open issue is the current one
      const first = S.issues.find((it) => isOpen(it) && inFilters(it));
      if (first) Q.current = first.id;
    }
    renderIssues();
  }
  return r;
};

// --- re-check on save: the audit of the book runs again on the server ---
let running = 0;
/** Run the audit of the book again; `also`: other pages whose issues to bring back (a page turn). */
export async function recheck(vol = S.vol, page = S.page, also = []) {
  running++;
  $("rechecking").textContent = "re-checking…";
  let r;
  try { r = await api("/api/recheck", { vol, page, also }); } catch (e) { r = { status: 0, body: {} }; }
  if (--running === 0) $("rechecking").textContent = "";
  if (r.status !== 200) { toast(`Re-check failed: ${r.body.error || "no answer"}`); return; }
  const byId = new Map(r.body.issues.map((it) => [it.id, it]));
  for (const it of Q.items) {
    const fresh = byId.get(it.id);
    if (fresh) Object.assign(it, { status: fresh.status, fixed: fresh.fixed, msg: fresh.msg, where: fresh.where });
  }
  if (S.vol === vol && (S.page === page || also.includes(S.page))) {
    S.issues = r.body.issues.filter((it) => it.page === S.page);
    S.around = r.body.around;
    renderIssues();
  }
  await refreshCounts();
  const said = [r.body.fixed && `${r.body.fixed} fixed on save`, r.body.added && `${r.body.added} new`].filter(Boolean);
  if (said.length) toast(said.join(", "));
  return r.body;
}
hooks.afterSave = () => recheck();
/** An issue's status changed elsewhere (a proposal accepted or rejected): the lists follow. */
export function setStatus(id, status) {
  for (const x of [...Q.items, ...S.issues]) if (x.id === id) x.status = status;
}
/** The filters in use. */
export const filters = () => ({ status: Q.status, cat: Q.cat, kind: Q.kind, book: Q.book });

/** Open an issue of the list by id. */
export function openItem(id) {
  const i = Q.items.findIndex((x) => x.id === id);
  return i >= 0 ? goItem(i) : null;
}
/** Another book chosen at the top: its issues (same status and category; the type kept if it has
 *  any there), from the first; a book without any opens at its first page. */
hooks.switchBook = async (vol) => {
  const f = { status: Q.status, cat: Q.cat, kind: Q.kind, book: vol };
  let r = await query(f);
  if (!r.body.items.length && f.kind) { f.kind = null; r = await query(f); }
  const prev = { ...Q };
  Object.assign(Q, f, { items: r.body.items, counts: r.body.counts, current: null });
  fillFilters();
  const ok = Q.items.length ? await goItem(0) : await go(vol, null);
  if (!ok) {  // cancelled: back to where it was
    Object.assign(Q, prev);
    fillFilters();
    updateCounter();
    renderIssues();
  }
  return ok;
};
export { currentItem, renderIssues, refreshCounts, step };

// --- wiring ---
$("f-status").onchange = () => applyFilters(readFilters(true));
$("f-cat").onchange = () => applyFilters(readFilters(true));
$("f-kind").onchange = () => applyFilters(readFilters(false));
$("issue-prev").onclick = () => step(-1);
$("issue-next").onclick = () => step(1);
$("mark-resolved").onclick = () => mark("resolved");
$("mark-fp").onclick = () => mark("false_positive");
$("mark-skip").onclick = () => mark("skipped");
$("mark-reopen").onclick = reopen;
document.addEventListener("keydown", (e) => {
  if (!(e.metaKey || e.ctrlKey)) return;
  const k = e.key;
  const act = k === "Enter" ? () => mark("resolved") : k.toLowerCase() === "p" ? () => mark("false_positive")
    : k === "]" ? () => step(1) : k === "[" ? () => step(-1) : null;
  if (act) { e.preventDefault(); act(); }
});

boot.start = async () => {
  CAT_OF = S.config.kind_category || {};
  const st = S.config.start;
  const f = { status: st.status || "open", cat: st.cat || null, kind: st.kind || null, book: st.book || null };
  const r = await query(f);
  Object.assign(Q, f, { items: r.body.items, counts: r.body.counts });
  fillFilters();
  if (st.vol) return go(st.vol, st.page ?? null);  // a page asked for: open it, the queue alongside
  if (Q.items.length) return goItem(0);
  const s = (await api("/api/state")).body;
  return go(s.vol || S.config.volumes[0], s.page);
};
