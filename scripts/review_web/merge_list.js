// The /merge list view: a volume's good_units, filtered, grouped by status.
import { el } from "./goodfig.js";
import { STATUS_ORDER, TYPES, counter, filterRows, sortRows, toHash } from "./merge_state.js";

const num = (n) => Number(n || 0).toLocaleString("en-US");
export const LABEL = { only_old: "only old", only_good: "only Good" };
export const badge = (status) => el("span", { className: `mg-badge mg-s-${status}`, textContent: LABEL[status] || status });

export function ref(r) {
  const at = r.verse != null ? `${r.chapter}:${r.verse}` : r.chapter != null ? `${r.chapter}` : "";
  return at;
}

const go = (state, patch) => { location.hash = toHash({ ...state, ...patch }); };

function chips(name, values, counts, selected, onToggle) {
  return el("div", { className: "mg-chips" }, el("span", { className: "muted small", textContent: name }),
    ...values.filter((v) => counts[v]).map((v) => {
      const on = !selected || selected.has(v);
      return el("button", {
        className: `mg-chip${on ? " on" : ""}`, title: on ? "Shown: click to hide" : "Hidden: click to show",
        onclick: () => onToggle(v),
      }, `${LABEL[v] || v} `, el("span", { className: "mg-n", textContent: num(counts[v]) }));
    }));
}

function tally(rows, key) {
  const out = {};
  for (const r of rows) out[r[key]] = (out[r[key]] || 0) + 1;
  return out;
}

/** The list: `list` is /api/merge/list's answer, `vols` /api/merge/vols's. */
export function renderList(root, list, vols, state) {
  const rows = list.rows;
  const shown = sortRows(filterRows(rows, state));
  const stale = rows.filter((r) => r.stale).length;

  const book = el("select", { title: "Book (volumes with a good_units.json)",
    onchange: () => go(state, { vol: book.value, uid: null, open: null, chapter: null }) },
    ...vols.map((v) => el("option", { value: v.vol, textContent: v.vol, selected: v.vol === list.vol })));
  const chapters = [...new Set(rows.map((r) => r.chapter).filter((c) => c != null))].sort((a, b) => a - b);
  const chapter = el("select", { title: "Chapter",
    onchange: () => go(state, { chapter: chapter.value === "" ? null : Number(chapter.value) }) },
    el("option", { value: "", textContent: "All chapters" }),
    ...chapters.map((c) => el("option", { value: c, textContent: `Chapter ${c}`, selected: c === state.chapter })));

  const toggleIn = (set, all, v) => {
    const s = new Set(set || all);
    if (s.has(v)) s.delete(v); else s.add(v);
    return s;
  };
  const types = chips("type", TYPES, tally(rows, "type"), state.types,
    (v) => go(state, { types: toggleIn(state.types, TYPES, v) }));
  const statuses = chips("status", STATUS_ORDER, tally(rows, "status"), state.statuses,
    (v) => go(state, { statuses: toggleIn(state.statuses, STATUS_ORDER, v) }));

  const count = el("div", { className: "mg-counter" }, counter(list.vol, rows, list.summary),
    stale ? el("span", { className: "mg-stale-n", title: "normalized changed since good_units ran: re-run good_units.py",
      textContent: ` · ${num(stale)} stale` }) : null,
    list.unattached ? el("span", { className: "muted", title: "Good blocks good_units could not attach to any unit: they have no row",
      textContent: ` · ${num(list.unattached)} unattached Good block${list.unattached > 1 ? "s" : ""}` }) : null);

  const top = el("header", { className: "mg-top" }, book, count, el("span", { className: "grow" }),
    el("a", { href: "/", className: "mg-toplink", textContent: "Queue" }));
  const filters = el("div", { className: "mg-filters" }, types, statuses, chapter,
    el("span", { className: "muted small", textContent: `${num(shown.length)} shown` }));

  const body = el("div", { className: "mg-list" });
  let group = null;
  for (const r of shown) {
    if (r.status !== group) {
      group = r.status;
      const n = shown.filter((x) => x.status === group).length;
      body.append(el("div", { className: "mg-group" }, badge(group), el("span", { textContent: ` · ${num(n)}` }),
        list.notes && list.notes[group] ? el("span", { className: "mg-note", textContent: list.notes[group] }) : null));
    }
    const words = r.lemma || r.first || "";
    body.append(el("a", { className: "mg-row", href: toHash({ ...state, uid: r.uid, open: null }) },
      el("span", { className: "mg-type", textContent: r.type }),
      el("span", { className: "mg-ref" }, ref(r), r.after ? el("span", { className: "muted small", textContent: ` · after ${r.after}` }) : null),
      el("span", { className: `mg-words${r.lemma ? " lemma" : ""}`, textContent: words }),
      badge(r.status),
      el("span", { className: "mg-n", title: "changes (noise left out)", textContent: r.n ? num(r.n) : "" }),
      el("span", { className: "mg-progress", title: "review progress (part 3)" }),
      r.stale ? el("span", { className: "mg-badge mg-stale", title: "normalized changed since good_units ran: re-run good_units.py", textContent: "stale" }) : el("span")));
  }
  if (!shown.length) body.append(el("p", { className: "muted", textContent: "No unit passes these filters." }));
  root.replaceChildren(top, filters, body);
}
