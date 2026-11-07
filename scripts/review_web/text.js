// Pure text helpers for the editor; italicRuns and toggleItalics are page_text.py's, ported
// (tests/js/text.test.mjs runs the same cases as tests/test_page_text.py).

const CLOSING_FOLLOWERS = new Set(",.;:!?)»]");
const TRAILING_PUNCT = /^_?[ \t]*([;?!]|:(?!\d))+/;
const JOIN_BEFORE = /_([ \t]*[,;:]?[ \t]*)$/;  // a run closing just before (spaces, a comma between)
const JOIN_AFTER = /^([ \t]*[,;:]?[ \t]*)_/;   // one opening just after
const ROMAN_TRAILING = /^[ \t]*(?:([;?!]|:(?!\d))+|[.,]+(?=_))/;
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
  const m = (make ? TRAILING_PUNCT : ROMAN_TRAILING).exec(s.slice(sb));
  if (m && (make || italic.has(sb + m[0].length - 1))) sb += m[0].length;
  const absorbs = (c) => c === "_" || (!make && isSpace(c) && c !== "\n");
  while (sa > 0 && absorbs(s[sa - 1])) sa--;
  while (sb < s.length && absorbs(s[sb])) sb++;
  const italicAt = (p) => ((s.slice(0, p).split("_").length - 1) % 2 === 1) !== (openAt === "start");
  const opening = italicAt(sa) !== make && (make || sa > 0) ? "_" : "";
  const closing = italicAt(sb) !== make && (make || sb < s.length) ? "_" : "";
  const mid = s.slice(sa, sb).replaceAll("_", "");
  let head = s.slice(0, sa), tail = s.slice(sb), open = opening, close = closing;
  if (make) {  // italics next to italics join: "_au_ Dieu" -> "_au Dieu_"
    let m = JOIN_BEFORE.exec(head);
    if (open && m) { head = head.slice(0, m.index) + m[1]; open = ""; }
    m = JOIN_AFTER.exec(tail);
    if (close && m) { tail = m[1] + tail.slice(m[0].length); close = ""; }
  }
  const start = head.length + open.length;
  return { text: head + open + mid + close + tail, start, end: start + mid.length };
}

/** Convert s[sa:sb] to uppercase; returns { text, start, end } or null if empty / unchanged. */
export function toUpper(s, sa, sb) {
  if (sa == null || sb == null || sa >= sb) return null;
  sa = Math.max(0, sa);
  sb = Math.min(sb, s.length);
  if (sa >= sb) return null;
  const target = s.slice(sa, sb);
  const u = target.toUpperCase();
  if (u === target) return null;
  return { text: s.slice(0, sa) + u + s.slice(sb), start: sa, end: sa + u.length };
}

/** Cut s[sa:sb] and prepend it (with a space) to `nextText` (or replace if null/empty).
 *  Returns { cutStart, cutEnd, nextEnd, nextInsert } or null when the selection is empty. */
export function cutToNext(s, sa, sb, nextText, nextIsNull = false) {
  if (sa == null || sb == null || sa >= sb) return null;
  sa = Math.max(0, sa);
  sb = Math.min(sb, s.length);
  const piece = s.slice(sa, sb).trim();
  if (!piece) return null;
  let cutStart = sa, cutEnd = sb;
  const hSpace = (c) => c === " " || c === "\t";
  if (s.slice(cutEnd).trim() === "") {
    cutEnd = s.length;
    while (cutStart > 0 && hSpace(s[cutStart - 1])) cutStart--;
  } else if (s.slice(0, cutStart).trim() === "") {
    cutStart = 0;
    while (cutEnd < s.length && hSpace(s[cutEnd])) cutEnd++;
  } else if (cutStart > 0 && cutEnd < s.length && hSpace(s[cutStart - 1]) && hSpace(s[cutEnd])) {
    while (cutEnd < s.length && hSpace(s[cutEnd])) cutEnd++;
  }
  const emptyNext = nextIsNull || !nextText || !nextText.trim();
  const nextEnd = !nextIsNull && nextText && !nextText.trim() ? nextText.length : 0;
  const nextInsert = emptyNext ? piece : piece + (/^\s/.test(nextText) ? "" : " ");
  return { cutStart, cutEnd, nextEnd, nextInsert };
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
// kinds whose second quotation is the start of a text the translation may have run into: marked up
// to its first full stop, the likely end of the translation
const TO_STOP = new Set(["no_translation", "long_translation"]);

export function snippets(msg, kind) {
  const out = [];
  if (kind === "missing_footnote") {
    const m = /marker \(([a-z])\)/.exec(msg);
    if (m) out.push(`^{(${m[1]})}`);
  }
  let first = true;
  for (const m of msg.matchAll(/“([^”]*)”/g)) {
    if (kind === "broken_marker" && first) { out.push(m[1].trim()); first = false; continue; }  // the call itself
    const toStop = TO_STOP.has(kind) && !first;
    first = false;
    for (const piece of m[1].split("…")) {
      let p = piece.trim();
      const stop = toStop ? p.indexOf(".") : -1;
      if (stop >= 0) p = p.slice(0, stop + 1);
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

/** Word-by-word difference of a and b: [[op, text]], op "=" kept, "-" only in a, "+" only in b
 *  (the "=" and "-" parts give a back, the "=" and "+" parts b). Spaces count as words. */
export function wordDiff(a, b) {
  const x = (a || "").match(/\s+|\S+/g) || [], y = (b || "").match(/\s+|\S+/g) || [];
  // L[i][j]: longest common run of x[i..] and y[j..]
  const L = Array.from({ length: x.length + 1 }, () => new Array(y.length + 1).fill(0));
  for (let i = x.length - 1; i >= 0; i--)
    for (let j = y.length - 1; j >= 0; j--)
      L[i][j] = x[i] === y[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  const out = [];
  const push = (op, t) => {
    const last = out[out.length - 1];
    if (last && last[0] === op) last[1] += t; else out.push([op, t]);
  };
  let i = 0, j = 0;
  while (i < x.length || j < y.length) {
    if (i < x.length && j < y.length && x[i] === y[j]) { push("=", x[i]); i++; j++; }
    else if (j >= y.length || (i < x.length && L[i + 1][j] >= L[i][j + 1])) push("-", x[i++]);
    else push("+", y[j++]);
  }
  return out;
}

/** Spans [a, b] after text[a0:b0] was replaced by `n` characters: moved, stretched or shrunk with their
 *  words; a span the edit takes in whole (its word rewritten) is dropped. */
export function shiftSpans(spans, a0, b0, n) {
  const d = n - (b0 - a0), out = [];
  for (const [s, e] of spans || []) {
    if (b0 <= s) out.push([s + d, e + d]);
    else if (a0 >= e) out.push([s, e]);
    else if (a0 <= s && b0 >= e) continue;
    else {
      const ns = a0 < s ? a0 + n : s, ne = b0 > e ? a0 + n : e + d;
      if (ne > ns) out.push([ns, ne]);
    }
  }
  return out;
}

/** Spans of `old` carried over to `neu` when only the change is known: italics marks put or taken away
 *  (the letters the same), a change of case, else the one stretch that differs (shiftSpans). */
export function mapSpans(spans, old, neu) {
  if (!spans || !spans.length || old === neu) return spans;
  if (old.length === neu.length && old.toLowerCase() === neu.toLowerCase()) return spans.map((x) => [...x]);
  if (old.replace(/_/g, "") === neu.replace(/_/g, "")) {
    const rank = [0];  // letters (not marks) before each offset of old
    for (let i = 0; i < old.length; i++) rank.push(rank[i] + (old[i] === "_" ? 0 : 1));
    const at = [];  // offset in neu of each letter
    for (let i = 0; i < neu.length; i++) if (neu[i] !== "_") at.push(i);
    const start = (k) => (k < at.length ? at[k] : neu.length), end = (k) => (k > 0 ? at[k - 1] + 1 : 0);
    return spans.map(([a, b]) => [start(rank[a]), end(rank[b])]).filter(([a, b]) => b > a);
  }
  let p = 0, q = 0;
  while (p < old.length && p < neu.length && old[p] === neu[p]) p++;
  while (q < old.length - p && q < neu.length - p && old[old.length - 1 - q] === neu[neu.length - 1 - q]) q++;
  return shiftSpans(spans, p, old.length - q, neu.length - q - p);
}
