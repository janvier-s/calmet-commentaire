"""Extract and modernize missing French verse translations from Dom Calmet scans using agy.

For each verse in a volume that has Latin from the Vulgate and empty French:
  1. Locates the source image for the page.
  2. Uses `agy` to read the scan, extract the French translation from the right-hand column,
     and modernize the 18th-century spelling into standard modern French.
  3. Populates `verse["french"]`.
  4. Clears the Vulgate missing verse annotation.
  5. Registers the modernized French text in `scripts/cache/llm_cache.json`.

Usage:
  python3 fill_missing_french.py [--dry-run] [volume ...]
"""
import asyncio
import hashlib
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from paths import DATA, LLM_CACHE, pages, load


def find_image(vol, pnm):
    stem = Path(pnm).stem
    candidates = list((DATA / vol / "source_images").rglob(f"{stem}.png"))
    return candidates[0] if candidates else None


async def extract_french_for_page(img_path, vnums, semaphore):
    vlist_str = ", ".join(str(v) for v in vnums)
    prompt = (
        f"Please use read_file on '{img_path}'. At the top of the page under the verse section "
        f"(or under the chapter heading), extract the French translation for verse(s) {vlist_str} "
        f"from the right-hand column. Modernize the spelling into standard modern French "
        f"(e.g., étoit -> était, & -> et, enfans -> enfants). "
        f"Output ONLY a valid JSON object mapping verse number as string to modernized French text, "
        f"e.g. {{\"{vnums[0]}\": \"...\"}}. No other text, no markdown code fence."
    )

    cmd = [
        "agy",
        "--dangerously-skip-permissions",
        "-p",
        prompt,
    ]

    async with semaphore:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            err = stderr.decode("utf-8", errors="replace")[:300]
            raise RuntimeError(f"agy error: {err}")

        out = stdout.decode("utf-8", errors="replace").strip()
        # Clean any markdown fences if present
        if out.startswith("```"):
            lines = out.split("\n")
            if len(lines) > 2:
                out = "\n".join(lines[1:-1]).strip()
        if out.startswith("json"):
            out = out[4:].strip()

        # Parse JSON
        m = re.search(r"\{.*\}", out, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        return json.loads(out)


async def process_volume(vol, dry=False, concurrency=2):
    page_files = pages(vol)
    if not page_files:
        return 0, 0

    # Collect pages needing French
    work = defaultdict(list)
    pages_data = {}

    for pf in page_files:
        d = load(pf)
        pages_data[pf.name] = (pf, d)
        for v in d.get("verses") or []:
            if "Latin from the Vulgate" in str(v.get("annotations")) and not (v.get("french") or "").strip():
                work[pf.name].append(v.get("verse_number"))

    if not work:
        print(f"{vol}: 0 verses needing French.")
        return 0, 0

    total_verses = sum(len(v) for v in work.values())
    print(f"{vol}: {total_verses} verses needing French across {len(work)} pages.")

    if dry:
        for pnm, vnums in sorted(work.items()):
            img = find_image(vol, pnm)
            print(f"  [dry-run] {pnm}: verses {vnums} -> image: {img.name if img else 'NOT FOUND'}")
        return len(work), total_verses

    semaphore = asyncio.Semaphore(concurrency)
    cache = load(LLM_CACHE) if LLM_CACHE.exists() else {}

    for pnm, vnums in sorted(work.items()):
        img_path = find_image(vol, pnm)
        if not img_path:
            print(f"  WARNING: image not found for {vol}/{pnm}")
            continue

        print(f"  Extracting {vol}/{pnm} (verses {vnums})...")
        try:
            result = await extract_french_for_page(img_path, vnums, semaphore)
        except Exception as e:
            print(f"  ERROR on {pnm}: {e}")
            continue

        pf, d = pages_data[pnm]
        updated = False
        for v in d.get("verses") or []:
            vn_str = str(v.get("verse_number"))
            if vn_str in result and result[vn_str]:
                mod_text = result[vn_str].strip()
                v["french"] = mod_text
                v["annotations"] = None
                cache[hashlib.md5(mod_text.encode("utf-8")).hexdigest()] = mod_text
                updated = True
                print(f"    v{vn_str}: {mod_text[:70]}...")

        if updated:
            pf.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

    LLM_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(work), total_verses


async def main_async(argv):
    dry = "--dry-run" in argv
    vols = [a for a in argv if not a.startswith("--")]

    if not vols:
        # Scan all volumes with missing verses
        vols_all = sorted([p.parent.name for p in DATA.glob("*/normalized")])
        vols = []
        for v in vols_all:
            for pf in pages(v):
                d = load(pf)
                if any("Latin from the Vulgate" in str(x.get("annotations")) and not (x.get("french") or "").strip() for x in d.get("verses") or []):
                    vols.append(v)
                    break

    print(f"Targeting volumes: {', '.join(vols)}")
    for vol in vols:
        await process_volume(vol, dry=dry)


def main():
    asyncio.run(main_async(sys.argv[1:]))


if __name__ == "__main__":
    main()
