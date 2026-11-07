// The /merge unit view: old (left) and Good (right), the whole unit, the recorded changes highlighted in
// place; a change's panel opens under its passage, with the source scan and the Good crop on demand.
// Read-only: the decision buttons are drawn disabled (part 3).
import { el, goodFigure } from "./goodfig.js";
import { badge, ref } from "./merge_list.js";
import { BOOK_TITLES, toHash } from "./merge_state.js";

const CLS_SHOWN = new Set(["substantive", "cosmetic", "moved"]);
const ROW_WORDS = 40;  // a row closes after a run that agrees on both sides, once it holds this many words

const words = (t) => (t.match(/\S+/g) || []).length;

function pages(parts) {
  const ps = [...new Set((parts || []).map((p) => p.page))];
  return ps.length ? (ps.length > 1 ? `p.${ps[0]}–${ps[ps.length - 1]}` : `p.${ps[0]}`) : "";
}

function goodPages(where) {
  if (!where || !where.length) return "";
  const pdfs = [...new Set(where.map((g) => g.pdf))];
  const ps = where.map((g) => g.pdf_page);
  const span = ps.length > 1 ? `p.${Math.min(...ps)}–${Math.max(...ps)}` : `p.${ps[0]}`;
  return `${pdfs.join(", ")} ${span}`;
}

/** One segment drawn in a column. `side` "old" | "good". */
function segNode(s, side, state, byKey, onPick) {
  if (s.kind === "seam") {
    return el("span", { className: "mg-seam", title: `normalized: page ${s.page} starts here`, textContent: `p.${s.page}` });
  }
  if (s.kind === "unrecorded") {
    if (!state.noise || !s.t.trim()) return s.t ? document.createTextNode(s.t) : null;
    return el("span", { className: "mg-unrec", title: "unrecorded: good_variants dropped this difference without a record (not a decision target)", textContent: s.t });
  }
  if (s.kind !== "change") return document.createTextNode(s.t);
  const c = byKey.get(s.id);
  const shown = CLS_SHOWN.has(s.cls) || state.noise;
  if (!shown) return s.t ? document.createTextNode(s.t) : null;
  const cls = CLS_SHOWN.has(s.cls) ? s.cls : "noise";
  const open = state.open === s.id ? " open" : "";
  const gap = c && c.gap_in_normalized ? " mg-gap" : "";
  const lead = s.t.match(/^\s*/)[0];
  const body = s.t.slice(lead.length);
  const node = body
    ? el("span", { className: `mg-ch mg-${cls}${gap}${open}`, textContent: body })
    : el("span", { className: `mg-ch mg-mark mg-${cls}${open}`, textContent: side === "good" ? "cut" : "added",
      title: side === "good" ? "Good has nothing here" : "only Good has words here" });
  node.dataset.id = s.id;
  node.title = node.title || `${s.cls} · ${c ? c.kind : ""}`;
  node.onclick = (e) => { e.stopPropagation(); onPick(s.id); };
  const out = [lead ? document.createTextNode(lead) : null, node];
  if (gap && side === "old") out.push(el("span", { className: "mg-gaplabel", textContent: "normalized lost this" }));
  return out;
}

/** Rows of pair indexes [k0, k1): a row ends after an agreeing run once it holds ROW_WORDS words. */
function rowsOf(old, good) {
  const n = Math.max(0, ...old.map((s) => s.k + 1), ...good.map((s) => s.k + 1));
  const kind = new Map(), size = new Map();
  for (const s of old.concat(good)) {
    if (s.kind !== "seam" && !kind.has(s.k)) kind.set(s.k, s.kind);
    size.set(s.k, Math.max(size.get(s.k) || 0, words(s.t)));
  }
  const out = [];
  let start = 0, count = 0;
  for (let k = 0; k < n; k++) {
    count += size.get(k) || 0;
    if (count >= ROW_WORDS && kind.get(k) === "same") {
      out.push([start, k + 1]);
      start = k + 1;
      count = 0;
    }
  }
  if (start < n || !out.length) out.push([start, n]);
  return out;
}

function fill(cell, segs, side, state, byKey, onPick) {
  for (const s of segs) {
    const n = segNode(s, side, state, byKey, onPick);
    if (n) cell.append(...[].concat(n).filter(Boolean));
  }
}

// --- the scans ---

function scanBand(vol, page, res) {
  const url = `/scan/${encodeURIComponent(vol)}/${page}`;
  const wrap = el("div", { className: "goodfig" },
    el("div", { className: "muted small" }, el("a", { href: url, target: "_blank", textContent: `Source scan ${vol} p.${page}` })));
  const img = el("img", { src: url, alt: "source scan", draggable: false });
  if (!res.boxes || !res.boxes.length) {
    img.className = "mg-fullscan";
    wrap.append(el("div", { className: "muted small", textContent: `Whole page: ${res.reason || "the words were not found"}.` }), img);
    return wrap;
  }
  const [cx, cy] = res.crop ? res.crop : [0, 0];  // /scan/ shows the margin crop; the boxes are the scan's
  const bs = res.boxes.map(([x, y, w, h]) => [x - cx, y - cy, w, h]);
  const pad = 40;
  const y0 = Math.max(0, Math.min(...bs.map((b) => b[1])) - pad);
  const y1 = Math.max(...bs.map((b) => b[1] + b[3])) + pad;
  const band = el("div", { className: "goodband" });
  band.append(img);
  img.onload = () => {
    const k = band.clientWidth / img.naturalWidth;
    band.style.height = `${Math.max(40, (y1 - y0) * k)}px`;
    img.style.top = `${-y0 * k}px`;
    for (const [x, y, w, h] of bs) {
      band.append(el("div", { className: "goodbox mg-srcbox", style: `left:${x * k}px;top:${(y - y0) * k}px;width:${w * k}px;height:${h * k}px` }));
    }
  };
  wrap.append(band);
  return wrap;
}

async function sourceScan(box, vol, c) {
  box.replaceChildren(el("div", { className: "muted small", textContent: "Loading the source scan…" }));
  const q = new URLSearchParams({ vol, page: c.page, path: c.path, at: c.at || 0, n: Math.max(c.old_words || 0, 1) });
  try {
    const r = await fetch(`/api/merge/scanwords?${q}`, { credentials: "same-origin" });
    const res = await r.json();
    if (!r.ok) throw new Error(res.error || r.status);
    if (res.reason === "no scan") {
      box.replaceChildren(el("div", { className: "muted small", textContent: `No scan for p.${c.page}.` }));
      return;
    }
    box.replaceChildren(scanBand(vol, c.page, res));
  } catch (e) {
    box.replaceChildren(el("div", { className: "mg-error small", textContent: `Source scan: ${e.message}` }));
  }
}

/** Where a change with no Good words of its own sits in Good: the unit's word boxes around its Good word index.
 * Boxes run a little ahead of words (a word cut at a line's end has two), so this is an estimate. */
function around(view, c, reach = 4) {
  const where = view.unit.good_where || [];
  const flat = where.flatMap((g, w) => (g.boxes || []).map((b) => [w, b]));
  if (c.good_at == null || !flat.length || !view.good_tokens) return null;
  const i = Math.min(flat.length - 1, Math.round(c.good_at * flat.length / view.good_tokens));
  const w = flat[i][0];
  const near = flat.slice(Math.max(0, i - reach), i + reach).filter(([x]) => x === w).map(([, b]) => b);
  return { ...where[w], boxes: near };
}

function goodCrop(box, c, view) {
  const gs = (c.good || []).filter((g) => g.boxes && g.boxes.length);
  if (gs.length) {
    box.replaceChildren(...gs.map((g) => goodFigure(g, c.good_modern || c.good_raw)));
    return;
  }
  const near = around(view, c);
  if (near) {
    box.replaceChildren(el("div", { className: "muted small", textContent: "Good has nothing here; the Good words around where it would be (approximate):" }),
      goodFigure(near, null));
    return;
  }
  const page = (view.unit.good_where || [])[0];
  box.replaceChildren(el("div", { className: "muted small", textContent: page ? "Good has nothing here; the unit's first Good page:" : "Good has nothing here, and the unit has no Good page." }),
    ...(page ? [goodFigure({ ...page, boxes: [] }, null)] : []));
}

// --- the panel ---

function panel(c, view, state, nav) {
  const vol = state.vol;
  const row = (k, v) => (v === null || v === undefined || v === "" ? null : el("div", {}, el("span", { className: "mg-k", textContent: k }), v));
  const moved = c.class === "moved" || c.kind === "moved"
    ? (c.moved_with
      ? el("button", { className: "link", textContent: `→ ${c.moved_with}`, title: "Open the unit the passage moved to/from",
        onclick: () => nav.openUnit(c.moved_with, `moved:${view.unit.uid}`) })
      : el("span", { className: "muted", textContent: "moved · partner not found" }))
    : null;
  const ctx = c.good_before || c.good_after
    ? el("span", { className: "mg-ctx" }, `… ${c.good_before || ""} `, el("b", { textContent: c.good_modern || c.good_raw || "∅" }), ` ${c.good_after || ""} …`)
    : null;
  const srcBox = el("div", { className: "mg-scan" }), goodBox = el("div", { className: "mg-scan" });
  const toggle = (box, load) => () => { if (box.childNodes.length) box.replaceChildren(); else load(); };
  const decide = ["take Good", "keep old", "keep both", "edit"].map((t) => el("button", { textContent: t, disabled: true, title: "part 3" }));
  return el("div", { className: `mg-panel mg-p-${CLS_SHOWN.has(c.class) ? c.class : "noise"}` },
    el("div", { className: "mg-panel-head" },
      el("span", { className: `mg-tag mg-${CLS_SHOWN.has(c.class) ? c.class : "noise"}`, textContent: c.class }),
      el("span", { textContent: c.kind }),
      el("span", { className: "muted", textContent: `${c.old_words || 0} old word${c.old_words === 1 ? "" : "s"} → ${c.words || 0} Good` }),
      el("span", { className: "muted", textContent: `origin: ${c.origin}` }),
      c.gap_in_normalized ? el("span", { className: "mg-gaplabel", textContent: "normalized lost this" }) : null,
      c.placed ? null : el("span", { className: "mg-gaplabel", textContent: "not placed in the text" }),
      el("span", { className: "grow" }),
      el("button", { className: "link", textContent: "close", title: "Close (Esc)", onclick: () => nav.pick(null) })),
    el("div", { className: "mg-panel-body" },
      row("old", el("span", { className: "mg-serif", textContent: c.old || "∅" })),
      row("Good", el("span", { className: "mg-serif", textContent: (state.printed ? c.good_raw : c.good_modern || c.good_raw) || "∅" })),
      row("where", `p.${c.page} ${c.path}`),
      row("Good context", ctx),
      row("moved", moved)),
    el("div", { className: "mg-panel-actions" },
      el("button", { textContent: "Source scan", onclick: toggle(srcBox, () => sourceScan(srcBox, vol, c)) }),
      el("button", { textContent: "Good crop", onclick: toggle(goodBox, () => goodCrop(goodBox, c, view)) }),
      el("span", { className: "grow" }), ...decide),
    srcBox, goodBox);
}

// --- the view ---

/** `nav` = {prev, next, rows, list, openUnit(uid, open)}. */
export function renderUnit(root, view, state, nav) {
  const u = view.unit;
  const byKey = new Map(view.changes.map((c) => [c.key, c]));
  let movedFrom = null;
  if (state.open && state.open.startsWith("moved:")) {  // come from a moved passage: open the change linked back
    movedFrom = state.open.slice(6);
    const m = view.changes.find((c) => c.moved_with === movedFrom) || null;
    state = { ...state, open: m && m.key, _scrollTo: true };
    history.replaceState(null, "", toHash(state));
    if (m) movedFrom = null;
  }
  const go = (patch) => { location.hash = toHash({ ...state, ...patch }); };
  nav.pick = (key) => go({ open: key });
  const listHash = toHash({ ...state, uid: null, open: null });

  const counts = view.counts || {};
  const hidden = (counts.noise || 0) + (counts.unrecorded || 0);
  const cb = (label, on, key) => el("label", { className: "mg-toggle" },
    el("input", { type: "checkbox", checked: on, onchange: (e) => go({ [key]: e.target.checked }) }), ` ${label}`);
  const top = el("header", { className: "mg-top" },
    el("a", { href: listHash, className: "mg-toplink", textContent: "← list", title: "Back to the list (Esc)" }),
    el("button", { textContent: "‹ prev", disabled: !nav.prev, title: "Previous unit in the list (p)", onclick: () => go({ uid: nav.prev, open: null }) }),
    el("button", { textContent: "next ›", disabled: !nav.next, title: "Next unit in the list (n)", onclick: () => go({ uid: nav.next, open: null }) }),
    el("span", { className: "mg-title" }, `${BOOK_TITLES[state.vol] || state.vol} · ${u.type} ${ref(u)}`),
    u.lemma ? el("span", { className: "mg-serif mg-lemma", textContent: u.lemma }) : null,
    badge(u.status),
    el("span", { className: "mg-counts" },
      el("b", { className: "mg-c-s", textContent: `${counts.substantive || 0} S` }), " · ",
      el("b", { className: "mg-c-c", textContent: `${counts.cosmetic || 0} C` }), " · ",
      el("b", { className: "mg-c-m", textContent: `${counts.moved || 0} moved` }), " · ",
      el("span", { className: "muted", textContent: `${hidden} noise ${state.noise ? "shown" : "hidden"}` })),
    el("span", { className: "grow" }),
    cb("show noise", state.noise, "noise"), cb("Good as printed", state.printed, "printed"),
    el("span", { className: "mg-progress", title: "done / unreviewed (part 3)" }));

  const banners = [];
  if (movedFrom) {
    banners.push(el("div", { className: "mg-banner mg-info" }, "A passage of ",
      el("a", { href: toHash({ ...state, uid: movedFrom, open: null }), textContent: movedFrom }),
      " is recorded as moved, with this unit as its partner; no change here is linked back to it."));
  }
  if (view.stale) banners.push(el("div", { className: "mg-banner", textContent: "normalized changed since good_units ran: re-run good_units.py" }));
  if (u.after && !(view.old || []).length) {
    banners.push(el("div", { className: "muted small mg-after" }, "Falls after ",
      el("a", { href: toHash({ ...state, uid: u.after, open: null }), textContent: u.after })));
  }

  const oldSegs = view.old || [], goodSegs = (state.printed ? view.good_printed : view.good) || [];
  const grid = el("div", { className: "mg-cols" },
    el("div", { className: "mg-colhead" }, `Old · normalized ${pages(u.parts)}`),
    el("div", { className: "mg-colhead" }, `Good · ${goodPages(u.good_where)}${state.printed ? " · as printed" : ""}`));
  const openC = state.open ? byKey.get(state.open) : null;
  const addRow = (oldCell, goodCell, keys) => {
    grid.append(oldCell, goodCell);
    if (openC && openC.placed && keys.has(openC.key)) grid.append(panel(openC, view, state, nav));
  };
  const keysIn = (segs) => new Set(segs.filter((s) => s.kind === "change").map((s) => s.id));
  if (!oldSegs.length || !goodSegs.length) {  // one side empty: its explanation, the other side whole
    const o = el("div", { className: "mg-col mg-serif" }), g = el("div", { className: "mg-col mg-serif" });
    if (oldSegs.length) fill(o, oldSegs, "old", state, byKey, nav.pick);
    else o.append(el("div", { className: "mg-empty", textContent: view.empty.old || "No old text." }));
    if (goodSegs.length) fill(g, goodSegs, "good", state, byKey, nav.pick);
    else g.append(el("div", { className: "mg-empty", textContent: view.empty.good || "No Good text." }));
    addRow(o, g, new Set([...keysIn(oldSegs), ...keysIn(goodSegs)]));
  } else {
    for (const [a, b] of rowsOf(oldSegs, goodSegs)) {
      const os = oldSegs.filter((s) => s.k >= a && s.k < b), gs = goodSegs.filter((s) => s.k >= a && s.k < b);
      const o = el("div", { className: "mg-col mg-serif" }), g = el("div", { className: "mg-col mg-serif" });
      fill(o, os, "old", state, byKey, nav.pick);
      fill(g, gs, "good", state, byKey, nav.pick);
      addRow(o, g, keysIn(os));
    }
  }

  const unplaced = view.changes.filter((c) => !c.placed && (CLS_SHOWN.has(c.class) || state.noise));
  const below = [];
  if (unplaced.length) {
    const ul = el("div", { className: "mg-unplaced" },
      el("div", { className: "mg-group", textContent: `Not placed in the text: ${unplaced.length}` }));
    for (const c of unplaced) {
      ul.append(el("div", { className: `mg-uitem${state.open === c.key ? " open" : ""}`, onclick: () => nav.pick(c.key) },
        el("span", { className: `mg-tag mg-${CLS_SHOWN.has(c.class) ? c.class : "noise"}`, textContent: c.class }),
        el("span", { className: "mg-serif", textContent: ` ${c.old || "∅"} → ${c.good_modern || c.good_raw || "∅"}` }),
        el("span", { className: "muted small", textContent: ` · ${c.kind} · p.${c.page}` })));
      if (state.open === c.key) ul.append(panel(c, view, state, nav));
    }
    below.push(ul);
  }

  root.replaceChildren(top, ...banners, grid, ...below);

  // j/k: next/previous change (in the old column's order, unplaced last); n/p: unit; Esc: list
  const order = [...new Set([...root.querySelectorAll(".mg-col .mg-ch")].map((n) => n.dataset.id)), ...unplaced.map((c) => c.key)];
  document.onkeydown = (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey || /^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName)) return;
    const k = order.indexOf(state.open);
    if (e.key === "j" && order.length) go({ open: order[k < 0 ? 0 : Math.min(order.length - 1, k + 1)] });
    else if (e.key === "k" && order.length) go({ open: order[k <= 0 ? 0 : k - 1] });
    else if (e.key === "n" && nav.next) go({ uid: nav.next, open: null });
    else if (e.key === "p" && nav.prev) go({ uid: nav.prev, open: null });
    else if (e.key === "Escape") { if (state.open) go({ open: null }); else location.hash = listHash; }
    else return;
    e.preventDefault();
  };
}
