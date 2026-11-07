// The /merge screen's state, without the DOM: filters, order, the URL hash, the book counter, prev/next.

export const STATUS_ORDER = ["substantive", "only_old", "only_good", "uncovered", "unaligned", "cosmetic", "identical"];
export const DEFAULT_STATUSES = STATUS_ORDER.filter((s) => s !== "identical");
export const TYPES = ["commentary", "verse", "summary", "intro", "title", "unaligned"];
export const BOOK_TITLES = { "01_genese": "Genèse" };

/** The rows that pass the filters: `types` null = every type; `chapter` null = every chapter. */
export function filterRows(rows, f) {
  return rows.filter((r) => (!f.types || f.types.has(r.type)) && f.statuses.has(r.status)
    && (f.chapter == null || r.chapter === f.chapter));
}

/** Grouped by status in STATUS_ORDER, book order within a group. */
export function sortRows(rows) {
  const rank = (s) => { const k = STATUS_ORDER.indexOf(s); return k < 0 ? STATUS_ORDER.length : k; };
  return [...rows].sort((a, b) => rank(a.status) - rank(b.status) || a.i - b.i);
}

const sameSet = (a, b) => a.size === b.size && [...a].every((x) => b.has(x));

/** The state a hash ("#vol=…&uid=…&types=…&st=…&ch=…&noise=1&printed=1&open=…") stands for. */
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
  return "#" + q.toString();
}

const num = (n) => Number(n || 0).toLocaleString("en-US");

/** "Genèse: 0 of 2,958 reviewed · 672 substantive left" (reviewed counts come with part 3). */
export function counter(vol, rows, summary) {
  return `${BOOK_TITLES[vol] || vol}: 0 of ${num(rows.length)} reviewed · ${num((summary || {}).substantive)} substantive left`;
}

/** The units before and after `uid` in the given (filtered, sorted) rows. */
export function neighbours(rows, uid) {
  const k = rows.findIndex((r) => r.uid === uid);
  if (k < 0) return { prev: null, next: null };
  return { prev: k > 0 ? rows[k - 1].uid : null, next: k + 1 < rows.length ? rows[k + 1].uid : null };
}
