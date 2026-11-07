// The /merge screen's entry: the state lives in the URL hash; the list or one unit is drawn from it.
import { el } from "./goodfig.js";
import "./alive.js";
import { renderList } from "./merge_list.js";
import { renderUnit } from "./merge_unit.js";
import { filterRows, neighbours, parseHash, sortRows, toHash } from "./merge_state.js";
import { Undo, inverse } from "./merge_edit.js";

const root = document.getElementById("mg-root");
const lists = new Map();  // vol -> /api/merge/list answer
let vols = null;
const undo = new Undo();  // the screen's decisions and edits, for Ctrl/Cmd+Z

async function get(path) {
  const r = await fetch(path, { credentials: "same-origin" });
  const body = await r.json().catch(() => ({ error: `${r.status} ${r.statusText}` }));
  if (!r.ok) throw new Error(body.error || `${r.status}`);
  return body;
}

async function post(path, body) {
  const r = await fetch(path, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body) });
  const out = await r.json().catch(() => ({ error: `${r.status} ${r.statusText}` }));
  if (!r.ok) throw new Error(out.error || `${r.status}`);
  return out;
}

/** A decision or mark sent (key null: the unit's own); the unit fetched again, the list row's progress updated. */
async function send(path, vol, uid, body) {
  const r = await post(path, { vol, uid, ...body });
  unitCache = null;
  const row = lists.get(vol)?.rows.find((x) => x.uid === uid);
  if (row) row.progress = r.progress;
  return r;
}

/** Text typed in the merged column (or a free edit dropped): the answer carries the unit's fresh view. */
async function sendEdit(vol, uid, body, url = "/api/merge/edit", extra = {}) {
  const r = await post(url, { vol, uid, ...body, ...extra });
  unitCache = r.view ? [vol, uid, r.view] : null;
  const row = lists.get(vol)?.rows.find((x) => x.uid === uid);
  if (row && r.progress) row.progress = r.progress;
  if (r.merged_error) console.warn("merged not rebuilt:", r.merged_error);
  return r;
}

/** Ctrl/Cmd+Z: the last decision or edit put back as it was. */
async function undoLast() {
  const x = undo.pop();
  if (!x) return;
  const inv = inverse(x);
  try {
    if (inv.kind === "decide") await send("/api/merge/decide", inv.vol, inv.uid, { key: inv.key, choice: inv.choice, text: inv.text });
    else await sendEdit(inv.vol, inv.uid, { page: inv.page, path: inv.path, a: inv.a, b: inv.b, text: inv.text, h: x.h });
  } catch (e) {
    alert(`Not undone: ${e.message}`);
  }
  unitCache = null;
  draw();
}

async function list(vol) {
  if (!lists.has(vol)) lists.set(vol, await get(`/api/merge/list?vol=${encodeURIComponent(vol)}`));
  return lists.get(vol);
}

function fail(e) {
  root.replaceChildren(el("p", { className: "mg-error", textContent: `Could not load: ${e.message}` }),
    el("a", { href: "/", textContent: "Back to the queue" }));
}

let drawn = 0;  // the latest draw wins when hash changes overtake slow fetches
let unitCache = null;  // [vol, uid, view]: toggles and panels redraw without fetching again
let last = null;  // the state drawn before
const listScroll = new Map();  // list hash -> scroll, so going back to the list keeps the place

async function draw() {
  const me = ++drawn;
  const state = parseHash(location.hash);
  try { localStorage.setItem("rw-merge-hash", location.hash); } catch (e) {}  // the editor's Merge tab comes back here
  const prev = last;
  last = state;
  if (prev && !prev.uid) listScroll.set(toHash({ ...prev, open: null }), window.scrollY);
  try {
    if (!vols) vols = (await get("/api/merge/vols")).vols;
    if (!vols.length) {
      root.replaceChildren(el("p", { className: "muted", textContent: "No volume has a good_units.json yet (run good_units.py)." }));
      return;
    }
    if (!state.vol || !vols.some((v) => v.vol === state.vol)) {
      location.replace(toHash({ ...state, vol: vols[0].vol }));
      return;
    }
    const l = await list(state.vol);
    if (me !== drawn) return;
    if (!state.uid) {
      document.onkeydown = null;
      renderList(root, l, vols, state);
      window.scrollTo(0, listScroll.get(toHash({ ...state, open: null })) || 0);
      document.title = `${state.vol} · Calmet Merge`;
      return;
    }
    let view;
    if (unitCache && unitCache[0] === state.vol && unitCache[1] === state.uid) view = unitCache[2];
    else {
      view = await get(`/api/merge/unit?vol=${encodeURIComponent(state.vol)}&uid=${encodeURIComponent(state.uid)}`);
      if (me !== drawn) return;
      unitCache = [state.vol, state.uid, view];
    }
    const sameUnit = prev && prev.uid === state.uid && prev.vol === state.vol;
    state._scrollTo = sameUnit && prev.open !== state.open;
    const rows = sortRows(filterRows(l.rows, state, state.uid));
    const nav = { ...neighbours(rows, state.uid), rows, list: l,
      openUnit: (uid, open) => { location.hash = toHash({ ...state, uid, open }); },
      decide: (key, choice, text) => send("/api/merge/decide", state.vol, state.uid, { key, choice, text }),
      cleanup: (key, record, undoIt) => sendEdit(state.vol, state.uid, {}, "/api/merge/cleanup", { key, record, undo: undoIt }),
      mark: (key, label) => send("/api/merge/mark", state.vol, state.uid, { key, label }),
      edit: (page, path, a, b, text, h) => sendEdit(state.vol, state.uid, { page, path, a, b, text, h }),
      dropEdit: (key) => sendEdit(state.vol, state.uid, { drop: key }).then(() => draw(), (e) => alert(`Not saved: ${e.message}`)),
      undo, undoLast,
      redraw: draw, fail: (e) => alert(`Not saved: ${e.message}`) };
    const y = window.scrollY;
    renderUnit(root, view, state, nav);
    window.scrollTo(0, sameUnit ? y : 0);
    const opened = (state._scrollTo || (state.open || "").startsWith("moved:")) && root.querySelector(".mg-panel");
    if (opened) opened.scrollIntoView({ block: "nearest" });
    document.title = `${state.uid} · Calmet Merge`;
  } catch (e) {
    if (me === drawn) fail(e);
  }
}

window.addEventListener("hashchange", draw);
draw();
