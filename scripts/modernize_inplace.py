import json
import re
from pathlib import Path
from collections import Counter
import sys

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
    text = re.sub(r"\b(jusques?)\s+([àaâeéèêiîoôuûy]|aujourd'hui|au-delà|alors|où)\b", jusque_elide, text, flags=re.I)

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

def process_volume(folder_name, dry_run):
    folder = DATA / folder_name / "normalized"
    if not folder.is_dir():
        print(f"Directory not found: {folder}")
        return 0, 0

    total_replacements = 0
    pages_updated = 0

    for file_path in sorted(folder.glob("page_[0-9][0-9][0-9][0-9].json")):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
            data = data[0]

        changed = False

        def update_field(container, key):
            nonlocal changed, total_replacements
            if container.get(key) and isinstance(container[key], str):
                orig = container[key]
                mod, c = modernize_text(orig)
                if mod != orig:
                    container[key] = mod
                    changed = True
                    total_replacements += c

        update_field(data, "chapter_summary")
        update_field(data, "chapter_intro")
        update_field(data, "chapter_argument")

        for verse in data.get("verses") or []:
            update_field(verse, "french")

        for comm in data.get("commentary") or []:
            update_field(comm, "french_translation")
            update_field(comm, "french_commentary")

        for fn in data.get("footnotes") or []:
            update_field(fn, "text")
            update_field(fn, "footnote_text")

        if changed:
            pages_updated += 1
            if not dry_run:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

    mode = "Dry-run: would make" if dry_run else "Applied"
    print(f"{mode} {total_replacements} in-place modernizations across {pages_updated} pages in {folder_name}.")
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
    for vol in volumes:
        r, p = process_volume(vol, dry_run)
        grand_replacements += r
        grand_pages += p

    mode = "Dry-run total" if dry_run else "Total applied"
    print(f"\n{mode}: {grand_replacements} replacements across {grand_pages} pages in {len(volumes)} volumes.")

if __name__ == "__main__":
    main()
