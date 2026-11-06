"""The Good_Calmet footnotes read by agy (Gemini Flash) from a crop of each page's note block.

    uv run --with pillow python3 good_notes_read.py <vol> <chapter>[-<chapter>] [--jobs N] [--redo]
    uv run --with pillow python3 good_notes_read.py --page <pdf> <pdf_page>     one page (prints it)

Kraken misreads small type (XIIX, I7, X1) and reads Latin letters only; Flash reads the notes, Hebrew and
Greek included. Each Good page with notes (Kraken's marks, or footnotes on its source page in the JSON)
is cropped from a little above the first note (or from 70% down) to the foot, the crop sent to agy with
an @ mention, the answer parsed into notes [{mark, text}] and cached per page in cache/good_notes_agy/
(the crop beside it, for the review editor). About one call in six reaches for a tool and fails: it is
tried again, up to --tries times. good_notes.py reads these instead of Kraken's text where they exist,
keeping Kraken's boxes to locate each note.
"""
import asyncio
import json
import os
import re
import sys

from paths import SCRIPTS
import good_calmet_kraken as gk
import good_variants as gv

CACHE = SCRIPTS / "cache" / "good_notes_agy"
MODEL = os.environ.get("GOOD_NOTES_MODEL", "gemini-3.8-flash-medium")
VERSION = 1  # bump when the prompt or the crop changes

PROMPT = """The image is the foot of a page of an 18th-century French Bible commentary (Dom Calmet). Under the body text \
(larger type), usually below a horizontal rule, are the footnotes: small type, mostly in two columns, each note opening \
with a mark such as (a), (b), (c).

Transcribe the footnotes only, the left column first, then the right column. Write one note per line, starting with \
its mark in parentheses, for example:
(a) Exod. XXXII. 25.
(b) S. Aug. de Genes. ad litt. l. XI. c. 39.

Join each note's lines into one line and rejoin a word hyphenated at a line's end. Keep the spelling, abbreviations, \
punctuation and numbers exactly as printed (roman numerals as letters, upper or lower case as printed: XIV, xiv; the \
long s as s). Write Hebrew in Hebrew letters, with the vowel points only if printed; Greek in Greek letters with its \
accents and breathings. Leave out the body text above the notes, the catchword at the bottom right and the \
gathering's signature (such as B ij). Do not use any tool: answer with the transcription only. If the image has no \
footnotes, answer NONE."""

LINE = re.compile(r"^\s*[(\[]\s*([a-zA-Z*†]{1,2}|\d{1,2})\s*[)\]]\s*(.*)$")


def src(vol):
    """The `pdf` name standing for a volume's source scans (the third witness): src:<vol>."""
    return f"src:{vol}"


def path(pdf, page, ext="json"):
    return CACHE / pdf.replace(":", "_") / f"page_{page:04d}.{ext}"


def image(pdf, page):
    import scan_ocr
    return scan_ocr.scan_path(pdf[4:], page) if pdf.startswith("src:") else gk.crop_path(pdf, page)


def kraken_ocr(pdf, page):
    import scan_ocr
    if pdf.startswith("src:"):
        return scan_ocr.ocr(pdf[4:], page, run=False)
    p = gk.cache_path(pdf, page)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def cached(pdf, page):
    p = path(pdf, page)
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("version") == VERSION and d.get("notes") is not None:
            return d
    return None


def block_top(pdf, page):
    """The crop's top: two lines above Kraken's first note mark, else 70% down the page."""
    import good_notes as gn
    o = kraken_ocr(pdf, page)
    if o is None:
        return None, False
    h = o["size"][1]
    ns = gn.page_notes(pdf, page, o)
    ys = [x["box"][1] for n in ns for x in n["words"]]
    if ys:
        return max(0, min(ys) - max(60, int(0.045 * h))), True
    return int(0.7 * h), False


def make_crop(pdf, page, top):
    from PIL import Image
    out = path(pdf, page, "png")
    out.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(image(pdf, page)) as im:
        im.crop((0, top, im.size[0], im.size[1])).save(out)
    return out


def prepare(pdf, page):
    """(crop, top, kraken) for a page, or None when it has no OCR. Blocking: run off the event loop."""
    top, kraken = block_top(pdf, page)
    return None if top is None else (make_crop(pdf, page, top), top, kraken)


def enlarge(crop):
    """The crop at twice the size, beside it."""
    from PIL import Image
    out = crop.with_name(crop.stem + "_x2.png")
    with Image.open(crop) as im:
        im.resize((im.size[0] * 2, im.size[1] * 2), Image.LANCZOS).save(out)
    return out


def parse(text):
    """[{mark, text}] from the answer; [] for NONE; None when it is not a transcription."""
    t = text.strip()
    if re.fullmatch(r"NONE\.?", t, re.I):
        return []
    notes = []
    for ln in t.splitlines():
        ln = ln.strip().strip("`")
        if not ln:
            continue
        m = LINE.match(ln)
        if m:
            notes.append({"mark": m.group(1), "text": m.group(2).strip()})
        elif notes:
            notes[-1]["text"] += " " + ln  # a note's line the model left apart
    return notes or None


async def call(crop, sem, prompt=PROMPT):
    """One agy Flash call: (answer, None) or (None, error). `crop`: the image it reads (None: text only)."""
    async with sem:
        return await agy(crop, prompt)


async def agy(crop, prompt=PROMPT):
    """`call` without the semaphore (the caller holds it)."""
    if crop is None:
        cwd = CACHE / "_empty"
        cwd.mkdir(parents=True, exist_ok=True)
        text = "Answer directly, with text only: do not use any tool, do not run commands, do not read or write files.\n\n" + prompt
    else:
        cwd, text = crop.parent, f"@{crop.name} {prompt}"
    args = ["agy", "--print-timeout", "300s", "--disable-slash-commands", "--output-format", "json",
            "--model", MODEL, "-p", text]
    proc = await asyncio.create_subprocess_exec(*args, cwd=str(cwd), stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), 360)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return None, "timed out"
    try:
        d = json.loads(out.decode())
    except json.JSONDecodeError:
        return None, (err or out).decode()[:300]
    if d.get("status") != "SUCCESS":
        return None, str(d.get("response") or err.decode())[:300]
    return str(d.get("response") or ""), None


QUOTA = {"hit": False}


async def read_page(pdf, page, sem, tries=4, redo=False):
    if not redo and (d := cached(pdf, page)):
        return d
    async with sem:  # the whole page: its crop is made only when a slot is free, and off the event loop
        return await _read_page(pdf, page, tries)


async def _read_page(pdf, page, tries):
    if QUOTA["hit"]:
        return None
    prep = await asyncio.to_thread(prepare, pdf, page)
    if prep is None:
        return None
    crop, top, kraken = prep
    raw, err = None, None
    for t in range(tries):
        if QUOTA["hit"]:
            return None
        if t == tries // 2:  # a crop Flash keeps reaching for a tool on (to zoom?): sent at twice the size
            crop = await asyncio.to_thread(enlarge, crop)
        raw, err = await agy(crop)
        notes = parse(raw) if raw is not None else None
        if notes == [] and kraken and t < tries - 1:
            notes = None  # NONE where Kraken saw a note's mark: Flash missed them, ask again (accepted at the last try)
        if notes is not None:
            d = {"version": VERSION, "model": MODEL, "pdf": pdf, "pdf_page": page, "top": top,
                 "top_from": "kraken" if kraken else "70%", "raw": raw, "notes": notes}
            path(pdf, page).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            return d
        if err and re.search(r"quota|exhausted|429|rate limit", err, re.I):
            QUOTA["hit"] = True
            print(f"  agy quota: {err[:120]}", file=sys.stderr, flush=True)
    print(f"  {pdf} p.{page}: no transcription after {tries} tries: {(err or raw or '')[:150]!r}", file=sys.stderr, flush=True)
    return None


def pages_for(vol, chs):
    """The Good pages of these chapters worth a call: Kraken found a note mark, or the source page has footnotes."""
    import good_notes as gn
    pages = gv.chapter_pages(vol, chs)
    recs = sorted((r for r in gk.crops() if r["vol"] == vol and r.get("source") and pages[0] <= int(r["source"][5:]) <= pages[-1]),
                  key=lambda r: (r["pdf"], r["pdf_page"]))
    out = []
    for r in recs:
        src = int(r["source"][5:])
        if (gv.norm(vol, src) or {}).get("footnotes") or (  # Kraken's OCR read only when the JSON has no footnotes
                gk.cache_path(r["pdf"], r["pdf_page"]).exists() and gn.page_notes(r["pdf"], r["pdf_page"])):
            out.append((r["pdf"], r["pdf_page"]))
    return out


async def run(jobs, n, tries, redo):
    sem = asyncio.Semaphore(n)
    done = {"n": 0}

    async def one(pdf, page):
        d = await read_page(pdf, page, sem, tries, redo)
        done["n"] += 1
        if done["n"] % 10 == 0:
            print(f"  {done['n']}/{len(jobs)}", file=sys.stderr, flush=True)
        return d
    return await asyncio.gather(*(one(p, g) for p, g in jobs))


def main(argv):
    if not argv:
        sys.exit(__doc__)
    opt = lambda f, d: type(d)(argv[argv.index(f) + 1]) if f in argv else d
    n, tries, redo = opt("--jobs", 6), opt("--tries", 4), "--redo" in argv
    if argv[0] == "--page":
        d = asyncio.run(run([(argv[1], int(argv[2]))], 1, tries, redo))[0]
        for x in (d or {}).get("notes") or []:
            print(f"({x['mark']}) {x['text']}")
        return
    vol, spec = argv[0], argv[1]
    a, _, b = spec.partition("-")
    jobs = pages_for(vol, set(range(int(a), int(b or a) + 1)))
    todo = sum(1 for j in jobs if not cached(*j))
    print(f"{vol} ch. {spec}: {len(jobs)} pages with notes, {todo} to read", file=sys.stderr, flush=True)
    res = asyncio.run(run(jobs, n, tries, redo))
    print(f"read {sum(1 for d in res if d)}/{len(jobs)}; {sum(len(d['notes']) for d in res if d)} notes", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
