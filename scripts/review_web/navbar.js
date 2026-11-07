// The bar the editor and /merge share: Book › Issue › Page, then the Review / Merge tabs. Imports nothing from
// app.js (its import has side effects against index.html's DOM). The editor's copy is in index.html, same classes.
import { el } from "./goodfig.js";

/** `parts`: the crumbs, each a node or a string (null left out); `tab`: "review" or "merge"; `review` / `merge`:
 *  the tabs' links ({href, onclick}). Same tab: the browser's Back comes back. */
export function navBar(parts, tab, review, merge) {
  const crumbs = [];
  for (const p of parts.filter((x) => x != null)) {
    if (crumbs.length) crumbs.push(el("span", { className: "nav-sep", textContent: "›" }));
    crumbs.push(typeof p === "string" ? el("span", { className: "nav-crumb", textContent: p }) : p);
  }
  const t = (name, label, link) => el("a", { className: "nav-tab" + (tab === name ? " on" : ""), textContent: label, ...link });
  return [el("nav", { className: "nav-crumbs" }, ...crumbs),
          el("nav", { className: "nav-tabs" }, t("review", "Review", review), t("merge", "Merge", merge))];
}

/** The editor's address for a page of a book (queue.js opens it, the queue alongside). */
export const reviewHref = (vol, page) => `/#edit=${encodeURIComponent(vol)}:${page || ""}`;
