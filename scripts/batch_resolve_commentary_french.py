"""Batch extract and modernize French verse translations found in commentary blocks across:
28_jeremie, 21a_psaumes, 21b_psaumes, 21c_psaumes.
"""
import hashlib
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from paths import DATA, LLM_CACHE, pages, load

def find_commentary_french(d, verse):
    vn = str(verse.get("verse_number"))
    vl = (verse.get("latin") or "").lower()

    # 1. Exact verse_ref match
    for c in d.get("commentary") or []:
        ref = str(c.get("verse_ref") or "").replace("℣.", "").replace(".", "").strip()
        if ref == vn:
            fr = (c.get("french_translation") or c.get("french") or "").strip()
            if fr:
                return fr

    # 2. Latin quote prefix match
    if len(vl) > 15:
        vl_clean = re.sub(r"[^\w\s]", "", vl[:40])
        for c in d.get("commentary") or []:
            lq = (c.get("latin_quote") or "").lower()
            lq_clean = re.sub(r"[^\w\s]", "", lq[:40])
            if lq_clean and (lq_clean in vl_clean or vl_clean in lq_clean):
                fr = (c.get("french_translation") or c.get("french") or "").strip()
                if fr:
                    return fr

    return None


def modernize_batch_with_agy(items):
    """Modernize a dict of {key: text} using agy CLI."""
    if not items:
        return {}
    prompt = (
        "Modernize the French spelling of each sentence into standard modern French "
        "(e.g., étoit -> était, & -> et, enfans -> enfants, dispersez -> dispersés, eüe -> eue, paroître -> paraître). "
        "Keep the exact punctuation and structure. "
        "Input JSON:\n"
        + json.dumps(items, ensure_ascii=False)
        + "\nReturn ONLY a valid JSON object mapping the same keys to modernized French strings."
    )
    cmd = ["agy", "--dangerously-skip-permissions", "-p", prompt]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out = res.stdout.strip()

    if out.startswith("```"):
        lines = out.split("\n")
        if len(lines) > 2:
            out = "\n".join(lines[1:-1]).strip()
    if out.startswith("json"):
        out = out[4:].strip()

    m = re.search(r"\{.*\}", out, re.DOTALL)
    if m:
        return json.loads(m.group(0))
    return json.loads(out)


def main():
    vols = ["28_jeremie", "21a_psaumes", "21b_psaumes", "21c_psaumes"]
    cache = load(LLM_CACHE) if LLM_CACHE.exists() else {}

    candidates = [] # list of (vol, pnm, verse_idx, raw_french)

    for vol in vols:
        for pf in pages(vol):
            d = load(pf)
            for idx, v in enumerate(d.get("verses") or []):
                if "Latin from the Vulgate" in str(v.get("annotations")) and not (v.get("french") or "").strip():
                    fr = find_commentary_french(d, v)
                    if fr:
                        candidates.append((vol, pf.name, idx, fr))

    print(f"Found {len(candidates)} missing verses with translations in commentary.")

    # Batch modernizations
    batch_size = 20
    modernized_map = {} # (vol, pnm, idx) -> modern_fr

    for i in range(0, len(candidates), batch_size):
        chunk = candidates[i:i+batch_size]
        items = {str(k): c[3] for k, c in enumerate(chunk)}
        print(f"Modernizing batch {i // batch_size + 1}/{(len(candidates) + batch_size - 1) // batch_size} ({len(items)} items)...")
        try:
            mod_res = modernize_batch_with_agy(items)
            for k_str, mod_text in mod_res.items():
                k = int(k_str)
                vol, pnm, idx, _ = chunk[k]
                modernized_map[(vol, pnm, idx)] = mod_text.strip()
        except Exception as e:
            print(f"Error on batch: {e}")

    # Now apply to files
    updated_files = 0
    updated_verses = 0

    files_to_update = defaultdict(dict)
    for (vol, pnm, idx), mod_fr in modernized_map.items():
        files_to_update[(vol, pnm)][idx] = mod_fr

    for (vol, pnm), idx_map in files_to_update.items():
        pf = DATA / vol / "normalized" / pnm
        d = load(pf)
        for idx, mod_fr in idx_map.items():
            v = d["verses"][idx]
            v["french"] = mod_fr
            v["annotations"] = None
            h = hashlib.md5(mod_fr.encode("utf-8")).hexdigest()
            cache[h] = mod_fr
            updated_verses += 1
        pf.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        updated_files += 1

    LLM_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Successfully updated {updated_verses} verses across {updated_files} files.")
    print(f"LLM cache now has {len(cache)} entries.")


if __name__ == "__main__":
    main()
