// The /merge merged column's pure helpers (no DOM): normalized's raw text as nodes and back, the segments a
// typing session changed, the undo stack, and when Ctrl/Cmd+Z is the screen's undo rather than the text's.

const RAW = /\^\{[^}]*\}|_[^_\s][^_]*_/g;  // a note's marker ^{(a)}, an _italic_ run

/** "Son Verbe ^{(a)} et _sa_ sagesse" -> [{kind: "text"|"marker"|"italic", t}] (an italic's t without its _). */
export function toNodes(raw) {
  const out = [];
  let at = 0;
  for (const m of (raw || "").matchAll(RAW)) {
    if (m.index > at) out.push({ kind: "text", t: raw.slice(at, m.index) });
    out.push(m[0].startsWith("^") ? { kind: "marker", t: m[0] } : { kind: "italic", t: m[0].slice(1, -1) });
    at = m.index + m[0].length;
  }
  if (at < (raw || "").length) out.push({ kind: "text", t: raw.slice(at) });
  return out;
}

export function toRaw(nodes) {
  return nodes.map((n) => (n.kind === "italic" ? `_${n.t}_` : n.t)).join("");
}

/** The segments whose text changed: before [{t, page, path, a, b, key}], after [text] (same order). */
export function segmentEdits(before, after) {
  const out = [];
  before.forEach((s, i) => {
    if (after[i] !== s.t) out.push({ page: s.page, path: s.path, a: s.a, b: s.b, text: after[i], key: s.key, before: s.t });
  });
  return out;
}

/** The screen's actions, last first. An action: {kind: "decide", vol, uid, key, before: {choice, text}, after}
 * or {kind: "edit", vol, uid, page, path, a, b, before: text, after: text}. */
export class Undo {
  constructor() { this.stack = []; }
  push(action) { this.stack.push(action); }
  pop() { return this.stack.pop() || null; }
}

/** The call that puts back what an action changed. */
export function inverse(x) {
  if (x.kind === "decide") return { kind: "decide", vol: x.vol, uid: x.uid, key: x.key, choice: x.before.choice ?? null, text: x.before.text ?? null };
  return { kind: "edit", vol: x.vol, uid: x.uid, page: x.page, path: x.path, a: x.a, b: x.b, text: x.before };
}

/** Ctrl/Cmd+Z undoes the last decision unless the caret is in something typed in (that keeps its own undo). */
export function undoKey(e) {
  const t = e.target || {};
  if (e.key !== "z" && e.key !== "Z") return false;
  if (!(e.ctrlKey || e.metaKey) || e.shiftKey || e.altKey) return false;
  return !(t.isContentEditable || /^(INPUT|SELECT|TEXTAREA)$/.test(t.tagName || ""));
}
