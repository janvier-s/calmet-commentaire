"""The OCR overlay's alignment, on small made-up pages (no Kraken, no real data)."""
import scan_ocr as O


def line(y, *words, wc=0.99):
    x, out = 340, []
    for w in words:
        out.append({"t": w, "box": [x, y, 20 * len(w), 30], "wc": wc})
        x += 20 * len(w) + 15
    return {"box": [340, y, x - 355, 30], "words": out}


def ocr(*lines):
    return {"size": [1479, 1969], "lines": list(lines)}


def page(commentary, latin=None):
    return {"verses": [{"verse_number": 1, "latin": latin, "french": None}] if latin else [],
            "commentary": [{"latin_quote": None, "french_translation": None, "french_commentary": commentary}],
            "footnotes": []}


def statuses(r):
    return [(w["t"], w["s"]) for w in r["words"]]


def test_old_spelling_is_the_same_word():
    r = O.align(ocr(line(300, "S.", "Augustin", "croit", "qu’il", "avoit", "&", "Moy¬"), line(340, "se")),
                page("Saint Augustin croit qu'il avait et Moïse"))
    assert {s for _, s in statuses(r)} == {"ok"}
    assert r["extra"] == []


def test_running_header_and_commentaire_are_skipped():
    r = O.align(ocr(line(80, "COMMENTAIRE", "LITTERAL"), line(232, "COMMENTAIRE."), line(300, "le", "texte")),
                page("le texte"))
    assert statuses(r) == [("le", "ok"), ("texte", "ok")]


def test_missing_word_and_its_link():
    r = O.align(ocr(line(300, "une", "chose", "grande", "de", "Dieu")), page("une chose de Dieu"))
    assert ("grande", "missing") in statuses(r)
    dieu = r["words"][-1]
    assert (dieu["path"], dieu["a"], dieu["b"]) == ("commentary/0/french_commentary", 13, 17)


def test_two_words_run_together_in_the_json():
    r = O.align(ocr(line(120, "et", "tulit", "sicam", "de", "dextro")), page(None, latin="et tulissicam de dextro"))
    assert statuses(r)[1:3] == [("tulit", "diff"), ("sicam", "diff")]
    assert r["words"][1]["path"] == "verses/0/latin"


def test_a_space_lost_by_the_ocr_is_not_flagged():
    r = O.align(ocr(line(300, "QUI", "STATIMSURREXIT", "DE")), page("QUI STATIM SURREXIT DE"))
    assert {s for _, s in statuses(r)} == {"ok"}
    assert r["extra"] == []


def test_word_only_in_the_json_is_extra():
    r = O.align(ocr(line(300, "une", "chose", "de", "Dieu")), page("une chose grande de Dieu"))
    assert [w["t"] for w in r["extra"]] == ["grande"]


def test_unsure_reading_is_not_flagged():
    r = O.align(ocr(line(300, "le", "texte"), line(340, "xqzw", wc=0.3)), page("le texte"))
    assert statuses(r)[-1] == ("xqzw", "skip")


def test_ocr_slips_and_doubled_letters_are_not_flagged():
    r = O.align(ocr(line(300, "une", "salte", "pour", "jetter", "et", "traduite", "ils", "se", "déchaussent")),
                page("une salle pour jeter et traduire ils se déchaussaient"))
    assert [s for _, s in statuses(r)] == ["ok"] * 8 + ["near"]
