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
  // where to look: the issue's entry; without one, its section (a verse quoted in a note must not
  // light up the verse), and the whole page only if nothing is found there
  const section = (S.config.kind_category || {})[item.kind] || "commentary";
  const tiers = w ? [S.fields.filter((x) => x.path.join("/").startsWith(prefix))]
                  : [S.fields.filter((x) => x.path[0] === section), S.fields];
  let first = null;
  for (const fields of tiers) {
    for (const x of fields) {
      const spans = needles.length ? findSpans(x.field.text, needles) : [];
      const named = w && x.path.join("/") === `${prefix}${w.field}`;
      if (spans.length || named) x.field.setMarks(spans, named && !spans.length);
      if (spans.length && !first) first = x.field.el;
    }
    if (first) break;
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

// "Highlights": the marked words, the outlined field and the flash, shown or not (kept per browser)
let shown = true;
try { shown = localStorage.getItem("rw-highlights") !== "0"; } catch (e) {}
const hiBtn = Object.assign(document.createElement("button"), {
  id: "hi-btn", textContent: "Highlights", title: "Show or hide the issue's marked words and outlined field" });
const showHighlights = (on) => {
  shown = on;
  hiBtn.classList.toggle("on", on);
  document.body.classList.toggle("no-hi", !on);
  try { localStorage.setItem("rw-highlights", on ? "1" : "0"); } catch (e) {}
};
$("sections").insertBefore(hiBtn, $("sections").querySelector(".grow"));
hiBtn.onclick = () => showHighlights(!shown);
showHighlights(shown);
