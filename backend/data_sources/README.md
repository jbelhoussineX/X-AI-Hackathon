# Collecte officielle intégrée à Pipelex

Code repris de la contribution `feat/pipelex-comparison`, commit `f5d79fc`,
avec adaptation au parcours local existant. Aucun compte Pipelex hébergé requis.

## Utilisation

Le mode réel de Streamlit utilise par défaut `POLITICAL_DATA_SOURCE=official`.
Aucune clé n'est nécessaire pour les exports publics ; `OPENAI_API_KEY` reste
nécessaire pour les deux appels de modèle (évaluation des manques et rédaction).
Une collecte vide ne déclenche aucun appel de modèle. Aucun appel web OpenAI
n'est fait dans ce mode, même en cas d'indisponibilité d'un inventaire.

Commencer avec `logement`, `transport` ou `énergie`. La correspondance est lexicale,
pas sémantique : tous les mots significatifs doivent figurer dans le titre ou les
thèmes. Un LLM peut décider d'un complément avec un autre mot-clé, au plus une fois.

Le collecteur peut aussi être utilisé sans IA, depuis l'environnement Python :

```bash
python -m backend.data_sources.official --topic logement --start 2017-06-21 --end 2026-09-27 --output data/local/collecte-logement.json
```

Cette commande télécharge des données publiques. Utiliser un nom de sortie neuf.
`data/local/` est ignoré par Git. Il ne s'agit pas d'une base SQLite synchronisée :
les exports sont téléchargés à la demande et le corpus est construit en mémoire.

## Catalogue depuis le début de la 15e législature

Pour conserver toutes les notices reconnues dans les inventaires, sans mot-clé,
sans limite de résultats et sans appel IA :

```bash
conda activate xia-hackathon
python -m backend.data_sources.catalogue --output data/local/catalogue-depuis-15e.json
```

La 15e législature est incluse dans son ensemble. La période par défaut va du **21 juin 2017 à aujourd'hui**. Les options
`--start` et `--end` permettent de la fixer. Utiliser un nouveau nom de fichier
à chaque actualisation. Le fichier conserve les dates, liens, identifiants,
provenances et empreintes des exports ; il reste local et n'est pas poussé sur Git.
Il ne contient pas tous les textes intégraux et n'est pas utilisé comme cache par
Streamlit : chaque recherche consulte à nouveau les exports officiels.

Le catalogue retient une notice si son dépôt, sa publication ou sa promulgation
connue est dans la période ; `period_matched_on` précise la ou les dates retenues.
Un dossier déposé avant 2020 mais promulgué en 2020 peut ainsi être inclus côté
Sénat. Les notices sans date sont comptées et exclues. Les versions et les deux
chambres sont conservées séparément : **une notice n'est pas une loi distincte**.

Une archive indisponible produit un catalogue `partial` et un code de sortie 1,
avec les autres sources disponibles conservées. `ok` signifie que les exports
configurés ont été téléchargés et reconnus, pas que toutes les lois françaises
sont représentées. Aucun accès Légifrance ni certification de droit en vigueur.
Il n'y a pas de synchronisation quotidienne.

## Sources et limites

- Assemblée : archives JSON publiques des **15e, 16e et 17e législatures**.
  La recherche choisit les archives selon la période, avec recouvrement des
  années de transition 2022 et 2024 ; le catalogue les lit toutes.
  Limites de taille réseau et de décompression, sans extraction ZIP sur disque.
  Les indisponibilités sont signalées par législature sans supprimer les autres.
- Sénat : export CSV DOSLEG et lecture de pages HTML/PDF liées aux dossiers.
- Trois notices par institution et par collecte. La présélection filtre le
  **dépôt initial**, distinct de la publication filtrée lors de la validation du
  rapport. Cela peut exclure des textes dont la publication serait dans la période.
- Le corpus initial et le complément réunis sont limités à 60 000 caractères.
  Les pages tronquées et indisponibles sont signalées ; pas d'OCR ni de JavaScript.
- Les citations sont recherchées dans le texte effectivement transmis, en
  normalisant uniquement espaces et composition Unicode. Cela ne valide pas
  leur interprétation, la date ou l'actualité juridique.
- Légifrance/PISTE n'est pas connecté. Aucune clé Assemblée/Sénat n'est attendue.

Sources officielles des exports :
[15e législature](https://data.assemblee-nationale.fr/archives-anterieures/archives-15e/dossiers-legislatifs),
[16e législature](https://data.assemblee-nationale.fr/archives-16e/dossiers-legislatifs),
[17e législature](https://data.assemblee-nationale.fr/travaux-parlementaires/dossiers-legislatifs),
[DOSLEG](https://data.senat.fr/dosleg/).

L'ancien mode web reste disponible via `POLITICAL_DATA_SOURCE=web` ; il utilise
3 à 4 appels de modèle et l'outil web payant. Aucun basculement automatique.

## Vérifications

Les tests importés de l'équipe couvrent les archives, CSV, dates, limites et liens.
Les tests d'intégration utilisent le moteur Pipelex réel et les deux transports
HTTP simulés (`httpx` pour les données, `httpx2` pour le SDK OpenAI). Ils couvrent
le complément décidé par le modèle, les corpus vides et le refus des citations
absentes. Au 27 septembre 2026 : 162 tests hors ligne réussis.

Vérification publique effectuée le 27 septembre 2026, sans appel IA : les trois
ZIP Assemblée et le CSV Sénat ont été téléchargés et analysés. Le catalogue local
`data/local/catalogue-depuis-15e-2026-09-27.json` contient 9 384 notices depuis le
21 juin 2017 : 6 587 Assemblée et 2 797 Sénat, dont 637 dossiers Sénat avec une date de
promulgation dans la période. La date retenue la plus récente est le 23 septembre
2026. Les 2 927 notices de la 15e reconnues dans l’archive sont toutes conservées.
Ce sont des notices, pas 9 384 lois distinctes. Le nombre évoluera lors des
prochaines actualisations. La génération IA sur ces archives n'a pas été testée.

Le mode hébergé est également conservé : un appel de rapport via l’API Pipelex,
avec PIPELEX_API_KEY et ENABLE_PIPELEX_CALLS=true, sans complément IA local.

## Événements récents

`recent.search_recent(topic, days=30)` accepte 7 ou 30 jours calendaires inclusifs.
`dateActe` est parcouru récursivement dans l'archive Assemblée, indépendamment du
dépôt initial ; dates nulles et futures sont exclues. Les dates de dépôt et de
promulgation du CSV Sénat sont conservées avec leur nature exacte. Les actes restent
distincts même sur un même dossier. Les doublons exacts seuls sont supprimés.

Le résultat expose `events`, `datasets`, `limitations`, `collected_at`, `start`, `end`.
Chaque événement conserve `source_url`, `source_location`, `retrieved_at` et
`dataset_sha256`. Les métadonnées ne deviennent ni une citation du texte de loi
ni une preuve de la vigueur actuelle. Les erreurs d'un producteur restent visibles,
sans remplacement fictif. Ce chemin ne change pas le schéma du rapport Pipelex.

## Flux de publication officiels branchés

Le bloc Actualités consulte aussi les flux RSS du Sénat (textes, rapports et
logement lorsque ce mot est recherché) et les listes quotidiennes de publications
de l'Assemblée pour aujourd'hui et hier. Le téléchargement se fait au clic.
Les listes Assemblée sont filtrées sur les amendements XML de la 17e législature ;
au plus 12 détails distincts sont lus, les plus récemment publiés d'abord.
La correspondance du sujet porte sur le dispositif et l'exposé sommaire.

La date RSS ou celle de la liste est une mise en ligne/republication, pas une preuve
de dépôt, d'adoption ou de promulgation. Les notices de flux restent distinctes des
actes parlementaires. Pas de garantie de couverture de 30 jours par les flux :
ils complètent les inventaires. Les indisponibilités et les limites sont affichées.
Ces signaux restent dans le bloc sans IA, séparé du résumé Pipelex.

Contrôle réel du 27 septembre : deux inventaires, trois RSS et deux listes quotidiennes
accessibles. Pour logement, 13 événements au total ; aucun signal supplémentaire
correspondant dans les flux consultés. Aucun résultat fictif ajouté, aucun appel IA.
Validation : 262 tests et 28 sous-tests passent ; mypy valide les deux collecteurs.

Références : https://www.senat.fr/flux-rss.html et
https://data.assemblee-nationale.fr/foire-aux-questions .

## Validation de la fusion Windows

Après intégration de main (679bcfc), 280 tests et 28 sous-tests passent hors ligne.
Les tests du graphe local autorisent uniquement les sockets de boucle locale
nécessaires à asyncio sous Windows ; les appels fournisseurs restent simulés.
Les dépendances et les empreintes des types générés sont cohérentes.
Aucun essai de génération réelle n’a été lancé pendant cette fusion.
