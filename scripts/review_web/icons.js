// Small line icons (24×24, stroke = currentColor). icon(name) → an <svg>; [data-icon] elements get one.
const P = {
  verses: "M4 4.5A1.5 1.5 0 0 1 5.5 3H20v15H5.5A1.5 1.5 0 0 0 4 19.5zM4 19.5A1.5 1.5 0 0 0 5.5 21H20v-3M8 7h8M8 10.5h6",
  commentary: "M4 5h16v11H9l-5 4zM8 9h8M8 12.5h5",
  footnotes: "M12 3v8M8.5 5l7 4M15.5 5l-7 4M5 15h14M5 19h9",
  save: "M5 4h11l3 3v13H5zM8 4v5h7V4M8 20v-6h8v6",
  check: "M5 12.5l4.5 4.5L19 7",
  flag: "M6 21V4M6 4h11l-2 4 2 4H6",
  skip: "M5 6l7 6-7 6zM13 6l7 6-7 6",
  reopen: "M4 12a8 8 0 1 0 2.5-5.8M4 4v5h5",
  prev: "M15 5l-7 7 7 7",
  next: "M9 5l7 7-7 7",
  more: "M5 12h.01M12 12h.01M19 12h.01",
  italic: "M10 4h8M6 20h8M14 4l-4 16",
  up: "M12 19V5M5 12l7-7 7 7",
  down: "M12 5v14M19 12l-7 7-7-7",
  top: "M5 4h14M12 20V8M6 14l6-6 6 6",
  bottom: "M5 20h14M12 4v12M6 10l6 6 6-6",
  trash: "M12 21a9 9 0 1 1 0-18 9 9 0 0 1 0 18zM9 9l6 6M15 9l-6 6",
  undo: "M9 14L4 9l5-5M4 9h10a6 6 0 0 1 0 12h-3",
  grip: "M9 6h.01M15 6h.01M9 12h.01M15 12h.01M9 18h.01M15 18h.01",
  plus: "M12 5v14M5 12h14",
  back: "M10 7l-5 5 5 5M5 12h14",
  fwd: "M14 7l5 5-5 5M19 12H5",
  invert: "M12 3a9 9 0 1 0 0 18zM12 3a9 9 0 0 1 0 18",
  copy: "M9 9h11v11H9zM5 15H4V4h11v1",
  search: "M11 18a7 7 0 1 1 0-14 7 7 0 0 1 0 14zM16 16l4 4",
};

export function icon(name, size = 15) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("width", size);
  svg.setAttribute("height", size);
  svg.setAttribute("aria-hidden", "true");
  svg.classList.add("ic");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", P[name] || "");
  svg.append(path);
  return svg;
}

export function decorate(root = document) {
  for (const e of root.querySelectorAll("[data-icon]:not(.has-icon)")) {
    e.prepend(icon(e.dataset.icon));
    e.classList.add("has-icon");
  }
}
