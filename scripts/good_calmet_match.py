#!/usr/bin/env python3
"""Align Good_Calmet PDF pages to existing source_images pages by content.

The two scan sets have different pagination, so page numbers can't be used.
We compare OCR text of each new page (good_calmet_ocr.py) with the text we
already extracted per source page (data/<book>/raw_json/commentaire/*.json),
then pick the best order-preserving assignment.

Usage:
  uv run --with numpy --with scikit-learn scripts/good_calmet_match.py \
      <work_dir> <book_dir> <out.json> <manifest.json>...
"""
import json, re, sys, unicodedata
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

TEXT_TYPES = {"commentary"}  # dissertation and front matter are under raw_json/intro and fin
THETA = 0.30     # a page must beat this similarity to count as a match (noise is ~0.12-0.17)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("ſ", "s").replace("æ", "ae").replace("œ", "oe")
    s = re.sub(r"[^a-z ]+", " ", s)
    s = s.replace("f", "s")          # tesseract reads long-s as f; source has plain s
    return re.sub(r"\s+", " ", s).strip()


def strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from strings(v)


def align(S):
    """Order-preserving assignment. f[i][j]: best score for the first i pages with
    every matched source index <= j. Ops: 0 = advance j, 1 = page unmatched, 2 = match."""
    n, m = S.shape
    f = np.zeros((n + 1, m))
    op = np.zeros((n + 1, m), dtype=np.int8)
    for i in range(1, n + 1):
        prev = f[i - 1]
        gain = prev + S[i - 1] - THETA
        for j in range(m):
            best, o = prev[j], 1
            if gain[j] > best:
                best, o = gain[j], 2
            if j > 0 and f[i, j - 1] > best:
                best, o = f[i, j - 1], 0
            f[i, j], op[i, j] = best, o
    res = [-1] * n
    i, j = n, m - 1
    while i > 0 and j >= 0:
        o = op[i, j]
        if o == 0:
            j -= 1
        elif o == 1:
            i -= 1
        else:
            res[i - 1] = j
            i -= 1
    return res


def load_text(f: Path) -> str:
    raw = f.read_text()
    try:
        return " ".join(strings(json.loads(raw, strict=False)))
    except json.JSONDecodeError:
        return raw          # still fine for n-gram matching


def main():
    work, book, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    pdf_pages, pdf_txt = [], []
    for m in sys.argv[4:]:
        man = json.loads(Path(m).read_text()); stem = Path(m).stem
        for p in man["pages"]:
            if p.get("type") in TEXT_TYPES:
                t = work / stem / "ocr" / f"{p['pdf_page']}.txt"
                if t.exists():
                    pdf_pages.append((stem, p["pdf_page"], p["type"], p.get("header", "")))
                    pdf_txt.append(norm(t.read_text()))
    src_files = sorted((book / "raw_json" / "commentaire").glob("page_*.json"))
    src_txt = [norm(load_text(f)) for f in src_files]
    print(len(pdf_txt), "pdf pages,", len(src_txt), "source pages")

    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(4, 5), sublinear_tf=True, min_df=2)
    vec.fit(src_txt + pdf_txt)
    A, B = vec.transform(pdf_txt), vec.transform(src_txt)
    S = (A @ B.T).toarray()
    mono = align(S)                      # order-preserving answer, used only to flag conflicts
    best = S.argmax(1)                   # per-page best match: robust, since real matches
    rows = []                            # (>= THETA) sit well above the ~0.12-0.17 noise floor
    for k, (stem, pg, typ, hdr) in enumerate(pdf_pages):
        j = int(best[k])
        row = {"pdf": stem, "pdf_page": pg, "type": typ, "header": hdr}
        if S[k, j] >= THETA:
            row.update(source=src_files[j].stem, sim=round(float(S[k, j]), 3))
            if mono[k] != j:
                row["out_of_order"] = True
            nb = [(S[k, x], x) for x in (j - 1, j + 1) if 0 <= x < len(src_files)]
            s2, x2 = max(nb)
            if s2 > 0.6 * S[k, j] and s2 > THETA:
                row.update(also=src_files[x2].stem, also_sim=round(float(s2), 3))
        rows.append(row)
    out.write_text(json.dumps(rows, indent=1, ensure_ascii=False))
    matched = [r for r in rows if "source" in r]
    sims = np.array([r["sim"] for r in matched])
    print(f"matched {len(matched)}/{len(rows)}; sim mean {sims.mean():.2f}, p10 {np.percentile(sims,10):.2f}")
    used = {r["source"] for r in matched}
    miss = [f.stem for f in src_files if f.stem not in used]
    cov = used | {r["also"] for r in matched if "also" in r}
    miss = [f.stem for f in src_files if f.stem not in cov]
    print(len(miss), "source pages not covered even counting neighbours:", miss[:30])
    print(sum(1 for r in matched if r.get("out_of_order")), "pages out of order vs the order-preserving fit")


if __name__ == "__main__":
    main()
