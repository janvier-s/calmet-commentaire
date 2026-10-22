import json
import hashlib
import os
import datetime

vol_dir = "/Users/Janvier/Library/Mobile Documents/com~apple~CloudDocs/for-the-kingdom/STUDIUM/data/47_matthieu"
norm_dir = os.path.join(vol_dir, "normalized")
scan_dir = os.path.join(vol_dir, "source_images", "commentaire")

registry_file = os.path.join(vol_dir, "verified_pages.json")
md_file = os.path.join(vol_dir, "VERIFIED_PAGES.md")

def sha256_file(p):
    if not os.path.exists(p):
        return None
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()[:12]

# Initial verified pages
verified = {
    # 16 full OCR pages
    "page_0432": ("full_transcription_from_scan", "Full transcript from scan PNG; chapter 13 commentary; 0 audit items"),
    "page_0433": ("full_transcription_from_scan", "Full transcript from scan PNG; chapter 13 commentary; 0 audit items"),
    "page_0435": ("full_transcription_from_scan", "Full transcript from scan PNG; chapter 13 commentary; 0 audit items"),
    "page_0525": ("full_transcription_from_scan", "Full transcript from scan PNG; chapter 15/16 transition; 0 audit items"),
    "page_0526": ("full_transcription_from_scan", "Full transcript from scan PNG; chapter 16 Latin/French text; 0 audit items"),
    "page_0527": ("full_transcription_from_scan", "Full transcript from scan PNG; chapter 16 commentary; 0 audit items"),
    "page_0528": ("full_transcription_from_scan", "Full transcript from scan PNG; chapter 16 commentary; 0 audit items"),
    "page_0529": ("full_transcription_from_scan", "Full transcript from scan PNG; chapter 16 commentary; 0 audit items"),
    "page_0530": ("full_transcription_from_scan", "Full transcript from scan PNG; chapter 16 commentary; 0 audit items"),
    "page_0531": ("full_transcription_from_scan", "Full transcript from scan PNG; chapter 16 commentary; 0 audit items"),
    "page_0628": ("full_transcription_from_scan", "Full transcript from scan PNG; chapter 21 commentary; 0 audit items"),
    "page_0629": ("full_transcription_from_scan", "Full transcript from scan PNG; chapter 21 commentary; 0 audit items"),
    "page_0630": ("full_transcription_from_scan", "Full transcript from scan PNG; chapter 21 commentary; 0 audit items"),
    "page_0672": ("full_transcription_from_scan", "Full transcript from scan PNG; chapter 23 commentary; 0 audit items"),
    "page_0785": ("full_transcription_from_scan", "Full transcript from scan PNG; chapter 27 commentary; 0 audit items"),
    "page_0791": ("full_transcription_from_scan", "Full transcript from scan PNG; chapter 27 commentary; 0 audit items"),

    # 5 syntax-corrupted recovered pages
    "page_0215": ("syntax_repair_and_scan_verification", "Repaired JSON structure, verified text, verses & commentary against scan PNG"),
    "page_0223": ("syntax_repair_and_scan_verification", "Repaired JSON structure, verified text, verses & commentary against scan PNG"),
    "page_0234": ("syntax_repair_and_scan_verification", "Repaired JSON structure, verified text, verses & commentary against scan PNG"),
    "page_0240": ("syntax_repair_and_scan_verification", "Repaired JSON structure, verified text, verses & commentary against scan PNG"),
    "page_0331": ("syntax_repair_and_scan_verification", "Repaired JSON structure, verified text, verses & commentary against scan PNG"),

    # 16 no_lemma image-guided repairs
    "page_0278": ("image_guided_repair", "Merged verse 23 continuation paragraph into note 2"),
    "page_0290": ("image_guided_repair", "Restored dropped verse 38 lemma and French translation; merged 3 paragraphs"),
    "page_0291": ("image_guided_repair", "Updated verse_ref to 38 for continuation from page 290"),
    "page_0307": ("image_guided_repair", "Extracted verse 7 lemma and translation; corrected verse_ref"),
    "page_0309": ("image_guided_repair", "Extracted verse 9 lemma and translation; corrected OCR noise and footnote markers"),
    "page_0311": ("image_guided_repair", "Extracted verse 10 lemma and translation; cleaned marker artifacts"),
    "page_0314": ("image_guided_repair", "Extracted verse 12 lemma and translation; cleaned OCR artifacts"),
    "page_0318": ("image_guided_repair", "Extracted verse 13 AMEN lemma and translation"),
    "page_0366": ("image_guided_repair", "Extracted verse 8 lemma and translation; corrected OCR smudge hallucination from scan"),
    "page_0423": ("image_guided_repair", "Restored verse 7 lemmata (QUID EXISTIS... and ARUNDINEM...) and translations"),
    "page_0427": ("image_guided_repair", "Restored dropped verse 12 lemma and translation; merged 3 paragraphs"),
    "page_0496": ("image_guided_repair", "Restored dropped verse 8 lemma and translation; corrected verse refs"),
    "page_0499": ("image_guided_repair", "Restored dropped verse 13 lemma and translation; removed bogus 2°. Que lemma"),
    "page_0618": ("image_guided_repair", "Restored missing opening words and merged verse 28 addition into continuation"),
    "page_0707": ("image_guided_repair", "Merged verse 51 paragraphs 2 and 3 into single commentary block"),
    "page_0721": ("image_guided_repair", "Verified Calmet printed no lemma for verse 38 (pure textual note)"),


    # Subagent Batch 1: Caps in Commentary, Seam Turns, and Marker Corrections
    "page_0172": ("image_guided_repair", "Extracted embedded lemma JESU-CHRISTI into block 2; corrected verse_ref to 1"),
    "page_0175": ("image_guided_repair", "Normalized small caps JESUS - CHRIST to standard French typography"),
    "page_0176": ("image_guided_repair", "Normalized small caps JESUS - CHRIST in block 3"),
    "page_0187": ("image_guided_repair", "Completely restored authentic page 17 text, verses and 11 footnotes from scan (reversing OCR hallucination)"),
    "page_0188": ("image_guided_repair", "Restored initial continuation line from page 187; verified verse 20 lemma"),
    "page_0234": ("image_guided_repair", "Extracted lemma VIDIT SPIRITUM DEI...; restored corrupted footnote calls and footnotes"),
    "page_0280": ("image_guided_repair", "Restored missing completion line from page 279; verified verse 25 translation and seam"),
    "page_0281": ("image_guided_repair", "Verified seam from page 280; verse 26 translation continuous"),
    "page_0292": ("image_guided_repair", "Matched scan italics; normalized small caps"),
    "page_0316": ("image_guided_repair", "Restored full verse 13 translation; continuous seam to page 317"),
    "page_0317": ("image_guided_repair", "Verified continuous seam from page 316"),
    "page_0328": ("image_guided_repair", "Restored missing 3 concluding lines of chapter 6 and footnote (a)"),
    "page_0329": ("image_guided_repair", "Verified chapter 7 opening and continuous seam from page 328"),
    "page_0405": ("image_guided_repair", "Extracted lemma ET AD PRÆSIDES... into block 2; fixed footnote call numbering"),
    "page_0433": ("image_guided_repair", "Extracted lemma SI IN TYRO ET SIDONE into block 4"),
    "page_0446": ("image_guided_repair", "Restored omitted line at page top; continuous seam to page 447"),
    "page_0447": ("image_guided_repair", "Verified continuous seam from page 446"),
    "page_0493": ("image_guided_repair", "Restored missing italics from scan; normalized small caps"),
    "page_0520": ("image_guided_repair", "Repaired corrupted marker ^{(4)} to ^{(a)}; realigned footnote calls"),
    "page_0524": ("image_guided_repair", "Restored omitted top line; continuous seam to page 525"),
    "page_0527": ("image_guided_repair", "Extracted lemma ROGAVERUNT EUM...; fixed OCR typo ROCAVERUNT"),
    "page_0533": ("image_guided_repair", "Separated verse 17 translation continuation from commentary into french_translation"),
    "page_0585": ("image_guided_repair", "Converted broken markers ^{1°} to standard text 1°.; fixed OCR typos"),
    "page_0655": ("image_guided_repair", "Restored omitted Latin citation from scan; continuous seam to page 656"),
    "page_0656": ("image_guided_repair", "Corrected critical metadata: verse 46 and chapter 23 verse 1 were misattributed to ch 22 v 26"),
    "page_0663": ("image_guided_repair", "Restored missing top block 1; restored verse 13 lemma at bottom"),
    "page_0664": ("image_guided_repair", "Separated verse 13 translation into french_translation; continuous seam from page 663"),
    "page_0679": ("image_guided_repair", "Normalized Latin quote SEDENTE EO SUPER MONTEM OLIVETI; cleaned small caps"),
    "page_0694": ("image_guided_repair", "Restored omitted top phrase of verse 26 into block 1; verified verse 27 translation"),
    "page_0695": ("image_guided_repair", "Added verse 29 lemma at bottom of page (STATIM AUTEM POST TRIBULATIONEM...)"),
    "page_0696": ("image_guided_repair", "Corrected verse_ref to 29; separated translation into french_translation"),
    "page_0741": ("image_guided_repair", "Repaired marker ^{(4)} to ^{(a)}; cleaned OCR typos"),
    "page_0788": ("image_guided_repair", "Fixed hyphenation at page turn (Jé- / sus)"),
    "page_0789": ("image_guided_repair", "Verified continuous seam from page 788"),
    "page_0798": ("image_guided_repair", "Cleaned spaced small caps J E S U S; corrected note (f) text"),

    # Defect verifications
    "page_0229": ("visual_defect_verification", "Verified authentic blank plate in source book; no missing text"),
    "page_0734": ("visual_defect_verification", "Corrected verse 21/22 numbering; restored French translation alignment"),
    "page_0282": ("visual_defect_verification", "Verified Latin distich is embedded poetry in note 1; fixed empty note 2"),
    "page_0426": ("visual_defect_verification", "Restored Latin continuation text from page 425; eliminated empty note"),
    "page_0440": ("visual_defect_verification", "Restored verse 3 translation and seam continuity to page 441"),
    "page_0441": ("visual_defect_verification", "Restored verse 3 continuation and separated verse 4 commentary"),
    "page_0607": ("visual_defect_verification", "Restored Latin citation in continuation from page 606; eliminated empty note")
}

def update_registry():
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    reg = {
        "volume": "47_matthieu",
        "last_updated": now,
        "total_verified": len(verified),
        "pages": {}
    }

    md_lines = [
        "# Verified Pages Log — 47_matthieu",
        "",
        f"Last updated: `{now}`  ",
        f"Total verified pages: **{len(verified)} / 648**",
        "",
        "These pages have been visually inspected against original scan PNGs (`source_images/commentaire/page_NNNN.png`) and verified for 100% fidelity in content, lemmata, translations, verse refs, and typography. **No re-scanning is needed for these pages.**",
        "",
        "| Page | Method | Scan Hash | JSON Hash | Description / Verification Details |",
        "| :--- | :--- | :--- | :--- | :--- |"
    ]

    for p, (method, desc) in sorted(verified.items()):
        json_path = os.path.join(norm_dir, f"{p}.json")
        png_path = os.path.join(scan_dir, f"{p}.png")
        j_hash = sha256_file(json_path) or "n/a"
        p_hash = sha256_file(png_path) or "n/a"
        reg["pages"][p] = {
            "status": "perfect_verified",
            "method": method,
            "description": desc,
            "scan_sha256": p_hash,
            "json_sha256": j_hash,
            "verified_at": now
        }
        md_lines.append(f"| `{p}` | `{method}` | `{p_hash}` | `{j_hash}` | {desc} |")

    with open(registry_file, "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)

    with open(md_file, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines) + "\n")

    print(f"Wrote {len(verified)} verified pages to {registry_file} and {md_file}")

if __name__ == "__main__":
    update_registry()
