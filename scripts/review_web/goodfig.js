// The Good_Calmet crop figure, shared by the queue's proposal cards and the /merge screen. Imports nothing
// from app.js (its import has side effects against index.html's DOM).

const el = (tag, props = {}, ...kids) => {
  const e = Object.assign(document.createElement(tag), props);
  e.append(...kids.filter((k) => k != null));
  return e;
};

/** A Good_Calmet crop's band around the boxes, the boxes highlighted, with its PDF and printed page. */
export function goodFigure(g, goodText) {
  const url = `/goodcrop/${encodeURIComponent(g.pdf)}/${g.pdf_page}`;
  const bs = g.boxes || [];
  const pad = 30;
  const y0 = Math.max(0, Math.min(...bs.map((b) => b[1])) - pad);
  const y1 = Math.max(...bs.map((b) => b[1] + b[3])) + pad;
  const band = el("div", { className: "goodband" });
  const img = el("img", { src: url, alt: "Good_Calmet", draggable: false });
  band.append(img);
  img.onload = () => {
    const k = band.clientWidth / img.naturalWidth;
    band.style.height = `${Math.max(40, (y1 - y0) * k)}px`;
    img.style.top = `${-y0 * k}px`;
    for (const [x, y, w, h] of bs) {
      band.append(el("div", { className: "goodbox", style: `left:${x * k}px;top:${(y - y0) * k}px;width:${w * k}px;height:${h * k}px` }));
    }
  };
  const cap = el("div", { className: "muted small" },
    el("a", { href: url, target: "_blank", textContent: `Good_Calmet ${g.pdf} p.${g.pdf_page}` }),
    g.printed ? ` · printed page ${g.printed}` : "");
  return el("div", { className: "goodfig" }, cap, bs.length ? band : null,
    goodText ? el("div", { className: "small goodtext", textContent: `Good reads: ${goodText}` }) : null);
}
