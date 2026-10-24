"""The audit's items say where they are (section, index, field). Read-only on the real data."""
import hashlib
import json
import re

import pytest

import audit_integrity as A
from paths import DATA

pytestmark = pytest.mark.skipif(not (DATA / "22_proverbes" / "normalized").is_dir(), reason="no real data")

MUST = {"lowercase_lemma", "long_translation", "caps_in_commentary", "hyphen_cut", "period_seam"}


@pytest.fixture(scope="module")
def queue():
    info = A.BOOKS["proverbs"]
    return A.audit_book("proverbs", info, info.get("site") or A.site_slugs().get(info["fr"]))["queue"]


def quoted(msg):
    m = re.search(r"“([^”]+)”", msg)
    if not m:
        return None
    pieces = [p.strip(" .,;:") for p in m.group(1).split("…")]
    best = max(pieces, key=len)
    return best if len(best) >= 12 else None


def test_where_on_the_kinds_that_need_it(queue):
    for it in queue:
        if it["kind"] in MUST:
            assert "where" in it, it


def test_where_points_at_the_quoted_entry(queue):
    checked = hits = 0
    for it in queue:
        w, snip = it.get("where"), quoted(it["msg"])
        if not w or not w.get("field") or not snip:
            continue
        d = json.loads((DATA / it["book_dir"] / "normalized" / f"page_{it['page']:04d}.json").read_text(encoding="utf-8"))
        # the quote is in the entry (some kinds quote the lemma while pointing at the translation or verse_ref)
        text = " ".join(str(v) for v in d[w["section"]][w["index"]].values() if v is not None)
        checked += 1
        hits += snip in text or re.sub(r"\s+", " ", snip) in re.sub(r"\s+", " ", text)
    assert checked > 50
    assert hits / checked >= 0.9, (hits, checked)


def test_ids_hash_the_message_only(queue):
    for it in queue:
        assert it["id"].endswith(hashlib.md5(it["msg"].encode()).hexdigest()[:8])
