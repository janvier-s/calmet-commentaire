import json
import re
from pathlib import Path
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import sys

import clean_mechanical
from paths import DATA

WORD_MAP = {
    # Tems and Accents
    "tems": "temps",
    "colére": "colère",
    "coléres": "colères",
    "reméde": "remède",
    "remédes": "remèdes",
    "maniére": "manière",
    "maniéres": "manières",
    "matiére": "matière",
    "matiéres": "matières",
    "priére": "prière",
    "priéres": "prières",
    "premiére": "première",
    "premiéres": "premières",
    "derniére": "dernière",
    "derniéres": "dernières",
    "entiére": "entière",
    "entiéres": "entières",
    "lumiére": "lumière",
    "lumiéres": "lumières",
    "arriére": "arrière",
    "carriére": "carrière",
    "carriéres": "carrières",
    "riviéres": "rivières",
    "riviére": "rivière",
    "poussiére": "poussière",
    "prophéte": "prophète",
    "prophétes": "prophètes",
    "interpréte": "interprète",
    "interprétes": "interprètes",
    "modéle": "modèle",
    "modéles": "modèles",
    "mystére": "mystère",
    "mystéres": "mystères",
    "aprés": "après",
    "trés": "très",
    "prés": "près",
    "succés": "succès",
    "accés": "accès",
    "excés": "excès",
    "procés": "procès",
    "décés": "décès",
    "sévere": "sévère",
    "séveres": "sévères",
    "fidele": "fidèle",
    "fideles": "fidèles",
    "zele": "zèle",
    "zeles": "zèles",
    "septiéme": "septième",
    "septiémes": "septièmes",
    "huitiéme": "huitième",
    "huitiémes": "huitièmes",
    "neuviéme": "neuvième",
    "neuviémes": "neuvièmes",
    "dixiéme": "dixième",
    "dixiémes": "dixièmes",
    "onziéme": "onzième",
    "douziéme": "douzième",
    
    # Plural -ns -> -nts
    "enfans": "enfants",
    "parens": "parents",
    "sentimens": "sentiments",
    "jugemens": "jugements",
    "mouvemens": "mouvements",
    "commandemens": "commandements",
    "châtimens": "châtiments",
    "élémens": "éléments",
    "tourmens": "tourments",
    "fondemens": "fondements",
    "instrumens": "instruments",
    "argumens": "arguments",
    "puissans": "puissants",
    "présens": "présents",
    "suivans": "suivants",
    "vivans": "vivants",
    "habitans": "habitants",
    "méchans": "méchants",
    "descendans": "descendants",
    "inconstans": "inconstants",
    "sanglans": "sanglants",
    "triomphans": "triomphants",
    "mourans": "mourants",
    "croyans": "croyants",
    "pensans": "pensants",
    "constans": "constants",
    "absens": "absents",
    "innocens": "innocents",
    "pénitens": "pénitents",
    "excellens": "excellents",
    "differens": "différents",
    "différens": "différents",
    "ardens": "ardents",
    "serpens": "serpents",

    # Tréma diphthongs
    "loüer": "louer",
    "loüé": "loué",
    "loüée": "louée",
    "loüés": "loués",
    "loüées": "louées",
    "loüange": "louange",
    "loüanges": "louanges",
    "loüerai": "louerai",
    "loüera": "louera",
    "loüeront": "loueront",
    "loüez": "louez",
    "loüable": "louable",
    "loüables": "louables",
    "joüir": "jouir",
    "joüi": "joui",
    "joüissant": "jouissant",
    "joüissance": "jouissance",
    "joüissances": "jouissances",
    "joüira": "jouira",
    "joüiront": "jouiront",
    "réjoüir": "réjouir",
    "réjoüi": "réjoui",
    "réjoüira": "réjouira",
    "réjoüiront": "réjouiront",
    "réjoüissent": "réjouissent",
    "réjoüissance": "réjouissance",
    "réjoüissances": "réjouissances",
    "soüiller": "souiller",
    "soüillé": "souillé",
    "soüillée": "souillée",
    "soüillés": "souillés",
    "soüillées": "souillées",
    "soüillure": "souillure",
    "soüillures": "souillures",
    "soüillent": "souillent",
    "soüillait": "souillait",
    "secoüer": "secouer",
    "secoüé": "secoué",
    "avouër": "avouer",
    "dévouër": "dévouer",
    "dévouërent": "dévouèrent",
    "échoüer": "échouer",
    "foüet": "fouet",
    "foüets": "fouets",
    
    # Vowels y -> i, oi -> ai, circumflexes
    "joye": "joie",
    "joyes": "joies",
    "voye": "voie",
    "voyes": "voies",
    "payen": "païen",
    "payens": "païens",
    "payenne": "païenne",
    "payennes": "païennes",
    "toûjours": "toujours",
    "vû": "vu",
    "vûe": "vue",
    "vûes": "vues",
    "vûs": "vus",
    "vûë": "vue",
    "vûës": "vues",
    "reçû": "reçu",
    "reçûe": "reçue",
    "reçûs": "reçus",
    "reçûes": "reçues",
    "crû": "cru",
    "pû": "pu",
    "sû": "su",
    "plûtôt": "plutôt",
    "assûrance": "assurance",
    "assûrances": "assurances",
    "assûrer": "assurer",
    "assûré": "assuré",
    "assûrée": "assurée",
    "assûrés": "assurés",
    "assûrées": "assurées",
    "soûmission": "soumission",
    "accoûtumé": "accoutumé",
    "accoûtumée": "accoutumée",
    "accoûtumés": "accoutumés",
    "accoûtumées": "accoutumées",
    "connoître": "connaître",
    "connoît": "connaît",
    "connoissant": "connaissant",
    "connoissent": "connaissent",
    "connoissons": "connaissons",
    "connoissez": "connaissez",
    "connoissance": "connaissance",
    "connoissances": "connaissances",
    "reconnoître": "reconnaître",
    "reconnoît": "reconnaît",
    "reconnoissent": "reconnaissent",
    "reconnoissant": "reconnaissant",
    "reconnoissance": "reconnaissance",
    "paroître": "paraître",
    "paroît": "paraît",
    "paroissent": "paraissent",
    "paroisse": "paraisse",
    "paroissant": "paraissant",
    "apparoître": "apparaître",
    "disparoître": "disparaître",
    "poëte": "poète",
    "poëtes": "poètes",
    "poësie": "poésie",
    "poëme": "poème",
    "poëmes": "poèmes",
    "authorité": "autorité",
    "authorités": "autorités",
    "thrésor": "trésor",
    "thrésors": "trésors",
    "bapthême": "baptême",
    
    # Consonants / adverbs / stragglers
    "quelquefais": "quelquefois",
    "cy-devant": "ci-devant",
    "hazard": "hasard",
    "hazards": "hasards",
    "rejetter": "rejeter",
    "rejjetter": "rejeter",
    "jetter": "jeter",
    "jettent": "jettent",
    "appellé": "appelé",
    "appellée": "appelée",
    "appellés": "appelés",
    "appellées": "appelées",
    "appellait": "appelait",
    "esperance": "espérance",
    "étoit": "était",
    "massoréte": "Massorète",
    "massorétes": "Massorètes",
    "soüillûre": "souillure",
    "soüillûres": "souillures",
    "réüssi": "réussi",
    "réüssir": "réussir",
    "réüssiront": "réussiront",
    "réüssissent": "réussissent",
    "réüssissez": "réussissez",
    
    # 21b additions
    "adhérans": "adhérents",
    "adultére": "adultère",
    "amére": "amère",
    "artéres": "artères",
    "assistans": "assistants",
    "avertissemens": "avertissements",
    "avoüe": "avoue",
    "avoüent": "avouent",
    "boüillonner": "bouillonner",
    "brisemens": "brisements",
    "broüillon": "brouillon",
    "bâtimens": "bâtiments",
    "caractére": "caractère",
    "caractéres": "caractères",
    "centiéme": "centième",
    "changemens": "changements",
    "cinquiéme": "cinquième",
    "combattans": "combattants",
    "commencemens": "commencements",
    "connoisse": "connaisse",
    "connoissions": "connaissions",
    "connoissois": "connaissais",
    "considére": "considère",
    "criniére": "crinière",
    "crûrent": "crurent",
    "derriére": "derrière",
    "deuxiéme": "deuxième",
    "disparoissent": "disparaissent",
    "disparoissons": "disparaissons",
    "dénombremens": "dénombrements",
    "dénoüement": "dénouement",
    "dépoüilles": "dépouilles",
    "dépoüillez": "dépouillez",
    "dépoüillé": "dépouillé",
    "dépoüillée": "dépouillée",
    "dépoüillérent": "dépouillèrent",
    "déréglemens": "dérèglements",
    "elémens": "éléments",
    "emportemens": "emportements",
    "empressemens": "empressements",
    "espére": "espère",
    "excéde": "excède",
    "fidéle": "fidèle",
    "fidéles": "fidèles",
    "infidéle": "infidèle",
    "infidéles": "infidèles",
    "florissans": "florissants",
    "foüillent": "fouillent",
    "foüillé": "fouillé",
    "guére": "guère",
    "guéres": "guère",
    "gémissemens": "gémissements",
    "importans": "importants",
    "joüe": "joue",
    "joüer": "jouer",
    "joüeront": "joueront",
    "joüet": "jouet",
    "joüez": "jouez",
    "languissans": "languissants",
    "legére": "légère",
    "légére": "légère",
    "loüant": "louant",
    "loüent": "louent",
    "loüerons": "louerons",
    "loüis": "louis",
    "mensongéres": "mensongères",
    "ministére": "ministère",
    "misére": "misère",
    "miséres": "misères",
    "momens": "moments",
    "monumens": "monuments",
    "médisans": "médisants",
    "opére": "opère",
    "ornemens": "ornements",
    "oüailles": "ouailles",
    "oüi": "oui",
    "oüis": "ouïs",
    "oüit": "ouït",
    "paralléle": "parallèle",
    "particuliére": "particulière",
    "passans": "passants",
    "persévérans": "persévérants",
    "piége": "piège",
    "piéges": "pièges",
    "privilége": "privilège",
    "priviléges": "privilèges",
    "profére": "profère",
    "protége": "protège",
    "précéde": "précède",
    "préfére": "préfère",
    "quarantiéme": "quarantième",
    "quatriéme": "quatrième",
    "quinziéme": "quinzième",
    "rafraîchissemens": "rafraîchissements",
    "ravissemens": "ravissements",
    "rebéle": "rebelle",
    "rebéles": "rebelles",
    "reconnoissable": "reconnaissable",
    "reconnoisse": "reconnaisse",
    "reconnoissez": "reconnaissez",
    "reconnoissons": "reconnaissons",
    "rejoüissez": "réjouissez",
    "retardemens": "retardements",
    "reçûë": "reçue",
    "reçûës": "reçues",
    "rugissemens": "rugissements",
    "réjoüie": "réjouie",
    "réjoüirai": "réjouirai",
    "réjoüis": "réjouis",
    "réjoüissez": "réjouissez",
    "réjoüissons": "réjouissons",
    "répéte": "répète",
    "secoüant": "secouant",
    "secoüérent": "secouèrent",
    "sermens": "serments",
    "sincére": "sincère",
    "sixiéme": "sixième",
    "siége": "siège",
    "soüillez": "souillez",
    "tempére": "tempère",
    "tressaillemens": "tressaillements",
    "troisiéme": "troisième",
    "uniéme": "unième",
    "voüer": "vouer",
    "voüez": "vouez",
    "zéle": "zèle",
    "ébloüi": "ébloui",
    "ébloüit": "éblouit",
    "éclatans": "éclatants",
    "écoulemens": "écoulements",
    "événemens": "événements",

    # 21c additions
    "abrége": "abrège",
    "alimens": "aliments",
    "amusemens": "amusements",
    "améres": "amères",
    "appartemens": "appartements",
    "barriére": "barrière",
    "barriéres": "barrières",
    "boüillons": "bouillons",
    "broüillard": "brouillard",
    "chaudiére": "chaudière",
    "choüette": "chouette",
    "choüettes": "chouettes",
    "chére": "chère",
    "cimetiére": "cimetière",
    "connois": "connais",
    "connoissiez": "connaissiez",
    "conquérans": "conquérants",
    "crûement": "crûment",
    "différe": "diffère",
    "dénoüemens": "dénouements",
    "dépoüillement": "dépouillement",
    "dépoüiller": "dépouiller",
    "dévorans": "dévorants",
    "errans": "errants",
    "excrémens": "excréments",
    "fromens": "froments",
    "ignorans": "ignorants",
    "infére": "infère",
    "inoüi": "inouï",
    "inoüie": "inouïe",
    "inoüis": "inouïs",
    "joüant": "jouant",
    "joüent": "jouent",
    "joüerai": "jouerai",
    "joüets": "jouets",
    "joüirent": "jouirent",
    "joüit": "jouit",
    "juremens": "jurements",
    "loüa": "loua",
    "loüe": "loue",
    "loüons": "louons",
    "mandemens": "mandements",
    "meurtriére": "meurtrière",
    "meurtriéres": "meurtrières",
    "obéle": "obèle",
    "obéïssans": "obéissants",
    "oüez": "oyez",
    "particuliéres": "particulières",
    "passagére": "passagère",
    "passagéres": "passagères",
    "paupiéres": "paupières",
    "portiére": "portière",
    "posséde": "possède",
    "ravissans": "ravissants",
    "reconnois": "reconnais",
    "reçûrent": "reçurent",
    "roüille": "rouille",
    "réjoüirent": "réjouirent",
    "réjoüissant": "réjouissant",
    "réjoüisse": "réjouisse",
    "réjoüit": "réjouit",
    "sacagemens": "saccagements",
    "singuliére": "singulière",
    "singuliéres": "singulières",
    "soüilla": "souilla",
    "soüillera": "souillera",
    "sphére": "sphère",
    "séduisans": "séduisants",
    "traitemens": "traitements",
    "tréspuissans": "très-puissants",
    "vêtemens": "vêtements",
    "ébloüir": "éblouir",
    "égaremens": "égarements",
    "évanoüis": "évanouis",

    # 22_proverbes additions
    "adultéres": "adultères",
    "agrémens": "agréments",
    "altiére": "altière",
    "assiége": "assiège",
    "avoüant": "avouant",
    "boüillie": "bouillie",
    "broüilleries": "brouilleries",
    "broüillez": "brouillez",
    "cautionnemens": "cautionnements",
    "chaudiéres": "chaudières",
    "comparoitre": "comparaître",
    "compatissans": "compatissants",
    "complaisans": "complaisants",
    "complimens": "compliments",
    "confére": "confère",
    "cueillére": "cuillère",
    "divertissemens": "divertissements",
    "déguisemens": "déguisements",
    "dégénére": "dégénère",
    "dépoüillant": "dépouillant",
    "dépoüille": "dépouille",
    "désagrémens": "désagréments",
    "enchére": "enchère",
    "engagemens": "engagements",
    "enseignemens": "enseignements",
    "etrangére": "étrangère",
    "evenemens": "événements",
    "extréme": "extrême",
    "fragmens": "fragments",
    "fréres": "frères",
    "hazarde": "hasarde",
    "héritiére": "héritière",
    "impuissans": "impuissants",
    "ingére": "ingère",
    "inquiéte": "inquiète",
    "joüera": "jouera",
    "joüeur": "joueur",
    "joüirez": "jouirez",
    "joüirons": "jouirons",
    "joüée": "jouée",
    "manquemens": "manquements",
    "modére": "modère",
    "méme": "même",
    "ménagemens": "ménagements",
    "ménagére": "ménagère",
    "ouvriére": "ouvrière",
    "oüir": "ouïr",
    "paroissois": "paraissais",
    "persévére": "persévère",
    "pesans": "pesants",
    "plaisans": "plaisants",
    "pressans": "pressants",
    "procéde": "procède",
    "prémiére": "première",
    "quenoüille": "quenouille",
    "resistans": "résistants",
    "ressentimens": "ressentiments",
    "retranchemens": "retranchements",
    "roüe": "roue",
    "roüillé": "rouillé",
    "réglemens": "règlements",
    "réjoüirez": "réjouirez",
    "sacremens": "sacrements",
    "soüille": "souille",
    "succéde": "succède",
    "suffisans": "suffisants",
    "suggére": "suggère",
    "séculiéres": "séculières",
    "séme": "sème",
    "sévére": "sévère",
    "sévéres": "sévères",
    "tempérammens": "tempéraments",
    "tisserans": "tisserands",
    "trentiéme": "trentième",
    "troüez": "trouez",
    "vipére": "vipère",
    "ébloüira": "éblouira",
    "ébloüissans": "éblouissants",
    "épithétes": "épithètes",
    "étrangére": "étrangère",
    "étrangéres": "étrangères",
    "roy": "roi",
    "roys": "rois",
    "briéveté": "brièveté",
    "sacrez": "sacrés",
    "qualitez": "qualités",
    "extrémitez": "extrémités",
    "difficultez": "difficultés",
    "véritez": "vérités",
    "côtez": "côtés",
    "iniquitez": "iniquités",
    "volontez": "volontés",
    "calamitez": "calamités",
    "beautez": "beautés",
    "vanitez": "vanités",
    "facilitez": "facilités",
    "bontez": "bontés",
    "libertez": "libertés",
    "sociétez": "sociétés",
    "dignitez": "dignités",
    "clartez": "clartés",
    "rejettez": "rejetez",
    "établissemens": "établissements",

    # 22_proverbes additional vocabulary
    "voüé": "voué",
    "voüée": "vouée",
    "voüés": "voués",
    "voüées": "vouées",
    "voüer": "vouer",
    "avoüez": "avouez",
    "avoüer": "avouer",
    "joüais": "jouais",
    "joüait": "jouait",
    "joüissent": "jouissent",
    "boüillon": "bouillon",
    "loüait": "louait",
    "loüent": "louent",
    "géans": "géants",
    "tranchans": "tranchants",
    "ignorans": "ignorants",
    "savans": "savants",
    "amans": "amants",
    "ambulans": "ambulants",
    "errans": "errants",
    "servans": "servants",
    "torrens": "torrents",
    "précédens": "précédents",
    "accidens": "accidents",
    "prudens": "prudents",
    "imprudens": "imprudents",
    "indigens": "indigents",
    "impatiens": "impatients",
    "intelligens": "intelligents",
    "insolens": "insolents",
    "violens": "violents",
    "diligens": "diligents",
    "espéce": "espèce",
    "espéces": "espèces",
    "homére": "homère",
    "pése": "pèse",
    "antithése": "antithèse",
    "thése": "thèse",
    "piéce": "pièce",
    "piéces": "pièces",
    "reléve": "relève",
    "léve": "lève",
    "enléve": "enlève",
    "soûléve": "soulève",
    "gréce": "grèce",
    "épithéte": "épithète",
    "féve": "fève",
    "féves": "fèves",
    "répéte": "répète",

    # 23_ecclesiaste vocabulary
    "voluptez": "voluptés",
    "incommoditez": "incommodités",
    "inutilitez": "inutilités",
    "obscuritez": "obscurités",
    "infirmitez": "infirmités",
    "libéralitez": "libéralités",
    "adversitez": "adversités",
    "jettez": "jetez",
    "raisonnemens": "raisonnements",
    "évenemens": "événements",
    "évenement": "événement",
    "evenement": "événement",
    "évenements": "événements",
    "vaillans": "vaillants",
    "talens": "talents",
    "embrassemens": "embrassements",
    "joüissez": "jouissez",
    "joüissions": "jouissions",
    "loüerions": "louerions",
    "rejoüissoient": "réjouissaient",
    "rejoüissaient": "réjouissaient",
    "roüillée": "rouillée",
    "broüillards": "brouillards",
    "artére": "artère",
    "artéres": "artères",
    "réguliéres": "régulières",
    "réguliére": "régulière",
    "hypothése": "hypothèse",
    "digére": "digère",
    "tréve": "trêve",
    "chimére": "chimère",
    "archimédes": "archimèdes",
    "dérangemens": "dérangements",
    "agréemens": "agréments",
    "renversemens": "renversements",
    "enchaînemens": "enchaînements",
    "obscurcissemens": "obscurcissements",
    "joüaient": "jouaient",
    "chofe": "chose",
    "chofes": "choses",
    "foleil": "soleil",

    # 24_cantique vocabulary
    "veritez": "vérités",
    "superfluitez": "superfluités",
    "honnêtetez": "honnêtetés",
    "principautez": "principautés",
    "solemnitez": "solennités",
    "ajoûtez": "ajoutez",
    "jumens": "juments",
    "testamens": "testaments",
    "brillans": "brillants",
    "pendans": "pendants",
    "fervens": "fervents",
    "distillans": "distillants",
    "dormans": "dormants",
    "entens": "entends",
    "joües": "joues",
    "verroüil": "verrou",
    "veroüil": "verrou",
    "verroux": "verrous",
    "évanoüissement": "évanouissement",
    "évanoüissemens": "évanouissements",
    "réjoüirons": "réjouirons",
    "réjoüissions": "réjouissions",
    "loüë": "loue",
    "litiére": "litière",
    "litiéres": "litières",
    "bergére": "bergère",
    "bergéres": "bergères",
    "genése": "Genèse",
    "génése": "Genèse",
    "légére": "légère",
    "légéres": "légères",
    "fiére": "fière",
    "fiéres": "fières",
    "achéve": "achève",
    "éléve": "élève",
    "eléves": "élèves",
    "éléves": "élèves",
    "monastére": "monastère",
    "monastéres": "monastères",
    "frontiére": "frontière",
    "frontiéres": "frontières",
    "siéges": "sièges",
    "pére": "père",
    "péres": "pères",
    "mére": "mère",
    "méres": "mères",
    "lucréce": "Lucrèce",
    "vingtiéme": "vingtième",
    "fans": "sans",
    "éloignemens": "éloignements",
    "compartimens": "compartiments",
    "ajustemens": "ajustements",
    "pere": "père",
    "peres": "pères",
    "mere": "mère",
    "meres": "mères",
    "frere": "frère",
    "freres": "frères",

    # 25_sagesse vocabulary
    "divinitez": "divinités",
    "propriétez": "propriétés",
    "assiduitez": "assiduités",
    "déreglemens": "dérèglements",
    "enchantemens": "enchantements",
    "penchans": "penchants",
    "grenoüilles": "grenouilles",
    "grenoüille": "grenouille",
    "dépoüilla": "dépouilla",
    "enfoüit": "enfouit",
    "voüant": "vouant",
    "voüa": "voua",
    "boüeuse": "boueuse",
    "boüeux": "boueux",
    "évanoüir": "évanouir",
    "joüissons": "jouissons",
    "conseillére": "conseillère",
    "conseilléres": "conseillères",
    "sacrilége": "sacrilège",
    "sacriléges": "sacrilèges",
    "séve": "sève",
    "poussiniére": "poussinière",
    "praxitéle": "Praxitèle",
    "treiziéme": "treizième",
    "quatorziéme": "quatorzième",
    "apparoissent": "apparaissent",
    "apparoist": "apparaît",
    "violemens": "violements",
    "tremblemens": "tremblements",
    "heurtemens": "heurtements",
    "sifflemens": "sifflements",
    "médicamens": "médicaments",
    "étonnemens": "étonnements",
    "elemens": "éléments",
    "élemens": "éléments",
    "réjoüissaient": "réjouissaient",
    "joüé": "joué",
    "joüée": "jouée",
    "joüés": "joués",
    "joüées": "jouées",
    "joüissaient": "jouissaient",

    # 26_ecclesiastique vocabulary
    "facultez": "facultés",
    "oüie": "ouïe",
    "foüetter": "fouetter",
    "embroüillez": "embrouillez",
    "embroüille": "embrouille",
    "embroüiller": "embrouiller",
    "broüiller": "brouiller",
    "joüeuse": "joueuse",
    "doüaire": "douaire",
    "avoüera": "avouera",
    "secoüera": "secouera",
    "secoüëra": "secouera",
    "dépoüillera": "dépouillera",
    "dépoüillent": "dépouillent",
    "dépoüillées": "dépouillées",
    "soüillerez": "souillerez",
    "soüilloit": "souillait",
    "réjoüissiez": "réjouissiez",
    "réjoüît": "réjouit",
    "loüiez": "louiez",
    "diéte": "diète",
    "diétes": "diètes",
    "ulcére": "ulcère",
    "ulcéres": "ulcères",
    "austére": "austère",
    "austéres": "austères",
    "céde": "cède",
    "gére": "gère",
    "coopére": "coopère",
    "révére": "révère",
    "révéle": "révèle",
    "familiére": "familière",
    "familiéres": "familières",
    "journaliére": "journalière",
    "journaliéres": "journalières",
    "carnaciére": "carnacière",
    "ministére": "ministère",
    "ministéres": "ministères",
    "jarretiéres": "jarretières",
    "sincére": "sincère",
    "sincéres": "sincères",
    "vipére": "vipère",
    "vipéres": "vipères",
    "troifiéme": "troisième",
    "comparoître": "comparaître",
    "mendians": "mendiants",
    "bienfaisans": "bienfaisants",
    "malfaisans": "malfaisants",
    "flottans": "flottants",
    "rugissans": "rugissants",
    "vigilans": "vigilants",
    "éclattans": "éclatants",
    "embarassans": "embarrassants",
    "épanchemens": "épanchements",
    "éléphans": "éléphants",
    "devorans": "dévorants",
    "craignans": "craignant",
    "sachans": "sachant",
    "aimans": "aimant",
    "étans": "étant",
    "logemens": "logements",
    "débordemens": "débordements",
    "ossemens": "ossements",
    "fentimens": "sentiments",
    "adouciffemens": "adoucissements",
    "doüé": "doué",
    "doüée": "douée",
    "doüés": "doués",
    "doüées": "douées",
    "loüassent": "louassent",
    "joüeurs": "joueurs",
    "loüaient": "louaient",
    "réjoüissait": "réjouissait",
    "joüissait": "jouissait",
    "poüille": "pouille",
    "foüriant": "souriant",
    "réjoüiffez": "réjouissez",
    "oüvrez": "ouvrez",
    "oüons": "ouïons",
    "pluye": "pluie",
    "pluyes": "pluies",

    # 27_isaie vocabulary
    "boüis": "buis",
    "coü": "cou",
    "coüs": "cous",
    "méde": "Mède",
    "médes": "Mèdes",
    "eusébe": "Eusèbe",
    "chaumiéres": "chaumières",
    "chaumiére": "chaumière",
    "sortiléges": "sortilèges",
    "sortilége": "sortilège",
    "museliére": "muselière",
    "museliéres": "muselières",
    "cinquantiéme": "cinquantième",
    "seiziéme": "seizième",
    "paupiére": "paupière",
    "créte": "crête",
    "crétes": "crêtes",
    "guerriére": "guerrière",
    "guerriéres": "guerrières",
    "hémisphére": "hémisphère",
    "hémisphéres": "hémisphères",
    "galéres": "galères",
    "galére": "galère",
    "messagére": "messagère",
    "messagéres": "messagères",
    "filiére": "filière",
    "affiége": "assiège",
    "hurlemens": "hurlements",
    "prospéritez": "prospérités",
    "fenoüil": "fenouil",
    "boüillir": "bouillir",
    "débroüillement": "débrouillement",
    "broüillérent": "brouillèrent",
    "devoüera": "dévouera",
    "secoüa": "secoua",
    "secoüât": "secouât",
    "secoüerent": "secouèrent",
    "secoüerez": "secouerez",
    "avoüerons": "avouerons",
    "dépoüillerai": "dépouillerai",
    "évanoüira": "évanouira",
    "habillemens": "habillements",
    "heurlemens": "hurlements",
    "gouvernemens": "gouvernements",
    "élancemens": "élancements",
    "affoiblissemens": "affaiblissements",
    "éternuëmens": "éternuements",
    "applaussissemens": "applaudissements",
    "dévoüez": "dévouez",
    "désavoüer": "désavouer",
    "foüillez": "fouillez",
    "foüillures": "fouillures",
    "loüëront": "loueront",
    "loüerez": "louerez",
    "avoüons": "avouons",
    "broüilleront": "brouilleront",
    "broüillons": "brouillons",
    "enroüât": "enrouât",
    "oüies": "ouïes",
    "joüiraient": "jouiraient",

    # 28_jeremie vocabulary
    "infidélitez": "infidélités",
    "impudicitez": "impudicités",
    "cruautez": "cruautés",
    "boüillant": "bouillant",
    "boüillante": "bouillante",
    "boüillants": "bouillants",
    "boüillantes": "bouillantes",
    "boüë": "boue",
    "foüillée": "fouillée",
    "foüilla": "fouilla",
    "enfoüi": "enfoui",
    "enfoüis": "enfouis",
    "enroüer": "enrouer",
    "moüillée": "mouillée",
    "roüillez": "rouillez",
    "foüillure": "fouillure",
    "roües": "roues",
    "roüës": "roues",
    "avoüée": "avouée",
    "rejoüissance": "réjouissance",
    "foüette": "fouette",
    "soüillérent": "souillèrent",
    "broüillerie": "brouillerie",
    "dépoüilleront": "dépouilleront",
    "tanniére": "tanière",
    "tanniéres": "tanières",
    "taniére": "tanière",
    "taniéres": "tanières",
    "parenthése": "parenthèse",
    "parenthéses": "parenthèses",
    "réïtére": "réitère",
    "fougére": "fougère",
    "bruyére": "bruyère",
    "briéve": "brève",
    "briéves": "brèves",
    "tolére": "tolère",
    "persevére": "persévère",
    "voliére": "volière",
    "dixéme": "dixième",
    "collége": "collège",
    "tibére": "Tibère",
    "prisonniére": "prisonnière",
    "prisonniéres": "prisonnières",
    "grossiére": "grossière",
    "grossiéres": "grossières",
    "fiége": "siège",
    "perçans": "perçants",
    "crians": "criants",
    "désobéïssans": "désobéissants",
    "brûlans": "brûlants",
    "surprenans": "surprenants",
    "odoriférans": "odoriférants",
    "hennissemens": "hennissements",
    "commandans": "commandants",
    "extravagans": "extravagants",
    "intendans": "intendants",
    "instumens": "instruments",
    "accroissemens": "accroissements",
    "détachemens": "détachements",
    "detachemens": "détachements",
    "mugissemens": "mugissements",
    "ébranlemens": "ébranlements",

    # 29_lamentations vocabulary
    "impuretez": "impuretés",
    "indignitez": "indignités",
    "charmans": "charmants",
    "évanoüie": "évanouie",
    "évanoüies": "évanouies",
    "viscéres": "viscères",
    "sorciére": "sorcière",
    "sorciéres": "sorcières",
    "epithéte": "épithète",
    "emprisonnemens": "emprisonnements",

    # 30_baruch vocabulary
    "captivitez": "captivités",
    "dévoüement": "dévouement",
    "ébloüissent": "éblouissent",
    "reconnoissances": "reconnaissances",
    "soûtiens": "soutiens",
    "inftrumens": "instruments",
    "réjoüiffent": "réjouissent",

    # 31_ezechiel vocabulary
    "antiquitez": "antiquités",
    "déïtez": "déités",
    "autoritez": "autorités",
    "commoditez": "commodités",
    "contrariétez": "contrariétés",
    "diversitez": "diversités",
    "immunitez": "immunités",
    "impietez": "impiétés",
    "impiétez": "impiétés",
    "moralitez": "moralités",
    "méchancetez": "méchancetés",
    "nécessitez": "nécessités",
    "particularitez": "particularités",
    "societez": "sociétés",
    "somptuositez": "somptuosités",
    "variétez": "variétés",
    "députez": "députés",
    "assaisonnemens": "assaisonnements",
    "déhordemens": "débordements",
    "fermens": "ferments",
    "ferremens": "ferrements",
    "frémissemens": "frémissements",
    "ligamens": "ligaments",
    "sarmens": "sarments",
    "assiégeans": "assiégeants",
    "consultans": "consultants",
    "dépendans": "dépendants",
    "frappans": "frappants",
    "geans": "géants",
    "insultans": "insultants",
    "montans": "montants",
    "négocians": "négociants",
    "pénétrans": "pénétrants",
    "remuans": "remuants",
    "tremblans": "tremblants",
    "venans": "venants",
    "élephans": "éléphants",
    "étincelans": "étincelants",
    "ayans": "ayant",
    "tuans": "tuant",
    "ebloüi": "ébloui",
    "ébloüis": "éblouis",
    "avoüa": "avoua",
    "avoüaient": "avouaient",
    "avoüé": "avoué",
    "boüillies": "bouillies",
    "enfoüissent": "enfouissent",
    "enroüillée": "enrouillée",
    "foüettent": "fouettent",
    "foüillant": "fouillant",
    "foüilleront": "fouilleront",
    "foüillées": "fouillées",
    "foüillérent": "fouillèrent",
    "noüait": "nouait",
    "soüillaient": "souillaient",
    "soüillassent": "souillassent",
    "soüillerai": "souillerai",
    "soüilleront": "souilleront",
    "troüveront": "trouveront",
    "échoüa": "échoua",
    "phylactére": "phylactère",
    "phylactéres": "phylactères",
    "taloniére": "talonière",
    "taloniéres": "talonières",
    "soixantiéme": "soixantième",
    "soixantiémes": "soixantièmes",
    "milliéme": "millième",
    "milliémes": "millièmes",
    "fixiéme": "sixième",
    "défordre": "désordre",
    "défordres": "désordres",
    "funébre": "funèbre",
    "funébres": "funèbres",
    "geniévre": "genièvre",
    "chévre": "chèvre",
    "chévres": "chèvres",
    "cédre": "cèdre",
    "cédres": "cèdres",
    "lévre": "lèvre",
    "lévres": "lèvres",
    "frére": "frère",
    "fréres": "frères",
    "délibére": "délibère",
    "délibérent": "délibèrent",
    "assiéte": "assiette",
    "assiétes": "assiettes",

    # 32_daniel vocabulary
    "souverainetez": "souverainetés",
    "formalitez": "formalités",
    "deïtez": "déités",
    "étez": "étés",
    "hyver": "hiver",
    "hyvers": "hivers",
    "avoüérent": "avouèrent",
    "broüet": "brouet",
    "broüille": "brouille",
    "broüillé": "brouillé",
    "broüillée": "brouillée",
    "broüillés": "brouillés",
    "broüillées": "brouillées",
    "broüillant": "brouillant",
    "doüanne": "douane",
    "doüannes": "douanes",
    "dépoüillât": "dépouillât",
    "embroüillée": "embrouillée",
    "embroüillées": "embrouillées",
    "loüai": "louai",
    "moüille": "mouille",
    "moüillé": "mouillé",
    "moüillés": "mouillés",
    "moüillées": "mouillées",
    "moüiller": "mouiller",
    "veillans": "veillants",
    "participans": "participants",
    "prétendans": "prétendants",
    "regnans": "régnants",
    "éblouïssans": "éblouissants",
    "éblouïssant": "éblouissant",
    "éblouïssante": "éblouissante",
    "éblouïssantes": "éblouissantes",
    "ténebres": "ténèbres",
    "ténébres": "ténèbres",
    "tenebres": "ténèbres",
    "théatre": "théâtre",
    "théatres": "théâtres",
    "theatre": "théâtre",
    "theatres": "théâtres",
    "célebre": "célèbre",
    "célebres": "célèbres",
    "célébre": "célèbre",
    "célébres": "célèbres",
    "celebre": "célèbre",
    "celebres": "célèbres",
    "pénétre": "pénètre",
    "pénétrent": "pénètrent",
    "légere": "légère",
    "légeres": "légères",

    # 33_osee vocabulary
    "infidelitez": "infidélités",
    "déitez": "déités",
    "celébre": "célèbre",
    "diamétre": "diamètre",
    "diamétres": "diamètres",
    "géométre": "géomètre",
    "géométres": "géomètres",
    "liévre": "lièvre",
    "liévres": "lièvres",
    "lépre": "lèpre",
    "lepre": "lèpre",
    "étrangere": "étrangère",
    "étrangeres": "étrangères",
    "sépulchre": "sépulcre",
    "sépulchres": "sépulcres",
    "sepulchre": "sépulcre",
    "sepulchres": "sépulcres",
    "nourrissans": "nourrissants",
    "brigans": "brigands",
    "enfoüir": "enfouir",
    "foüille": "fouille",
    "doüaires": "douaires",

    # 34_joel vocabulary
    "gemissemens": "gémissements",
    "haletans": "haletants",
    "poussans": "poussant",
    "raffemblez": "rassemblez",
    "enyvrer": "enivrer",
    "enyvré": "enivré",
    "enyvrée": "enivrée",
    "enyvrés": "enivrés",
    "enyvrées": "enivrées",
    "enyvre": "enivre",
    "enyvrent": "enivrent",
    "enyvrez": "enivrez",
    "enyvrons": "enivrons",
    "enyvrerai": "enivrerai",
    "enyvrera": "enivrera",
    "enyvreras": "enivreras",
    "enyvreront": "enivreront",
    "enyvrerez": "enivrerez",
    "enyvrerions": "enivrerions",
    "enyvra": "enivra",
    "enyvrérent": "enivrèrent",
    "enyvrerent": "enivrèrent",
    "enyvrant": "enivrant",
    "enyvrante": "enivrante",
    "enyvrans": "enivrants",
    "enyvrants": "enivrants",
    "enyvrantes": "enivrantes",
    "enyvrement": "enivrement",
    "enyvremens": "enivrements",
    "yvre": "ivre",
    "yvres": "ivres",
    "yvresse": "ivresse",
    "yvresses": "ivresses",
    "yvrogne": "ivrogne",
    "yvrognes": "ivrognes",
    "yvrognerie": "ivrognerie",
    "yvrogneries": "ivrogneries",
    "yvraie": "ivraie",
    "yvraye": "ivraie",
    "yvrayes": "ivraies",

    # 35_amos vocabulary
    "austéritez": "austérités",
    "hostilitez": "hostilités",
    "inhumanitez": "inhumanités",
    "inégalitez": "inégalités",
    "affermiffez": "affermissez",
    "appaiser": "apaiser",
    "appaise": "apaise",
    "appaisent": "apaisent",
    "appaisez": "apaisez",
    "appaisons": "apaisons",
    "appaisé": "apaisé",
    "appaisés": "apaisés",
    "appaisée": "apaisée",
    "appaisées": "apaisées",
    "appaisa": "apaisa",
    "appaisèrent": "apaisèrent",
    "appaisérent": "apaisèrent",
    "appaiserent": "apaisèrent",
    "appaisera": "apaisera",
    "appaiserai": "apaiserai",
    "appaiseront": "apaiseront",
    "appaisement": "apaisement",
    "appaisemens": "apaisements",
    "appaisant": "apaisant",
    "appaisait": "apaisait",
    "appaisaient": "apaisaient",
    "appercevoir": "apercevoir",
    "appercevant": "apercevant",
    "appercevez": "apercevez",
    "appercevons": "apercevons",
    "apperceviez": "aperceviez",
    "appercevions": "apercevions",
    "appercevais": "apercevais",
    "appercevait": "apercevait",
    "appercevaient": "apercevaient",
    "appercevra": "apercevra",
    "appercevront": "apercevront",
    "appercevrai": "apercevrai",
    "appercevrez": "apercevrez",
    "appercevrions": "apercevrions",
    "appercevroient": "apercevraient",
    "appercevraient": "apercevraient",
    "apperçoit": "aperçoit",
    "apperçoivent": "aperçoivent",
    "apperçois": "aperçois",
    "apperçoive": "aperçoive",
    "apperçu": "aperçu",
    "apperçus": "aperçus",
    "apperçue": "aperçue",
    "apperçues": "aperçues",
    "apperçut": "aperçut",
    "apperçurent": "aperçurent",
    "apperçût": "aperçut",
    "apperçû": "aperçu",
    "apperçûs": "aperçus",
    "apperçûe": "aperçue",
    "apperçûes": "aperçues",
    "apperçûrent": "aperçurent",

    # 36_abdias vocabulary
    "aggrandir": "agrandir",
    "aggrandi": "agrandi",
    "aggrandie": "agrandie",
    "aggrandis": "agrandis",
    "aggrandies": "agrandies",
    "aggrandit": "agrandit",
    "aggrandirent": "agrandirent",
    "aggrandirez": "agrandirez",
    "aggrandissant": "agrandissant",
    "aggrandissement": "agrandissement",
    "aggrandissemens": "agrandissements",
    "delivrez": "délivrez",
    "profererez": "proférerez",

    # 37_jonas vocabulary
    "bêlemens": "bêlements",
    "belemens": "bêlements",
    "belement": "bêlement",
    "gazouillemens": "gazouillements",

    # 38_michee vocabulary
    "revenans": "revenant",
    "voüera": "vouera",
    "voüerez": "vouerez",
    "voüeront": "voueront",
    "voüerai": "vouerai",
    "dévoüer": "dévouer",
    "dévoüé": "dévoué",
    "dévoüée": "dévouée",
    "dévoüés": "dévoués",
    "dévoüées": "dévouées",
    "dévoüera": "dévouera",
    "dévoüerez": "dévouerez",
    "dévoüeront": "dévoueront",
    "dévoüerai": "dévouerai",
    "dévoüent": "dévouent",
    "dévoüait": "dévouait",
    "dévoüaient": "dévouaient",
    "dévoüoit": "dévouait",
    "dévoüoient": "dévouaient",
    "recüeillir": "recueillir",
    "recüeilli": "recueilli",
    "recüeillie": "recueillie",
    "recüeillis": "recueillis",
    "recüeillies": "recueillies",
    "recüeille": "recueille",
    "recüeillent": "recueillent",
    "recüeillez": "recueillez",
    "recüeillons": "recueillons",
    "recüeillit": "recueillit",
    "recüeillirent": "recueillirent",
    "recüeillera": "recueillera",
    "recüeillerai": "recueillerai",
    "recüeillerez": "recueillerez",
    "recüeilleront": "recueilleront",
    "recüeilloit": "recueillait",
    "recüeilloient": "recueillaient",
    "recüeillant": "recueillant",
    "recüeillement": "recueillement",
    "recüeillemens": "recueillements",
    "cüeillir": "cueillir",
    "cüeilli": "cueilli",
    "cüeillie": "cueillie",
    "cüeillis": "cueillis",
    "cüeillies": "cueillies",
    "cüeille": "cueille",
    "cüeillent": "cueillent",
    "cüeillez": "cueillez",
    "cüeillons": "cueillons",
    "cüeillit": "cueillit",
    "cüeillirent": "cueillirent",
    "cüeillera": "cueillera",
    "cüeillerai": "cueillerai",
    "cüeillerez": "cueillerez",
    "cüeilleront": "cueilleront",
    "cüeillant": "cueillant",
    "cüeilloit": "cueillait",
    "cüeilloient": "cueillaient",
    "cüeillette": "cueillette",
    "cüeillettes": "cueillettes",
    "accüeillir": "accueillir",
    "accüeilli": "accueilli",
    "accüeillie": "accueillie",
    "accüeillis": "accueillis",
    "accüeillies": "accueillies",
    "accüeille": "accueille",
    "accüeillent": "accueillent",

    # 39_nahum vocabulary
    "insensez": "insensés",
    "raffurez": "rassurez",
    "étincellans": "étincelants",
    "étincellants": "étincelants",
    "étincellant": "étincelant",
    "étincellante": "étincelante",
    "étincellantes": "étincelantes",
    "étincelloit": "étincelait",
    "étincelloient": "étincelaient",
    "éclatter": "éclater",
    "éclatte": "éclate",
    "éclattent": "éclatent",
    "éclattez": "éclatez",
    "éclatta": "éclata",
    "éclatté": "éclaté",
    "éclattée": "éclatée",
    "éclattés": "éclatés",
    "éclattées": "éclatées",
    "éclattera": "éclatera",
    "éclatterai": "éclaterai",
    "éclatteront": "éclateront",
    "éclatterez": "éclaterez",
    "éclattoit": "éclatait",
    "éclattoient": "éclataient",
    "éclattant": "éclatant",
    "éclattante": "éclatante",
    "éclattants": "éclatants",
    "éclattans": "éclatants",
    "éclattantes": "éclatantes",
    "éclattérent": "éclatèrent",
    "éclatterent": "éclatèrent",

    # 40_habacuc vocabulary
    "fossez": "fossés",
    "santez": "santés",
    "ressemblans": "ressemblants",
    "joüa": "joua",
    "joüeuses": "joueuses",

    # 41_sophonie vocabulary
    "extrêmitez": "extrémités",
    "extremitez": "extrémités",
    "hébêtez": "hébétés",

    # 42_aggee vocabulary
    "appellez": "appelez",
    "rappellez": "rappelez",
    "renouvellez": "renouvelez",
    "bâtiffez": "bâtissez",

    # 43_zacharie vocabulary
    "profpéritez": "prospérités",
    "carquans": "carcans",
    "rafraichissemens": "rafraîchissements",
    "ameublemens": "ameublements",
    "régimens": "régiments",
    "indépendans": "indépendants",
    "demeurans": "demeurants",
    "oüirent": "ouïrent",
    "avoüait": "avouait",
    "dépoüillaient": "dépouillaient",
    "foüiller": "fouiller",
    "heurlez": "hurlez",
    "heurler": "hurler",
    "heurleront": "hurleront",
    "heurlant": "hurlant",
    "heurlé": "hurlé",

    # 44_malachie vocabulary
    "orfévre": "orfèvre",
    "orfévres": "orfèvres",
    "révere": "révère",
    "réverent": "révèrent",
    "supplians": "suppliants",
    "dépoüillais": "dépouillais",

    # 45_1_maccabees vocabulary
    "liberalitez": "libéralités",
    "saletez": "saletés",
    "subtilitez": "subtilités",
    "fiévre": "fièvre",
    "fiévres": "fièvres",
    "fievre": "fièvre",
    "fievres": "fièvres",
    "payement": "paiement",
    "payemens": "paiements",
    "foüler": "fouler",
    "sçachez": "sachez",
    "sçavans": "savants",
    "arrogans": "arrogants",
    "restans": "restants",
    "eléphans": "éléphants",
    "détruifez": "détruisez",
    "réfifterez": "résisterez",
    "gémiffemens": "gémissements",
    "dépoüillait": "dépouillait",
    "dévoüa": "dévoua",
    "soüillât": "souillât",

    # 46_2_maccabees vocabulary
    "communautez": "communautés",
    "contrarietez": "contrariétés",
    "prodigalitez": "prodigalités",
    "encensemens": "encensements",
    "apartenans": "appartenant",
    "normans": "normands",
    "foüettaient": "fouettaient",
    "foüetté": "fouetté",
    "foüettée": "fouettée",
    "joüiffance": "jouissance",
    "réguliere": "régulière",
    "régulieres": "régulières",
    "irréguliere": "irrégulière",
    "irrégulieres": "irrégulières",
    "addressez": "adressez",
    "addresser": "adresser",
    "addresse": "adresse",
    "addresses": "adresses",
    "addressa": "adressa",
    "addressé": "adressé",
    "addressée": "adressée",
    "addressés": "adressés",
    "addressées": "adressées",
    "addressèrent": "adressèrent",
    "addressent": "adressent",

    # Soul
    "ame": "âme",
    "ames": "âmes",

    # Weak
    "foible": "faible",
    "foibles": "faibles",
    "foiblesse": "faiblesse",
    "foiblesses": "faiblesses",
    "foiblement": "faiblement",
    "affoiblir": "affaiblir",
    "affoibli": "affaibli",
    "affoiblit": "affaiblit",
    "affoiblis": "affaiblis",
    "affoiblie": "affaiblie",
    "affoiblies": "affaiblies",
    "affoiblissement": "affaiblissement",
    "affoiblissements": "affaiblissements",

    # Wounds
    "playe": "plaie",
    "playes": "plaies",

    # True
    "vray": "vrai",
    "vraye": "vraie",
    "vrays": "vrais",
    "vrayes": "vraies",
    "vrayement": "vraiment",

    # Grace
    "grace": "grâce",
    "graces": "grâces",

    # Island
    "isle": "île",
    "isles": "îles",

    # Century & Rules
    "siecle": "siècle",
    "siecles": "siècles",
    "regle": "règle",
    "regles": "règles",

    # Same
    "mesme": "même",
    "mesmes": "mêmes",

    # Master
    "maistre": "maître",
    "maistres": "maîtres",
    "maistresse": "maîtresse",

    # Stiff
    "roide": "raide",
    "roides": "raides",
    "roideur": "raideur",
    "roideurs": "raideurs",

    # Why
    "pourquoy": "pourquoi",
    "quoy": "quoi",

    # Vault
    "voute": "voûte",
    "voutes": "voûtes",

    # Priest
    "prestre": "prêtre",
    "prestres": "prêtres",

    # Host
    "hoste": "hôte",
    "hostes": "hôtes",

    # Head
    "testes": "têtes",

    # Clothes
    "vestement": "vêtement",
    "vestemens": "vêtements",

    # Forests
    "forests": "forêts",
    "foreste": "forêt",

    # Please
    "plaist": "plaît",

    # Roles
    "roles": "rôles",
    "role": "rôle",

    # Demonstratives
    "icy": "ici",
    "cecy": "ceci",
    "celuy": "celui",

    # Verbs and participles
    "connoissais": "connaissais",
    "connoiffez": "connaissez",
    "connoissez": "connaissez",
    "connoissait": "connaissait",
    "connoissaient": "connaissaient",
    "connoissant": "connaissant",
    "connoissance": "connaissance",
    "connoissances": "connaissances",
    "paroissais": "paraissais",
    "paroissait": "paraissait",
    "paroissaient": "paraissaient",
    "paroissant": "paraissant",
    "reconnoissais": "reconnaissais",
    "reconnoissait": "reconnaissait",
    "reconnoissaient": "reconnaissaient",
    "reconnoissant": "reconnaissant",
    "reconnoissance": "reconnaissance",
    "reconnoissances": "reconnaissances",
    "pécheroit": "pécherait",
    "sortans": "sortants",
    "lieutenans": "lieutenants",
    "imposans": "imposants",
    "saccagemens": "saccagements",
    "attachemens": "attachements",
    "embrasemens": "embrasements",
    "clémens": "cléments",
    "expédiens": "expédients",
    "démens": "déments",

    # -uë feminine participles
    "venuë": "venue",
    "venuës": "venues",
    "étenduë": "étendue",
    "étenduës": "étendues",
    "connuë": "connue",
    "connuës": "connues",
    "résoluë": "résolue",
    "résoluës": "résolues",
    "reçuë": "reçue",
    "reçuës": "reçues",
    "pourveuë": "pourvue",
    "pourveuës": "pourvues",
    "dûë": "due",
    "dûës": "dues",
    "décheuë": "déchue",
    "décheuës": "déchues",
    "émûë": "émue",
    "émûës": "émues",
    "continuë": "continue",
    "continuës": "continues",

    # -yent verb forms
    "croyent": "croient",
    "ayent": "aient",
    "voyent": "voient",
    "employent": "emploient",
    "envoyent": "envoient",
    "fuyent": "fuient",
    "appuyent": "appuient",
    "essuyent": "essuient",

    # y -> i / i -> y nouns & adverbs
    "proye": "proie",
    "proyes": "proies",
    "stile": "style",
    "stiles": "styles",
    "autrefais": "autrefois",
    "toutefais": "toutefois",
    "noye": "noie",
    "noyent": "noient",

    # Accents & circumflexes
    "plûpart": "plupart",
    "misericorde": "miséricorde",
    "misericordes": "miséricordes",
    "misericordieux": "miséricordieux",
    "siécle": "siècle",
    "siécles": "siècles",
    "déja": "déjà",
    "regne": "règne",
    "regnes": "règnes",
    "regner": "régner",
    "fléche": "flèche",
    "fléches": "flèches",
    "chûte": "chute",
    "chûtes": "chutes",
    "disgrace": "disgrâce",
    "disgraces": "disgrâces",
    "précede": "précède",
    "précedent": "précèdent",
    "succede": "succède",
    "succedent": "succèdent",

    # ü digraphs
    "orgüeil": "orgueil",
    "orgüils": "orgueils",
    "orgüilleux": "orgueilleux",
    "écüeil": "écueil",
    "écüeils": "écueils",
    "obéïssance": "obéissance",
    "obéïr": "obéir",
    "obéït": "obéit",
    "obéïrent": "obéirent",
    "obéïssent": "obéissent",
    "obéïssant": "obéissant",
    "louë": "loue",
    "louënt": "louent",
    "avouë": "avoue",
    "avouënt": "avouent",
    "dévouë": "dévoue",
    "dévouënt": "dévouent",

    # 5p. Archaic oi -> ai, -oître inflections, and archaic -oit / -oient verb endings
    # connoître / paroître family inflections and long-s variants
    "paroissez": "paraissez",
    "paroissoit": "paraissait",
    "paroissoient": "paraissaient",
    "connoissoient": "connaissaient",
    "reconnoissoient": "reconnaissaient",
    "apparoissoient": "apparaissaient",
    "disparoissoient": "disparaissaient",
    "paroissons": "paraissons",
    "paroissions": "paraissions",
    "disparoissions": "disparaissions",
    "apparoissions": "apparaissions",
    "paroissiez": "paraissiez",
    "paroitre": "paraître",
    "paroiffent": "paraissent",
    "paroißent": "paraissent",
    "disparoisse": "disparaisse",
    "disparoiffe": "disparaisse",
    "disparoitre": "disparaître",
    "apparoissait": "apparaissait",
    "apparoissaient": "apparaissaient",
    "comparoissaient": "comparaissaient",
    "connoiffance": "connaissance",
    "connoiffances": "connaissances",
    "connoiffent": "connaissent",
    "connoiffant": "connaissant",
    "connoisseurs": "connaisseurs",
    "connoissables": "connaissables",
    "reconnoissiez": "reconnaissiez",
    "reconnoissions": "reconnaissions",
    "reconnoiffance": "reconnaissance",
    "reconnoiffances": "reconnaissances",
    "reconnoiffait": "reconnaissait",
    "reconnoiffe": "reconnaisse",
    "reconnoissables": "reconnaissables",
    "méconnoissez": "méconnaissez",
    "méconnoîtront": "méconnaîtront",
    "reconnoi-tront": "reconnaîtront",

    # foible / affoiblir family
    "affoiblissent": "affaiblissent",
    "affoiblifsent": "affaiblissent",
    "affoiblira": "affaiblira",
    "affoiblirai": "affaiblirai",
    "affoibliffe": "affaiblisse",
    "affoiblissait": "affaiblissait",
    "affoibliraient": "affaibliraient",
    "assoiblis": "affaiblis",

    # roide / roidir family
    "roidissez": "raidissez",
    "roidir": "raidir",
    "roidi": "raidi",

    # monnoie
    "monnoie": "monnaie",
    "monnoies": "monnaies",

    # Françoise / Narbonnoise adjectives
    "françoise": "française",
    "françoises": "françaises",
    "narbonnoise": "narbonnaise",

    # Archaic verbs in -oit / -oient
    "duisoit": "duisait",
    "obsedoit": "obsédait",
    "laveroît": "laverait",
    "dérivoit": "dérivait",
    "dévivoit": "dérivait",
    "disoit": "disait",
    "lisoient": "lisaient",
    "liloit": "lisait",
    "blanchissoit": "blanchissait",
    "siffloient": "sifflaient",
    "assiégeoint": "assiégeaient",
    "prenoiens": "prenaient",
    "descendroiens": "descendraient",
    "étoiens": "étaient",
    "croistrons": "croîtront",
    "estoit": "était",
    "empêcheroitelle": "empêcherait-elle",
    "veloppoit": "enveloppait",

    # Miscellaneous archaic words
    "moïen": "moyen",
    "cicoigne": "cigogne",
    "refectoire": "réfectoire",
    "resectoire": "réfectoire",
    "dequoi": "de quoi",
    # Plural past participles / adjectives in -ez -> -és with 0 verb occurrences
    "passionnez": "passionnés",
    "ensanglantez": "ensanglantés",
    "entortillez": "entortillés",
    "abandonez": "abandonnés",
    "abbreuvez": "abreuvés",
    "abreuvez": "abreuvés",
    "abrogez": "abrogés",
    "abrégez": "abrégés",
    "accréditez": "accrédités",
    "accez": "accès",
    "acharnez": "acharnés",
    "addonnez": "adonnés",
    "adoptez": "adoptés",
    "affigez": "affligés",
    "aifez": "aisés",
    "ammoncelez": "amoncelés",
    "amorcez": "amorcés",
    "apprivoisez": "apprivoisés",
    "apprêtez": "apprêtés",
    "aquittez": "acquittés",
    "assigez": "assiégés",
    "assiégez": "assiégés",
    "avisez": "avisés",
    "blessez": "blessés",
    "caparaçonnez": "caparaçonnés",
    "cassez": "cassés",
    "choquez": "choqués",
    "citez": "cités",
    "collez": "collés",
    "comoditez": "commodités",
    "conditionnez": "conditionnés",
    "consternez": "consternés",
    "damnez": "damnés",
    "décharnez": "décharnés",
    "dégoûtez": "dégoûtés",
    "déjeunez": "déjeuners",
    "démêlez": "démêlés",
    "dénommez": "dénommés",
    "déposez": "déposés",
    "dérivez": "dérivés",
    "déréglez": "déréglés",
    "déséchez": "desséchés",
    "désignez": "désignés",
    "désinteressez": "désintéressés",
    "désolez": "désolés",
    "détrompez": "détrompés",
    "développez": "développés",
    "dévouez": "dévoués",
    "distinguez": "distingués",
    "effraïez": "effrayés",
    "efféminez": "efféminés",
    "enchaînez": "enchaînés",
    "enchaffez": "enchâssés",
    "enfermez": "enfermés",
    "enflamez": "enflammés",
    "enflâmez": "enflammés",
    "enfoncez": "enfoncés",
    "enlacez": "enlacés",
    "enragez": "enragés",
    "enslez": "enflés",
    "entassez": "entassés",
    "entez": "entés",
    "entrelacez": "entrelacés",
    "expolez": "exposés",
    "exprimez": "exprimés",
    "exterrninez": "exterminés",
    "exténuez": "exténués",
    "fabriquez": "fabriqués",
    "fiancez": "fiancés",
    "folemnitez": "solennités",
    "forgez": "forgés",
    "fouettez": "fouettés",
    "frapez": "frappés",
    "frisez": "frisés",
    "glacez": "glacés",
    "habillez": "habillés",
    "habituez": "habitués",
    "humectez": "humectés",
    "incensez": "insensés",
    "incommoddez": "incommodés",
    "indignez": "indignés",
    "intéressez": "intéressés",
    "liguez": "ligués",
    "maltratez": "maltraités",
    "marquetez": "marquetés",
    "mocquez": "moqués",
    "necessitez": "nécessités",
    "noïez": "noyés",
    "parsemez": "parsemés",
    "peignez": "peignés",
    "piquottez": "piquotés",
    "plombez": "plombés",
    "procez": "procès",
    "prophanez": "profanés",
    "préordonnez": "préordonnés",
    "prépolez": "préposés",
    "précédez": "précédés",
    "préjugez": "préjugés",
    "rongez": "rongés",
    "rouillez": "rouillés",
    "réfutez": "réfutés",
    "réprouvez": "réprouvés",
    "senversez": "renversés",
    "situez": "situés",
    "solemnisez": "solennisés",
    "sterilitez": "stérilités",
    "subjugez": "subjugués",
    "succcez": "succès",
    "suffoquez": "suffoqués",
    "surnommez": "surnommés",
    "tachetez": "tachetés",
    "transplantez": "transplantés",
    "échappez": "échappés",
}

def match_case(src, tgt):
    if src.isupper():
        return tgt.upper()
    if src[0].isupper():
        return tgt[0].upper() + tgt[1:]
    return tgt

keys = sorted(WORD_MAP.keys(), key=len, reverse=True)
pattern = re.compile(r"(?<![A-Za-zÀ-ÿ0-9])(" + "|".join(re.escape(k) for k in keys) + r")(?![A-Za-zÀ-ÿ0-9])", re.I)

SAINT_FOLLOWERS = (
    "Jérôme", "Jerôme", "Jérome", "Jeronyme", "Hieronym", "Hieronymi", "Ieronym", "Ieronymi",
    "Ieron", "Ierom", "Ierôme", "Hier", "Augustin", "Aug", "August", "Paul", "Ambroise",
    "Ambros", "Ambr", "Chrysostome", "Chrysost", "Hilaire", "Hilar", "Grégoire", "Cyprien",
    "Pierre", "Petri", "Matthieu", "Mathieu", "Matth", "Jean", "Jean-Baptiste", "Joannis",
    "Joan", "Ioan", "Germain", "Germ", "Germani", "German", "Thomas", "Thom", "Cyrille",
    "Cyrill", "Cyr", "Michel", "Athanase", "Athan", "Justin", "Jacques", "Clément", "Fulgence",
    "Épiphane", "Epiphane", "Luc", "Marc", "Bernard", "Raphaël", "Benoît", "Bened", "Basile",
    "Bafil", "Étienne", "Etienne", "Prosper", "Isidore", "Irénée", "Irenée", "Aubin", "Albini",
    "Timothée", "Éphrem", "Philippe", "Fiacre", "Antoine", "Hilarion", "Jude", "Martin",
    "Martini", "Léon", "Satyre", "Symeon", "Maxim", "Ignace", "Zabulon", "Dorotheus", "Saba",
    "Esprit", "Siège", "Prophète", "Abbé", "Cher", "Paule"
)

S_PATTERN = re.compile(
    r'(^|[\.\?!;:]|\n)?(\s*(?:[\"\'_«\(\*]|\^\{[^\}]+\}\s*)*)\bS\.\s+(' +
    '|'.join(re.escape(n) for n in sorted(SAINT_FOLLOWERS, key=len, reverse=True)) +
    r')\b'
)

# 1. Expand J. C. and variants to Jésus-Christ
RX_JC_FULL = re.compile(r"\b(Jesus-Christ|JESUS-CHRIST|JEsus-Christ|Jésus\s+Christ|JESUS\s+CHRIST)\b")
RX_JC_ABBR = re.compile(r"\bJ\s*\.?\s*-?\s*C(\.?)")

# 2. Move punctuation to the left of footnote calls (e.g. ^{(a)})
RX_FN_PUNCT = re.compile(r"(\S+)?(\s*)(\^\{\([a-zA-Z_0-9\*\+†]+\)\})(\s*)([,;:\.!\?]+)")
RX_FN_FOLLOW = re.compile(r"(\^\{\([a-zA-Z_0-9\*\+†]+\)\})(?=[A-Za-zÀ-ÿ«“])")

# 3. Ensure space after punctuation
RX_SPACE_COMMA = re.compile(r"(?<=[a-zA-ZÀ-ÿ0-9_\)»”]),(?=[A-Za-zÀ-ÿ«“])")
RX_SPACE_SEMI = re.compile(r"(?<=[a-zA-ZÀ-ÿ0-9_\)»”]);(?=[A-Za-zÀ-ÿ«“])")
RX_SPACE_COLON = re.compile(r"(?<=[a-zA-ZÀ-ÿ0-9_\)»”]):(?=[A-Za-zÀ-ÿ«“])")
RX_SPACE_EXCL_QUEST = re.compile(r"(?<=[a-zA-ZÀ-ÿ0-9_\)»”])([!\?])(?=[A-Za-zÀ-ÿ«“])")
RX_SPACE_PERIOD = re.compile(r"(?<=[a-zA-ZÀ-ÿ]{2})\.(?=[A-ZÀ-ÿ«“])")

# 4. Contextual OCR Long-S and Typographical Confusions
RX_FORTE_ADV1 = re.compile(r"\b([Ee]n|[Dd]e)\s+forte\s+(que\b|qu['\b])", re.I)
RX_FORTE_ADV2 = re.compile(r"\b([Ee]n|[Dd]e)\s+(quelque|cette|même|telle)\s+forte\b", re.I)
RX_FORTE_LA = re.compile(r"\b([Dd]e)\s+la\s+forte\b", re.I)
RX_FAIRE_EN_FORTE = re.compile(r"\b([Ff]aire|[Ff]ait|[Ff]aisant|[Ff]it|[Ff]irent)\s+en\s+forte\b", re.I)
RX_FORTE_DET = re.compile(r"\b([Cc]ette|[Uu]ne|[Aa]utre|[Tt]oute|[Nn]ouvelle)\s+forte\s+(de\b|d')", re.I)
RX_FORTES_DET = re.compile(r"\b([Cc]es|[Pp]lusieurs|[Tt]outes|[Dd]ifférentes|[Dd]iverses|[Nn]ouvelles|deux|trois|quatre|cinq|six|sept|huit|neuf|dix)\s+fortes\s+(de\b|d')", re.I)

RX_ON_FAIT_QUE = re.compile(r"(?<!-t')(?<!-t-)(?<!-)\b([Oo]n|l'on|L'on)\s+fait(\s+(?:que\b|qu'))")
RX_NE_FAIT_ON = re.compile(r"\b(Ne\s+)fait(-on\s+pas\s+(?:que\b|qu'))", re.I)
RX_QUI_FAIT_SI = re.compile(r"\b(Qui\s+)fait(\s+si\b)", re.I)
RX_NUL_NE_FAIT = re.compile(r"\b(Nul\s+ne\s+)fait(\s+(?:ce\s+qui|ce\s+que|si\b|que\b|qu'))", re.I)
RX_ON_NE_FAIT = re.compile(r"\b((?:[Oo]n|[Ii]l|[Ee]lle)\s+ne\s+)fait(\s+(?:que\s+trop|pas\s+précisément|point\b|ni\s+le\b|comment\b|quel\b|quelle\b|quels\b|quelles\b))")
RX_ON_FAIT_ADV = re.compile(r"(?<!-t')(?<!-t-)(?<!-)\b([Oo]n|l'on|L'on)\s+fait(\s+(?:d'ailleurs\b|certainement\b|indubitablement\b|pourtant\b|très\s+peu\b|par\s+l'Histoire\b|par\s+Joseph\b))")

# 4b. Contextual OCR Long-S in Future Verb Forms (ferai -> serai, feront -> seront, etc.)
RX_NE_VOUS_FERAI = re.compile(r"\b([Nn]e\s+vous\s+)ferai(-je\b)")
RX_JE_FERAI_AVEC = re.compile(r"(?<!que )(?<!qu'on )\b([Jj]e\s+)ferai(\s+avec\s+vous\b(?!(?:\s+[\w']+){0,3}?\s+(?:alliance|pacte)\b))")
RX_JE_FERAI_PRED = re.compile(r"\b([Jj]e\s+)ferai(\s+(?:dans\s+votre\s+bouche|leur\s+Dieu|votre\s+Dieu|bien\s+aise|agréable|fidèle|touché|assise|ta\s+mort|ta\s+ruine|comme\s+(?:un|une|la|le|l')\s*(?:panthère|lion|lionne|ours|ourse|teigne|pourriture|rosée|léopard)\b))")
RX_FERAI_PRINCE = re.compile(r"\b([Ff])erai(-je\s+votre\s+Prince\b)")
RX_JE_NE_FERAI = re.compile(r"\b([Jj]e\s+ne\s+)ferai(\s+plus\s+votre\s+Dieu\b)")
RX_FERONT_PRED = re.compile(r"\b([Ff])eront(\s+(?:circoncis|au\s+Seigneur|mon\s+peuple|savants|point\s+agréables|comme\s+la\b|rassemblés|enterrés|point\s+vaines|point\s+pleurés|restés|desséchés|dispersés|chassés|enveloppées|point\s+montés|toujours\s+aussi\s+chers|appelés|assis|comblés\b))")
RX_FEREZ_PRED = re.compile(r"\b([Ff])erez(\s+(?:point\s+obligé|mon\s+peuple|aplanie\b))")
RX_FERAIT_MORT = re.compile(r"\b([Ff])erait(\s+morte?\s+de\s+soif\b)")
RX_FERAIENT_AVEC = re.compile(r"\b(qui\s+)feraient(\s+avec\s+lui\b)")
RX_FUIS_TOMBEE = re.compile(r"\b(ce\s+que\s+je\s+)fuis(\s+tombée\b)")

RX_O_TARGETS = re.compile(r"\bO\s+(Dieu|Seigneur|Jésus|Christ|Sauveur|Père|Roi|Monarque|Créateur|Maître|Prince|Pontife|Pasteur|Soleil|Terre|Ciel|Cieux|Mort|Mortels|Hommes|Génération|Vierge|Marie|Patrie|Jérusalem|Sion|Béthel|Israélites|Israélite|Israël|Jacob|Juda|Éphraïm|Rome|Tyre|Babel|Babylone|Monsieur|Monseigneur|Chrétien|Chrétiens|Âme|mon\s+Dieu|mon\s+Seigneur|mon\s+âme|mon\s+cher|mon\s+frère|mon\s+fils|mon\s+peuple|ma\s+patrie|notre\s+Dieu|mes\s+frères|mes\s+enfants|vous\b|toi\b|homme\b|femme\b|prince\b|roi\b|peuple\b|pasteur\b|mort\b|mortel\b|mortels\b|malheureux\b|aveugle\b|insensé\b|insensés\b|race\b|si\b|combien\b|qu\'il\b|qu\'elle\b|qu\'ils\b|qu\'elles\b)", re.I)
RX_O_PUNCT = re.compile(r"\bO\s*([!\?])")

# 5. Obsolete Diaeresis (¨) Cleanup
PROTECTED_UE = {
    'aiguë', 'aiguës', 'ciguë', 'ciguës', 'contiguë', 'contiguës', 'ambiguë', 'ambiguës',
    'exiguë', 'exiguës', 'suraiguë', 'suraiguës',
    'manuë', 'suë', 'thécuë', 'elisuë', 'abisuë', 'bouterouë',
}
RX_UE = re.compile(r"\b([A-Za-zÀ-ÿ]+)uë(s?)\b")

EXACT_TREMA_MAP = {
    'enÿvrée': 'enivrée', 'paÿs': 'pays', 'martianaÿ': 'martianay',
    'tÿrin': 'tyrin', 'ieronÿm': 'ieronym',
    'nöces': 'noces', 'médäilles': 'médailles', 'bäton': 'bâton', 'bätons': 'bâtons',
    'considéröit': 'considérait', 'moäb': 'moab', 'canaän': 'canaan',
    'naäman': 'naaman', 'önkélos': 'onkélos',
    'désobéïssante': 'désobéissante', 'désobéïssantes': 'désobéissantes',
    'désobéïssance': 'désobéissance', 'désobéïssances': 'désobéissances', 'désobéïssances_': 'désobéissances_',
    'obéïssions': 'obéissions', 'obéïffez': 'obéissez',
    'boëte': 'boîte', 'boëtes': 'boîtes', 'emboëttaient': 'emboîtaient',
    'coëffure': 'coiffure', 'coëffures': 'coiffures', 'coëffe': 'coiffe', 'coëffes': 'coiffes',
    'moëlle': 'moelle', 'moëlles': 'moelles', 'moëlleux': 'moelleux', 'moëlleuse': 'moelleuse', 'moëlleuses': 'moelleuses',
    'recoëilli': 'recueilli',
    'moüelleuse': 'moelleuse', 'moüelleuses': 'moelleuses',
    'secoüaient': 'secouaient', 'secoüez': 'secouez', 'secoüons': 'secouons',
    'joüions': 'jouions', 'joüoient': 'jouaient',
    'foüillera': 'fouillera', 'foüetteront': 'fouetteront', 'foüettèrent': 'fouettèrent',
    'soüetté': 'fouetté', 'soüettez': 'fouettez', 'doüane': 'douane', 'broüillars': 'brouillards',
    'recüilli': 'recueilli', 'recüeiilir': 'recueillir', 'cüeuillette': 'cueillette',
    'orgüeisleux': 'orgueilleux', 'orgüeuilleuse': 'orgueilleuse', 'enorgüeilleront': 'enorgueilliront',
    'réüniffez': 'réunissez', 'réüffit': 'réussit', 'réüsfira': 'réussira',
    'réjoüissont': 'réjouissent', 'réjoüies': 'réjouies', 'éüeillex': 'éveillez',
    'dépoüilloit': 'dépouillait', 'poüilla': 'dépouilla', 'concliüera': 'conclura',
    'ponctüent': 'ponctuent', 'tüiez': 'tuiez', 'salüé': 'salué', 'salüssent': 'saluent',
    'infinüent': 'insinuent', 'remüement': 'remuement', 'remüa': 'remua',
    'prostitüait': 'prostituait', 'exténüera': 'exténuera',
    'baudoüin': 'baudouin', 'hardoüin': 'hardouin', 'hardüin': 'hardouin', 'chasteüil': 'chasteuil',
    'ouëst': 'ouest', 'eduëens': 'éduens', 'elymëens': 'élyméens', 'elyméëns': 'élyméens',
    'suëves': 'suèves', 'aëriens': 'aériens', 'ifraëlites': 'israëlites',
    'infinuë': 'insinue', 'insinuëra': 'insinuera', 'in-sinuë': 'in-sinue',
    'diminuëront': 'diminueront', 'perpetuë': 'perpétue', 'reftituë': 'restitue', 'fouvenuë': 'souvenue',
    'abbatuë': 'abattue', 'abbatuës': 'abattues', 'abbattuës': 'abattues', 'acruë': 'accrue',
    'charrouës': 'charrues', 'perluë': 'perdue', 'deffenduës': 'défendues', 'devennës': 'devenues',
    'prévûë': 'prévue', 'prévûës': 'prévues', 'pourvûës': 'pourvues',
    'résoluëment': 'résolument', 'cruëment': 'crûment', 'hochequeuë': 'hochequeue',
    'continuëraient': 'continueraient', 'avouëront': 'avoueront', 'excluëra': 'exclura',
    'concluëra': 'conclura', 'prostituëront': 'prostitueront', 'entretuërent': 'entretuèrent',
}

# 6. Obsolete & Broken Hyphens Normalization
EXACT_HYPHEN_MAP = {
    # 18th century compound adverbs / words -> single word
    "long-temps": "longtemps",
    "Long-temps": "Longtemps",
    "bien-tôt": "bientôt",
    "Bien-tôt": "Bientôt",
    "aussi-tôt": "aussitôt",
    "Aussi-tôt": "Aussitôt",
    "si-tôt": "sitôt",
    "Si-tôt": "Sitôt",
    "sur-tout": "surtout",
    "Sur-tout": "Surtout",
    "par-tout": "partout",
    "Par-tout": "Partout",
    "mal-aisé": "malaisé",
    "Mal-aisé": "Malaisé",
    "mal-aisée": "malaisée",
    "Mal-aisée": "Malaisée",
    "mal-aisés": "malaisés",
    "Mal-aisés": "Malaisés",
    "mal-aisées": "malaisées",
    "Mal-aisées": "Malaisées",
    "marche-pied": "marchepied",
    "Marche-pied": "Marchepied",
    "marche-pieds": "marchepieds",
    "Marche-pieds": "Marchepieds",
    "vrai-semblable": "vraisemblable",
    "Vrai-semblable": "Vraisemblable",
    "vrai-semblables": "vraisemblables",
    "Vrai-semblables": "Vraisemblables",
    "vrai-semblance": "vraisemblance",
    "Vrai-semblance": "Vraisemblance",
    "vrai-semblablement": "vraisemblablement",
    "Vrai-semblablement": "Vraisemblablement",
    "contre-temps": "contretemps",
    "Contre-temps": "Contretemps",
    "contre-sens": "contresens",
    "Contre-sens": "Contresens",
    "haut-bois": "hautbois",
    "Haut-bois": "Hautbois",
    "bien-faisant": "bienfaisant",
    "Bien-faisant": "Bienfaisant",
    "bien-faisante": "bienfaisante",
    "Bien-faisante": "Bienfaisante",
    "bien-faisants": "bienfaisants",
    "Bien-faisants": "Bienfaisants",
    "bien-faisantes": "bienfaisantes",
    "Bien-faisantes": "Bienfaisantes",
    "bien-heureux": "bienheureux",
    "Bien-heureux": "Bienheureux",
    "bien-heureuse": "bienheureuse",
    "Bien-heureuse": "Bienheureuse",
    "bien-heureuses": "bienheureuses",
    "Bien-heureuses": "Bienheureuses",
    "bien-séant": "bienséant",
    "Bien-séant": "Bienséant",
    "bien-séante": "bienséante",
    "Bien-séante": "Bienséante",
    "bien-séants": "bienséants",
    "Bien-séants": "Bienséants",
    "bien-séantes": "bienséantes",
    "Bien-séantes": "Bienséantes",
    "mal-habile": "malhabile",
    "Mal-habile": "Malhabile",
    "mal-habiles": "malhabiles",
    "Mal-habiles": "Malhabiles",
    "mal-propre": "malpropre",
    "Mal-propre": "Malpropre",
    "mal-propres": "malpropres",
    "Mal-propres": "Malpropres",
    "mal-propreté": "malpropreté",
    "Mal-propreté": "Malpropreté",
    "mal-faire": "malfaire",
    "Mal-faire": "Malfaire",
    "mal-avisé": "malavisé",
    "Mal-avisé": "Malavisé",
    "mal-avisée": "malavisée",
    "Mal-avisée": "Malavisée",
    "mal-avisés": "malavisés",
    "Mal-avisés": "Malavisés",
    "mal-heur": "malheur",
    "Mal-heur": "Malheur",
    "non-obstant": "nonobstant",
    "Non-obstant": "Nonobstant",
    "quelque-fois": "quelquefois",
    "Quelque-fois": "Quelquefois",
    "clair-voyant": "clairvoyant",
    "Clair-voyant": "Clairvoyant",
    "clair-voyante": "clairvoyante",
    "Clair-voyante": "Clairvoyante",
    "clair-voyants": "clairvoyants",
    "Clair-voyants": "Clairvoyants",

    # 18th century compound adverbs / phrases -> spaced words
    "même-temps": "même temps",
    "Même-temps": "Même temps",
    "aussi-bien": "aussi bien",
    "Aussi-bien": "Aussi bien",
    "non-seulement": "non seulement",
    "Non-seulement": "Non seulement",
    "non-feulement": "non seulement",
    "Non-feulement": "Non seulement",
    "dès-lors": "dès lors",
    "Dès-lors": "Dès lors",
    "dés-lors": "dès lors",
    "Dés-lors": "Dès lors",
    "bonne-heure": "bonne heure",
    "Bonne-heure": "Bonne heure",
    "bonne-chère": "bonne chère",
    "Bonne-chère": "Bonne chère",
    "peu-près": "peu près",
    "Peu-près": "Peu près",
    "mal-à-propos": "mal à propos",
    "Mal-à-propos": "Mal à propos",
    "tout-à-fait": "tout à fait",
    "Tout-à-fait": "Tout à fait",
    "petit-à-petit": "petit à petit",
    "Petit-à-petit": "Petit à petit",
    "bien-aise": "bien aise",
    "Bien-aise": "Bien aise",
    "bien-fait": "bien fait",
    "Bien-fait": "Bien fait",
    "bien-faits": "bien faits",
    "Bien-faits": "Bien faits",
    "au-long": "au long",
    "Au-long": "Au long",
    "au-travers": "au travers",
    "Au-travers": "Au travers",
    "à-cause": "à cause",
    "À-cause": "À cause",
    "au-de-là": "au-delà",
    "Au-de-là": "Au-delà",
    "en-bas": "en bas",
    "En-bas": "En bas",
    "d'en-bas": "d'en bas",
    "D'en-bas": "D'en bas",
    "en-haut": "en haut",
    "En-haut": "En haut",
    "d'en-haut": "d'en haut",
    "D'en-haut": "D'en haut",

    # OCR broken words mid-word line hyphenations
    "com-me": "comme",
    "di-sant": "disant",
    "afflic-tion": "affliction",
    "de-vant": "devant",
    "cui-vre": "cuivre",
    "in-constant": "inconstant",
    "in-constants": "inconstants",
    "in-constante": "inconstante",
    "in-constantes": "inconstantes",
    "recueil-lez": "recueillez",
    "englou-tit": "engloutit",
    "signi-fient": "signifient",
    "ce-la": "cela",
    "Ce-la": "Cela",
    "Ben-jamin": "Benjamin",
    "Jo-seph": "Joseph",
    "Crain-dre": "Craindre",
    "crain-dre": "craindre",
    "re-cherchaient": "recherchaient",
    "nom-mé": "nommé",
    "en-droit": "endroit",
    "triom-phé": "triomphé",
    "entre-voir": "entrevoir",
    "lâ-che": "lâche",
    "lâ-ches": "lâches",
    "res-semble": "ressemble",
    "res-semblance": "ressemblance",
    "Gar-dez": "Gardez",
    "gar-dez": "gardez",
    "sai-sons": "saisons",
    "sai-son": "saison",
    "Offi-ciers": "Officiers",
    "offi-ciers": "officiers",
    "ter-re": "terre",
    "ter-res": "terres",
    "el-le": "elle",
    "el-les": "elles",
    "e-lle": "elle",
    "e-lles": "elles",
    "menson-ges": "mensonges",
    "vi-sions": "visions",
    "voya-ges": "voyages",
    "dé-laissée": "délaissée",
    "re-connaître": "reconnaître",
    "abat-tement": "abattement",
    "éga-lât": "égalât",
    "de-çà": "deçà",
    "principale-ment": "principalement",
    "de-mander": "demander",
    "déchire-ra": "déchirera",
    "hiron-delle": "hirondelle",
    "accom-plira": "accomplira",
    "régulière-ment": "régulièrement",
    "Prê-tres": "Prêtres",
    "prê-tres": "prêtres",
    "quel-ques": "quelques",
    "ven-dre": "vendre",
    "pré-diction": "prédiction",
    "dé-sert": "désert",
    "pré-cisément": "précisément",
    "re-garde": "regarde",
    "pré-cédentes": "précédentes",
    "ex-pressément": "expressément",
    "Commenta-teurs": "Commentateurs",
    "commenta-teurs": "commentateurs",
    "ren-versement": "renversement",
    "ap-prenant": "apprenant",
    "riches-ses": "richesses",
    "obscu-rité": "obscurité",
    "dis-persées": "dispersées",
    "compa-rables": "comparables",
    "de-hors": "dehors",
    "demeure-rez": "demeurerez",
    "em-menée": "emmenée",
    "cein-te": "ceinte",
    "veu-lent": "veulent",
    "épouvante-ront": "épouvanteront",
    "bâti-ment": "bâtiment",
    "ex-cessivement": "excessivement",
    "pro-fondeur": "profondeur",
    "cherche-rait": "chercherait",
    "ré-pudiée": "répudiée",
    "dénomina-tion": "dénomination",
    "ef-frayée": "effrayée",
    "rejette-ra": "rejettera",
    "qui-conque": "quiconque",
    "pre-mier": "premier",
    "pre-miers": "premiers",
    "pre-mière": "première",
    "pre-mières": "premières",
    "car-nages": "carnages",
    "ti-ra": "tira",
    "sou-haitait": "souhaitait",
    "ap-parut": "apparut",
    "pro-pre": "propre",
    "pro-pres": "propres",
    "de-puis": "depuis",
    "au-tres": "autres",
    "cer-tain": "certain",
    "cer-tains": "certains",
    "cer-taine": "certaine",
    "cer-taines": "certaines",
    "in-fructueux": "infructueux",
    "in-fructueuse": "infructueuse",
    "in-fructueuses": "infructueuses",
    "originai-rement": "originairement",
    "in-sinue": "insinue",
    "ef-frayer": "effrayer",
    "cueil-lettes": "cueillettes",
    "quel-que": "quelque",
    "Pour-quoi": "Pourquoi",
    "pour-quoi": "pourquoi",
    "plu-sieurs": "plusieurs",
    "ancê-tre": "ancêtre",
    "ancê-tres": "ancêtres",
    "com-parent": "comparent",
    "Tradi-tion": "Tradition",
    "tradi-tion": "tradition",
    "morale-ment": "moralement",
    "cou-tume": "coutume",
    "cou-tumes": "coutumes",
    "pro-fanaient": "profanaient",
    "Sau-veur": "Sauveur",
    "sau-veur": "sauveur",
    "co-héritier": "cohéritier",
    "co-héritiers": "cohéritiers",
    "co-héritière": "cohéritière",
    "co-héritières": "cohéritières",
    "gran-de": "grande",
    "gran-des": "grandes",
    "don-ne": "donne",
    "rafraî-chir": "rafraîchir",
    "défail-lance": "défaillance",
    "Ro-mains": "Romains",
    "ro-mains": "romains",
    "per-mit": "permit",
    "vinai-gre": "vinaigre",
    "Biblio-thécaires": "Bibliothécaires",
    "biblio-thécaires": "bibliothécaires",
    "Baby-lonie": "Babylonie",
    "Is-raël": "Israël",
    "Jé-rusalem": "Jérusalem",
    "Jérusa-lem": "Jérusalem",
    "Zacha-rie": "Zacharie",
    "Za-charie": "Zacharie",
    "Na-zareth": "Nazareth",
    "Eusè-be": "Eusèbe",
    "Jérô-me": "Jérôme",
    "reste-s": "restes",
    "usur-pant": "usurpant",
    "a-lors": "alors",
    "a-vant": "avant",
    "a-près": "après",
    "Qui-dam": "Quidam",
    "qui-dam": "quidam",
    "les-ennemis": "les ennemis",
    "nous-prévienne": "nous prévienne",
    "la-grenade": "la grenade",
    "Jean-Bapriste": "Jean-Baptiste",
}

RX_HYPHEN_DELA = re.compile(r"(?<!\b[Aa]u-)(?<!\b[Pp]ar-)(?<!\b[Ee]n-)(?<!\b[Jj]usque-)\b([Dd])e-là\b")
RX_HYPHEN_AUTOUR = re.compile(r"\b([Aa])u-tour\b(?=\s+(?:de|du|des|d['’]))")
RX_HYPHEN_AUPRES = re.compile(r"\b([Aa])u-près\b(?=\s+(?:de|du|des|d['’]))")

_HYPHEN_ESCAPED = sorted(EXACT_HYPHEN_MAP.keys(), key=len, reverse=True)
RX_HYPHEN_EXACT = re.compile(r"(?<![\w\-])(" + "|".join(re.escape(k) for k in _HYPHEN_ESCAPED) + r")(?![\w\-])")

# 7. Obsolete & Incorrect Circumflex (^) Cleanup
EXACT_CIRC_MAP = {
    # Past participles in -û
    "lû": "lu",
    "bû": "bu",
    "tû": "tu",
    "eû": "eu",
    "foû": "fou",
    "soû": "fou",
    "fû": "su",
    "brû": "bru",
    "deçû": "déçu",
    "dépoûrû": "dépourvu",

    # Winged (ailés)
    "aîlez": "ailés",
    "aîlées": "ailées",
    "aîle": "aile",
    "aîles": "ailes",
    "aîlé": "ailé",
    "aîlée": "ailée",
    "aîlés": "ailés",

    # Asûre / assûre / affûre
    "asûre": "assure",
    "asûrent": "assurent",
    "asûrer": "assurer",
    "affûre": "assure",
    "affûré": "assuré",
    "affûrément": "assurément",
    "assûr": "assuré",
    "assûre": "assure",
    "assûrent": "assurent",
    "assûrera": "assurera",
    "assûreront": "assureront",
    "assûrait": "assurait",
    "assûraient": "assuraient",
    "assûrant": "assurant",

    # Flâme / Phantôme
    "flâme": "flamme",
    "flâmes": "flammes",
    "enflâme": "enflamme",
    "enflâmes": "enflammes",
    "phantôme": "fantôme",
    "phantômes": "fantômes",

    # Paîtrir / pétrir
    "paîtri": "pétri",
    "paîtris": "pétris",
    "pâtris": "pétris",
    "paîtrit": "pétrit",
    "paîtrir": "pétrir",
    "paîtrissent": "pétrissent",
    "paîtrirez": "pétrirez",
    "paîtrin": "pétrin",
    "repaîssez": "repaissez",

    # Archaic û words
    "piquûre": "piqûre",
    "piquûres": "piqûres",
    "meurtriffûres": "meurtrissures",
    "accoûtumance": "accoutumance",
    "accoûtumera": "accoutumera",
    "accoûtumerai": "accoutumerai",
    "plustôt": "plutôt",
    "dégoûtans": "dégoûtants",
    "foûtient": "soutient",
    "foûterraine": "souterraine",
    "soûlié": "soulier",
    "soûrire": "sourire",
    "sciûre": "sciure",
    "pâtiffier": "pâtissier",

    # Miscellaneous archaic circumflex words
    "nîtreuses": "nitreuses",
    "trême": "trame",
    "pêles": "pelles",
    "pître": "pitre",
    "rébêle": "rebelle",
    "rebêle": "rebelle",
    "aprêtées": "apprêtées",
    "trôn": "trône",
    "accraître": "accroître",
    "décraître": "décroître",
    "craîtrez": "croîtrez",
    "regîtres": "registres",
    "blaspêmes": "blasphèmes",
    "jarêts": "jarrets",
    "fâcherent": "fâchèrent",
    "dêtre": "d'être",
    "lâne": "l'âne",
    "aîne": "aine",
    "scellôit": "scellait",
    "confessoîs": "confessais",

    # Proper names with unnecessary circumflex
    "ierôme": "Jérôme",
    "iérôme": "Jérôme",
    "mathâthias": "Mathathias",
    "lasthêne": "Lasthène",
    "hérodiâs": "Hérodias",
    "eupolême": "Eupolème",
    "pamphîlie": "Pamphylie",
    "sennachêrib": "Sennachérib",

    # Verbs in -oître future / conditional
    "connoîtra": "connaîtra",
    "connoîtront": "connaîtront",
    "connoîtrai": "connaîtrai",
    "connoîtras": "connaîtras",
    "connoîtrait": "connaîtrait",
    "connoîtraient": "connaîtraient",
    "connoîtriez": "connaîtriez",
    "connoîtrions": "connaîtrions",
    "connoîtrons": "connaîtrons",
    "reconnoîtra": "reconnaîtra",
    "reconnoîtront": "reconnaîtront",
    "reconnoîtrai": "reconnaîtrai",
    "reconnoîtrons": "reconnaîtrons",
    "reconnoîtrait": "reconnaîtrait",
    "reconnoîtraient": "reconnaîtraient",
    "disparoît": "disparaît",
    "disparoîtra": "disparaîtra",
    "disparoîtront": "disparaîtront",
    "disparoîtrait": "disparaîtrait",
    "apparoît": "apparaît",
    "apparoîtra": "apparaîtra",
    "apparoîtront": "apparaîtront",
    "reparoît": "reparaît",
    "reparoîtra": "reparaîtra",
    "reparoîtront": "reparaîtront",
    "comparoîtront": "comparaîtront",
    "ellemême": "elle-même",
}

_CIRC_ESCAPED = sorted(EXACT_CIRC_MAP.keys(), key=len, reverse=True)
RX_CIRC_EXACT = re.compile(r"(?<![A-Za-zÀ-ÿ0-9])(" + "|".join(re.escape(k) for k in _CIRC_ESCAPED) + r")(?![A-Za-zÀ-ÿ0-9])", re.I)
RX_ME_NE = re.compile(r"\b([Mm])ê\s+ne\b")

# 7. Obsolete Y -> I / Î / AIE / OI Normalization
EXACT_Y_MAP = {
    # Abîme (y -> î)
    "abyme": "abîme",
    "abymes": "abîmes",
    "abysme": "abîme",
    "abysmes": "abîmes",
    # Enivrer / envier
    "envyrez": "enivrés",
    "envyre": "enivre",
    "envyvre": "enivre",
    "envyvrera": "enivrera",
    "enyvrait": "enivrait",
    "s'enyvrait": "s'enivrait",
    # Avoir (participle / subjunctive / auxiliary)
    "aye": "aie",
    "ay": "ai",
    # Ancestors (ayeul -> aïeul)
    "ayeul": "aïeul",
    "ayeuls": "aïeuls",
    "ayeule": "aïeule",
    "ayeules": "aïeules",
    "ayeux": "aïeux",
    "bisayeul": "bisaïeul",
    "bifayeul": "bisaïeul",
    # Asile
    "asyle": "asile",
    "asyles": "asiles",
    # Haie
    "haye": "haie",
    "hayes": "haies",
    # Nouns in -aye -> -aie
    "futaye": "futaie",
    "futayes": "futaies",
    "clayes": "claies",
    "brayes": "braies",
    "chênaye": "chênaie",
    "craye": "craie",
    "taye": "taie",
    "tayes": "taies",
    # Gaieté & gai
    "gayeté": "gaieté",
    "gayetés": "gaietés",
    "gayement": "gaiement",
    "gay": "gai",
    # Days & time
    "lundy": "lundi",
    "mardy": "mardi",
    "mercredy": "mercredi",
    "jeudy": "jeudi",
    "vendredy": "vendredi",
    "samedy": "samedi",
    "midy": "midi",
    # Cy
    "voicy": "voici",
    "celle-cy": "celle-ci",
    "gens-cy": "gens-ci",
    # Monosyllables
    "loy": "loi",
    "loys": "lois",
    "foy": "foi",
    "moy": "moi",
    # Common words with y -> i
    "hyrondelle": "hirondelle",
    "hyrondelles": "hirondelles",
    "éclypse": "éclipse",
    "éclypses": "éclipses",
    "tymbale": "timbale",
    "tymbales": "timbales",
    "cythare": "cithare",
    "cythares": "cithares",
    "crystal": "cristal",
    "chymérique": "chimérique",
    "acrostyche": "acrostiche",
    "phtysie": "phtisie",
    "hydeux": "hideux",
    "vrayment": "vraiment",
    "quoyque": "quoique",
    "aujourd'huy": "aujourd'hui",
    "doyvent": "doivent",
    "suye": "suie",
    "truyes": "truies",
    "enfuye": "enfuie",
    "buys": "buis",
    "luy": "lui",
    "courroyes": "courroies",
    "tygre": "tigre",
    "tygres": "tigres",
    "sphynx": "sphinx",
    # Future tense 1st person singular in -ray -> -rai
    "rendray": "rendrai",
    "répandray": "répandrai",
    "réduiray": "réduirai",
    "traiteray": "traiterai",
}

_Y_ESCAPED = sorted(EXACT_Y_MAP.keys(), key=len, reverse=True)
RX_Y_EXACT = re.compile(r"(?<![A-Za-zÀ-ÿ0-9_])(" + "|".join(re.escape(k) for k in _Y_ESCAPED) + r")(?!-[A-Za-zÀ-ÿ0-9_])\b", re.I)
RX_QU_IL_N_Y_AYE = re.compile(r"\b([Qq]u'il\s+n'y\s+)aye\b")
RX_N_ENVYEZ = re.compile(r"\b([Nn])'envyez\b")
RX_CY_APRES = re.compile(r"\b([Cc]y)[- ](après\b)")
RX_RUGISSEMENT_LYON = re.compile(r"\b([Rr]ugissement\s+du\s+)Lyon\b")
RX_NY_PAS = re.compile(r"\b([Nn])y\s+(tout\s+à\s+fait)\b")
RX_NY_A_T_IL = re.compile(r"\bNy\s+(a-t-il\b)")
RX_QU_AY = re.compile(r"\b([Qq]u)'ay(-je\b)")

# 5m. Missing Apostrophes and Elisions
EXACT_APOSTROPHE_MAP = {
    # Glued words without apostrophe
    "dautres": "d'autres",
    "quil": "qu'il",
    "quils": "qu'ils",
    "quon": "qu'on",
    "dun": "d'un",
    "dune": "d'une",
    "sentendre": "s'entendre",
    "lopposition": "l'opposition",
    "noffrirez": "n'offrirez",
    "lchangeait": "l'échangeait",

    # Missing apostrophe with space (pair elisions)
    "d orient": "d'Orient",
    "d airain": "d'airain",
    "d une": "d'une",
    "d un": "d'un",
    "d adam": "d'Adam",
    "d endroit": "d'endroit",
    "d elle": "d'elle",
    "d officier": "d'Officier",
    "d habits": "d'habits",
    "d autres": "d'autres",

    "l animal": "l'animal",
    "l évangile": "l'Évangile",
    "l homme": "l'homme",
    "l on": "l'on",
    "l entendre": "l'entendre",
    "l entendons": "l'entendons",
    "l absence": "l'absence",
    "l écriture": "l'Écriture",
    "l âme": "l'âme",
    "l équinoxe": "l'équinoxe",
    "l hébreu": "l'Hébreu",

    "qu il": "qu'il",
    "qu elle": "qu'elle",
    "qu est": "qu'est",

    "c étaient": "c'étaient",
    "c est": "c'est",

    "n y": "n'y",
    "n ait": "n'ait",
    "n en": "n'en",

    "s y": "s'y",

    "quelqu un": "quelqu'un",
    "quelqu une": "quelqu'une",

    "jusque au": "jusqu'au",
    "jusque aux": "jusqu'aux",

    "lorsque il": "lorsqu'il",
    "lorsque elle": "lorsqu'elle",
}

_APOS_ESCAPED = sorted(EXACT_APOSTROPHE_MAP.keys(), key=len, reverse=True)
RX_APOS_EXACT = re.compile(r"(?<![A-Za-zÀ-ÿ0-9_])(" + "|".join(re.escape(k) for k in _APOS_ESCAPED) + r")(?!-[A-Za-zÀ-ÿ0-9_])\b", re.I)

RX_L_A_MORDU = re.compile(r"\b([Ll])\s+a\s+(mordu\b)")
RX_L_HONNEUR = re.compile(r"\b([Ll])['’]\s+(honneur\b)")
RX_L_ABANDONNE = re.compile(r"\b([Ll])['’]\s*\n\s*(abandonné\b)")
RX_QUE_IL = re.compile(r"\b([Qq]u)e[\s\n]+(il\b)")
RX_LON_ELIDED = re.compile(r"\b(que|si|où|et|ou)\s+lon\b", re.I)
RX_QUON_NEN = re.compile(r"\b(qu'on)\s+nen\b", re.I)
RX_LORSQUE_LA_NUIT = re.compile(r"\blorsque\s+il\s+nuit\s+approche\b", re.I)
RX_IS_ONT_LU = re.compile(r"\bI's\s+ont\s+lu\b")
RX_SIS_ECOUTEZ = re.compile(r"\bsi's,\s*écoutez\b")
RX_LUI_N_EME = re.compile(r"\blui-n\.ême\b")
RX_Y_A_T_IL = re.compile(r"\bY\s+a-t\s+il\b")
RX_MAS_EMPORTE = re.compile(r"\bma's\s+emporté\b")
RX_S_AINT = re.compile(r"\b([Ss])\s+(aint\s+Matthieu\b)")
RX_S_OUVENT = re.compile(r"\b([Ss])\s+(ouvent\b)")
RX_S_E_PREND = re.compile(r"\b([Ss])\s+e\s+(prend\b)")
RX_CES_LA = re.compile(r"\bC'es\s+-\s*là\b")
RX_HISTOIRE = re.compile(r"\bl'His\s+toire\b")
RX_ROID_EGYPTE = re.compile(r"\bCe Roid'Égypte\b")

# 5n. Miscellaneous Archaic Spellings and Pattern Families
EXACT_MISC_ARCHAIC_MAP = {
    # 1. éthimologies -> étymologies
    "éthimologies": "étymologies",
    "éthimologie": "étymologie",

    # 2. monstrer family
    "monstrer": "montrer",
    "monstrèrent": "montrèrent",
    "monstrée": "montrée",
    "monstrées": "montrées",
    "monstrerait": "montrerait",
    "monstrera": "montrera",
    "monstreront": "montreront",
    "monstrez": "montrez",
    "monstrant": "montrant",

    # 3. croissans family (-ans / -ens plurals)
    "croissans": "croissants",
    "fréquens": "fréquents",
    "mécontens": "mécontents",
    "équivalens": "équivalents",
    "menaçans": "menaçants",
    "inconvéniens": "inconvénients",
    "permanens": "permanents",
    "fainéans": "fainéants",
    "turbulens": "turbulents",
    "glissans": "glissants",
    "coulans": "coulants",
    "indifférens": "indifférents",
    "apparens": "apparents",
    "commençans": "commençants",
    "contractans": "contractants",
    "étonnans": "étonnants",
    "suffocans": "suffocants",
    "défians": "défiants",
    "arpens": "arpents",
    "accens": "accents",
    "règlemens": "règlements",
    "entablemens": "entablements",
    "battemens": "battements",
    "relâchemens": "relâchements",
    "assoupissemens": "assoupissements",
    "abaissemens": "abaissements",
    "vomissemens": "vomissements",
    "vomiſsemens": "vomissements",
    "applaudissemens": "applaudissements",
    "applaudiffemens": "applaudissements",
    "puiffans": "puissants",
    "mésdisans": "médisants",
    "judaïzans": "judaïsants",
    "impénitens": "impénitents",
    "déficiens": "déficients",
    "palpitans": "palpitants",
    "quadrans": "quadrants",
    "ingrédiens": "ingrédients",
    "opulens": "opulents",
    "insinuans": "insinuants",
    "communians": "communiants",
    "fermans": "fermants",
    "volans": "volants",
    "clairvoyans": "clairvoyants",
    "concurrens": "concurrents",
    "tempéramens": "tempéraments",
    "truchemens": "truchements",
    "rassasiemens": "rassasiements",
    # Specific phrases for homographs that have Latin occurrences
    "vos agens": "vos agents",
    "les continens": "les continents",

    # 4. brasselets family (ss -> c)
    "brasselet": "bracelet",
    "brasselets": "bracelets",
    "sausse": "sauce",
    "sausses": "sauces",
    "nasselle": "nacelle",
    "nasselles": "nacelles",
    "entrelassé": "entrelacé",
    "entrelassée": "entrelacée",
    "entrelassés": "entrelacés",
    "entrelassées": "entrelacées",
    "entrelassent": "entrelacent",
    "entrelassez": "entrelacez",
    "enlassez": "enlacez",

    # 5. Genéfe OCR long-s
    "genéfe": "Genèse",

    # 7. bled family
    "bled": "blé",
    "bleds": "blés",

    # 8. gozier family (z -> s)
    "gozier": "gosier",
    "goziers": "gosiers",
    "magazin": "magasin",
    "magazins": "magasins",
    "cizeau": "ciseau",
    "cizeaux": "ciseaux",
    "cizelée": "ciselée",
    "cizelées": "ciselées",
    "cizelé": "ciselé",
    "cizelés": "ciselés",
    "hazard": "hasard",
    "hazards": "hasards",
    "hazarder": "hasarder",
    "hazardent": "hasardent",
    "hazardez": "hasardez",
    "hazardait": "hasardait",
    "hazardaient": "hasardaient",
    "hazardèrent": "hasardèrent",
    "hazarderait": "hasarderait",
    "hazarderaient": "hasarderaient",
    "hazarderont": "hasarderont",
    "hazardera": "hasardera",
    "hazardée": "hasardée",
    "hazardées": "hasardées",
    "hazardé": "hasardé",
    "hazardés": "hasardés",
    "hazardant": "hasardant",
    "nazeaux": "naseaux",
    "azile": "asile",
    "aziles": "asiles",
    "ozier": "osier",
    "oziers": "osiers",
    "bize": "bise",
    "sarrazin": "sarrasin",
    "sarrazins": "sarrasins",

    # 9. robbe family (consonant normalization)
    "robbe": "robe",
    "robbes": "robes",
    "abbattre": "abattre",
    "abbattu": "abattu",
    "abbattus": "abattus",
    "abbattue": "abattue",
    "abbattues": "abattues",
    "abbatu": "abattu",
    "abbatus": "abattus",
    "abbatue": "abattue",
    "abbatues": "abattues",
    "abbattement": "abattement",
    "abbattemens": "abattements",
    "abbatement": "abattement",
    "abbat": "abat",
    "abbattent": "abattent",
    "abbattront": "abattront",
    "abbatront": "abattront",
    "abbattra": "abattra",
    "abbattrai": "abattrai",
    "abbattit": "abattit",
    "abbatit": "abattit",
    "abbattant": "abattant",
    "abbattaient": "abattaient",
    "rabbaissaient": "rabaissaient",
    "abbaisser": "abaisser",
    "abbaissez": "abaissez",
    "abbaissent": "abaissent",
    "abbaissée": "abaissée",
    "abbaissés": "abaissés",
    "abbaissées": "abaissées",
    "abbaissement": "abaissement",
    "abbaissements": "abaissements",
    "embaras": "embarras",
    "embarasse": "embarrasse",
    "embarassent": "embarrassent",
    "embarassé": "embarrassé",
    "embarassée": "embarrassée",
    "embarassés": "embarrassés",
    "embarassées": "embarrassées",
    "embarasser": "embarrasser",
    "embarassaient": "embarrassaient",
    "embarassant": "embarrassant",
    "embarasseront": "embarrasseront",
    "débarasser": "débarrasser",
    "débarassent": "débarrassent",
    "débarassé": "débarrassé",
    "nouriture": "nourriture",
    "nouritures": "nourritures",
    "nourir": "nourrir",
    "nourissent": "nourrissent",
    "canelle": "cannelle",
    "canelles": "cannelles",
    "houpe": "houppe",
    "houpes": "houppes",
    "hupe": "huppe",
    "hupes": "huppes",
    "échaper": "échapper",
    "échapera": "échappera",
    "échapez": "échappez",
    "échapent": "échappent",
    "échapant": "échappant",
    "bastonade": "bastonnade",
    "bastonades": "bastonnades",
    "fanné": "fané",
    "fannée": "fanée",
    "fannés": "fanés",
    "fannées": "fanées",
    "fannera": "fanera",
    "floccons": "flocons",
    "floccon": "flocon",
    "agraffes": "agrafes",
    "agraffe": "agrafe",
    "applanir": "aplanir",
    "applanira": "aplanira",
    "applanissez": "aplanissez",
    "applanirai": "aplanirai",
    "applanirez": "aplanirez",
    "applanisse": "aplanisse",
    "applaniront": "aplaniront",
    "applanit": "aplanit",
    "applanissant": "aplanissant",
    "appaiser": "apaiser",
    "appaifer": "apaiser",
    "appaiserons": "apaiserons",
    "appaisions": "apaisions",
    "appaiserait": "apaiserait",
    "appaifa": "apaisa",
    "appaiferai": "apaiserai",
    "appaisé": "apaisé",
    "appaisée": "apaisée",
    "appaisés": "apaisés",
    "appaisées": "appaisées",
    "abboyeur": "aboyeur",
    "abbreuvera": "abreuvera",
    "abbréviateur": "abréviateur",
    "carrouge": "carouge",
}

_MISC_ARCHAIC_ESCAPED = sorted(EXACT_MISC_ARCHAIC_MAP.keys(), key=len, reverse=True)
RX_MISC_ARCHAIC = re.compile(r"(?<![A-Za-zÀ-ÿ0-9_])(" + "|".join(re.escape(k) for k in _MISC_ARCHAIC_ESCAPED) + r")(?!-[A-Za-zÀ-ÿ0-9_])\b", re.I)

# 6. Contextual par tout -> partout
RX_PAR_TOUT = re.compile(r"\b([Pp]ar)\s+tout\b")
RX_PAR_TOUT_KEEP = re.compile(r"^\s+(?:le\b|ce\b|cet\b|ceci\b|cela\b|son\s+[a-zA-ZÀ-ÿ]+|un\s+[a-zA-ZÀ-ÿ]+|l[\x27\x92\u2019]|Israël\b|homme\b)", re.I)
RX_PAR_TOUT_ADVERBIAL_EXCEPTIONS = re.compile(
    r"^\s+(?:l[\x27\x92\u2019](?:Évangile|effroi|ordre|harmonie)\b|"
    r"le\s+(?:ménage|désintéressement|feu)\b|"
    r"son\s+(?:injustice|horreur|attachement)\b|"
    r"un\s+(?:pain\s+entier|et\s+avant)\b)",
    re.I
)

# 6b. Possédez participle / noun -> Possédés / possédés
RX_POSSEDEZ_PARTICIPLE = re.compile(r"\b([Oo]u|[Ee]t)\s+possédez\s+par\b")
RX_POSSEDEZ_CAP = re.compile(r"\bPossédez\s+par\s+leur\s+affection\b")
RX_POSSEDEZ_NOUN = re.compile(r"(?<!vous )\b(vrais|les)\s+possédez\b", re.I)

# 7. Expansion of abbreviations: l'Heb. -> l'Hébreu, Chap. -> Chapitre
RX_LHEB = re.compile(
    r"\b([Ll][\x27\x92\u2019])([Hh][eé]br?)(?:\.eu|\s+u(?=\s*:)|(?:\.(?![a-zA-ZÀ-ÿ0-9])|\b(?![a-zA-ZÀ-ÿ0-9])))"
)
RX_TEXTE_HEB = re.compile(r"\b([Tt]exte)\s+([Hh][eé]br?)\.?(?=\s|$|[,\);:!?«»_\^])")
RX_PAREN_HEB = re.compile(r"\(([Hh][eé]br?)\.\s*")

RX_CHAP_PLURAL = re.compile(
    r"\b(les|ces|aux|des|deux|trois|quatre|cinq|six|sept|huit|neuf|dix|plusieurs)\s+(CHAP|Chap|chap)\.(?![a-zA-ZÀ-ÿ0-9])",
    re.IGNORECASE
)
RX_CHAP_PLURAL_ADJ = re.compile(
    r"\b(CHAP|Chap|chap)\.\s+(précédents|suivants)\b",
    re.IGNORECASE
)
RX_CH_NUM = re.compile(r"\b(Ch|ch)\.\s*([0-9IVXLCDMivxlcdm]+)")
RX_CH_WORD = re.compile(r"\b(Ch|ch)\.\s*(suivant|précédent|premier)", re.IGNORECASE)
RX_CHAP_NODOT = re.compile(r"\b(CHAP|Chap|chap)\s+([0-9IVXLCDMivxlcdm]+)")
RX_CHAP_GEN = re.compile(r"\b(CHAP|Chap|chap)\.(?![a-zA-ZÀ-ÿ0-9])")

LATIN_BROKEN_WORDS = {
    "AN-NORUM": "ANNORUM",
    "CECIDERIT-QUE": "CECIDERITQUE",
    "ANNO-RUM": "ANNORUM",
    "CIBA-RIA": "CIBARIA",
    "MONTE-LIBANO": "MONTE LIBANO",
    "BETHLE-HEM": "BETHLEHEM",
    "PLAUS-TRUM": "PLAUSTRUM",
    "EXCELSO-RUM": "EXCELSORUM",
    "AQUÆ-DUCTUM": "AQUÆDUCTUM",
    "AN-NULUM": "ANNULUM",
    "DI-NUMERAVERUNT": "DINUMERAVERUNT",
    "AUXILIUM-TUUM": "AUXILIUM TUUM",
    "LE-GEM": "LEGEM",
    "ANI-MA": "ANIMA",
    "PEC-CATORUM": "PECCATORUM",
    "IL-LIUS": "ILLIUS",
    "VISITA-TIO": "VISITATIO",
    "VISI-TATIO": "VISITATIO",
    "SUAVE-OLENTEM": "SUAVEOLENTEM",
    "VASTA-TORES": "VASTATORES",
    "AU-SITIDIS": "AUSITIDIS",
    "ULTO-RI": "ULTORI",
    "VOVE-RUNT": "VOVERUNT",
    "NE-QUE": "NEQUE",
    "DESER-TUROS": "DESERTUROS",
    "IMMUNDO-RUM": "IMMUNDORUM",
    "ADIMPLE-TUR": "ADIMPLETUR",
}

RX_LATIN_BROKEN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in LATIN_BROKEN_WORDS.keys()) + r")\b"
)


def clean_latin_quote(text):
    if not text:
        return text, 0
    count = 0

    def sub_broken(m):
        nonlocal count
        count += 1
        return LATIN_BROKEN_WORDS[m.group(1)]

    text = RX_LATIN_BROKEN.sub(sub_broken, text)

    if "SAVE - KARIATHAIM" in text:
        text = text.replace("SAVE - KARIATHAIM", "SAVE-KARIATHAIM")
        count += 1
    if "SCRIBAM PRINCIPEM MILITUM, - QUI" in text:
        text = text.replace("SCRIBAM PRINCIPEM MILITUM, - QUI", "SCRIBAM PRINCIPEM MILITUM, QUI")
        count += 1

    return text, count




def modernize_text(text):
    if not text:
        return text, 0
    
    count = 0

    # 1. Trailing apostrophe OCR artifacts (e.g., "moi'")
    def strip_ocr_apostrophe(m):
        nonlocal count
        count += 1
        return m.group(1)
    text = re.sub(r"\b(moi|toi|lui|soi)'", strip_ocr_apostrophe, text)

    # 2. Contextual participles (after auxiliaries)
    def participles_replacer(m):
        nonlocal count
        count += 1
        return m.group(1) + ' ' + (m.group(2) or '') + ('étonnés' if 'étonn' in m.group(3).lower() else 'troublés')
    text = re.sub(r'\b(sont|étaient|seront|furent|été|yeux)\s+(tout\s+)?(étonnez|troublez)\b', participles_replacer, text, flags=re.I)

    # 2b. Contextual participles (-ez -> -és vs 2nd person plural / imperative)
    def dechirez_replacer(m):
        nonlocal count
        count += 1
        return m.group(1) + match_case(m.group(2), "déchirés")
    text = re.sub(r'(\b(?:(?:habits|vêtements)(?:\s+\w+,?)?\s+et|habits|vêtements|blessés,?\s+et)\s+)(déchirez)\b', dechirez_replacer, text, flags=re.I)

    def abaissez_replacer(m):
        nonlocal count
        count += 1
        return m.group(1) + match_case(m.group(2), "abaissés")
    text = re.sub(r'(\b(?:fermés[_,\s]+ou|seront|feront|humiliés,?\s+et|être)\s+)(abaissez)\b', abaissez_replacer, text, flags=re.I)

    def avancez_replacer(m):
        nonlocal count
        count += 1
        return m.group(1) + match_case(m.group(2), "avancés")
    text = re.sub(r'(\b(?:aussi|fruits|beaucoup)\s+)(avancez)\b', avancez_replacer, text, flags=re.I)

    def appuyez_replacer(m):
        nonlocal count
        count += 1
        return m.group(1) + match_case(m.group(2), "appuyés")
    text = re.sub(r'(\b(?:adopté|hasard|conséquence)\b[,\s]+)(appuyez)\b', appuyez_replacer, text, flags=re.I)

    def sauvez_replacer(m):
        nonlocal count
        count += 1
        return m.group(1) + match_case(m.group(2), "sauvés")
    text = re.sub(r'(\b(?:serons|nombre\s+de|de)\s+)(sauvez)(\b(?!\s*-(?:moi|vous|nous|la)))', sauvez_replacer, text, flags=re.I)

    def elevez_replacer(m):
        nonlocal count
        count += 1
        return m.group(1) + match_case(m.group(2), "élevés")
    text = re.sub(r'(\b(?:grands,?\s+et|gazons,|sont|nourris,?\s+et|j\'ai|j\'avais|vent|plus)\s+)(élevez)\b', elevez_replacer, text, flags=re.I)

    def fondez_replacer(m):
        nonlocal count
        count += 1
        return match_case(m.group(0), "fondés")
    text = re.sub(r'\b(F|f)ondez\b(?!\s+votre\b)', fondez_replacer, text)

    def contextual_ez_sub(target, replacement):
        def _sub(m):
            nonlocal count
            count += 1
            return m.group(1) + match_case(m.group(2), replacement)
        return _sub

    # Auxiliary être & reflexive compound forms
    text = re.sub(r'(\b(?:étaient|étoient|sont|furent|fussent|seront|seraient|seroient|étant|été|s\'en\s+(?:étant|sont|étaient|étoient|furent))\s+)(allez)\b', contextual_ez_sub('allez', 'allés'), text, flags=re.I)
    text = re.sub(r'(\b(?:se\s+sont|s\'étaient|s\'étoient|s\'étant|s\'en\s+sont|s\'en\s+étaient|s\'en\s+étant|ont\s+été|avaient\s+été|sont|étaient|étoient)\s+(?:(?:point|pas|plus|tous|promptement)\s+)?)(retirez)\b', contextual_ez_sub('retirez', 'retirés'), text, flags=re.I)
    def eveillez_replacer(m):
        nonlocal count
        count += 1
        return m.group(1) + "éveillés"
    text = re.sub(r'(\b(?:se\s+sont)\s+)(éveilleZ)\b', eveillez_replacer, text)
    text = re.sub(r'(\b(?:seront|ferez|seraient|seroient)\s+(?:point\s+)?)(rassasiez)\b', contextual_ez_sub('rassasiez', 'rassasiés'), text, flags=re.I)
    text = re.sub(r'(\b(?:été|sont)\s+)(tirez)\b', contextual_ez_sub('tirez', 'tirés'), text, flags=re.I)
    text = re.sub(r'(\b(?:mille|hommes|soldats)\s+de\s+)(tuez)\b', contextual_ez_sub('tuez', 'tués'), text, flags=re.I)
    text = re.sub(r'(\b(?:seront)\s+)(considérez)\b', contextual_ez_sub('considérez', 'considérés'), text, flags=re.I)
    text = re.sub(r'(\b(?:étaient|seront)\s+)(éclairez)\b', contextual_ez_sub('éclairez', 'éclairés'), text, flags=re.I)
    text = re.sub(r'(\b(?:Aveugles|créancier|Simples)\s+)(éclairiez|éclairez)\b', contextual_ez_sub('éclairiez', 'éclairés'), text, flags=re.I)
    text = re.sub(r'(\b(?:s\'y\s+étaient)\s+)(réfugiez)\b', contextual_ez_sub('réfugiez', 'réfugiés'), text, flags=re.I)

    # Noun phrases & adjective modifiers
    def souliers_replacer(m):
        nonlocal count
        count += 1
        return m.group(1) + match_case(m.group(2), "souliers")
    text = re.sub(r'(\b[Ss]ans\s+)(souliez)\b', souliers_replacer, text)
    text = re.sub(r'(\b(?:gens|hommes)\s+)(armez)\b', contextual_ez_sub('armez', 'armés'), text, flags=re.I)
    text = re.sub(r'(\b(?:grains|impudiques)\s+)(mêlez)\b', contextual_ez_sub('mêlez', 'mêlés'), text, flags=re.I)
    text = re.sub(r'(\b(?:boucs)\s+)(engraissez)\b', contextual_ez_sub('engraissez', 'engraissés'), text, flags=re.I)
    text = re.sub(r'(\b(?:hommes)\s+)(percez)\b', contextual_ez_sub('percez', 'percés'), text, flags=re.I)
    text = re.sub(r'(\b(?:lieux)\s+)(arrosez)\b', contextual_ez_sub('arrosez', 'arrosés'), text, flags=re.I)
    text = re.sub(r'(\b(?:deux)\s+)(possédez)\b', contextual_ez_sub('possédez', 'possédés'), text, flags=re.I)
    text = re.sub(r'(\b(?:toujours)\s+)(prosternez)\b', contextual_ez_sub('prosternez', 'prosternés'), text, flags=re.I)
    text = re.sub(r'(\bsoyons\s+)(comblez)\b', contextual_ez_sub('comblez', 'comblés'), text, flags=re.I)
    text = re.sub(r'(\bsoyons\s+)(informez)\b', contextual_ez_sub('informez', 'informés'), text, flags=re.I)
    text = re.sub(r'(\btous\s+)(frappez)\b', contextual_ez_sub('frappez', 'frappés'), text, flags=re.I)
    text = re.sub(r'(\bsommes\s+)(détournez)\b', contextual_ez_sub('détournez', 'détournés'), text, flags=re.I)
    text = re.sub(r'(\bnous-mêmes\s+)(chassez)\b', contextual_ez_sub('chassez', 'chassés'), text, flags=re.I)
    text = re.sub(r'(\bnoirs,\s+et\s+)(défigurez)\b', contextual_ez_sub('défigurez', 'défigurés'), text, flags=re.I)
    text = re.sub(r'(\baguerris\s+et\s+)(exercez)\b', contextual_ez_sub('exercez', 'exercés'), text, flags=re.I)
    text = re.sub(r'(\bpeuples\s+)(éloignez)\b', contextual_ez_sub('éloignez', 'éloignés'), text, flags=re.I)
    text = re.sub(r'(\bpeuples\s+)(assemblez)\b', contextual_ez_sub('assemblez', 'assemblés'), text, flags=re.I)
    text = re.sub(r'(\btemps\s+)(ordonnez)\b', contextual_ez_sub('ordonnez', 'ordonnés'), text, flags=re.I)

    # Chapter summaries and editorial participles
    text = re.sub(r'(\bSonges de Pharaon\s+)(expliquez)\b', contextual_ez_sub('expliquez', 'expliqués'), text, flags=re.I)
    def chargez_replacer(m):
        nonlocal count
        count += 1
        return m.group(1) + match_case(m.group(2), "chargés") + m.group(3)
    text = re.sub(r'(\bretournent\s+)(chargez)(\s+de présents)\b', chargez_replacer, text, flags=re.I)
    text = re.sub(r'(\bCaptifs\s+)(assurez)\b', contextual_ez_sub('assurez', 'assurés'), text, flags=re.I)
    text = re.sub(r'(\bSages,?\s+)(opposez)\b', contextual_ez_sub('opposez', 'opposés'), text, flags=re.I)
    text = re.sub(r'(\bimpie,?\s+)(opposez)\b', contextual_ez_sub('opposez', 'opposés'), text, flags=re.I)
    text = re.sub(r'(\bcœurs\s+)(éprouvez)\b', contextual_ez_sub('éprouvez', 'éprouvés'), text, flags=re.I)
    def environnez_replacer(m):
        nonlocal count
        count += 1
        return m.group(1) + match_case(m.group(2), "environnés") + m.group(3)
    text = re.sub(r'(\bÉgyptiens\s+)(environnez)(\s+de ténèbres)\b', environnez_replacer, text, flags=re.I)
    text = re.sub(r'(\bancienne Loi\s+)(méprisez)\b', contextual_ez_sub('méprisez', 'méprisés'), text, flags=re.I)
    text = re.sub(r'(\bseront un jour\s+)(transportez)\b', contextual_ez_sub('transportez', 'transportés'), text, flags=re.I)
    text = re.sub(r'(\bIsraëlites\s+)(rappelez)\b', contextual_ez_sub('rappelez', 'rappelés'), text, flags=re.I)
    text = re.sub(r'(\bcaptifs d\'Israël\s+)(rappelez)\b', contextual_ez_sub('rappelez', 'rappelés'), text, flags=re.I)
    text = re.sub(r'(\bSacrifices\s+)(rejetez)\b', contextual_ez_sub('rejetez', 'rejetés'), text, flags=re.I)
    text = re.sub(r'(\bpécheurs\s+)(envoyez)\b', contextual_ez_sub('envoyez', 'envoyés'), text, flags=re.I)
    text = re.sub(r'(\bEnnemis\s+)(envoyez)\b', contextual_ez_sub('envoyez', 'envoyés'), text, flags=re.I)
    text = re.sub(r'(\bRogommélech\s+)(envoyez)\b', contextual_ez_sub('envoyez', 'envoyés'), text, flags=re.I)
    text = re.sub(r'(\bJuifs\s+)(restez)\b', contextual_ez_sub('restez', 'restés'), text, flags=re.I)
    text = re.sub(r'(\bJuifs\s+)(menez)\b', contextual_ez_sub('menez', 'menés'), text, flags=re.I)
    text = re.sub(r'(\bJuifs\s+)(retirez)\b', contextual_ez_sub('retirez', 'retirés'), text, flags=re.I)
    text = re.sub(r'(\bDieux\s+)(désolez)\b', contextual_ez_sub('désolez', 'désolés'), text, flags=re.I)
    def comblez_replacer(m):
        nonlocal count
        count += 1
        return match_case(m.group(1), "comblés") + m.group(2)
    text = re.sub(r'(\bcomblez)(\s+de gloire)\b', comblez_replacer, text, flags=re.I)
    def representez_replacer(m):
        nonlocal count
        count += 1
        return match_case(m.group(1), "représentés") + m.group(2)
    text = re.sub(r'(\breprésentez)(\s+sous l\'idée)\b', representez_replacer, text, flags=re.I)
    text = re.sub(r'(\bLévites\s+)(souillez)\b', contextual_ez_sub('souillez', 'souillés'), text, flags=re.I)
    text = re.sub(r'(\bDaniel\s+)(accusez)\b', contextual_ez_sub('accusez', 'accusés'), text, flags=re.I)
    text = re.sub(r'(\bRoi\s+)(livrez)\b', contextual_ez_sub('livrez', 'livrés'), text, flags=re.I)
    text = re.sub(r'(\bChâtiments\s+)(exercez)\b', contextual_ez_sub('exercez', 'exercés'), text, flags=re.I)
    text = re.sub(r'(\bSages\s+)(aveuglez)\b', contextual_ez_sub('aveuglez', 'aveuglés'), text, flags=re.I)
    text = re.sub(r'(\bEnfants\s+)(présentez)\b', contextual_ez_sub('présentez', 'présentés'), text, flags=re.I)
    def recompensez_replacer(m):
        nonlocal count
        count += 1
        return match_case(m.group(1), "récompensés") + m.group(2)
    text = re.sub(r'(\brécompensez)(\s+également)\b', recompensez_replacer, text, flags=re.I)

    # 3. Contextual noun "péchés" (when preceded by determiners)
    def pechez_replacer(m):
        nonlocal count
        count += 1
        return m.group(1) + ' ' + match_case(m.group(2), 'péchés')
    text = re.sub(r'\b(les|des|mes|tes|ses|nos|vos|leurs|ces|aux|plusieurs|tous)\s+(p[ée]chez)\b', pechez_replacer, text, flags=re.I)

    # 4. Jusques elisions & normalization
    def jusque_elide(m):
        nonlocal count
        count += 1
        lead = m.group(1)
        vowel_part = m.group(2)
        prefix = "Jusqu'" if lead[0].isupper() else "jusqu'"
        return prefix + vowel_part
    text = re.sub(r"\b(jusques?)\s+([àaâäeéèêëiîïoôuûüüy][a-zà-ÿ]*)\b", jusque_elide, text, flags=re.I)

    def jusque_hyphen(m):
        nonlocal count
        lead = m.group(1)
        prefix = "Jusque-là" if lead[0].isupper() else "jusque-là"
        if prefix != m.group(0):
            count += 1
        return prefix
    text = re.sub(r'\b(jusques?)\s*-\s*là\b', jusque_hyphen, text, flags=re.I)

    def standalone_jusques(m):
        nonlocal count
        count += 1
        return match_case(m.group(0), 'jusque')
    text = re.sub(r'\bjusques\b', standalone_jusques, text, flags=re.I)

    # 5. Adjective vôtre/nôtre vs pronoun le/la/les vôtre/nôtre
    def votre_notre_replacer(m):
        nonlocal count
        prefix = m.group(1) or ""
        word = m.group(2)
        prev = prefix.lower().strip()
        if prev in ("le", "la", "les", "du", "des", "au", "aux"):
            return m.group(0)  # keep pronoun with circumflex
        count += 1
        base = "votre" if "v" in word.lower() else "notre"
        return prefix + match_case(word, base)
    text = re.sub(r'(\b\w+\s+)?\b([VvNn]ôtre)\b', votre_notre_replacer, text)

    # 5b. très-X hyphen modernization (keep "Très-Haut" for God's title)
    def tres_replacer(m):
        nonlocal count
        lead = m.group(1)
        word = m.group(2)
        if word.lower() == "haut" and lead == "Très":
            if word != "Haut":
                count += 1
            return "Très-Haut"
        count += 1
        return lead + " " + word
    text = re.sub(r'\b(très|Très)-([A-Za-zÀ-ÿ]+)\b', tres_replacer, text)

    # 5c. Expand "S." / "Ste" to "Saint" / "saint" / "sainte" before saint names / titles
    def s_replacer(m):
        nonlocal count
        lead = m.group(1)
        sep = m.group(2)
        name = m.group(3)
        count += 1
        is_start = m.start() == 0 or (lead is not None and lead != "")
        prefix = (lead or "") + sep
        if name in ("Esprit", "Siège", "Cher"):
            return prefix + f"Saint-{name}"
        sw = "Saint" if is_start else "saint"
        return prefix + f"{sw} {name}"
    text = S_PATTERN.sub(s_replacer, text)

    def ste_replacer(m):
        nonlocal count
        count += 1
        lead = m.group(1)
        sep = m.group(2)
        sw = "Sainte" if (m.start() == 0 or (lead is not None and lead != "")) else "sainte"
        return (lead or "") + sep + sw + " Paule"
    text = re.sub(r'(^|[\.\?!;:]|\n)?(\s*(?:[\"\'_«\(\*]|\^\{[^\}]+\}\s*)*)\bSte\.?\s+Paule\b', ste_replacer, text)

    # 5d. Capitalize "saint" -> "Saint" at start of field/sentence or after a semicolon/colon
    def saint_replacer(m):
        nonlocal count
        count += 1
        return m.group(1) + m.group(2) + "Saint"
    text = re.sub(r'(^|[\.\?!;:]|\n)(\s*(?:[\"\'_«\(\*]|\^\{[^\}]+\}\s*)*)\bsaint\b', saint_replacer, text)

    # 5e. Expand J. C. and variants to Jésus-Christ
    def jc_full_sub(m):
        nonlocal count
        count += 1
        return "Jésus-Christ"
    text = RX_JC_FULL.sub(jc_full_sub, text)

    def jc_abbr_sub(m):
        nonlocal count
        count += 1
        dot = m.group(1)
        rest = m.string[m.end():]
        if dot:
            if re.match(r'^\s*$', rest) or re.match(r'^\s*\^\{[^\}]+\}\s*([A-ZÀ-ÿ«“]|$)', rest) or re.match(r'^\s+[A-ZÀ-ÿ«“]', rest):
                return "Jésus-Christ."
        return "Jésus-Christ"
    text = RX_JC_ABBR.sub(jc_abbr_sub, text)

    # 5f. Move punctuation to the left of footnote calls (e.g. ^{(a)})
    def fn_move_sub(m):
        nonlocal count
        lead = m.group(1) or ""
        call = m.group(3)
        punct = m.group(5)

        p = punct[0]
        stripped = lead.rstrip("_*\"'»)]")
        last_char = stripped[-1] if stripped else ""

        if last_char == p:
            new_lead = lead
        elif last_char == "." and p == ".":
            new_lead = lead
        elif last_char in (":", ";", "?", "!") and p in (".", ","):
            new_lead = lead
        elif last_char == "." and p in (",", ";", ":", "?", "!"):
            if p == ",":
                new_lead = lead + ","
            else:
                new_lead = lead + " " + p
        else:
            if p in (",", "."):
                new_lead = lead + p
            else:
                new_lead = lead + " " + p

        count += 1
        rest_idx = m.end()
        rest = m.string[rest_idx:]
        sep_after = " " if (rest and not rest.startswith((" ", "\n", "\r", "\t", ")", "»", "”"))) else ""
        return new_lead + " " + call + sep_after

    text = RX_FN_PUNCT.sub(fn_move_sub, text)

    def fn_follow_sub(m):
        nonlocal count
        count += 1
        return m.group(1) + " "
    text = RX_FN_FOLLOW.sub(fn_follow_sub, text)

    # 5g. Ensure space after punctuation
    text, n = RX_SPACE_COMMA.subn(", ", text); count += n
    text, n = RX_SPACE_SEMI.subn("; ", text); count += n
    text, n = RX_SPACE_COLON.subn(": ", text); count += n
    text, n = RX_SPACE_EXCL_QUEST.subn(r"\1 ", text); count += n
    text, n = RX_SPACE_PERIOD.subn(". ", text); count += n

    # 5h. Contextual OCR Long-S and Typographical Confusions
    # 5h.1 çç -> ç, contextual disait & conçoit
    if "diççait" in text:
        text, n = re.subn(r"\bdiççait\b", "disait", text); count += n
    if "conççait" in text:
        text, n = re.subn(r"\bconççait\b", "conçoit", text); count += n
    if "conçait" in text:
        text, n = re.subn(r"\bconçait\b", "conçoit", text); count += n
    if "çç" in text:
        text, n = re.subn(r"çç", "ç", text); count += n

    # 5h.2 forte(s) -> sorte(s)
    def sub_forte1(m):
        nonlocal count; count += 1
        return m.group(1) + " " + ("sorte" if "forte" in m.group(0) else "Sorte") + " " + m.group(2)
    text = RX_FORTE_ADV1.sub(sub_forte1, text)

    def sub_forte2(m):
        nonlocal count; count += 1
        return m.group(1) + " " + m.group(2) + " " + ("sorte" if "forte" in m.group(0) else "Sorte")
    text = RX_FORTE_ADV2.sub(sub_forte2, text)

    def sub_forte_la(m):
        nonlocal count; count += 1
        return m.group(1) + " la " + ("sorte" if "forte" in m.group(0) else "Sorte")
    text = RX_FORTE_LA.sub(sub_forte_la, text)

    def sub_faire_forte(m):
        nonlocal count; count += 1
        return m.group(1) + " en " + ("sorte" if "forte" in m.group(0) else "Sorte")
    text = RX_FAIRE_EN_FORTE.sub(sub_faire_forte, text)

    def sub_forte_det(m):
        nonlocal count; count += 1
        sep = " " if m.group(2) == "de" else ""
        return m.group(1) + " " + ("sorte" if "forte" in m.group(0) else "Sorte") + " " + m.group(2)
    text = RX_FORTE_DET.sub(sub_forte_det, text)

    def sub_fortes_det(m):
        nonlocal count; count += 1
        sep = " " if m.group(2) == "de" else ""
        return m.group(1) + " " + ("sortes" if "fortes" in m.group(0) else "Sortes") + " " + m.group(2)
    text = RX_FORTES_DET.sub(sub_fortes_det, text)

    # 5h.3 fait -> sait
    def sub_fait_que(m):
        nonlocal count; count += 1
        return m.group(1) + " " + ("sait" if m.group(0).split()[1] == "fait" else "Sait") + m.group(2)
    text = RX_ON_FAIT_QUE.sub(sub_fait_que, text)

    def sub_ne_fait_on(m):
        nonlocal count; count += 1
        return m.group(1) + "sait" + m.group(2)
    text = RX_NE_FAIT_ON.sub(sub_ne_fait_on, text)

    def sub_qui_fait_si(m):
        nonlocal count; count += 1
        return m.group(1) + "sait" + m.group(2)
    text = RX_QUI_FAIT_SI.sub(sub_qui_fait_si, text)

    def sub_nul_ne_fait(m):
        nonlocal count; count += 1
        return m.group(1) + "sait" + m.group(2)
    text = RX_NUL_NE_FAIT.sub(sub_nul_ne_fait, text)

    def sub_on_ne_fait(m):
        if "cuisine" in m.string[m.end():m.end() + 20]:
            return m.group(0)
        nonlocal count; count += 1
        return m.group(1) + "sait" + m.group(2)
    text = RX_ON_NE_FAIT.sub(sub_on_ne_fait, text)

    def sub_on_fait_adv(m):
        nonlocal count; count += 1
        return m.group(1) + " " + ("sait" if m.group(0).split()[1] == "fait" else "Sait") + m.group(2)
    text = RX_ON_FAIT_ADV.sub(sub_on_fait_adv, text)

    # 5h.3b ferai/feront/ferez/ferait -> serai/seront/serez/serait/suis
    def sub_ne_vous_ferai(m):
        nonlocal count; count += 1
        return m.group(1) + "serai" + m.group(2)
    text = RX_NE_VOUS_FERAI.sub(sub_ne_vous_ferai, text)

    def sub_je_ferai_avec(m):
        nonlocal count; count += 1
        return m.group(1) + "serai" + m.group(2)
    text = RX_JE_FERAI_AVEC.sub(sub_je_ferai_avec, text)

    def sub_je_ferai_pred(m):
        nonlocal count; count += 1
        return m.group(1) + "serai" + m.group(2)
    text = RX_JE_FERAI_PRED.sub(sub_je_ferai_pred, text)

    def sub_ferai_prince(m):
        nonlocal count; count += 1
        return ("S" if m.group(1) == "F" else "s") + "erai" + m.group(2)
    text = RX_FERAI_PRINCE.sub(sub_ferai_prince, text)

    def sub_je_ne_ferai(m):
        nonlocal count; count += 1
        return m.group(1) + "serai" + m.group(2)
    text = RX_JE_NE_FERAI.sub(sub_je_ne_ferai, text)

    def sub_feront_pred(m):
        nonlocal count; count += 1
        return ("S" if m.group(1) == "F" else "s") + "eront" + m.group(2)
    text = RX_FERONT_PRED.sub(sub_feront_pred, text)

    def sub_ferez_pred(m):
        nonlocal count; count += 1
        return ("S" if m.group(1) == "F" else "s") + "erez" + m.group(2)
    text = RX_FEREZ_PRED.sub(sub_ferez_pred, text)

    def sub_ferait_mort(m):
        nonlocal count; count += 1
        return ("S" if m.group(1) == "F" else "s") + "erait" + m.group(2)
    text = RX_FERAIT_MORT.sub(sub_ferait_mort, text)

    def sub_feraient_avec(m):
        nonlocal count; count += 1
        return m.group(1) + "seraient" + m.group(2)
    text = RX_FERAIENT_AVEC.sub(sub_feraient_avec, text)

    def sub_fuis_tombee(m):
        nonlocal count; count += 1
        return m.group(1) + "suis" + m.group(2)
    text = RX_FUIS_TOMBEE.sub(sub_fuis_tombee, text)

    # 5h.4 Vocative O -> Ô
    def sub_o_vocative(m):
        nonlocal count; count += 1
        return "Ô " + m.group(1)
    text = RX_O_TARGETS.sub(sub_o_vocative, text)

    def sub_o_punct(m):
        nonlocal count; count += 1
        return "Ô " + m.group(1)
    text = RX_O_PUNCT.sub(sub_o_punct, text)

    # 5i. Obsolete Diaeresis (¨) Cleanup
    if "Nathanäel" in text:
        text, n = re.subn(r"\bNathanäel\b", "Nathanaël", text); count += n

    def sub_trema_exact(m):
        nonlocal count
        w = m.group(0)
        lw = w.lower()
        if lw in EXACT_TREMA_MAP:
            count += 1
            return match_case(w, EXACT_TREMA_MAP[lw])
        return w

    # Apply exact map when any diaeresis exists
    if any(c in text for c in 'ëËïÏüÜÿŸäÄöÖ'):
        text = re.sub(r'\b[A-Za-zÀ-ÿ0-9_\'\-]+\b', sub_trema_exact, text)

    # General -uë / -uës normalization
    def sub_ue(m):
        nonlocal count
        full = m.group(0)
        stem = m.group(1)
        plural = m.group(2)
        if full.lower() in PROTECTED_UE:
            return full
        count += 1
        return stem + "ue" + plural
    text = RX_UE.sub(sub_ue, text)

    # 5j. Obsolete & Broken Hyphens Normalization
    if "-" in text:
        def sub_hyphen(m):
            nonlocal count
            count += 1
            return EXACT_HYPHEN_MAP[m.group(1)]
        text = RX_HYPHEN_EXACT.sub(sub_hyphen, text)

        def sub_dela(m):
            nonlocal count
            count += 1
            return m.group(1) + "e là"
        text = RX_HYPHEN_DELA.sub(sub_dela, text)

        def sub_autour(m):
            nonlocal count
            count += 1
            return m.group(1) + "utour"
        text = RX_HYPHEN_AUTOUR.sub(sub_autour, text)

        def sub_aupres(m):
            nonlocal count
            count += 1
            return m.group(1) + "uprès"
        text = RX_HYPHEN_AUPRES.sub(sub_aupres, text)

    # 5k. Obsolete Circumflex (^) Cleanup
    if any(c in text for c in 'âêîôûÂÊÎÔÛ'):
        def sub_circ(m):
            nonlocal count
            w = m.group(1)
            lw = w.lower()
            if lw in EXACT_CIRC_MAP:
                tgt = match_case(w, EXACT_CIRC_MAP[lw])
                if tgt != w:
                    count += 1
                    return tgt
            return w
        text = RX_CIRC_EXACT.sub(sub_circ, text)

        def sub_mene(m):
            nonlocal count
            count += 1
            return ("Même" if m.group(1) == "M" else "même")
        text = RX_ME_NE.sub(sub_mene, text)

    # 5l. Obsolete Y -> I / Î / AIE / OI Normalization
    if "y" in text or "Y" in text:
        def sub_qu_il_aye(m):
            nonlocal count; count += 1
            return m.group(1) + "ait"
        text = RX_QU_IL_N_Y_AYE.sub(sub_qu_il_aye, text)

        def sub_n_envyez(m):
            nonlocal count; count += 1
            return m.group(1) + "'enviez"
        text = RX_N_ENVYEZ.sub(sub_n_envyez, text)

        def sub_cy_apres(m):
            nonlocal count; count += 1
            return ("Ci-après" if m.group(1) == "Cy" else "ci-après")
        text = RX_CY_APRES.sub(sub_cy_apres, text)

        def sub_rugissement_lyon(m):
            nonlocal count; count += 1
            return m.group(1) + "lion"
        text = RX_RUGISSEMENT_LYON.sub(sub_rugissement_lyon, text)

        def sub_ny_pas(m):
            nonlocal count; count += 1
            return ("Ni" if m.group(1) == "N" else "ni") + " " + m.group(2)
        text = RX_NY_PAS.sub(sub_ny_pas, text)

        def sub_ny_a_t_il(m):
            nonlocal count; count += 1
            return "N'y " + m.group(1)
        text = RX_NY_A_T_IL.sub(sub_ny_a_t_il, text)

        def sub_qu_ay(m):
            nonlocal count; count += 1
            return m.group(1) + "'ai" + m.group(2)
        text = RX_QU_AY.sub(sub_qu_ay, text)

        def sub_y_exact(m):
            nonlocal count
            w = m.group(1)
            lw = w.lower()
            if lw in EXACT_Y_MAP:
                tgt = match_case(w, EXACT_Y_MAP[lw])
                if tgt != w:
                    count += 1
                    return tgt
            return w
        text = RX_Y_EXACT.sub(sub_y_exact, text)

    # 5m. Missing Apostrophe & Elision Cleanup
    def sub_lorsque_la_nuit(m):
        nonlocal count; count += 1
        return "lorsque la nuit approche"
    text = RX_LORSQUE_LA_NUIT.sub(sub_lorsque_la_nuit, text)

    def sub_apos_exact(m):
        nonlocal count
        w = m.group(1)
        lw = w.lower()
        if lw in EXACT_APOSTROPHE_MAP:
            tgt = match_case(w, EXACT_APOSTROPHE_MAP[lw])
            if tgt != w:
                count += 1
                return tgt
        return w
    text = RX_APOS_EXACT.sub(sub_apos_exact, text)

    def sub_l_a_mordu(m):
        nonlocal count; count += 1
        return m.group(1) + "'a " + m.group(2)
    text = RX_L_A_MORDU.sub(sub_l_a_mordu, text)

    def sub_l_honneur(m):
        nonlocal count; count += 1
        return m.group(1) + "'honneur"
    text = RX_L_HONNEUR.sub(sub_l_honneur, text)

    def sub_l_abandonne(m):
        nonlocal count; count += 1
        return m.group(1) + "'abandonné"
    text = RX_L_ABANDONNE.sub(sub_l_abandonne, text)

    def sub_que_il(m):
        nonlocal count; count += 1
        return m.group(1) + "'il"
    text = RX_QUE_IL.sub(sub_que_il, text)

    def sub_lon_elided(m):
        nonlocal count; count += 1
        return m.group(1) + " l'on"
    text = RX_LON_ELIDED.sub(sub_lon_elided, text)

    def sub_quon_nen(m):
        nonlocal count; count += 1
        return m.group(1) + " n'en"
    text = RX_QUON_NEN.sub(sub_quon_nen, text)

    def sub_is_ont_lu(m):
        nonlocal count; count += 1
        return "Ils ont lu"
    text = RX_IS_ONT_LU.sub(sub_is_ont_lu, text)

    def sub_sis_ecoutez(m):
        nonlocal count; count += 1
        return "fils, écoutez"
    text = RX_SIS_ECOUTEZ.sub(sub_sis_ecoutez, text)

    def sub_lui_n_eme(m):
        nonlocal count; count += 1
        return "lui-même"
    text = RX_LUI_N_EME.sub(sub_lui_n_eme, text)

    def sub_y_a_t_il(m):
        nonlocal count; count += 1
        return "Y a-t-il"
    text = RX_Y_A_T_IL.sub(sub_y_a_t_il, text)

    def sub_mas_emporte(m):
        nonlocal count; count += 1
        return "mais emporté"
    text = RX_MAS_EMPORTE.sub(sub_mas_emporte, text)

    def sub_s_aint(m):
        nonlocal count; count += 1
        return m.group(1) + "aint Matthieu"
    text = RX_S_AINT.sub(sub_s_aint, text)

    def sub_s_ouvent(m):
        nonlocal count; count += 1
        return m.group(1) + "ouvent"
    text = RX_S_OUVENT.sub(sub_s_ouvent, text)

    def sub_s_e_prend(m):
        nonlocal count; count += 1
        return m.group(1) + "e prend"
    text = RX_S_E_PREND.sub(sub_s_e_prend, text)

    def sub_ces_la(m):
        nonlocal count; count += 1
        return "C'est-là"
    text = RX_CES_LA.sub(sub_ces_la, text)

    def sub_histoire(m):
        nonlocal count; count += 1
        return "l'Histoire"
    text = RX_HISTOIRE.sub(sub_histoire, text)

    def sub_roid_egypte(m):
        nonlocal count; count += 1
        return "Ce Roi d'Égypte"
    text = RX_ROID_EGYPTE.sub(sub_roid_egypte, text)

    # 5n. Miscellaneous Archaic Spellings and Pattern Families
    def sub_par_tout(m):
        nonlocal count
        after = text[m.end():]
        if RX_PAR_TOUT_KEEP.match(after) and not RX_PAR_TOUT_ADVERBIAL_EXCEPTIONS.match(after):
            return m.group(0)
        count += 1
        src = m.group(1)
        return "Partout" if src[0].isupper() else "partout"
    text = RX_PAR_TOUT.sub(sub_par_tout, text)

    def sub_possedez_part(m):
        nonlocal count; count += 1
        return f"{m.group(1)} possédés par"
    text = RX_POSSEDEZ_PARTICIPLE.sub(sub_possedez_part, text)

    def sub_possedez_cap(m):
        nonlocal count; count += 1
        return "Possédés par leur affection"
    text = RX_POSSEDEZ_CAP.sub(sub_possedez_cap, text)

    def sub_possedez_noun(m):
        nonlocal count; count += 1
        return f"{m.group(1)} possédés"
    text = RX_POSSEDEZ_NOUN.sub(sub_possedez_noun, text)

    def sub_misc_archaic(m):
        nonlocal count
        w = m.group(1)
        lw = w.lower()
        if lw in EXACT_MISC_ARCHAIC_MAP:
            tgt = match_case(w, EXACT_MISC_ARCHAIC_MAP[lw])
            if tgt != w:
                count += 1
                return tgt
        return w
    text = RX_MISC_ARCHAIC.sub(sub_misc_archaic, text)

    # 5o. Expansion of abbreviations: l'Heb. -> l'Hébreu, Chap. -> Chapitre
    def sub_lheb(m):
        nonlocal count
        count += 1
        lead = m.group(1)
        return "L\x27Hébreu" if lead[0] == "L" else "l\x27Hébreu"
    text = RX_LHEB.sub(sub_lheb, text)

    def sub_texte_heb(m):
        nonlocal count
        count += 1
        t = m.group(1)
        h = m.group(2)
        hw = "Hébreu" if (h[0].isupper() or t[0].isupper()) else "hébreu"
        return f"{t} {hw}"
    text = RX_TEXTE_HEB.sub(sub_texte_heb, text)

    def sub_paren_heb(m):
        nonlocal count
        count += 1
        return "(Hébreu "
    text = RX_PAREN_HEB.sub(sub_paren_heb, text)

    def sub_chap_plural(m):
        nonlocal count
        count += 1
        det = m.group(1)
        w = m.group(2)
        cw = "CHAPITRES" if w.isupper() else ("Chapitres" if w[0].isupper() else "chapitres")
        return f"{det} {cw}"
    text = RX_CHAP_PLURAL.sub(sub_chap_plural, text)

    def sub_chap_plural_adj(m):
        nonlocal count
        count += 1
        w = m.group(1)
        adj = m.group(2)
        cw = "CHAPITRES" if w.isupper() else ("Chapitres" if w[0].isupper() else "chapitres")
        return f"{cw} {adj}"
    text = RX_CHAP_PLURAL_ADJ.sub(sub_chap_plural_adj, text)

    def sub_ch_num(m):
        nonlocal count
        count += 1
        cw = "Chapitre" if m.group(1)[0].isupper() else "chapitre"
        return f"{cw} {m.group(2)}"
    text = RX_CH_NUM.sub(sub_ch_num, text)

    def sub_ch_word(m):
        nonlocal count
        count += 1
        cw = "Chapitre" if m.group(1)[0].isupper() else "chapitre"
        return f"{cw} {m.group(2)}"
    text = RX_CH_WORD.sub(sub_ch_word, text)

    def sub_chap_nodot(m):
        nonlocal count
        count += 1
        w = m.group(1)
        cw = "CHAPITRE" if w.isupper() else ("Chapitre" if w[0].isupper() else "chapitre")
        return f"{cw} {m.group(2)}"
    text = RX_CHAP_NODOT.sub(sub_chap_nodot, text)

    def sub_chap_gen(m):
        nonlocal count
        count += 1
        w = m.group(1)
        cw = "CHAPITRE" if w.isupper() else ("Chapitre" if w[0].isupper() else "chapitre")
        rest = m.string[m.end():]
        if re.match(r"^\s*$", rest):
            return cw + "."
        if re.match(r"^\s*(?:[0-9IVXLCDMivxlcdm]+|premier|premiers|deux|trois|quatre|cinq|six|sept|huit|neuf|dix|onze|douze|treize|quatorze|quinze|seize|suiv|précéd|dernier)", rest, re.IGNORECASE):
            return cw
        if re.match(r"^\s*\^\{[^\}]+\}", rest):
            return cw
        if re.match(r"^\s*([A-ZÀ-ÿ«“]|$)", rest):
            return cw + "."
        return cw
    text = RX_CHAP_GEN.sub(sub_chap_gen, text)

    # 5b. Hyphen normalization (broken words & OCR erroneous hyphens)
    def sub_grand_pontife(m):
        nonlocal count
        count += 1
        return f"{m.group(1)}rand-{m.group(2)}ontife"

    def sub_grand_pretre(m):
        nonlocal count
        count += 1
        return f"{m.group(1)}rand-{m.group(2)}rêtre"

    def french_hyphen_sub(repl):
        def _sub(m):
            nonlocal count
            count += 1
            if callable(repl):
                return repl(m)
            return repl
        return _sub

    text = re.sub(r"\bau-jourd'hui\b", french_hyphen_sub(lambda m: "aujourd'hui" if m.group(0)[0].islower() else "Aujourd'hui"), text, flags=re.I)
    text = re.sub(r"\bHéré-mie\b", french_hyphen_sub("Jérémie"), text)
    text = re.sub(r"\bC'est-pourquoi\b", french_hyphen_sub("C'est pourquoi"), text)
    text = re.sub(r"\bc'est-pourquoi\b", french_hyphen_sub("c'est pourquoi"), text)
    text = re.sub(r"\bAbel-maison-de-Maacha\b", french_hyphen_sub("Abel-maison de Maacha"), text)
    text = re.sub(r"\bDu-fondement\b", french_hyphen_sub("Du fondement"), text)
    text = re.sub(r"\bassez-cruel\b", french_hyphen_sub("assez cruel"), text)
    text = re.sub(r"\bdonnez-point\b", french_hyphen_sub("donnez point"), text)
    text = re.sub(r"\bdes-hommes\b", french_hyphen_sub("des hommes"), text)
    text = re.sub(r"\best-dans\b", french_hyphen_sub("est dans"), text)
    text = re.sub(r"\bla-clef\b", french_hyphen_sub("la clef"), text)
    text = re.sub(r"\bmesura-tout\b", french_hyphen_sub("mesura tout"), text)
    text = re.sub(r"\bfaux-Prophètes\b", french_hyphen_sub("faux Prophètes"), text)
    text = re.sub(r"\bfaux-prophètes\b", french_hyphen_sub("faux prophètes"), text)
    text = re.sub(r"\bgrand-Champ\b", french_hyphen_sub("grand Champ"), text)
    text = re.sub(r"\bpoint-là\b", french_hyphen_sub("point là"), text)
    text = re.sub(r"\bc'est-à\s+dire\b", french_hyphen_sub("c'est-à-dire"), text)
    text = re.sub(r"\bC'est-à\s+dire\b", french_hyphen_sub("C'est-à-dire"), text)
    text = re.sub(r"\b(G|g)rand\s+-\s+(P|p)ontife\b", sub_grand_pontife, text)
    text = re.sub(r"\b(G|g)rand\s+-\s+(P|p)rêtre\b", sub_grand_pretre, text)
    text = re.sub(r"\bLaissez\s+-\s+les\b", french_hyphen_sub("Laissez-les"), text)

    # 6. Global WORD_MAP matching
    def replacer(match):
        nonlocal count
        word = match.group(0)
        lower = word.lower()
        if lower in WORD_MAP:
            tgt = match_case(word, WORD_MAP[lower])
            if tgt != word:
                count += 1
                return tgt
        return word

    text = pattern.sub(replacer, text)
    return text, count

def modernize_page(data):
    """Modernize one page in place; returns (changed, replacements).

    clean_mechanical.clean_page runs first: its spelling rules repair the words (long s, accents,
    charuë, abregez) that the context rules below expect, and in the other order those rules miss
    them. On the corpus the two never undo each other."""
    changed = clean_mechanical.clean_page(data)
    total = 0

    def update(container, key, fn):
        nonlocal changed, total
        if container.get(key) and isinstance(container[key], str):
            orig = container[key]
            mod, c = fn(orig)
            if mod != orig:
                container[key] = mod
                changed = True
                total += c

    def printed(lead=False):
        # Latin in italics and the halves of words broken at a page turn are left as printed
        def run(text):
            n = 0

            def rules(t):
                nonlocal n
                t, n = modernize_text(t)
                return t
            out = clean_mechanical.keep_printed(rules, text, lead=lead)
            return out, (n if out != text else 0)
        return run

    for key in ("chapter_title", "chapter_summary", "chapter_intro", "chapter_argument",
                "book_end_marker"):
        update(data, key, printed())
    for i, verse in enumerate(data.get("verses") or []):
        update(verse, "french", printed(lead=i == 0))
    for i, comm in enumerate(data.get("commentary") or []):
        update(comm, "latin_quote", clean_latin_quote)
        update(comm, "french_translation", printed(lead=i == 0))
        update(comm, "french_commentary", printed(lead=i == 0))
    for fn in data.get("footnotes") or []:
        update(fn, "text", printed())
        update(fn, "footnote_text", printed())
    return changed, total


def _page(args):
    """(changed, replacements, error) for one page file, written unless dry_run."""
    path, dry_run = args
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
            data = data[0]
        changed, n = modernize_page(data)
        if changed and not dry_run:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        return changed, n, None
    except Exception as e:
        return False, 0, f"{type(e).__name__}: {e}"


def process_volume(folder_name, dry_run, executor=None):
    folder = DATA / folder_name / "normalized"
    if not folder.is_dir():
        print(f"Directory not found: {folder}")
        return 0, 0

    files = [(str(p), dry_run) for p in sorted(folder.glob("page_[0-9][0-9][0-9][0-9].json"))]
    results = list(executor.map(_page, files, chunksize=8) if executor else map(_page, files))
    for (path, _), (_, _, err) in zip(files, results):
        if err:
            print(f"  ERROR {Path(path).relative_to(DATA)}: {err}", file=sys.stderr)
    total_replacements = sum(n for _, n, _ in results)
    pages_updated = sum(1 for changed, _, _ in results if changed)

    mode = "Dry-run: would make" if dry_run else "Applied"
    print(f"{mode} {total_replacements} in-place modernizations across {pages_updated} pages in {folder_name}.",
          flush=True)
    return total_replacements, pages_updated

def main():
    if len(sys.argv) < 2:
        print("Usage: python modernize_inplace.py <book_folder | all> [--dry-run]")
        sys.exit(1)

    dry_run = "--dry-run" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--dry-run"]

    if "all" in args:
        volumes = sorted([d.name for d in DATA.iterdir() if (d / "normalized").is_dir()])
    else:
        volumes = args

    grand_replacements = 0
    grand_pages = 0
    with ProcessPoolExecutor() as executor:
        for vol in volumes:
            r, p = process_volume(vol, dry_run, executor)
            grand_replacements += r
            grand_pages += p

    mode = "Dry-run total" if dry_run else "Total applied"
    print(f"\n{mode}: {grand_replacements} replacements across {grand_pages} pages in {len(volumes)} volumes.")

if __name__ == "__main__":
    main()
