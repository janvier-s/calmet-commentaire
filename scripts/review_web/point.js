// Pointing at an issue: its quoted words marked in the fields of its entry (or the page), the field
// it names outlined, scrolled into view and its block flashed.
import { S } from "./app.js";
import { findSpans, snippets } from "./text.js";

const $ = (id) => document.getElementById(id);

export function clearPoint() {
  for (const { field } of S.fields || []) if (field.marks || field.el.classList.contains("flagged")) field.setMarks(null);
}

export function point(item) {
  clearPoint();
  if (!item || item.book_dir !== S.vol || item.page !== S.page || !S.fields) return;
  const w = item.where;
  if (w && S.section !== "all" && S.section !== w.section) {  // the entry is hidden by the section filter
    document.querySelector('#sections button[data-sec="all"]').click();
  }
  const needles = snippets(item.msg, item.kind);
  const prefix = w ? `${w.section}/${w.index}/` : "";
  let fields = S.fields.filter((x) => x.path.join("/").startsWith(prefix));
  if (!fields.length) fields = S.fields;
  let first = null;
  for (const x of fields) {
    const spans = needles.length ? findSpans(x.field.text, needles) : [];
    const named = w && x.path.join("/") === `${prefix}${w.field}`;
    if (spans.length || named) x.field.setMarks(spans, named && !spans.length);
    if (spans.length && !first) first = x.field.el;
  }
  const named = w && document.querySelector(`.f[data-path="${prefix}${w.field}"]`);
  const block = w && document.querySelector(`.block[data-section="${w.section}"][data-index="${w.index}"]`);
  const target = (first && first.querySelector("mark")) || first || named || block;
  if (!target) return;
  const pane = $("text-pane");
  const y = target.getBoundingClientRect().top - pane.getBoundingClientRect().top + pane.scrollTop;
  pane.scrollTop = Math.max(0, y - pane.clientHeight / 3);
  const b = target.closest(".block");
  if (b) {
    b.classList.remove("flash");
    void b.offsetWidth;  // restart the animation
    b.classList.add("flash");
  }
}
