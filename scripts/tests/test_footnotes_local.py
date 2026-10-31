"""footnotes.py's local stage (no Claude): notes of Bible references written out, flags set."""
import pytest

import footnotes as F

JEREMIE_4_5 = F.B.find_refs("Jerem. 4. 5.")[0]


def note(text, chap=5):
    return dict(id="0001a", page="page_0001", marker="(a)", chap=chap, verse=1, before="", after="",
                text=text, raw="", vol_book="Isaïe", why=[], flags=[])


@pytest.mark.parametrize("text, written", [
    ("Genes. 3. 4.", "Genèse 3:4."),
    ("Vide Exod. 12. 3.", "Voyez Exode 12:3."),
    ("Psalm. 22. 1. confer Matth. 27. 46.", "Psaumes 22:1 ; comparez Matthieu 27:46."),
    ("Isai. 7. 14. etc.", "Isaïe 7:14 etc."),
    ("Gen. 3. 4. & seq.", "Genèse 3:4 et suivants."),
    ("Matth. 5. 3. 4. Luc. 6. 20.", "Matthieu 5:3-4 ; Luc 6:20."),      # 4 is a verse, not "4 Luc"
    ("Psal. 31. 1. 2. Reg. 3. 4.", "Psaumes 31:1 ; 2 Rois 3:4."),       # 2 is the book's number
    ("Ibid. v. 7.", "Jérémie 4:7."),  # the reference before
    ("v. 9.", "Isaïe 5:9."),          # the volume's book and the note's chapter
])
def test_references_written_out(text, written):
    assert F.render_bible(note(text), JEREMIE_4_5)[0] == written


@pytest.mark.parametrize("text", ["Aug. l. 4. Confess.", "Gen. 3. 4. [UNCERTAIN WORD]"])
def test_not_references_alone(text):
    assert F.render_bible(note(text), JEREMIE_4_5) is None


def test_local_stage_carries_the_reference_over_and_flags_uncertain_words():
    ns = [note("Genes. 3. 4."), note("Ibid. v. 7."), note("Gen. 3. 4. [UNCERTAIN WORD]"), note("Aug. l. 4. Confess.")]
    F.local_stage(ns)
    assert [n["proposed"] for n in ns] == ["Genèse 3:4.", "Genèse 3:7.", "Gen. 3. 4. [UNCERTAIN WORD]", "Aug. l. 4. Confess."]
    assert [n["done"] for n in ns] == [True, True, False, False]
    assert [n["flags"] for n in ns] == [[], [], ["uncertain"], []]
    assert ns[2]["scan_why"] == ["contains [UNCERTAIN WORD]"]
    assert ns[3]["prev"] == "Genèse 3:4"
