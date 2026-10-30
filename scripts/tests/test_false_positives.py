"""Tests for resilient false positive tracking across text modifications."""

import difflib
from review_store import FalsePositives, Progress, fp_sig, match_fp_sigs, in_status


def test_fp_sig_matching_survives_text_changes():
    # Case 1: Typography / quote edit (Jeremie 570)
    old_msg = "Note 3 (℣ 16) has no latin_quote: “Ils sont tombés en foule ; ils ont été terrassés les uns sur les autre…”: one note split in two, or a lemma lost?"
    new_msg = "Note 3 (℣ 16) has no latin_quote: “_Ils sont tombés en foule ; ils ont été terrassés les uns sur les autr…”: one note split in two, or a lemma lost?"
    s1 = fp_sig("28_jeremie", 570, "no_lemma", old_msg)
    s2 = fp_sig("28_jeremie", 570, "no_lemma", new_msg)
    assert match_fp_sigs(s1, s2)

    # Case 2: Modernized spelling (Isaiah 481: IESUS -> JESUS)
    s3 = fp_sig("27_isaie", 481, "caps_in_commentary", "Capitals inside the comment: “…ui reviennent toujours à IESUS-CHRIST…”")
    s4 = fp_sig("27_isaie", 481, "caps_in_commentary", "Capitals inside the comment: “…ui reviennent toujours à JESUS-CHRIST…”")
    assert match_fp_sigs(s3, s4)

    # Case 3: Different note on same page must NOT match
    s5 = fp_sig("01_genese", 254, "no_translation", "Note 2 (℣ 3): latin_quote has no matching french_translation")
    s6 = fp_sig("01_genese", 254, "no_translation", "Note 4 (℣ 6): latin_quote has no matching french_translation")
    assert not match_fp_sigs(s5, s6)


def test_false_positives_class_matches():
    fp_id = "28_jeremie/0570/no_lemma/32a1282f"
    old_msg = "Note 3 (℣ 16) has no latin_quote: “Ils sont tombés en foule…”"
    sig = fp_sig("28_jeremie", 570, "no_lemma", old_msg)
    fps = FalsePositives([fp_id], [sig])

    # Exact ID match
    assert fp_id in fps

    # Mutated text generates a different hash / new ID
    new_id = "28_jeremie/0570/no_lemma/99999999"
    new_msg = "Note 3 (℣ 16) has no latin_quote: “_Ils sont tombés en foule…”"
    assert fps.matches(new_id, "28_jeremie", 570, "no_lemma", new_msg)

    # After matching, new_id is cached for fast lookup
    assert new_id in fps

    # Different page or kind must not match
    assert not fps.matches("28_jeremie/0571/no_lemma/88888888", "28_jeremie", 571, "no_lemma", new_msg)
    assert not fps.matches("28_jeremie/0570/other_kind/77777777", "28_jeremie", 570, "other_kind", new_msg)
