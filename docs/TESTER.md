# Tester Sed Lex sur un autre ordinateur

Ce guide concerne la branche `feat/pipelex-comparison`, qui contient le parcours
agentique décrit dans le README. Pour vérifier la version récupérée, contrôler la
présence de `backend/recent_agent.py` et de `methods/recent_agent/main.mthds`.
Le lien de soumission doit pointer vers la branche ou le commit effectivement livré.

## Accès nécessaires

- Le dépôt GitHub est public : aucun compte GitHub n'est nécessaire pour le cloner.
- Python **3.12** et un accès Internet pour installer les dépendances et consulter
  les sources parlementaires.
- Pour lancer une recherche réelle : une **clé API OpenAI personnelle, utilisable
  avec des crédits disponibles**, dans le mode local décrit ci-dessous.
- Aucun compte Google, Dust ou Pipelex hébergé n'est nécessaire pour ce parcours.
  Le moteur Pipelex s'installe avec les dépendances Python.

La clé de l'équipe n'est pas livrée. `.env` et `.streamlit/secrets.toml` sont exclus
de Git. Cloner le dépôt ne donne aucun accès aux crédits de l'équipe.
Sans clé, on peut démarrer l'interface et exécuter les tests hors ligne ; une
recherche réelle et sa synthèse IA nécessitent l'accès au fournisseur.

## Installer

Cloner la branche livrée, puis se placer à la racine :

```bash
git clone --branch feat/pipelex-comparison https://github.com/jbelhoussineX/X-AI-Hackathon.git
cd X-AI-Hackathon
python --version
python -m venv .venv
```

La commande `python` doit désigner Python 3.12. Sur Windows, on peut utiliser
`py -3.12 -m venv .venv` si plusieurs versions sont installées.

Sur macOS/Linux :

```bash
.venv/bin/python -m pip install -r requirements-ui.txt
.venv/bin/python -m pip check
```

Sur Windows PowerShell :

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-ui.txt
.\.venv\Scripts\python.exe -m pip check
```

La configuration `.pipelex/` est livrée dans le dépôt. Il n'est pas nécessaire
de lancer `pipelex init` ni de copier l'environnement Conda de l'équipe.

## Configurer une recherche réelle

Copier `.env.example` vers `.env` à la racine, uniquement si `.env` n'existe pas
déjà. Ouvrir ce nouveau fichier dans l'éditeur et régler :

```dotenv
PIPELEX_EXECUTION_MODE=local
ENABLE_PIPELEX_CALLS=true
OPENAI_API_KEY=remplacer_localement_par_sa_cle
DO_NOT_TRACK=1
```

`PIPELEX_API_KEY` peut rester vide dans ce mode. Ne pas publier `.env`, ni mettre
une clé dans le README, la vidéo, un ticket GitHub ou un message de diagnostic.
Le modèle configuré est `gpt-4o-mini`. Une recherche non vide utilise généralement
trois étapes IA, quatre si un complément est décidé ; elle consomme les crédits
associés à la clé renseignée. Aucun appel IA n'est lancé au simple démarrage.

Les variables déjà définies dans le terminal priment sur `.env` : vérifier qu'un
ancien `ENABLE_PIPELEX_CALLS=false` ou `PIPELEX_EXECUTION_MODE=hosted` n'y reste pas.
Redémarrer l'application après une modification de configuration.

## Démarrer et contrôler

macOS/Linux :

```bash
.venv/bin/python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8502 --browser.gatherUsageStats false
```

Windows PowerShell :

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1 --server.port 8502 --browser.gatherUsageStats false
```

Ouvrir **http://localhost:8502**, garder le terminal ouvert, puis :

1. Dans Mon profil, renseigner éventuellement une situation, par exemple Locataire.
2. Dans Recherche, choisir un sujet, par exemple logement, et une période de trois mois.
3. Vérifier que le formulaire affiche **Pipelex local et OpenAI**, puis cliquer sur
   Rechercher. Ce clic autorise une recherche facturée sur la clé configurée.
4. Contrôler le résumé et ouvrir sa source officielle. Un lien avec le profil n'est
   affiché que lorsqu'il est renseigné par l'analyse et correspond aux réponses.
5. Ajouter un favori et rouvrir l'historique : ces actions ne relancent pas l'IA.

Les résultats dépendent des sources publiques et de la période choisie. Le corpus
est borné et peut être partiel ou vide. Aucun résultat fictif ne remplace un échec.
Les informations du profil et l'historique sont propres à la session du navigateur ;
un redémarrage peut les effacer. Aucun accès à la base locale de l'équipe n'est requis.

## Vérification sans clé ni dépense IA

macOS/Linux :

```bash
PYTHON_DOTENV_DISABLED=1 DO_NOT_TRACK=1 .venv/bin/python -m pytest -q
```

Windows PowerShell :

```powershell
$env:PYTHON_DOTENV_DISABLED = '1'
$env:DO_NOT_TRACK = '1'
.\.venv\Scripts\python.exe -m pytest -q
Remove-Item Env:PYTHON_DOTENV_DISABLED
```

Les tests simulent les fournisseurs. Ils ne prouvent ni la validité d'une clé, ni
les crédits disponibles, ni la qualité d'une réponse réelle. Sur une installation
sans clé, laisser `ENABLE_PIPELEX_CALLS=false` pour consulter simplement l'interface.

Si la recherche est désactivée, vérifier le mode et son activation. Si une clé
est refusée ou un quota atteint, consulter l'activité du fournisseur avant de
relancer. Aucun nouvel essai n'est effectué automatiquement.
