# Synthèse des informations liées à un sujet

Parcours principal : **sujet → recherche Dust → explication Pipelex → interface**.
Pas besoin de deux documents ni de version antérieure. L'ancienne méthode
`political_watch` est réservée à une éventuelle comparaison ultérieure et n'est
pas appelée par la recherche.

La méthode `political_summary.summarize_interest` reçoit :

```json
{"request": {"topic": "Logement étudiant", "corpus_json": "JSON préparé par backend.summary_service.prepare_summary"}}
```

`corpus_json` contient les documents et extraits fournis par Dust avec leurs
références `e1`, `e2`, etc., locales à chaque document. Il ne contient ni les
résumés générés Dust ni les contacts. Le sujet provient de la saisie utilisateur.

La sortie contient une fiche par document : `document_id`, `explanation`
(texte accessible et références), `relevance` (lien documentaire au sujet et
références), `limitations`. Elle ne recommande aucun choix politique et n'infère
aucun profil de l'utilisateur. Un lien incertain doit être présenté comme tel.

Python assemble ensuite le rapport `citoyen_report` déjà attendu par l'interface :
seul `summary` est remplacé par l'explication et le lien au sujet avec les numéros
d'extraits. Des limites peuvent être ajoutées. Les dates, catégories, étapes,
sources, citations, contacts et limites Dust sont conservés. L'étape de procédure
reste affichée séparément ; une étape ancienne n'est pas certifiée actuelle.

Les contrôles refusent les références absentes, les fiches manquantes ou dupliquées,
et les tentatives de modification des métadonnées. Ils ne prouvent pas qu'une
interprétation est fidèle ou que la page source contient réellement l'extrait.
Les extraits restent ceux transmis par Dust, sans collecte web indépendante.

## Raccordement

`backend.summary_service.synthesize_report(topic, report, analyze)` fonctionne
avec un analyseur injecté ; `backend.pipelex_summary.analyze_summary` est son
adaptateur réel. L'appel SDK asynchrone typé `summarize_interest(SummaryRequest)`
retourne `SummaryRun(output, results)`, avec les métadonnées du run.

`src.service.search` filtre d'abord les publications par période, puis appelle
cette synthèse seulement si `ENABLE_PIPELEX_CALLS=true`. Sans cette activation,
il conserve les résumés Dust en indiquant explicitement que Pipelex est désactivé.
Un corpus vide n'entraîne aucun appel Pipelex. Une erreur n'est pas remplacée par
une fausse réussite ni une réponse fictive. Le mode Démonstration existant n'appelle rien.

**Aucun essai réel autorisé ou effectué.** Les clés et activations restent dans
l'environnement du serveur, jamais dans le frontend. Ne pas activer les appels
pour vérifier ce développement : les tests utilisent des analyseurs factices.

## Vérification

La méthode a passé la validation statique Pipelex ; les types sont générés via
`pipelex-integrate` en Python/Pydantic dans `backend/generated/political_summary`.
Ne pas les éditer : les régénérer après tout changement du bundle.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/codegen_check.py backend/generated/political_summary
.\.venv\Scripts\python.exe -m mypy backend/pipelex_summary.py backend/generated/political_summary src/service.py
```

Avant un premier essai autorisé : obtenir un rapport réel du coéquipier Dust,
vérifier ses extraits, convenir d'un budget, puis juger manuellement la fidélité,
les conditions/ exceptions, les incertitudes, le lien au sujet et la neutralité.
Les tests hors ligne ne mesurent pas la qualité des réponses du modèle.
