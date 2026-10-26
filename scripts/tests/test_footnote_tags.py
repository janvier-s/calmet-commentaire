import footnote_tags as T


def tags(t):
    return set(T.local_tags(t)[0])


def test_scripts_and_uncertain():
    assert {"hebrew", "greek", "uncertain"} <= tags("מועד ὄργανα [UNCERTAIN]")
    assert "uncertain" in tags("Saint Basile, Homélie* 6.")


def test_verse_forms():
    assert "verse" in tags("Jean 1:1.")
    assert "verse" in tags("Chapitre 36.")
    assert "verse" in tags("Voyez ci-dessus 43:9.")


def test_old_and_bad_references():
    assert "old-ref" in tags("Marc. XV. 21.")
    assert "old-ref" not in tags("Jean 12:31 ; 14:30 ; 16:11.")
    assert "bad-ref" in tags("Deutéronome 32:61.")
    assert "bad-ref" not in tags("Deutéronome 32:6.")


def test_authors_and_versions():
    assert {"fathers"} <= tags("Saint Thomas, Contre les Gentils, livre 2.")
    assert {"classical"} <= tags("Hérodote, livre 2, chapitre 84.")
    assert {"commentators"} <= tags("Estius, sur ce passage.")
    assert {"versions"} <= tags("70. ἐλοιδόρουν convitiati sunt.")


def test_ibid_and_abbreviations():
    assert "ibid" in tags("Le même, livre 7, chapitre 60.")
    assert "abbrev" in tags("Chrysost. hom. 5. in Genes.")
    assert "abbrev" not in tags("Saint Augustin, La Cité de Dieu, livre 16, chapitre 13.")


def test_latin():
    assert "latin" in tags("A principio.")
    assert "latin" not in tags("Saint Justin, Dialogue avec Tryphon.")  # one capitalized word: a name


def test_plain_citation_needs_no_model():
    assert T.local_tags("Saint Augustin, livre 16, chapitre 13 ; Hérodote, livre 2.")[2] is False
    assert T.local_tags("On dit qu'en langue Cophte, psotemphané signifie le Sauveur du monde.")[2] is True


def test_merge_keeps_hand_changes():
    # first run: the tagger's tags
    assert T.merge(None, None, {"verse"}) == ["verse"]
    # tagged before any record of the tagger's own: all the tagger's
    assert T.merge(["verse"], None, {"verse", "fathers"}) == ["verse", "fathers"]
    # "latin" added by hand, "verse" taken away by hand: both stay so on the next run
    assert T.merge(["fathers", "latin"], ["verse", "fathers"], {"verse", "fathers", "title"}) == ["fathers", "title", "latin"]


def test_checks_mark_lines_to_look_at():
    assert T.checks("title", "Vie de Moïse", "Philon", "classical", "De vita Mosis") == \
        "  # CHECK: Philon counts as rabbis here, not classical"
    assert "no original title" in T.checks("title", "Synopsis", "", "fathers", "")
    assert "ambiguous" in T.checks("author", "Marc", "", "classical", "")
    assert T.checks("title", "La Cité de Dieu", "Augustin", "fathers", "De civitate Dei") == ""


def test_check_notes_are_not_read_as_tags(tmp_path, monkeypatch):
    f = tmp_path / "names.txt"
    f.write_text("title: Vie de Moïse = De vita Mosis | Philon | classical  # CHECK: Philon counts as rabbis\n"
                 "author: Ferrand | commentators  # CHECK: x\n", encoding="utf-8")
    monkeypatch.setattr(T, "NAMES_FILE", f)
    titles, authors, _ = T.read_names()
    assert titles["Vie de Moïse"] == ("De vita Mosis", "Philon", "rabbis") and authors == {"Ferrand": "commentators"}
