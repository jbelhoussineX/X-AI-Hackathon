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

## Licence

MIT — voir `LICENSE`.
