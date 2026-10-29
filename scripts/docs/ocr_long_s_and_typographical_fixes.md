# OCR Long-S and Typographical Normalization Guide

This document records the rules, rationales, patterns, and safety constraints established on October 27–28, 2026, for resolving OCR long-s (`ſ`), double-cedilla (`çç`), and vocative (`O` / `Ô`) confusions across Dom Calmet's commentary corpus.

These rules are implemented directly into [`scripts/modernize_inplace.py`](file:///Users/Janvier/Projects/calmet-commentaire/scripts/modernize_inplace.py) and guarded by automated tests in [`scripts/tests/test_modernize_inplace.py`](file:///Users/Janvier/Projects/calmet-commentaire/scripts/tests/test_modernize_inplace.py).

---

## 1. `forte(s)` $\rightarrow$ `sorte(s)` (324 replacements)

### Problem
In 18th-century French typography, the long-s (`ſ`) in *forte* vs *ſorte* is frequently confused by OCR engines. Because both *forte* and *sorte* are valid French words, standard spellcheckers cannot flag the error.

### Applied Rules
Only syntactic contexts where *forte* is unequivocally used as a noun meaning "kind/manner" or in adverbial conjunctions are converted:

1. **Adverbial Phrases:**
   - `en forte que` / `de forte que` $\rightarrow$ `en sorte que` / `de sorte que`
   - `en quelque forte` / `de quelque forte` $\rightarrow$ `en quelque sorte` / `de quelque sorte`
   - `de cette forte` / `en cette forte` $\rightarrow$ `de cette sorte` / `en cette sorte`
   - `de la forte` $\rightarrow$ `de la sorte`
   - `de même forte` / `en même forte` $\rightarrow$ `de même sorte` / `en même sorte`
   - `de telle forte` / `en telle forte` $\rightarrow$ `de telle sorte` / `en telle sorte`
   - `faire en forte` / `fait en forte` / `faisant en forte` / `fit en forte` $\rightarrow$ `faire en sorte`, etc.

2. **Determiners & Quantifiers:**
   - Singular: `cette forte de`, `une forte de`, `autre forte de`, `toute forte de`, `nouvelle forte de` $\rightarrow$ `cette sorte de`, etc.
   - Plural: `ces fortes de`, `plusieurs fortes de`, `toutes fortes de`, `différentes fortes de`, `diverses fortes de`, `nouvelles fortes de`, `[deux-dix] fortes de` $\rightarrow$ `ces sortes de`, etc.
   - Supports both `de` and `d'` elisions (`plusieurs sortes d'animaux`).

3. **Strict Preservations (False Positives Avoided):**
   - Genuine adjectives qualifying feminine nouns: *« ville forte »*, *« places fortes »*, *« armée forte d'un million d'hommes »*, *« femme forte »*, *« la plus forte de leurs raisons »*.

---

## 2. `fait` $\rightarrow$ `sait` (133 replacements)

### Problem
OCR models read *ſait* (from *savoir*) as *fait* (from *faire*).

### Applied Rules
Only clauses requiring the propositional cognitive verb *savoir* are converted:

1. **Propositional / Knowledge Clauses:**
   - `(?<!-t')(?<!-)\b([Oo]n|l'on)\s+fait\s+(?:que\b|qu')` $\rightarrow$ `On sait que` / `l'on sait que`
   - `Ne fait-on pas que` $\rightarrow$ `Ne sait-on pas que`
   - `Qui fait si` $\rightarrow$ `Qui sait si`
   - `Nul ne fait ce qui / ce que / si / que` $\rightarrow$ `Nul ne sait ce qui`, etc.
   - `Elle ne fait ce que c'est` $\rightarrow$ `Elle ne sait ce que c'est`

2. **Negative Knowledge Idioms:**
   - `On ne fait que trop` $\rightarrow$ `On ne sait que trop`
   - `On ne fait pas précisément` $\rightarrow$ `On ne sait pas précisément`
   - `On ne fait point` (excluding *faire la cuisine*) $\rightarrow$ `On ne sait point`
   - `On ne fait ni le` $\rightarrow$ `On ne sait ni le`
   - `On ne fait comment / quel / quelle / quels / quelles` $\rightarrow$ `On ne sait comment`, etc.

3. **Adverbs of Certitude with *savoir*:**
   - `On fait d'ailleurs que` $\rightarrow$ `On sait d'ailleurs que`
   - `On fait certainement que` $\rightarrow$ `On sait certainement que`
   - `On fait indubitablement que` $\rightarrow$ `On sait indubitablement que`
   - `On fait pourtant que` $\rightarrow$ `On sait pourtant que`
   - `On fait très peu` $\rightarrow$ `On sait très peu`
   - `On fait par l'Histoire / par Joseph` $\rightarrow$ `On sait par l'Histoire`, etc.

4. **Strict Preservations:**
   - Idiomatic and past constructions of *faire*: *« faire attention »*, *« faire mention »*, *« faire cas »*, *« faire difficulté »*, *« faire des présents »*, *« a-t-on fait »*, *« on ne fait point la cuisine »*. Preceding hyphens in compound verbs (`-t'on`, `-on`) are guarded via negative lookbehinds.

---

## 3. Double Cedilla `çç` $\rightarrow$ `ç` & Contextual Restorations (207 replacements)

### Problem
18th-century ligature fonts for imperfect `-çoit` (modernized to `-çait`) or `ç` were frequently misread as double-cedilla `çç`. Furthermore, a naive replace `çç -> ç` turned `conççait` into invalid French `conçait` instead of the original 3rd-person singular present `conçoit`.

### Applied Rules
1. **Standard Cedilla:**
   - `commenççait` $\rightarrow$ `commençait`
   - `exerççait` / `éxerççait` $\rightarrow$ `exerçait` / `éxerçait`
   - `menaççait` / `ménaççait` $\rightarrow$ `menaçait` / `ménaçait`
   - `avanççait` $\rightarrow$ `avançait`
   - `Franççais` $\rightarrow$ `Français`
   - `annonççait`, `aperççait`, `apperççait`, `plaççait`, `lanççait`, `prononççait`, `efforççait`, `exauççait`, `perççait`, `recommenççait`, `renonççait`, `agaççait`, `dénonççait`, `effaççait`, `grinççait`, `suççait`, `traççait`.

2. **Source Restorations:**
   - `conççait` / `conçait` $\rightarrow$ **`conçoit`** (19 occurrences: restored present indicative of *concevoir*, confirmed against page scans: *« On conçoit aisément »*, *« il conçoit de grands projets »*).
   - `diççait` $\rightarrow$ **`disait`** (2 occurrences in Sagesse page 76, printed *difoit*).
   - Hyphenated seam lines: `re-` + `ççait` $\rightarrow$ `re-çoit` (Job 78), `avan-` + `ççait` $\rightarrow$ `avan-çait` (Zacharie 60).

3. **Pipeline Protection in `modernize.py`:**
   - Hardened `replace_oit()` in `modernize.py` so `-cevoir` verbs in the present indicative (`reçoit`, `conçoit`, `aperçoit`, `apperçoit`, `déçoit`) are guarded and never transformed into `-çait`.

---

## 4. Vocative `O` $\rightarrow$ `Ô` (186 replacements)

### Problem
French vocative and exclamative direct addresses standardly take circumflex `Ô`. Old editions frequently used unaccented `O`.

### Applied Rules
1. Standalone `O` before divine titles, sacred names, and direct addresses:
   - `Ô Dieu`, `Ô Seigneur`, `Ô Jésus`, `Ô Christ`, `Ô Père`, `Ô Roi`, `Ô Créateur`, `Ô Maître`, `Ô Prince`, etc.
   - `Ô Israël`, `Ô Jacob`, `Ô Sion`, `Ô Jérusalem`, `Ô Juda`, `Ô Béthel`, `Ô Babel`, etc.
   - `Ô mon âme`, `Ô mon Dieu`, `Ô mon Seigneur`, `Ô mon frère`, `Ô mon fils`, `Ô mon peuple`, `Ô mes frères`, `Ô mes enfants`, `Ô notre Dieu`.
   - `Ô vous`, `Ô toi`, `Ô homme`, `Ô femme`, `Ô mort`, `Ô mortels`, `Ô insensés`, `Ô malheureux`, `Ô génération`, etc.
   - Standalone exclamations: `Ô !`, `Ô ?`.

2. **Strict Preservations:**
   - Latin quotes (`O clavis David`, `O Rex gentium`, etc.) in `latin_quote` and Latin verses.
   - Hebrew alphabetical acrostic headers (`COPH`, `O`).

---

## 5. Obsolete Diaeresis (`¨`) Normalization (222 replacements)

### Problem
In 18th-century French printing and OCR transcription, diaereses (`¨`) were commonly used:
1. Over the silent `e` of feminine participles and adjectives ending in `-u` (`tonduë`, `abbatuë`, `cheveluës`, `interrompuës`, `prévûë`).
2. Over the mute `e` of verbs ending in `-uer` (`diminuë`, `contribuë`, `remuë`, `influë`, `statuë`, `perpetuë`, `restituë`, `exténuë`).
3. Over `y` (`ÿ`) in words like `Enÿvrée`, `paÿs`, or names (`Martianaÿ`, `Tÿrin`).
4. Over `o` (`oë`) in archaic spellings like `boëte`, `coëffure`, `moëlle`.
5. Over `u` (`ü`) in French words (`moüelleuse`, `secoüez`, `joüions`, `doüane`, `remüement`).

### Applied Rules
1. **Participles & Adjectives in `-uë / -uës` $\rightarrow$ `-ue / -ues`**:
   - `tonduë` $\rightarrow$ `tondue`, `abbatuë` $\rightarrow$ `abattue`, `abbattuës` $\rightarrow$ `abattues`, `cheveluës` $\rightarrow$ `chevelues`, `interrompuës` $\rightarrow$ `interrompues`, `prévûë` $\rightarrow$ `prévue`, `devenuë` $\rightarrow$ `devenue`, `bleuës` $\rightarrow$ `bleues`, `accouruës` $\rightarrow$ `accourues`, `fouvenuë` $\rightarrow$ `souvenue`, `acruë` $\rightarrow$ `accrue`, `induës` $\rightarrow$ `indues`, `deffenduës` $\rightarrow$ `défendues`, `devennës` $\rightarrow$ `devenues`, `charrouës` $\rightarrow$ `charrues`, `perluë` $\rightarrow$ `perdue`.

2. **Verbs in `-uer` $\rightarrow$ `-ue`**:
   - `diminuë` $\rightarrow$ `diminue`, `contribuë` $\rightarrow$ `contribue`, `remuë` $\rightarrow$ `remue`, `influë` $\rightarrow$ `influe`, `statuë` $\rightarrow$ `statue`, `perpetuë` $\rightarrow$ `perpétue`, `restituë` $\rightarrow$ `restitue`, `exténuë` $\rightarrow$ `exténue`, `substituë` $\rightarrow$ `substitue`, `continuë` $\rightarrow$ `continue`, `prostituë` $\rightarrow$ `prostitue`, `instituë` $\rightarrow$ `institue`, `vouë` $\rightarrow$ `voue`, `infinuë` $\rightarrow$ `insinue`.
   - Inflected forms: `diminuëront` $\rightarrow$ `diminueront`, `insinuëra` $\rightarrow$ `insinuera`, `continuëraient` $\rightarrow$ `continueraient`, `avouëront` $\rightarrow$ `avoueront`, `prostituëront` $\rightarrow$ `prostitueront`, `excluëra` $\rightarrow$ `exclura`, `concluëra` $\rightarrow$ `conclura`.

3. **Tréma on `ÿ`**:
   - `Enÿvrée` $\rightarrow$ `Enivrée`, `paÿs` $\rightarrow$ `pays`, `Martianaÿ` $\rightarrow$ `Martianay`, `Tÿrin` $\rightarrow$ `Tyrin`, `Ieronÿm` $\rightarrow$ `Ieronym`, `ÿ. 6.` $\rightarrow$ `℣. 6.`.

4. **Archaic `oë`, `ü`, `ä`, `ö` in French**:
   - `boëte` / `boëtes` $\rightarrow$ `boîte / boîtes`, `coëffure` $\rightarrow$ `coiffure`, `moëlle` / `moüelleuse` $\rightarrow$ `moelle / moelleuse`.
   - `secoüez` $\rightarrow$ `secouez`, `joüions` $\rightarrow$ `jouions`, `réüniffez` $\rightarrow$ `réunissez`, `réüffit` $\rightarrow$ `réussit`, `doüane` $\rightarrow$ `douane`, `soüetté` $\rightarrow$ `fouetté`, `remüement` $\rightarrow$ `remuement`.
   - `bäton` $\rightarrow$ `bâton`, `Médäilles` $\rightarrow$ `Médailles`, `nöces` $\rightarrow$ `noces`, `considéröit` $\rightarrow$ `considérait`, `Nathanäel` $\rightarrow$ `Nathanaël`.

5. **Strict Preservations**:
   - Legitimate French diaereses: `aiguë`, `aiguës`, `ciguë`, `ciguës`, `contiguë`, `contiguës`, `ambiguë`, `ambiguës`, `exiguë`, `exiguës`, `suraiguë`.
   - Legitimate biblical and proper names: `Manuë`, `Suë`, `Thécuë`, `Saül`, `Ésaü`, `Emmaüs`, `Capharnaüm`, `Archelaüs`, `Ménélaüs`, `Israël`, `Joël`, `Moïse`, etc.
   - Latin text fields (`latin`, `latin_quote`) are completely bypassed.

---

## 6. Obsolete & Broken Hyphens Normalization (2,618 replacements)

### Problem
Two distinct hyphenation issues exist across the corpus:
1. **18th-century Compound Spellings**: French in the 1700s systematically hyphenated compound adverbs, prepositions, and nouns that modern orthography writes as either a single word (`bien-tôt`, `long-temps`, `aussi-tôt`, `sur-tout`, `par-tout`, `mal-aisé`, `marche-pied`, `vrai-semblable`, `contre-temps`, `haut-bois`) or separate words without hyphens (`même-temps`, `aussi-bien`, `non-seulement`, `dès-lors`, `bonne-heure`, `bonne-chère`, `peu-près`, `mal-à-propos`, `tout-à-fait`, `petit-à-petit`, `bien-aise`, `de-là`, `d'en-bas`, `d'en-haut`).
2. **OCR Mid-Word Line-Wrap Hyphenations**: Words hyphenated at the end of a line in the physical printed page were often digitized with a literal hyphen preserved mid-word (`com-me`, `di-sant`, `afflic-tion`, `cui-vre`, `in-constant`, `Sau-veur`, `Ben-jamin`, `Jo-seph`, `Crain-dre`, `Offi-ciers`, `Prê-tres`, `Commenta-teurs`, `Ro-mains`, `Biblio-thécaires`, `Baby-lonie`, etc.).

### Applied Rules
1. **Single-Word Modernization:**
   - `long-temps` / `Long-temps` $\rightarrow$ `longtemps` / `Longtemps` (567 occurrences)
   - `bien-tôt` / `Bien-tôt` $\rightarrow$ `bientôt` / `Bientôt` (292 occurrences)
   - `aussi-tôt` / `Aussi-tôt` $\rightarrow$ `aussitôt` / `Aussitôt` (279 occurrences)
   - `si-tôt` / `Si-tôt` $\rightarrow$ `sitôt` / `Sitôt` (16 occurrences)
   - `sur-tout` / `Sur-tout` $\rightarrow$ `surtout` / `Surtout` (25 occurrences)
   - `par-tout` / `Par-tout` $\rightarrow$ `partout` / `Partout` (26 occurrences)
   - `mal-aisé(e)(s)` / `Mal-aisé(e)(s)` $\rightarrow$ `malaisé(e)(s)` / `Malaisé(e)(s)` (78 occurrences)
   - `marche-pied(s)` / `Marche-pied(s)` $\rightarrow$ `marchepied(s)` / `Marchepied(s)` (37 occurrences)
   - `vrai-semblable(s)` / `Vrai-semblable(s)` $\rightarrow$ `vraisemblable(s)` / `Vraisemblable(s)` (16 occurrences)
   - `vrai-semblance(s)` / `Vrai-semblance(s)` $\rightarrow$ `vraisemblance(s)` / `Vraisemblance(s)` (11 occurrences)
   - `vrai-semblablement` $\rightarrow$ `vraisemblablement` (1 occurrence)
   - `contre-temps` / `Contre-temps` $\rightarrow$ `contretemps` / `Contretemps` (19 occurrences)
   - `contre-sens` $\rightarrow$ `contresens` (2 occurrences)
   - `haut-bois` $\rightarrow$ `hautbois` (5 occurrences)
   - `bien-faisant(e)(s)` $\rightarrow$ `bienfaisant(e)(s)` (12 occurrences)
   - `bien-heureux` / `bien-heureuse(s)` $\rightarrow$ `bienheureux` / `bienheureuse(s)` (3 occurrences)
   - `bien-séant(e)(s)` $\rightarrow$ `bienséant(e)(s)` (2 occurrences)
   - `mal-habile(s)` $\rightarrow$ `malhabile(s)` (2 occurrences)
   - `mal-propre(s)` / `mal-propreté` $\rightarrow$ `malpropre(s) / malpropreté` (5 occurrences)
   - `mal-faire` $\rightarrow$ `malfaire` (4 occurrences)
   - `mal-avisé(e)(s)` $\rightarrow$ `malavisé(e)(s)` (1 occurrence)
   - `mal-heur` $\rightarrow$ `malheur` (1 occurrence)
   - `non-obstant` $\rightarrow$ `nonobstant` (1 occurrence)
   - `quelque-fois` $\rightarrow$ `quelquefois` (1 occurrence)
   - `clair-voyant(e)(s)` $\rightarrow$ `clairvoyant(e)(s)` (1 occurrence)

2. **Spaced Words Modernization:**
   - `même-temps` / `Même-temps` $\rightarrow$ `même temps` / `Même temps` (163 occurrences)
   - `aussi-bien` / `Aussi-bien` $\rightarrow$ `aussi bien` / `Aussi bien` (176 occurrences)
   - `non-seulement` / `Non-seulement` / `non-feulement` $\rightarrow$ `non seulement / Non seulement` (271 occurrences)
   - `dès-lors` / `Dès-lors` / `dés-lors` $\rightarrow$ `dès lors / Dès lors` (29 occurrences)
   - `bonne-heure` $\rightarrow$ `bonne heure` (13 occurrences)
   - `bonne-chère` $\rightarrow$ `bonne chère` (14 occurrences)
   - `peu-près` $\rightarrow$ `peu près` (27 occurrences)
   - `mal-à-propos` $\rightarrow$ `mal à propos` (52 occurrences)
   - `tout-à-fait` $\rightarrow$ `tout à fait` (64 occurrences)
   - `petit-à-petit` $\rightarrow$ `petit à petit` (9 occurrences)
   - `bien-aise` $\rightarrow$ `bien aise` (8 occurrences)
   - `bien-fait(s)` $\rightarrow$ `bien fait(s)` (5 occurrences)
   - `au-long` $\rightarrow$ `au long` (1 occurrence)
   - `au-travers` $\rightarrow$ `au travers` (5 occurrences)
   - `à-cause` $\rightarrow$ `à cause` (2 occurrences)
   - `d'en-bas` / `en-bas` $\rightarrow$ `d'en bas / en bas` (12 occurrences)
   - `d'en-haut` / `en-haut` $\rightarrow$ `d'en haut / en haut` (6 occurrences)

3. **Demonstrative / Adverbial `de-là` $\rightarrow$ `de là` (205 occurrences):**
   - Modernizes `de-là` to `de là` (*« de là vient »*, *« de là il s'ensuit »*, *« sortir de là »*).
   - Strictly preserves valid compounds: `au-delà`, `par-delà`, `en-deçà`, `jusque-là`.
   - Normalizes rare OCR variants: `au-de-là` $\rightarrow$ `au-delà`, `au-tour de` $\rightarrow$ `autour de`, `au-près de` $\rightarrow$ `auprès de`.

4. **OCR Mid-Word Line-Wrap Hyphenations:**
   - Automatically collapsed to continuous French words: `com-me` $\rightarrow$ `comme`, `di-sant` $\rightarrow$ `disant`, `afflic-tion` $\rightarrow$ `affliction`, `cui-vre` $\rightarrow$ `cuivre`, `in-constant(s)` $\rightarrow$ `inconstant(s)`, `Sau-veur` $\rightarrow$ `Sauveur`, `Ben-jamin` $\rightarrow$ `Benjamin`, `Jo-seph` $\rightarrow$ `Joseph`, `Crain-dre` $\rightarrow$ `Craindre`, `Offi-ciers` $\rightarrow$ `Officiers`, `Prê-tres` $\rightarrow$ `Prêtres`, `Commenta-teurs` $\rightarrow$ `Commentateurs`, `Ro-mains` $\rightarrow$ `Romains`, `Biblio-thécaires` $\rightarrow$ `Bibliothécaires`, `Baby-lonie` $\rightarrow$ `Babylonie`, `Is-raël` $\rightarrow$ `Israël`, `Jé-rusalem` $\rightarrow$ `Jérusalem`, `Zacha-rie` $\rightarrow$ `Zacharie`, `Na-zareth` $\rightarrow$ `Nazareth`, `Eusè-be` $\rightarrow$ `Eusèbe`, `Jérô-me` $\rightarrow$ `Jérôme`, `Jean-Bapriste` $\rightarrow$ `Jean-Baptiste`, etc. (Hebrew decomposition `Emmanu-el` in *« Quia Emmanu-el »* [Isaïe 8:10] is strictly preserved).

5. **Strict Preservations:**
   - Legitimate French compound nouns and adverbs: `peut-être`, `grand-prêtre`, `vis-à-vis`, `par-dessus`, `au-dessus`, `au-dessous`, `au-delà`, `par-delà`, `ci-devant`, `ci-après`, `arc-en-ciel`, `chef-d'œuvre`, `petit-fils`, `beau-père`, `plate-forme`.
   - Inverted verbs with subject pronouns: `est-ce`, `dit-il`, `a-t-on`, `peut-on`.
   - Imperative verbs with object pronouns: `louez-le`, `mettez-la`, `animez-les`, `sauvez-nous`.
   - Biblical Hebrew hyphenated names: `Cariath-iarim`, `Cadés-Barné`, `Beth-Maacha`, `Rabbath-Ammon`.
   - Latin text fields (`latin`, `latin_quote`) are strictly untouched.

---

## 7. Obsolete & Erroneous Circumflex (`^`) Normalization (821 replacements across 650 files)

### Problem
In 18th-century French printing and OCR scanning:
1. **Past participles in `-û`**: 18th-century French frequently put a circumflex on past participles of verbs in *-oir* and *-re* (`lû`, `bû`, `tû`, `eû`, `deçû`, `dépoûrû`), which are obsolete in modern standard French (`lu`, `bu`, `tu`, `eu`, `déçu`, `dépourvu`). Note that `dû` and `mûr` are legitimate and must retain the circumflex.
2. **Long-S and OCR artifacts on `-û`**:
   - `foû` / `soû` (long-s misread) for `fou` (*« Traiter son frère de foû »*, *« enseigner un soû »*).
   - `fû` for `su` (*« n'en ai rien fû »*).
   - `affûre` / `affûré` for `assure` / `assuré`.
   - Spacing artifact `mê ne` for `même` (*« dans la mê ne barque »*).
   - Concatenated pronoun `ellemême` for `elle-même`.
3. **Archaic `aî` in *ailé***: `aîlez` $\rightarrow$ `ailés`, `aîlées` $\rightarrow$ `ailées`, `aîle(s)` $\rightarrow$ `aile(s)`.
4. **Erroneous circumflex on `asûre` / `assûre`**: `asûre` $\rightarrow$ `assure`, `asûrent` $\rightarrow$ `assurent`, `asûrer` $\rightarrow$ `assurer`.
5. **Archaic doubled consonants with circumflex**:
   - `flâme(s)` $\rightarrow$ `flamme(s)`, `enflâme` $\rightarrow$ `enflamme`.
   - `phantôme(s)` $\rightarrow$ `fantôme(s)`.
   - `pêles` $\rightarrow$ `pelles`, `jarêts` $\rightarrow$ `jarrets`.
6. **Archaic `paîtrir` / `pâtrir`**: `paîtri(s/t/r/ssent/rez/n)` $\rightarrow$ `pétri(s/t/r/ssent/rez/n)`, `pâtris` $\rightarrow$ `pétris`, `repaîssez` $\rightarrow$ `repaissez`.
7. **Archaic / obsolete circumflex words**:
   - `piquûre(s)` $\rightarrow$ `piqûre(s)`, `meurtriffûres` $\rightarrow$ `meurtrissures`.
   - `accoûtumance/era/erai` $\rightarrow$ `accoutumance/era/erai`, `plustôt` $\rightarrow$ `plutôt`.
   - `dégoûtans` $\rightarrow$ `dégoûtants`, `sciûre` $\rightarrow$ `sciure`, `pâtiffier` $\rightarrow$ `pâtissier`.
   - `foûtient` $\rightarrow$ `soutient`, `foûterraine` $\rightarrow$ `souterraine`, `soûlié` $\rightarrow$ `soulier`, `soûrire` $\rightarrow$ `sourire`.
   - `nîtreuses` $\rightarrow$ `nitreuses`, `trême` $\rightarrow$ `trame`, `pître` $\rightarrow$ `pitre`, `rébêle` / `rebêle` $\rightarrow$ `rebelle`.
   - `aprêtées` $\rightarrow$ `apprêtées`, `trôn` $\rightarrow$ `trône`, `regîtres` $\rightarrow$ `registres`, `blaspêmes` $\rightarrow$ `blasphèmes`.
   - `accraître` $\rightarrow$ `accroître`, `décraître` $\rightarrow$ `décroître`, `craîtrez` $\rightarrow$ `croîtrez`.
   - `fâcherent` $\rightarrow$ `fâchèrent`, `dêtre` $\rightarrow$ `d'être`, `lâne` $\rightarrow$ `l'âne`, `aîne` $\rightarrow$ `aine`.
   - `scellôit` $\rightarrow$ `scellait`, `confessoîs` $\rightarrow$ `confessais`.
8. **Proper names**: `ierôme` / `iérôme` $\rightarrow$ `Jérôme`, `mathâthias` $\rightarrow$ `Mathathias`, `lasthêne` $\rightarrow$ `Lasthène`, `hérodiâs` $\rightarrow$ `Hérodias`, `eupolême` $\rightarrow$ `Eupolème`, `pamphîlie` $\rightarrow$ `Pamphylie`, `sennachêrib` $\rightarrow$ `Sennachérib`.
9. **Verbs in `-oître` (future & conditional)**: `connoîtra/ront/rai/ras/rait/raient/riez/rions/rons` $\rightarrow$ `connaîtra...`, `reconnoîtra...` $\rightarrow$ `reconnaîtra...`, `disparoît/tra/tront/trait` $\rightarrow$ `disparaît...`, `apparoît/tra/tront` $\rightarrow$ `apparaît...`, `reparoît/tra/tront` $\rightarrow$ `reparaît...`, `comparoîtront` $\rightarrow$ `comparaîtront`.

### Applied Rules & Preservations
- **Strictly preserved French words**: `fête`, `même`, `être`, `père`, `grâce`, `âme`, `bête`, `tête`, `maître`, `connaître`, `abîme`, `apôtre`, `août`, `sûr`, `mûr`, `dû`, `jeûne`, `goût`, `croître`, `traînoir`, `empêcher`, `enchaîner`, `châtier`, `opiniâtrer`, `mâchelière`, `aînesse` (*droit d'aînesse*).
- **Strictly preserved 3rd-person singular imperfect subjunctives**: Verbs ending in `-t` with circumflex are required by French grammar and kept intact: `qu'il éteignît`, `qu'il entreprît`, `qu'il s'abstînt`, `qu'il s'assît`, `qu'il endurcît`, `qu'on applaudît`, `qu'il parût`, `qu'il connût`.
- **Strictly preserved Latin ablatives and 4th declension genitives**: `aquâ`, `terrâ`, `suâ`, `totâ`, `quâ`, `causâ`, `dextrâ`, `linguâ`, `domûs`, `vultûs`, `exercitûs`, `spiritûs` in Latin quotations and Latin verse fields.

---

## 8. Obsolete `y` $\rightarrow$ `i` / `î` / `aie` / `oi` Normalization (355 replacements across 264 files)

### Problem
In 18th-century French printing and OCR transcriptions, the letter `y` was commonly substituted for `i`, `î`, `aie`, or `oi`:
1. **`abyme` $\rightarrow$ `abîme`**: In 18th-century typography, the Greek-derived noun was systematically written *abyme* / *abymes* or *abysme*. In modern French, it is written `abîme` / `abîmes` with a circumflex.
2. **`envyrez` / `envyre` $\rightarrow$ `enivrés` / `enivre`**: Archaic variants of *enivrer* with `y` (*« Tous ces peuples furent envyrez »*, *« On envyre aussi quelquefois les éléphants »*, *« l'ivraie envyvre »*). Also handles `s'enyvrait` $\rightarrow$ `s'enivrait`, `enyvrait` $\rightarrow$ `enivrait`, `envyvrera` $\rightarrow$ `enivrera`, and `n'envyez` $\rightarrow$ `n'enviez`.
3. **Auxiliary / Subjunctive of *avoir***:
   - 3rd-person singular subjunctive: `qu'il n'y aye` $\rightarrow$ `qu'il n'y ait`.
   - 1st-person singular subjunctive: `j'aye`, `l'aye`, `n'aye`, `m'aye`, and standalone French `aye` $\rightarrow$ `j'aie`, `l'aie`, `n'aie`, `m'aie`, `aie` (*« que j'aie dit »*, *« quoique je vous aie offensé »*).
   - Indicative forms: `j'ay` $\rightarrow$ `j'ai`, `n'ay` $\rightarrow$ `n'ai`, `qu'ay-je` $\rightarrow$ `qu'ai-je`, `ay` $\rightarrow$ `ai`.
4. **Ancêtres (*ayeul* $\rightarrow$ *aïeul*)**: `ayeul` $\rightarrow$ `aïeul`, `ayeule` $\rightarrow$ `aïeule`, `ayeuls` $\rightarrow$ `aïeuls`, `ayeules` $\rightarrow$ `aïeules`, `ayeux` $\rightarrow$ `aïeux`, `bisayeul` $\rightarrow$ `bisaïeul`, `bifayeul` $\rightarrow$ `bisaïeul`.
5. **Asile, haie, craie, taie, futaie, claies, braies**:
   - `asyle` / `asyles` $\rightarrow$ `asile` / `asiles`
   - `haye` / `hayes` $\rightarrow$ `haie` / `haies`
   - `futaye` / `futayes` $\rightarrow$ `futaie` / `futaies`
   - `taye` / `tayes` $\rightarrow$ `taie` / `taies` (corneal opacity or membrane)
   - `clayes` $\rightarrow$ `claies`, `brayes` $\rightarrow$ `braies`, `craye` $\rightarrow$ `craie`, `chênaye` $\rightarrow$ `chênaie`
6. **Gaieté & gai**: `gayeté(s)` $\rightarrow$ `gaieté(s)`, `gayement` $\rightarrow$ `gaiement`, `gay` $\rightarrow$ `gai` (*« visage gai »*, *« cœur gai »*).
7. **Days of the week & midi**: `lundy` $\rightarrow$ `lundi`, `mardy` $\rightarrow$ `mardi`, `mercredy` $\rightarrow$ `mercredi`, `jeudy` $\rightarrow$ `jeudi`, `vendredy` $\rightarrow$ `vendredi`, `samedy` $\rightarrow$ `samedi`, `midy` $\rightarrow$ `midi`.
8. **Demonstratives & Adverbs with `cy`**: `cy-après` / `cy après` $\rightarrow$ `ci-après`, `Cy-après` / `Cy après` $\rightarrow$ `Ci-après`, `voicy` $\rightarrow$ `voici`, `celle-cy` $\rightarrow$ `celle-ci`, `gens-cy` $\rightarrow$ `gens-ci`.
9. **Monosyllabic `-oy`**: `loy` / `loys` $\rightarrow$ `loi` / `lois`, `Loy` / `Loys` $\rightarrow$ `Loi` / `Lois`, `foy` / `Foy` $\rightarrow$ `foi` / `Foi`, `moy` $\rightarrow$ `moi`.
10. **Words with `y` before consonants**: `hyrondelle(s)` $\rightarrow$ `hirondelle(s)`, `éclypse(s)` $\rightarrow$ `éclipse(s)`, `tymbale(s)` $\rightarrow$ `timbale(s)`, `cythare(s)` $\rightarrow$ `cithare(s)`, `crystal` $\rightarrow$ `cristal`, `chymérique` $\rightarrow$ `chimérique`, `acrostyche` $\rightarrow$ `acrostiche`, `phtysie` $\rightarrow$ `phtisie`, `hydeux` $\rightarrow$ `hideux`, `vrayment` $\rightarrow$ `vraiment`, `quoyque` $\rightarrow$ `quoique`, `aujourd'huy` $\rightarrow$ `aujourd'hui`, `doyvent` $\rightarrow$ `doivent`, `suye` $\rightarrow$ `suie`, `truyes` $\rightarrow$ `truies`, `enfuye` $\rightarrow$ `enfuie`, `buys` $\rightarrow$ `buis`, `luy` $\rightarrow$ `lui`, `courroyes` $\rightarrow$ `courroies`, `tygre(s)` $\rightarrow$ `tigre(s)`, `sphynx` $\rightarrow$ `sphinx`.
11. **Future tense 1st person singular (`-ray` $\rightarrow$ `-rai`)**: `rendray` $\rightarrow$ `rendrai`, `répandray` $\rightarrow$ `répandrai`, `réduiray` $\rightarrow$ `réduirai`, `traiteray` $\rightarrow$ `traiterai`.
12. **OCR artifact**: `rugissement du Lyon` $\rightarrow$ `rugissement du lion`.

### Strict Preservations
- **Genuine French words with `y`**: `yeux`, `pays`, `style`, `moyen`, `envoyer`, `payer`, `aboyer`, `croire/croyant`, `chrysostome`, `physique`, `symbole`, `type`, `hymne`, `cyprès`, `martyr`, `prosélyte`, `pyramide`, `lyre`, `système`, `synode`, `chrysolithe`, `hysope`, `polyglotte`, `ayez`, `ayons`, etc.
- **Proper nouns with `y`**: `Égypte`, `Babylone`, `Cyrus`, `Syrie`, `Chypre`, `Cyme`, `Hieronym`, `Symmaque`, `Lysias`, and the city of `Lyon` (*« Saint Irénée, près de Lyon »*, *« édition de Lyon »*).
- **Latin text fields**: `latin` and `latin_quote` are strictly excluded.

---

## 9. Missing Apostrophes & Elisions Normalization (`d Orient`, `d une`, `l animal`, `quil`, etc.)

Implemented in `scripts/modernize_inplace.py` (Step 5m & Step 4 update) and verified in `scripts/tests/test_modernize_inplace.py` (`test_missing_apostrophe_cleanup`).

### Patterns & Rules
1. **Missing apostrophe before vowel / mute h with space (118 replacements across 49 volumes):**
   - **`d ` elisions**: `d Orient -> d'Orient`, `d airain -> d'airain`, `d une -> d'une`, `d un -> d'un`, `d adam -> d'Adam`, `d endroit -> d'endroit`, `d elle -> d'elle`, `d officier -> d'Officier`, `d habits -> d'habits`, `d autres / D autres -> d'autres / D'autres`.
   - **`l ` elisions**: `l animal -> l'animal`, `l évangile -> l'Évangile`, `l homme -> l'homme`, `l on -> l'on`, `l entendre -> l'entendre`, `l entendons -> l'entendons`, `l absence -> l'absence`, `l écriture -> l'Écriture`, `l âme -> l'âme`, `l équinoxe -> l'équinoxe`, `l hébreu / L Hébreu -> l'Hébreu / L'Hébreu`.
   - **`qu ` elisions**: `qu il -> qu'il`, `qu elle -> qu'elle`, `qu est -> qu'est`.
   - **`c ` elisions**: `c étaient -> c'étaient`, `c est / C est -> c'est / C'est`.
   - **`n ` elisions**: `n y -> n'y`, `n ait -> n'ait`, `n en -> n'en`.
   - **`s ` elisions**: `s y -> s'y`.
   - **`quelqu ` elisions**: `quelqu un / Quelqu un -> quelqu'un / Quelqu'un`, `quelqu une -> quelqu'une`.
   - **`jusque` before vowels/diphthongs**: `jusque au -> jusqu'au`, `jusque aux -> jusqu'aux` (in verses and commentaries).
   - **`lorsque` before pronouns**: `lorsque il -> lorsqu'il`, `lorsque elle -> lorsqu'elle`.
   - **`que` before `il`**: `que il / que\nil -> qu'il`.

2. **Glued tokens without apostrophe or space (e.g. OCR missing apostrophe entirely):**
   - `dautres / Dautres -> d'autres / D'autres`
   - `quil -> qu'il`
   - `quils -> qu'ils`
   - `quon -> qu'on`
   - `dun -> d'un`
   - `dune -> d'une`
   - `sentendre -> s'entendre`
   - `lopposition -> l'opposition`
   - `noffrirez -> n'offrirez`
   - `lchangeait -> l'échangeait`
   - `si/que lon -> si/que l'on`
   - `qu'on nen -> qu'on n'en`

3. **Whitespace / Newline after apostrophe:**
   - `l' honneur -> l'honneur`
   - `l'\nabandonné -> l'abandonné`

4. **OCR typographical confusions:**
   - `I's ont lu -> Ils ont lu` (apostrophe for `l`)
   - `si's, écoutez -> fils, écoutez` (`si's` for `fils`)
   - `lui-n.ême -> lui-même`
   - `Y a-t il -> Y a-t-il`
   - `ma's emporté -> mais emporté` (`'s` for `is` following `ja-`)
   - `lorsque il nuit approche -> lorsque la nuit approche` (`il` OCR for `la`)
   - `s aint Matthieu -> saint Matthieu`
   - `s e prend -> se prend`
   - `s ouvent -> souvent`
   - `C'es -là -> C'est-là`
   - `l'His toire -> l'Histoire`

### Strict Preservations
- **Latin text fields**: `latin` and `latin_quote` are strictly excluded.
- **Greek transliterations in footnotes**: `d' eè`, `d' enèsi` preserved.
- **Hebrew transliterations**: `Negedyali 'm iphôd` preserved.
- **Grammar discussions on letters**: *« en changeant le D en T, et l'l en r »*, *« L est mis au lieu de R »* preserved.

---

## 10. Miscellaneous Archaic Spellings and Pattern Families

Applied in Step 5n of `modernize_inplace.py` across all 49 volumes (749 replacements across 579 pages).

1. **`éthimologies` $\rightarrow$ `étymologies` (`thi -> ty`)**:
   - `éthimologies` $\rightarrow$ `étymologies`
   - `éthimologie` $\rightarrow$ `étymologie`
   - *Strictly preserves Hebrew place/tribal names*: `Séthim`, `Céthim`, `Céréthims`.

2. **`monstrer` family (mute `s` before `t` in verbs)**:
   - `monstrer` $\rightarrow$ `montrer`, `monstrèrent` $\rightarrow$ `montrèrent`, `monstrée(s)` $\rightarrow$ `montrée(s)`, `monstrera` $\rightarrow$ `montrera`, `monstreront` $\rightarrow$ `montreront`, `monstrez` $\rightarrow$ `montrez`, `monstrant` $\rightarrow$ `montrant`.
   - *Strictly preserves noun*: `monstre` (*un monstre*).

3. **`-ans` / `-ens` plurals $\rightarrow$ `-ants` / `-ents` (`croissans` family)**:
   - `croissans` $\rightarrow$ `croissants`
   - `fréquens` $\rightarrow$ `fréquents`
   - `mécontens` $\rightarrow$ `mécontents`
   - `équivalens` $\rightarrow$ `équivalents`
   - `menaçans` $\rightarrow$ `menaçants`
   - `inconvéniens` $\rightarrow$ `inconvénients`
   - `permanens` $\rightarrow$ `permanents`
   - `fainéans` $\rightarrow$ `fainéants`
   - `turbulens` $\rightarrow$ `turbulents`
   - `glissans` $\rightarrow$ `glissants`
   - `coulans` $\rightarrow$ `coulants`
   - `indifférens` $\rightarrow$ `indifférents`
   - `apparens` $\rightarrow$ `apparents`
   - `commençans` $\rightarrow$ `commençants`
   - `contractans` $\rightarrow$ `contractants`
   - `étonnans` $\rightarrow$ `étonnants`
   - `suffocans` $\rightarrow$ `suffocants`
   - `défians` $\rightarrow$ `défiants`
   - `arpens` $\rightarrow$ `arpents`
   - `accens` $\rightarrow$ `accents`
   - `règlemens` $\rightarrow$ `règlements`
   - `entablemens` $\rightarrow$ `entablements`
   - `battemens` $\rightarrow$ `battements`
   - `relâchemens` $\rightarrow$ `relâchements`
   - `assoupissemens` $\rightarrow$ `assoupissements`
   - `abaissemens` $\rightarrow$ `abaissements`
   - `vomissemens` / `vomiſsemens` $\rightarrow$ `vomissements`
   - `applaudissemens` / `applaudiffemens` $\rightarrow$ `applaudissements`
   - `puiffans` $\rightarrow$ `puissants`
   - `mésdisans` $\rightarrow$ `médisants`
   - `judaïzans` $\rightarrow$ `judaïsants`
   - `impénitens` $\rightarrow$ `impénitents`
   - `déficiens` $\rightarrow$ `déficients`
   - `palpitans` $\rightarrow$ `palpitants`
   - `quadrans` $\rightarrow$ `quadrants`
   - `ingrédiens` $\rightarrow$ `ingrédients`
   - `opulens` $\rightarrow$ `opulents`
   - `insinuans` $\rightarrow$ `insinuants`
   - `communians` $\rightarrow$ `communiants`
   - `fermans` $\rightarrow$ `fermants`
   - `volans` $\rightarrow$ `volants`
   - `clairvoyans` $\rightarrow$ `clairvoyants`
   - `concurrens` $\rightarrow$ `concurrents`
   - `tempéramens` $\rightarrow$ `tempéraments`
   - `truchemens` $\rightarrow$ `truchements`
   - `rassasiemens` $\rightarrow$ `rassasiements`
   - *Strictly preserves genuine words and Latin quotes*: `dedans`, `ans` (after numbers), `rubans`, `artisans`, `partisans`, `courtisans`, `paysans`, `carcans`, `talismans`, `titans`, `tyrans`, `plans`, Latin `demens`, `clemens`, `vomens`, `pertinens`, `agens`, `continens` (with French phrases `vos agents` and `les continents` targeted safely).

4. **`brasselets` family (`ss -> c`)**:
   - `brasselet(s)` $\rightarrow$ `bracelet(s)`
   - `sausse(s)` $\rightarrow$ `sauce(s)`
   - `nasselle(s)` $\rightarrow$ `nacelle(s)`
   - `entrelassé(e)(s)` $\rightarrow$ `entrelacé(e)(s)`
   - `entrelassent` $\rightarrow$ `entrelacent`
   - `entrelassez` $\rightarrow$ `entrelacez`
   - `enlassez` $\rightarrow$ `enlacez`

5. **`Genéfe` (OCR long-s in Book Title)**:
   - `Genéfe` $\rightarrow$ `Genèse` (in *« Voyez notre Commentaire sur la Genéfe »*).

6. **Contextual `par tout` $\rightarrow$ `partout`**:
   - Converted when used as adverbial `partout`:
     - Before punctuation (`,`, `.`, `;`, `:`, `!`, `?`): `fouillé partout,`, `régnera partout.`
     - Before adverbs and conjunctions: `partout où`, `partout ailleurs`.
     - In general verbal/adverbial constructions: `battit partout`, `cherche partout`, `porta partout la mort`, `placez partout des sentinelles`, `Je lui déclare partout une guerre`.
   - *Strictly preserves determiner constructions*: `par tout le...`, `par tout un...`, `par tout ce...`, `par tout cet...`, `par tout ceci...`, `par tout cela...`, `par tout son...`, `par tout Israël`, `par tout homme`, `par tout l'...` (e.g. `par tout l'Orient`, `par tout l'univers`, `par tout le monde`).

7. **`bled` family (`final mute d -> é`)**:
   - `bled` $\rightarrow$ `blé`
   - `bleds` $\rightarrow$ `blés`

8. **`gozier` family (archaic `z -> s`)**:
   - `gozier(s)` $\rightarrow$ `gosier(s)`
   - `magazin(s)` $\rightarrow$ `magasin(s)`
   - `cizeau(x)` $\rightarrow$ `ciseau(x)`, `cizelé(e)(s)` $\rightarrow$ `ciselé(e)(s)`
   - `hazard` / `hazards` $\rightarrow$ `hasard` / `hasards`
   - `hazarder`, `hazardent`, `hazardez`, `hazardait`, `hazardaient`, `hazardèrent`, `hazarderait`, `hazarderaient`, `hazarderont`, `hazardera`, `hazardé(e)(s)`, `hazardant` $\rightarrow$ `hasard...`
   - `nazeaux` $\rightarrow$ `naseaux`
   - `azile(s)` $\rightarrow$ `asile(s)`
   - `ozier(s)` $\rightarrow$ `osier(s)`
   - `bize` $\rightarrow$ `bise`
   - `sarrazin(s)` $\rightarrow$ `sarrasin(s)`

9. **`robbe` family (consonant normalization)**:
   - `robbe(s)` $\rightarrow$ `robe(s)`
   - `abbattre` / `abbattu(s)` / `abbattue(s)` / `abbatu(s)` / `abbatue(s)` $\rightarrow$ `abatt...`
   - `abbattement(s)` / `abbatement` $\rightarrow$ `abattement(s)`
   - `abbat` $\rightarrow$ `abat`, `abbattent` $\rightarrow$ `abattent`, `abbattront` / `abbatront` $\rightarrow$ `abattront`, `abbattra` $\rightarrow$ `abattra`, `abbattrai` $\rightarrow$ `abattrai`, `abbattit` / `abbatit` $\rightarrow$ `abattit`, `abbattant` $\rightarrow$ `abattant`, `abbattaient` $\rightarrow$ `abattaient`
   - `rabbaissaient` $\rightarrow$ `rabaissaient`
   - `abbaisser`, `abbaissez`, `abbaissent`, `abbaissée(s)`, `abbaissement(s)` $\rightarrow$ `abaiss...`
   - `embaras`, `embarasse(nt)`, `embarassé(e)(s)`, `embarasser`, `embarassaient`, `embarassant`, `embarasseront`, `débarasser`, `débarassent`, `débarassé` $\rightarrow$ `embarras... / débarras...`
   - `nouriture(s)` $\rightarrow$ `nourriture(s)`, `nourir` $\rightarrow$ `nourrir`, `nourissent` $\rightarrow$ `nourrissent`
   - `canelle(s)` $\rightarrow$ `cannelle(s)`
   - `houpe(s)` $\rightarrow$ `houppe(s)`, `hupe(s)` $\rightarrow$ `huppe(s)`
   - `échaper`, `échapera`, `échapez`, `échapent`, `échapant` $\rightarrow$ `échapp...`
   - `bastonade(s)` $\rightarrow$ `bastonnade(s)`
   - `fanné(e)(s)`, `fannera` $\rightarrow$ `fané(e)(s)`, `fanera`
   - `floccon(s)` $\rightarrow$ `flocon(s)`
   - `agraffe(s)` $\rightarrow$ `agrafe(s)`
   - `applanir`, `applanira`, `applanissez`, `applanirai`, `applanirez`, `applanisse`, `applaniront`, `applanit`, `applanissant` $\rightarrow$ `aplanir...`
   - `appaiser`, `appaifer`, `appaiserons`, `appaisions`, `appaiserait`, `appaifa`, `appaiferai`, `appaisé(e)(s)` $\rightarrow$ `apaiser...`
   - `abboyeur` $\rightarrow$ `aboyeur`
   - `abbreuvera` $\rightarrow$ `abreuvera`
   - `abbréviateur` $\rightarrow$ `abréviateur`
   - `carrouge` $\rightarrow$ `carouge`

---

## 11. Expansion of Abbreviations: `l'Heb.` and `Chap.` (1,339 replacements)

### Problem
Calmet's text frequently leaves references to the Hebrew text/original abbreviated as `l'Heb.`, `l'Héb.`, `l'Hébr.`, `L'Héb.`, `l'Hebr.`, and chapter headings and cross-references abbreviated as `CHAP.`, `Chap.`, `chap.`, `Ch.`, or `ch.`.

### Applied Rules (Step 5o in `modernize_inplace.py`)

1. **`l'Heb.` Family $\rightarrow$ `l'Hébreu` / `L'Hébreu`**:
   - `l'Heb.`, `l'Héb.`, `l'Hebr.`, `l'Hébr.`, `l'Heb`, `l'Héb` $\rightarrow$ `l'Hébreu`
   - `L'Heb.`, `L'Héb.`, `L'Hebr.`, `L'Hébr.` $\rightarrow$ `L'Hébreu`
   - OCR glitches: `l'Héb.eu` $\rightarrow$ `l'Hébreu`, `l'Hébr u :` $\rightarrow$ `l'Hébreu :`
   - Phrasal: `texte Heb.` / `texte Héb.` $\rightarrow$ `texte hébreu` / `Texte Hébreu`
   - Parenthetical: `(Hébr. _Nééman_)` $\rightarrow$ `(Hébreu _Nééman_)`

2. **`Chap.` Family $\rightarrow$ `Chapitre` / `CHAPITRE`**:
   - **Chapter Titles (`chapter_title`)**:
     `CHAP. IV.` $\rightarrow$ `CHAPITRE IV.` (500 chapter titles updated, unifying with the 830 existing `CHAPITRE` titles).
   - **Singular Cross-References**:
     - `Chap.` before numbers/words $\rightarrow$ `Chapitre` (`Chap. 11.` $\rightarrow$ `Chapitre 11.`, `Chap. premier` $\rightarrow$ `Chapitre premier`)
     - `chap.` before numbers/words $\rightarrow$ `chapitre` (`chap. 10:23.` $\rightarrow$ `chapitre 10:23.`, `chap. xv.` $\rightarrow$ `chapitre xv.`)
     - `Ch.` / `ch.` before numbers/words $\rightarrow$ `Chapitre` / `chapitre` (`Ch. x.` $\rightarrow$ `Chapitre x.`, `ch. 13.` $\rightarrow$ `chapitre 13.`, `Ch. suivant` $\rightarrow$ `Chapitre suivant`)
     - Unpunctuated: `Chap 37:14` $\rightarrow$ `Chapitre 37:14`
   - **Plural Cross-References**:
     - Preceded by determiners/numbers (`les`, `ces`, `aux`, `des`, `deux`, `trois`, `plusieurs`): `les Chap.` $\rightarrow$ `les Chapitres`, `aux chap.` $\rightarrow$ `aux chapitres`
     - Followed by plural adjectives: `Chap. précédents` $\rightarrow$ `Chapitres précédents`, `chap. suivants` $\rightarrow$ `chapitres suivants`
   - **Dot Handling**:
     - Stripped before numbers, ordinals, words, and footnote calls (`Chap. IV.` $\rightarrow$ `Chapitre IV.`, `Chap.^{(a)}` $\rightarrow$ `Chapitre ^{(a)}`).
     - Sentence-ending period preserved at the end of a clause (`...de ce Chap.` $\rightarrow$ `...de ce Chapitre.`).

3. **Strict Preservations (False Positives Avoided)**:
   - Latin citations and critical apparatus in footnotes preserved.
   - Verse numbers (`verses[].french`) completely untouched (0 changes).
   - The French noun `vers` (worms / verses) strictly preserved.

---

## 12. Archaic `oi` $\rightarrow$ `ai` and Verb Endings (125 replacements)

### Problem
In 18th-century French, verbal imperfect/conditional endings (`-ois`, `-oit`, `-oient`), certain present stems (`connoître`, `paroître`, `affoiblir`, `roidir`), and related adjectives and nouns were spelled with `oi`. While most root forms were modernized in earlier passes, inflected, subjunctive, imperfect, compound, OCR long-s/eszett variants, and isolated archaic verb endings remained across the corpus.

### Applied Rules (Step 5p in `modernize_inplace.py`)

1. **`connoître` / `paroître` Inflections and OCR Variants (57 occurrences)**:
   - `paroissez` $\rightarrow$ `paraissez`, `paroissoit` $\rightarrow$ `paraissait`, `paroissoient` $\rightarrow$ `paraissaient`, `paroissons` $\rightarrow$ `paraissons`, `paroissiez` $\rightarrow$ `paraissiez`, `paroissions` $\rightarrow$ `paraissions`
   - `paroitre` $\rightarrow$ `paraître`, `disparoitre` $\rightarrow$ `disparaître`
   - `disparoisse` / `disparoiffe` $\rightarrow$ `disparaisse`, `disparoissions` $\rightarrow$ `disparaissions`, `disparoissoient` $\rightarrow$ `disparaissaient`
   - `apparoissait` $\rightarrow$ `apparaissait`, `apparoissaient` / `apparoissoient` $\rightarrow$ `apparaissaient`, `apparoissions` $\rightarrow$ `apparaissions`
   - `comparoissaient` $\rightarrow$ `comparaissaient`
   - OCR long-s and eszett: `paroiffent` / `paroißent` $\rightarrow$ `paraissent`
   - `connoiffance(s)` $\rightarrow$ `connaissance(s)`, `connoiffent` $\rightarrow$ `connaissent`, `connoiffant` $\rightarrow$ `connaissant`, `connoissoient` $\rightarrow$ `connaissaient`
   - `connoisseurs` $\rightarrow$ `connaisseurs`, `connoissables` $\rightarrow$ `connaissables`
   - `reconnoissiez` $\rightarrow$ `reconnaissiez`, `reconnoissions` $\rightarrow$ `reconnaissions`, `reconnoissoient` $\rightarrow$ `reconnaissaient`, `reconnoiffance(s)` $\rightarrow$ `reconnaissance(s)`, `reconnoiffait` $\rightarrow$ `reconnaissait`, `reconnoiffe` $\rightarrow$ `reconnaisse`, `reconnoissables` $\rightarrow$ `reconnaissables`
   - `méconnoissez` $\rightarrow$ `méconnaissez`, `méconnoîtront` $\rightarrow$ `méconnaîtront`
   - Hyphenated OCR break: `reconnoi-tront` $\rightarrow$ `reconnaîtront`

2. **`foible` / `affoiblir` Family (20 occurrences)**:
   - `affoiblissent` / `affoiblifsent` $\rightarrow$ `affaiblissent`, `affoiblira` $\rightarrow$ `affaiblira`, `affoiblirai` $\rightarrow$ `affaiblirai`, `affoibliffe` $\rightarrow$ `affaiblisse`, `affoiblissait` $\rightarrow$ `affaiblissait`, `affoibliraient` $\rightarrow$ `affaibliraient`
   - `assoiblis` $\rightarrow$ `affaiblis`

3. **`roide` / `roidir` Family (8 occurrences)**:
   - `roidissez` $\rightarrow$ `raidissez`, `roidir` $\rightarrow$ `raidir`, `roidi` $\rightarrow$ `raidi`
   - Missing space: `Ce Roid'Égypte` $\rightarrow$ `Ce Roi d'Égypte`

4. **`monnoie` Family (2 occurrences)**:
   - `monnoie(s)` $\rightarrow$ `monnaie(s)`

5. **`Françoise` / `Narbonnoise` Adjectives (12 occurrences)**:
   - Adjective / language: `Françoise(s)` $\rightarrow$ `Française(s)`, `françoise(s)` $\rightarrow$ `française(s)` (*« Version Françoise »*, *« Traduction Françoise »*, *« langue Françoise »*)
   - `Narbonnoise` $\rightarrow$ `Narbonnaise` (*« Gaule Narbonnoise »*)
   - Proper noun strictly preserved: *François* (27 occurrences, e.g. *François de Vitoria*, *François Valois*, *saint François*)

6. **Isolated Archaic `-oit` / `-oient` Verb Endings and Contractions (17 occurrences)**:
   - `duisoit` $\rightarrow$ `duisait`, `obsedoit` $\rightarrow$ `obsédait`, `laveroît` $\rightarrow$ `laverait`, `dérivoit` / `dévivoit` $\rightarrow$ `dérivait`, `disoit` $\rightarrow$ `disait`, `lisoient` / `liloit` $\rightarrow$ `lisaient` / `lisait`, `blanchissoit` $\rightarrow$ `blanchissait`, `siffloient` $\rightarrow$ `sifflaient`, `assiégeoint` $\rightarrow$ `assiégeaient`, `prenoiens` $\rightarrow$ `prenaient`, `descendroiens` $\rightarrow$ `descendraient`, `étoiens` $\rightarrow$ `étaient`, `croistrons` $\rightarrow$ `croîtront`, `estoit` $\rightarrow$ `était` (`c'estoit` $\rightarrow$ `c'était`, `N'estoit-ce` $\rightarrow$ `N'était-ce`), `empêcheroitelle` $\rightarrow$ `empêcherait-elle`, `dequoi` $\rightarrow$ `de quoi`, `veloppoit` $\rightarrow$ `enveloppait`
   - Miscellaneous: `moïen` $\rightarrow$ `moyen`, `cicoigne` $\rightarrow$ `cigogne`, `refectoire` / `resectoire` $\rightarrow$ `réfectoire`

7. **Strict Preservations (False Positives Avoided)**:
   - Genuine modern French words with `oi`: `froid`, `froide`, `froids`, `froides`, `froideur`, `refroidir`, `refroidi`, `refroidissement`, `refroidira`, `refroidit`, `parois` (walls of the sanctuary), `bois`, `roi`, `loi`, `moi`, `toi`, `soi`, `fois`, `mois`, `poids`, `trois`, `doit`, `droit`, `étroit`, `choix`, `croire`, `croître`, `voir`, `noir`, `soir`, `foi`, `voix`, `croix`, `noix`, `soie`, `voie`, `joie`, `proie`, `gloire`, `mémoire`, `histoire`, `victoire`, `poisson`, `toile`, `voile`, `étoile`, `moindre`, `moins`, `point`, `témoin`, `besoin`, `soin`, `coin`, `loin`, `reçoit`, `conçoit`, `aperçoit`, `déçoit`, `boire`, `boit`, `soit`, `quoique`, `pourquoi`.
   - Proper nouns: `Paros` (the island), `Pierre de Blois`, `Valois`, `François`.
   - First-person plural verb forms in `-ons`: `comparons`, `préparons`, `réparons`, `séparons`.

---

## 13. Classical Plural Past Participles & Adjectives (`-ez` $\rightarrow$ `-és`) vs 2nd Person Plural / Imperative Preservations

In Classical pre-1740 French orthography, masculine plural past participles of 1st-conjugation verbs and adjectives ending in `-é` were written with `-ez` (`aimé` $\rightarrow$ plural `aimez`, `élevé` $\rightarrow$ `élevez`, `déchiré` $\rightarrow$ `déchirez`). Because 2nd-person plural present indicative and imperative verbs also end in `-ez` (*« Vous élevez vos mains »*, *« Sauvez-moi ! »*, *« Déchirez vos cœurs »*), normalization requires careful separation of unconditional pure participles/nouns from contextual disambiguation.

**280 occurrences across 253 pages** have been normalized across all 49 volumes:

1. **Unconditional Plural Participles & Adjectives (103 words, 209 occurrences)**:
   - Words with 0% verbal usage across Dom Calmet's text, directly modernized in `WORD_MAP`:
     - `passionnez` $\rightarrow$ `passionnés`, `ensanglantez` $\rightarrow$ `ensanglantés`, `entortillez` $\rightarrow$ `entortillés`
     - `abandonez` $\rightarrow$ `abandonnés`, `abbreuvez` / `abreuvez` $\rightarrow$ `abreuvés`, `abrogez` $\rightarrow$ `abrogés`, `abrégez` $\rightarrow$ `abrégés`, `accréditez` $\rightarrow$ `accrédités`, `acharnez` $\rightarrow$ `acharnés`, `addonnez` $\rightarrow$ `adonnés`, `adoptez` $\rightarrow$ `adoptés`, `affigez` $\rightarrow$ `affligés`, `aifez` $\rightarrow$ `aisés`, `ammoncelez` $\rightarrow$ `amoncelés`, `amorcez` $\rightarrow$ `amorcés`, `apprivoisez` $\rightarrow$ `apprivoisés`, `apprêtez` $\rightarrow$ `apprêtés`, `aquittez` $\rightarrow$ `acquittés`, `assigez` / `assiégez` $\rightarrow$ `assiégés`, `avisez` $\rightarrow$ `avisés`, `blessez` $\rightarrow$ `blessés`, `caparaçonnez` $\rightarrow$ `caparaçonnés`, `cassez` $\rightarrow$ `cassés`, `choquez` $\rightarrow$ `choqués`, `citez` $\rightarrow$ `cités`, `collez` $\rightarrow$ `collés`, `conditionnez` $\rightarrow$ `conditionnés`, `consternez` $\rightarrow$ `consternés`, `décharnez` $\rightarrow$ `décharnés`, `dégoûtez` $\rightarrow$ `dégoûtés`, `dénommez` $\rightarrow$ `dénommés`, `déposez` $\rightarrow$ `déposés`, `dérivez` $\rightarrow$ `dérivés`, `déréglez` $\rightarrow$ `déréglés`, `déséchez` $\rightarrow$ `desséchés`, `désignez` $\rightarrow$ `désignés` (16 occs), `désinteressez` $\rightarrow$ `désintéressés`, `désolez` $\rightarrow$ `désolés`, `détrompez` $\rightarrow$ `détrompés`, `développez` $\rightarrow$ `développés`, `dévouez` $\rightarrow$ `dévoués`, `distinguez` $\rightarrow$ `distingués` (13 occs), `effraïez` $\rightarrow$ `effrayés`, `efféminez` $\rightarrow$ `efféminés` (8 occs), `enchaînez` $\rightarrow$ `enchaînés`, `enchaffez` $\rightarrow$ `enchâssés`, `enfermez` $\rightarrow$ `enfermés`, `enflamez` / `enflâmez` $\rightarrow$ `enflammés`, `enfoncez` $\rightarrow$ `enfoncés`, `enlacez` $\rightarrow$ `enlacés`, `enragez` $\rightarrow$ `enragés`, `enslez` $\rightarrow$ `enflés`, `entassez` $\rightarrow$ `entassés`, `entez` $\rightarrow$ `entés`, `entrelacez` $\rightarrow$ `entrelacés`, `expolez` $\rightarrow$ `exposés`, `exprimez` $\rightarrow$ `exprimés`, `exterrninez` $\rightarrow$ `exterminés`, `exténuez` $\rightarrow$ `exténués`, `fabriquez` $\rightarrow$ `fabriqués`, `fiancez` $\rightarrow$ `fiancés`, `forgez` $\rightarrow$ `forgés`, `fouettez` $\rightarrow$ `fouettés`, `frapez` $\rightarrow$ `frappés`, `frisez` $\rightarrow$ `frisés`, `glacez` $\rightarrow$ `glacés`, `habillez` $\rightarrow$ `habillés`, `habituez` $\rightarrow$ `habitués`, `humectez` $\rightarrow$ `humectés`, `incommoddez` $\rightarrow$ `incommodés`, `indignez` $\rightarrow$ `indignés`, `intéressez` $\rightarrow$ `intéressés`, `liguez` $\rightarrow$ `ligués`, `maltratez` $\rightarrow$ `maltraités`, `marquetez` $\rightarrow$ `marquetés`, `mocquez` $\rightarrow$ `moqués`, `noïez` $\rightarrow$ `noyés`, `parsemez` $\rightarrow$ `parsemés`, `peignez` $\rightarrow$ `peignés`, `piquottez` $\rightarrow$ `piquotés`, `plombez` $\rightarrow$ `plombés`, `prophanez` $\rightarrow$ `profanés`, `préordonnez` $\rightarrow$ `préordonnés`, `prépolez` $\rightarrow$ `préposés`, `précédez` $\rightarrow$ `précédés`, `préjugez` $\rightarrow$ `préjugés`, `rongez` $\rightarrow$ `rongés`, `rouillez` $\rightarrow$ `rouillés`, `réfutez` $\rightarrow$ `réfutés`, `réprouvez` $\rightarrow$ `réprouvés`, `senversez` $\rightarrow$ `renversés`, `situez` $\rightarrow$ `situés`, `solemnisez` $\rightarrow$ `solennisés`, `subjugez` $\rightarrow$ `subjugués`, `suffoquez` $\rightarrow$ `suffoqués`, `surnommez` $\rightarrow$ `surnommés`, `tachetez` $\rightarrow$ `tachetés`, `transplantez` $\rightarrow$ `transplantés`, `échappez` $\rightarrow$ `échappés`.

2. **Unconditional Classical Nouns in `-ez` $\rightarrow$ `-ès`, `-és`, `-ers` (10 words, 16 occurrences)**:
   - `accez` $\rightarrow$ `accès`, `comoditez` $\rightarrow$ `commodités`, `damnez` $\rightarrow$ `damnés`, `déjeunez` $\rightarrow$ `déjeuners`, `démêlez` $\rightarrow$ `démêlés`, `folemnitez` $\rightarrow$ `solennités`, `incensez` $\rightarrow$ `insensés`, `necessitez` $\rightarrow$ `nécessités`, `procez` $\rightarrow$ `procès`, `sterilitez` $\rightarrow$ `stérilités`, `succcez` $\rightarrow$ `succès`.

3. **Contextual Plural Participles vs Imperative / Verb Forms (55 occurrences)**:
   - `déchirez` $\rightarrow$ `déchirés` (12 occurrences): when preceded by *habits*, *vêtements*, or *blessés, et* (*« ayant leurs vêtements déchirés »*, *« en habits sales, et déchirés »*). Imperatives preserved: *« Déchirez vos cœurs »*, *« Déchirez vos vêtements »*, *« ne déchirez point vos habits »*.
   - `fondez` $\rightarrow$ `fondés` (13 occurrences): all non-imperative occurrences (*« attachés au Seigneur, fondés sur la pierre »*, *« n'étaient point fondés sur la vérité »*). Imperative preserved: *« Fondez votre or »* (Ecclésiastique 468).
   - `abaissez` $\rightarrow$ `abaissés` (5 occurrences): when preceded by *seront*, *feront*, *ou*, *et*, *être* (*« les yeux des superbes seront abaissés »*, *« ceux qui sont humiliés, et abaissés »*). Imperatives preserved: *« Abaissez vos mains »*, *« Abaissez vos cieux »*, *« abaissez votre cœur »*, *« abaissez-vous »*.
   - `avancez` $\rightarrow$ `avancés` (3 occurrences): when preceded by *aussi*, *fruits*, *beaucoup* (*« s'étaient beaucoup avancés »*, *« fruits avancés »*, *« aussi avancés l'un que l'autre »*). Verbs preserved: *« ce que vous avancez »*, *« avancez-vous »*, *« avancez hardiment »*, *« Avancez toujours »*.
   - `appuyez` $\rightarrow$ `appuyés` (3 occurrences): when preceded by *adopté,*, *hasard,*, *conséquence* (*« adoptés, appuyés sur quelques passages »*, *« appuyés sur de simples conjectures »*). Verbs preserved: *« ne vous appuyez point »*, *« vous vous appuyez sur »*, *« sur quoi vous appuyez-vous »*.
   - `sauvez` $\rightarrow$ `sauvés` (9 occurrences): when preceded by *nous serons*, *nombre de*, *de sauvez que* (*« et nous serons sauvés »*, *« un très petit nombre de sauvés »*, *« il n'y aura de sauvés que »*). Verbs and imperatives preserved (105 occurrences): *« Sauvez votre vie »*, *« Sauvez-moi »*, *« Sauvez-nous »*, *« sauvez-vous »*, *« vous les sauvez »*.
   - `élevez` $\rightarrow$ `élevés` (10 occurrences): when preceded by *grands, et*, *gazons,*, *sont*, *nourris, et*, *j'ai*, *j'avais*, *vent*, *plus* (*« j'ai nourris, et élevés »*, *« autels de gazons, élevés »*, *« tuyaux à vent élevés »*, *« vous ne marcherez plus élevés »*). Verbs and imperatives preserved (125 occurrences): *« Élevez vos mains »*, *« Élevez vos voix »*, *« vous vous élevez »*, *« ne vous élevez point »*.

4. **Strict Preservations (False Positives Avoided)**:
   - Proper names ending in `-ez`: *Mendez* (*Fernand Mendez Pinto*), *Sánchez*, *Séez* (*saint Martin de Séez*), *Tellez* (*PP. Lobo et Tellez*), *Cenez*, *Cénez*, *Ascénez*, *Ascenez*, *Aschenez*, *Asphenez*, *Asphénez*, *Gezez*, *Fez*, *Bez*, *Abenez*.
   - Technical / Hebrew terms: *taschbez*.
   - All genuine 2nd-person plural present indicative and imperative verbs: *« Sauvez votre vie »*, *« Élevez vos mains »*, *« Déchirez vos cœurs »*, *« Abaissez vos mains »*, *« ne vous appuyez point »*, etc.

---

## 14. How to Apply to Future Volumes

When processing a new volume (e.g. `48_marc`):

1. **Run in-place modernization:**
   ```bash
   cd scripts
   python3 modernize_inplace.py <volume_folder>
   ```
   To test changes beforehand without modifying files:
   ```bash
   python3 modernize_inplace.py <volume_folder> --dry-run
   ```

2. **Run test suite:**
   ```bash
   uv run --no-project --with pytest --with pillow python -m pytest tests -q
   ```
