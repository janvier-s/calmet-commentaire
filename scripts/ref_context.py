"""Check every Bible reference (commentary and footnotes) against what its context says, with a log
so a rerun only checks the references that are new or whose context changed.

  python3 ref_context.py <volume|book|all> ...            local stage, then the model for the rest
  python3 ref_context.py <volume|book|all> ... --local    local stage only (no calls)
  python3 ref_context.py ... --limit N                    at most N references sent to the model
  python3 ref_context.py <volume|book|all> ... --third    a third, richer reading of what is still `unsure`
                                                          (--limit N); then --apply writes in what it settled
  python3 ref_context.py <volume|book|all> ... --apply    write in the fixes both models gave (no calls);
                                                          --arbitrate also settles the `unsure` ones the
                                                          words the models quoted decide

Each reference is keyed by its page, its text and its context: fixing the text or the reference
gives a new key, and the next run checks it again; an unchanged one is never sent twice.
  local    the Latin quoted right against it is that verse (ref_check.fits_here): ok, no call
  first    the reference, the Vulgate text of the verse, the passage it stands in (for a note,
           the sentence that calls it too) and the verses it may have meant (a digit or Roman
           numeral misread, the verses around): ok, wrong (with the right one) or unsure
  second   a `wrong` or `unsure` goes to a stronger model (REF_SECOND), asked blind: its `ok` stands,
           a fix stands only when both give it, anything else is `unsure` (both readings kept)
The log is docs/ref_context.json; `wrong` and `unsure` are listed in docs/ref_context_review.json.
--apply writes a fix in only where the field has the reference once, with a book name in front of it
(Calmet's "Psaume"/"Psaumes" is kept as printed; a bare "; 88:14" takes the book of the reference it follows);
an applied entry is marked, so a rerun does not ask about the text it wrote in. When agy's quota runs out
the run goes on with Claude; the rest go to the review queue (review_proposals.py:
`ref_context` with the readings the models gave, `ref_unsure` with none).
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
from footnotes import latin_words
from ref_check import candidates, fits_here, quote_near

LOG = DOCS / "ref_context.json"
REVIEW = DOCS / "ref_context_review.json"
BACKEND = os.environ.get("REF_BACKEND", "agy")
USE = {"backend": BACKEND}  # the backend in use: agy falls back to claude when its quota is out
MODELS = {"first": {"agy": "gemini-3.8-flash-low", "claude": "sonnet"},
          "second": {"agy": "gemini-4-argon-medium", "claude": "opus"},
          "third": {"agy": "gemini-4-argon-medium", "claude": "sonnet"},
          "third_hard": {"agy": "gemini-4-argon-medium", "claude": "opus"}}


def model_for(role, backend):
    """REF_MODEL / REF_SECOND pick the model of the backend the run started with."""
    env = os.environ.get({"first": "REF_MODEL", "second": "REF_SECOND"}.get(role, "REF_THIRD"))
    return env if env and backend == BACKEND else MODELS[role][backend]


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


async def ask(todo, role, make, log, build=None):
    """Send the items in batches; make(item, answer, model) sets its log entry. When agy's quota runs
    out the rest of the run goes to Claude (sonnet, opus for the second opinion)."""
    sem = asyncio.Semaphore(4)
    batches = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]

    async def one(b):
        prompt = (build or (lambda b: PROMPT.format(items="\n".join(prompt_item(i, it) for i, it in enumerate(b)))))(b)
        ans, model = {}, None
        for backend in dict.fromkeys([USE["backend"], "claude"]):
            model = model_for(role, backend)
            ans = await (F.agy(prompt, sem, model) if backend == "agy" else F.claude(prompt, model, sem))
            if ans or backend != "agy" or not F.LIMIT_HIT:
                break
            if USE["backend"] == "agy":
                print("  agy is out of quota: the rest of the run goes to Claude", file=sys.stderr, flush=True)
                USE["backend"] = "claude"
            F.LIMIT_HIT = False  # agy's limit is not Claude's
        for i, it in enumerate(b):
            a = ans.get(str(i))
            if a and a.get("verdict") in ("ok", "wrong", "unsure"):
                log[it["key"]] = make(it, a, model)
        save(log)
    await asyncio.gather(*(one(b) for b in batches))


BOOKREF = re.compile(r"^((?:\d+ )?[A-ZÀ-Ý][^\d:;,]*?)\s+(\d+:\S.*)$")
TAIL = re.compile(r"\d+:\S.*$")


def rewrite(written, fix, ref=""):
    new = _rewrite(written, fix, ref)
    stop = re.search(r"[.,;:]+$", written)  # the punctuation the printed text ended on stays
    return new + stop.group(0) if new and stop and not new.endswith(stop.group(0)) else new


def _rewrite(written, fix, ref=""):
    """The text to put where `written` stands for the reference `fix`. Calmet's "Psaume"/"Psaumes" is kept.
    `written` with no book name in front ("; 88:14", "et 32:3") has the book of `ref` (the reference as
    the script read it): only the chapter and verse change, or the book is named when `fix` is another."""
    f = BOOKREF.match(fix or "")
    if not f:
        return None
    w = BOOKREF.match(written)
    if w:
        same = w.group(1) in (f.group(1), f.group(1)[:-1], f.group(1) + "s")
        return f"{w.group(1)} {f.group(2)}" if same else fix
    head = TAIL.sub("", written)
    if head == written:
        return None
    r = BOOKREF.match(ref or "")
    return head + (f.group(2) if r and r.group(1) == f.group(1) else fix)


def verse_fit(words, ref_text):
    """How much of `words` (Latin words the models quoted) the verse `ref_text` has, 0..1."""
    rs = B.find_refs(ref_text)
    q = latin_words(words)
    return len(q & latin_words(B.vulgate_text(rs[0]))) / len(q) if rs and len(q) >= 4 and B.exists(rs[0]) else 0


def arbitrate(v):
    """An `unsure` entry whose models gave different fixes (or one gave none): the one whose Vulgate verse has
    the words they quoted, when it clearly does (0.6 and more, 0.3 over the other readings and the printed
    reference). Returns the fix or None."""
    third = v.get("third") or {}
    cands = list(dict.fromkeys(x for x in (v["first"].get("fix"), v["second"].get("fix"), third.get("fix")) if x))
    if v["verdict"] != "unsure" or not cands:
        return None
    words = v["first"]["why"] + " " + v["second"]["why"] + " " + third.get("why", "")
    scores = sorted(((verse_fit(words, c), c) for c in cands), reverse=True)
    best, rest = scores[0], [s for s, _ in scores[1:]] + [verse_fit(words, v["written"])]
    return best[1] if best[0] >= 0.6 and best[0] - max(rest) >= 0.3 else None


def settled(v):
    """The (section, index, field, new text) a `wrong` entry both models agree on (or the quoted words
    decide) can be written with."""
    m = re.fullmatch(r"(\w+)\[(\d+)\]\.(\w+)", v["field"])
    new = rewrite(v["written"], v["fix"], v["ref"])
    ok = v["verdict"] == "wrong" and v["fix"] and (v["fix"] == v["second"].get("fix") or v.get("arbiter"))
    return (m.group(1), int(m.group(2)), m.group(3), new) if ok and new and m else None


def write_review(log, vols):
    open_ = {(v["where"], v["field"], v["written"]): v for v in log.values() if v["verdict"] != "ok"
             and not v.get("applied") and v["where"].split("/")[0] in vols}  # one per reference
    review = sorted(open_.values(), key=lambda v: (v["where"], v["field"]))
    REVIEW.write_text(json.dumps(review, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return review


def apply_settled(log, vols, decide=False):
    """Write in the fixes both models gave, where the reference is in its field once; mark them `applied`
    (the new text is not asked about again). An `unsure` the quoted words decide is settled first."""
    from paths import DATA
    by_page, done, left, arbitrated = {}, 0, Counter(), 0
    for v in log.values():
        if decide and v["where"].split("/")[0] in vols and "first" in v and (fix := arbitrate(v)):
            v.update(verdict="wrong", fix=fix, arbiter="the words they quoted are in this verse")
            arbitrated += 1
    for v in log.values():
        vol, stem = v["where"].split("/")
        if vol in vols and not v.get("applied") and (st := settled(v)):
            by_page.setdefault((vol, stem), []).append((v, st))
    for (vol, stem), todo in sorted(by_page.items()):
        path = DATA / vol / "normalized" / f"{stem}.json"
        raw = path.read_text(encoding="utf-8")
        d, changed = json.loads(raw), False
        for v, (sec, i, name, new) in todo:
            e = (d.get(sec) or [])
            text = e[i].get(name) if i < len(e) else None
            if isinstance(text, str) and v["written"] not in text and new in text:  # done by an earlier run
                v["applied"] = new
            elif not isinstance(text, str) or text.count(v["written"]) != 1:
                left["not once in the field"] += 1
            else:
                e[i][name] = text.replace(v["written"], new)
                v["applied"], changed, done = new, True, done + 1
        if changed:
            path.write_text(json.dumps(d, ensure_ascii=False, indent=2) + ("\n" if raw.endswith("\n") else ""), encoding="utf-8")
    save(log)
    write_review(log, vols)
    print(f"{done} references set right ({arbitrated} of them settled by the quoted words)"
          + "".join(f", {n} left ({k})" for k, n in left.items()))


PROMPT3 = """You settle Bible references in Dom Augustin Calmet's Commentaire littéral (1707-1716), modernized
French. Calmet cites the Latin Vulgate, with its numbering (Psalms too). The scans misread digits, and he
cites from memory. Two readers could not settle each item below. You have more than they had: a long passage
and the Vulgate text of the printed verse, of the verses they proposed and of those round the printed one.

Answer "ok" when the printed reference is right as printed (a loose allusion, or Calmet's own numbering,
such as the Psalms' title verses). Answer "wrong" with the verse meant in "fix" ("Livre C:V", Vulgate
numbering) only when a verse's text clearly says what the passage quotes or discusses; prefer one of the
proposed readings when it does. Answer "unsure" when the texts do not decide. "why": a few words.

Answer with a JSON array only: [{{"id": "...", "verdict": "ok|wrong|unsure", "fix": "", "why": "..."}}]

{items}"""


def wide(v):
    """About 800 characters of the field round the printed reference (a note: and the place it is called from)."""
    from paths import DATA
    vol, stem = v["where"].split("/")
    d = json.loads((DATA / vol / "normalized" / f"{stem}.json").read_text(encoding="utf-8"))
    sec, i, name = re.fullmatch(r"(\w+)\[(\d+)\]\.(\w+)", v["field"]).groups()
    e = d[sec][int(i)]
    text, k = e[name], e[name].find(v["written"])
    out = text[max(0, k - 500):k + len(v["written"]) + 300]
    called = calls_of(d).get(e.get("marker")) if sec == "footnotes" else None
    return (f"[called after:] {called}\n[note:] " if called else "") + out


def prompt3(b):
    from ref_check import neighbours
    out = []
    for i, v in enumerate(b):
        r = (B.find_refs(v["ref"]) or [None])[0]
        near = [x.render() + ": " + B.vulgate_text(x)[:110] for x in neighbours(r) if abs(x.verses[0] - r.verses[0]) == 1] if r else []
        reads = [f"{x['by']}: {x.get('fix') or '-'} ({x['why'][:90]})" for x in (v["first"], v["second"])]
        fixes = list(dict.fromkeys(x["fix"] for x in (v["first"], v["second"]) if x.get("fix")))
        texts = [f"{f}: {B.vulgate_text(m[0])[:200]}" for f in fixes if (m := B.find_refs(f))]
        out.append(f"id {i}\nprinted: {v['written']} (read as {v['ref']}): "
                   f"{B.vulgate_text(r)[:200] if r and B.exists(r) else '(no such verse)'}\nreaders: {' | '.join(reads)}\n"
                   f"proposed verses: {' || '.join(texts) or '-'}\nround the printed one: {' || '.join(near) or '-'}\n"
                   f"passage: {wide(v)}\n")
    return PROMPT3.format(items="\n".join(out))


def settle3(v, a, model):
    """The third reading: `ok` clears the item; a fix stands when it is one an earlier reader gave."""
    third = dict(verdict=a["verdict"], fix=a.get("fix") or "", why=a.get("why") or "", by=model)
    v = {**v, "third": third}
    if third["verdict"] == "ok":
        v.update(verdict="ok", fix="")
    elif third["verdict"] == "wrong" and any(x.get("fix") and same(x["fix"], third["fix"]) for x in (v["first"], v["second"])):
        v.update(verdict="wrong", fix=third["fix"], arbiter="a third reader agrees with an earlier one")
    return v


def follow_applied(log):
    """An open entry whose printed text was set right elsewhere to one fix, a reading it has: the same fix."""
    fixes = {}
    for v in log.values():
        if v.get("applied"):
            fixes.setdefault(v["written"], set()).add(v["fix"])
    n = 0
    for v in log.values():
        if v["verdict"] == "unsure" and "first" in v and not v.get("applied") and len(fixes.get(v["written"], ())) == 1:
            (fix,) = fixes[v["written"]]
            if any(x.get("fix") and same(x["fix"], fix) for x in (v["first"], v["second"])):
                v.update(verdict="wrong", fix=fix, arbiter="the same reference was set right so elsewhere")
                n += 1
    return n


def third_pass(log, vols, limit=None):
    stats = Counter()
    stats["settled like the same reference elsewhere"] = follow_applied(log)
    todo = [(k, v) for k, v in log.items() if v["verdict"] == "unsure" and "first" in v and "third" not in v
            and not v.get("applied") and v["where"].split("/")[0] in vols]
    seen, items = set(), []
    for k, v in todo:
        if (v["where"], v["field"], v["written"]) not in seen:
            seen.add((v["where"], v["field"], v["written"]))
            items.append(dict(v, key=k))
    items = items[:limit] if limit else items
    hard = [v for v in items if not v["fix"] or len({x.get("fix") for x in (v["first"], v["second"]) if x.get("fix")}) != 1]
    easy = [v for v in items if v not in hard]
    stats["asked"] = len(items)
    for role, group in (("third", easy), ("third_hard", hard)):
        if group:
            asyncio.run(ask(group, role, lambda it, a, m: settle3(log[it["key"]], a, m), log, prompt3))
    save(log)
    stats.update(Counter(log[v["key"]].get("third", {}).get("verdict", "no answer") for v in items))
    stats["now settled"] = sum(1 for v in items if log[v["key"]]["verdict"] != "unsure")
    print(", ".join(f"{k}: {n}" for k, n in stats.items()))


def main(argv):
    if "--third" in argv:
        vols = volumes_of([a for a in argv if not a.startswith("--") and not a.isdigit()] or ["all"])
        limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else None
        log = json.loads(LOG.read_text(encoding="utf-8"))
        third_pass(log, vols, limit)
        return write_review(log, vols) and None
    if "--apply" in argv:
        vols = volumes_of([a for a in argv if not a.startswith("--")] or ["all"])
        return apply_settled(json.loads(LOG.read_text(encoding="utf-8")), vols, "--arbitrate" in argv)
    only_local = "--local" in argv
    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else None
    vols = volumes_of([a for a in argv if not a.startswith("--") and not a.isdigit()] or ["all"])
    log = json.loads(LOG.read_text(encoding="utf-8")) if LOG.exists() else {}
    applied = {(v["where"], v["field"], v["applied"]) for v in log.values() if v.get("applied")}
    fixed_pages = {v["where"] for v in log.values() if v.get("applied")}
    loose = {}  # on a page a fix touched, a reference whose own text is unchanged keeps its verdict
    for k, v in log.items():
        if v["where"] in fixed_pages and not v.get("applied"):
            loose.setdefault((v["where"], v["field"], v["written"]), k)
    stats, todo, seconds = Counter(), [], []
    for vol in vols:
        for it in collect(vol):
            stats["references"] += 1
            if it["key"] in log:
                stats["already checked"] += 1
                if log[it["key"]]["verdict"] != "ok" and "second" not in log[it["key"]]:
                    seconds.append(it)
                continue
            if (it["where"], it["field"], it["written"]) in applied:
                stats["already set right"] += 1  # the text a fix wrote in: not asked again
                continue
            if (it["where"], it["field"], it["written"]) in loose:  # only the words round it moved
                log[it["key"]] = log.pop(loose[(it["where"], it["field"], it["written"])])
                stats["kept: only the words round it moved"] += 1
                if log[it["key"]]["verdict"] != "ok" and "second" not in log[it["key"]]:
                    seconds.append(it)
            elif local(it):
                log[it["key"]] = entry(it, dict(verdict="ok", why="the quotation is this verse"), "local")
                stats["ok by the quotation"] += 1
            else:
                todo.append(it)
    save(log)
    stats["to ask"] = len(todo)
    if not only_local and todo:
        todo = todo[:limit] if limit else todo
        asyncio.run(ask(todo, "first", lambda it, a, m: entry(it, a, m), log))
        seconds += [it for it in todo if log.get(it["key"], {}).get("verdict") in ("wrong", "unsure")]
    if not only_local and seconds:
        stats["second opinions"] = len(seconds)
        asyncio.run(ask(seconds, "second", lambda it, a, m: settle(log[it["key"]], a, m), log))
    write_review(log, vols)
    stats.update(Counter(v["verdict"] for v in log.values() if v["where"].split("/")[0] in vols and v["by"] != "local"))
    print(", ".join(f"{k}: {n}" for k, n in stats.items()) + f"  -> {REVIEW.name}")


if __name__ == "__main__":
    main(sys.argv[1:])
