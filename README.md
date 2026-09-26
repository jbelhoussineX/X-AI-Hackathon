# X-AI-Hackathon
Agent IA de veille politique personnalisée qui suit les sujets qui vous intéressent et synthétise l’actualité pour vous tenir informé.

Agent IA de veille politique personnalisée, conçu pour un hackathon de trois jours par une équipe de trois personnes. Le projet vise à aider chaque utilisateur à suivre les sujets politiques qui l’intéressent et à consulter des synthèses adaptées à ses besoins.

## Structure du repository

```text
political-watch-agent/
├── frontend/
├── backend/
├── data/
├── scripts/
├── tests/
├── .env.example
├── .gitignore
├── README.md
└── LICENSE
```

Les dossiers vides sont conservés dans Git grâce à des fichiers `.gitkeep`.

## Configuration locale

Copier le fichier d’exemple depuis la racine du repository :

```bash
cp .env.example .env
```

Sous PowerShell :

```powershell
Copy-Item .env.example .env
```

Renseigner les valeurs nécessaires uniquement dans le fichier local `.env`.
**Ne jamais committer `.env` ni aucune clé API ou autre secret.** Le fichier `.env.example` doit rester sans secrets réels.

## Analyse des changements avec Pipelex

La [méthode de comparaison](methods/political_watch/README.md) définit le contrat d'échange avec Dust et les sorties attendues. Elle est validée par Pipelex ; les [quatre cas fictifs](tests/fixtures/political_watch/README.md) sont prêts pour les essais, qui n'ont pas encore été exécutés avec un modèle.

Les contrôles Python et la fonction de raccordement sont dans `backend/`.
Pour lancer les 22 tests locaux, sans API ni crédits, depuis la racine du dépôt :

```bash
python -m unittest discover -s tests -v
```

Python 3.11 ou ultérieur suffit, sans dépendance externe. Le client Dust, le client
Pipelex, la persistance et l'interface ne sont pas encore raccordés.

## Licence

MIT — voir `LICENSE`.
