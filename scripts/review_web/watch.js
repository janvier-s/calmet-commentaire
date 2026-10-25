// Pages edited outside the editor (by hand, by an LLM): the open page, or both pages of the page
// turn, are loaded again when their file changes, and the book re-checked. Unsaved edits are never
// replaced without asking.
import { S, api, ask, loadPage, toast } from "./app.js";
import { setDirty } from "./edit.js";
import { recheck } from "./queue.js";
import { T, reloadFromDisk } from "./turn.js";

const $ = (id) => document.getElementById(id);
const EVERY = 1500;  // ms
let busy = false;

/** The pages shown: [{page, version, dirty, side}]. */
function shown() {
  if (document.body.classList.contains("batch-open")) return { vol: null, pages: [] };
  if (T.open) {
    return { vol: T.vol, pages: [T.a, T.b].filter(Boolean).map((s) => ({ page: s.page, version: s.version, dirty: s.dirty, side: s })) };
  }
  return { vol: S.vol, pages: S.data ? [{ page: S.page, version: S.version, dirty: S.dirty }] : [] };
}
const sig = (w) => JSON.stringify([w.vol, w.pages.map((p) => [p.page, p.version])]);

async function readable(vol, page) {  // a file still being written is not valid JSON yet
  const r = await api(`/api/page?vol=${encodeURIComponent(vol)}&page=${page}`);
  return r.status === 200;
}

async function tick() {
  if (busy || document.hidden || S.posting || $("dialog").open) return;
  const w = shown();
  if (!w.vol || !w.pages.length) return;
  busy = true;
  try {
    const r = await api(`/api/versions?vol=${encodeURIComponent(w.vol)}&pages=${w.pages.map((p) => p.page).join(",")}`);
    // a save, a page change or a reload since the question was asked: its answer is old
    if (r.status !== 200 || S.posting || sig(shown()) !== sig(w)) return;
    const changed = w.pages.filter((p) => r.body.versions[p.page] && r.body.versions[p.page] !== p.version);
    if (!changed.length) return;
    for (const p of changed) if (!(await readable(w.vol, p.page))) return;  // try again next time
    const reload = [];
    for (const p of changed) {
      if (p.dirty) {
        const choice = await ask(`${w.vol} p.${p.page} was changed on disk while you have unsaved changes to it here.\n\n` +
                                 "Reload theirs: your unsaved changes to it are dropped.\nKeep mine: your next save writes over theirs.",
                                 [["mine", "Keep mine"], ["theirs", "Reload theirs", "warn"]]);
        if (sig(shown()) !== sig(w)) return;
        if (choice !== "theirs") {  // keep mine: the disk's version becomes the one to save over
          if (p.side) p.side.version = r.body.versions[p.page];
          else S.version = r.body.versions[p.page];
          continue;
        }
      }
      reload.push(p.page);
    }
    if (!reload.length) return;
    if (T.open) {
      await reloadFromDisk(reload);
    } else {
      const { opened } = S, top = $("text-pane").scrollTop;
      setDirty(false);
      if (!(await loadPage(w.vol, reload[0]))) return;
      if (opened && opened.vol === S.vol && opened.page === S.page) S.opened = opened;  // Undo all goes back past it too
      $("text-pane").scrollTop = top;
      await recheck(S.vol, S.page);
    }
    const said = document.querySelector(".toast");
    toast(`p.${reload.join(" and p.")} updated on disk` + (said ? ` · ${said.textContent}` : ""));
  } finally {
    busy = false;
  }
}

setInterval(tick, EVERY);
