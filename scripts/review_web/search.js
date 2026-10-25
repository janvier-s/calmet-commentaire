// Word search, from the ch:v box: every place in the book (or every book) where the words occur,
// accents and case aside; a hit opens its page with the words marked.
import { S, api, hooks, nav } from "./app.js";

const $ = (id) => document.getElementById(id);
const el = (tag, props = {}, ...kids) => {
  const e = Object.assign(document.createElement(tag), props);
  e.append(...kids.filter((k) => k != null));
  return e;
};

const R = { q: null, vol: null, hits: [], total: 0, at: -1 };
let allBooks = false;

const where = (h) => `${h.vol === S.vol && !allBooks ? "" : h.vol + " "}p.${h.page} · ${h.path[h.path.length - 1].replace(/_/g, " ")}`;

function row(h, i) {
  return el("button", { className: "hit" + (i === R.at ? " cur" : ""), onclick: () => openHit(i) },
    el("span", { className: "where", textContent: where(h) }),
    el("span", { className: "snip" }, h.before.length >= 50 ? "…" : "", h.before.replace(/\s+/g, " "),
       el("mark", { textContent: h.match }), h.after.replace(/\s+/g, " "), h.after.length >= 50 ? "…" : ""));
}

function render() {
  const pages = new Set(R.hits.map((h) => `${h.vol}/${h.page}`)).size;
  const msg = !R.total ? `No “${R.q}” in ${R.vol || "any book"}`
    : `${R.total} hit${R.total > 1 ? "s" : ""} on ${pages}${R.hits.length < R.total ? "+" : ""} page${pages > 1 ? "s" : ""}` +
      (R.hits.length < R.total ? ` (first ${R.hits.length} shown)` : "");
  $("search-panel").replaceChildren(
    el("div", { className: "search-head" }, el("b", { textContent: msg }), el("span", { className: "grow" }),
       el("label", { className: "muted small" },
          el("input", { type: "checkbox", checked: allBooks, onchange: (e) => { allBooks = e.target.checked; run(R.q); } }),
          " All books"),
       el("button", { className: "link", title: "Close (Esc)", textContent: "✕", onclick: () => showPanel(false) })),
    el("div", { className: "hits" }, ...R.hits.map(row)));
  $("search-step").hidden = !R.hits.length;
  $("search-pos").textContent = R.hits.length ? `${R.at + 1 || "–"}/${R.hits.length}` : "";
}

function showPanel(on) {
  $("search-panel").hidden = !on;
  if (on) {
    const cur = $("search-panel").querySelector(".hit.cur");
    if (cur) cur.scrollIntoView({ block: "nearest" });
  }
}

async function run(q) {
  R.q = q.trim();
  R.vol = allBooks ? null : S.vol;
  const p = new URLSearchParams({ q: R.q });
  if (R.vol) p.set("vol", R.vol);
  $("jump-msg").textContent = "searching…";
  const r = await api(`/api/search?${p}`);
  $("jump-msg").textContent = "";
  if (r.status !== 200) { $("jump-msg").textContent = r.body.error || "search failed"; return; }
  Object.assign(R, { hits: r.body.hits, total: r.body.total, at: -1 });
  render();
  showPanel(true);
}

/** Mark every hit of the page shown; the current one scrolled to and flashed. */
function markPage() {
  const h = R.hits[R.at];
  if (!h || h.vol !== S.vol || h.page !== S.page || !S.fields) return;
  const key = (path) => path.join("/");
  if (S.section !== "all" && !S.fields.some((x) => key(x.path) === key(h.path))) {
    document.querySelector('#sections button[data-sec="all"]').click();  // the field is hidden by the section filter
  }
  const spans = new Map();
  for (const x of R.hits) {
    if (x.vol === S.vol && x.page === S.page) spans.set(key(x.path), [...(spans.get(key(x.path)) || []), [x.start, x.end]]);
  }
  for (const { path, field } of S.fields) {
    const s = spans.get(key(path));
    if (s || field.marks) field.setMarks(s || null);
  }
  const f = S.fields.find((x) => key(x.path) === key(h.path));
  if (!f) return;
  // the hit's line: as far down the field as the hit is into its text
  const pane = $("text-pane"), r = f.field.el.getBoundingClientRect();
  const y = r.top - pane.getBoundingClientRect().top + pane.scrollTop + r.height * (h.start / Math.max(1, f.field.text.length));
  pane.scrollTop = Math.max(0, y - pane.clientHeight / 3);
  const b = f.field.el.closest(".block");
  if (b) { b.classList.remove("flash"); void b.offsetWidth; b.classList.add("flash"); }
}

async function openHit(i) {
  if (i < 0 || i >= R.hits.length) return;
  const prev = R.at;
  R.at = i;
  showPanel(false);
  const h = R.hits[i];
  if (h.vol !== S.vol || h.page !== S.page || $("cols").hidden) {
    if ((await nav.go(h.vol, h.page)) === null) { R.at = prev; return; }  // the person stayed
  }
  render();
  markPage();
}

hooks.search = (q) => (q.trim() === R.q && R.hits.length && (allBooks || R.vol === S.vol) ? openHit((R.at + 1) % R.hits.length) : run(q));

$("search-prev").onclick = () => openHit((R.at - 1 + R.hits.length) % R.hits.length);
$("search-next").onclick = () => openHit((R.at + 1) % R.hits.length);
$("search-pos").onclick = () => showPanel($("search-panel").hidden);
document.addEventListener("click", (e) => { if (!e.target.closest(".jumpbox, #search-step")) showPanel(false); });
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !$("search-panel").hidden) { e.preventDefault(); e.stopImmediatePropagation(); showPanel(false); }
}, true);
