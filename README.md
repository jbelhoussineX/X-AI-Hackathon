# Repères citoyens — socle de hackathon

## Mise à jour locale : interface de l'équipe et Pipelex

`app.py` lance désormais l'interface de `frontend/interface_b.py`, avec un mode
**Démonstration** sans réseau et un mode **Pipelex + OpenAI**. Le moteur Pipelex
tourne localement ; les appels de modèles et la recherche web utilisent OpenAI.

Sur le Mac de l'équipe :

```bash
conda activate xia-hackathon
python -m streamlit run app.py --server.address 127.0.0.1 --server.fileWatcherType none
```

L'ouverture et la navigation ne déclenchent aucun appel IA. Une recherche réelle
nécessite le consentement dans le menu et un clic. La source par défaut est
`POLITICAL_DATA_SOURCE=official` : exports publics Sénat et Assemblée nationale,
sans clé ni outil web payant. OpenAI (`gpt-4o-mini`) évalue les manques, peut demander
un complément de collecte et rédige : **deux appels de modèle**, ou zéro si le
corpus initial est vide. Aucun compte Pipelex hébergé n'est nécessaire.

Commencer avec un mot-clé simple, par exemple **logement**. La collecte est lexicale,
étendue aux 15e, 16e et 17e législatures pour l'Assemblée (recherche depuis juin 2017, incluant toute la 15e législature),
avec un corpus de 60 000 caractères au total. Un [catalogue complet des notices](backend/data_sources/README.md)
peut être exporté sans IA ; le rapport reste limité à quatre documents.
Le repérage filtre le dépôt initial ; le rapport filtre ensuite la publication.
Cette différence et les limites de couverture sont signalées à l'utilisateur.
Les citations du rapport sont contrôlées contre le corpus effectivement collecté.
Leur présence ne certifie pas l'interprétation ni l'actualité juridique.

L'ancien parcours reste disponible avec `POLITICAL_DATA_SOURCE=web` (3 à 4 appels
et outil web payant). Aucun repli automatique vers ce mode n'est effectué.
Les corrections du rapport et les plafonds de quatre documents/trois interlocuteurs
restent actifs. Une page de contact sans preuve dédiée est omise avec une explication.

**Validation : 162 tests hors ligne réussis**, dont les collecteurs importés de
l'équipe, les parcours Pipelex officiel et web et l'interface Streamlit.
Le 27 septembre 2026, les trois archives Assemblée et l'export Sénat ont été
téléchargés sans appel IA : 9 384 notices retenues depuis le 21 juin 2017 (6 587 Assemblée,
2 797 Sénat), dont toutes les 2 927 notices de la 15e reconnues dans l’archive,
dans `data/local/catalogue-depuis-15e-2026-09-27.json` sur le Mac de l'équipe.
Le fichier est ignoré par Git ; la commande documentée permet de le régénérer.
Le parcours web précédent a fonctionné lors d'un essai utilisateur ; la génération
IA sur la nouvelle couverture historique n'a pas été testée avec les fournisseurs réels.
Voir [le collecteur et ses limites](backend/data_sources/README.md).

Voir [le branchement et ses limites](docs/BRANCHEMENT_STREAMLIT.md) et
[l'installation Pipelex](docs/INSTALLATION_PIPELEX.md).
La signature du service et le rapport JSON v1 sont conservés ; `mode="pipelex"`
est ajouté. Les schémas et `CONTRACT.md` ne sont pas modifiés.

Les sections Dust ci-dessous documentent le socle historique, toujours conservé
dans le service pour compatibilité, et ne décrivent pas le nouveau moteur.

Prototype de recherche documentaire : thème → textes parlementaires → extraits → interlocuteurs.
**Ce dossier est un point de départ généré avec une IA, pas un produit terminé.**

## État du kit au moment de sa génération

- 38 tests automatisés exécutés avec succès hors ligne, avec des réponses API simulées.
- Syntaxe Python de l'application, des outils et des modules compilée sans erreur.
- **Connexion à un compte Dust réel NON testée.** Aucun accès ni crédit partenaire utilisé.
- **Interface Streamlit NON lancée ni inspectée dans un navigateur dans l'environnement de création.**
- **Aucune recherche politique réelle intégrée ni validée.**
- Le mode exemple est fictif, fixe et explicitement marqué. Il ne répond pas au sujet saisi.
- Les contrôles vérifient un format et certaines cohérences ; ils ne prouvent pas l'exactitude des sources.

À votre charge : configurer et tester Dust, améliorer le produit, choisir un cas, relire les preuves,
mesurer le fonctionnement réel, documenter les contributions et enregistrer la vidéo.
Le script de connexion est fondé sur la documentation citée dans docs/SOURCES.md ; un ajustement
peut être nécessaire selon vos permissions, la région de l'espace et la version des réponses API.

## 1. Installer — Python 3.11 ou 3.12 conseillé pour l'équipe

Ouvrir dans VS Code le dossier qui contient `app.py`. Ouvrir Terminal > New Terminal.
Vérifier que le terminal se trouve dans ce dossier. Les commandes n'activent pas le venv : elles
utilisent directement son exécutable, ce qui évite les problèmes de politique PowerShell.

### Mac
```bash
python3 --version
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest -q
.venv/bin/python -m streamlit run app.py
```
### Windows — PowerShell
```powershell
py --version
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m streamlit run app.py
```
Si `py` n'existe pas mais `python --version` retourne une version adaptée, utiliser `python`
pour créer `.venv`. Si aucun Python n'est installé, installer Python depuis python.org,
fermer/réouvrir le terminal puis recommencer. Ne pas modifier le Python système sur Mac.
L'adresse locale s'affiche dans le terminal. Arrêter le serveur avec Ctrl+C dans ce terminal.

Le mode exemple ne demande pas de clé. Le premier succès attendu : une fiche marquée FICTIVE.
L'environnement `.venv` est local à chaque ordinateur et ne doit pas être envoyé dans Git.
Les versions exactes testées hors ligne : requests 2.32.5, python-dotenv 1.2.2,
jsonschema 4.26.0 et pytest 9.0.2. Streamlit doit être installé et testé chez vous.

## 2. Configurer l'agent Dust

Dans votre espace Dust, créer un agent nommé `ReperesCitoyens`.
Coller `prompts/01_AGENT_DUST.txt` dans ses instructions. Le Sidekick de Dust peut aider,
mais relire sa configuration ; il ne doit pas ajouter des outils externes non nécessaires.
Activer **Web Search & Browse**. Ne pas confondre avec la recherche dans les documents internes.
Choisir un modèle autorisé compatible avec le format structuré.
Dans **Advanced > Structured Response Format**, coller le contenu entier de
`schemas/dust_response_format.json`, puis sauvegarder. Enregistrer l'agent avec les accès nécessaires.
Tester dans l'aperçu avec un sujet précis. Ouvrir les actions réelles de recherche et les pages
sources lorsqu'elles sont accessibles dans votre interface. Un récit d'actions n'est pas une trace.

Les instructions bornent approximativement les recherches ; ce n'est pas un blocage logiciel des coûts.
La sortie est contrôlée contre `schemas/report.schema.json`. Ne pas changer un schéma seul.

## 3. Configurer la clé localement

Copier `.env.example` vers `.env` dans VS Code. Modifier `.env` à la main :
- DUST_API_KEY : clé de votre espace autorisé ; jamais un mot de passe ni une clé OpenAI.
- DUST_WORKSPACE_ID : identifiant après `/w/` dans l'URL de votre espace.
- DUST_AGENT_ID : sId de l'agent, obtenu avec le script ci-dessous ; pas `@ReperesCitoyens`.

La documentation Dust indique **Admin > API & Programmatic > API Keys > Create an API Key**
pour les administrateurs. Si cette fonction manque, demander à l'organisateur l'accès autorisé.
Ne pas contourner un contrôle d'accès. Ne pas échanger de clés personnelles dans Git, les chats ou les prompts.

Après avoir rempli la clé et le workspace, lister les agents :
```bash
# Mac
.venv/bin/python tools/check_dust.py --list-agents
```
```powershell
# Windows
.\.venv\Scripts\python.exe tools/check_dust.py --list-agents
```
La sortie affiche seulement les noms et identifiants des agents accessibles. Copier l'ID attendu
localement dans `.env`. Puis remplacer `--list-agents` par `--check` et relancer : cet appel
fait une génération LLM de diagnostic, sans recherche web demandée. Il consomme donc potentiellement
des crédits. Aucun de ces scripts ne crée ou ne finance de compte.

Le diagnostic doit annoncer connexion et format JSON validés. Il ne valide PAS la recherche web.
Dans l'application, sélectionner ensuite **Recherche réelle — Dust**, saisir un sujet et cliquer
Rechercher. Les filtres/retours d'interface ne doivent pas relancer l'API automatiquement.
Les résultats sont conservés dans la session de l'interface ; Dust peut conserver sa conversation.
« Application locale » ne signifie pas « modèle local », « fonctionnement hors ligne » ou « absence de stockage fournisseur ».

## 4. Travailler à trois

A : intégration, src/, tools/, schémas et dépendances. B : interface. C : agent, corpus/tests, documentation et vidéo.
Tous lisent AGENTS.md et CONTRACT.md. Chaque personne donne à son Codex le prompt associé dans prompts/.
Même contrat, trois branches : `a-integration`, `b-interface`, `c-agent-tests`.
A fusionne une contribution à la fois après tests. Ne pas éditer les mêmes fichiers en parallèle.
Pour un conflit Git : arrêter les modifications, faire un commit de sauvegarde sur la branche
concernée quand c'est possible, puis résoudre avec A ; pas de force-push ni suppression au hasard.

## 5. Vérifier avant la démo

Lire docs/TESTS_MANUELS.md. Choisir quelques sources officielles réelles et ouvrir chaque lien.
Vérifier contenu, statut, dates, fonction de l'interlocuteur et page de contact.
Le site officiel de la personne, le dossier législatif et le texte peuvent être trois sources distinctes.
Ne pas prétendre avoir prouvé une absence de position quand le moteur n'a trouvé aucun résultat.
Ne pas noter ni recommander des choix politiques. Ne pas inventer d'email.
Ne pas afficher un badge « vérifié » pour une simple sortie JSON valide.

## 6. Limites techniques et sécurité

Un POST de création de conversation par recherche ; aucun retry automatique.
HTTP 401 : clé ; 403 : permissions ; 404 : IDs/région ; 429 : limites ; 5xx : service.
Un délai de lecture de 120 s ne constitue pas un plafond du temps total ou des crédits distants.
En cas de timeout, ouvrir Dust pour examiner/arrêter la conversation avant une nouvelle tentative.
La voie plus avancée est création non bloquante + suivi + annulation ; elle n'est pas implémentée.
Les sources ne sont pas téléchargées séparément par Python. Leurs citations restent à vérifier.
Le filtre de lien empêche certains liens dangereux mais n'est pas un audit de DNS ni de sécurité Web.
Ne pas ajouter de comptes, de profil sensible, d'hébergement public ou de service payant pour la démo.
`.gitignore` évite les ajouts usuels à Git, mais n'empêche pas un assistant de lire un fichier local.
En cas de clé exposée : la révoquer et la remplacer ; enlever le fichier du dernier commit ne suffit pas.

## 7. Dépôt final

Adapter ce README à l'état réellement obtenu : fonctionnalités, limites, résultats observés,
modèle/agent utilisés, sources, versions de paquets et instructions reproductibles.
Fournir les instructions et schémas pour recréer l'agent : l'ID d'un agent privé seul ne suffit pas au jury.
Aucun crédit/clé personnelle dans le dépôt. Préciser la dépendance aux accès partenaires et leur durée.
Déclarer l'utilisation de ce socle généré avec une IA et les éléments développés par l'équipe.
Vérifier dans le règlement comment les ressources préexistantes doivent être signalées.

À compléter par l'équipe :
- Membres : …
- Description courte : …
- Vidéo, deux minutes maximum : …
- Accès du jury au dépôt : …
- Date/heure de soumission et confirmation : …

## Fichiers du dépôt GitHub de l'équipe

Le dépôt partagé apporte également `frontend/interface_b.py`, une interface Streamlit
avec résultats, exports, historique et veilles conservées dans la session.
Le point d'entrée du socle reste `app.py`. La présence du dossier `frontend/`
n'ajoute pas de frontend React ni de serveur supplémentaire.
Les dossiers `backend/`, `data/` et `scripts/` sont des emplacements préparatoires.
La sauvegarde SQLite, Pipelex et l'actualisation quotidienne restent des extensions.

Sur le Mac de Maison, l'environnement existant s'utilise ainsi depuis la racine :
```bash
conda activate xia-hackathon
python -m pytest -q
python -m streamlit run app.py
```
Dans cet environnement, utiliser `python` (3.12), car `python3` pointe vers un ancien Python.
Pour ouvrir l'interface de l'équipe depuis la même racine :
```bash
python -m streamlit run frontend/interface_b.py --server.address 127.0.0.1
```
La connexion réelle à Dust reste à vérifier séparément avec un accès partenaire autorisé.

Le dépôt partagé fournit la licence MIT dans `LICENSE`.
