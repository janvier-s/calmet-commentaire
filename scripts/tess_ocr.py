"""Tesseract's reading of a scan page, a second witness beside Kraken's for the OCR overlay.

  python tess_ocr.py <volume> <page>...   read the pages (12, 30-34) and cache them

The reading: {"size": [w, h], "words": [{"t", "box": [x, y, w, h], "conf"}]}, cached in
cache/tess/<volume>/page_NNNN.json. Models: cache/tessdata (fra; lat and frm from tessdata_best).
Tesseract itself: $CALMET_TESSERACT, else the one on the PATH, else Homebrew's."""
import datetime
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

from paths import SCRIPTS
from scan_ocr import _fmt_duration, scan_path

TESS_CACHE = SCRIPTS / "cache" / "tess"
TESSDATA = SCRIPTS / "cache" / "tessdata"
TESSERACT = os.environ.get("CALMET_TESSERACT") or shutil.which("tesseract") or "/opt/homebrew/bin/tesseract"
MODELS = "https://github.com/tesseract-ocr/tessdata_best/raw/main/{}.traineddata"


def cache_path(vol, page):
    return TESS_CACHE / vol / f"page_{page:04d}.json"


def parse_tsv(text):
    """Tesseract's TSV → its words (level 5, text not blank): [{t, box, conf}]."""
    out = []
    for ln in text.splitlines()[1:]:
        f = ln.split("\t")
        if len(f) == 12 and f[0] == "5" and f[11].strip():
            out.append({"t": f[11].strip(), "box": [int(v) for v in f[6:10]], "conf": float(f[10])})
    return out


def _size(text):
    """The page's size, from the TSV's level-1 row."""
    for ln in text.splitlines()[1:]:
        f = ln.split("\t")
        if len(f) >= 10 and f[0] == "1":
            return [int(f[8]), int(f[9])]
    return [0, 0]


def read(vol, page, run=False):
    """The page's Tesseract reading, from the cache; else, with `run`, Tesseract's (cached). None: no
    scan, or not run. A run that fails gives no words and its `error` (not cached: it is tried again)."""
    out, scan = cache_path(vol, page), scan_path(vol, page)
    if out.exists():
        return json.loads(out.read_text(encoding="utf-8"))
    if not run or not scan.exists():
        return None
    fetch_models()
    try:
        tsv = subprocess.run([TESSERACT, str(scan), "-", "--tessdata-dir", str(TESSDATA), "-l", "frm+lat+fra",
                              "--psm", "3", "-c", "tessedit_create_tsv=1"],
                             check=True, capture_output=True).stdout.decode("utf-8", errors="replace")
    except FileNotFoundError:
        why = f"tesseract not found ({TESSERACT}; set CALMET_TESSERACT)"
    except subprocess.CalledProcessError as e:
        why = (e.stderr or b"").decode("utf-8", errors="replace").strip()[-300:] or f"exit {e.returncode}"
    except OSError as e:
        why = str(e)
    else:
        why = None
    if why:
        print(f"  {vol} p.{page}: Tesseract failed: {why}", flush=True)
        return {"size": [0, 0], "words": [], "error": why}
    data = {"size": _size(tsv), "words": parse_tsv(tsv)}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return data


def under(tess, boxes):
    """Tesseract's words beneath `boxes` (overlapping one by more than 40% of the smaller of the two), in
    its reading order, joined."""
    def over(a, b):
        w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
        h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
        return w > 0 and h > 0 and w * h > 0.4 * min(a[2] * a[3], b[2] * b[3])
    return "".join(w["t"] for w in tess["words"] if any(over(w["box"], b) for b in boxes))


def fetch_models():
    """lat and frm (tessdata_best), downloaded if missing; fra is there already."""
    TESSDATA.mkdir(parents=True, exist_ok=True)
    for lang in ("lat", "frm"):
        dest = TESSDATA / f"{lang}.traineddata"
        if not dest.exists():
            print(f"  downloading {lang}.traineddata", flush=True)
            part = dest.with_suffix(".part")
            urllib.request.urlretrieve(MODELS.format(lang), part)
            part.rename(dest)


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)
    vol = argv[0]
    pages = []
    for arg in argv[1:]:
        a, _, b = arg.partition("-")
        pages.extend(range(int(a), int(b or a) + 1))

    scanned = [p for p in pages if scan_path(vol, p).exists()]
    todo = [p for p in scanned if not cache_path(vol, p).exists()]
    total_scanned = len(scanned)
    cached_count = total_scanned - len(todo)
    total_todo = len(todo)
    now_str = datetime.datetime.now().strftime("%H:%M:%S")

    print(f"[{now_str}] {vol}: {cached_count} pages cached, {total_todo} to OCR", flush=True)

    t0 = time.time()
    done_count = 0
    chunk_t0 = time.time()

    for p in pages:
        is_cached = cache_path(vol, p).exists()
        page_t0 = time.time()
        t = read(vol, p, run=True)
        page_took = time.time() - page_t0
        now = datetime.datetime.now()
        now_time = now.strftime("%H:%M:%S")

        if is_cached:
            status = "no scan" if t is None else t.get("error") or f"{len(t['words'])} words"
            print(f"[{now_time}] {vol} p.{p}: {status}", flush=True)
        elif t is None:
            print(f"[{now_time}] {vol} p.{p}: no scan", flush=True)
        elif "error" in t:
            print(f"[{now_time}] {vol} p.{p}: Tesseract failed: {t['error']}", flush=True)
        else:
            done_count += 1
            current_count = cached_count + done_count
            pct = (current_count / total_scanned) * 100 if total_scanned else 100.0
            elapsed = time.time() - t0
            words = len(t["words"])
            if done_count < total_todo:
                sec_per_item = elapsed / done_count
                remaining_sec = sec_per_item * (total_todo - done_count)
                eta_time = (now + datetime.timedelta(seconds=remaining_sec)).strftime("%H:%M:%S")
                time_info = f"ETA {eta_time} (~{_fmt_duration(remaining_sec)} left)"
            else:
                time_info = f"done in {_fmt_duration(elapsed)}"
            print(f"[{now_time}] {vol} p.{p}: {words} words ({page_took:.1f}s) · {current_count}/{total_scanned} ({pct:4.1f}%) · {time_info}", flush=True)
            if done_count % 10 == 0 or done_count == total_todo:
                chunk_took = time.time() - chunk_t0
                print(f"[{now_time}]   {current_count:3d}/{total_scanned} ({pct:5.1f}%) (p.{p}) · took {_fmt_duration(chunk_took)} ({_fmt_duration(elapsed)} elapsed, {time_info})", flush=True)
                chunk_t0 = time.time()

    if total_todo:
        total_time = time.time() - t0
        sec_per_page = total_time / total_todo
        now_time = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[{now_time}] {vol}: {total_todo} pages OCR'd in {_fmt_duration(total_time)} ({sec_per_page:.1f}s/page)", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
