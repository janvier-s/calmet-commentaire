// Adding, deleting and moving verses, commentary blocks and footnotes; the page tools menu.
import { S, api, ask, hooks, toast } from "./app.js";
import { op } from "./edit.js";

const $ = (id) => document.getElementById(id);
const el = (tag, props = {}, ...kids) => {
  const e = Object.assign(document.createElement(tag), props);
  e.append(...kids.filter((k) => k != null));
  return e;
};
const btn = (text, title, onclick) => el("button", { className: "link", textContent: text, title, onclick });

function describe(section, i) {
  const x = S.data[section][i];
  if (section === "verses") return `verse ${x.verse_number}: ${(x.latin || x.french || "").slice(0, 60)}`;
  if (section === "footnotes") return `footnote ${x.marker}: ${(x.text || "").slice(0, 60)}`;
  return `commentary ${x.commentary_id} (v.${x.verse_ref}): ${(x.latin_quote || x.french_commentary || "").slice(0, 60)}`;
}

async function remove(section, i) {
  if (await ask(`Delete ${describe(section, i)}?`, [["no", "Cancel"], ["yes", "Delete", "warn"]]) === "yes") {
    op({ op: "delete", section, index: i });
  }
}

function move(section, i, j) {
  const n = (S.data[section] || []).length;
  if (j < 0 || j >= n || i === j) return;
  op({ op: "move", section, from: i, to: j, renumber: $("renumber").checked });
}

hooks.blockTools = (section, i) => {
  const n = (S.data[section] || []).length;
  const tools = [el("span", { className: "grow" })];
  if (section !== "footnotes" && n > 1) {
    const handle = el("span", { className: "handle", textContent: "⠿", title: "Drag to move", draggable: true });
    handle.addEventListener("dragstart", (e) => {
      e.dataTransfer.setData("text/x-entry", JSON.stringify({ section, i }));
      e.dataTransfer.effectAllowed = "move";
    });
    tools.push(handle, btn("⤒", "Move to the top", () => move(section, i, 0)),
               btn("↑", "Move up", () => move(section, i, i - 1)),
               btn("↓", "Move down", () => move(section, i, i + 1)),
               btn("⤓", "Move to the bottom", () => move(section, i, n - 1)));
  }
  tools.push(btn("✕ delete", "Delete this entry", () => remove(section, i)));
  return tools;
};

// drop a dragged block on another of the same section: it takes that place
document.addEventListener("dragover", (e) => {
  if (e.dataTransfer.types.includes("text/x-entry") && e.target.closest(".block[data-section]")) e.preventDefault();
});
document.addEventListener("drop", (e) => {
  const target = e.target.closest(".block[data-section]");
  const raw = e.dataTransfer.getData("text/x-entry");
  if (!target || !raw) return;
  e.preventDefault();
  const { section, i } = JSON.parse(raw);
  if (target.dataset.section === section) move(section, i, +target.dataset.index);
});

hooks.addTop = () => {
  const last = S.ctx && S.ctx.prev;
  const where = last && (last.verse_ref != null || last.commentary_chapter != null)
    ? ` (continues ${[last.commentary_chapter, last.verse_ref].filter((x) => x != null).join(":")} from p.${last.page})` : "";
  return el("button", { className: "add", textContent: `+ add block at top${where}`,
                        onclick: () => op({ op: "add_commentary", after: null }) });
};

hooks.addBelow = (i) => el("button", { className: "add", textContent: "+ add below",
                                       onclick: () => op({ op: "add_commentary", after: i }) });

async function askValue(msg, check) {
  const input = el("input", { autocomplete: "off" });
  const body = el("div", {}, input);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); $("dialog").close("ok"); } });
  if (await ask(msg, [["cancel", "Cancel"], ["ok", "Add", "ok"]], body) !== "ok") return null;
  const v = input.value.trim();
  if (!check(v)) { toast("Not added: that value doesn't fit"); return null; }
  return v;
}

hooks.addEnd = (section) => el("div", { className: "adds" }, section === "verses"
  ? el("button", { textContent: "+ Verse", onclick: async () => {
      const n = await askValue("Number of the new verse:", (v) => /^\d+$/.test(v));
      if (n) op({ op: "add_verse", n: +n });
    } })
  : el("button", { textContent: "+ Footnote", onclick: async () => {
      const m = await askValue("Marker letter (e.g. a):", (v) => /^\(?[\p{L}\d*]+\)?$/u.test(v));
      if (m) op({ op: "add_footnote", marker: m });
    } }));

// page tools
for (const b of document.querySelectorAll("#menu [data-tool]")) {
  b.onclick = async () => {
    $("menu").hidden = true;
    const tool = b.dataset.tool;
    const r = tool === "flag" ? await api("/api/flag", { vol: S.vol, page: S.page })
      : await api("/api/open", { vol: S.vol, page: S.page, what: tool });
    if (r.status !== 200) toast(r.body.error || "Failed");
    else if (tool === "flag") toast(`Copied ${r.body.copied.join(", ")} to modernization_error/`);
  };
}
