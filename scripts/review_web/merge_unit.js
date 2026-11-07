// The /merge unit view: old (left) and Good (right), the whole unit, the recorded changes highlighted in
// place; a change's panel opens under its passage, with the old and Good pages side by side on demand.
import { el } from "./goodfig.js";
import { badge, ref } from "./merge_list.js";
import { BOOK_TITLES, toHash, undecided, unitScans } from "./merge_state.js";
import { diffClass, segmentEdits, toNodes, undoKey } from "./merge_edit.js";
import { fitHeight, nextZoom } from "./scan_zoom.js";

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
  const open = state.open === s.id ? " open" : "";
  const gap = c && c.gap_in_normalized ? " mg-gap" : "";
  const lead = s.t.match(/^\s*/)[0];
  const body = s.t.slice(lead.length);
  const d = (c && c.decision) || {};
  const dc = diffClass({ kind: c ? c.kind : "replace", class: s.cls }, !!(d.choice && (d.state === "current" || d.state === "reattached")));
  const node = body
    ? el("span", { className: `mg-ch ${dc}${gap}${open}` }, ...flagged(body, s.flags || [], lead.length))
    : el("span", { className: `mg-ch mg-mark ${dc}${open}`, textContent: side === "good" ? "cut" : "added",
      title: side === "good" ? "Good has nothing here" : "only Good has words here" });
  node.dataset.id = s.id;
  node.title = node.title || `${s.cls} · ${c ? c.kind : ""}`;
  node.onclick = (e) => { e.stopPropagation(); onPick(s.id); };
  const out = [lead ? document.createTextNode(lead) : null, node];
  if (gap && side === "old") out.push(el("span", { className: "mg-gaplabel", textContent: "normalized lost this" }));
  return out;
}

const FLAG_WHY = { stop_lower: "a stop, then a lowercase word", inner: "a mark inside a word", doubled: "two marks",
  low_conf: "Kraken read this mark unsure", no_end: "no closing mark" };

/** text with its flagged marks (offsets into the segment, `off` before text starts) dotted, to check on the scan. */
function flagged(text, flags, off) {
  const out = [];
  let at = 0;
  for (const f of flags) {
    const a = f.a - off, b = Math.max(f.b - off, a + (f.why === "no_end" ? 0 : 1));
    if (a < at || a > text.length) continue;
    if (a > at) out.push(document.createTextNode(text.slice(at, a)));
    out.push(el("span", { className: "mg-flag", title: `check on the scan: ${FLAG_WHY[f.why] || f.why}`,
      textContent: text.slice(a, b) || "␣" }));
    at = b;
  }
  if (at < text.length) out.push(document.createTextNode(text.slice(at)));
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

// --- the merged column: normalized with the decisions applied, editable, buttons after every change ---

const BTNS = [["good", "✓", "take Good (g)"], ["old", "✗", "keep old (o)"], ["both", "✎", "keep both, then edit (e)"]];
let pendingFocus = null;  // a change whose text the caret goes to after the redraw (✎)

/** normalized's raw text as DOM: markers as superscripts (atomic), _italics_ as <em>. */
function rawNodes(t) {
  return toNodes(t).map((n) => n.kind === "text" ? document.createTextNode(n.t)
    : n.kind === "marker" ? el("sup", { className: "mg-marker", contentEditable: "false", textContent: n.t.slice(2, -1), dataset: { raw: n.t } })
      : el("em", { textContent: n.t }));
}

/** A segment's text as normalized writes it, from its DOM (ghosts and buttons left out). */
export function serial(node) {
  let out = "";
  for (const ch of node.childNodes) {
    if (ch.nodeType === 3) out += ch.nodeValue;
    else if (ch.nodeType !== 1 || ch.dataset.noser) continue;
    else if (ch.dataset.raw) out += ch.dataset.raw;
    else if (ch.tagName === "EM" || ch.tagName === "I") out += `_${serial(ch)}_`;
    else if (ch.tagName === "BR") out += " ";
    else out += serial(ch);
  }
  return out.replace(/\u00a0/g, " ");
}

function mergedNode(s, i, state, byKey, nav) {
  if (s.kind === "join") return el("span", { contentEditable: "false", textContent: " ", dataset: { noser: "1" } });
  if (s.kind === "seam") {
    return el("span", { className: "mg-seam", contentEditable: "false", title: `normalized: page ${s.page} starts here`, textContent: `p.${s.page}`, dataset: { noser: "1" } });
  }
  const span = el("span", { className: "mg-seg", dataset: { i: String(i) } }, ...rawNodes(s.t));
  if (s.kind === "edit") {
    span.classList.add("mg-edited");
    span.title = "your edit";
    return span;
  }
  if (s.kind === "unrecorded" && state.noise && s.t.trim()) {
    span.classList.add("mg-unrec");
    span.title = "unrecorded: good_variants dropped this difference without a record (not a decision target)";
  }
  if (s.kind !== "change") return span;
  const c = byKey.get(s.id);
  if (!(CLS_SHOWN.has(s.cls) || state.noise)) return span;
  span.classList.add("mg-ch", ...diffClass({ kind: s.ckind, class: s.cls }, !!s.choice).split(" "));
  if (state.open === s.id) span.classList.add("open");
  span.dataset.id = span.dataset.key = s.id;
  span.title = `${s.cls} · ${s.ckind}${s.choice ? ` · decided: ${s.choice}` : ""}`;
  if (s.ghost) {
    const cut = !!s.choice;  // a decision cut these old words; else Good's words of an insert, not yet taken
    span.append(el("span", { className: `mg-ghost ${cut ? "mg-ghost-cut" : "mg-ghost-add"}`, contentEditable: "false",
      textContent: s.ghost, title: cut ? "cut by the decision (not in the text)" : "Good adds these words: ✓ takes them",
      dataset: { noser: "1" } }));
  }
  const pressed = (choice) => s.choice === choice || (choice === "both" && s.choice === "edit");
  const btns = el("span", { className: "mg-btns", contentEditable: "false", dataset: { noser: "1" } },
    ...BTNS.map(([choice, label, title]) => el("button", {
      className: `mg-btn mg-btn-${choice}${pressed(choice) ? " on" : ""}`, textContent: label,
      title: pressed(choice) ? `${title}: chosen, click to undo` : title,
      onclick: (e) => {
        e.preventDefault(); e.stopPropagation();
        if (!c) return;
        if (pressed(choice)) return nav.choose(c, null);
        if (choice === "both") pendingFocus = s.id;
        nav.choose(c, choice);
      },
    })),
    el("button", { className: "mg-btn mg-btn-info", textContent: "ⓘ", title: "Details, scans, noise/real (click the change too)",
      onclick: (e) => { e.preventDefault(); e.stopPropagation(); nav.pick(state.open === s.id ? null : s.id); } }));
  return [span, btns];
}

/** Text typed in the merged column, sent when the caret leaves the cell (or on Enter). */
function editable(cell, merged, nav) {
  cell.contentEditable = "true";
  cell.spellcheck = false;
  const commit = () => {
    const spans = [...cell.querySelectorAll(".mg-seg[data-i]")];
    const before = spans.map((sp) => ({ ...merged[+sp.dataset.i], key: merged[+sp.dataset.i].id || null }));
    const edits = segmentEdits(before, spans.map(serial));
    if (edits.length) nav.typed(edits);
  };
  cell.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); cell.blur(); }
    else if (e.key === "Escape") { e.preventDefault(); nav.redraw(); }
  });
  cell.addEventListener("focusout", (e) => { if (!cell.contains(e.relatedTarget)) commit(); });
  cell.addEventListener("paste", (e) => {  // plain text only
    e.preventDefault();
    document.execCommand("insertText", false, (e.clipboardData || window.clipboardData).getData("text/plain").replace(/\s+/g, " "));
  });
}

function fill(cell, segs, side, state, byKey, onPick) {
  for (const s of segs) {
    const n = segNode(s, side, state, byKey, onPick);
    if (n) cell.append(...[].concat(n).filter(Boolean));
  }
}

// --- the scans: the old page and the Good page side by side, whole, the change marked on both ---

const pct = (v, total) => `${(100 * v) / total}%`;

/** A whole page, its boxes (and an insert's caret) drawn on it in percent of the image, in a pane that scrolls
 * to them. `off`: where the served image starts in the boxes' pixels (the source scan's margin crop). */
function fullPage(caption, url, boxes, { caret = null, off = [0, 0], cls = "", note = null } = {}) {
  const pane = el("div", { className: "mg-pagepane" });
  const sheet = el("div", { className: "mg-sheet" });
  const img = el("img", { src: url, alt: caption, draggable: false });
  sheet.append(img);
  pane.append(sheet);
  img.onload = () => {
    const W = img.naturalWidth, H = img.naturalHeight, [cx, cy] = off;
    for (const [x, y, w, h] of boxes) {
      sheet.append(el("div", { className: `goodbox ${cls}`, style: `left:${pct(x - cx, W)};top:${pct(y - cy, H)};width:${pct(w, W)};height:${pct(h, H)}` }));
    }
    if (caret) {
      const [x, y, h] = caret;
      sheet.append(el("div", { className: "mg-caret", title: "Good's text goes here", style: `left:${pct(x - cx, W)};top:${pct(y - cy - h * 0.4, H)};height:${pct(h * 1.8, H)}` }));
    }
    const box = pane.closest(".mg-sidebyside");
    if (box && box.mgLayout) box.mgLayout();
    const ys = boxes.map((b) => b[1]).concat(caret ? [caret[1]] : []);
    if (ys.length) pane.scrollTop = Math.max(0, ((Math.min(...ys) - cy) / H) * sheet.clientHeight - pane.clientHeight / 3);
  };
  return el("div", { className: "mg-pagecol" },
    el("div", { className: "muted small" }, el("a", { href: url, target: "_blank", textContent: caption })),
    note ? el("div", { className: "muted small", textContent: note }) : null, pane);
}

/** The old page of a change, from /api/merge/scanwords: its old words boxed, or for an insert a caret. */
async function oldPage(vol, page, path, at, n) {
  const q = new URLSearchParams({ vol, page, path, at: at || 0, n });
  const url = `/scan/${encodeURIComponent(vol)}/${page}`;
  try {
    const r = await fetch(`/api/merge/scanwords?${q}`, { credentials: "same-origin" });
    const res = await r.json();
    if (!r.ok) throw new Error(res.error || r.status);
    if (res.reason === "no scan") return el("div", { className: "mg-pagecol muted small", textContent: `No scan for p.${page}.` });
    const note = res.reason ? `Not marked: ${res.reason}.` : res.caret ? "The red bar marks where Good's text would go." : null;
    return fullPage(`Old · source scan p.${page}`, url, res.boxes || [], { caret: res.caret, off: res.crop || [0, 0], cls: "mg-srcbox", note });
  } catch (e) {
    return el("div", { className: "mg-pagecol mg-error small", textContent: `Source scan p.${page}: ${e.message}` });
  }
}

const goodUrl = (g) => `/goodcrop/${encodeURIComponent(g.pdf)}/${g.pdf_page}`;
const goodCaption = (g) => `Good · ${g.pdf} p.${g.pdf_page}${g.printed ? ` (printed ${g.printed})` : ""}`;

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

/** The Good page(s) of a change, whole, its words boxed. */
function goodPagesOf(c, view) {
  const gs = (c.good || []).filter((g) => g.boxes && g.boxes.length);
  if (gs.length) return gs.map((g) => fullPage(goodCaption(g), goodUrl(g), g.boxes));
  const near = around(view, c);
  if (near) return [fullPage(goodCaption(near), goodUrl(near), near.boxes, { note: "Good has nothing here; the words around where it would be (approximate)." })];
  const page = (view.unit.good_where || [])[0];
  return page ? [fullPage(goodCaption(page), goodUrl(page), [], { note: "Good has nothing here: the unit's first Good page." })]
    : [el("div", { className: "mg-pagecol muted small", textContent: "Good has nothing here, and the unit has no Good page." })];
}

const scanView = { zoom: 1, fitV: false, marks: true };  // kept from one opening of the scans to the next

/** The scans' toolbar, as the review editor's scan pane has it: zoom out/in, Fit ↔, Fit ↕, the marks on or
 * off; it drives both pages together (Ctrl/Cmd+wheel over a page too). */
function scanTools(box) {
  const label = el("span", { className: "mg-zoom", textContent: "100%" });
  const layout = () => {
    box.classList.toggle("mg-nomarks", !scanView.marks);
    for (const pane of box.querySelectorAll(".mg-pagepane")) {
      const sheet = pane.querySelector(".mg-sheet"), img = sheet && sheet.querySelector("img");
      if (!sheet) continue;
      const z = scanView.fitV && img && img.naturalWidth
        ? fitHeight(pane.clientHeight, pane.clientWidth, img.naturalWidth, img.naturalHeight) : scanView.zoom;
      const keep = [(pane.scrollLeft + pane.clientWidth / 2) / (pane.scrollWidth || 1), (pane.scrollTop + pane.clientHeight / 2) / (pane.scrollHeight || 1)];
      sheet.style.width = `${Math.round(z * 1000) / 10}%`;
      sheet.style.margin = z < 1 ? "0 auto" : "";
      pane.scrollLeft = keep[0] * pane.scrollWidth - pane.clientWidth / 2;
      pane.scrollTop = keep[1] * pane.scrollHeight - pane.clientHeight / 2;
    }
    label.textContent = scanView.fitV ? "Fit ↕" : `${Math.round(scanView.zoom * 100)}%`;
  };
  const step = (dir) => { scanView.zoom = nextZoom(scanView.fitV ? Math.min(1, scanView.zoom) : scanView.zoom, dir); scanView.fitV = false; layout(); };
  box.mgLayout = layout;
  box.addEventListener("wheel", (e) => {
    if (!(e.metaKey || e.ctrlKey) || !e.target.closest(".mg-pagepane")) return;
    e.preventDefault();
    step(e.deltaY < 0 ? 1 : -1);
  }, { passive: false });
  const marks = el("input", { type: "checkbox", checked: scanView.marks, onchange: (e) => { scanView.marks = e.target.checked; layout(); } });
  return el("div", { className: "mg-scantools" },
    el("button", { textContent: "−", title: "Zoom out (Ctrl/Cmd+wheel)", onclick: () => step(-1) }), label,
    el("button", { textContent: "+", title: "Zoom in (Ctrl/Cmd+wheel)", onclick: () => step(1) }),
    el("button", { textContent: "Fit ↔︎", title: "Fit the page's width to the pane", onclick: () => { scanView.zoom = 1; scanView.fitV = false; layout(); } }),
    el("button", { textContent: "Fit ↕︎", title: "Fit the whole page's height to the pane", onclick: () => { scanView.fitV = true; layout(); } }),
    el("label", { className: "mg-toggle", title: "Show the change's marks on the pages" }, marks, " marks"));
}

function sideBySide(left, right) {
  const l = el("div", { className: "mg-side" }, ...left), r = el("div", { className: "mg-side" }, ...right);
  const box = el("div", { className: "mg-sidebyside" }, l, r);
  box.prepend(scanTools(box));
  requestAnimationFrame(() => box.mgLayout());
  return box;
}

async function changeScans(box, vol, c, view) {
  const loading = el("div", { className: "muted small", textContent: "Loading the source scan…" });
  box.replaceChildren(sideBySide([loading], goodPagesOf(c, view)));
  loading.replaceWith(await oldPage(vol, c.page, c.path, c.at, c.old_words || 0));
}

/** The unit's old and Good pages, side by side, under its text. */
function unitScanBar(view, state) {
  const { sources, good } = unitScans(view);
  if (!sources.length && !good.length) return null;
  const box = el("div", { className: "mg-scan" });
  const open = async () => {
    if (box.childNodes.length) return box.replaceChildren();
    const goods = good.map((g) => fullPage(goodCaption(g), goodUrl(g), g.boxes || []));
    const slots = sources.map(() => el("div", { className: "muted small", textContent: "Loading the source scan…" }));
    box.replaceChildren(sideBySide(slots.length ? slots : [el("div", { className: "muted small", textContent: "No old text." })],
      goods.length ? goods : [el("div", { className: "muted small", textContent: "No Good page." })]));
    await Promise.all(sources.map(async (s, k) => slots[k].replaceWith(await oldPage(state.vol, s.page, s.path, s.at, s.n))));
  };
  return el("div", { className: "mg-unitscans" },
    el("div", { className: "mg-panel-actions" }, el("button", { textContent: "Scans", onclick: open })), box);
}

// --- the panel ---

const DECISIONS = [["good", "take Good", "g"], ["old", "keep old", "o"], ["both", "keep both", "b"], ["edit", "edit", "e"]];
const ONE_SIDED = new Set(["only_old", "only_good", "uncovered", "unaligned"]);

/** The hand edit: Good's wording to start from; Enter saves, Shift+Enter a new line, Esc cancels. */
function openEdit(box, c, nav) {
  const d = c.decision || {};
  const ta = el("textarea", { className: "mg-edit mg-serif", value: d.text || c.good_punct || c.good_modern || c.good_raw || "" });
  ta.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (ta.value.trim()) nav.choose(c, "edit", ta.value.trim()); }
    else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); box.replaceChildren(); }
  });
  box.replaceChildren(el("div", { className: "muted small", textContent: "Enter saves · Shift+Enter: new line · Esc cancels" }), ta);
  ta.focus();
}

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
    ? el("span", { className: "mg-ctx" }, `… ${c.good_before || ""} `, el("b", { textContent: c.good_punct || c.good_modern || c.good_raw || "∅" }), ` ${c.good_after || ""} …`)
    : null;
  const scanBox = el("div", { className: "mg-scan" });
  const toggle = (box, load) => () => { if (box.childNodes.length) box.replaceChildren(); else load(); };
  const d = c.decision || {};
  const live = d.state === "current" || d.state === "reattached";
  const editBox = el("div");
  const decide = DECISIONS.map(([choice, label, key]) => el("button", {
    className: live && d.choice === choice ? "on" : "", textContent: label,
    title: live && d.choice === choice ? `Chosen: click to clear (${key})` : `${label} (${key})`,
    onclick: () => (choice === "edit" && !(live && d.choice === "edit") ? openEdit(editBox, c, nav) : nav.choose(c, live && d.choice === choice ? null : choice)),
  }));
  const marks = ["noise", "real"].map((m) => el("button", {
    className: `mg-markbtn${live && d.mark === m ? " on" : ""}`, textContent: m,
    title: live && d.mark === m ? "Marked: click to clear" : `Mark ${m}: kept as a good_variants reference item`,
    onclick: () => nav.markIt(c, live && d.mark === m ? null : m),
  }));
  const reopened = d.state === "reopened"
    ? el("div", { className: "mg-reopen" }, `Reopened: “${d.choice || d.mark}” was decided on `,
      el("span", { className: "mg-serif", textContent: `${(d.was || {}).old || "∅"} → ${(d.was || {}).good_raw || "∅"}` }),
      ", and the texts have changed since.")
    : null;
  const edited = live && d.choice === "edit" ? row("edited", el("span", { className: "mg-serif", textContent: d.text })) : null;
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
      row("Good", el("span", { className: "mg-serif", textContent: (state.printed ? c.good_raw : c.good_punct || c.good_modern || c.good_raw) || "∅" })),
      row("where", `p.${c.page} ${c.path}`),
      row("Good context", ctx),
      row("moved", moved), edited),
    reopened,
    el("div", { className: "mg-panel-actions mg-dec" },
      el("button", { textContent: "Scans", title: "The old and the Good page side by side", onclick: toggle(scanBox, () => changeScans(scanBox, vol, c, view)) }),
      el("span", { className: "grow" }), ...decide, el("span", { className: "muted small", textContent: " · " }), ...marks),
    editBox, scanBox);
}

// --- the view ---

function progressBadge(p) {
  if (!p) return el("span");
  if (p.done) return el("span", { className: "mg-progress mg-done", textContent: "✓ done" });
  return el("span", { className: `mg-progress${p.reopened ? " mg-reopened" : ""}`,
    textContent: `${p.todo} to decide${p.reopened ? ` (${p.reopened} reopened)` : ""}` });
}

/** keep / drop for a one-sided unit with no change to decide on. */
function unitDecision(view, nav) {
  if (!view.progress || view.changes.length || !ONE_SIDED.has(view.unit.status)) return [];
  const now = view.unit_decision;
  return [["keep", "keep"], ["drop", "drop"]].map(([choice, label]) => el("button", {
    className: now === choice ? "on" : "", textContent: label,
    title: now === choice ? "Chosen: click to clear" : choice === "keep" ? "Keep this unit's text in the merge" : "Leave it out of the merge",
    onclick: () => nav.choose(null, now === choice ? null : choice),
  }));
}

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
  // a decision made: the next change still to decide opens (in the j/k order), else the view redraws
  const after = (key) => () => {
    const k = order.indexOf(key);
    const next = [...order.slice(k + 1), ...order.slice(0, Math.max(0, k))].find((x) => byKey.get(x) && undecided(byKey.get(x)));
    if (key !== null && next && next !== state.open) go({ open: next });
    else nav.redraw();
  };
  nav.choose = (c, choice, text) => {
    if (c) {
      const d = c.decision || {}, isLive = d.state === "current" || d.state === "reattached";
      nav.undo.push({ kind: "decide", vol: state.vol, uid: u.uid, key: c.key,
        before: { choice: isLive ? d.choice : null, text: isLive ? d.text : null }, after: { choice, text } });
    }
    return nav.decide(c ? c.key : null, choice, text).then(state.open && choice && c && choice !== "both" ? after(c.key) : () => nav.redraw(), nav.fail);
  };
  nav.typed = async (edits) => {
    try {
      for (const e of edits) {
        const seg = view.merged.find((s) => s.page === e.page && s.path === e.path && s.a === e.a && s.b === e.b && (s.id || null) === e.key);
        if (seg && seg.kind === "change") {
          const c = byKey.get(seg.id), d = (c && c.decision) || {}, isLive = d.state === "current" || d.state === "reattached";
          nav.undo.push({ kind: "decide", vol: state.vol, uid: u.uid, key: seg.id,
            before: { choice: isLive ? d.choice : null, text: isLive ? d.text : null }, after: { choice: "edit", text: e.text } });
        } else {
          nav.undo.push({ kind: "edit", vol: state.vol, uid: u.uid, page: e.page, path: e.path, a: e.a, b: e.b, before: e.before, after: e.text });
        }
        await nav.edit(e.page, e.path, e.a, e.b, e.text);
      }
    } catch (err) { nav.fail(err); }
    nav.redraw();
  };
  nav.markIt = (c, label) => nav.mark(c.key, label).then(() => nav.redraw(), nav.fail);
  let order = [];
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
    progressBadge(view.progress), ...unitDecision(view, nav));

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

  const live = !!view.editable;
  const oldSegs = (live ? view.merged : view.old) || [], goodSegs = (state.printed ? view.good_printed : view.good) || [];
  const index = new Map(oldSegs.map((s, i) => [s, i]));
  const fillOld = (cell, segs) => {
    if (!live) return fill(cell, segs, "old", state, byKey, nav.pick);
    for (const s of segs) cell.append(...[].concat(mergedNode(s, index.get(s), state, byKey, nav)).filter(Boolean));
    editable(cell, oldSegs, nav);
  };
  const grid = el("div", { className: "mg-cols" },
    el("div", { className: "mg-colhead" }, live ? `Merged · normalized ${pages(u.parts)} with your decisions (type to edit)` : `Old · normalized ${pages(u.parts)}`),
    el("div", { className: "mg-colhead" }, `Good · ${goodPages(u.good_where)}${state.printed ? " · as printed" : ""}`));
  const openC = state.open ? byKey.get(state.open) : null;
  const addRow = (oldCell, goodCell, keys) => {
    grid.append(oldCell, goodCell);
    if (openC && openC.placed && keys.has(openC.key)) grid.append(panel(openC, view, state, nav));
  };
  const keysIn = (segs) => new Set(segs.filter((s) => s.kind === "change").map((s) => s.id));
  for (const e of view.edits || []) {  // free edits that no longer fit normalized
    banners.push(el("div", { className: "mg-banner" }, `Your edit “${e.old.trim() || "∅"} → ${e.text.trim() || "∅"}” (p.${e.page}) `,
      e.state === "overlap" ? "now runs across a change, " : "no longer finds its words in normalized, ", "so it is not applied. ",
      el("button", { className: "link", textContent: "drop it", onclick: () => nav.dropEdit(e.key) })));
  }
  if (!oldSegs.length || !goodSegs.length) {  // one side empty: its explanation, the other side whole
    const o = el("div", { className: "mg-col mg-serif" }), g = el("div", { className: "mg-col mg-serif" });
    if (oldSegs.length) fillOld(o, oldSegs);
    else o.append(el("div", { className: "mg-empty", textContent: view.empty.old || "No old text." }));
    if (goodSegs.length) fill(g, goodSegs, "good", state, byKey, nav.pick);
    else g.append(el("div", { className: "mg-empty", textContent: view.empty.good || "No Good text." }));
    addRow(o, g, new Set([...keysIn(oldSegs), ...keysIn(goodSegs)]));
  } else {
    for (const [a, b] of rowsOf(oldSegs, goodSegs)) {
      const os = oldSegs.filter((s) => s.k >= a && s.k < b), gs = goodSegs.filter((s) => s.k >= a && s.k < b);
      const o = el("div", { className: "mg-col mg-serif" }), g = el("div", { className: "mg-col mg-serif" });
      fillOld(o, os);
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
        el("span", { className: "mg-serif", textContent: ` ${c.old || "∅"} → ${c.good_punct || c.good_modern || c.good_raw || "∅"}` }),
        el("span", { className: "muted small", textContent: ` · ${c.kind} · p.${c.page}` })));
      if (state.open === c.key) ul.append(panel(c, view, state, nav));
    }
    below.push(ul);
  }

  const scans = unitScanBar(view, state);  // every unit: its old and Good pages side by side, under the text
  root.replaceChildren(top, ...banners, grid, ...(scans ? [scans] : []), ...below);
  if (pendingFocus) {  // ✎: the caret at the end of that change's text, to edit it
    const sp = root.querySelector(`.mg-seg[data-key="${CSS.escape(pendingFocus)}"]`);
    pendingFocus = null;
    if (sp) {
      const r = document.createRange(), last = [...sp.childNodes].filter((n) => !(n.dataset && n.dataset.noser)).pop();
      if (last) r.setStartAfter(last); else r.setStart(sp, 0);
      r.collapse(true);
      sp.closest(".mg-col").focus();
      const sel = getSelection(); sel.removeAllRanges(); sel.addRange(r);
    }
  }

  // j/k: next/previous change (in the old column's order, unplaced last); n/p: unit; Esc: list
  order = [...new Set([...root.querySelectorAll(".mg-col .mg-ch")].map((n) => n.dataset.id)), ...unplaced.map((c) => c.key)];
  document.onkeydown = (e) => {
    if (undoKey(e)) { e.preventDefault(); nav.undoLast(); return; }
    if (e.metaKey || e.ctrlKey || e.altKey || e.target.isContentEditable || /^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName)) return;
    const k = order.indexOf(state.open);
    if (e.key === "j" && order.length) go({ open: order[k < 0 ? 0 : Math.min(order.length - 1, k + 1)] });
    else if (e.key === "k" && order.length) go({ open: order[k <= 0 ? 0 : k - 1] });
    else if (e.key === "n" && nav.next) go({ uid: nav.next, open: null });
    else if (e.key === "p" && nav.prev) go({ uid: nav.prev, open: null });
    else if (state.open && byKey.get(state.open) && DECISIONS.some(([, , key]) => key === e.key)) {
      const [choice] = DECISIONS.find(([, , key]) => key === e.key);
      const c = byKey.get(state.open);
      if (choice === "edit") { const box = root.querySelector(".mg-panel .mg-dec + div"); if (box) openEdit(box, c, nav); }
      else nav.choose(c, choice);
    }
    else if (e.key === "Escape") { if (state.open) go({ open: null }); else location.hash = listHash; }
    else return;
    e.preventDefault();
  };
}
