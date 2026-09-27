# X-AI-Hackathon — Repères citoyens

Agent de recherche documentaire sur les politiques françaises, développé pour un
hackathon de trois jours. L’utilisateur choisit un sujet et une période ; le
programme recherche des textes parlementaires et présente un résumé, des preuves
et des limites, sans recommander de choix politique.

Le parcours actif utilise **Pipelex uniquement** : sujet → recherche de sources
→ collecte Python des pages officielles → rapport Pipelex → contrôle des citations
→ interface Streamlit existante. Aucune comparaison entre deux documents n’est
nécessaire. Dust ne fait plus partie de ce parcours.

## Démarrer

Depuis la racine du dépôt, dans PowerShell, avec Python 3.11 à 3.14 :

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-ui.txt
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

Le mode **Démonstration** fonctionne sans clé ni réseau, avec des fiches fictives.
Le mode **Recherche réelle · Pipelex** appelle
`src.service.search(topic, start, end, mode='pipelex')` après clic et consentement.
Par défaut, les inventaires officiels Sénat et Assemblée sont téléchargés sans IA,
puis les pages pertinentes sont collectées. Un seul appel de synthèse est demandé
si le corpus n'est pas vide. Aucune synthèse n'est demandée si la collecte est vide.
Les extraits sont contrôlés dans le corpus exact transmis. Il n’y a ni relance automatique, ni planification.
Ce nombre d’exécutions ne constitue pas un plafond de facturation fournisseur.

## Configuration

```powershell
Copy-Item .env.example .env
```

Deux exécutions sont disponibles, sans changer l'interface :

- `PIPELEX_EXECUTION_MODE=hosted` (défaut) : API Pipelex, avec `PIPELEX_API_KEY`.
- `PIPELEX_EXECUTION_MODE=local` : moteur Pipelex sur l'ordinateur et API OpenAI,
  avec `OPENAI_API_KEY`. C'est le parcours ajouté par l'équipe sur main.

`POLITICAL_DATA_SOURCE=official` sélectionne la collecte officielle.
`web` active explicitement l'ancien parcours de recherche IA : deux méthodes
hébergées, ou trois à quatre appels OpenAI avec le moteur local.
Aucune bascule automatique entre fournisseurs ou modes de recherche.

**Ne jamais committer `.env` ou une clé API.** En mode hébergé, renseigner `PIPELEX_API_KEY` et
`ENABLE_PIPELEX_CALLS=true`. Les clients lisent
les variables du processus : `.env` n’est pas chargé automatiquement.
Les appels restent désactivés par défaut. Pour un essai volontaire, saisir la clé
sans l’afficher ni l’inscrire dans l’historique PowerShell, puis lancer l’interface
depuis cette même fenêtre :

```powershell
$pipelexSecret = Read-Host "Cle API Pipelex" -AsSecureString
$env:PIPELEX_API_KEY = [System.Net.NetworkCredential]::new('', $pipelexSecret).Password
$env:ENABLE_PIPELEX_CALLS = 'true'
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

Après l’arrêt de Streamlit :

```powershell
$env:ENABLE_PIPELEX_CALLS = 'false'
Remove-Item Env:PIPELEX_API_KEY
Remove-Variable pipelexSecret
```

## Structure utile

```text
app.py                           Point d’entrée Streamlit
frontend/interface_b.py          Interface de l’équipe
src/service.py                   Contrat du formulaire et filtre de dates
backend/pipelex_research.py       Parcours hébergé et vérification
backend/data_sources/            Inventaires et collecte officielle
src/openai_research.py            Parcours local avec le même corpus
methods/recherche_citoyenne/      Graphe local ajouté par l’équipe
backend/pipelex_search.py         Appel typé de recherche
backend/pipelex_report.py         Appel typé de rapport
backend/report_schema.json       Contrat citoyen_report 1.0 indépendant du fournisseur
backend/source_verification.py   Contrôle des pages HTML/PDF
backend/generated/               Types générés et empreintes de sources
methods/political_search/        PipeSearch sur les domaines officiels
methods/political_report/        Rapport structuré à partir du corpus lu
tests/                           Tests locaux et réponses simulées
```

`backend/dust/` et les méthodes historiques `political_summary` et
`political_watch` restent disponibles pour référence et compatibilité des anciens
outils ; le formulaire ne les appelle plus. Le stockage SQLite et la comparaison
de versions restent des extensions hors du parcours principal.

## Vérifier sans appel IA

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/codegen_check.py backend/generated/political_search backend/generated/political_report backend/generated/political_summary backend/generated/political_watch
.\.venv\Scripts\python.exe -m mypy backend/pipelex_search.py backend/pipelex_report.py backend/method_bundle.py backend/pipelex_research.py backend/source_verification.py backend/report_contract.py src/service.py backend/generated
```

Les deux nouvelles méthodes ont été validées par Pipelex et leurs types générés
avec `python-pydantic`. Aucun essai réel de ce nouveau parcours complet n’a encore
été exécuté. L’ancien essai de synthèse sur un cas fictif ne valide pas la nouvelle
recherche.

À faire : un essai réel limité sur un sujet, puis une relecture humaine des
résumés, des dates et des citations. Les veilles restent en mémoire de session ;
leur persistance et leur actualisation quotidienne ne sont pas raccordées.

Voir [le raccordement](backend/INTEGRATION.md) et [les limites des sources](backend/SOURCES.md).

La [partie API et données](backend/data_sources/README.md) est raccordée aux deux
modes Pipelex. La recherche est lexicale sur titres/thèmes ; elle n'est pas exhaustive.
Les métadonnées servent au repérage, les pages lues servent aux citations.
L'API Légifrance/PISTE n'est pas connectée. Aucun statut « en vigueur » n'est certifié.

Pour vérifier uniquement la collecte, sans clé ni appel IA :

```powershell
.\.venv\Scripts\python.exe -m backend.data_sources.official --topic logement --start 2025-01-01 --end 2026-09-27 --output data/local/collecte-logement.json
```

La sortie est ignorée par Git. Choisir un nouveau nom si le fichier existe déjà.
Le contrôle réel du 27 septembre a recueilli dix pages, six notices sélectionnées,
60 000 caractères (limite atteinte, troncatures signalées). Il ne valide pas un résumé IA.

Licence MIT — voir [LICENSE](LICENSE).

## Validation de l'intégration du 27 septembre 2026

191 tests et 28 sous-tests passent (`python -m pytest -q`), dont le moteur
Pipelex local avec réponses OpenAI simulées et l'interface Streamlit.
`pip check` ne détecte aucune dépendance cassée ; les quatre ensembles de types
générés sont à jour. Mypy passe sur les huit fichiers ciblés du service et des données.
Le SDK Pipelex 0.13.0 et le moteur 0.67.0 partagent la dépendance MTHDS 0.16.0.
Les appels payants du parcours fusionné n'ont pas été testés.

## Correctif équipe intégré

Le commit `4eb20af` de main améliore le parcours local OpenAI : recherche web,
validation des rapports, gestion des compléments tronqués et diagnostics expurgés.
Voir [le branchement](docs/BRANCHEMENT_STREAMLIT.md) et
[la revue des sources](docs/REVUE_SOURCES_OFFICIELLES.md).
Ces changements ne prouvent pas la résolution d’une erreur réseau de l’API hébergée.
