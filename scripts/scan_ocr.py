"""Kraken OCR of the scans, for the review editor's overlay only (never a source of text).

    python3 scan_ocr.py <volume> [first-last]     OCR every page of a volume (or a range) not yet cached

`ocr(vol, page)` runs Kraken (CATMuS-Print Large, about 30 s a page) and caches the words with their
boxes in cache/ocr/<vol>/page_NNNN.json; `align(ocr, data)` sets each OCR word against the page's
JSON fields: the same word (old spelling allowed), a different one, or missing from the JSON.
"""
import difflib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

from paths import DATA, SCRIPTS, STUDIUM

OCR_CACHE = SCRIPTS / "cache" / "ocr"
KRAKEN = Path(os.environ.get("CALMET_KRAKEN") or STUDIUM / ".kraken-venv" / "bin" / "kraken")
MODEL = Path(os.environ.get("CALMET_KRAKEN_MODEL") or Path.home() / "Library" / "Application Support" / "htrmopo"
             / "d96caf7a-122e-5576-ab2b-a246c4e64221" / "catmus-print-fondue-large.mlmodel")


def scan_path(vol, page):
    return DATA / vol / "source_images" / "commentaire" / f"page_{page:04d}.png"


def cache_path(vol, page):
    return OCR_CACHE / vol / f"page_{page:04d}.json"


# --- OCR ---
def parse_alto(xml):
    """ALTO → {"size": [w, h], "lines": [{"box": [x, y, w, h], "words": [{"t", "box", "wc"}]}]}."""
    root = ET.fromstring(xml)
    ns = root.tag.split("}")[0] + "}" if root.tag.startswith("{") else ""
    box = lambda e: [int(float(e.get(k))) for k in ("HPOS", "VPOS", "WIDTH", "HEIGHT")]
    page = root.find(f".//{ns}Page")
    lines = [{"box": box(ln), "words": [{"t": unicodedata.normalize("NFC", s.get("CONTENT")), "box": box(s), "wc": round(float(s.get("WC") or 0), 3)}
                                        for s in ln.iter(f"{ns}String")]}
             for ln in root.iter(f"{ns}TextLine")]
    return {"size": [int(page.get("WIDTH")), int(page.get("HEIGHT"))], "lines": [ln for ln in lines if ln["words"]]}


_running = {}
_running_lock = threading.Lock()


def ocr(vol, page, run=True, scan=None):
    """The page's OCR, from the cache; else, with `run`, Kraken's (cached). None: no scan, or not run.
    `scan`: the image, if not the one in data/."""
    out, scan = cache_path(vol, page), Path(scan or scan_path(vol, page))
    if out.exists():
        return json.loads(out.read_text(encoding="utf-8"))
    if not run or not scan.exists():
        return None
    with _running_lock:  # one Kraken per page at a time: a second request waits for the first
        lock = _running.setdefault((vol, page), threading.Lock())
    with lock:
        if out.exists():
            return json.loads(out.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            xml = Path(tmp) / "page.xml"
            subprocess.run([str(KRAKEN), "-a", "-i", str(scan), str(xml),
                            "segment", "-bl", "ocr", "-m", str(MODEL)], check=True, capture_output=True)
            data = parse_alto(xml.read_bytes())
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        return data


# --- alignment ---
TOKEN = re.compile(r"[^\W_]+(?:-[^\W_]+)*")
OCR_TOKEN = re.compile(r"&|[^\W_]+(?:-[^\W_]+)*")  # & is "et"
ABBREV = {"s": "saint", "ste": "sainte", "st": "saint"}


def key(t):
    """A word's spelling-blind key: no accents or case; ſ, &, y, j, v, oi as in the modernized text."""
    t = unicodedata.normalize("NFKD", t.lower().replace("ſ", "s").replace("æ", "ae").replace("œ", "oe"))
    t = "".join(c for c in t if c.isalnum())
    t = t.replace("y", "i").replace("j", "i").replace("v", "u").replace("oi", "ai")
    return ABBREV.get(t, "et" if t == "" else t)


def ocr_tokens(o):
    """The OCR's words in reading order as tokens: a String may hold several ("21.Et"), a word cut at
    the line's end (¬) is joined to the next line's first. Each: {t, k, boxes, wc, line}."""
    out, carry = [], None
    for li, ln in enumerate(o["lines"]):
        for wi, w in enumerate(ln["words"]):
            text, (x, y, bw, bh) = unicodedata.normalize("NFC", w["t"]), w["box"]
            n = max(1, len(text))
            for m in OCR_TOKEN.finditer(text):
                a, b = m.span()
                tok = {"t": m.group(), "boxes": [[x + round(bw * a / n), y, max(1, round(bw * (b - a) / n)), bh]],
                       "wc": w["wc"], "line": li}
                if carry:  # the first word after a cut
                    carry["t"] += tok["t"]
                    carry["boxes"] += tok["boxes"]
                    carry["wc"] = min(carry["wc"], tok["wc"])
                    tok, carry = carry, None
                out.append(tok)
            if wi == len(ln["words"]) - 1 and text.endswith(("¬", "-")) and out and out[-1]["line"] == li:
                carry = out.pop()
    if carry:
        out.append(carry)
    for t in out:
        t["k"] = key(t["t"])
    return out


HEAD_FIELDS = ["book_title", "chapter_title", "chapter_summary", "chapter_argument", "chapter_intro"]
TEXT_FIELDS = {"verses": ["annotations", "latin"], "verses_fr": ["french"],  # the year is in the left margin
               "commentary": ["latin_quote", "french_translation", "french_commentary"], "footnotes": ["marker", "text"]}
MARKUP = re.compile(r"\^\{|\}")


def json_tokens(data):
    """The page's words in the scan's order: headings, the verses' Latin column then their French, the
    commentary, the footnotes. Each: {t, k, path, a, b} (a, b: offsets in the field's string)."""
    fields = [(f, data.get(f)) for f in HEAD_FIELDS]
    for sec in ("verses", "verses_fr", "commentary", "footnotes"):
        src = "verses" if sec == "verses_fr" else sec
        for i, blk in enumerate(data.get(src) or []):
            for f in TEXT_FIELDS[sec]:
                fields.append((f"{src}/{i}/{f}", blk.get(f)))
    fields.append(("book_end_marker", data.get("book_end_marker")))
    out = []
    for path, s in fields:
        if not isinstance(s, str):
            continue
        for m in TOKEN.finditer(MARKUP.sub(lambda m: " " * len(m.group()), s)):
            out.append({"t": m.group(), "k": key(m.group()), "path": path, "a": m.start(), "b": m.end()})
    return out


def similar(a, b):
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


CONFUSED = [set("tlrfsi"), set("ceo"), set("nu")]  # letters Kraken mistakes for each other in this type


def slip(o, j):
    """Two keys that differ only as Kraken's slips or old spelling do: a doubled letter (jetter, AAn), or
    one letter for a look-alike (salte, traduite)."""
    def look_alike(o, j):
        diff = [(x, y) for x, y in zip(o, j) if x != y]
        return len(o) == len(j) and len(diff) == 1 and any(set(diff[0]) <= g for g in CONFUSED)
    single = lambda t: re.sub(r"(.)\1+", r"\1", t)
    return single(o) == single(j) or look_alike(o, j) or look_alike(single(o), single(j))


def _pair(ocr_run, json_run):
    """Inside a stretch the two disagree on: [(ocr indexes, json index or None, json count, status)]."""
    out, j = [], 0
    i = 0
    while i < len(ocr_run):
        best = None
        for jj in range(j, min(len(json_run), j + 3)):
            for take, jtake in ((1, 1), (2, 1), (1, 2)):  # 2:1 or 1:2, a space lost on one side
                if i + take > len(ocr_run) or jj + jtake > len(json_run):
                    continue
                k = "".join(t["k"] for t in ocr_run[i:i + take])
                jk = "".join(t["k"] for t in json_run[jj:jj + jtake])
                r = similar(k, jk) - 0.05 * (jj - j) - 0.02 * (take + jtake - 2)
                if best is None or r > best[0]:
                    best = (r, jj, take, jtake, k == jk)
        if best and best[0] >= 0.5:
            r, jj, take, jtake, same = best
            status = ("ok" if same or (take == jtake == 1 and slip(k, json_run[jj]["k"]))  # a lost space is the OCR's
                      else "near" if r >= 0.8 and take == jtake == 1 else "diff")
            out.append((list(range(i, i + take)), jj, jtake, status))
            i, j = i + take, jj + jtake
        else:
            out.append(([i], None, 0, "missing"))
            i += 1
    return out


HEADER = re.compile(r"COMMENTAIRE|LITTERAL|^SUR\b|CHAP", re.I)


def skipped_lines(o):
    """Lines no field holds: the running header (in the top band, but for the year in the margin) and the
    "COMMENTAIRE." between the verses and the commentary."""
    h = o["size"][1]
    out = set()
    for li, ln in enumerate(o["lines"]):
        text = " ".join(w["t"] for w in ln["words"])
        top = ln["box"][1] < 0.075 * h
        if (top and (HEADER.search(text) or re.fullmatch(r"[\dIVXLC.\s]+", text))) or re.fullmatch(r"COMMENTAIRE\.?", text.strip()):
            out.add(li)
    return out


def align(o, data):
    """The OCR set against the JSON: {"size", "words": [{t, boxes, s, path?, a?, b?}], "extra": [{t, path,
    a, b}]}. A word's `s`: ok (the same word, old spelling allowed), near (nearly), diff (a different
    word), missing (not in the JSON), skip (the running header, an unsure reading, a footnote: they are
    expanded, so they differ by design). `extra`: the JSON's words the scan does not have (but for the
    footnotes'), with what they are written in."""
    skip = skipped_lines(o)
    ot = [t for t in ocr_tokens(o) if t["line"] not in skip]
    jt = json_tokens(data)
    res = [dict(t=t["t"], boxes=t["boxes"], s="missing") for t in ot]

    used = set()

    def link(i, j, status, n=1):
        res[i].update(s=status, path=jt[j]["path"], a=jt[j]["a"], b=jt[j + n - 1]["b"])
        used.update(range(j, j + n))

    sm = difflib.SequenceMatcher(None, [t["k"] for t in ot], [t["k"] for t in jt], autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for d in range(i2 - i1):
                link(i1 + d, j1 + d, "ok")
        elif op == "replace":
            for idx, j, n, status in _pair(ot[i1:i2], jt[j1:j2]):
                for i in idx:
                    if j is not None:
                        link(i1 + i, j1 + j, status, n)
    # around the footnotes (expanded by design), the unmatched are not flagged; nor are unsure readings
    near_path = [None] * len(res)
    last = None
    for i, r in enumerate(res):
        last = r.get("path", last)
        near_path[i] = last
    for i in range(len(res) - 1, -1, -1):
        nxt = res[i].get("path") or (near_path[i + 1] if i + 1 < len(res) else None)
        near_path[i] = near_path[i] or nxt
    for r, t, p in zip(res, ot, near_path):
        if r["s"] in ("missing", "diff", "near") and (
                t["wc"] < 0.6 or (p or "").startswith("footnotes/") or (r.get("path") or "").startswith("footnotes/")):
            r["s"] = "skip" if r["s"] == "missing" else "ok"
        if r["s"] == "missing" and (t["t"].isdigit() or len(t["t"]) <= 1):  # a verse number, a stray letter
            r["s"] = "skip"
    extra = [dict(t=t["t"], path=t["path"], a=t["a"], b=t["b"]) for j, t in enumerate(jt)
             if j not in used and not t["path"].startswith("footnotes/") and len(t["t"]) > 1 and not t["t"].isdigit()]
    return {"size": o["size"], "words": res, "extra": extra}


def main(argv):
    if not argv:
        sys.exit(__doc__)
    vol = argv[0]
    pages = sorted(int(p.stem.split("_")[1]) for p in (DATA / vol / "source_images" / "commentaire").glob("page_*.png"))
    if len(argv) > 1:
        a, _, b = argv[1].partition("-")
        pages = [p for p in pages if int(a) <= p <= int(b or a)]
    todo = [p for p in pages if not cache_path(vol, p).exists()]
    print(f"{vol}: {len(pages) - len(todo)} pages cached, {len(todo)} to OCR", flush=True)
    for n, p in enumerate(todo, 1):
        try:
            ocr(vol, p)
        except subprocess.CalledProcessError as e:
            print(f"  p.{p}: Kraken failed: {e.stderr.decode(errors='replace')[-300:]}", flush=True)
            continue
        if n % 10 == 0 or n == len(todo):
            print(f"  {n}/{len(todo)} (p.{p})", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
