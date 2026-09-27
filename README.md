# X-AI-Hackathon — Repères citoyens

Agent de recherche documentaire et de veille politique sur la France, développé
par trois personnes pour un hackathon de trois jours. Il vise à présenter des
documents, leurs sources et leurs évolutions sans recommander de choix politique.

## Lancer la page de l'équipe

Depuis la racine du dépôt, sous PowerShell, avec Python 3.11 ou ultérieur :

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-ui.txt
.\.venv\Scripts\python.exe -m streamlit run frontend/interface_b.py --server.address 127.0.0.1
```

Le mode **Démonstration** utilise des fiches fictives, sans clé et sans appel IA.
La page existante de l'équipe est conservée. Son formulaire est raccordé à
`src.service.search(topic, start, end, mode='dust')` ; les appels réels restent
désactivés par défaut et n'ont pas été testés en réel.

## Configuration

```powershell
Copy-Item .env.example .env
```

**Ne jamais committer `.env` ni de clé API.** L'exemple reste sans secrets.
Les clients lisent les variables d'environnement du processus ; copier `.env`
ne les charge pas automatiquement. Les clés restent exclusivement côté serveur.
Ne pas activer `ENABLE_PIPELEX_CALLS` tant qu'un essai n'a pas été autorisé.

## État actuel

- Interface Streamlit : recherche, fiches, preuves, contacts, export, veilles de session.
- Dust : contrat JSON et client préparés, filtre de dates côté service, appels désactivés.
- Pipelex : méthode de comparaison, types Pydantic générés, client et validation locale.
- SQLite : stockage transactionnel et actualisations simulées testés ; pas encore reliés
  aux veilles de session de l'interface.
- À faire : collecte réelle des pages, parcours complet Dust → sources → Pipelex → SQLite,
  affichage des changements dans la page existante, puis essais réels autorisés.
  Aucune actualisation quotidienne n'est active.

Voir le [guide de raccordement](backend/INTEGRATION.md) pour les fonctions disponibles,
les limites et les prochaines étapes. Le contrôle de structure ne certifie pas
l'exactitude factuelle des sorties.

## Structure

```text
X-AI-Hackathon/
├── frontend/interface_b.py       # Page de l'équipe
├── src/service.py                # Contrat appelé par cette page
├── backend/                     # Validation, clients, SQLite, simulation
│   ├── dust/
│   └── generated/political_watch/
├── methods/political_watch/     # Méthode Pipelex
├── data/                        # Données locales ignorées par Git
├── scripts/codegen_check.py
├── tests/                       # Tests et exemples fictifs
├── requirements.txt
├── requirements-ui.txt
├── .env.example
├── .gitignore
└── LICENSE
```

## Vérification hors ligne

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/codegen_check.py backend/generated/political_watch
.\.venv\Scripts\python.exe -m mypy backend/pipelex_comparison.py backend/clients.py backend/generated backend/dust/client.py src/service.py
```

52 tests avec les dépendances UI installées, dont interactions de démonstration
Streamlit et clients simulés. Aucun de ces tests n'exécute Dust ou Pipelex.
Les fichiers générés ne doivent pas être modifiés à la main.

## Licence

MIT — voir `LICENSE`.
