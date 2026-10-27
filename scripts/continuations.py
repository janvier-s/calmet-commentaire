"""Which commentary blocks go on the note before them, and keeping their chapter and verse in step.

A note printed over a page turn (or one the transcription split in two) is stored as several blocks:
the first has the lemma and its translation, the others have neither, and each carries its own
`chapter` and `verse_ref`. No lemma and no translation makes a block a continuation, unless its text
says it starts a note: the lemma in capitals, or a capital opening a sentence after the full stop that
ended the note before (then a reader decides: audit_integrity's `first_no_lemma`).
"""
import copy
import re

REF_FIELDS = ("chapter", "verse_ref")
LEMMA_START = re.compile(r"\s*[A-ZÀ-ÝŒÆ]{2,}[\sA-ZÀ-ÝŒÆ',.;:?!-]{6,}")
ABBREV = re.compile(r"\b(etc|v|ch|c|chap|[Ii]bid|S|St|M|p|l|liv|[Ll]ib|cap|Ps|Gen|Reg|Exod|Num|Deut|Jos|Judic|"
                    r"Isai|Jerem|Ezech|Matt|Luc|Joan|Rom|Cor|Hebr?|vers|n|An)\.$|\b[IVXLC]+\.$|\d\.$")


def strip_calls(text):
    """`text` without the footnote calls and spaces at its end."""
    return re.sub(r"(\s*\^\{[^}]*\})+\s*$", "", text or "").rstrip()


def sentence_ended(before):
    """Does the comment `before` end a sentence (not an abbreviation, no italics left open)?"""
    body = strip_calls(before)
    return bool(re.search(r"[.!?»]_?$", body) and not ABBREV.search(body.rstrip("_")) and not (before or "").count("_") % 2)


def opens_with_capital(text):
    m = re.match(r"[\s_«\"“(]*([^\W\d_])", text or "")
    return bool(m and m.group(1).isupper())


def continues(before, block):
    """Is `block` the rest of the note whose comment is `before`? Not when it has a lemma or a translation
    of its own, opens with its lemma in capitals, or opens a sentence after a full stop (unsure, so left
    to a reader). A word cut by a hyphen at the page turn goes on."""
    if (block.get("latin_quote") or "").strip() or (block.get("french_translation") or "").strip():
        return False
    fc = block.get("french_commentary") or ""
    if not fc.strip() or strip_calls(before).endswith("-"):
        return True
    if LEMMA_START.match(fc):
        return False
    return not (sentence_ended(before) and opens_with_capital(fc))


def refs(block):
    return tuple("" if block.get(k) is None else str(block[k]) for k in REF_FIELDS)


def copy_refs(block, parent):
    """Give `block` the chapter and verse_ref of `parent` (the ones it has): True if that changed it."""
    before = refs(block)
    for k in REF_FIELDS:
        if parent.get(k) not in (None, ""):
            block[k] = parent[k]
    return refs(block) != before


def carry_refs(page, old, next_page=None):
    """A saved page whose notes had their chapter or verse_ref changed (`old`: the page as it was):
    the blocks that go on from those notes follow, on the page and, from its last note, on the
    next page. Back: the page, and the next page when it changed (else None). Nothing is carried when
    blocks were added or removed (the numbers can't be matched), nor into a block changed on its own."""
    page = copy.deepcopy(page)
    cs, oc = page.get("commentary") or [], (old or {}).get("commentary") or []
    if len(cs) != len(oc):
        return page, None
    changed = [refs(c) != refs(o) for c, o in zip(cs, oc)]
    for j, c in enumerate(cs):
        if not changed[j]:
            continue
        for k in range(j + 1, len(cs)):
            if changed[k] or not continues(cs[k - 1].get("french_commentary"), cs[k]):
                break
            copy_refs(cs[k], c)
    if not cs or not next_page or refs(cs[-1]) == refs(oc[-1]):
        return page, None
    nxt = copy.deepcopy(next_page)
    ncs, moved = nxt.get("commentary") or [], False
    for k, b in enumerate(ncs):
        before = (cs[-1] if k == 0 else ncs[k - 1]).get("french_commentary")
        if not continues(before, b):
            break
        moved |= copy_refs(b, cs[-1])
    return page, nxt if moved else None


def opens_lowercase(block):
    """Does the block's comment open in the middle of a sentence (lower case after any italics mark,
    bracket or footnote call)?"""
    m = re.match(r"[\s_«\"“(]*(?:\^\{[^}]*\}[\s_]*)?([^\W\d_])", block.get("french_commentary") or "")
    return bool(m and m.group(1).islower())


def start_missing(last, block):
    """`block` is the first of its page, no lemma and no translation, opening in lower case: the end of a
    comment. `last`, the last block of the page before (None: that page has no notes), is no comment it
    could be the end of. Back: True when the start of the comment is missing. Not when `last` is a
    lemma or translation left unfinished at the foot (a word cut at the turn is hyphen_cut's)."""
    if (block.get("latin_quote") or "").strip() or (block.get("french_translation") or "").strip():
        return False
    if not opens_lowercase(block):
        return False
    if last is None:
        return True
    if (last.get("french_commentary") or "").strip():
        return False
    head = (last.get("french_translation") or last.get("latin_quote") or "").strip()
    return not head or bool(re.search(r"[.!?»…)\]]$", head))
