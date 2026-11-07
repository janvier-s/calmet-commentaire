// The /merge screen's state, without the DOM: filters, order, the URL hash, the book counter, prev/next.

export const STATUS_ORDER = ["substantive", "only_old", "only_good", "uncovered", "unaligned", "cosmetic", "identical"];
export const DEFAULT_STATUSES = STATUS_ORDER.filter((s) => s !== "identical");
export const TYPES = ["commentary", "verse", "summary", "intro", "title", "unaligned"];
export const BOOK_TITLES = { "01_genese": "Genèse" };

const isDone = (r) => !!(r.progress && r.progress.done);

/** The rows that pass the filters: `types` null = every type; `chapter` null = every chapter; `progress`
 * "todo" / "done" / null = both; `keep`: a uid that stays whatever (the unit open, just done under "to do"). */
export function filterRows(rows, f, keep = null) {
  return rows.filter((r) => r.uid === keep || (!f.types || f.types.has(r.type)) && f.statuses.has(r.status)
    && (f.chapter == null || r.chapter === f.chapter)
    && (!f.progress || (f.progress === "done") === isDone(r))
    && (!f.check || (f.check === "unplaced" ? r.unplaced > 0 : !!(r.via && r.via.length))));
}

/** Grouped by status in STATUS_ORDER, book order within a group. */
export function sortRows(rows) {
  const rank = (s) => { const k = STATUS_ORDER.indexOf(s); return k < 0 ? STATUS_ORDER.length : k; };
  return [...rows].sort((a, b) => rank(a.status) - rank(b.status) || a.i - b.i);
}

const sameSet = (a, b) => a.size === b.size && [...a].every((x) => b.has(x));

/** The state a hash ("#vol=…&uid=…&types=…&st=…&ch=…&noise=1&printed=1&open=…&ck=…") stands for. */
export function parseHash(hash) {
  const q = new URLSearchParams((hash || "").replace(/^#/, ""));
  const list = (k) => new Set(q.get(k).split(",").filter(Boolean));
  const ch = q.get("ch");
  return {
    vol: q.get("vol") || null,
    uid: q.get("uid") || null,
    types: q.has("types") ? list("types") : null,
    statuses: q.has("st") ? list("st") : new Set(DEFAULT_STATUSES),
    chapter: ch && /^\d+$/.test(ch) ? Number(ch) : null,
    noise: q.get("noise") === "1",
    printed: q.get("printed") === "1",
    open: q.get("open") || null,
    progress: ["todo", "done"].includes(q.get("pr")) ? q.get("pr") : null,
    check: ["unplaced", "via"].includes(q.get("ck")) ? q.get("ck") : null,
  };
}

export function toHash(s) {
  const q = new URLSearchParams();
  if (s.vol) q.set("vol", s.vol);
  if (s.uid) q.set("uid", s.uid);
  if (s.types) q.set("types", [...s.types].join(","));
  if (!sameSet(s.statuses, new Set(DEFAULT_STATUSES))) q.set("st", [...s.statuses].join(","));
  if (s.chapter != null) q.set("ch", String(s.chapter));
  if (s.noise) q.set("noise", "1");
  if (s.printed) q.set("printed", "1");
  if (s.open) q.set("open", s.open);
  if (s.progress) q.set("pr", s.progress);
  if (s.check) q.set("ck", s.check);
  return "#" + q.toString();
}

const num = (n) => Number(n || 0).toLocaleString("en-US");

/** "Genèse: 212 of 2,958 done · 640 substantive left". */
export function counter(vol, rows) {
  const done = rows.filter(isDone).length, left = rows.filter((r) => r.status === "substantive" && !isDone(r)).length;
  return `${BOOK_TITLES[vol] || vol}: ${num(done)} of ${num(rows.length)} done · ${num(left)} substantive left`;
}

/** The units before and after `uid` in the given (filtered, sorted) rows. */
export function neighbours(rows, uid) {
  const k = rows.findIndex((r) => r.uid === uid);
  if (k < 0) return { prev: null, next: null };
  return { prev: k > 0 ? rows[k - 1].uid : null, next: k + 1 < rows.length ? rows[k + 1].uid : null };
}

/** A unit's own scans, for a side with no change to open a panel on: the source scan's first words on each
 * normalized page the unit has text on, and its Good pages. */
export function unitScans(view) {
  const u = view.unit || {};
  const seen = new Set(), sources = [];
  for (const p of u.parts || []) {
    if (seen.has(p.page)) continue;
    seen.add(p.page);
    sources.push({ page: p.page, path: p.path, at: 0, n: 12 });
  }
  return { sources, good: [...(u.good_where || [])] };
}
/** Whether change c still needs a decision (marked noise: no; marked real or not noise: until decided). */
export function undecided(c) {
  const d = c.decision || {};
  const live = d.state === "current" || d.state === "reattached";
  const m = live ? d.mark : null;
  const needs = m ? m === "real" : c.class !== "noise";
  return needs && !(live && d.choice);
}

