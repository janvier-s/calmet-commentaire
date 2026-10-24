// The queue: filters with counts, the page's issues, issue to issue, Resolved / False positive / Skip.
import { S, api, ask, boot, go, nav, renderPage, showScan, toast, updateTop } from "./app.js";
import { save, setDirty } from "./edit.js";
import { icon } from "./icons.js";

const $ = (id) => document.getElementById(id);
const el = (tag, props = {}, ...kids) => {
  const e = Object.assign(document.createElement(tag), props);
  e.append(...kids.filter((k) => k != null));
  return e;
};
const DONE = new Set(["resolved", "false_positive"]);
const STATUS_LABELS = { open: "Open", false_positive: "False positives", skipped: "Skipped", resolved: "Resolved", all: "All" };
const CAT_LABELS = { all: "All", verses: "Verses", commentary: "Commentary", footnotes: "Footnotes" };

const KIND = { verses: "k-verse", commentary: "k-note", footnotes: "k-fn" };
let CAT_OF = {};  // kind -> category, from the server

const Q = { items: [], idx: 0, status: "open", cat: null, kind: null, book: null, counts: null, current: null };
const label = (k) => S.config.labels[k] || k;
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
  if (Q.kind && !kinds.includes(Q.kind)) kinds.push(Q.kind);
  const kindTotal = Object.values(c.kind).reduce((a, b) => a + b, 0);
  $("f-kind").replaceChildren(opt("", `All types (${kindTotal})`), ...kinds.map((k) => opt(k, `${label(k)} (${c.kind[k] || 0})`)));
  const books = Object.keys(c.book).sort();
  if (Q.book && !books.includes(Q.book)) books.push(Q.book);
  const bookTotal = Object.values(c.book).reduce((a, b) => a + b, 0);
  $("f-book").replaceChildren(opt("", `All books (${bookTotal})`), ...books.map((b) => opt(b, `${b} (${c.book[b] || 0})`)));
  $("f-status").value = Q.status;
  $("f-cat").value = Q.cat || "";
  $("f-kind").value = Q.kind || "";
  $("f-book").value = Q.book || "";
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
  const f = { status: $("f-status").value, cat: $("f-cat").value || null, kind: $("f-kind").value || null,
              book: $("f-book").value || null };
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
  return go(it.book_dir, it.page);
}

function step(dir) {
  for (let i = Q.idx + dir; i >= 0 && i < Q.items.length; i += dir) {
    if (Q.status === "open" && !isOpen(Q.items[i])) continue;  // marked during this session
    return goItem(i);
  }
  toast(dir > 0 ? `No more issues after this one (${STATUS_LABELS[Q.status]})` : `No earlier issues (${STATUS_LABELS[Q.status]})`);
}

function currentItem() {
  return Q.items.find((it) => it.id === Q.current) || S.issues.find((it) => it.id === Q.current) || null;
}

async function mark(status) {
  const it = currentItem();
  if (!it) { toast("No issue selected: click one in the left column"); return; }
  if (S.dirty && !(await save({ redraw: false }))) return;  // a failed save stays put
  const r = await api("/api/mark", { id: it.id, status });
  if (r.status !== 200) { toast(r.body.error || "Could not mark the issue"); return; }
  for (const x of [...Q.items, ...S.issues]) if (x.id === it.id) x.status = status;
  await refreshCounts();
  renderIssues();
  if (status) step(1);
}

// --- the left column ---
function renderIssues() {
  const box = $("page-issues");
  const cur = currentItem();
  const here = cur && cur.book_dir === S.vol && cur.page === S.page;
  $("page-issues-title").textContent = `This page · ${S.issues.length} issue${S.issues.length === 1 ? "" : "s"}`;
  const away = cur && !here ? el("p", { className: "muted small" },
    `You have left the current issue's page (${cur.book_dir} p.${cur.page}). `,
    el("button", { className: "link", textContent: "Back to it", onclick: () => go(cur.book_dir, cur.page) })) : null;
  box.replaceChildren(...(away ? [away] : []), ...S.issues.map((it) => {
    const st = statusOf(it);
    const cat = it.kind in CAT_OF ? CAT_OF[it.kind] : "commentary";
    const card = el("div", { className: `issue ${KIND[cat]}` + (DONE.has(st) ? " done" : "") + (it.id === Q.current ? " cur" : "") },
      st ? el("span", { className: "st", textContent: st.replace("_", " ") }) : null,
      el("small", {}, icon(cat, 11), " ", label(it.kind)), el("span", { className: "msg", textContent: it.msg }));
    card.onclick = () => {
      Q.current = it.id;
      const i = Q.items.findIndex((x) => x.id === it.id);
      if (i >= 0) Q.idx = i;
      updateCounter();
      renderIssues();
    };
    return card;
  }));
  const a = S.around || {};
  $("around").replaceChildren(
    a.prev != null ? el("button", { textContent: `◀ p.${a.prev} has open issues`, onclick: () => go(S.vol, a.prev) }) : null,
    a.next != null ? el("button", { textContent: `p.${a.next} has open issues ▶`, onclick: () => go(S.vol, a.next) }) : null,
    el("span", { className: "muted", textContent: `${a.open_in_book ?? 0} open in ${S.vol}` }));
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
      const first = S.issues.find(isOpen);
      if (first) Q.current = first.id;
    }
    renderIssues();
  }
  return r;
};

// --- wiring ---
$("f-status").onchange = () => applyFilters(readFilters(true));
$("f-cat").onchange = () => applyFilters(readFilters(true));
$("f-kind").onchange = () => applyFilters(readFilters(false));
$("f-book").onchange = () => applyFilters(readFilters(false));
$("issue-prev").onclick = () => step(-1);
$("issue-next").onclick = () => step(1);
$("mark-resolved").onclick = () => mark("resolved");
$("mark-fp").onclick = () => mark("false_positive");
$("mark-skip").onclick = () => mark("skipped");
$("mark-reopen").onclick = () => mark(null);
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
