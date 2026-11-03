"""Text and file helpers shared by the page editors (no Tk, no Pillow)."""
import json
import re
from pathlib import Path

# --- Configuration ---
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
STATE_FILE = DATA_DIR / ".page_editor_state.json"


def find_source_image(book_path, page_num):
    """Locate the source image for a given page number across subdirectories."""
    page_str = f"{page_num:04d}"
    french_name = "_".join(book_path.name.split("_")[1:])
    accent_map = {
        "genese": "genèse", "exode": "exode", "levitique": "lévitique",
        "nombres": "nombres", "deuteronome": "deutéronome",
    }
    accented = accent_map.get(french_name, french_name)

    candidates = [
        book_path / "source_images" / "commentaire" / f"page_{page_str}.png",
        book_path / "source_images" / "intro" / "done" / f"{accented}_page_{page_str}.png",
        book_path / "source_images" / "fin" / "done" / f"{accented}_page_{page_str}.png",
        book_path / "source_images" / "intro" / "done" / f"{french_name}_page_{page_str}.png",
        book_path / "source_images" / "fin" / "done" / f"{french_name}_page_{page_str}.png",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def trim(o):
    """No spaces or line breaks at either end of a field, none around a line break (as tidy_fields.py)."""
    if isinstance(o, dict):
        return {k: trim(v) for k, v in o.items()}
    if isinstance(o, list):
        return [trim(v) for v in o]
    if isinstance(o, str):
        return re.sub(r"[ \t\u00a0]*\n[ \t\u00a0]*", "\n", o).strip()
    return o


def save_state(book_name, page_num, state_file=None):
    """Persist the current book and page for --resume."""
    try:
        (state_file or STATE_FILE).write_text(json.dumps({"book": book_name, "page": page_num}))
    except Exception:
        pass


def load_state(state_file=None):
    """Load persisted book and page. Returns (book_name, page_num) or (None, None)."""
    try:
        d = json.loads((state_file or STATE_FILE).read_text())
        return d["book"], d["page"]
    except Exception:
        return None, None


LRM = "‎"
HEBREW_RUN = re.compile(r"[֐-׿יִ-ﭏ]+(?:[  ]+[֐-׿יִ-ﭏ]+)*")


def isolate_hebrew(s):
    """Fence each Hebrew phrase with left-to-right marks for display, so numbers, Greek and
    the order of a list of words around it stay put; the marks are stripped again on save."""
    return HEBREW_RUN.sub(lambda m: LRM + m.group() + LRM, s.replace(LRM, ""))


BRACKETS = set("[](){}")
CLOSING_FOLLOWERS = set(",.;:!?)»]")
TRAILING_PUNCT = re.compile(r"_?[ \t]*([;?!]|:(?!\d))+")
JOIN_BEFORE = re.compile(r"_([ \t]*[,;:]?[ \t]*)$")  # a run closing just before (spaces, a comma between)
JOIN_AFTER = re.compile(r"([ \t]*[,;:]?[ \t]*)_")  # one opening just after
ROMAN_TRAILING = re.compile(r"[ \t]*(?:([;?!]|:(?!\d))+|[.,]+(?=_))")


def italic_runs(s):
    """Italic stretches of `s` between _underscore_ marks, as (start, end) offsets.

    Returns (runs, marks, open_at). With an odd number of marks the italics cross
    the field's edge: open_at is "start" when the first mark closes a run begun
    before the field (followed by a space or punctuation), else "end".
    """
    marks, i = [], s.find("_")
    while i != -1:  # str.find, not a loop over every character: long fields, thousands of calls at start
        marks.append(i)
        i = s.find("_", i + 1)
    edges, open_at = marks, None
    if len(marks) % 2:
        i = marks[0]
        closes = i + 1 == len(s) or s[i + 1].isspace() or s[i + 1] in CLOSING_FOLLOWERS
        open_at = "start" if closes else "end"
        edges = [-1] + marks if closes else marks + [len(s)]
    runs = [(edges[k] + 1, edges[k + 1]) for k in range(0, len(edges), 2)]
    return runs, marks, open_at


def toggle_italics(s, sa, sb):
    """Italicize s[sa:sb], or make it roman when it is all italic already.

    Only the selection and the marks touching it change. Returns (text, start, end)
    with the new selection, or None when the selection holds no text.
    """
    sa, sb = max(0, sa), min(sb, len(s))  # a selection to the end takes in Tk's final newline
    while sa < sb and (s[sa] == "_" or s[sa].isspace()):
        sa += 1
    while sb > sa and (s[sb - 1] == "_" or s[sb - 1].isspace()):
        sb -= 1
    if sa >= sb:
        return None
    runs, _, open_at = italic_runs(s)
    italic = {i for a, b in runs for i in range(a, b)}
    make = not all(i in italic for i in range(sa, sb) if s[i] != "_" and not s[i].isspace())
    if make:  # a bracket at the selection's edge is roman: [ faire ce plaisir ] _écoutez-moi._
        while sa < sb and (s[sa] in BRACKETS or s[sa].isspace()) and any(c.isalnum() for c in s[sa + 1:sb]):
            sa += 1
        while sb > sa and (s[sb - 1] in BRACKETS or s[sb - 1].isspace()) and any(c.isalnum() for c in s[sa:sb - 1]):
            sb -= 1
    m = (TRAILING_PUNCT if make else ROMAN_TRAILING).match(s, sb)
    if m and (make or m.end() - 1 in italic):
        sb = m.end()
    # Take in the marks at the selection's edges, and when un-italicizing the spaces
    # too, so that "_a b c_" becomes "_a_ b _c_".
    def absorbs(c):
        return c == "_" or (not make and c.isspace() and c != "\n")
    while sa > 0 and absorbs(s[sa - 1]):
        sa -= 1
    while sb < len(s) and absorbs(s[sb]):
        sb += 1

    def italic_at(p):
        return (s[:p].count("_") % 2 == 1) != (open_at == "start")
    # Italics carried over a field edge simply stop there: no mark at the edge itself.
    opening = "_" if italic_at(sa) != make and (make or sa > 0) else ""
    closing = "_" if italic_at(sb) != make and (make or sb < len(s)) else ""
    mid = s[sa:sb].replace("_", "")
    head, tail = s[:sa], s[sb:]
    if make:  # italics next to italics join: "_au_ Dieu" -> "_au Dieu_"
        m = JOIN_BEFORE.search(head)
        if opening and m:
            head, opening = head[:m.start()] + m.group(1), ""
        m = JOIN_AFTER.match(tail)
        if closing and m:
            tail, closing = m.group(1) + tail[m.end():], ""
    start = len(head) + len(opening)
    return head + opening + mid + closing + tail, start, start + len(mid)
