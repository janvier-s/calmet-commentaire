// "Merged": the page as /merge built it (data/<vol>/merged), read-only, the words taken from Good
// underlined blue and wavy. The editor's own text is normalized; this only shows what the merge makes of it.
import { S, api, hooks, renderPage, showScan, toast } from "./app.js";
import { render } from "./field.js";

const $ = (id) => document.getElementById(id);

let on = false;
try { on = localStorage.getItem("rw-merged") === "1"; } catch (e) {}
const cache = new Map();  // "vol:page" -> {data, marks} | "loading"

const btn = document.createElement("button");
Object.assign(btn, { id: "merged-btn", textContent: "Merged", className: on ? "on" : "",
  title: "Show the page as /merge built it (read-only); the words taken from Good are underlined in blue; the scan switches to Good_Calmet" });
$("sections").insertBefore(btn, $("sections").querySelector(".grow"));
btn.onclick = () => {
  on = !on;
  btn.classList.toggle("on", on);
  try { localStorage.setItem("rw-merged", on ? "1" : "0"); } catch (e) {}
  if (hooks.collect) hooks.collect();
  const top = $("text-pane").scrollTop;
  scanTo(on);  // the scan of Good_Calmet beside its text
  cache.delete(`${S.vol}:${S.page}`);  // fresh: a decision may have been made since
  renderPage();
  $("text-pane").scrollTop = top;
};

let plain = true;  // the ordinary scan existed when Good_Calmet was put on by this toggle
function scanTo(good) {
  if (!S.good) return;
  if (good && !S.goodOn) { plain = !$("no-scan").hidden; S.goodOn = true; showScan(true); }
  else if (!good && S.goodOn) { S.goodOn = false; S.goodIdx = 0; showScan(plain); }
}

function at(data, path) {
  let x = data;
  for (const p of path.split("/")) { if (x == null) return undefined; x = x[p]; }
  return x;
}

hooks.afterRender.push((root) => {
  document.body.classList.toggle("merged-view", on);
  if (!on) return;
  scanTo(true);
  const k = `${S.vol}:${S.page}`;
  const hit = cache.get(k);
  if (!hit) {
    cache.set(k, "loading");
    api(`/api/merged?vol=${encodeURIComponent(S.vol)}&page=${S.page}`).then((r) => {
      cache.set(k, r.status === 200 ? r.body : { data: null, marks: {} });
      if (on && k === `${S.vol}:${S.page}`) renderPage();
    });
    return;
  }
  if (hit === "loading") return;
  if (!hit.data) { toast("No merged text for this page: nothing was decided in /merge here"); return; }
  for (const f of root.querySelectorAll(".f[data-path]")) {
    const v = at(hit.data, f.dataset.path);
    if (typeof v !== "string") continue;
    f.contentEditable = "false";
    f.classList.add("mv");
    render(f, v, null, hit.marks[f.dataset.path] || null);
  }
});
