"""The agent pass over Good's text: real-word and context errors rules cannot see ("As commencement", "ov la Terre").

    python3 good_spell_agent.py prepare 01_genese OUT.json [--origin both_scans,normalized_differs] [--limit N]
        -> OUT.json: [{"id": change id, "text": the cleaned text}] for an agent (the prompt is PROMPT below)
    python3 good_spell_agent.py import 01_genese ANSWERS.json [--dry-run]
        <- ANSWERS.json: [{"id": ..., "changes": [{"before": "As", "after": "Au", "ctx": "word before"}]}]
        -> data/<vol>/good_normalized.json: the changes become `agent` records, listed in the merge view with
           undo like every other automatic change. Each is checked first and refused (and listed) unless:
           its `before` words are in the text, in order, after `ctx`; the _italic_ marks and ^{(a)} call markers
           are the same before and after; no more than 4 words change, and only letters (no new digits, no marks).
Nothing is applied silently: the answers are only stored as records, shown in the merge view, one undo each.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import good_normalized as gn
from paths import DATA

PROMPT = """You proofread French text OCR-read from a printed 18th-century book (Calmet's Bible commentary), already
modernized. Find only clear errors of reading: a word read wrong that is still a real word ("As commencement" for
"Au commencement"), a letter or word garbled by OCR ("ov la Terre" for "ou la Terre"), a repeated or missing small word.
Do NOT change style, spelling choices, names, Latin, numbers or punctuation. Keep `_italic_` marks and `^{(a)}` markers.
For each text, answer {"id": ..., "changes": [{"before": "<the words as they are>", "after": "<corrected>",
"ctx": "<the one word before them, or empty>"}]} with at most 4 words per change; no change: an empty list."""


def prepare(vol, out, origins, limit):
    doc = gn.load_json(Path(DATA) / vol / "good_units.json", None)
    store = gn.load_json(gn.store_path(DATA, vol), {}).get("changes", {})
    rows = []
    for u in doc["units"]:
        for c in u.get("changes") or []:
            text = gn.source(c)
            if text and c.get("origin") in origins:
                e = store.get(c["id"])
                rows.append({"id": c["id"], "text": gn.cleaned(text, e)[0] if e and e["src"] == gn.src_hash(text) else text})
    rows = rows[:limit] if limit else rows
    Path(out).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(rows)


def check(text, ch):
    """None when the change is sound for `text` (words list), else why not."""
    b, a, ctx = ch.get("before", "").split(), ch.get("after", "").split(), ch.get("ctx", "").split()
    if not b or len(b) > 4 or len(a) > 4 or b == a:
        return "size"
    if re.findall(r"_", " ".join(b)) != re.findall(r"_", " ".join(a)) or re.findall(r"\^\{\(.*?\)\}", " ".join(b)) != re.findall(r"\^\{\(.*?\)\}", " ".join(a)):
        return "marks"
    if re.findall(r"\d", " ".join(a)) != re.findall(r"\d", " ".join(b)):
        return "digits"
    words = text.split()
    n = len(ctx)
    for i in range(n, len(words) - len(b) + 1):
        if words[i:i + len(b)] == b and words[i - n:i] == ctx:
            return None
    return "not found"


def import_(vol, answers, dry):
    p = gn.store_path(DATA, vol)
    store = gn.load_json(p, {"vol": vol, "changes": {}})
    doc = gn.load_json(Path(DATA) / vol / "good_units.json", None)
    texts = {c["id"]: gn.source(c) for u in doc["units"] for c in u.get("changes") or [] if gn.source(c)}
    ok = bad = 0
    for ans in answers:
        cid = ans["id"]
        if cid not in texts:
            continue
        e = store["changes"].setdefault(cid, {"src": gn.src_hash(texts[cid]), "records": []})
        if e["src"] != gn.src_hash(texts[cid]):
            continue
        cur = gn.cleaned(texts[cid], dict(e, agent=None))[0]
        agent = []
        for ch in ans.get("changes") or []:
            why = check(cur, ch)
            if why:
                bad += 1
                print(f"refused ({why}): {cid} {ch.get('before')!r} -> {ch.get('after')!r}", file=sys.stderr)
                continue
            agent.append({"before": ch["before"], "after": ch["after"], "ctx": ch.get("ctx", ""), "rule": "agent"})
            ok += 1
            print(f"{ch.get('ctx', '')} [{ch['before']} -> {ch['after']}]")
        if agent:
            e["agent"] = agent
        elif not e["records"]:
            store["changes"].pop(cid)
    if not dry:
        p.write_text(json.dumps(store, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{ok} agent changes {'(dry run) ' if dry else 'stored '}, {bad} refused")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("prepare")
    a.add_argument("vol")
    a.add_argument("out")
    a.add_argument("--origin", default="both_scans,normalized_differs,only_good")
    a.add_argument("--limit", type=int, default=0)
    b = sub.add_parser("import")
    b.add_argument("vol")
    b.add_argument("answers")
    b.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "prepare":
        print(prepare(args.vol, args.out, set(args.origin.split(",")), args.limit), "texts;", "prompt:\n" + PROMPT)
    else:
        import_(args.vol, json.loads(Path(args.answers).read_text(encoding="utf-8")), args.dry_run)


if __name__ == "__main__":
    main()
