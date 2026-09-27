# Parcours actif : Pipelex uniquement

La page Streamlit existante appelle :

```python
from src.service import search
result = search('Logement étudiant', '2026-01-01', '2026-09-27', mode='pipelex')
```

Cet appel consomme des crédits si les variables `PIPELEX_API_KEY` et
`ENABLE_PIPELEX_CALLS=true` sont présentes. Aucune clé Dust n’est nécessaire.
Ne pas lancer cet exemple lors des tests hors ligne.

## Étapes

1. Validation du sujet, des dates et de l’activation explicite.
2. `political_search.find_sources(request: SearchRequest) -> SearchResult` :
   une recherche PipeSearch, au plus six résultats sur les trois domaines officiels.
3. Le backend collecte les pages HTML/PDF. La réponse textuelle et les snippets du
   moteur de recherche sont écartés : ils ne deviennent jamais des preuves.
4. `political_report.build_report(request: ReportRequest) -> Report` reçoit
   uniquement le texte effectivement collecté, les URLs et les limites de collecte.
   Aucun appel de rapport si aucune page n’est exploitable.
5. Validation du JSON brut, du sujet, des identifiants, références et preuves de
   procédure ; concordance des citations avec le corpus transmis. Une citation
   absente ou une URL non lue fait échouer la recherche, sans résultat fictif de secours.
6. Filtrage des dates de publication hors période et suppression des contacts
   devenus orphelins. Date inconnue : document conservé avec réserve explicite.
7. Retour à l’interface avec `mode='pipelex'`, `report`, `duration_seconds` et
   `source_checks`. Les identifiants de vérification suivent les documents filtrés.

Le contrat `report_schema.json` conserve les champs `schema_version`, `topic`,
`scope`, `documents`, `contacts` et `limitations`. Au plus quatre documents et trois
contacts. La première version traite projets et propositions de loi. Un contact
n’est rendu que si les pages disponibles documentent sa relation et ses coordonnées
publiques ; il est normal d’obtenir `contacts=[]`.

Les modules d’appels typés conservent `RunResults` avec le résultat. Le contrôleur
retourne ces métadonnées dans `ResearchResult.runs` aux appelants Python, pas à
l’interface. Les erreurs HTTP ne sont pas affichées en clair. Il n’y a pas de retry
applicatif : un timeout ne garantit pas l’annulation distante.

## Types et validation

Types Pydantic générés dans `generated/political_search` et `generated/political_report`
par le générateur Pipelex, moteur 0.65.0. Ne pas les éditer. Leurs `sources.json`
pointent vers les méthodes locales et enregistrent leurs SHA-256 ; le chargement
refuse toute dérive avant un appel. `scripts/codegen_check.py` vérifie hors ligne
les fichiers générés et les sources. Les deux bundles ont passé la validation
statique et ne contiennent aucun placeholder de pipe.

Les tests automatiques remplacent les réponses Pipelex et HTTP par des données
fictives. Ils couvrent notamment le contrat de l’interface, les citations inventées,
les domaines trompeurs, la troncature, les PDF, le filtre de dates, les sorties vides
et la désactivation avant réseau. Le nouveau parcours reste à tester en réel.

## Travaux futurs

- Évaluer un parcours réel avec un budget et vérifier manuellement la fidélité du rapport.
- Affiner la recherche de dossiers législatifs si les résultats ne suffisent pas à établir une étape.
- Raccorder les veilles de session au stockage existant en conservant aussi la période.
- Ajouter éventuellement un suivi des versions ; ce n’est pas une condition pour informer selon un sujet.

Les fichiers Dust et l’ancienne synthèse sont conservés comme historiques. Ils ne
sont pas importés par le parcours actif. Aucun changement distant dans le compte
Dust ni déploiement au catalogue Pipelex n’a été effectué.
