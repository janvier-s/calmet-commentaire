// The server stops when its last tab is closed (review_web.py's Presence): this tab says it is alive every
// few seconds and goodbye when it goes. A reload or Review <-> Merge comes back within the server's grace.
let tab = null;
const newTab = () => { tab = (crypto.randomUUID && crypto.randomUUID()) || String(Math.random()).slice(2); };
const post = (path) => fetch(path, { method: "POST", credentials: "same-origin", keepalive: true,
  headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tab }) }).catch(() => {});
const beat = () => post("/api/alive");

newTab();
beat();
setInterval(beat, 5000);
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") beat(); });
addEventListener("pagehide", () => {
  if (!navigator.sendBeacon || !navigator.sendBeacon("/api/bye", JSON.stringify({ tab }))) post("/api/bye");
});
addEventListener("pageshow", (e) => { if (e.persisted) { newTab(); beat(); } });  // back from the page cache: a new tab
