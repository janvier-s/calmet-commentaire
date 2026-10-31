"""The OCR overlay's alignment, on small made-up pages (no Kraken, no real data)."""
import scan_ocr as O


def line(y, *words, wc=0.99, sl=None):
    """A line of words; `sl`: their slants (one each), as scan_slant.py measures them."""
    x, out = 340, []
    for k, w in enumerate(words):
        out.append({"t": w, "box": [x, y, 20 * len(w), 30], "wc": wc, "sl": sl and sl[k]})
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


def test_gap_put_in_after_the_word_before_it_in_modern_spelling():
    o = ocr(line(300, "ou", "Ajoth,", "comme", "quelques", "exemplaires", "des", "Septante,", "ou", "Judé,", "comme"),
            line(340, "lit", "Joſeph,", "étoit", "de", "la", "tribu"))
    d = page("ou _Ajoth_, comme _Judé_, comme lit Joseph, était de la tribu")
    [g] = O.gaps(o, d)
    assert (g["path"], g["ocr"], g["text"]) == ("commentary/0/french_commentary", "quelques exemplaires des Septante, ou",
                                                "quelques exemplaires des Septante, ou")
    s = d["commentary"][0]["french_commentary"]
    assert O.insert(s, g["pos"], g["text"]) == "ou _Ajoth_, comme quelques exemplaires des Septante, ou _Judé_, comme lit Joseph, était de la tribu"


def test_no_gap_for_one_word_an_unsure_run_or_a_reference():
    d = page("ils étaient du voyage du désert et le reste")
    assert O.gaps(ocr(line(300, "ils", "étoient", "seuls", "du", "voyage", "du", "désert", "&", "le", "reste")), d) == []
    assert O.gaps(ocr(line(300, "ils", "étoient", "du"), line(340, "xqzw", "olaolas", "glodo", wc=0.7),
                      line(380, "voyage", "du", "désert", "&", "le", "reste")), d) == []
    assert O.gaps(ocr(line(300, "ils", "étoient", "du", "voyage", "du", "désert", "Judic.", "XVII.", "4.", "&", "le", "reste")), d) == []


def test_a_run_opening_with_a_lemma_is_a_whole_note():
    o = ocr(line(300, "la", "fin", "du", "texte."), line(340, "10.ET", "FUIT", "IN", "EO", "SPIRITUS", "DOMINI.", "Il", "fut", "rempli"))
    [g] = O.gaps(o, page("la fin du texte."))
    assert g["note"]


def test_italics_the_scan_has_and_the_text_lacks_and_the_other_way():
    o = ocr(line(300, "Il", "vint", "dans", "Aïalon,", "puis", "il", "dit:", sl=[0, -1, 1, 16, 0, 0, -2]),
            line(340, "Je", "suis", "dit-il", "votre", "Dieu", sl=[14, 15, -1, 16, 15]))
    d = page("Il vint dans Aïalon, puis il dit : _Je suis, dit-il, votre Dieu_")
    r = O.italics(o, d)
    assert [(x["to"], x["old"]) for x in r] == [("italic", "Aïalon"), ("roman", "dit-il")]
    assert r[0]["new"] == "Il vint dans _Aïalon_, puis il dit : _Je suis, dit-il, votre Dieu_"
    assert r[1]["new"] == "Il vint dans Aïalon, puis il dit : _Je suis,_ dit-il_, votre Dieu_"


def test_no_italics_for_a_lone_word_that_leans_anyway_or_hardly():
    o = ocr(line(300, "les", "voyes", "du", "Seigneur", "sont", "droites", sl=[0, 15, 0, 10, 0, 1]))
    assert O.italics(o, page("les voies du Seigneur sont droites")) == []
