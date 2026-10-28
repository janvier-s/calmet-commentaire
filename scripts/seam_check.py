"""Check every page break in Calmet's commentary: does the text run on correctly?

For each pair of consecutive pages, take the end of the last commentary block on one
page and the start of the first block on the next (what page_editor shows as
"prev"/"next"), then:
  - repetition: found by script (the end of one page reprinted at the top of the next);
  - missing text: judged by a model, reading the two sides together (agy by default;
    SEAM_BACKEND=claude for Claude Code, AGY_MODEL to pick agy's model, AGY_EFFORT=low
    for a faster pass).

Usage: python3 seam_check.py 01_genese [02_exode ...]   (foreground; results cached)
Writes STUDIUM/docs/seam_check.json, which audit_integrity.py turns into review items.
"""
import asyncio, hashlib, json, os, re, sys, tempfile, time
from pathlib import Path

from paths import DOCS, SEAM_CACHE as CACHE, pages as volume_pages

OUT = DOCS / "seam_check.json"
BACKEND = os.environ.get("SEAM_BACKEND", "agy")
MODEL = os.environ.get("CLAUDE_MODEL", "sonnet")
AGY_MODEL = os.environ.get("AGY_MODEL", "")
AGY_EFFORT = os.environ.get("AGY_EFFORT", "")
BATCH, PARALLEL = 40, 4
LIMIT_HIT = False
AGY_PLAIN = ("Answer directly, with text only: do not use any tool, do not run commands, "
             "do not read or write files.\n\n")

PROMPT = """You are proofreading a transcription of an 18th-century French Bible commentary (Dom Calmet).
Each item below is a PAGE BREAK: BEFORE is the end of one printed page, AFTER is the start of the next.
In the printed book the text runs straight on across the break (a word may be hyphenated across it).
Transcription errors at breaks: a whole printed LINE (roughly 6-12 words) is missing, or text is repeated.
NEW_NOTE=yes means the next page opens a new lemma (a new Latin quotation), so BEFORE should end a sentence.

For each item decide:
- "ok": the text plausibly continues (or BEFORE ends a sentence and a new note begins). Hyphenated words split across the break, and a stray full stop added at the break, are ok.
- "missing": words are clearly missing: the sentence cannot join grammatically or logically.
- "repeat": AFTER repeats words already at the end of BEFORE (beyond a split word).
- "unclear": cannot tell.
Be conservative: only say "missing" when the join is clearly broken.

Output ONLY a JSON array, one object per item, same order: {{"id": <id>, "v": "ok|missing|repeat|unclear", "why": "<max 12 words, only if not ok>"}}

ITEMS:
{items}"""


def norm_words(s):
    return re.findall(r"[a-zà-ÿœæç]+", (s or "").lower().replace("ſ", "s"))


def repetition(tail, head):
    """Words at the end of `tail` reprinted at the start of `head`: 3+ words, or one or two when the page
    breaks mid-sentence and they are longer than a particle (un homme ‖ homme dont)."""
    tw, hw = norm_words(tail), norm_words(head)
    for k in range(min(len(tw), len(hw), 25), 2, -1):
        if tw[-k:] == hw[:k]:
            return " ".join(hw[:k])
    mid_sentence = not re.search(r"[.!?;:»]\W*$", re.sub(r"\^\{\([a-z]\)\}", "", tail or "").rstrip(" _*"))
    for k in (2, 1):
        if mid_sentence and len(tw) >= k and len(hw) >= k and tw[-k:] == hw[:k] and len("".join(hw[:k])) >= 5:
            return " ".join(hw[:k])
    # the whole last line repeated a little further into the next page
    if len(tw) >= 6:
        last = " ".join(tw[-6:])
        if last in " ".join(hw[:40]):
            return last
    return None


def seams(book):
    pages = []
    for p in volume_pages(book):
        try:
            pages.append((p.stem, json.loads(p.read_text(encoding="utf-8"))))
        except json.JSONDecodeError:
            pages.append((p.stem, None))
    out = []
    for (a, da), (b, db) in zip(pages, pages[1:]):
        if not da or not db or int(b[5:9]) - int(a[5:9]) != 1:
            continue
        # The text on each side of the break, whatever field it is in: a page often ends
        # on a lemma (Latin + start of its translation) whose comment is on the next page.
        def text(c):
            return " ".join(filter(None, ((c.get(k) or "").strip() for k in
                                          ("latin_quote", "french_translation", "french_commentary"))))
        ca = [c for c in da.get("commentary") or [] if text(c)]
        cb = [c for c in db.get("commentary") or [] if text(c)]
        if not ca or not cb:
            continue
        first = cb[0]
        new_note = bool((first.get("latin_quote") or "").strip())
        out.append(dict(book=book, before_page=a, page=b, new_note=new_note,
                        tail=text(ca[-1])[-220:], head=text(first)[:220]))
    return out


async def ask(batch, sem):
    global LIMIT_HIT
    items = "\n".join(f'#{i}: NEW_NOTE={"yes" if s["new_note"] else "no"}\nBEFORE: …{s["tail"]}\nAFTER: {s["head"]}…\n'
                      for i, s in batch)
    prompt = PROMPT.format(items=items)
    async with sem:
        if LIMIT_HIT:
            return {}
        if BACKEND == "agy":
            empty = Path(tempfile.gettempdir()) / "seam_check_agy"
            empty.mkdir(exist_ok=True)
            # agy names its log by the second; four calls starting together collide on that file
            log = empty / f"agy-{os.getpid()}-{time.time_ns()}.log"
            args = ["agy", "-p", AGY_PLAIN + prompt, "--print-timeout", "600s", "--log-file", str(log),
                    "--disable-slash-commands", "--output-format", "json"]
            args += ["--model", AGY_MODEL] if AGY_MODEL else []
            args += ["--effort", AGY_EFFORT] if AGY_EFFORT else []
            proc = await asyncio.create_subprocess_exec(*args, cwd=str(empty),
                                                        stdout=asyncio.subprocess.PIPE,
                                                        stderr=asyncio.subprocess.PIPE)
            try:  # agy does not always keep to --print-timeout
                out, err = await asyncio.wait_for(proc.communicate(), 660)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                out, err = b"", b"timed out"
            try:
                d = json.loads(out.decode())
            except json.JSONDecodeError:
                d = {"status": "ERROR", "response": (err or out).decode()[:300]}
            text = str(d.get("response") or "")
            if d.get("status") != "SUCCESS":
                print("  batch failed:", text[:150] or err.decode()[:150], file=sys.stderr)
                if re.search(r"quota|limit|exhausted|429", text + err.decode(), re.I):
                    LIMIT_HIT = True
                return {}
        else:
            proc = await asyncio.create_subprocess_exec(
                "claude", "-p", "--model", MODEL, "--tools", "", "--strict-mcp-config", "--disable-slash-commands",
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            out, err = await proc.communicate(prompt.encode())
            text = out.decode().strip()
    text = re.sub(r"^```(?:json)?|```$", "", text).strip()
    try:
        res = json.loads(text)
    except Exception:
        m = re.search(r"\[\s*\{.*\}\s*\]", text, re.S)  # a little prose around the array
        try:
            res = json.loads(m.group()) if m else None
        except Exception:
            res = None
    if not isinstance(res, list):
        print("  batch failed:", text[:150], file=sys.stderr)
        return {}
    try:
        return {int(str(r["id"]).lstrip("#")): r for r in res}
    except Exception:
        print("  batch failed: bad item shape:", text[:150], file=sys.stderr)
        return {}


async def main(books):
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    results = json.loads(OUT.read_text()) if OUT.exists() else {}
    for book in books:
        ss = seams(book)
        todo = []
        for i, s in enumerate(ss):
            s["key"] = hashlib.md5(f"{s['tail']}||{s['head']}".encode()).hexdigest()
            s["repeat"] = repetition(s["tail"], s["head"])
            if s["key"] not in cache:
                todo.append((i, s))
        print(f"{book}: {len(ss)} page breaks, {len(todo)} to read", flush=True)
        sem = asyncio.Semaphore(PARALLEL)
        batches = [todo[j:j + BATCH] for j in range(0, len(todo), BATCH)]
        answers = await asyncio.gather(*(ask(b, sem) for b in batches))
        for b, ans in zip(batches, answers):
            for i, s in b:
                if i in ans:
                    cache[s["key"]] = {"v": ans[i].get("v"), "why": ans[i].get("why", "")}
        CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1))
        flagged, unread = [], 0
        for s in ss:
            c = cache.get(s["key"], {"v": "unread"})
            v = "repeat" if s["repeat"] else c["v"]
            if v == "unread":
                unread += 1
            elif v != "ok":
                flagged.append(dict(page=s["page"], before_page=s["before_page"], verdict=v,
                                    why=f"repeated: “{s['repeat']}”" if s["repeat"] else c.get("why", ""),
                                    tail=s["tail"][-90:], head=s["head"][:90]))
        results[book] = dict(checked=len(ss) - unread, unread=unread, flagged=flagged)
        from collections import Counter
        print(f"  {dict(Counter(f['verdict'] for f in flagged))}" + (f", {unread} unread" if unread else ""), flush=True)
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1))
    print("wrote", OUT)
    unread_books = {b: r["unread"] for b, r in results.items() if r.get("unread")}
    if unread_books:
        print(f"WARNING: {sum(unread_books.values())} page breaks still unread in {len(unread_books)} book(s) — "
              f"the model calls failed (quota?); rerun: "
              + " ".join(f"{b} ({n})" for b, n in unread_books.items()), file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
