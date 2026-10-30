"""Fix Hebrew letter headers on acrostic verses (Lamentations 1-4 and Psalm 118).

Ensures each acrostic verse starts with:
"<Letter>.\n<verse text>"
in Titlecase, matching the user's specification.
Removes letter spacing like 'S A M E C H.' -> 'Samech.', cleans extra keys,
and purges spurious letter-only verse entries.
"""

import argparse
import glob
import json
import re
from pathlib import Path

# Canonical spelling of the 22 letters in Titlecase:
LETTERS_CALMET_LAM1 = [
    "Aleph", "Beth", "Ghimel", "Daleth", "He", "Vau", "Zain", "Heth", "Teth", "Jod",
    "Caph", "Lamed", "Mem", "Nun", "Samech", "Ain", "Phe", "Sade", "Coph", "Res", "Sin", "Thau"
]
LETTERS_CALMET_LAM2_4 = [
    "Aleph", "Beth", "Ghimel", "Daleth", "He", "Vau", "Zain", "Heth", "Teth", "Jod",
    "Caph", "Lamed", "Mem", "Nun", "Samech", "Phe", "Ain", "Sade", "Coph", "Res", "Sin", "Thau"
]
LETTERS_PS118 = {
    1: "Aleph", 9: "Beth", 17: "Ghimel", 25: "Daleth", 33: "He", 41: "Vau",
    49: "Zain", 57: "Heth", 65: "Teth", 73: "Jod", 81: "Caph", 89: "Lamed",
    97: "Mem", 105: "Nun", 113: "Samech", 121: "Ain", 129: "Phe", 137: "Sade",
    145: "Coph", 153: "Res", 161: "Sin", 169: "Thau"
}

HEB_NAMES_VARIANTS = [
    r"A\s*L\s*E\s*P\s*H", r"B\s*E\s*T\s*H", r"G\s*H\s*I\s*M\s*E\s*L", r"G\s*U\s*I\s*M\s*E\s*L",
    r"D\s*A\s*L\s*E\s*T\s*H", r"H\s*E\s*T\s*H", r"H\s*E", r"V\s*A\s*U", r"Z\s*A\s*[IÏ]\s*N",
    r"T\s*E\s*T\s*H", r"J\s*O\s*D", r"I\s*O\s*D", r"C\s*A\s*P\s*H", r"L\s*A\s*M\s*E\s*D",
    r"M\s*E\s*M", r"N\s*U\s*N", r"S\s*A\s*M\s*E\s*C\s*H", r"A\s*[IÏ]\s*N", r"P\s*H\s*E",
    r"S\s*A\s*D\s*E", r"C\s*O\s*P\s*H", r"R\s*E\s*S", r"S\s*I\s*N", r"T\s*H\s*A\s*U", r"T\s*A\s*U"
]
names_pattern = "|".join(sorted(HEB_NAMES_VARIANTS, key=lambda x: -len(x)))
STRIP_PREFIX = re.compile(
    r"^\s*(?:" + names_pattern + r")\b\s*[.:,-]?\s*(?:\n\s*)*(?:\d+\.\s*)?",
    re.I
)

ALLOWED_KEYS = {"verse_number", "chapter", "latin", "french", "annotations"}


def clean_verse_text(text: str, letter: str) -> str:
    """Strip any existing Hebrew letter name header or leading verse number and prefix with 'Letter.\\n'."""
    if not text:
        return text
    stripped = STRIP_PREFIX.sub("", text).strip()
    return f"{letter}.\n{stripped}"


def process_file(path: Path, dry_run: bool = True):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    changed = False
    verses = data.get("verses") or []

    # Handle special case: page_0015 of 29_lamentations has standalone spurious letter verses
    if path.name == "page_0015.json" and "29_lamentations" in str(path):
        filtered_verses = []
        for v in verses:
            la = (v.get("latin") or "").strip()
            if re.match(r"^(?:" + names_pattern + r")\s*\.?$", la, re.I):
                changed = True
                continue
            filtered_verses.append(v)
        verses = filtered_verses
        data["verses"] = verses

    for v in verses:
        ch = v.get("chapter")
        vn = v.get("verse_number")

        # Strip any extra keys not in ALLOWED_KEYS
        extra_keys = set(v.keys()) - ALLOWED_KEYS
        if extra_keys:
            for k in extra_keys:
                del v[k]
            changed = True

        # Clear annotations if they only contain a Hebrew letter name
        ann = (v.get("annotations") or "").strip()
        if ann and re.match(r"^(?:" + names_pattern + r")\s*\.?$", ann, re.I):
            v["annotations"] = None
            changed = True

        letter = None
        if "29_lamentations" in str(path):
            if ch == 1 and isinstance(vn, int) and 1 <= vn <= 22:
                letter = LETTERS_CALMET_LAM1[vn - 1]
            elif ch in (2, 4) and isinstance(vn, int) and 1 <= vn <= 22:
                letter = LETTERS_CALMET_LAM2_4[vn - 1]
            elif ch == 3 and isinstance(vn, int) and 1 <= vn <= 66:
                letter = LETTERS_CALMET_LAM2_4[(vn - 1) // 3]
        elif "21c_psaumes" in str(path):
            if ch == 118 and isinstance(vn, int) and vn in LETTERS_PS118:
                letter = LETTERS_PS118[vn]

        if letter:
            old_la = v.get("latin") or ""
            old_fr = v.get("french") or ""
            new_la = clean_verse_text(old_la, letter)
            new_fr = clean_verse_text(old_fr, letter)
            if new_la != old_la or new_fr != old_fr:
                changed = True
                v["latin"] = new_la
                v["french"] = new_fr

    if changed:
        if not dry_run:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.write("\n")
    return changed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", default=False)
    args = parser.parse_args()

    files = sorted(glob.glob("data/29_lamentations/normalized/page_*.json")) + \
            sorted(glob.glob("data/21c_psaumes/normalized/page_*.json"))

    modified_count = 0
    for p in files:
        if process_file(Path(p), dry_run=args.dry_run):
            modified_count += 1
            print(f"[{'DRY-RUN' if args.dry_run else 'APPLIED'}] {p}")

    print(f"\nTotal files {'to modify' if args.dry_run else 'modified'}: {modified_count}")


if __name__ == "__main__":
    main()
