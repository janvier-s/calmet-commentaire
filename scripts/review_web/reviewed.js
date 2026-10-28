// Reviewed pages: the text read through (typos, italics), apart from the issues, for the commentary, the verses
// and the footnotes each. Kept per book in data/<book>/review.json. "Reviewed ›" (⌘⇧⏎) marks this page and goes to the next.
// The buttons after the chips (next, up to here, count) work on the section shown (All: the commentary).
import { S, api, ask, go, hooks, toast } from "./app.js";
import { save } from "./edit.js";
import { icon } from "./icons.js";

const $ = (id) => document.getElementById(id);
const el = (tag, props = {}, ...kids) => {
  const e = Object.assign(document.createElement(tag), props);
  e.append(...kids.filter((k) => k != null));
  return e;
};
const SECTIONS = [["commentary", "Commentary"], ["verses", "Verses"], ["footnotes", "Footnotes"]];
const focus = () => (S.section === "all" || !S.section ? "commentary" : S.section);
const done = (sec) => S.reviewed[sec] || new Set();

async function send(sec, body) {
  const r = await api("/api/reviewed", { vol: S.vol, section: sec, ...body });
  if (r.status !== 200) { toast(r.body.error || "Could not save", "error"); return false; }
  S.reviewed = Object.fromEntries(Object.entries(r.body.reviewed).map(([k, v]) => [k, new Set(v)]));
  return true;
}

async function toggle(sec) {
  if (await send(sec, { pages: [S.page], reviewed: !done(sec).has(S.page) })) draw();
}

/** Mark this page (in the section shown) and go to the next one. */
async function markAndNext() {
  const sec = focus();
  if (S.dirty && !(await save())) return;  // your edits to this page first
  if (!done(sec).has(S.page) && !(await send(sec, { pages: [S.page] }))) return;
  const i = S.pages.indexOf(S.page);
  if (i >= 0 && i < S.pages.length - 1) await go(S.vol, S.pages[i + 1]);
  else draw();
}

/** Mark every page up to this one (no button for now). */
async function upToHere() {
  const sec = focus();
  const n = S.pages.filter((p) => p <= S.page && !done(sec).has(p)).length;
  if (!n) { toast(`The ${sec} up to here is already marked`); return; }
  if (await ask(`Mark the ${sec} of ${n} page${n > 1 ? "s" : ""} up to p.${S.page} as reviewed?`, [["no", "Cancel"], ["yes", "Mark them", "ok"]]) !== "yes") return;
  if (await send(sec, { upto: S.page })) { draw(); toast(`${sec} reviewed up to p.${S.page}`); }
}

let hidden = false;
try { hidden = localStorage.getItem("rw-reviewed-hidden") === "1"; } catch (e) {}
function setHidden(v) {
  hidden = v;
  try { localStorage.setItem("rw-reviewed-hidden", v ? "1" : "0"); } catch (e) {}
  draw();
}

function draw() {
  if (!S.reviewed.commentary) return;
  $("reviewed").hidden = false;
  $("reviewed").classList.toggle("min", hidden);
  document.body.classList.toggle("rev-on", !hidden);
  if (hidden) {  // only a way back
    $("reviewed").replaceChildren(el("button", { className: "link", title: "Show the reviewed bar", textContent: "Reviewed ▴", onclick: () => setHidden(false) }));
    return;
  }
  const sec = focus(), have = done(sec);
  const nextUn = S.pages.find((p) => p > S.page && !have.has(p));
  const firstUn = S.pages.find((p) => !have.has(p));
  $("reviewed").replaceChildren(
    ...SECTIONS.map(([k, label]) => el("button", {
      className: (done(k).has(S.page) ? "on" : "") + (k === sec ? " cur" : ""),
      title: `${label} of this page read through (independent of the issues)`, onclick: () => toggle(k),
    }, icon(done(k).has(S.page) ? "check" : "pause", 12), label)),
    el("button", { className: "ok", title: `Mark this page's ${sec} reviewed and go to the next page (⌘⇧⏎)`, onclick: markAndNext },
       have.has(S.page) ? "Next page" : "Reviewed", icon("next", 12)),
    el("span", { className: "muted small", textContent: ` ${have.size}/${S.pages.length} ${sec} ` }),
    firstUn != null ? el("button", { title: `Back to the first page whose ${sec} is not reviewed: where you left off`, onclick: () => go(S.vol, firstUn) },
                         icon("fwd", 12), `Resume p.${firstUn}`) : null,
    nextUn != null && nextUn !== firstUn ? el("button", { className: "link", title: `The next page after this one whose ${sec} is not reviewed`, onclick: () => go(S.vol, nextUn) }, `next p.${nextUn}`, icon("next", 12)) : null,
    el("button", { className: "link", title: "Hide this bar", textContent: "Hide ▾", onclick: () => setHidden(true) }),
  );
}

hooks.afterRender.push(draw);
$("sections").addEventListener("click", () => setTimeout(draw));
document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key === "Enter") { e.preventDefault(); markAndNext(); }
});
