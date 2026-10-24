"""Every location the Calmet pipeline reads or writes, in one place."""
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
STUDIUM = SCRIPTS.parent
DATA = STUDIUM / "data"                      # DATA/<volume>/normalized/page_NNNN.json: the definitive text
DOCS = STUDIUM / "docs"
WEB = Path("/Users/Janvier/Documents/Bible n stuff/Websites/dom-calmet-web/src/lib/data")
VUL = Path("/Users/Janvier/Library/Mobile Documents/com~apple~CloudDocs/for-the-kingdom/douayrheimsbible/static/data/vul")
LLM_CACHE = SCRIPTS / "cache" / "llm_cache.json"
SEAM_CACHE = SCRIPTS / "cache" / "seam_cache.json"
HUNSPELL_CACHE = SCRIPTS / "cache" / "hunspell_cache.json"
HUNSPELL_DICT = Path.home() / "Library" / "Spelling" / "fr_FR"     # fr_FR.dic + fr_FR.aff

# key -> {fr, vul, studium: [volume folders], site: website slug}
BOOKS = json.loads((SCRIPTS / "books.json").read_text(encoding="utf-8"))
BY_VOLUME = {vol: key for key, b in BOOKS.items() for vol in b["studium"]}


def pages(volume):
    """The page files of a volume, in order (conflict copies like 'page_0001 2.json' excluded)."""
    return sorted((DATA / volume / "normalized").glob("page_[0-9][0-9][0-9][0-9].json"))


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def volumes_of(args):
    """Volume folders named on the command line; a book key (job, psalms) stands for all its
    volumes, `all` for every volume."""
    vols = []
    for a in args:
        if a == "all":
            vols += sorted(p.name for p in DATA.iterdir() if (p / "normalized").is_dir())
        elif a in BOOKS:
            vols += BOOKS[a]["studium"]
        elif (DATA / a / "normalized").is_dir():
            vols.append(a)
        else:
            sys.exit(f"Unknown volume or book: {a}")
    return vols
