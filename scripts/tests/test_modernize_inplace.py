from modernize_inplace import modernize_text


def test_cc_normalization():
    # Standard çç -> ç
    text, n = modernize_text("La foule commenççait à s'assembler et on exerççait la justice.")
    assert "commençait" in text
    assert "exerçait" in text
    assert "çç" not in text
    assert n >= 2

    # Contextual concevoir: conççait -> conçoit
    text, n = modernize_text("On conççait aisément que Dieu est tout-puissant.")
    assert "On conçoit aisément" in text
    assert "conçait" not in text
    assert n >= 1

    # Contextual dire: diççait -> disait
    text, n = modernize_text("Le juste qui diççait qu'il était le fils de Dieu.")
    assert "qui disait qu'il" in text
    assert "diçait" not in text
    assert n >= 1


def test_forte_to_sorte():
    # Adverbial turns
    text, _ = modernize_text("Il agit en forte que tout réussisse de forte qu'on voie sa gloire.")
    assert "en sorte que" in text
    assert "de sorte qu'on" in text

    text, _ = modernize_text("C'est en quelque forte une preuve de cette forte de foi.")
    assert "en quelque sorte" in text
    assert "de cette sorte" in text

    text, _ = modernize_text("Ils font de même forte et de la forte.")
    assert "de même sorte" in text
    assert "de la sorte" in text

    text, _ = modernize_text("Il faut faire en forte d'obéir.")
    assert "faire en sorte" in text

    # Determiners & quantifiers
    text, _ = modernize_text("Cette forte de fruit, une forte de miracle, toutes fortes de biens.")
    assert "Cette sorte de" in text
    assert "une sorte de" in text
    assert "toutes sortes de" in text

    text, _ = modernize_text("Deux fortes de sacrifices et plusieurs fortes d'offrandes.")
    assert "Deux sortes de" in text
    assert "plusieurs sortes d'" in text

    # Genuine adjective forte must remain unchanged
    text, _ = modernize_text("Une ville forte avec des murailles fortes et une armée forte.")
    assert "Une ville forte" in text
    assert "murailles fortes" in text
    assert "armée forte" in text


def test_fait_to_sait():
    # Propositional / knowledge clauses
    text, _ = modernize_text("On fait que la terre est ronde et l'on fait qu'il viendra.")
    assert "On sait que" in text
    assert "l'on sait qu'il" in text

    text, _ = modernize_text("Ne fait-on pas que les prophètes ont parlé ?")
    assert "Ne sait-on pas que" in text

    text, _ = modernize_text("Qui fait si le Seigneur aura pitié ?")
    assert "Qui sait si" in text

    text, _ = modernize_text("Nul ne fait ce qui arrivera.")
    assert "Nul ne sait ce qui" in text

    text, _ = modernize_text("On ne fait que trop par expérience.")
    assert "On ne sait que trop" in text

    text, _ = modernize_text("On ne fait pas précisément l'année.")
    assert "On ne sait pas précisément" in text

    text, _ = modernize_text("On fait d'ailleurs que Moïse l'a écrit.")
    assert "On sait d'ailleurs que" in text

    # Genuine faire must remain unchanged
    text, _ = modernize_text("On fait mention de son nom et on fait attention à sa parole.")
    assert "On fait mention" in text
    assert "on fait attention" in text

    text, _ = modernize_text("On ne fait point la cuisine ce jour-là.")
    assert "On ne fait point la cuisine" in text

    text, _ = modernize_text("A-t-on fait que des fautes ?")
    assert "A-t-on fait que" in text


def test_vocative_o_to_circumflex():
    text, _ = modernize_text("O Dieu, écoute ma prière ! O Seigneur, sauve-nous !")
    assert "Ô Dieu" in text
    assert "Ô Seigneur" in text

    text, _ = modernize_text("O Israël, reviens au Seigneur ! O mon âme, bénis Dieu !")
    assert "Ô Israël" in text
    assert "Ô mon âme" in text

    text, _ = modernize_text("O vous tous qui passez, écoutez !")
    assert "Ô vous tous" in text

    text, _ = modernize_text("O mort, où est ta victoire ? O !")
    assert "Ô mort" in text
    assert "Ô !" in text


def test_obsolete_diaeresis_cleanup():
    # User examples
    text, _ = modernize_text("La tristesse se perpetuë et diminuë à mesure qu'on contribuë.")
    assert "perpétue" in text
    assert "diminue" in text
    assert "contribue" in text

    text, _ = modernize_text("Sa tête sera tonduë comme une brebis.")
    assert "tondue" in text

    text, _ = modernize_text("Enÿvrée non pas de vin mais d'amertume.")
    assert "Enivrée" in text

    # Verbs in -uer
    text, _ = modernize_text("Il remuë et restituë ce qu'il a pris ; cela influë sur l'état.")
    assert "remue" in text
    assert "restitue" in text
    assert "influe" in text

    # Participles & adjectives in -uë / -uës
    text, _ = modernize_text("Des tentes abbattuës, des murailles interrompuës et des branches cheveluës.")
    assert "abattues" in text
    assert "interrompues" in text
    assert "chevelues" in text

    # Protected legitimate diaeresis
    text, _ = modernize_text("Une douleur aiguë causée par la ciguë dans une chambre contiguë.")
    assert "aiguë" in text
    assert "ciguë" in text
    assert "contiguë" in text

    # Protected proper names
    text, _ = modernize_text("L'Ange apparut à Manuë dans le désert de Thécuë.")
    assert "Manuë" in text
    assert "Thécuë" in text

    # 18th-century oë spellings
    text, _ = modernize_text("Une boëte de parfum pour sa coëffure, avec de la moëlle.")
    assert "boîte" in text
    assert "coiffure" in text
    assert "moelle" in text

    # Obsolete ü in French
    text, _ = modernize_text("Secoüez la poussière, joüions de la musique et que tout réüffit.")
    assert "Secouez" in text
    assert "jouions" in text
    assert "réussit" in text


def test_hyphen_normalization():
    # User-requested 18th century compounds
    text, _ = modernize_text("Il partira bien-tôt, car il a attendu long-temps en même-temps, et aussi-tôt il reviendra.")
    assert "bientôt" in text
    assert "longtemps" in text
    assert "même temps" in text
    assert "aussitôt" in text

    # Other single-word compounds
    text, _ = modernize_text("C'est sur-tout et par-tout un chemin mal-aisé qui sert de marche-pied.")
    assert "surtout" in text
    assert "partout" in text
    assert "malaisé" in text
    assert "marchepied" in text

    text, _ = modernize_text("Il est vrai-semblable qu'ils ont fait cela sans contre-temps.")
    assert "vraisemblable" in text
    assert "contretemps" in text

    # Spaced compounds
    text, _ = modernize_text("Non-seulement les Apôtres, mais aussi-bien les fidèles sont venus de bonne-heure.")
    assert "Non seulement les Apôtres" in text
    assert "aussi bien les fidèles" in text
    assert "de bonne heure" in text

    text, _ = modernize_text("Il est tout-à-fait mal-à-propos de juger à peu-près dès-lors.")
    assert "tout à fait" in text
    assert "mal à propos" in text
    assert "peu près" in text
    assert "dès lors" in text

    # De-là demonstrative vs Au-delà / Par-delà
    text, _ = modernize_text("De-là vient qu'on ne peut aller au-delà ni par-delà le fleuve, mais sortir de-là.")
    assert "De là vient" in text
    assert "au-delà" in text
    assert "par-delà" in text
    assert "sortir de là" in text

    # Preservation of valid standard French compounds
    text, _ = modernize_text("Le grand-prêtre a dit : peut-être est-ce par-dessus la montagne, vis-à-vis du temple ?")
    assert "grand-prêtre" in text
    assert "peut-être" in text
    assert "est-ce" in text
    assert "par-dessus" in text
    assert "vis-à-vis" in text

    # OCR broken words mid-word line hyphenations
    text, _ = modernize_text("Il était com-me un lion di-sant son afflic-tion, avec des vases de cui-vre.")
    assert "comme" in text
    assert "disant" in text
    assert "affliction" in text
    assert "cuivre" in text

    text, _ = modernize_text("Notre Sau-veur et Ben-jamin ne sont point in-constants.")
    assert "Sauveur" in text
    assert "Benjamin" in text
    assert "inconstants" in text

    # Preserved Hebrew decomposition
    text, _ = modernize_text("Suivant l'Hébreu : _Quia Emmanu-el._")
    assert "Quia Emmanu-el" in text


def test_obsolete_circumflex_cleanup():
    # User examples
    text, _ = modernize_text("Des chérubins aîlez, après avoir lû le livre, comme il l'asûre.")
    assert "ailés" in text
    assert "lu" in text
    assert "l'assure" in text

    # Participles in -û
    text, _ = modernize_text("Il a bû du vin, s'est tû devant le juge et a eû grand peur.")
    assert "bu" in text
    assert "tu" in text
    assert "eu" in text

    # Long-s / OCR confusions on -û
    text, _ = modernize_text("Traiter son frère de foû, enseigner un soû.")
    assert "fou" in text
    assert "un fou" in text

    # Archaic spellings with circumflex
    text, _ = modernize_text("Une flâme ardente, un phantôme effrayant, du pain paîtri.")
    assert "flamme" in text
    assert "fantôme" in text
    assert "pétri" in text

    # Future / conditional of -oître verbs
    text, _ = modernize_text("Chacun connoîtra la vérité et l'erreur disparoîtra.")
    assert "connaîtra" in text
    assert "disparaîtra" in text

    # OCR broken words
    text, _ = modernize_text("Dans la mê ne maison, ellemême l'avait dit.")
    assert "même" in text
    assert "elle-même" in text

    # Preservation of legitimate French circumflex words
    text, _ = modernize_text("Le jour de la fête, il est sûr et mûr d'être au temple pour le jeûne avec grâce.")
    assert "fête" in text
    assert "sûr" in text
    assert "mûr" in text
    assert "être" in text
    assert "jeûne" in text
    assert "grâce" in text

    # Preservation of legitimate aînesse
    text, _ = modernize_text("Ésaü vendit son droit d'aînesse.")
    assert "droit d'aînesse" in text

    # Preservation of imperfect subjunctives in -ît / -ût
    text, _ = modernize_text("Il fallait qu'il éteignît le feu avant qu'il parût, et qu'il s'abstînt de parler.")
    assert "qu'il éteignît" in text
    assert "avant qu'il parût" in text
    assert "qu'il s'abstînt" in text

    # Preservation of Latin ablatives / 4th declension
    text, _ = modernize_text("In terrâ alienâ, ex aquâ et spiritûs sancti.")
    assert "terrâ" in text
    assert "aquâ" in text
    assert "spiritûs" in text


def test_obsolete_y_cleanup():
    # User examples
    text, _ = modernize_text("Il fonde l'abyme, et d'abyme en abyme dans les abymes.")
    assert "l'abîme" in text
    assert "d'abîme" in text
    assert "abîmes" in text

    text, _ = modernize_text("Ils furent envyrez du calice, et on envyre les éléphants d'un vin qui envyvre.")
    assert "enivrés" in text
    assert "enivre les éléphants" in text
    assert "qui enivre" in text

    text, _ = modernize_text("Qu'il n'y aye aucun doute que j'aye dit la vérité et que je l'aye comprise.")
    assert "Qu'il n'y ait aucun doute" in text
    assert "que j'aie dit" in text
    assert "que je l'aie comprise" in text

    # Ancestors
    text, _ = modernize_text("Son ayeul et son ayeule ont laissé ce royaume à leurs ayeux et son bisayeul.")
    assert "aïeul" in text
    assert "aïeule" in text
    assert "aïeux" in text
    assert "bisaïeul" in text

    # Asile, haie, futaie, taie, craie, etc.
    text, _ = modernize_text("Chercher un asyle derrière la haye d'une futaye couverte de buys.")
    assert "asile" in text
    assert "haie" in text
    assert "futaie" in text
    assert "buis" in text

    text, _ = modernize_text("Une taye sur les yeux, des clayes de roseaux, et des brayes de toile avec de la craye.")
    assert "taie" in text
    assert "claies" in text
    assert "braies" in text
    assert "craie" in text

    # Gaieté & gai
    text, _ = modernize_text("Un visage gay et plein de gayeté chante gayement.")
    assert "gai" in text
    assert "gaieté" in text
    assert "gaiement" in text

    # Days & time
    text, _ = modernize_text("Du lundy au samedy, le jeudy et le vendredy à midy.")
    assert "lundi" in text
    assert "samedi" in text
    assert "jeudi" in text
    assert "vendredi" in text
    assert "midi" in text

    # Cy & monosyllables
    text, _ = modernize_text("Voyez cy-après et Cy après : voicy la Loy et la foy en Dieu pour moy.")
    assert "ci-après" in text
    assert "Ci-après" in text
    assert "voici" in text
    assert "la Loi" in text
    assert "la foi" in text
    assert "pour moi" in text

    # Common words with y -> i
    text, _ = modernize_text("L'hyrondelle a son nid, une éclypse de soleil, une voûte de crystal, le son de la tymbale et de la cythare.")
    assert "L'hirondelle" in text
    assert "éclipse" in text
    assert "cristal" in text
    assert "timbale" in text
    assert "cithare" in text

    text, _ = modernize_text("Un spectre hydeux, quoiqu'ils doyvent venir aujourd'huy avec les truyes dans la suye.")
    assert "hideux" in text
    assert "quoiqu'ils" in text
    assert "doivent" in text
    assert "aujourd'hui" in text
    assert "truies" in text
    assert "suie" in text

    # Future verbs in -ray -> -rai
    text, _ = modernize_text("Je vous rendray témoignage et je répandray ma grâce.")
    assert "rendrai" in text
    assert "répandrai" in text

    # Animal lion vs City Lyon
    text, _ = modernize_text("La colère du Roi est comme le rugissement du Lyon.")
    assert "rugissement du lion" in text

    text, _ = modernize_text("Saint Irénée était évêque de Lyon, et l'édition de Lyon en 1620.")
    assert "évêque de Lyon" in text
    assert "édition de Lyon" in text

    # Legitimate standard words preserved
    text, _ = modernize_text("Ayez confiance, ouvrez les yeux, voyez ce pays et ce style d'Égypte.")
    assert "Ayez" in text
    assert "yeux" in text
    assert "voyez" in text
    assert "pays" in text
    assert "style" in text
    assert "Égypte" in text


def test_missing_apostrophe_cleanup():
    # User examples & pair elisions
    text, _ = modernize_text("Les femmes d Orient sont fort passionnées, comme le Serpent d airain dans le désert.")
    assert "d'Orient" in text
    assert "d'airain" in text

    text, _ = modernize_text("Quand ce Saint parle d une croix, on ne doit pas l entendre d une potence.")
    assert "d'une croix" in text
    assert "l'entendre" in text
    assert "d'une potence" in text

    text, _ = modernize_text("C est ce qui oblige Jérémie, et c étaient des serpents ailés.")
    assert "C'est" in text
    assert "c'étaient" in text

    text, _ = modernize_text("Le fils de l homme dans l Évangile et l Écriture sainte.")
    assert "l'homme" in text
    assert "l'Évangile" in text
    assert "l'Écriture" in text

    text, _ = modernize_text("Il n y a point d endroit où l on ait pu dresser ce signal dans l âme.")
    assert "n'y a point" in text
    assert "d'endroit" in text
    assert "l'on ait pu" in text
    assert "l'âme" in text

    text, _ = modernize_text("L Hébreu à la lettre porte qu il n ait pu découvrir le voleur et qu elle conserve la Loi.")
    assert "L'Hébreu" in text
    assert "qu'il n'ait pu" in text
    assert "qu'elle" in text

    text, _ = modernize_text("Si Quelqu un emprunte d un autre quelqu une de ces choses en l absence du maître.")
    assert "Quelqu'un" in text
    assert "d'un autre" in text
    assert "quelqu'une" in text
    assert "l'absence" in text

    # Glued words without apostrophe
    text, _ = modernize_text("Dautres soutiennent quon mettait à mort le premier-né dun âne.")
    assert "D'autres" in text
    assert "qu'on" in text
    assert "d'un âne" in text

    text, _ = modernize_text("Ce qui ne doit sentendre que par lopposition, et vous noffrirez point ce prix.")
    assert "s'entendre" in text
    assert "l'opposition" in text
    assert "n'offrirez point" in text

    text, _ = modernize_text("Le contrat quil passait, et on lui ôtera ce quil a.")
    assert "qu'il passait" in text
    assert "qu'il a" in text

    text, _ = modernize_text("La raison qui faisait quon nen offrait pas et quon nen fait point de trafic.")
    assert "qu'on n'en offrait pas" in text
    assert "qu'on n'en fait point" in text

    text, _ = modernize_text("Si lon ne lchangeait pas contre la valeur dune brebis.")
    assert "l'on" in text
    assert "l'échangeait" in text
    assert "d'une brebis" in text

    # Whitespace after apostrophe
    text, _ = modernize_text("Tout l' honneur de la royauté, et l'\nabandonné dans Israël.")
    assert "l'honneur" in text
    assert "l'abandonné" in text

    # Conjunction elisions
    text, _ = modernize_text("Le faîte s'élève jusque aux nues, et votre justice jusque au Ciel.")
    assert "jusqu'aux nues" in text
    assert "jusqu'au Ciel" in text

    text, _ = modernize_text("Lorsque il sera détendu, lorsque elle présenta, et il porte que il fut chanté.")
    assert "Lorsqu'il sera" in text
    assert "lorsqu'elle présenta" in text
    assert "qu'il fut chanté" in text

    text, _ = modernize_text("Ils les ramènent de même, lorsque il nuit approche.")
    assert "lorsque la nuit approche" in text

    # OCR fixes
    text, _ = modernize_text("I's ont lu ce passage, et lui-n.ême l'avait dit.")
    assert "Ils ont lu" in text
    assert "lui-même" in text

    text, _ = modernize_text("Maintenant donc, ô mon si's, écoutez-moi. Y a-t il du pain ?")
    assert "mon fils, écoutez-moi" in text
    assert "Y a-t-il" in text


def test_misc_archaic_and_pattern_families():
    # 1. éthimologies -> étymologies
    text, _ = modernize_text("les éthimologies de ces termes, et une éthimologie certaine.")
    assert "les étymologies" in text
    assert "une étymologie" in text

    # 2. monstrer family
    text, _ = modernize_text("Je vais vous monstrer ce monstre marin qu'ils lui monstrèrent.")
    assert "vous montrer ce monstre marin qu'ils lui montrèrent." in text

    # 3. croissans family (-ans / -ens plurals)
    text, _ = modernize_text("Des croissans d'or, des bruits fréquens, des mécontens turbulens, et deux ans dedans.")
    assert "croissants d'or" in text
    assert "fréquents" in text
    assert "mécontents turbulents" in text
    assert "deux ans dedans" in text

    # 4. brasselets family (ss -> c)
    text, _ = modernize_text("Elle portait un brasselet et des brasselets, du pain dans la sausse sur la nasselle.")
    assert "un bracelet et des bracelets" in text
    assert "la sauce sur la nacelle" in text

    # 5. Genéfe OCR long-s
    text, _ = modernize_text("Voyez notre Commentaire sur la Genéfe, page 10.")
    assert "sur la Genèse, page 10." in text

    # 6. Contextual par tout -> partout
    text, _ = modernize_text("Par tout où les sauterelles passent, le soldat porta par tout la mort. Mais par tout le monde, et par tout ce peuple.")
    assert "Partout où" in text
    assert "partout la mort" in text
    assert "par tout le monde" in text
    assert "par tout ce peuple" in text

    text, _ = modernize_text("Ils ont fouillé par tout, et ils allèrent par tout ailleurs.")
    assert "fouillé partout," in text
    assert "partout ailleurs." in text

    # 7. bled -> blé
    text, _ = modernize_text("Où est le bled et les bleds mûrs ?")
    assert "le blé et les blés mûrs" in text

    # 8. gozier family (z -> s)
    text, _ = modernize_text("Un gozier doux, dans le magazin des cizeaux, sans aucun hazard.")
    assert "Un gosier doux" in text
    assert "le magasin des ciseaux" in text
    assert "aucun hasard" in text

    # 9. robbe family (consonant normalization)
    text, _ = modernize_text("Une robbe blanche pour abbattre cet embaras de nouriture et de canelle.")
    assert "Une robe blanche pour abattre cet embarras de nourriture et de cannelle." in text


def test_expand_abbreviations_heb_and_chap():
    # 1. l'Heb family
    text, _ = modernize_text("Il faut lire dans l'Heb. gag, un toit. L'Héb. ^{(a)} _Pour bénir._")
    assert "lire dans l'Hébreu gag" in text
    assert "L'Hébreu ^{(a)} _Pour bénir._" in text

    text, _ = modernize_text("L'Hébr. _Secourez-les_ dans l'Héb._ au lieu de")
    assert "L'Hébreu _Secourez-les_" in text
    assert "dans l'Hébreu_ au lieu de" in text

    text, _ = modernize_text("Le texte Héb.^{(b)} et dans le texte Heb. de la Genèse.")
    assert "Le texte Hébreu^{(b)}" in text
    assert "dans le texte Hébreu de la Genèse." in text

    text, _ = modernize_text("Samuel (Hébr. _Nééman_) était destiné")
    assert "Samuel (Hébreu _Nééman_) était destiné" in text

    # 2. Chap family in chapter_title
    text, _ = modernize_text("SUR JOEL. CHAP. IV.")
    assert text == "SUR JOEL. CHAPITRE IV."

    text, _ = modernize_text("CHAP. III.")
    assert text == "CHAPITRE III."

    # 3. Chap family in running text
    text, _ = modernize_text("Voyez le Chap. 11. versets 3. 4. et au Chap. xx. de Jérémie.")
    assert "Voyez le Chapitre 11. versets 3. 4." in text
    assert "au Chapitre xx. de Jérémie." in text

    text, _ = modernize_text("avec le chap. 10:23. et au chap. xv. ℣. 34.")
    assert "avec le chapitre 10:23." in text
    assert "au chapitre xv. ℣. 34." in text

    text, _ = modernize_text("ci-après, Ch. x. ℣. 8. et Ch. suivant, ℣. 25.")
    assert "ci-après, Chapitre x. ℣. 8." in text
    assert "Chapitre suivant, ℣. 25." in text

    text, _ = modernize_text("comme les Chap. précédents, et aux chap. 14. et 15.")
    assert "comme les Chapitres précédents" in text
    assert "aux chapitres 14. et 15." in text

    text, _ = modernize_text("Ce que l'on voit à la fin de ce Chap. Ensuite il parle...")
    assert "à la fin de ce Chapitre. Ensuite il parle..." in text

    text, _ = modernize_text("ci-après Chap 37:14.")
    assert "ci-après Chapitre 37:14." in text


def test_modernize_oi_to_ai_and_archaic_verbs():
    # 1. Connoître / paroître inflections and OCR variants
    text, _ = modernize_text("Vous paroissez devant Dieu, et ils paroissoient autrefois.")
    assert "Vous paraissez devant Dieu" in text
    assert "ils paraissaient autrefois" in text

    text, _ = modernize_text("Qu'ils paroissent et qu'il paroisse, afin que nous paroissions.")
    assert "Qu'ils paraissent" in text
    assert "qu'il paraisse" in text
    assert "afin que nous paraissions." in text

    text, _ = modernize_text("Si vous paroissez et si vous paroissiez, sans qu'ils paroiffent ou paroißent.")
    assert "Si vous paraissez" in text
    assert "si vous paraissiez" in text
    assert "sans qu'ils paraissent" in text
    assert "ou paraissent." in text

    text, _ = modernize_text("Faire paroitre ou disparoitre ce prodige.")
    assert "Faire paraître ou disparaître ce prodige." in text

    text, _ = modernize_text("Que la gloire disparoisse ou qu'elle disparoiffe.")
    assert "Que la gloire disparaisse" in text
    assert "ou qu'elle disparaisse." in text

    text, _ = modernize_text("Les anges apparoissaient et le Seigneur apparoissait.")
    assert "Les anges apparaissaient et le Seigneur apparaissait." in text

    text, _ = modernize_text("Ils comparoissaient devant le juge.")
    assert "Ils comparaissaient devant le juge." in text

    text, _ = modernize_text("La connoiffance des saints et les connoiffances humaines.")
    assert "La connaissance des saints et les connaissances humaines." in text

    text, _ = modernize_text("Ils connoiffent la loi et connoiffant la vérité.")
    assert "Ils connaissent la loi et connaissant la vérité." in text

    text, _ = modernize_text("Des connoisseurs en cette matière.")
    assert "Des connaisseurs en cette matière." in text

    text, _ = modernize_text("Des choses connoissables et reconnoissables.")
    assert "Des choses connaissables et reconnaissables." in text

    text, _ = modernize_text("Vous reconnoissiez et nous reconnoissions sa bonté.")
    assert "Vous reconnaissiez et nous reconnaissions sa bonté." in text

    text, _ = modernize_text("Une juste reconnoiffance ; il reconnoiffait son maître.")
    assert "Une juste reconnaissance ; il reconnaissait son maître." in text

    text, _ = modernize_text("Qu'il reconnoiffe ses fautes ; vous méconnoissez Dieu ; ils méconnoîtront sa loi.")
    assert "Qu'il reconnaisse ses fautes" in text
    assert "vous méconnaissez Dieu" in text
    assert "ils méconnaîtront sa loi." in text

    text, _ = modernize_text("Ils en reconnoi-tront un jour la fausseté.")
    assert "Ils en reconnaîtront un jour la fausseté." in text

    # 2. Foible / affoiblir family
    text, _ = modernize_text("Les forces s'affoiblissent et s'affoiblifsent de jour en jour.")
    assert "s'affaiblissent et s'affaiblissent de jour en jour." in text

    text, _ = modernize_text("Cela affoiblira leur courage, et je l'affoiblirai.")
    assert "Cela affaiblira leur courage, et je l'affaiblirai." in text

    text, _ = modernize_text("Pourvu qu'on l'affoibliffe, quoiqu'il s'affoiblissait.")
    assert "Pourvu qu'on l'affaiblisse, quoiqu'il s'affaiblissait." in text

    text, _ = modernize_text("S'ils s'affoibliraient, ils se verraient assoiblis.")
    assert "S'ils s'affaibliraient, ils se verraient affaiblis." in text

    # 3. Roide / roidir family
    text, _ = modernize_text("Roidissez votre bras, il voulut roidir le cou, et il s'est roidi.")
    assert "Raidissez votre bras, il voulut raidir le cou, et il s'est raidi." in text

    text, _ = modernize_text("Ce Roid'Égypte, est Pharaon Hophra.")
    assert "Ce Roi d'Égypte, est Pharaon Hophra." in text

    # Preserving legitimate French words with oi
    text, _ = modernize_text("Le froid, la froide saison, les froids rigoureux et la froideur.")
    assert text == "Le froid, la froide saison, les froids rigoureux et la froideur."

    text, _ = modernize_text("L'eau va se refroidir et les cœurs vont refroidir.")
    assert text == "L'eau va se refroidir et les cœurs vont refroidir."

    text, _ = modernize_text("Les parois du sanctuaire étaient couvertes de bois.")
    assert text == "Les parois du sanctuaire étaient couvertes de bois."

    text, _ = modernize_text("Le marbre de Paros et saint François de Paule.")
    assert text == "Le marbre de Paros et saint François de Paule."

    # 4. Monnoie
    text, _ = modernize_text("Battre de la monnoie et peser les monnoies.")
    assert "Battre de la monnaie et peser les monnaies." in text

    # 5. Françoise / Narbonnoise adjectives
    text, _ = modernize_text("La Version Françoise et les traductions françoises dans la Gaule Narbonnoise.")
    assert "La Version Française et les traductions françaises dans la Gaule Narbonnaise." in text

    # 6. Archaic verb endings and contractions
    text, _ = modernize_text("L'orge duisoit sa graine et il l'obsedoit.")
    assert "L'orge duisait sa graine et il l'obsédait." in text

    text, _ = modernize_text("Qu'on laveroît le char ; comme s'il dérivoit ou dévivoit de ce terme.")
    assert "Qu'on laverait le char ; comme s'il dérivait ou dérivait de ce terme." in text

    text, _ = modernize_text("Comme si l'argile disoit au potier : les serpents siffloient.")
    assert "Comme si l'argile disait au potier : les serpents sifflaient." in text

    text, _ = modernize_text("Origenes liloit le passage, et d'autres lisoient : on les blanchissoit.")
    assert "Origenes lisait le passage, et d'autres lisaient : on les blanchissait." in text

    text, _ = modernize_text("Ceux qui m'assiégeoint ; ils prenoiens et descendroiens.")
    assert "Ceux qui m'assiégeaient ; ils prenaient et descendraient." in text

    text, _ = modernize_text("Ceux qui étoiens là ; c'estoit la coutume, n'estoit-ce pas vrai ?")
    assert "Ceux qui étaient là ; c'était la coutume, n'était-ce pas vrai ?" in text

    text, _ = modernize_text("Les épines croistrons sur la terre ; empêcheroitelle le feu ?")
    assert "Les épines croîtront sur la terre ; empêcherait-elle le feu ?" in text

    text, _ = modernize_text("Il veloppoit les villes ; ils avaient dequoi manger.")
    assert "Il enveloppait les villes ; ils avaient de quoi manger." in text

    # 7. Misc
    text, _ = modernize_text("Par le moïen de Moïse, la cicoigne sur les sapins, au refectoire et au resectoire.")
    assert "Par le moyen de Moïse, la cigogne sur les sapins, au réfectoire et au réfectoire." in text


def test_modernize_ez_to_es_participles_and_preserve_verbs():
    # 1. Unconditional participles in -ez
    text, _ = modernize_text("Ceux qui sont passionnez pour le monde, entre amants passionnez.")
    assert "Ceux qui sont passionnés pour le monde, entre amants passionnés." in text

    text, _ = modernize_text("Percez de coups, et ensanglantez, avec des cheveux frisés, (entortillez).")
    assert "Percez de coups, et ensanglantés, avec des cheveux frisés, (entortillés)." in text

    # 2. Contextual participles vs imperatives for déchirez, abaissez, avancez
    text, _ = modernize_text("Ayant leurs vêtements déchirez, et avec des habits sales, et déchirez ; mais déchirez vos cœurs, et ne déchirez point vos habits.")
    assert "Ayant leurs vêtements déchirés, et avec des habits sales, et déchirés ; mais déchirez vos cœurs, et ne déchirez point vos habits." in text

    text, _ = modernize_text("Les yeux des superbes seront abaissez, et ceux qui sont humiliés, et abaissez ; mais Seigneur, abaissez vos cieux et abaissez votre cœur.")
    assert "Les yeux des superbes seront abaissés, et ceux qui sont humiliés, et abaissés ; mais Seigneur, abaissez vos cieux et abaissez votre cœur." in text

    text, _ = modernize_text("Ils sont aussi avancez l'un que l'autre, et chargés de fruits avancez ; mais avancez hardiment et ne vous avancez jamais.")
    assert "Ils sont aussi avancés l'un que l'autre, et chargés de fruits avancés ; mais avancez hardiment et ne vous avancez jamais." in text

    # 3. Contextual participles vs imperatives for appuyez, sauvez, élevez, fondez
    text, _ = modernize_text("Les nouveaux l'ont adopté, appuyez sur ce texte ; mais ne vous appuyez point sur votre prudence.")
    assert "Les nouveaux l'ont adopté, appuyés sur ce texte ; mais ne vous appuyez point sur votre prudence." in text

    text, _ = modernize_text("Un petit nombre de sauvez, et nous serons sauvez ; mais Seigneur, sauvez-moi, sauvez votre vie et sauvez-vous.")
    assert "Un petit nombre de sauvés, et nous serons sauvés ; mais Seigneur, sauvez-moi, sauvez votre vie et sauvez-vous." in text

    text, _ = modernize_text("Ceux que j'ai nourris, et élevez, ils sont élevez contre Dieu ; mais élevez vos mains et ne vous élevez point.")
    assert "Ceux que j'ai nourris, et élevés, ils sont élevés contre Dieu ; mais élevez vos mains et ne vous élevez point." in text

    text, _ = modernize_text("Ils sont fondez sur la vérité, mais fondez votre or et votre argent.")
    assert "Ils sont fondés sur la vérité, mais fondez votre or et votre argent." in text








