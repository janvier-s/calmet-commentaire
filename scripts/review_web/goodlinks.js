// A Good_Calmet note pairing (good_note): a note Good adds, drops, merges or splits, linked by hand to its
// counterpart (docs/good_notes_links/<vol>.json, good_links.py) when the pairing got it wrong.
import { S, api, hooks, toast } from "./app.js";
import { icon } from "./icons.js";
import { goodFigure } from "./proposal.js";
import { applyIssues, currentItem, refreshCounts, renderIssues, setStatus } from "./queue.js";

const el = (tag, props = {}, ...kids) => {
  const e = Object.assign(document.createElement(tag), props);
  e.append(...kids.filter((k) => k != null));
  return e;
};
const btn = (label, title, onclick, ic) => el("button", { title, onclick }, ...(ic ? [icon(ic, 13), " "] : []), label);
const goodName = (g) => `${g.pdf} p.${g.pdf_page} ${g.mark}`;
const jsonName = (j) => `p.${j.page} ${j.marker || "?"}`;
const goodId = (g) => ({ pdf: g.pdf, pdf_page: g.pdf_page, mark: g.mark, ...(g.n != null ? { n: g.n } : {}) });
const jsonId = (j) => ({ page: j.page, marker: j.marker, index: j.index });

function jsonBox(j) {
  return el("div", { className: "gn-json" }, el("span", { className: "muted small", textContent: `Normalized ${jsonName(j)} ` }),
    el("span", { textContent: j.text }));
}

function linkLine(e, cur) {
  const side = (x) => (x == null ? [] : Array.isArray(x) ? x : [x]);
  const gs = side(e.good), js = side(e.json);
  const what = e.kind === "none"
    ? `${gs.length ? `Good ${goodName(gs[0])}` : `normalized ${jsonName(js[0])}`}: no counterpart`
    : `Good ${gs.map(goodName).join(" + ")} ↔ normalized ${js.map(jsonName).join(" + ")} (${e.kind})`;
  return el("div", { className: "gn-link" }, icon("check", 12), ` ${what} `,
    el("span", { className: "muted small", textContent: e.by ? `${e.by}, ${(e.at || "").slice(0, 10)} ` : "" }),
    btn("Unlink", "Remove this link: the pairing decides again", () => send(cur, { op: "unlink", good: gs, json: js })));
}

async function send(cur, body) {
  const r = await api("/api/good_link", { vol: cur.book_dir, page: S.page, ...body });
  if (r.status !== 200) { toast(r.body.error || "Could not save the link"); return; }
  if ((r.body.fixed_ids || []).includes(cur.id)) setStatus(cur.id, "resolved");
  if (r.body.issues && S.vol === cur.book_dir) await applyIssues(cur.book_dir, S.page, [], r.body);
  else { await refreshCounts(); renderIssues(); }
  toast(body.op === "unlink" ? "Unlinked" : body.op === "none" ? "Marked: no counterpart" : "Linked", "ok");
  show(cur);
}

/** The other side's notes around the page, to tick and link to `from` (a Good note or a normalized one). */
async function picker(cur, box, from, fromSide) {
  const other = fromSide === "good" ? "json" : "good";
  const page = fromSide === "good" ? cur.page : from.page;
  box.replaceChildren(el("div", { className: "muted small", textContent: "Loading the notes around…" }));
  const q = (side) => api(`/api/good_note/candidates?vol=${encodeURIComponent(cur.book_dir)}&page=${page}&side=${side}`);
  const [r, r2] = await Promise.all([q(other), q(fromSide)]);
  if (r.status !== 200 || r2.status !== 200) { box.replaceChildren(); toast((r.status !== 200 ? r : r2).body.error || "Could not list the notes"); return; }
  const isFrom = (n) => (fromSide === "good" ? n.pdf === from.pdf && n.pdf_page === from.pdf_page && n.n === from.n
    : n.page === from.page && n.index === from.index);
  // the anchor's own side, near it: ticked with it, a merge (several normalized notes) or a split (several Good ones)
  const near = r2.body.notes.filter((n) => !isFrom(n) && Math.abs((fromSide === "good" ? n.src_page : n.page) - page) <= 1);
  const picked = new Set(), also = new Set();
  const row = (n, side, set) => {
    const cb = el("input", { type: "checkbox", onchange: () => (cb.checked ? set.add(n) : set.delete(n)) });
    const head = el("label", { className: "gn-pick-head" }, cb, " ",
      el("b", { textContent: side === "good" ? goodName(n) : jsonName(n) }),
      n.linked && n.linked.length ? el("span", { className: "muted small", textContent: ` (linked: ${n.linked.join(", ")})` }) : null);
    return el("div", { className: "gn-pick" + ((side === "good" ? n.src_page : n.page) === page ? " here" : "") }, head,
      side === "good" ? goodFigure(n, n.text) : el("div", { className: "small", textContent: n.text }));
  };
  const go = btn("Link", "Link the ticked notes (several: a merge or a split)", () => {
    if (!picked.size) { toast("Tick a note"); return; }
    const ids = (set, side) => [...set].map(side === "good" ? goodId : jsonId);
    const mine = [fromSide === "good" ? goodId(from) : jsonId(from), ...ids(also, fromSide)];
    const theirs = ids(picked, other);
    send(cur, { op: "link", good: fromSide === "good" ? mine : theirs, json: fromSide === "good" ? theirs : mine });
  }, "check");
  const otherName = other === "good" ? "Good_Calmet" : "normalized";
  box.replaceChildren(el("div", { className: "gn-picker" },
    el("div", { className: "muted small", textContent: `Its counterpart: ${otherName} notes, pages ${page - 2}–${page + 2}` }),
    ...(r.body.notes.length ? r.body.notes.map((n) => row(n, other, picked)) : [el("div", { className: "muted small", textContent: "None" })]),
    near.length ? el("div", { className: "muted small gn-also", textContent: `Together with (a ${fromSide === "good" ? "split" : "merge"}: several ${fromSide === "good" ? "Good_Calmet" : "normalized"} notes, one ${otherName} note):` }) : null,
    ...near.map((n) => row(n, fromSide, also)),
    el("div", { className: "acts" }, go, btn("Cancel", "", () => box.replaceChildren()))));
}

function card(cur, d) {
  const e = d.entry, ns = e.notes || {}, gs = ns.good || [], js = ns.json || [];
  const pick = el("div");
  const linked = d.links.length > 0;
  const forNote = (n, side) => el("div", { className: "acts" },
    btn("Link to…", `Pick the ${side === "good" ? "normalized" : "Good_Calmet"} note(s) it is`, () => picker(cur, pick, n, side), "plus"),
    btn("No counterpart", "This note truly has no counterpart: a real addition or drop",
      () => send(cur, { op: "none", ...(side === "good" ? { good: [goodId(n)] } : { json: [jsonId(n)] }) })));
  const parts = [];
  for (const g of gs) parts.push(goodFigure(g, g.text), forNote(g, "good"));
  for (const j of js) parts.push(jsonBox(j), forNote(j, "json"));
  const confirm = gs.length && js.length
    ? el("div", { className: "acts" }, btn(e.kind === "notes_merged" ? "Confirm merge" : e.kind === "note_split" ? "Confirm split" : "Confirm pair",
        "The pairing is right: link these notes as found", () => send(cur, { op: "link", good: gs.map(goodId), json: js.map(jsonId) }), "check"))
    : null;
  return el("div", { className: "proposal goodnote" },
    el("div", { className: "ptitle" }, el("b", { textContent: "Good_Calmet note pairing" }),
      el("span", { className: "muted small", textContent: ` ${e.kind.replace(/_/g, " ")} · ${e.cause || "unsure"}${linked ? " · linked" : ""}` })),
    ...d.links.map((x) => linkLine(x, cur)),
    ...parts, confirm, pick);
}

async function show(cur) {
  const r = await api(`/api/good_note?id=${encodeURIComponent(cur.id)}`);
  const now = currentItem();
  if (!now || now.id !== cur.id) return;
  const box = document.getElementById("current");
  box.querySelectorAll(".proposal").forEach((x) => x.remove());
  if (r.status !== 200) { toast(r.body.error || "Could not load the note pairing"); return; }
  box.append(card(cur, r.body));
}

const prev = hooks.afterIssues;
hooks.afterIssues = async (cur, here) => {
  if (!cur || cur.kind !== "good_note") return prev ? prev(cur, here) : undefined;
  if (here) await show(cur);
};
