# Collecte officielle : Sénat et Assemblée nationale

La collecte est désormais appelée par défaut par les deux modes Pipelex
(`POLITICAL_DATA_SOURCE=official`). Les sections Sénat ci-dessous décrivent
les étapes précédentes et leurs tests, pas un branchement restant à faire.

`official.py` réunit les deux institutions dans un corpus de 60 000 caractères.
`assembly.py` lit l'archive JSON officielle de la 17e législature, sans extraction
sur disque. Il conserve séparément dépôt, publication et mise en ligne.
Les URL construites depuis les identifiants sont des candidates, jamais des preuves
avant lecture réussie. Chaque version reste distincte. Trois notices par institution
au maximum sont retenues par correspondance lexicale ; cela n'est pas une recherche exhaustive.

Test réel du 27 septembre 2026 : sujet logement, 2025-01-01 à 2026-09-27,
deux inventaires disponibles, six notices sélectionnées, dix pages dans le corpus,
60 000 caractères. Deux textes sont tronqués et une page supplémentaire omise après
atteinte de la limite. Sortie locale ignorée : `data/local/official-logement-integration-20260927.json`.
Aucun appel IA ni validation juridique.

Sources : [Assemblée](https://data.assemblee-nationale.fr/travaux-parlementaires/dossiers-legislatifs),
[Sénat](https://data.senat.fr/dosleg/).
Légifrance/PISTE nécessite encore des identifiants d'application ; aucun accès n'est simulé.

## Historique et détails du collecteur Sénat

# Ta partie : API et données officielles

Tu fournis à l'agent des documents exploitables avec leur provenance. Ton livrable
est un connecteur Python et un JSON documenté ; les autres membres peuvent travailler
sur l'interface et les instructions Pipelex à partir de ce contrat.

## Sources retenues et état

| Source | Utilité | Accès | État dans ce dépôt |
|---|---|---|---|
| Sénat, DOSLEG | Repérer les dossiers par titre/thème, dépôt et état déclaré | Export CSV public, sans clé | Premier connecteur implémenté et testé sur les données réelles |
| Assemblée nationale | Dossiers et documents parlementaires de l'Assemblée | Open data ; formats et lots à choisir | Pages accessibles par le collecteur existant ; connecteur aux exports à ajouter |
| Légifrance | Compléter avec les textes publiés et leurs versions | API PISTE, inscription et OAuth | Pages accessibles par le collecteur existant ; client API à ajouter après configuration |

Un export CSV accessible en HTTP est une source de données structurées ; ce n'est
pas une API REST de recherche. Le programme télécharge ici l'export puis filtre
localement. Il n'est pas nécessaire de créer un serveur FastAPI pour cela.

Documentation officielle consultée le 27 septembre 2026 :

- [Export DOSLEG du Sénat](https://data.senat.fr/dosleg/).
- [Sens des champs de la liste des dossiers](https://data.senat.fr/aide/liste-des-dossiers-legislatifs/).
- [Portail open data de l'Assemblée](https://data.assemblee-nationale.fr/).
- [Accès à l'API Légifrance](https://www.legifrance.gouv.fr/contenu/pied-de-page/open-data-et-api).
- [Authentification et environnements PISTE](https://www.legifrance.gouv.fr/contenu/pied-de-page/foire-aux-questions-api).

## Premier connecteur disponible

Fichiers : `backend/data_sources/senate.py` (index des dossiers) et
`senate_documents.py` (dossiers et textes liés). Aucun appel IA ni secret nécessaire.

Depuis la racine du dépôt :

```powershell
.\.venv\Scripts\python.exe -m backend.data_sources.senate --topic "logement" --start 2024-01-01 --end 2026-09-27 --fetch-pages --output data/local/senat-logement-nouvel-essai.json
```

Choisir un nom de sortie inexistant. Sans `--fetch-pages`, seule la liste des
dossiers est préparée : aucun téléchargement des pages et aucune entrée Pipelex.
Le JSON et les sources téléchargées restent sous `data/local/`, ignoré par Git.

Fonction utilisable depuis Python :

```python
from backend.data_sources.senate import prepare

prepared = prepare('logement', '2024-01-01', '2026-09-27', fetch_pages=True)
records = prepared['records']
inputs = prepared['pipelex_inputs']  # None si aucun corpus n'a pu être préparé
```

## Contrat de données

Le résultat contient :

- `dataset` : URL de l'export, date réelle de récupération, SHA-256 du fichier,
  date HTTP Last-Modified si présente. Cette date HTTP n'est pas une date de texte juridique.
- `records` : au plus six dossiers, du dépôt le plus récent au plus ancien.
  Chaque dossier garde `id`, `title`, `kind`, `original_kind`, `initial_date`,
  `dossier_url`, `original_url`, `reported_state`, `promulgation_date`,
  `law_number` et `themes`.
- `limitations` : couverture, sens du filtre et problèmes de collecte.
- `linked_documents` : liens vers les textes trouvés dans les dossiers et statut
  de leur collecte (`included`, `not_attempted` ou cause d'échec).
- `pipelex_inputs` : enveloppe `request` attendue par `political_report.build_report`,
  uniquement si des pages ont été récupérées. Le `corpus_json` contient le texte
  effectivement lu, les URLs, l'horodatage et les indicateurs de troncature.
  Chaque source comporte aussi son rôle (`dossier` ou `legislative_text`), les
  dossiers qui la référencent et l'empreinte SHA-256 du contenu transmis.

Les métadonnées CSV servent au repérage. Elles ne sont pas transformées en
citations de dispositions légales. Les dates absentes restent nulles. La date
initiale correspond au dépôt initial du dossier selon les règles du Sénat ; elle
n'est pas renommée `publication_date`. Un état « promulgué » ne prouve pas qu'une
disposition soit encore en vigueur aujourd'hui.

La recherche est lexicale : tous les mots significatifs doivent être présents
dans le titre ou les thèmes. Les accents et majuscules sont normalisés. Il n'y a
pas de synonymes, de rapprochement singulier/pluriel ou de classement politique.
Commencer avec un mot simple comme `logement`, `transport` ou `énergie` ; une forme
différente peut donner d'autres résultats. Les dates inconnues sont exclues du
filtre de dépôt. Les résolutions et motions sont hors périmètre de cette version.

## Raccordement à l'agent : ce qui est prêt et ce qui reste

Le connecteur peut préparer une entrée pour la méthode Pipelex déjà validée.
Il n'a pas remplacé automatiquement PipeSearch dans l'interface : ce choix et la
fusion avec les nouvelles contributions de `main` restent à traiter à l'intégration.
Le formulaire actuel continue son parcours PipeSearch habituel.

Pour intégrer cette source, le contrôleur devra utiliser `pipelex_inputs` avec le
client `backend.pipelex_report.build_report`, puis valider le JSON brut et ses
citations contre le corpus exact, comme dans `backend.pipelex_research`. Ne pas
afficher directement la sortie du modèle. Conserver aussi les limites du collecteur.

Le collecteur suit désormais les liens explicites vers les textes HTML/PDF du
Sénat, sans inventer d'URL à partir du nom du dossier. Il parcourt au plus trois
dossiers et deux textes par dossier, dans l'ordre des liens. Les différentes URL
de versions restent distinctes ; HTML est préféré au PDF si les deux liens ont
le même nom de document. Un lien de l'Assemblée nationale n'est pas suivi ici.

L'extraction privilégie la balise HTML `main` lorsqu'elle existe ; sans cette
balise, l'extraction générale reste utilisée. Les espaces et la composition
Unicode du HTML sont normalisés avant de limiter la taille. Les pages PDF restent
séparées, sans OCR. Une absence de lien reconnu est signalée, sans prétendre que
le texte n'existe pas.

Limites : 45 secondes de budget vérifié entre lectures (une lecture en cours peut
le dépasser jusqu'à son timeout), 60 000 caractères de corpus, 4 000 par dossier
et 12 000 par texte. Les limites de taille réseau et de redirections du collecteur
commun restent actives. Toute troncature est signalée ; les champs de statut du
CSV ne deviennent pas des citations. Ce suivi reste un parcours limité et ne
reconstitue pas toute la navette parlementaire.

## Suite de ton travail, dans l'ordre

1. Choisir deux ou trois thèmes pour la démonstration et vérifier les dossiers retrouvés.
2. Contrôler les textes désormais collectés et étendre les formats de liens si
   des documents utiles ne sont pas reconnus. Relire les dispositions et leurs versions.
3. Relire les textes de l’Assemblée désormais collectés par le nouvel adaptateur.
4. Pour Légifrance, configurer une application PISTE : API souscrite, CGU validées,
   identifiants OAuth côté serveur. Sandbox et production utilisent des accès distincts.
   Ne jamais envoyer le client secret dans Git ou dans une conversation.
5. Avec le responsable de l'agent, vérifier un résultat
   complet : sujet → documents → résumé → citations.

La détection périodique des nouveaux textes peut ensuite utiliser les
[flux officiels du Sénat](https://www.senat.fr/flux-rss.html), distinctement de cette
recherche dans les dossiers. Aucun ordonnanceur n'est ajouté ici.

## Vérifications

Tests locaux :

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m mypy backend/data_sources
```

Premier contrôle réel du 27 septembre 2026 : export de 3 627 200 octets,
12 443 lignes, 11 171 dossiers de projets/propositions reconnus. Pour `logement`
du 2024-01-01 au 2026-09-27 : six dossiers retenus et quatre pages récupérées,
toutes tronquées, pour 60 000 caractères au total. Les deux pages restantes
n'ont pas été lues après atteinte du budget. Le résultat local est
`data/local/senat-logement-20260927.json`. Ces chiffres décrivent cet essai,
pas une garantie de couverture. Aucun résumé IA ni fait juridique n'a été validé.

Second contrôle réel : `data/local/senat-logement-corpus-20260927.json`, après ajout
du parcours des liens et extraction du contenu principal. Six dossiers sélectionnés,
trois parcourus, cinq sources transmises (trois dossiers et deux textes législatifs),
20 825 caractères sans troncature du contenu extrait. Un dossier n'avait pas de
lien de texte reconnu ; trois dossiers n'ont pas été parcourus par limite explicite.
Aucun appel IA. Cela ne valide ni la fidélité d'un résumé ni la vigueur des mesures.

119 tests passent avec les dépendances de l'interface installées. Les tests
automatiques utilisent des CSV et réponses HTTP fictifs. Ils vérifient
l'encodage, les dates, les URL, les doublons, les limites, les erreurs et la
préparation sans appel IA. Les droits de réutilisation des données restent ceux
du producteur ; la licence MIT du code ne remplace pas leur licence.

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
