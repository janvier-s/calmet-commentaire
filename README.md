# Calmet, *Commentaire littéral*

Une transcription modernisée du *Commentaire littéral sur tous les livres de l'Ancien et du Nouveau
Testament* de dom Augustin Calmet (1707-1716) : le texte latin et français de chaque verset, le
commentaire de Calmet et ses notes, page par page, vérifiés sur les scans et sur la Vulgate. Elle
alimente le site [dom-calmet-web](https://github.com/janvier-s/dom-calmet-web).

Tout le contenu est versé dans le domaine public ([CC0 1.0](LICENSE)) : chacun peut en faire ce
qu'il veut, sans autorisation ni mention.

## Ce que contient le dépôt

| | |
|---|---|
| `data/<volume>/normalized/page_NNNN.json` | **le texte** : un fichier par page imprimée (versets, commentaire, notes) |
| `data/<volume>/review.json` | la relecture du livre : points résolus, passés ou faux positifs, et les choses à faire relevées page par page |
| `docs/review_queue.json` | la file de relecture : chaque endroit où une vérification a trouvé quelque chose à revoir |
| `docs/*_check.json`, `docs/footnotes/` | les rapports dont la file est tirée |
| `scripts/` | la chaîne de traitement, les vérifications et l'éditeur de relecture ([scripts/README.md](scripts/README.md), en anglais) |
| `scripts/vulgate/` | la Vulgate clémentine, à laquelle les vérifications comparent le texte |
| `scripts/footnote_names.txt` | les œuvres et les auteurs cités dans les notes, avec leur titre original |

Ne sont pas dans le dépôt : les scans (`data/<volume>/source_images/`), l'OCR brut
(`data/<volume>/raw_json/`) et le cache des modèles (`scripts/cache/`). Les réponses déjà payées sont
jointes aux [publications](https://github.com/janvier-s/calmet-commentaire/releases) : décompressez
l'archive dans `scripts/cache/` (`tar xzf calmet-model-cache.tar.gz -C scripts/cache`) et les
scripts les réutilisent au lieu de redemander.

## Pour commencer

Il faut Python 3.12 ou plus et [uv](https://docs.astral.sh/uv/) (pour les tests et quelques outils).

```sh
git clone https://github.com/janvier-s/calmet-commentaire
cd calmet-commentaire/scripts
python3 review_web.py 01_genese 120      # l'éditeur de relecture, dans votre navigateur
uv run --no-project --with pytest --with pillow python -m pytest tests -q
```

L'éditeur fonctionne sans les scans (il affiche « No scan for this page ») ; demandez les scans du
volume sur lequel vous travaillez. Certaines vérifications demandent davantage :

- l'hébreu et le grec des notes : la Bible hébraïque (Open Scriptures, `scripts/cache/refs/hebrew_oshb.json`)
  et la Septante (getbible, `scripts/cache/refs/lxx/`) ;
- le correcteur orthographique : hunspell (`brew install hunspell`) et un dictionnaire français dans `~/Library/Spelling/fr_FR` ;
- le développement des abréviations des notes et les autres passes par modèle : [Claude Code](https://claude.com/claude-code) (`claude`) ou agy ;
- l'export vers le site : `dom-calmet-web` cloné à côté de ce dépôt (ou `CALMET_WEB=<son src/lib/data>`).

## Participer

1. Choisissez un livre parmi les [tickets « livre »](https://github.com/janvier-s/calmet-commentaire/issues?q=is%3Aissue+is%3Aopen+label%3Alivre)
   et dites-le en commentaire, pour que deux personnes ne travaillent pas sur les mêmes pages.
2. Créez une branche, ouvrez l'éditeur sur ce livre et parcourez sa file : comparez le texte au scan,
   corrigez-le, marquez chaque point résolu ou faux positif.
3. Validez (commit) les pages modifiées avec le `review.json` du livre, puis ouvrez une
   demande de fusion (pull request).

Les conventions — ce qu'on modernise et ce qu'on garde tel que Calmet l'a écrit — sont dans
[scripts/README.md](scripts/README.md) et [scripts/NEXT_VOLUMES.md](scripts/NEXT_VOLUMES.md). En
bref : orthographe française moderne, formes modernes des noms (Maccabées, Israélites, Samuel), mais
le latin de Calmet tel qu'il l'a imprimé (cœli, terrâ, cùm), et le latin cité dans les champs
français n'est jamais « corrigé » comme du français. Les abréviations des notes sont développées
selon `scripts/footnote_glossary.txt`.
