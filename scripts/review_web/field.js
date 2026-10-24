// A page field: the text as stored (with _italic_ marks) shown with its italics, small caps and
// Hebrew direction. The DOM is only a view; the string is the model.
import { italicRuns } from "./text.js";

export const ITALIC_FIELDS = new Set(["chapter_summary", "latin", "french_translation"]);
const HEBREW = /[֐-׿יִ-ﭏ]+(?:[  ]+[֐-׿יִ-ﭏ]+)*/g;

/** Per character: is it italic, is it a mark, is it the unpaired mark, is it small caps. */
function styles(s, smallcaps) {
  const { runs, marks, openAt } = italicRuns(s);
  const st = Array.from(s, () => ({ it: false, mk: false, open: false, sc: false, he: false }));
  for (const [a, b] of runs) for (let i = a; i < b; i++) st[i].it = true;
  for (const i of marks) st[i].mk = true;
  if (openAt) st[openAt === "start" ? marks[0] : marks[marks.length - 1]].open = true;
  if (smallcaps) for (const i of smallcaps) if (st[i]) st[i].sc = true;
  for (const m of s.matchAll(HEBREW)) for (let i = m.index; i < m.index + m[0].length; i++) st[i].he = true;
  return st;
}

/** Fill `el` with `s` as styled spans. `smallcaps`: indexes set in small caps. */
export function render(el, s, smallcaps = null) {
  el.textContent = "";
  if (!s) return;
  const st = styles(s, smallcaps);
  let i = 0;
  while (i < s.length) {
    const k = st[i];
    let j = i + 1;
    while (j < s.length && st[j].it === k.it && st[j].mk === k.mk && st[j].open === k.open
           && st[j].sc === k.sc && st[j].he === k.he) j++;
    const piece = s.slice(i, j);
    if (!k.it && !k.mk && !k.sc && !k.he) el.append(piece);
    else {
      const span = document.createElement("span");
      span.className = [k.it && "it", k.mk && "mk", k.open && "open", k.sc && "sc"].filter(Boolean).join(" ");
      if (k.he) span.dir = "rtl";
      span.textContent = piece;
      el.append(span);
    }
    i = j;
  }
}
