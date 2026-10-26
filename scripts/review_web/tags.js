// Footnote tags (footnote_tags.py): hidden until "Tags" is on; then every tag shows under each
// footnote, the ones it has filled in, and a click adds or takes one away (saved with the page);
// then the original titles of the works it names.
import { S, hooks, renderPage } from "./app.js";
import { setDirty } from "./edit.js";

const $ = (id) => document.getElementById(id);
const el = (tag, props = {}, ...kids) => {
  const e = Object.assign(document.createElement(tag), props);
  e.append(...kids.filter((k) => k != null));
  return e;
};

const TAGS = ["hebrew", "greek", "verse", "fathers", "rabbis", "versions", "classical", "commentators",
              "title", "latin", "explanation", "abbrev", "old-ref", "bad-ref", "ibid", "uncertain"];

let on = false;
try { on = localStorage.getItem("rw-tags") === "1"; } catch (e) {}

const btn = el("button", { id: "tags-btn", textContent: "Tags", className: on ? "on" : "",
                           title: "Show the footnotes' tags, to add the ones not found (search tag:fathers, tag:none)" });
$("sections").insertBefore(btn, $("sections").querySelector(".grow"));
btn.onclick = () => {
  on = !on;
  btn.classList.toggle("on", on);
  try { localStorage.setItem("rw-tags", on ? "1" : "0"); } catch (e) {}
  if (hooks.collect) hooks.collect();
  const top = $("text-pane").scrollTop;
  renderPage();
  $("text-pane").scrollTop = top;
};

function draw(row, i) {
  const fn = S.data.footnotes[i];
  const have = new Set(fn.tags || []);
  row.replaceChildren(
    "tags" in fn ? "" : el("span", { className: "muted", textContent: "not tagged yet ·" }),
    ...TAGS.map((t) => el("button", {
      className: "ftag" + (have.has(t) ? " on" : ""), textContent: t, title: have.has(t) ? `Remove ${t}` : `Add ${t}`,
      onmousedown: (e) => e.preventDefault(),  // the field being typed in keeps its cursor
      onclick: () => {
        const f = S.data.footnotes[i];  // S.data may have been replaced by a redraw since
        const now = new Set(f.tags || []);
        now.has(t) ? now.delete(t) : now.add(t);
        f.tags = TAGS.filter((x) => now.has(x));
        S.edits++;
        setDirty(true);
        draw(row, i);
      } })),
    ...(fn.titles || []).map((x) => el("span", { className: "ftitle", title: "Original title (footnote_names.txt)" },
                                       `${x.fr} = `, el("i", { textContent: x.original }))));
}

hooks.footnoteTags = (i) => {
  if (!on) return null;
  const row = el("div", { className: "fn-tags" });
  draw(row, i);
  return row;
};
