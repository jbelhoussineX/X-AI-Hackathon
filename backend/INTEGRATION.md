# Raccordement de la page de l'équipe

La page Streamlit de l'équipe, `frontend/interface_b.py`, a été récupérée depuis
`origin/main` (commit `210d188`). Ce dépôt n'ajoute pas de deuxième interface.
Son point d'entrée `src.service.search(topic, start, end, mode='dust')` est fourni :
il transmet la période à Dust, filtre les publications datées hors période et
conserve l'incertitude sur les dates inconnues. Aucun appel réel n'a été effectué.

## Disponible, vérifié hors ligne

- `dust/adapter.py` valide le contrat `citoyen_report` et vérifie que les citations
  sélectionnées sont présentes dans le texte source réellement récupéré.
- `comparison_service.py` valide une comparaison avant de proposer un état à conserver.
- `storage.py` conserve veilles, sources, versions et historique dans SQLite.
  Une transaction échouée est annulée ; un résultat non confirmé conserve l'état précédent.
  Une seule actualisation par veille peut être en cours. Des contenus identiques ne
  créent pas de nouvelle version ; chaque tentative reste dans l'historique.
- `refresh.py` fournit une simulation persistante sans réseau ni modèle.
- `dust/client.py` prépare un appel Dust bloquant, sans relance automatique.
- `pipelex_comparison.py` fournit un appel asynchrone typé à la méthode locale.
  Les métadonnées `RunResults` restent disponibles avec le résultat.

Les deux clients externes sont **désactivés par défaut et non testés en réel**.
Le contrôle du JSON et des citations ne certifie pas la vérité d'une analyse.

## Raccordement Python de la simulation

Depuis la racine du dépôt, après installation de `requirements.txt` :

```python
from backend.storage import Store
from backend.refresh import refresh_demo

store = Store('data/local/watch.sqlite3')
watch_id = store.add_watch('Accessibilité des transports', mode='demo')
refresh_demo(store, watch_id, 'Version du 10 octobre')
refresh_demo(store, watch_id, 'Version du 20 octobre')
documents = store.documents(watch_id)
history = store.runs(watch_id)
```

Scénarios : `Version du 10 octobre`, `Version du 20 octobre`, `Source indisponible`.
La première récupération valide est nouvelle dans cette veille ; répéter une version
produit « inchangé » ; changer de version produit « modifié ». Une indisponibilité
produit « non confirmé », sans effacer la version conservée. Tout est fictif,
quel que soit le sujet saisi. Aucun contact ou fait politique réel n'est généré.

Pour afficher une fiche, utiliser `title`, `url`, `report.description`,
`report.change_type`, `report.evidence`, `report.limitations` et
`snapshot.retrieved_at` si un état valide existe. Afficher séparément la date
de tentative (`runs.started_at`) et la date du dernier contenu conservé.
Les états d'exécution sont `running`, `completed`, `partial`, `failed`.
L'historique détaillé des rapports est conservé dans la table `results`.

Une interruption brutale peut laisser `running` : ne pas relancer automatiquement
un appel potentiellement facturé. Après vérification de l'absence de processus actif,
un développeur peut clôturer explicitement la tentative avec `store.fail(run_id, motif)`.

## Ce qui reste à intégrer

1. Raccorder les veilles de session de la page au stockage SQLite en conservant
   sujet, mode ET période (le stockage actuel ne conserve que sujet et mode).
   Ajouter l'affichage des comparaisons dans cette même page, avec sa développeuse.
2. Ajouter le collecteur de pages sources (dates réelles, erreurs, PDF, redirections,
   texte extrait et périmètre clairement identifiés). Les résumés Dust ne sont jamais
   des instantanés sources. Une même URL n'établit pas à elle seule l'identité juridique.
3. Relier recherche Dust → validation → collecte des sources → comparaison Pipelex
   → validation → transaction SQLite. Recontrôler aussi les sources déjà connues
   qu'une nouvelle recherche ne retrouve pas ; une absence ne signifie pas suppression.
4. Conserver les limites, les preuves de statut et les relations/contacts séparés
   des changements de contenu ; aucune prise de contact automatique.
5. Après autorisation explicite d'essais réels, vérifier un seul parcours avec un
   budget convenu. Aucun appel Pipelex n'est autorisé par les tests locaux.
6. En dernier : authentification pour un déploiement partagé et planification quotidienne.

## Configuration externe, pour plus tard

Ne jamais placer les clés dans le frontend, Git ou une conversation. Le programme
appelant doit charger les variables d'environnement ; les modules ne lisent pas
automatiquement `.env`. L'exemple garde `ENABLE_DUST_CALLS=false` et
`ENABLE_PIPELEX_CALLS=false`. Les identifiants connus sont le workspace
`E1CnnabqLA` et l'agent `McsricPkF8`.

`research(topic)` retourne `DustResult(report, conversation_id)` ;
`await compare_document(ComparisonRequest(...))` retourne
`ComparisonRun(output, results)`. Ne pas exposer les exceptions HTTP brutes aux utilisateurs
ni les enregistrer avec des informations d'authentification. Un timeout n'assure pas
l'annulation distante : inspecter la tentative avant de recommencer.

Le client Dust repose sur la [documentation officielle de création d'une conversation](https://docs.dust.tt/api-reference/conversations/create-a-new-conversation).
La compatibilité réelle de la réponse devra être confirmée lors du premier essai autorisé.

## Vérifications sans appels externes

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/codegen_check.py backend/generated/political_watch
.\.venv\Scripts\python.exe -m mypy backend/pipelex_comparison.py backend/clients.py backend/generated backend/dust/client.py
```

Les types Pydantic sont générés depuis tous les `.mthds` du bundle.
Après modification, utiliser `pipelex-integrate` pour les régénérer ; ne pas éditer
`models.py` ou `codegen.lock`. Le contrôle de dérive est entièrement local.
