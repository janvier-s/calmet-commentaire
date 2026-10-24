"""psalms_check against the real Psalms (read-only)."""
import pytest

from paths import DATA

pytestmark = pytest.mark.skipif(not (DATA / "21c_psaumes" / "normalized").is_dir(), reason="no real data")


def test_refrain_verses_are_not_taken_for_a_repeat():
    # Ps 117:10 and 117:11 share "et in nomine Domini, quia ultus sum in eos": each keeps its own verse
    import psalms_check as P
    rows, issues = P.check("21c_psaumes")
    vul = {r["number"]: r["vulgate"] for r in rows if r["psalm"] == 117 and r["number"] in (10, 11, 12)}
    assert vul == {10: 10, 11: 11, 12: 12}
    assert not any("117:11" in i["msg"] or ("Ps 117" in i["msg"] and i["kind"] == "repeated") for i in issues)
