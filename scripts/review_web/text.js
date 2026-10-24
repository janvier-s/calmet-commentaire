// Pure text helpers for the editor; italicRuns and toggleItalics are page_text.py's, ported
// (tests/js/text.test.mjs runs the same cases as tests/test_page_text.py).

const CLOSING_FOLLOWERS = new Set(",.;:!?)»]");
const isSpace = (c) => /\s/.test(c);

/** Italic stretches between _underscore_ marks. openAt: an odd mark carries italics over the
 *  field's edge, "start" when the first mark closes a run begun before the field. */
export function italicRuns(s) {
  const marks = [];
  for (let i = 0; i < s.length; i++) if (s[i] === "_") marks.push(i);
  let edges = marks, openAt = null;
  if (marks.length % 2) {
    const i = marks[0];
    const closes = i + 1 === s.length || isSpace(s[i + 1]) || CLOSING_FOLLOWERS.has(s[i + 1]);
    openAt = closes ? "start" : "end";
    edges = closes ? [-1, ...marks] : [...marks, s.length];
  }
  const runs = [];
  for (let k = 0; k < edges.length; k += 2) runs.push([edges[k] + 1, edges[k + 1]]);
  return { runs, marks, openAt };
}

/** Italicize s[sa:sb], or make it roman when it is all italic already. */
export function toggleItalics(s, sa, sb) {
  sa = Math.max(0, sa);
  sb = Math.min(sb, s.length);
  while (sa < sb && (s[sa] === "_" || isSpace(s[sa]))) sa++;
  while (sb > sa && (s[sb - 1] === "_" || isSpace(s[sb - 1]))) sb--;
  if (sa >= sb) return null;
  const { runs, openAt } = italicRuns(s);
  const italic = new Set();
  for (const [a, b] of runs) for (let i = a; i < b; i++) italic.add(i);
  let make = false;
  for (let i = sa; i < sb; i++) if (s[i] !== "_" && !isSpace(s[i]) && !italic.has(i)) make = true;
  const absorbs = (c) => c === "_" || (!make && isSpace(c) && c !== "\n");
  while (sa > 0 && absorbs(s[sa - 1])) sa--;
  while (sb < s.length && absorbs(s[sb])) sb++;
  const italicAt = (p) => ((s.slice(0, p).split("_").length - 1) % 2 === 1) !== (openAt === "start");
  const opening = italicAt(sa) !== make && (make || sa > 0) ? "_" : "";
  const closing = italicAt(sb) !== make && (make || sb < s.length) ? "_" : "";
  const mid = s.slice(sa, sb).replaceAll("_", "");
  const start = sa + opening.length;
  return { text: s.slice(0, sa) + opening + mid + closing + s.slice(sb), start, end: start + mid.length };
}

/** "17:2" → {chapter, verse}; "17" → {chapter, verse: null}; "p194" or "194p" → {page}. */
export function parseRef(s) {
  let m = /^\s*(\d+)\s*(?:[:.,]\s*(\d+))?\s*$/.exec(s);
  if (m) return { chapter: +m[1], verse: m[2] ? +m[2] : null };
  m = /^\s*p\.?\s*(\d+)\s*$/i.exec(s) || /^\s*(\d+)\s*p\s*$/i.exec(s);
  return m ? { page: +m[1] } : null;
}

/** The words an issue message quotes (“…”), to look for in the page: each quotation split at its
 *  ellipses into pieces of 6+ characters; a footnote call for the footnote kinds. */
export function snippets(msg, kind) {
  const out = [];
  if (kind === "missing_footnote") {
    const m = /marker \(([a-z])\)/.exec(msg);
    if (m) out.push(`^{(${m[1]})}`);
  }
  let first = true;
  for (const m of msg.matchAll(/“([^”]*)”/g)) {
    if (kind === "broken_marker" && first) { out.push(m[1].trim()); first = false; continue; }  // the call itself
    first = false;
    for (const piece of m[1].split("…")) {
      const p = piece.trim();
      if (p.length >= 6) out.push(p);
    }
  }
  return out;
}

const escape = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const loose = (s) => new RegExp(s.trim().split(/\s+/).map(escape).join("\\s+"), "g");

/** Where the needles are in `text`: every exact or whitespace-insensitive occurrence; for a needle
 *  found nowhere, its longest run of whole words (12+ characters) that is. Sorted, overlaps merged. */
export function findSpans(text, needles) {
  const spans = [];
  const all = (rx) => [...text.matchAll(rx)].map((m) => [m.index, m.index + m[0].length]);
  for (const n of needles) {
    if (!n.trim()) continue;
    let found = all(loose(n));
    if (!found.length) {
      const words = n.trim().split(/\s+/);
      search: for (let len = words.length - 1; len >= 2; len--) {
        for (let i = 0; i + len <= words.length; i++) {
          const part = words.slice(i, i + len).join(" ");
          if (part.length < 12) continue;
          found = all(loose(part));
          if (found.length) break search;
        }
      }
    }
    spans.push(...found);
  }
  spans.sort((a, b) => a[0] - b[0]);
  const merged = [];
  for (const s of spans) {
    const last = merged[merged.length - 1];
    if (last && s[0] <= last[1]) last[1] = Math.max(last[1], s[1]);
    else merged.push([...s]);
  }
  return merged;
}
