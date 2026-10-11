import json, re
page = json.loads(open("/Users/Janvier/Library/Mobile Documents/com~apple~CloudDocs/for-the-kingdom/STUDIUM/data/09_1_rois/normalized/page_0182.json").read())
ch = page.get("chapter_number")
title = page.get("chapter_title", "")
if title:
    m = re.search(r"CHAPITRE\s+([A-Z]+)", title)
    if m:
        roman = m.group(1)
        roman_map = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
        val = 0
        i = 0
        valid = True
        while i < len(roman):
            if roman[i] not in roman_map:
                valid = False
                break
            if i + 1 < len(roman) and roman_map[roman[i]] < roman_map[roman[i+1]]:
                val += roman_map[roman[i+1]] - roman_map[roman[i]]
                i += 2
            else:
                val += roman_map[roman[i]]
                i += 1
        if valid:
            ch = val
print("Parsed chapter:", ch)
print("Verses:", len(page.get("verses") or []))
