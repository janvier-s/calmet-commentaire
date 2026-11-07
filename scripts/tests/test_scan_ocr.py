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


def verses_page(latin, french):
    """A page with one verse holding both its fields."""
    return {"verses": [{"verse_number": 1, "latin": latin, "french": french}], "commentary": [], "footnotes": []}


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
            line(340, "Je", "suis", "dit-il", "à", "tous", "ici", "votre", "Dieu", sl=[14, 15, -1, -2, -1, 0, 16, 15]))
    d = page("Il vint dans Aïalon, puis il dit : _Je suis, dit-il à tous ici, votre Dieu_")
    r = O.italics(o, d)
    assert [(x["to"], x["old"]) for x in r] == [("italic", "Aïalon"), ("roman", "dit-il à tous ici")]
    assert r[0]["new"] == "Il vint dans _Aïalon_, puis il dit : _Je suis, dit-il à tous ici, votre Dieu_"
    assert r[1]["new"] == "Il vint dans Aïalon, puis il dit : _Je suis,_ dit-il à tous ici_, votre Dieu_"


def test_no_italics_for_a_lone_word_that_leans_anyway_or_hardly():
    o = ocr(line(300, "les", "voyes", "du", "Seigneur", "sont", "droites", sl=[0, 15, 0, 10, 0, 1]))
    assert O.italics(o, page("les voies du Seigneur sont droites")) == []


def test_a_few_words_measured_roman_inside_italics_are_a_misread_glyph():
    o = ocr(line(300, "Sur", "la", "montagne", "aux", "Tuiles,", sl=[14, 15, -3, 16, 17]))
    assert O.italics(o, page("_Sur la montagne aux Tuiles,_")) == []


def test_small_words_vote_when_clear_and_note_letters_and_pieces_do_not():
    o = ocr(line(300, "Il", "dit", "à", "vous", "ne", sl=[0, 0, 15, 15, 0]))  # alone, no issue (a lone short word)
    assert [x["old"] for x in O.italics(o, page("Il dit à vous ne"))] == ["à vous"]
    o = ocr(line(300, "Il", "dit", "(a)", "vous", "ne", sl=[0, 0, 15, 0, 0]))
    assert O.italics(o, page("Il dit a vous ne")) == []


def test_a_body_line_in_the_top_band_opening_with_sur_is_read():
    r = O.align(ocr(line(80, "SUR", "LES", "JUGES."), line(130, "sur", "lui,", "ce", "qu’il", "avoit")),
                page("sur lui, ce qu'il avait"))
    assert {s for _, s in statuses(r)} == {"ok"} and r["unscanned"] == []


def test_the_margin_year_with_a_comma_ends_the_line():
    r = O.align(ocr(line(300, "celui", "qui", "reprend", "An-2917,"), line(340, "sur", "lui")),
                page("celui qui reprend sur lui"))
    assert statuses(r)[3] == ("An-2917", "skip") and {s for _, s in statuses(r)} == {"ok", "skip"}


def test_spelling_pairs_and_the_modernizer_make_old_words_the_same():
    assert O.key("Caldéen") == O.key("Chaldéen") and O.key("loix") != O.key("lois")
    r = O.align(ocr(line(300, "les", "loix", "des", "Caldéens", "entr’eux")), page("les lois des Chaldéens entre eux"))
    assert {s for _, s in statuses(r)} == {"ok"}


def test_words_the_scan_lacks_between_words_it_has():
    o = ocr(line(300, "Il", "passe", "le", "Jourdain", "avec", "ses", "gens"))
    r = O.align(o, page("Il passe le Jourdain sans aucun bateau avec ses gens"))
    assert [(x["path"], page("Il passe le Jourdain sans aucun bateau avec ses gens")["commentary"][0]["french_commentary"][x["a"]:x["b"]])
            for x in r["unscanned"]] == [("commentary/0/french_commentary", "sans aucun bateau")]


def test_no_unscanned_run_where_the_scan_has_misread_words():
    r = O.align(ocr(line(300, "Il", "passe", "Orda", "concubinc", "quixz", "avec", "ses", "gens")),
                page("Il passe Or sa concubine qui avec ses gens"))
    assert r["unscanned"] == []


def test_the_text_running_on_past_the_scan_page_is_flagged():
    d = page("Zeb était caché dans une de ces cavernes souterraines du roc")
    r = O.align(ocr(line(300, "Zeb", "étoit", "caché")), d)
    assert [x.get("end") for x in r["unscanned"]] == [True]


def test_align_gives_each_word_its_slant():
    o = ocr(line(300, "Il", "vint", "dans", sl=[0, 14.6, None]))
    w = O.align(o, page("Il vint dans"))["words"]
    assert [x.get("sl") for x in w] == [0, 15, None]


def test_italics_take_in_a_word_cut_at_its_apostrophe():
    o = ocr(line(300, "Il", "dit", "qu’il", "enleva", "les", "deux", "portes", sl=[0, 0, 15, 16, 15, 15, 16]))
    (it,) = O.italics(o, page("Il dit qu'il enleva les deux portes"))
    assert it["to"] == "italic" and it["old"] == "qu'il enleva les deux portes"


def test_default_is_todays_alignment():
    o, d = ocr(line(300, "le", "troupeaur")), page("le troupeaux")
    assert O.align(o, d) == O.align(o, d, fix=False)


def test_fix_pairs_a_misread_left_unpaired():
    r = O.align(ocr(line(300, "Nequanda", "dicat", "inimi-I"), line(340, "eus", "meus")),
                page("Nequando dicat inimicus meus"), fix=True)
    assert "missing" not in {s for _, s in statuses(r)} and r["extra"] == []


def test_fix_joins_a_split_without_any_hyphen():
    r = O.align(ocr(line(300, "ils", "répom"), line(340, "dent", "ainsi")), page("ils répondent ainsi"), fix=True)
    assert "missing" not in {s for _, s in statuses(r)} and r["extra"] == []


def test_fix_keeps_a_word_only_on_the_scan_red():
    r = O.align(ocr(line(300, "il", "dit", "alors", "ceci")), page("il dit ceci"), fix=True)
    assert ("alors", "missing") in statuses(r)


def test_fix_keeps_a_deletion_beside_an_unrelated_addition_red():
    r = O.align(ocr(line(300, "il", "dit", "alors", "ceci")), page("il dit pourtant ceci"), fix=True)
    assert ("alors", "missing") in statuses(r) and [e["t"] for e in r["extra"]] == ["pourtant"]


def test_fix_never_pairs_across_the_verse_columns():
    right = {"box": [800, 300, 100, 30], "words": [{"t": "aurez", "box": [800, 300, 100, 30], "wc": .99}]}
    r = O.align(ocr(line(300, "manfueris"), right), verses_page(latin="fueris", french="vous aurez"), fix=True)
    assert not any(w["t"] == "aurez" and w.get("path", "").endswith("/latin") for w in r["words"])


def test_fix_never_pairs_a_verse_number_with_a_word():
    r = O.align(ocr(line(300, "6", "Quæ", "dixit")), verses_page(latin="Quæ dixit", french=None), fix=True)
    assert "path" not in r["words"][0]


def test_fix_still_pairs_a_number_with_a_number():
    assert ("37", "ok") in statuses(O.align(ocr(line(300, "chap.", "37")), page("chapitre 37"), fix=True))


def test_fix_pairs_on_the_right_half_of_a_commentary_page():
    o = ocr({"box": [800, 300, 300, 30], "words": [{"t": "parple", "box": [800, 300, 120, 30], "wc": .99}]})
    assert O.align(o, page("parole"), fix=True)["words"][0].get("path") == "commentary/0/french_commentary"


def test_leftovers_are_not_paired_across_two_fields():
    d = {"verses": [], "footnotes": [], "commentary": [
        {"latin_quote": None, "french_translation": None, "french_commentary": "il dit"},
        {"latin_quote": None, "french_translation": None, "french_commentary": "parole vraie"}]}
    r = O.align(ocr(line(300, "il", "dit", "Xparolx"), line(340, "vraie")), d, fix=True)
    paths = [w.get("path") for w in r["words"]]
    assert paths[:2] == ["commentary/0/french_commentary"] * 2 and paths[3] == "commentary/1/french_commentary"


def test_the_words_are_the_same_with_and_without_fix():
    o, d = ocr(line(300, "le", "troupeaur", "alors")), page("le troupeaux")
    assert [w["t"] for w in O.align(o, d)["words"]] == [w["t"] for w in O.align(o, d, fix=True)["words"]]


def test_fix_keeps_a_right_column_word_out_of_the_latin():
    right = {"box": [800, 300, 100, 30], "words": [{"t": "aurez", "box": [800, 300, 100, 30], "wc": .99}]}
    o, d = ocr(line(300, "fueris"), right), verses_page(latin="fueris aurem", french="vous")
    assert O.align(o, d)["words"][1]["path"] == "verses/0/latin"  # today: paired across the gutter
    assert "path" not in O.align(o, d, fix=True)["words"][1]


def test_fix_keeps_a_roman_verse_number_out_of_a_word():
    o, d = ocr(line(300, "et", "VI", "dixit")), verses_page(latin="et vir dixit", french=None)
    assert O.align(o, d)["words"][1]["s"] == "near"  # today: VI read as vir
    assert "path" not in O.align(o, d, fix=True)["words"][1]


def _leftovers(commentary, *words, linked, **kw):
    """`words` read, those of `linked` ({scan index: json index}) linked, the rest left to _repair_leftovers."""
    ot = O.ocr_tokens(ocr(line(300, *words)))
    jt = O.json_tokens({"verses": [], "footnotes": [], "commentary": [
        {"latin_quote": None, "french_translation": None, "french_commentary": c} for c in commentary]})
    res = [dict(t=t["t"]) for t in ot]

    def link(i, j, status, n=1):
        res[i].update(s=status, path=jt[j]["path"], a=jt[j]["a"], b=jt[j + n - 1]["b"])
    for i, j in linked.items():
        link(i, j, "ok")
    O._repair_leftovers(res, ot, jt, link, None, **kw)
    return [(r["t"], r.get("path"), r.get("a")) for r in res]


def test_leftovers_pair_with_the_unpaired_between_their_neighbours():
    out = _leftovers(["il dit répondent ainsi"], "il", "dit", "répom", "dent", "ainsi", linked={0: 0, 1: 1, 4: 3})
    assert out[2:4] == [("répom", "commentary/0/french_commentary", 7), ("dent", "commentary/0/french_commentary", 7)]


def test_leftovers_need_the_likeness_asked():
    out = _leftovers(["il dit répondent ainsi"], "il", "dit", "répom", "dent", "ainsi", linked={0: 0, 1: 1, 4: 3}, least=0.95)
    assert [p for _, p, _ in out[2:4]] == [None, None]


def test_leftovers_stay_out_of_a_field_neither_neighbour_is_in():
    out = _leftovers(["il", "répondent", "ainsi"], "il", "répondent", "ainsi", linked={0: 0, 2: 2})
    assert out[1][1] is None


def test_fix_pairs_a_number_with_a_range():
    r = O.align(ocr(line(300, "versets", "52", "ainsi")), page("versets 51-52 ainsi"), fix=True)
    assert r["words"][1].get("path") == "commentary/0/french_commentary"


def test_fix_pairs_the_same_word_across_the_gutter():
    right = {"box": [800, 300, 100, 30], "words": [{"t": "au", "box": [800, 300, 40, 30], "wc": .99},
                                                   {"t": "rem", "box": [855, 300, 60, 30], "wc": .99}]}
    r = O.align(ocr(line(300, "dixit"), right), verses_page(latin="dixit aurem", french="vous"), fix=True)
    assert [w.get("path") for w in r["words"][1:]] == ["verses/0/latin"] * 2


def test_the_gutter_is_the_right_columns_start_else_045():
    tok = lambda x: {"t": "aurez", "boxes": [[x, 300, 100, 30]]}
    latin = {"t": "aurem", "path": "verses/0/latin"}
    left_only = ocr(line(300, "dixit"))  # no line starts mid-page: the right column from 0.45 of the width
    assert not O._allow(left_only)(tok(700), latin) and O._allow(left_only)(tok(600), latin)
    two = ocr(line(300, "dixit"), {"box": [900, 340, 100, 30], "words": []})
    assert O._allow(two)(tok(700), latin) and not O._allow(two)(tok(875), latin)


def test_fix_pairs_a_numeral_with_the_same_numeral():
    d = {"chapter_title": "PSEAUME XC", "verses": [], "commentary": [], "footnotes": []}
    r = O.align(ocr(line(300, "PSEAUME", "X", "C")), d, fix=True)
    assert [w.get("path") for w in r["words"]] == ["chapter_title"] * 3


def test_fix_pairs_a_numeral_that_is_a_slip_for_a_word():
    assert ("II", "ok") in statuses(O.align(ocr(line(300, "dit", "II", "vient")), page("dit Il vient"), fix=True))


def test_fix_does_not_flag_the_margin_year_the_json_keeps():
    d = {"verses": [{"verse_number": 1, "annotations": "An. 2585", "latin": "Et dixit", "french": None}],
         "commentary": [], "footnotes": []}
    r = O.align(ocr(line(300, "Et", "dixit")), d, fix=True)
    assert r["extra"] == []
    assert [e["t"] for e in O.align(ocr(line(300, "Et", "dixit")), d)["extra"]] == ["An"]  # today: flagged


def test_fix_skips_misread_roman_numerals():
    r = O.align(ocr(line(300, "xII", "Et", "dixit", "L2")), verses_page(latin="Et dixit", french=None), fix=True)
    assert ("xII", "skip") in statuses(r) and ("L2", "skip") in statuses(r)


def test_fix_still_flags_latin_words_made_of_numeral_letters():
    r = O.align(ocr(line(300, "Et", "dixi", "dic", "vix", "mi")), page("Et"), fix=True)  # a Latin quotation in the commentary
    assert {t for t, s in statuses(r) if s == "missing"} == {"dixi", "dic", "vix", "mi"}


def test_fix_still_flags_a_capitalized_word_made_of_numeral_letters():
    r = O.align(ocr(line(300, "et", "Il", "Civil", "vint")), page("et vint"), fix=True)
    assert {t for t, s in statuses(r) if s == "missing"} == {"Il", "Civil"}


def test_fix_skips_a_misread_running_head():  # Juges p. 232 (COMMENTAIRF. at 0.083), p. 171, p. 155
    o = ocr(line(30, "SURLESIUGES", "CHNR", "VIII."), line(55, "S'UR", "LES"), line(160, "COMMENTAIRF."), line(300, "le", "texte"))
    assert statuses(O.align(o, page("le texte"), fix=True)) == [("le", "ok"), ("texte", "ok")]
    assert ("COMMENTAIRF", "missing") in statuses(O.align(o, page("le texte")))  # today: red


def test_fix_reads_a_lemma_or_a_head_misread_below_the_top_band():
    o = ocr(line(80, "V.", "JO.FERTE", "SENTENTIAM."), line(300, "COMMENTAIRF."), line(340, "le", "texte"))
    r = O.align(o, page("FERTE SENTENTIAM le texte"), fix=True)
    assert ("SENTENTIAM", "ok") in statuses(r) and ("COMMENTAIRF", "missing") in statuses(r)


def test_leftovers_join_only_json_words_next_to_each_other():
    ot = O.ocr_tokens(ocr(line(300, "il", "répondent", "ainsi", "XX")))
    jt = O.json_tokens({"verses": [], "footnotes": [], "commentary": [
        {"latin_quote": None, "french_translation": None, "french_commentary": "il répon XX dent ainsi"}]})
    res = [dict(t=t["t"]) for t in ot]

    def link(i, j, status, n=1):
        res[i].update(s=status, path=jt[j]["path"], a=jt[j]["a"], b=jt[j + n - 1]["b"])
    for i, j in {0: 0, 2: 4, 3: 2}.items():
        link(i, j, "ok")
    O._repair_leftovers(res, ot, jt, link, None)
    assert res[1].get("b") != jt[2]["b"]  # not over XX, linked to the scan's last word


def tess(*words):
    return {"size": [1479, 1969], "words": [{"t": t, "box": b, "conf": 90} for t, b in words]}


def test_tesseract_pairs_a_garbled_word_kraken_could_not():
    o = ocr(line(300, "ejus", "xqdzmi", "in"))   # similar(key("xqdzmi"), key("sedenti")) = 0.31: Kraken alone cannot pair it
    r = O.align(o, verses_page(latin="ejus sedenti in", french=None), fix=True,
                tess=tess(("sedenti", o["lines"][0]["words"][1]["box"])))
    assert r["words"][1].get("by") == "tess" and r["extra"] == []


def test_tesseract_does_not_pair_a_real_deletion_with_an_unrelated_addition():
    o = ocr(line(300, "il", "dit", "alors", "ceci"))
    r = O.align(o, page("il dit pourtant ceci"), fix=True, tess=tess(("alors", o["lines"][0]["words"][2]["box"])))
    assert ("alors", "missing") in statuses(r)


def test_both_ocrs_against_the_json():
    o = ocr(line(300, "telles", "choses"))
    r = O.align(o, page("celles choses"), fix=True, tess=tess(("telles", [340, 300, 120, 30])))
    assert (r["tess"], r["words"][0]["s"]) == (True, "both")


def test_a_word_both_ocrs_read_stays_a_word_that_differs_marked_both():
    o, d = ocr(line(300, "telles", "choses", wc=0.99)), page("celles choses")
    fx = O.align(o, d, fix=True, tess=tess(("telles", [340, 300, 120, 30])))["words"]
    assert [(x["old"], x["new"], x.get("both")) for x in O.differs(o, d, fx)] == [("celles", "telles", True)]
    fx = O.align(o, d, fix=True)["words"]
    assert [(x["old"], x.get("both")) for x in O.differs(o, d, fx)] == [("celles", None)]


def test_not_both_when_tesseract_reads_the_json_word():
    o = ocr(line(300, "parple"))
    r = O.align(o, page("parole"), fix=True, tess=tess(("parole", [340, 300, 120, 30])))
    assert r["words"][0]["s"] != "both"


def test_not_both_for_numbers_and_pieces():
    o = ocr(line(300, "ma"), line(340, "culini"))
    r = O.align(o, verses_page(latin="masculini", french=None), fix=True,
                tess=tess(("ma", [340, 300, 40, 30]), ("culini", [340, 340, 120, 30])))
    assert "both" not in {w["s"] for w in r["words"]}


def test_no_tesseract_reading_falls_back_and_says_so():
    o, d = ocr(line(300, "telles")), page("celles")
    for t in (None, {"size": [1479, 1969], "words": []}):
        r = O.align(o, d, fix=True, tess=t)
        assert r["tess"] is False and r["words"][0]["s"] in ("diff", "near")


def test_leftovers_do_not_skip_unpaired_json_words_for_a_weak_likeness():  # Juges p. 286: nostrum deleted, nostram further on
    out = _leftovers(["dit in manus terram nostram", "eux"], "manus", "terram", "dit", "nostrum", "eux",
                     linked={0: 2, 1: 3, 2: 0, 4: 5})
    assert out[3] == ("nostrum", None, None)


def test_leftovers_still_skip_unpaired_json_words_for_a_near_word():
    out = _leftovers(["dit in manus terram nostrums", "eux"], "manus", "terram", "dit", "nostrum", "eux",
                     linked={0: 2, 1: 3, 2: 0, 4: 5})
    assert out[3][1:] == ("commentary/0/french_commentary", 20)


def test_fix_joins_two_scan_words_only_when_they_make_the_json_word():  # Juges p. 286: deux deleted before colomnes
    r = O.align(ocr(line(300, "il", "dit", "entre", "deux", "colomnes", "Dieu")), page("il dit entre colonnes Dieu"), fix=True)
    assert ("deux", "missing") in statuses(r) and r["words"][4]["s"] in ("ok", "near")


def test_plain_still_joins_two_scan_words_by_likeness():
    r = O.align(ocr(line(300, "il", "dit", "entre", "deux", "colomnes", "Dieu")), page("il dit entre colonnes Dieu"))
    assert [w["s"] for w in r["words"][3:5]] == ["diff", "diff"]


def test_fix_does_not_join_a_short_word_to_a_long_misread():  # et + miséricordieusemeut: the long word alone is likelier
    r = O.align(ocr(line(300, "il", "dit", "et", "miséricordieusemeut", "Dieu")),
                page("il dit miséricordieusement Dieu"), fix=True)
    assert ("et", "missing") in statuses(r) and r["words"][3]["s"] in ("ok", "near")


def test_tesseract_reading_nothing_beneath_does_not_join_a_scan_only_word():  # "" + "sedenti" made sedenti
    o = ocr(line(300, "ejus", "alors", "xqdzmi", "in"))
    r = O.align(o, verses_page(latin="ejus sedenti in", french=None), fix=True,
                tess=tess(("sedenti", o["lines"][0]["words"][2]["box"])))
    assert "path" not in r["words"][1]  # unpaired (and not red: the verses' Latin)


def test_tesseract_reading_nothing_beneath_does_not_join_in_the_commentary():
    o = ocr(line(300, "il", "dit", "alors", "xqdzmi", "ceci"))
    r = O.align(o, page("il dit pourtant ceci"), fix=True,
                tess=tess(("pourtant", o["lines"][0]["words"][3]["box"])))
    assert ("alors", "missing") in statuses(r)


def test_tesseract_reading_only_punctuation_is_no_reading():  # _key("") is "et"
    o = ocr(line(300, "il", "dit", "xqdzmi", "ceci"))
    r = O.align(o, page("il dit et ceci"), fix=True, tess=tess(("—", o["lines"][0]["words"][2]["box"])))
    assert r["words"][2].get("by") != "tess" and r["words"][2]["s"] != "ok"


def _verse_page_lines():
    """A verse page as the scan reads it: a Latin line (left), its French (right), the next Latin line..."""
    right = lambda y, *ws: {"box": [800, y, 300, 30], "words": [
        {"t": w, "box": [800 + 120 * k, y, 100, 30], "wc": .99} for k, w in enumerate(ws)]}
    return ocr(line(300, "Qui", "judicavit"), right(300, "Il", "jugea"), line(340, "soptem", "annis"), right(340, "sept", "ans"))


def test_leftovers_pair_between_neighbours_of_their_own_field():  # Juges p. 233: soptem between jugea and annis
    o = _verse_page_lines()
    ot = O.ocr_tokens(o)
    jt = O.json_tokens(verses_page(latin="Qui judicavit septem annis", french="Il jugea sept ans"))
    res = [dict(t=t["t"]) for t in ot]

    def link(i, j, status, n=1):
        res[i].update(s=status, path=jt[j]["path"], a=jt[j]["a"], b=jt[j + n - 1]["b"])
    for i, j in {0: 0, 1: 1, 2: 4, 3: 5, 5: 3, 6: 6, 7: 7}.items():
        link(i, j, "ok")
    O._repair_leftovers(res, ot, jt, link, O._allow(o))
    assert (res[4].get("path"), res[4].get("a")) == ("verses/0/latin", jt[2]["a"])


def test_no_red_in_the_verses_latin():
    o = _verse_page_lines()
    r = O.align(o, verses_page(latin="Qui judicavit pater septem annis", french="Il jugea sept ans"), fix=True)
    assert r["extra"] == [] and "missing" not in {w["s"] for w in r["words"]}
    assert [e["t"] for e in O.align(o, verses_page(latin="Qui judicavit pater septem annis",
                                                    french="Il jugea sept ans"))["extra"]][:1] == ["pater"]  # plain: red


def test_no_red_for_a_word_only_in_the_latin_column():
    o = _verse_page_lines()
    o["lines"][2]["words"].insert(0, {"t": "xqdzmi", "box": [300, 340, 60, 30], "wc": .99})
    r = O.align(o, verses_page(latin="Qui judicavit septem annis", french="Il jugea sept ans"), fix=True)
    assert ("xqdzmi", "skip") in statuses(r)


def test_still_red_in_the_verses_french():
    o = _verse_page_lines()
    r = O.align(o, verses_page(latin="Qui judicavit septem annis", french="Il jugea Israël sept ans"), fix=True)
    assert [e["t"] for e in r["extra"]] == ["Israël"]
    o["lines"][3]["words"].append({"t": "alors", "box": [1040, 340, 100, 30], "wc": .99})
    r = O.align(o, verses_page(latin="Qui judicavit septem annis", french="Il jugea sept ans"), fix=True)
    assert ("alors", "missing") in statuses(r)


def test_no_red_in_the_margin_notes():
    d = {"verses": [{"verse_number": 1, "annotations": "Hebr. Gedeon", "latin": "Et dixit", "french": None}],
         "commentary": [], "footnotes": []}
    assert O.align(ocr(line(300, "Et", "dixit")), d, fix=True)["extra"] == []


def _lemma_page(*words):
    d = {"verses": [], "footnotes": [], "commentary": [
        {"latin_quote": None, "french_translation": None, "french_commentary": "il dit ceci"},
        {"latin_quote": "VENITE SUB UMBRA", "french_translation": None, "french_commentary": "Le texte"}]}
    return O.align(ocr(line(300, *words)), d, fix=True)


def test_no_red_for_a_lemmas_verse_number():  # ỳ. 19. read Y19, VA7, IJ
    for mark in ("Y19", "VA7", "IJ"):
        assert (mark, "skip") in statuses(_lemma_page("il", "dit", "ceci", mark, "VENITE", "SUB", "UMBRA", "Le", "texte"))


def test_a_real_word_before_a_lemma_stays_red():
    assert ("champ", "missing") in statuses(_lemma_page("il", "dit", "ceci", "champ", "VENITE", "SUB", "UMBRA", "Le", "texte"))


def test_no_gap_for_the_commentaire_heading_misread():  # Juges p. 254: C.OM MENT.AIRE.
    o = ocr(line(300, "il", "dit", "C.OM", "MENT.AIRE.", "ceci", wc=0.99))
    assert O.gaps(o, page("il dit ceci"), least=2) == []


def test_fix_pairs_a_number_printed_with_et():  # Juges p. 160: soixante & dix-sept, soixante-dix-sept
    r = O.align(ocr(line(300, "les", "soixante", "&", "dix-sept", "hommes")), page("les soixante-dix-sept hommes"), fix=True)
    assert [w["s"] for w in r["words"]] == ["ok"] * 5 and r["extra"] == []
    r = O.align(ocr(line(300, "les", "soixante", "&", "dix", "fils")), page("les soixante-dix fils"), fix=True)
    assert "missing" not in {w["s"] for w in r["words"]} and r["extra"] == []


def test_three_scan_words_are_not_joined_by_likeness():
    r = O.align(ocr(line(300, "il", "dit", "soit", "&", "dix", "ceci")), page("il dit soixante-dix ceci"), fix=True)
    links = [(w.get("path"), w.get("a")) for w in r["words"] if "path" in w]
    assert max(links.count(x) for x in links) < 3  # soit is no number: no join of three


def test_et_before_a_lone_number_stays_red():
    assert ("et", "missing") in statuses(O.align(ocr(line(300, "il", "dit", "et", "dix", "fils")), page("il dit dix fils"), fix=True))


def test_no_italics_vote_for_the_ampersand():  # the & leans in roman too: 852 issues "et" corpus-wide
    o = ocr(line(300, "branche", "&", "&c.", "pour", "lui", sl=[0, 16, 17, 0, 0]))
    assert O.italics(o, page("branche et etc. pour lui")) == []


def test_no_italics_vote_for_a_notes_letter_numbers_or_a_books_name():  # ^{(f)}, Les 70 (LXX), Psal. cxviii. 17
    o = ocr(line(300, "commerce", "f", "Les", "LXX", "voyez", "Psal.", "118:17", "ici", sl=[0, 16, 0, 16, 0, 17, 0, 0]))
    assert O.italics(o, page("commerce ^{(f)} Les 70 voyez Psaumes 118:17 ici")) == []


def test_no_italics_for_a_scan_word_the_text_already_splits():  # d'_Achat_: d' roman, the name italic
    o = ocr(line(300, "assez", "d'Achat", "ou", "Acada", sl=[0, 16, 0, 16]))
    assert O.italics(o, page("assez d'_Achat_ ou _Acada_")) == []


def test_italics_still_found_beside_an_ampersand():
    o = ocr(line(300, "il", "dit", "le", "firmament", "du", "Ciel", "&", "puis", sl=[0, 0, 16, 17, 16, 17, 16, 0]))
    assert [(x["to"], x["old"]) for x in O.italics(o, page("il dit le firmament du Ciel et puis"))] == [("italic", "le firmament du Ciel")]


def test_italics_take_in_a_first_word_too_unclear_to_vote():  # La terre de Sual: La at 10 degrees votes not
    o = ocr(line(300, "Jourdain", "La", "terre", "de", "Sual", "ou", sl=[0, 10, 16, 15, 17, 0]))
    r = O.italics(o, page("Jourdain La terre de Sual ou"))
    assert [(x["old"], x["new"]) for x in r] == [("La terre de Sual", "Jourdain _La terre de Sual_ ou")]


def test_italics_do_not_take_in_a_roman_neighbour():
    o = ocr(line(300, "Jourdain", "La", "terre", "de", "Sual", "ou", sl=[0, 3, 16, 15, 17, 0]))
    assert [x["old"] for x in O.italics(o, page("Jourdain La terre de Sual ou"))] == ["terre de Sual"]


def test_italics_leave_the_elision_before_a_name_roman():  # d'Achad: the d' roman, the name italic
    o = ocr(line(300, "assez", "d’", "Achat", "Acada", "ou", sl=[0, 3, 16, 17, 0]))
    assert [x["new"] for x in O.italics(o, page("assez d'Achat Acada ou"))] == ["assez d'_Achat Acada_ ou"]
    o = ocr(line(300, "ville", "d’Achad", "ici", sl=[0, 16, 0]))
    assert [x["new"] for x in O.italics(o, page("ville d'Achad ici"))] == ["ville d'_Achad_ ici"]
    o = ocr(line(300, "dit", "qu’Arphaxad", "ici", sl=[0, 16, 0]))
    assert [x["new"] for x in O.italics(o, page("dit qu'Arphaxad ici"))] == ["dit qu'_Arphaxad_ ici"]


def test_italics_take_in_the_elision_before_a_common_word():  # _d'un homme sage_
    o = ocr(line(300, "parole", "d’un", "homme", "sage", "ici", sl=[0, 16, 16, 17, 0]))
    assert [x["new"] for x in O.italics(o, page("parole d'un homme sage ici"))] == ["parole _d'un homme sage_ ici"]


def test_a_split_elision_is_made_whole():
    o = ocr(line(300, "assez", "d", "Achat", "Acada", "ou", sl=[0, 16, 17, 17, 0]))
    assert [x["new"] for x in O.italics(o, page("assez _d_'Achat Acada ou"))] == ["assez _d'Achat Acada_ ou"]


def test_italics_do_not_take_in_a_notes_mark():
    o = ocr(line(300, "dit", "f", "Comme", "la", "prairie", "ou", sl=[0, 11, 16, 15, 17, 0]))
    assert [x["new"] for x in O.italics(o, page("dit ^{(f)} Comme la prairie ou"))] == ["dit ^{(f)} _Comme la prairie_ ou"]


def test_no_italics_for_a_lone_short_word():  # Juges p. 228: ſes read fes, roman on the scan, at 15 degrees
    o = ocr(line(300, "dans", "fes", "pieds", "dit", sl=[0, 16, 0, 0]))
    assert O.italics(o, page("dans ses pieds dit")) == []


def test_italics_leave_a_notes_mark_out():  # Genèse p. 845: _vestiges^{(f)} du pays_ made vestiges_^{(f)} _du pays_
    o = ocr(line(300, "dit", "Vous", "venez", "observer", "les", "vestiges", "(f)", "du", "pays", "ici", sl=[0, 16, 17, 16, 17, 16, 15, 16, 17, 0]))
    r = O.italics(o, page("dit Vous venez observer les vestiges^{(f)} du pays ici"))
    assert [x["new"] for x in r] == ["dit _Vous venez observer les vestiges_^{(f)} _du pays_ ici"]


def test_no_word_differs_for_a_notes_letter():
    o = ocr(line(300, "il", "dit", "Ce", "que", "vous", "dites", wc=0.99))
    assert O.differs(o, page("il dit ^{(e)} que vous dites")) == []


def test_a_note_mark_misread_is_neither_red_nor_a_different_word():
    """Kraken reads "(e)" as "Ce)", "(b)" as "1b)": the same as the text's note letter, or left out."""
    words = ["une", "chose", "Ce)", "grande", "de", "Dieu", "1b)", "pour", "nous"]
    r = O.align(ocr(line(300, *words)), page("une chose^{(e)} grande de Dieu pour nous"), fix=True)
    assert statuses(r) == [(w, "ok") for w in ["une", "chose", "Ce", "grande", "de", "Dieu"]] + [
        ("1b", "skip"), ("pour", "ok"), ("nous", "ok")]
    r = O.align(ocr(line(300, "une", "Ce)", "chose")), page("une chose"), fix=True)
    assert ("Ce", "skip") in statuses(r)
    r = O.align(ocr(line(300, "une", "chose", "grande")), page("une chose"), fix=True)
    assert ("grande", "missing") in statuses(r)


def _words(y, *spec):
    """A line from (text, x, width) triples."""
    ws = [{"t": t, "box": [x, y, bw, 30], "wc": 0.99, "sl": None} for t, x, bw in spec]
    return {"box": [ws[0]["box"][0], y, ws[-1]["box"][0] + ws[-1]["box"][2] - ws[0]["box"][0], 30], "words": ws}


def test_a_line_read_across_the_gutter_without_a_gap_is_cut_and_a_cut_word_goes_on_in_its_column():
    """Kraken reads the rule as a letter (mani-i re) or glues it in a word (addu-[mandérent); a word cut at
    the end of a French line goes on at the next French line, not at the Latin line read after it."""
    o = ocr(_words(300, ("Latin", 340, 100), ("unum", 460, 80)),
            _words(333, ("dixit", 340, 340), ("mani-i", 700, 90), ("re", 805, 40), ("que", 860, 60)),
            _words(366, ("dixit", 340, 280), ("addu-[mandérent", 640, 330)),
            _words(399, ("ctus", 340, 80)),
            _words(300, ("Vous", 790, 80), ("ter¬", 890, 60)),
            _words(399, ("suite", 790, 100)),
            _words(900, ("COMMENTAIRE.", 600, 250)))
    toks = [t["t"] for t in O.ocr_tokens(O.split_columns(o))]
    assert "terre" in toks and "adductus" in toks and "mandérent" in toks
    assert toks.index("terre") > toks.index("adductus")  # the French after the Latin column


def test_a_word_differs_after_an_elision_names_the_word_not_the_elision():  # qu'Abraham: not "qu"
    o = ocr(line(300, "il", "dit", "lorsqu'avant", "tout", "vint", wc=0.99))
    assert [(x["old"], x["new"]) for x in O.differs(o, page("il dit lorsqu'ayant tout vint"))] == [("ayant", "avant")]


def test_words_the_json_has_in_italics_are_marked_for_the_underline():
    o = ocr(line(300, "Il", "dit:", "Je", "suis", "votre", "Dieu"))
    d = page("Il dit : _Je suis_ vo_tre_ Dieu")
    words = O.mark_json_italics(O.align(o, d)["words"], d)
    assert [w["t"] for w in words if w.get("it")] == ["Je", "suis"]


def test_italics_take_in_il_read_as_a_roman_numeral():  # 3 Rois p. 174: Il read II, skipped as a number
    o = ocr(line(300, "rangs.", "II", "fit", "des", "réseaux", "ici", sl=[0, 17, 22, 18, 16, 0]))
    assert [x["old"] for x in O.italics(o, page("rangs. Il fit des réseaux ici"))] == ["Il fit des réseaux"]


def test_italics_leave_out_a_short_word_the_scan_measures_roman():  # Psaumes p. 121: Le conseil, ou le secret
    o = ocr(line(300, "lettre", "Le", "conseil,", "ou", "le", "secret", "des", "justes", sl=[0, 15, 16, 4, 15, 16, 0, 0]))
    assert [x["new"] for x in O.italics(o, page("lettre Le conseil, ou le secret des justes"))] == ["lettre _Le conseil,_ ou _le secret_ des justes"]


def test_italics_take_in_an_ampersand_that_leans_with_them():  # 3 Rois p. 143: & ce vestibule
    o = ocr(line(300, "large,", "&", "ce", "vestibule", "était", "ici", sl=[0, 15, 16, 17, 16, 0]))
    assert [x["old"] for x in O.italics(o, page("large, et ce vestibule était ici"))] == ["et ce vestibule était"]


def test_italics_take_in_a_short_word_opening_the_sentence():  # Job p. 119: A quoi peut-on, the A not measured
    o = ocr(line(300, "trompeuse.", "A", "quoi", "peut-on", "comparer", "ici", sl=[0, None, 16, 17, 16, 0]))
    assert [x["old"] for x in O.italics(o, page("trompeuse. A quoi peut-on comparer ici"))] == ["A quoi peut-on comparer"]


def test_italics_leave_out_a_short_word_measured_roman_opening_the_sentence():  # 3 Rois p. 138: Le _core_ contenait
    o = ocr(line(300, "ornement.", "Le", "core", "contenait", sl=[0, -1, 16, 0]))
    assert [x["old"] for x in O.italics(o, page("ornement. Le core contenait"))] == ["core"]


def test_italics_leave_out_an_ampersand_measured_roman():  # 1 Chroniques p. 154: Mochori ; & _Mosollam_
    o = ocr(line(300, "Mochori;", "&", "Mosollam", "fils", sl=[0, -3, 16, 0]))
    assert [x["old"] for x in O.italics(o, page("Mochori ; et Mosollam fils"))] == ["Mosollam"]


def test_italics_leave_a_short_roman_word_inside_a_sentence():
    o = ocr(line(300, "voici", "le", "Serpent", "tortueux,", "que", sl=[0, -2, 16, 17, 0]))
    assert [x["old"] for x in O.italics(o, page("voici le Serpent tortueux, que"))] == ["Serpent tortueux"]


# --- the printed surface of the scan's words, and printed(): modern text with its punctuation ---

def tok(pt, wc=0.9):
    return {"t": O.TOKEN.sub(lambda m: m.group(), pt), "pt": pt, "wc": wc}


def test_tokens_keep_printed_surface():
    o = ocr(line(300, "l’Homme.", "Terre,", "com-"), line(340, "mencement", "du", "(Gen.", "21.Et"))
    ws = O.ocr_tokens(o)
    assert [w["pt"] for w in ws] == ["l’", "Homme.", "Terre,", "commencement", "du", "(Gen.", "21.", "Et"]


def test_printed_modernizes_and_glues_elisions():
    ws = [tok("l’"), tok("Homme"), tok("&"), tok("avoit,"), tok("ſes")]
    assert O.printed(ws)["text"] == "l'Homme et avait, ses"


def test_printed_flags():
    r = O.printed([tok("Firmament."), tok("des"), tok("Eaux,,")])
    assert [f["why"] for f in r["flags"]] == ["stop_lower", "doubled"]
    assert r["text"][r["flags"][0]["a"]:r["flags"][0]["b"]] == "."


def test_printed_inner_mark_flagged_but_not_initials():
    assert [f["why"] for f in O.printed([tok("Firm.ament")])["flags"]] == ["inner"]
    assert O.printed([tok("J.C."), tok("4000")])["flags"] == []


def test_printed_abbreviations_not_flagged():
    for t in (["S.", "Augustin"], ["ch.", "iii"], ["Exod.", "xx"], ["etc.", "et"], ["Matth.", "v"]):
        assert O.printed([tok(x) for x in t])["flags"] == [], t


def test_printed_low_confidence_mark_and_open_end():
    r = O.printed([tok("Dieu", wc=0.9), tok("créa;", wc=0.4), tok("le"), tok("Ciel.")], closes=True)
    assert [f["why"] for f in r["flags"]] == ["low_conf"]
    assert [f["why"] for f in O.printed([tok("la"), tok("Terre")], closes=True)["flags"]] == ["no_end"]
    assert O.printed([tok("la"), tok("Terre")])["flags"] == []
