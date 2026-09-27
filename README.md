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

Depuis la racine du dépôt, dans PowerShell, avec Python 3.11 ou ultérieur :

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-ui.txt
.\.venv\Scripts\python.exe -m streamlit run frontend/interface_b.py --server.address 127.0.0.1
```

Le mode **Démonstration** fonctionne sans clé ni réseau, avec des fiches fictives.
Le mode **Recherche réelle · Pipelex** appelle
`src.service.search(topic, start, end, mode='pipelex')` après clic et consentement.
Il utilise au plus deux exécutions de méthode : recherche, puis rapport si un
corpus a pu être collecté. Il n’y a ni relance automatique, ni planification.
Ce nombre d’exécutions ne constitue pas un plafond de facturation fournisseur.

## Configuration

```powershell
Copy-Item .env.example .env
```

**Ne jamais committer `.env` ou une clé API.** Seuls `PIPELEX_API_KEY` et
`ENABLE_PIPELEX_CALLS` sont nécessaires pour le parcours réel. Les clients lisent
les variables du processus : `.env` n’est pas chargé automatiquement.
Les appels restent désactivés par défaut. Pour un essai volontaire, saisir la clé
sans l’afficher ni l’inscrire dans l’historique PowerShell, puis lancer l’interface
depuis cette même fenêtre :

```powershell
$pipelexSecret = Read-Host "Cle API Pipelex" -AsSecureString
$env:PIPELEX_API_KEY = [System.Net.NetworkCredential]::new('', $pipelexSecret).Password
$env:ENABLE_PIPELEX_CALLS = 'true'
.\.venv\Scripts\python.exe -m streamlit run frontend/interface_b.py --server.address 127.0.0.1
```

Après l’arrêt de Streamlit :

```powershell
$env:ENABLE_PIPELEX_CALLS = 'false'
Remove-Item Env:PIPELEX_API_KEY
Remove-Variable pipelexSecret
```

## Structure utile

```text
frontend/interface_b.py          Interface de l’équipe
src/service.py                   Contrat du formulaire et filtre de dates
backend/pipelex_research.py       Recherche, collecte et vérification
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
.\.venv\Scripts\python.exe -m unittest discover -s tests
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

Licence MIT — voir [LICENSE](LICENSE).
