import json, re, sys, hashlib
from pathlib import Path

# Usage: python3 fix_typography.py [--latin-only] 06_josue 07_juges ...
# Old printing conventions in normalized pages: long s (ſ) -> s, "&c." -> "etc.", "&" -> "et".
# --latin-only leaves the French fields alone (for books not yet LLM-modernized).
# Modernized French that changes is added to the LLM cache, so llm_modernize won't resend it.
# Don't run while llm_modernize.py is running: it rewrites the whole cache when it finishes.
from paths import DATA as STUDIUM, LLM_CACHE as CACHE
FRENCH = {"french", "french_translation", "french_commentary", "chapter_summary"}


def fix(s):
    s = s.replace("ſ", "s")
    s = re.sub(r"&\s*c\.", "etc.", s)
    return re.sub(r"&(?![a-z]+;)", "et", s)


def walk(node, key, latin_only, cache, stats):
    if isinstance(node, dict):
        return {k: walk(v, k, latin_only, cache, stats) for k, v in node.items()}
    if isinstance(node, list):
        return [walk(v, key, latin_only, cache, stats) for v in node]
    if isinstance(node, str) and not (latin_only and key in FRENCH):
        new = fix(node)
        if new != node:
            stats["dirty"] = True
            if key in FRENCH:
                cache[hashlib.md5(new.encode()).hexdigest()] = new
                stats["cached"] += 1
        return new
    return node


def main(args):
    latin_only = "--latin-only" in args
    books = [a for a in args if not a.startswith("--")]
    cache = json.loads(CACHE.read_text())
    stats = {"cached": 0}
    for book in books:
        pages = changed = 0
        for p in sorted((STUDIUM / book / "normalized").glob("page_[0-9][0-9][0-9][0-9].json")):
            stats["dirty"] = False
            try:
                page = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                print(f"  skipped malformed {book}/{p.name}: {e}")
                continue
            data = walk(page, None, latin_only, cache, stats)
            pages += 1
            if stats["dirty"]:
                changed += 1
                p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{book}: {changed}/{pages} pages updated")
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2))
    print(f"{stats['cached']} modernized French blocks registered in the LLM cache")


if __name__ == "__main__":
    main(sys.argv[1:])
