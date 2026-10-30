// A page field: the text as stored (with _italic_ marks) shown with its italics, small caps and
// Hebrew direction. The DOM is only a view; the string is the model: every edit (typing, deleting,
// pasting, Cmd+I, undo) is applied to the string and the field drawn again, the caret kept.
//
// Checks (Task 8 acceptance, by hand in the browser):
//  - typing, Return (a line break), Backspace / Delete, word deletes (⌥⌫), selection replace
//  - accents typed with dead keys (⌥e e → é) and the accent menu (hold e)
//  - ⌘Z / ⇧⌘Z undo and redo within a field; typing coalesces into one step; ⌘I is one step
//  - ⌘I on a selection italicizes, again makes it roman; the I button acts on the last field
//  - paste of formatted text (from Safari, Word) arrives as plain text
//  - Tab / Shift-Tab: next / previous field, its text selected
//  - a null field shows grey "null"; typing replaces it; emptied again it saves as null
//  - "Show _ marks" hides and shows the marks; an unpaired mark shows red
//  - latin_quote in small caps but for the first letter and the Vulgate's proper nouns
//  - Hebrew stays right-to-left; no U+200E reaches the file
//  - empty french_commentary has room for four lines
import { italicRuns, toggleItalics, toUpper } from "./text.js";

export const ITALIC_FIELDS = new Set(["chapter_summary", "latin", "french_translation"]);
const HEBREW = /[֐-׿יִ-ﭏ]+(?:[  ]+[֐-׿יִ-ﭏ]+)*/g;

/** Per character: is it italic, is it a mark, is it the unpaired mark, is it small caps. */
function styles(s, smallcaps, highlight) {
  const { runs, marks, openAt } = italicRuns(s);
  const st = Array.from(s, () => ({ it: false, mk: false, open: false, sc: false, he: false, hl: false }));
  if (highlight) for (const [a, b] of highlight) for (let i = a; i < b && i < s.length; i++) st[i].hl = true;
  for (const [a, b] of runs) for (let i = a; i < b; i++) st[i].it = true;
  for (const i of marks) st[i].mk = true;
  if (openAt) st[openAt === "start" ? marks[0] : marks[marks.length - 1]].open = true;
  if (smallcaps) for (const i of smallcaps) if (st[i]) st[i].sc = true;
  for (const m of s.matchAll(HEBREW)) for (let i = m.index; i < m.index + m[0].length; i++) st[i].he = true;
  return st;
}

/** Fill `el` with `s` as styled spans. `smallcaps`: indexes set in small caps; `highlight`: [a, b]
 *  spans drawn as <mark> (the words an issue points at). */
export function render(el, s, smallcaps = null, highlight = null) {
  el.textContent = "";
  if (!s) return;
  const st = styles(s, smallcaps, highlight);
  let i = 0;
  while (i < s.length) {
    const k = st[i];
    let j = i + 1;
    while (j < s.length && st[j].it === k.it && st[j].mk === k.mk && st[j].open === k.open
           && st[j].sc === k.sc && st[j].he === k.he && st[j].hl === k.hl) j++;
    const piece = s.slice(i, j);
    if (!k.it && !k.mk && !k.sc && !k.he && !k.hl) el.append(piece);
    else {
      const span = document.createElement(k.hl ? "mark" : "span");
      span.className = [k.it && "it", k.mk && "mk", k.open && "open", k.sc && "sc"].filter(Boolean).join(" ");
      if (k.he) span.dir = "rtl";
      span.textContent = piece;
      el.append(span);
    }
    i = j;
  }
  if (s.endsWith("\n")) el.append(document.createElement("br"));  // show a final empty line
}

// --- offsets in the drawn field ---
function textNodes(el) {
  const out = [], w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  while (w.nextNode()) out.push(w.currentNode);
  return out;
}

function offsetOf(el, node, off) {
  if (node.nodeType !== Node.TEXT_NODE) {  // an element and a child index
    const r = document.createRange();
    r.selectNodeContents(el);
    r.setEnd(node, off);
    return r.toString().length;
  }
  let n = 0;
  for (const t of textNodes(el)) {
    if (t === node) return n + off;
    n += t.length;
  }
  return n;
}

function pointAt(el, k) {
  for (const t of textNodes(el)) {
    if (k <= t.length) return [t, k];
    k -= t.length;
  }
  return [el, el.childNodes.length];
}

const WORD_CHAR = /[\p{L}\p{N}_'’-]/u;

export class Field {
  /** `el` is drawn and edited in place; `onChange(field)` after each edit. */
  constructor(el, { name, value, onChange, latinCase }) {
    this.el = el;
    this.name = name;
    this.wasNull = value === null || value === undefined;
    this.text = this.wasNull ? "null" : String(value);
    this.onChange = onChange;
    this.latinCase = name === "latin_quote" ? latinCase : null;
    this.undo = [];
    this.redo = [];
    this.lastEdit = 0;
    el.contentEditable = "true";
    el.spellcheck = false;
    el.addEventListener("beforeinput", (e) => this.beforeInput(e));
    el.addEventListener("keydown", (e) => {
      if (!(e.metaKey || e.ctrlKey)) return;
      const k = e.key.toLowerCase();
      if (k === "z") { e.preventDefault(); e.shiftKey ? this.history(this.redo, this.undo) : this.history(this.undo, this.redo); }
      else if (k === "y") { e.preventDefault(); this.history(this.redo, this.undo); }
      else if (k === "i") { e.preventDefault(); this.toggleItalic(); }
    });
    el.addEventListener("compositionstart", () => { this.composing = true; });
    el.addEventListener("compositionend", () => { this.composing = false; this.resync(); });
    el.addEventListener("input", (e) => { if (!e.isComposing && this.domText() !== this.text) this.resync(); });
    el.addEventListener("focus", () => { if (this.isNull()) this.select(0, this.text.length); });
    this.draw();
  }

  isNull() { return this.text === "null" && this.wasNull; }

  /** The value to save: null for "null", or for a null field left empty. */
  get value() {
    if (this.text.trim() === "null" || (this.wasNull && this.text.trim() === "")) return null;
    return this.text;
  }

  domText() { return textNodes(this.el).map((t) => t.data).join(""); }

  draw(sel) {
    this.el.classList.toggle("null", this.isNull());
    let sc = null;
    if (this.latinCase && this.text && !this.isNull()) {
      sc = this.latinCase(this.text, () => { if (!this.composing) this.draw(this.selection()); });
    }
    render(this.el, this.text, sc, this.marks);
    if (sel) this.select(...sel);
  }

  /** Mark the words an issue points at (until the next edit); `flag` outlines the field. */
  setMarks(spans, flag = false) {
    this.marks = spans && spans.length ? spans : null;
    this.el.classList.toggle("flagged", flag);
    this.draw(document.activeElement === this.el ? this.selection() : null);
  }

  selection() {
    const s = getSelection();
    if (!s.rangeCount || !this.el.contains(s.anchorNode)) return null;
    const a = offsetOf(this.el, s.anchorNode, s.anchorOffset), b = offsetOf(this.el, s.focusNode, s.focusOffset);
    return [Math.min(a, b), Math.max(a, b)];
  }

  select(a, b = a) {
    const s = getSelection();
    const r = document.createRange();
    r.setStart(...pointAt(this.el, a));
    r.setEnd(...pointAt(this.el, b));
    s.removeAllRanges();
    s.addRange(r);
  }

  /** Replace text[a:b] with `ins`; `kind` groups typing into one undo step. */
  edit(a, b, ins, kind = "other") {
    const now = Date.now();
    if (!(kind === "type" && this.lastKind === "type" && now - this.lastEdit < 1000)) {
      this.undo.push({ text: this.text, sel: this.selection() || [a, b] });
      if (this.undo.length > 200) this.undo.shift();
    }
    this.redo = [];
    this.lastEdit = now;
    this.lastKind = kind;
    if (this.isNull()) { a = 0; b = this.text.length; }
    this.unmark();
    this.text = this.text.slice(0, a) + ins + this.text.slice(b);
    this.draw([a + ins.length, a + ins.length]);
    this.onChange(this);
  }

  /** The issue's marks go with the first change to the text (their offsets no longer hold). */
  unmark() {
    this.marks = null;
    this.el.classList.remove("flagged");
  }

  /** Text changed outside our hands (composition, the accent menu): take the DOM's. */
  resync() {
    const sel = this.selection();
    const t = this.domText();
    if (t === this.text) return;
    this.unmark();
    this.undo.push({ text: this.text, sel: sel || [0, 0] });
    this.redo = [];
    this.lastKind = "other";
    this.text = t;
    this.draw(sel);
    this.onChange(this);
  }

  history(from, to) {
    const h = from.pop();
    if (!h) return;
    to.push({ text: this.text, sel: this.selection() || [0, 0] });
    this.unmark();
    this.text = h.text;
    this.lastKind = "other";
    this.draw(h.sel);
    this.onChange(this);
  }

  toggleItalic() {
    const sel = this.selection();
    if (!sel || sel[0] === sel[1]) return;
    const r = toggleItalics(this.text, sel[0], sel[1]);
    if (!r) return;
    this.undo.push({ text: this.text, sel });
    this.redo = [];
    this.lastKind = "other";
    this.unmark();
    this.text = r.text;
    this.draw([r.start, r.end]);
    this.onChange(this);
  }

  toUpperCase(sel = this.selection()) {
    if (!sel || sel[0] === sel[1]) return;
    const r = toUpper(this.text, sel[0], sel[1]);
    if (!r) return;
    this.undo.push({ text: this.text, sel });
    this.redo = [];
    this.lastKind = "other";
    this.unmark();
    this.text = r.text;
    this.draw([r.start, r.end]);
    this.onChange(this);
  }

  range(e) {
    const r = e.getTargetRanges && e.getTargetRanges()[0];
    if (r) {
      const a = offsetOf(this.el, r.startContainer, r.startOffset), b = offsetOf(this.el, r.endContainer, r.endOffset);
      return [Math.min(a, b), Math.max(a, b)];
    }
    return this.selection() || [this.text.length, this.text.length];
  }

  beforeInput(e) {
    const t = e.inputType;
    if (e.isComposing || t.includes("Composition")) return;  // WebKit's too; resynced on compositionend
    const [a, b] = this.range(e);
    const plain = () => (e.dataTransfer && e.dataTransfer.getData("text/plain")) || e.data || "";
    e.preventDefault();
    if (t === "insertText") this.edit(a, b, e.data || "", "type");
    else if (t === "insertLineBreak" || t === "insertParagraph") this.edit(a, b, "\n");
    else if (t === "insertFromPaste" || t === "insertFromDrop" || t === "insertReplacementText" || t === "insertFromYank")
      this.edit(a, b, plain().replace(/\r\n?/g, "\n"));
    else if (t.startsWith("delete")) {
      if (a !== b) this.edit(a, b, "");
      else if (t.endsWith("Backward") && a > 0) this.edit(t === "deleteContentBackward" ? a - 1 : this.wordStart(a), a, "");
      else if (t.endsWith("Forward") && a < this.text.length) this.edit(a, t === "deleteContentForward" ? a + 1 : this.wordEnd(a), "");
    } else if (t === "historyUndo") this.history(this.undo, this.redo);
    else if (t === "historyRedo") this.history(this.redo, this.undo);
    else if (t === "formatItalic") this.toggleItalic();
  }

  wordStart(k) {
    while (k > 0 && !WORD_CHAR.test(this.text[k - 1])) k--;
    while (k > 0 && WORD_CHAR.test(this.text[k - 1])) k--;
    return k;
  }

  wordEnd(k) {
    while (k < this.text.length && !WORD_CHAR.test(this.text[k])) k++;
    while (k < this.text.length && WORD_CHAR.test(this.text[k])) k++;
    return k;
  }
}
