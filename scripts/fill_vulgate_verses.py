"""Insert verses missing from the transcription, with their Latin from the Vulgate.

For each verse missing from the sequence, a verse is inserted at the nearest page with:
  - chapter: the chapter number
  - verse_number: the missing verse number
  - latin: the Vulgate text
  - french: "" (to type from the scan)
  - annotations: standard note indicating the Latin came from the Vulgate

Usage: python3 fill_vulgate_verses.py [--dry-run] [volume ...]
"""
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

from paths import BOOKS, DATA, VUL, pages, load

NOTE = (
    "Latin from the Vulgate (verse missing from the transcription): check it against the scan, "
    "keep only the part Calmet prints under this number, and type his French"
)


def words(s):
    s = unicodedata.normalize("NFKD", (s or "").lower()).encode("ascii", "ignore").decode()
    s = s.replace("j", "i").replace("v", "u").replace("y", "i")
    out = []
    for w in re.findall(r"[a-z]+", s):
        if w == "etc":
            continue
        w = (
            w.replace("ae", "e")
            .replace("oe", "e")
            .replace("xs", "x")
            .replace("mq", "nq")
            .replace("ph", "f")
            .replace("h", "")
        )
        w = re.sub(r"(.)\1", r"\1", w)
        out.append(w[:5])
    return out


def sim(lw, vw):
    vs = set(vw)
    return sum(w in vs for w in lw) / max(len(lw), 1) if lw else 0


def process_volume(vol, key, dry=False):
    vul_p = VUL / f"{BOOKS[key]['vul']}.json"
    if not vul_p.exists():
        return 0, []

    vul_doc = load(vul_p)
    vul_map = {c["chapter"]: {v["verse"]: v["text"] for v in c["verses"]} for c in vul_doc["chapters"]}

    page_files = pages(vol)
    if not page_files:
        return 0, []

    pages_cache = {}
    v_entries = []

    for p in page_files:
        d = load(p)
        pages_cache[p.name] = (p, d)
        for idx, v in enumerate(d.get("verses") or []):
            v_entries.append((v.get("chapter"), v.get("verse_number"), p.name, idx, v))

    by_ch = defaultdict(list)
    for ch, vn, pnm, idx, v in v_entries:
        if ch is not None and isinstance(vn, int):
            by_ch[ch].append((vn, pnm, idx, v))

    # Determine plan of insertions: list of (pnm, insert_idx, new_verse_dict)
    # We must insert in reverse order per page so indices stay valid
    to_insert = []
    for ch, vlist in by_ch.items():
        if ch not in vul_map:
            continue
        vlist.sort(key=lambda t: t[0])
        have_nums = {vn for vn, _, _, _ in vlist}
        max_have = max(have_nums)

        existing_latins = [words(v.get("latin")) for _, _, _, v in vlist if v.get("latin")]

        for v in range(1, max_have + 1):
            if v not in have_nums and v in vul_map[ch]:
                vw = words(vul_map[ch][v])
                # Skip if text is already present under another verse number (misnumbered)
                if any(sim(vw, elw) > 0.6 for elw in existing_latins):
                    continue

                before = [item for item in vlist if item[0] < v]
                after = [item for item in vlist if item[0] > v]
                if before:
                    pnm, idx = before[-1][1], before[-1][2] + 1
                elif after:
                    pnm, idx = after[0][1], after[0][2]
                else:
                    continue

                clean_text = re.sub(r"^<[^>]+>", "", vul_map[ch][v]).strip()
                new_v = {
                    "verse_number": v,
                    "chapter": ch,
                    "latin": clean_text,
                    "french": "",
                    "annotations": NOTE,
                }
                to_insert.append((pnm, idx, new_v))

    if not to_insert:
        return 0, []

    # Sort descending by index so earlier insertions don't alter later indices
    # Group by page
    by_page = defaultdict(list)
    for pnm, idx, new_v in to_insert:
        by_page[pnm].append((idx, new_v))

    modified_pages = set()
    for pnm, items in by_page.items():
        p_path, d = pages_cache[pnm]
        if "verses" not in d or d["verses"] is None:
            d["verses"] = []
        for idx, new_v in sorted(items, key=lambda t: t[0], reverse=True):
            d["verses"].insert(min(idx, len(d["verses"])), new_v)
            modified_pages.add(pnm)

    if not dry:
        for pnm in modified_pages:
            p_path, d = pages_cache[pnm]
            p_path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

    return len(to_insert), to_insert


def main(argv):
    dry = "--dry-run" in argv
    args = [a for a in argv if not a.startswith("--")]

    # Build volume to book key map
    vol_to_key = {}
    for key, info in BOOKS.items():
        if key == "psalms":
            continue
        for v in info.get("studium", []):
            vol_to_key[v] = key

    vols = args or sorted(vol_to_key.keys())

    total_inserted = 0
    for vol in vols:
        key = vol_to_key.get(vol)
        if not key:
            continue
        count, items = process_volume(vol, key, dry=dry)
        if count:
            total_inserted += count
            print(f"{vol} ({key}): {count} verses {'would be ' if dry else ''}inserted")
            for pnm, idx, v in items[:5]:
                print(f"   ch {v['chapter']}:{v['verse_number']} on {pnm}")
            if len(items) > 5:
                print(f"   ... and {len(items) - 5} more")

    mode = "would be" if dry else "were"
    print(f"\nTotal: {total_inserted} verses {mode} inserted across {len(vols)} volumes.")


if __name__ == "__main__":
    main(sys.argv[1:])
