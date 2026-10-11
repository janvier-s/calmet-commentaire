"""Check every page break in Calmet's commentary: does the text run on correctly?

For each pair of consecutive pages, take the end of the last commentary block on one
page and the start of the first block on the next (what page_editor shows as
"prev"/"next"), then:
  - repetition: found by script (the end of one page reprinted at the top of the next);
  - missing text: judged by Claude, reading the two sides together.

Usage: python3 seam_check.py 01_genese [02_exode ...]   (foreground; results cached)
Writes STUDIUM/docs/seam_check.json, which audit_integrity.py turns into review items.
"""
import asyncio, hashlib, json, os, re, sys
from pathlib import Path

from paths import DOCS, SEAM_CACHE as CACHE, pages as volume_pages

OUT = DOCS / "seam_check.json"
MODEL = os.environ.get("CLAUDE_MODEL", "sonnet")
BATCH, PARALLEL = 40, 4

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
    """Words at the end of `tail` reprinted at the start of `head` (3+ words)."""
    tw, hw = norm_words(tail), norm_words(head)
    for k in range(min(len(tw), len(hw), 25), 2, -1):
        if tw[-k:] == hw[:k]:
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
        ca = [c for c in da.get("commentary") or [] if (c.get("french_commentary") or "").strip()]
        cb = [c for c in db.get("commentary") or [] if (c.get("french_commentary") or "").strip()]
        if not ca or not cb:
            continue
        first = cb[0]
        new_note = bool((first.get("latin_quote") or "").strip() or (first.get("french_translation") or "").strip())
        head = first["french_commentary"].strip()
        if new_note:
            head = " ".join(filter(None, [first.get("latin_quote"), first.get("french_translation"), head]))
        out.append(dict(book=book, before_page=a, page=b, new_note=new_note,
                        tail=ca[-1]["french_commentary"].strip()[-220:], head=head[:220]))
    return out


async def ask(batch, sem):
    items = "\n".join(f'#{i}: NEW_NOTE={"yes" if s["new_note"] else "no"}\nBEFORE: …{s["tail"]}\nAFTER: {s["head"]}…\n'
                      for i, s in batch)
    async with sem:
        proc = await asyncio.create_subprocess_exec(
            "claude", "-p", "--model", MODEL, "--tools", "", "--strict-mcp-config", "--disable-slash-commands",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await proc.communicate(PROMPT.format(items=items).encode())
    text = out.decode().strip()
    text = re.sub(r"^```(?:json)?|```$", "", text).strip()
    try:
        res = json.loads(text)
        return {int(str(r["id"]).lstrip("#")): r for r in res}
    except Exception:
        print("  batch failed:", (err or out).decode()[:150], file=sys.stderr)
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


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
