"""The audit's checks one at a time, on small made-up pages (no real data)."""
import pytest

import audit_integrity as A

VOL = "22_proverbes"
INFO = {"fr": "Proverbes", "studium": [VOL], "vul": "proverbs"}


@pytest.fixture(autouse=True)
def no_false_positives(monkeypatch):
    monkeypatch.setattr(A, "FP_IDS", A.FalsePositives())


def book(*pages):
    """A Book holding these pages, numbered 1, 2, … unless given as (number, page)."""
    b = A.Book("proverbs", INFO, "proverbes")
    for k, p in enumerate(pages, 1):
        no, p = p if isinstance(p, tuple) else (k, p)
        b.pages.append((VOL, f"page_{no:04d}.json", p))
    return b


def note(lemma=None, tr=None, fc=None, ref=1, cid=2, ch=1):
    return dict(commentary_id=cid, verse_ref=ref, chapter=ch, latin_quote=lemma,
                french_translation=tr, french_commentary=fc)


def kinds(b):
    return [q["kind"] for q in b.queue]


def run(check, b):
    """A per-note check over every note of every page."""
    for i, (_, _, d) in enumerate(b.pages):
        for j in range(len(d.get("commentary") or [])):
            check(b, A.Note(b, i, j))
    return kinds(b)


def test_page_gaps_name_the_missing_range():
    b = book((1, {}), (2, {}), (6, {}))
    b.r["malformed"] = []
    A.page_gaps(b)
    assert b.r["page_number_gaps"] == [f"{VOL}/page_0003–0005"]


def test_seams_continuation_after_full_stop():
    b = book({"commentary": [note("A.", "A.", "Fin de phrase.")]},
             {"commentary": [note(None, None, "suite en minuscule.", ref=None)]})
    A.page_seams(b)
    assert [s["kind"] for s in b.r["suspicious_seams"]] == ["gap? continuation after a full stop"]


def test_empty_commentary_followed_by_a_block_without_lemma():
    b = book({"commentary": [note("MELIOR EST.", "Il vaut mieux.", ""), note(None, None, "suite.", cid=3)]})
    assert "empty_commentary" in run(A.empty_commentary, b)
    assert b.counts["empty_commentary"] == 1


def test_lemma_alone_at_the_foot_of_the_page_is_fine():
    b = book({"commentary": [note("MELIOR EST", None, "")]})
    assert run(A.empty_commentary, b) == []


def test_hyphen_cut_when_the_next_page_does_not_go_on():
    b = book({"commentary": [note("SERVUS SAPI-", None, "")]},
             {"commentary": [note(None, None, "Un esclave sage.", ref=None, cid=1)]})
    assert run(A.hyphen_cut, b) == ["hyphen_cut"]


def test_hyphen_cut_not_when_the_lemma_goes_on_overleaf():
    b = book({"commentary": [note("SERVUS SAPI-", None, "")]},
             {"commentary": [note("ENS.", "Le serviteur sage.", "Un esclave.", cid=1)]})
    assert run(A.hyphen_cut, b) == []


def test_field_ends_on_a_note_followed_by_another():
    b = book({"commentary": [note("MELIOR EST", "il vaut mieux", "x."), note("SERVUS.", "Le serviteur.", "y.", cid=3)]})
    assert run(A.field_ends, b) == ["translation_no_punct", "lemma_no_punct"]


def test_no_lemma_after_the_first_block():
    b = book({"commentary": [note("A.", "A.", "a."), note(None, "Le serviteur.", "Un esclave.", cid=3)]})
    assert run(A.no_lemma, b) == ["no_lemma"]


def test_ref_order_goes_back_within_a_chapter():
    b = book({"commentary": [note("A.", ref=5, cid=1), note("B.", ref=3, cid=2)]})
    A.ref_order(b)
    assert kinds(b) == ["ref_order"]
    assert b.queue[0]["where"] == dict(section="commentary", index=1, field="verse_ref")


def test_chapter_field_skipping_a_chapter():
    b = book({"verses": [dict(chapter=1, verse_number=1), dict(chapter=3, verse_number=1)]})
    A.chapter_field(b)
    assert [q["msg"] for q in b.queue] == ["verses: chapter goes from 1 to 3 at verse_number 1"]


def test_missing_french_or_filled_from_the_vulgate():
    b = book({"verses": [dict(chapter=1, verse_number=1, latin="Parabolae.", french=""),
                         dict(chapter=1, verse_number=2, latin="Ad sciendam.", french=None,
                              annotations="Latin from the Vulgate")]})
    A.missing_french(b)
    assert kinds(b) == ["missing_french", "vulgate_filled"]


def test_item_skips_false_positives(monkeypatch):
    b = book()
    assert b.item("no_lemma", VOL, 1, "msg")
    monkeypatch.setattr(A, "FP_IDS", A.FalsePositives({b.queue[0]["id"]}))
    assert not b.item("no_lemma", VOL, 1, "msg")
    assert len(b.queue) == 1


def test_names_left_untranslated_are_optional():
    b = book({"commentary": [note("LOD, HADID, ET ONO.", None, "Ce sont des villes."),
                             note("EN-GANNIM.", None, "Ville des Lévites.", cid=3),
                             note("QUASI STORAX.", None, "Le storax est une liqueur.", cid=4)]})
    run(A.translation_length, b)
    assert [q["optional"] for q in b.queue] == [True, True, False]


def test_long_translation_of_a_lemma_cut_with_etc_is_optional():
    tr = "Celui qui justifie l'injuste, et celui qui condamne le juste, sont tous deux abominables devant Dieu."
    b = book({"commentary": [note("QUI JUSTIFICAT IMPIUM, ETC.", tr, "x."), note("QUI JUSTIFICAT.", tr, "y.", cid=3)]})
    run(A.translation_length, b)
    assert [q["optional"] for q in b.queue] == [True, False]


def test_ou_for_aut_or_a_gloss_is_not_flagged():
    b = book({"commentary": [note("IN STAMINE, AUT SUBTEGMINE.", "Dans la chaîne, ou dans la trame.", "x."),
                             note("TUUM EST DECUS.", "La gloire _(ou la beauté)_ vous appartient.", "y.", cid=3),
                             note("TUUM EST DECUS.", "La gloire, ou la beauté vous appartient.", "z.", cid=4),
                             note("IN STAMINE, AUT SUBTEGMINE.", "Dans la chaîne, à la lettre, ou la trame.", "w.", cid=5)]})
    assert run(A.hebrew_in_translation, b) == ["hebrew_in_translation"] * 2
    assert [q["where"]["index"] for q in b.queue] == [2, 3]
