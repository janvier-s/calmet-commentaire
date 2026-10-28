import json
import re
from pathlib import Path
from paths import DATA
import sys

def modernize_french(text):
    if not text:
        return text
        
    # Replace the actual long 's' character
    text = text.replace('ſ', 's')
    
    # Common OCR f -> s mistakes
    words = {
        r'\bJofue\b': 'Josue',
        r'\bJofué\b': 'Josué',
        r'\bfans\b': 'sans',
        r'\bfous\b': 'sous',
        r'\bfaint\b': 'saint',
        r'\bfainte\b': 'sainte',
        r'\bfaints\b': 'saints',
        r'\bfaintes\b': 'saintes',
        r'\bfaifoit\b': 'faisait',
        r'\bfaifoient\b': 'faisaient',
        r'\bpaffa\b': 'passa',
        r'\bfeigneur\b': 'seigneur',
        r'\bSeigneur\b': 'Seigneur', # Just in case it was 'Feigneur'
        r'\bFeigneur\b': 'Seigneur',
        r'\bfon\b': 'son',
        r'\bfes\b': 'ses',
        r'\bfe\b': 'se',
        r'\bfils\b': 'fils', # in case of 'filf'
        r'\bfilf\b': 'fils',
        r'\bfi\b': 'si',
        r'\beft\b': 'est',
        r'\btouffours\b': 'toujours',
    }
    for k, v in words.items():
        text = re.sub(k, v, text)
        
    # Archaic verbs: -oient -> -aient
    text = re.sub(r'oient\b', 'aient', text)
    
    # Archaic verbs: -oit -> -ait
    # Exceptions: droit, soit, doit, voit, croit, reçoit, reçoit, toit, doigt (often oit), etc.
    # We use a negative lookbehind for these specific letters/words
    # Actually, the safest way is a regex with a function or lookbehind
    def replace_oit(m):
        word = m.group(0)
        exceptions = ["droit", "soit", "doit", "voit", "croit", "reçoit", "conçoit", "aperçoit", "apperçoit", "déçoit", "toit", "étroit", "endroit", "froid"]
        # check if it is exactly one of the exceptions
        if word.lower() in exceptions:
            return word
        # specific suffixes like 'çoit' for verbs in -cer (commençoit -> commençait), excluding -cevoir present forms
        if word.endswith("çoit") and word.lower() not in exceptions:
            return word[:-3] + "çait"
        return word[:-3] + "ait"
        
    text = re.sub(r'\b\w+oit\b', replace_oit, text)
    
    # Archaic verbs: -ois -> -ais (e.g. j'avois -> j'avais, je faifois -> je faisais)
    def replace_ois(m):
        word = m.group(0)
        exceptions = ["fois", "bois", "trois", "mois", "vois", "crois", "dois", "poids", "choix", "rois", "lois", "voix"]
        if word.lower() in exceptions:
            return word
        if word.lower() == "françois":
            return word[:-3] + "çais"
        return word[:-3] + "ais"
        
    text = re.sub(r'\b\w+ois\b', replace_ois, text)
    
    # -oître -> -aître
    text = re.sub(r'oître', 'aître', text)
    text = re.sub(r'oistre', 'aître', text) # just in case
    
    # Other common old spellings
    text = text.replace('évenemens', 'événements')
    text = text.replace('évenement', 'événement')
    text = text.replace('&', 'et')
    
    return text

def clean_verse_number(v):
    if v is None:
        return None
    if isinstance(v, int):
        return v
    # It's a string like "℣. 1."
    digits = re.sub(r'[^\d]', '', str(v))
    if digits:
        return int(digits)
    return None

def main():
    if len(sys.argv) < 2:
        print("Usage: python modernize.py <book_folder>")
        sys.exit(1)
        
    folder_name = sys.argv[1]
    folder = DATA / folder_name / "normalized"
    
    for file_path in folder.glob("page_[0-9][0-9][0-9][0-9].json"):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
            data = data[0]
            
        if data.get("chapter_summary"):
            data["chapter_summary"] = modernize_french(data["chapter_summary"])
            
        if data.get("chapter_argument"):
            data["chapter_argument"] = modernize_french(data["chapter_argument"])
            
        if "verses" in data:
            for verse in data["verses"]:
                verse["verse_number"] = clean_verse_number(verse.get("verse_number"))
                if verse.get("french"):
                    verse["french"] = modernize_french(verse["french"])
                    
        if "commentary" in data:
            for comm in data["commentary"]:
                if comm.get("french_commentary"):
                    comm["french_commentary"] = modernize_french(comm["french_commentary"])
                if comm.get("french_translation"):
                    comm["french_translation"] = modernize_french(comm["french_translation"])
                    
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
