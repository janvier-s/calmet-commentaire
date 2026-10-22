#!/usr/bin/env python3
"""
fill_missing_pngs.py

Fills in missing PNG scan images for volumes in STUDIUM/data by rendering them
from the corresponding Calmet source PDFs in STUDIUM/sources/calmet at 200 DPI.
"""

import os
import re
import sys
import shutil
import tempfile
import subprocess
from pathlib import Path
from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = Path("/Users/Janvier/Library/Mobile Documents/com~apple~CloudDocs/for-the-kingdom/STUDIUM/data")
SOURCES_DIR = Path("/Users/Janvier/Library/Mobile Documents/com~apple~CloudDocs/for-the-kingdom/STUDIUM/sources/calmet")


def get_pdf_page_count(pdf_path: Path) -> int:
    res = subprocess.run(["pdfinfo", str(pdf_path)], capture_output=True, text=True)
    for line in res.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":")[1].strip())
    raise ValueError(f"Could not read page count for {pdf_path}")


def render_pdf_page(pdf_path: Path, page_num: int, out_path: Path, target_mode: str = "L"):
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_prefix = Path(tmpdir) / "render"
        cmd = [
            "pdftoppm",
            "-png",
            "-gray",
            "-r", "200",
            "-f", str(page_num),
            "-l", str(page_num),
            str(pdf_path),
            str(tmp_prefix)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"pdftoppm failed on {pdf_path} page {page_num}: {res.stderr}")
        
        rendered = list(Path(tmpdir).glob("render*.png"))
        if not rendered:
            raise FileNotFoundError(f"No output rendered for {pdf_path} page {page_num}")
        
        im = Image.open(rendered[0])
        if target_mode == "L" and im.mode != "L":
            im = im.convert("L")
        elif target_mode == "RGB" and im.mode != "RGB":
            im = im.convert("RGB")
            
        out_path.parent.mkdir(parents=True, exist_ok=True)
        im.save(out_path, "PNG", optimize=True)


def main():
    dry_run = "--dry-run" in sys.argv
    only_norm = "--only-normalized" in sys.argv

    if not SOURCES_DIR.exists():
        print(f"Sources directory not found: {SOURCES_DIR}")
        sys.exit(1)

    pdf_map = {}
    for p in SOURCES_DIR.glob("*.pdf"):
        prefix = p.name.split("_")[0]
        pdf_map[prefix] = p

    plan = []

    for book_dir in sorted(DATA_DIR.iterdir()):
        if not book_dir.is_dir() or book_dir.name.startswith("."):
            continue

        prefix = book_dir.name.split("_")[0]
        pdf = pdf_map.get(prefix)
        if not pdf:
            continue

        pdf_pages = get_pdf_page_count(pdf)

        # Detect sample mode from existing images
        existing_imgs = list(book_dir.rglob("*.png"))
        book_mode = "L"
        if existing_imgs:
            try:
                with Image.open(existing_imgs[0]) as sample:
                    book_mode = sample.mode
            except Exception:
                book_mode = "L"

        img_nums = set()
        for f in (book_dir / "source_images").rglob("*.png"):
            m = re.search(r"page_(\d+)", f.name)
            if m:
                img_nums.add(int(m.group(1)))

        norm_dir = book_dir / "normalized"
        norm_pages = set()
        if norm_dir.exists():
            for f in norm_dir.glob("page_*.json"):
                m = re.search(r"page_(\d+)\.json", f.name)
                if m:
                    norm_pages.add(int(m.group(1)))

        comm_dir = book_dir / "source_images" / "commentaire"
        comm_nums = [int(re.search(r"\d+", f.name).group()) for f in comm_dir.glob("page_*.png") if re.search(r"\d+", f.name)]
        cmin = min(comm_nums) if comm_nums else 999999
        cmax = max(comm_nums) if comm_nums else -1

        # Determine needed pages
        needed = []
        if book_dir.name == "21a_psaumes":
            # 1..667 from 21a
            for p in range(1, 668):
                if p not in img_nums:
                    needed.append((p, pdf, p))
            # 668..888 from 21b (pages 1..221)
            pdf_21b = pdf_map.get("21b")
            for p in range(668, 889):
                if p not in img_nums:
                    needed.append((p, pdf_21b, p - 667))
        elif book_dir.name == "21b_psaumes":
            for p in range(223, 634):
                if p not in img_nums:
                    needed.append((p, pdf, p))
        else:
            for p in range(1, pdf_pages + 1):
                if p not in img_nums:
                    needed.append((p, pdf, p))

        for p_num, src_pdf, pdf_page in needed:
            is_norm = p_num in norm_pages
            if only_norm and not is_norm:
                continue

            # Determine destination
            if is_norm or (cmin <= p_num <= cmax):
                dest = comm_dir / f"page_{p_num:04d}.png"
            elif p_num < cmin:
                # Place in intro (if intro/done exists, put in intro or nearest)
                dest = book_dir / "source_images" / "intro" / f"page_{p_num:04d}.png"
            else:
                dest = book_dir / "source_images" / "fin" / f"page_{p_num:04d}.png"

            plan.append({
                "book": book_dir.name,
                "page": p_num,
                "pdf": src_pdf,
                "pdf_page": pdf_page,
                "dest": dest,
                "mode": book_mode,
                "is_norm": is_norm,
            })

    print(f"Found {len(plan)} missing PNG images to fill.")
    norm_count = sum(1 for item in plan if item["is_norm"])
    print(f"  - Needed by normalized pages: {norm_count}")
    print(f"  - Other missing pages: {len(plan) - norm_count}")

    if dry_run:
        print("\n[Dry Run] Images that would be rendered:")
        for item in plan:
            tag = "[NORMALIZED]" if item["is_norm"] else "[OTHER]"
            print(f"  {tag:12s} {item['book']} page {item['page']:04d} -> {item['dest'].relative_to(DATA_DIR)} (from {item['pdf'].name} p.{item['pdf_page']})")
        return

    print("\nRendering images...")
    rendered_count = 0
    for i, item in enumerate(plan, 1):
        tag = "[NORM]" if item["is_norm"] else "[OTHER]"
        print(f"[{i:02d}/{len(plan):02d}] {tag} {item['book']} p.{item['page']:04d} from {item['pdf'].name} p.{item['pdf_page']} -> {item['dest'].name}")
        render_pdf_page(item["pdf"], item["pdf_page"], item["dest"], item["mode"])
        rendered_count += 1

    print(f"\nDone! Rendered {rendered_count} images.")


if __name__ == "__main__":
    main()
