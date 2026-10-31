"""Check every Bible reference (commentary and footnotes) against what its context says, with a log
so a rerun only checks the references that are new or whose context changed.

  python3 ref_context.py <volume|book|all> ...            local stage, then the model for the rest
  python3 ref_context.py <volume|book|all> ... --local    local stage only (no calls)
  python3 ref_context.py ... --limit N                    at most N references sent to the model

Each reference is keyed by its page, its text and its context: fixing the text or the reference
gives a new key, and the next run checks it again; an unchanged one is never sent twice.
  local    the Latin quoted right against it is that verse (ref_check.fits_here): ok, no call
  first    the reference, the Vulgate text of the verse, the passage it stands in (for a note,
           the sentence that calls it too) and the verses it may have meant (a digit or Roman
           numeral misread, the verses around): ok, wrong (with the right one) or unsure
  second   a `wrong` or `unsure` goes to a stronger model (REF_SECOND), asked blind: its `ok` stands,
           a fix stands only when both give it, anything else is `unsure` (both readings kept)
The log is docs/ref_context.json; `wrong` and `unsure` are listed in docs/ref_context_review.json.
The Vulgate numbering is the one used (Psalms too). The calls go through agy, REF_MODEL picking
its model (default gemini-3.8-flash-low); REF_BACKEND=claude sends them to Claude (REF_MODEL
then defaults to sonnet); the second opinion defaults to gemini-4-argon-medium (opus on Claude).
"""
import asyncio
import hashlib
import json
import os
import re
import sys
from collections import Counter

import bible_refs as B
import footnotes as F
from paths import DOCS, pages, volumes_of
from ref_check import candidates, fits_here, quote_near

LOG = DOCS / "ref_context.json"
REVIEW = DOCS / "ref_context_review.json"
BACKEND = os.environ.get("REF_BACKEND", "agy")
MODEL = os.environ.get("REF_MODEL", "sonnet" if BACKEND == "claude" else "gemini-3.8-flash-low")
SECOND = os.environ.get("REF_SECOND", "opus" if BACKEND == "claude" else "gemini-4-argon-medium")
BATCH = int(os.environ.get("REF_BATCH", 15))

PROMPT = """You check Bible references in Dom Augustin Calmet's Commentaire littéral (1707-1716),
modernized French. Calmet cites the Latin Vulgate, with its numbering (Psalms too: Psaume 50 is
the Miserere). He often cites from memory, and the scans misread digits and Roman numerals
(IX. 28 read XIX. 8, VIII read XVI), so a reference can be wrong.

For each item: does the verse cited fit what the passage says or quotes there? Answer "ok" when it
fits, or plausibly does (a loose allusion is fine). Answer "wrong" only when it clearly does not
AND you know which verse is meant: give it in "fix", Vulgate numbering, written "Livre C:V" like
the reference (a candidate if one fits). Answer "unsure" when it does not seem to fit and you
cannot tell which verse is meant. "why": a few words (the words of the verse that decide).

Answer with a JSON array only: [{{"id": "...", "verdict": "ok|wrong|unsure", "fix": "", "why": "..."}}]

{items}"""


def key(where, src, context):
    return hashlib.md5(f"{where}\n{src}\n{context}".encode()).hexdigest()[:16]


def calls_of(d):
    """marker -> the 300 characters before its call ^{(x)} in the page (lemma included)."""
    out = {}
    for c in d.get("commentary") or []:
        for k in ("latin_quote", "french_translation", "french_commentary"):
            t = c.get(k) or ""
            for m in re.finditer(r"\^\{(\([^)]*\))\}", t):
                lead = (c.get("latin_quote") or "") + " … " if k == "french_commentary" else ""
                out.setdefault(m.group(1), lead + t[max(0, m.start() - 300):m.start()])
    return out


def collect(vol):
    """Every reference with a verse in a volume, as items to check."""
    for f in pages(vol):
        d = json.loads(f.read_text(encoding="utf-8"))
        where = f"{vol}/{f.stem}"
        texts = [(f"commentary[{i}].{k}", c.get(k), None) for i, c in enumerate(d.get("commentary") or [])
                 for k in ("french_commentary", "french_translation")]
        calls = calls_of(d)
        texts += [(f"footnotes[{i}].text", n.get("text"), calls.get(n.get("marker")))
                  for i, n in enumerate(d.get("footnotes") or []) if isinstance(n, dict)]
        for field, text, called in texts:
            if not isinstance(text, str):
                continue
            refs = B.find_refs(text)
            for r in refs:
                if not r.verses or B.exists(r) is None:
                    continue
                src = text[r.start:r.end].strip()
                context = text[max(0, r.start - 250):r.end + 150]
                if called:
                    context = f"[called after:] {called}\n[note:] {context}"
                yield dict(key=key(where, src, context), where=where, field=field, ref=r.render(), written=src,
                           context=context, quote=quote_near(text, r, refs), _ref=r)


def local(item):
    """'ok' when the Latin quoted right against the reference is that verse; None: ask the model."""
    r = item["_ref"]
    return "ok" if item["quote"] and B.exists(r) and fits_here(item["quote"], r) else None


def prompt_item(i, item):
    r = item["_ref"]
    vg = B.vulgate_text(r)[:220] if B.exists(r) else "(no such verse in the Vulgate)"
    cands = "; ".join(f"{k}: {t[:90]}" for k, t, _ in candidates(r, item["quote"])[:4])
    return (f"id {i}\nreference: {item['ref']} (printed: {item['written']})\nVulgate: {vg}\n"
            f"candidates: {cands or '-'}\npassage: {item['context']}\n")


def save(log):
    LOG.write_text(json.dumps(log, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def entry(it, a, model):
    return dict(where=it["where"], field=it["field"], ref=it["ref"], written=it["written"],
                verdict=a["verdict"], fix=a.get("fix") or "", why=a.get("why") or "", by=model)


def same(a, b):
    return " ".join(a.split()).rstrip(".") == " ".join(b.split()).rstrip(".")


def settle(first, a, model):
    """The first reading and the second (asked blind): a fix stands only when both give it."""
    second = dict(verdict=a["verdict"], fix=a.get("fix") or "", why=a.get("why") or "", by=model)
    if second["verdict"] == "ok":
        verdict, fix = "ok", ""
    elif first["verdict"] == second["verdict"] == "wrong" and same(first["fix"], second["fix"]):
        verdict, fix = "wrong", first["fix"]
    else:
        verdict, fix = "unsure", " / ".join(dict.fromkeys(x for x in (first["fix"], second["fix"]) if x))
    return {**first, "verdict": verdict, "fix": fix, "first": {k: first[k] for k in ("verdict", "fix", "why", "by")},
            "second": second, "why": second["why"] or first["why"]}


async def ask(todo, model, record, log):
    """Send the items in batches; record(item, answer) sets its log entry."""
    sem = asyncio.Semaphore(4)
    batches = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]

    async def one(b):
        prompt = PROMPT.format(items="\n".join(prompt_item(i, it) for i, it in enumerate(b)))
        ans = await (F.agy(prompt, sem, model) if BACKEND == "agy" else F.claude(prompt, model, sem))
        for i, it in enumerate(b):
            a = ans.get(str(i))
            if a and a.get("verdict") in ("ok", "wrong", "unsure"):
                log[it["key"]] = record(it, a)
        save(log)
    await asyncio.gather(*(one(b) for b in batches))


def main(argv):
    only_local = "--local" in argv
    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else None
    vols = volumes_of([a for a in argv if not a.startswith("--") and not a.isdigit()] or ["all"])
    log = json.loads(LOG.read_text(encoding="utf-8")) if LOG.exists() else {}
    stats, todo, seconds = Counter(), [], []
    for vol in vols:
        for it in collect(vol):
            stats["references"] += 1
            if it["key"] in log:
                stats["already checked"] += 1
                if log[it["key"]]["verdict"] != "ok" and "second" not in log[it["key"]]:
                    seconds.append(it)
                continue
            if local(it):
                log[it["key"]] = entry(it, dict(verdict="ok", why="the quotation is this verse"), "local")
                stats["ok by the quotation"] += 1
            else:
                todo.append(it)
    save(log)
    stats["to ask"] = len(todo)
    if not only_local and todo:
        todo = todo[:limit] if limit else todo
        asyncio.run(ask(todo, MODEL, lambda it, a: entry(it, a, MODEL), log))
        seconds += [it for it in todo if log.get(it["key"], {}).get("verdict") in ("wrong", "unsure")]
    if not only_local and seconds:
        stats["second opinions"] = len(seconds)
        asyncio.run(ask(seconds, SECOND, lambda it, a: settle(log[it["key"]], a, SECOND), log))
    review = sorted((v for v in log.values() if v["verdict"] != "ok" and v["where"].split("/")[0] in vols),
                    key=lambda v: (v["where"], v["field"]))
    REVIEW.write_text(json.dumps(review, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    stats.update(Counter(v["verdict"] for v in log.values() if v["where"].split("/")[0] in vols and v["by"] != "local"))
    print(", ".join(f"{k}: {n}" for k, n in stats.items()) + f"  -> {REVIEW.name}")


if __name__ == "__main__":
    main(sys.argv[1:])
