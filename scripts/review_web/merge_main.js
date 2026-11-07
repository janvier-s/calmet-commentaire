// The /merge screen's entry: the state lives in the URL hash; the list or one unit is drawn from it.
import { el } from "./goodfig.js";
import { renderList } from "./merge_list.js";
import { filterRows, neighbours, parseHash, sortRows, toHash } from "./merge_state.js";

const root = document.getElementById("mg-root");
const lists = new Map();  // vol -> /api/merge/list answer
let vols = null;

async function get(path) {
  const r = await fetch(path, { credentials: "same-origin" });
  const body = await r.json().catch(() => ({ error: `${r.status} ${r.statusText}` }));
  if (!r.ok) throw new Error(body.error || `${r.status}`);
  return body;
}

async function list(vol) {
  if (!lists.has(vol)) lists.set(vol, await get(`/api/merge/list?vol=${encodeURIComponent(vol)}`));
  return lists.get(vol);
}

function fail(e) {
  root.replaceChildren(el("p", { className: "mg-error", textContent: `Could not load: ${e.message}` }),
    el("a", { href: "/", textContent: "Back to the queue" }));
}

let renderUnit = (r, view) => r.replaceChildren(el("p", { className: "muted", textContent: "unit view coming" }));
export function setUnitRenderer(fn) { renderUnit = fn; }

let drawn = 0;  // the latest draw wins when hash changes overtake slow fetches
async function draw() {
  const me = ++drawn;
  const state = parseHash(location.hash);
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
      renderList(root, l, vols, state);
      document.title = `${state.vol} · Calmet Merge`;
      return;
    }
    const view = await get(`/api/merge/unit?vol=${encodeURIComponent(state.vol)}&uid=${encodeURIComponent(state.uid)}`);
    if (me !== drawn) return;
    const rows = sortRows(filterRows(l.rows, state));
    const nav = { ...neighbours(rows, state.uid), rows, list: l,
      openUnit: (uid, open) => { location.hash = toHash({ ...state, uid, open }); } };
    renderUnit(root, view, state, nav);
    document.title = `${state.uid} · Calmet Merge`;
  } catch (e) {
    if (me === drawn) fail(e);
  }
}

window.addEventListener("hashchange", draw);
draw();
