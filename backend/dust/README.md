# Raccordement Dust — citoyen_report 1.0

Le schéma `structured_response_format.json` est la copie exacte fournie par
l'équipe et enregistrée dans Dust. Le workspace communiqué est `E1CnnabqLA`,
l'agent `McsricPkF8` (RepèresCitoyensDoc). Aucune clé n'est stockée ici.

## Ce qui fonctionne localement

- `validate_dust_report(report)` vérifie le schéma, les dates, l'unicité des
  identifiants, les liens contacts-documents et les preuves minimales.
- `prepare_comparison(...)` prépare une comparaison pour un document et une URL,
  avec les états ancien et actuel fournis par le programme.
- `python -m backend.dust chemin/rapport.json` valide un rapport enregistré, sans
  contacter Dust. Il faut fournir une réponse de l'agent, pas le schéma lui-même.

La validation structurelle implémente seulement les mots-clés utilisés par le
schéma versionné. Elle refuse les mots-clés inconnus plutôt que les ignorer.
Elle ajoute des règles applicatives : preuve de contenu pour chaque document,
preuve de relation pour chaque contact, références valides, dates réelles et
URLs HTTP(S) sans identifiants intégrés. Une sortie peut donc être conforme au
schéma Dust mais refusée par ces contrôles supplémentaires.

## Données que l'appelant doit fournir

```python
from backend.dust.adapter import prepare_comparison
from backend.comparison_service import compare_for_refresh

# Variables fournies par les futurs collecteur et stockage :
prepared = prepare_comparison(
    dust_report,
    dust_document_id="identifiant-dans-la-reponse-dust",
    stable_document_id="identifiant-permanent-attribue-par-l-application",
    current_snapshot=current_snapshot,
    previous_snapshot=previous_snapshot,
    document_is_new=False,
)
# analyze doit être un adaptateur explicitement configuré : cette bibliothèque
# ne fournit et ne lance aucun client d'API.
result = compare_for_refresh(prepared["request"], analyze)
```

Un snapshot contient `source_url`, `retrieved_at` (ISO 8601 avec fuseau),
`retrieval_status` (`ok`, `partial`, `unavailable`), `scope` (`full_document`,
`excerpts`) et `text`. Ils décrivent la récupération réelle par le programme,
pas une supposition fondée sur le texte généré par Dust.

Le texte ne vient jamais du champ `summary`. Si seul un extrait a été récupéré,
son scope est `excerpts`. Un texte intégral réellement téléchargé peut être
`full_document`. Pour une récupération réussie, chaque preuve Dust associée à
l'URL choisie doit exister exactement dans le texte fourni. Cela vérifie une
correspondance de chaînes, pas la vérité de l'interprétation.

`context` conserve la fiche Dust entière, les preuves correspondant à cette URL,
les contacts liés, le périmètre et les limites. Les preuves d'autres URLs restent
dans la fiche originale, sans être concaténées ni attribuées à la source choisie.
`context` doit être conservé et affiché avec les limites ; il n'est pas envoyé
automatiquement à la méthode de comparaison. Les incertitudes Dust ne doivent
pas disparaître lorsqu'une comparaison renvoie un résultat.

Pour un document nouvellement enregistré, passer `document_is_new=True` et
`previous_snapshot=None`. Pour un document connu, l'ancien snapshot de la même
URL est obligatoire. Si la source change, une réconciliation est nécessaire :
l'adaptateur refuse de qualifier automatiquement le document de nouveau.
L'application doit vérifier que les deux états correspondent au même objet et
à un périmètre comparable. L'égalité des URLs ne le garantit pas à elle seule.

Un rapport vide, notamment le diagnostic technique, est valide mais ne crée
aucune comparaison. L'absence d'un document dans une recherche n'implique jamais
sa suppression ou l'absence de changement. Les documents déjà suivis devront
être revérifiés par le collecteur même si Dust ne les rend pas dans sa réponse.

## Vérification locale

Depuis la racine, Python 3.11+ sans dépendance externe :

```bash
python -m unittest discover -s tests -v
python -m backend.dust tests/fixtures/dust/report.json
```

La fixture est entièrement fictive. Les 33 tests (22 comparaison, 11 Dust)
n'utilisent aucune API. Aucun essai Dust/Pipelex n'a été exécuté.

## Reste à connecter

1. Client Dust authentifié lisant les secrets dans l'environnement local.
2. Collecte des pages et métadonnées réelles ; gestion des échecs.
3. Identifiants documentaires persistants et anciennes versions en base.
4. Client Pipelex, puis stockage transactionnel et affichage du résultat.

Ces fonctions ne téléchargent pas de pages, n'appellent pas un agent et
n'écrivent pas de base de données. Ne pas présenter le parcours complet comme
fonctionnel avant ces intégrations. Les champs `role` et `relation` du schéma
Dust sont des chaînes obligatoires : toute évolution vers des valeurs nulles
doit être coordonnée avec la configuration enregistrée par l'équipe.
