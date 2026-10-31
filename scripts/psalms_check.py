"""Check the Psalms verses against the Vulgate text (read-only).

Calmet numbers the Psalms his own way (title unnumbered, verse 1 = first line of text,
and some verses split differently), so verse numbers can't be compared with the
Vulgate's. Instead each transcribed verse's Latin is matched to the Vulgate text, which
tells which psalm it belongs to and which Vulgate text it covers. From that:

  - wrong_psalm:  verse filed under another psalm (usually a misread "PSEAUME N." title)
  - missing:      Vulgate text that no transcribed verse covers (line lost: type it from the scan)
  - missing_title: the psalm's title (Vulgate verse 1) isn't among the verses (Calmet number 0)
  - repeated:     the same text transcribed twice (typically across a page break)
  - number:       verse number out of step with its neighbours (misread number)
  - unmatched:    transcribed Latin that matches no verse nearby

Usage: python3 psalms_check.py [volume]   (default 21a_psaumes) -> docs/psalms_check.json
"""
import json
import re
import sys
from collections import defaultdict


from export import chapter_of
from fill_vulgate_verses import words
from paths import DOCS, VUL, load, pages


VULGATE = {c["chapter"]: {v["verse"]: words(v["text"]) for v in c["verses"]}
           for c in json.loads((VUL / "psalms.json").read_text())["chapters"]}


def sim(lw, vw):
    """Share of a transcribed verse's words found in a Vulgate verse."""
    vs = set(vw)
    return sum(w in vs for w in lw) / max(len(lw), 1)


def align(rs, ps):
    """Assign each transcribed verse of a psalm to a Vulgate verse, in order.

    Calmet may split one Vulgate verse in two, so consecutive verses can share a Vulgate
    verse; a refrain later in the psalm is matched later, not taken for a repeat.
    """
    vn = sorted(VULGATE[ps])
    m, n = len(rs), len(vn)
    # a tie (a refrain: 117:10 and 117:11 share their second half) goes to the Vulgate verse whose
    # own words the transcription covers best
    S = [[sim(r["words"], VULGATE[ps][v]) + 0.01 * sim(VULGATE[ps][v], r["words"]) if len(r["words"]) >= 3 else 0
          for v in vn] for r in rs]
    # best[i][j]: best total for verses i.. when the previous one sat at Vulgate index >= j
    NONE = -1
    best = [[0.0] * (n + 1) for _ in range(m + 1)]
    choice = [[None] * (n + 1) for _ in range(m + 1)]
    for i in range(m - 1, -1, -1):
        for j in range(n, -1, -1):
            opt, ch = best[i + 1][j], NONE  # leave verse i unmatched
            for k in range(j, n):
                if S[i][k] >= 0.5 and S[i][k] + best[i + 1][k] > opt:
                    opt, ch = S[i][k] + best[i + 1][k], k
            best[i][j], choice[i][j] = opt, ch
    j = 0
    for i, r in enumerate(rs):
        k = choice[i][j]
        if k is None or k == NONE:
            r["vulgate"], r["score"] = None, max(S[i], default=0)
        else:
            r["vulgate"], r["score"] = vn[k], round(S[i][k], 2)
            j = k


def check(volume):
    rows, cur = [], None
    for p in pages(volume):
        try:
            d = load(p)
        except json.JSONDecodeError:
            continue
        opens = chapter_of(d)
        # as in export.py: on a page that opens a psalm, leading verses that continue the
        # previous psalm's numbering still belong to it
        last = max((r["number"] for r in rows if r["filed"] == cur and isinstance(r["number"], int)), default=0)
        carrying = bool(opens and cur and opens != cur and last)
        for i, v in enumerate(d.get("verses") or []):
            n = v.get("verse_number")
            if carrying and not (isinstance(n, int) and n >= last):
                carrying, cur = False, opens
            if carrying:
                last = n
            elif opens:
                cur = opens
            rows.append(dict(page=int(p.stem[5:9]), index=i, number=n, filed=cur,
                             latin=(v.get("latin") or "")[:70], words=words(v.get("latin"))))
        if opens:
            cur = opens  # also when the page has no verses, or only carried-over ones
    issues = []
    # which psalm: the one it's filed under, unless the text clearly belongs to another
    for r in rows:
        r["psalm"] = r["filed"]
        if len(r["words"]) < 3 or not r["filed"]:
            continue
        here = max((sim(r["words"], vw) for vw in VULGATE.get(r["filed"], {}).values()), default=0)
        if here < 0.5:
            other = max(((sim(r["words"], vw), ps, n) for ps in range(r["filed"] - 2, r["filed"] + 3)
                         if ps in VULGATE and ps != r["filed"] for n, vw in VULGATE[ps].items()), default=(0, None, None))
            if other[0] >= 0.7:
                r["psalm"] = other[1]
                issues.append(dict(kind="wrong_psalm", page=r["page"],
                                   msg=f"Verse {r['number']} “{r['latin'][:45]}” is Ps {other[1]}:{other[2]} (Vulgate) "
                                       f"but is filed under Ps {r['filed']}: psalm title misread or missing?"))
    by_psalm = defaultdict(list)
    for r in rows:
        if r["psalm"] in VULGATE:
            by_psalm[r["psalm"]].append(r)
    for ps, rs in sorted(by_psalm.items()):
        align(rs, ps)
        for r in rs:
            if r["vulgate"] is None and len(r["words"]) >= 3:
                issues.append(dict(kind="unmatched", page=r["page"],
                                   msg=f"Verse {r['number']} “{r['latin'][:50]}” matches no Vulgate verse of Ps {ps}"))
        covered = defaultdict(set)
        for r in rs:
            if r["vulgate"]:
                covered[r["vulgate"]] |= set(r["words"])
        for v, vw in VULGATE[ps].items():
            if len(covered[v] & set(vw)) / max(len(set(vw)), 1) < 0.5:
                before = [r for r in rs if r["vulgate"] and r["vulgate"] < v]
                if v == 1 and any(r["number"] == 0 for r in rs):
                    continue  # a verse 0 is the title, even when it spans Vulgate 1-2
                title = v == 1 and re.match(r"\s*(In finem|Psalmus|Canticum|Ipsi David|David|Alleluia|Oratio|Intellectus|Pro )", VULGATE_TEXT[ps][v])
                issues.append(dict(kind="missing_title" if title else "missing", page=(before[-1] if before else rs[0])["page"],
                                   msg=f"Ps {ps}:{v} (Vulgate) is not in the transcription: “{' '.join(VULGATE_TEXT[ps][v].split()[:10])}…”"))
        for a, b in zip(rs, rs[1:]):
            if a["vulgate"] and a["vulgate"] == b["vulgate"] and sim(b["words"], a["words"]) > 0.8 and sim(a["words"], b["words"]) > 0.8:
                issues.append(dict(kind="repeated", page=b["page"],
                                   msg=f"Ps {ps}: the same verse twice, page {a['page']} verse {a['number']} and "
                                       f"page {b['page']} verse {b['number']} “{b['latin'][:40]}”"))
        # Calmet's numbers should run on by one; a gap is fine where a verse is missing
        missing = {i["msg"] for i in issues if i["kind"] == "missing"}
        nums = [r for r in rs if isinstance(r["number"], int)]
        for a, b in zip(nums, nums[1:]):
            if b["number"] in (a["number"], a["number"] + 1):
                continue
            gap_missing = a["vulgate"] and b["vulgate"] and any(
                f"Ps {ps}:{v} (Vulgate)" in m for v in range(a["vulgate"] + 1, b["vulgate"]) for m in missing)
            if not gap_missing:
                issues.append(dict(kind="number", page=b["page"],
                                   msg=f"Ps {ps}: verse numbered {b['number']} follows {a['number']} "
                                       f"(“{b['latin'][:40]}”, Vulgate {ps}:{b['vulgate']}): misread number?"))
    return rows, issues


VULGATE_TEXT = {c["chapter"]: {v["verse"]: v["text"] for v in c["verses"]}
                for c in json.loads((VUL / "psalms.json").read_text())["chapters"]}


if __name__ == "__main__":
    vol = sys.argv[1] if len(sys.argv) > 1 else "21a_psaumes"
    rows, issues = check(vol)
    out = DOCS / "psalms_check.json"
    out.write_text(json.dumps(dict(volume=vol, issues=issues), ensure_ascii=False, indent=1))
    from collections import Counter
    print(f"{len(rows)} verses, {sum(1 for r in rows if r['psalm'])} matched to the Vulgate")
    print(dict(Counter(i["kind"] for i in issues)), "->", out)
