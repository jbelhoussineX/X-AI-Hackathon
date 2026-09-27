> Mise à jour du 27 septembre : ce document décrit le parcours local OpenAI
> ajouté par l'équipe. Pour l'activer, définir `PIPELEX_EXECUTION_MODE=local`
> et `ENABLE_PIPELEX_CALLS=true`. Le nouveau défaut de collecte est `official`
> (Sénat/Assemblée, puis deux appels OpenAI si le corpus est non vide).
> Les indications « 3 à 4 appels » concernent uniquement `POLITICAL_DATA_SOURCE=web`.
> Les variables sont fournies au processus ; aucun chargement automatique de .env.
> Voir le [README actuel](../README.md). Les anciens résultats de tests ci-dessous
> sont des constats historiques de l'auteur, pas la validation de cette fusion.

# Installer Pipelex pour Sed Lex

Ce guide prépare Pipelex sur le Mac de Maison, dans l'environnement Conda
`xia-hackathon`, avec la clé API OpenAI de l'équipe. Le moteur Pipelex tourne
localement ; les appels au modèle sont envoyés à OpenAI et consomment ses crédits API.
Ce parcours utilise l'accès direct OpenAI : aucun compte ni abonnement Pipelex
hébergé n'est nécessaire. [Accès aux fournisseurs](https://docs.pipelex.com/latest/get-started/configure-ai-providers/).

Version retenue pour ce guide : **Pipelex 0.67.0**, disponible lors de la préparation.
Ses métadonnées demandent Python 3.11 à 3.14 ; le Python 3.12.11 de l'équipe convient.
[Paquet publié](https://pypi.org/project/pipelex/0.67.0/).

L'objectif de ce guide est d'obtenir une installation, une validation sans appel IA,
puis un petit essai de connexion. Le branchement applicatif est maintenant réalisé
et décrit dans [BRANCHEMENT_STREAMLIT.md](BRANCHEMENT_STREAMLIT.md) : l'interface
de l'équipe propose Pipelex + OpenAI. Son nouveau parcours web est testé hors ligne
uniquement ; le diagnostic texte de ce guide ne valide pas la recherche réelle.

**État sur ce Mac après exécution de la procédure** : l'installation et
l'initialisation ci-dessous sont maintenant effectuées. Pipelex 0.67.0,
requests 2.33.0 et le SDK OpenAI 3.3.0 sont installés dans `xia-hackathon`.
La validation, la simulation et le test réel de connexion ont réussi. Après
configuration de la clé par l'utilisateur, les traces locales enregistrent deux
exécutions de `gpt-4o-mini`, pour un total de 50 tokens d'entrée et 20 de sortie.
Le second appel était involontaire : le compteur du diagnostic temporaire
surveillait `httpx`, alors que le SDK OpenAI 3.3.0 installé utilise `httpx2`.
Ce compteur a été corrigé ; aucun appel API supplémentaire n'a été lancé pour
vérifier la correction. Ne pas relancer `init` ni le test sur ce Mac : passer
au travail d'intégration de l'étape 7. Ce succès ne mesure pas le solde restant.

**1. Ouvrir le bon terminal et vérifier Python**

Dans le terminal de VS Code, exécuter :

```bash
cd /Users/maison/Downloads/kit_hackathon_reperes_citoyens
conda activate xia-hackathon
python --version
python -c "import sys; print(sys.executable)"
```

Les deux dernières commandes doivent afficher Python 3.12.11 et :

```text
/Users/maison/anaconda3/envs/xia-hackathon/bin/python
```

Utiliser `python` dans la suite. Sur ce Mac, `python3` désigne un ancien interpréteur.
Les autres membres utilisent leur propre chemin de projet et leur environnement Python.

**2. Adapter les dépendances, puis installer**

Sur un autre poste ou pour reproduire la modification, vérifier que
`requirements.txt` contient les versions ci-dessous. La modification est déjà
faite dans ce dépôt. La ligne précédente :

```text
requests==2.32.5
```

est remplacée par :

```text
requests==2.33.0
```

et cette ligne est ajoutée une seule fois :

```text
pipelex[cli]==0.67.0
```

Conserver les autres dépendances. Cette modification revient à A, responsable de
l'intégration. Elle est nécessaire : la simulation d'installation avec le fichier
actuel échoue, car Pipelex 0.67.0 exige `requests>=2.33.0`.
La simulation avec cette proposition a réussi sur le Python de l'équipe.
Le SDK `openai` fait partie des dépendances de Pipelex ; il n'est pas nécessaire
de l'installer séparément pour ce premier essai.

Exécuter d'abord la simulation, qui télécharge éventuellement des métadonnées
mais n'installe rien :

```bash
python -m pip install --dry-run -r requirements.txt
```

Si elle réussit, installer et contrôler :

```bash
python -m pip install -r requirements.txt
python -m pip check
python -m pytest -q
python -c "from importlib.metadata import version; print('Pipelex', version('pipelex'))"
```

Résultats attendus : aucune incompatibilité signalée par `pip check`, tests réussis
et `Pipelex 0.67.0`. Le socle comportait 41 tests avant cette installation.
Si une commande échoue, traiter son erreur avant de passer à la suivante ; ne pas
utiliser `--no-deps` pour contourner un conflit.

**3. Initialiser Pipelex avec OpenAI uniquement**

Toujours depuis la racine du projet, pour la première initialisation seulement
(déjà effectuée sur ce Mac) :

```bash
export DO_NOT_TRACK=1
pipelex-agent init --config '{"backends":["openai"],"primary_backend":"openai"}'
```

Cette commande crée la configuration locale `.pipelex/` et sélectionne OpenAI.
Elle ne contient aucune clé et ne demande pas d'activer la Gateway.
`DO_NOT_TRACK=1` désactive la télémétrie Pipelex pour les commandes de ce terminal.

Ne pas relancer `init` sur une configuration déjà personnalisée sans la sauvegarder :
les commandes d'initialisation peuvent remplacer ses fichiers.
[Initialisation officielle](https://docs.pipelex.com/latest/tools/cli/init/).

Ouvrir dans VS Code les fichiers de configuration générés et contrôler :

Dans `.pipelex/inference/backends.toml`, la section OpenAI doit être activée :

```toml
[openai]
enabled = true
api_key = "${OPENAI_API_KEY}"
```

La section `pipelex_gateway` doit être désactivée. Dans
`.pipelex/inference/routing_profiles.toml`, le profil actif doit être :

```toml
active = "all_openai"
```

Garder les autres champs générés : ces extraits servent à contrôler les valeurs,
pas à remplacer les fichiers complets. D'éventuels fichiers personnels
`backends_override.toml` et `routing_profiles_override.toml` peuvent modifier les
valeurs effectives ; `pipelex show backends` aide à les inspecter.
[Configuration et routage](https://docs.pipelex.com/latest/configuration/config-technical/inference-backend-config/).

Dans `.pipelex/pipelex.toml`, les relances automatiques sont désactivées pour
ce prototype. Ces réglages sont déjà appliqués sur ce Mac ; sur un autre poste,
modifier les sections existantes sans les dupliquer :

```toml
[inference]
transport_max_retries = 0

[inference.model_deck]
is_model_fallback_enabled = false

[inference.llm]
schema_reask_max_attempts = 1
```

**4. Valider l'exemple sans appeler OpenAI**

Un petit exemple est fourni dans
[`exemples_pipelex/verification.mthds`](exemples_pipelex/verification.mthds).
Il ne recherche aucune information politique. Il demande une courte réponse texte
avec `gpt-4o-mini`, modèle présent dans le catalogue OpenAI du paquet 0.67.0.
Ce modèle est choisi pour le diagnostic, pas comme choix définitif pour l'agent.
[Modèle OpenAI](https://developers.openai.com/api/docs/models/gpt-4o-mini).

Lancer :

```bash
pipelex validate bundle docs/exemples_pipelex/verification.mthds
pipelex run bundle docs/exemples_pipelex/verification.mthds --dry-run --no-save-main-stuff --no-save-working-memory --no-graph
```

La première commande contrôle la définition du parcours. La seconde simule son
exécution sans appeler les fournisseurs IA. Elles ne prouvent ni que la clé est
valide, ni que des crédits sont disponibles. Le texte éventuellement produit en
simulation est factice. [Validation](https://docs.pipelex.com/latest/tools/cli/validate/),
[exécution et simulation](https://docs.pipelex.com/latest/tools/cli/run/).

**5. Renseigner la clé OpenAI localement**

Ouvrir manuellement le `.env` existant dans VS Code. Compléter la ligne
`OPENAI_API_KEY` avec la clé de l'organisation disposant des crédits du hackathon.
Si elle est déjà renseignée correctement, la conserver.

- Ne pas recopier `.env.example` sur `.env` : cela écraserait sa configuration.
- Ne pas ajouter une deuxième ligne `OPENAI_API_KEY`.
- Ne pas mettre la valeur de la clé dans les fichiers TOML, les commandes du
  terminal, le dépôt ou un message.
- `PIPELEX_API_KEY` et `PIPELEX_GATEWAY_API_KEY` ne sont pas nécessaires à ce parcours.

Pipelex 0.67.0 charge les variables depuis `.env` à partir du répertoire courant.
Les valeurs du fichier du projet prennent priorité sur celles déjà présentes
dans le processus ou dans la configuration globale Pipelex. Exécuter les
commandes depuis la racine du projet. Ne jamais afficher la variable pour la vérifier.
[Configuration des clés](https://docs.pipelex.com/latest/get-started/configure-ai-providers/).

Vérifier dans la facturation de l'organisation OpenAI que les crédits partenaires
sont disponibles. L'existence d'une clé ne prouve pas le solde.

**6. Effectuer le premier essai réel, lorsque les crédits sont confirmés**

Cette étape transmet le petit prompt de diagnostic à OpenAI et consomme des crédits.
Si un assistant doit l'exécuter, lui donner une autorisation explicite pour cet essai,
comme le demande le fichier `AGENTS.md` du projet.

```bash
pipelex run bundle docs/exemples_pipelex/verification.mthds --no-save-main-stuff --no-save-working-memory --no-graph
```

Le résultat attendu est une courte réponse indiquant que la connexion fonctionne.
L'exemple possède une seule étape LLM et borne sa sortie à 64 tokens. Les relances
du transport, les nouvelles tentatives de structuration et le remplacement du
modèle en cas d'échec sont désactivés dans la configuration du projet. Cela ne
constitue pas un plafond monétaire. En cas d'erreur, ne pas répéter la commande en boucle.
[Paramètres PipeLLM](https://docs.pipelex.com/latest/building-methods/pipes/pipe-operators/PipeLLM/).

Ce succès confirme seulement l'exécution d'un petit appel texte via Pipelex.
Le parcours web et son branchement Streamlit ont depuis été développés et testés
hors ligne ; leur validation réelle reste distincte de ce diagnostic.

**7. Passer du diagnostic à l'agent citoyen**

Le branchement désormais implémenté suit ces étapes :

1. Créer le parcours qui prépare les recherches et rassemble les sources.
2. Appeler la recherche web OpenAI depuis une fonction Python intégrée à Pipelex.
3. Faire décider au LLM si des preuves manquent, avec au plus une recherche
   complémentaire pour le premier MVP.
4. Produire le JSON du projet et appeler la validation existante.
5. Brancher le mode Pipelex dans le service et l'interface de l'équipe.

Voir [BRANCHEMENT_STREAMLIT.md](BRANCHEMENT_STREAMLIT.md) pour les fichiers,
les modèles choisis, les limites d'appels et les résultats des tests hors ligne.

Le `PipeSearch` standard utilise Linkup ou la Gateway ; notre choix d'utiliser les
crédits OpenAI implique une intégration spécifique de sa recherche web.
[Opérateurs Pipelex](https://docs.pipelex.com/latest/features/pipe-operators/),
[recherche web OpenAI](https://developers.openai.com/api/docs/guides/tools-web-search).

Répartition : A prend les dépendances et `src/`, B le branchement de l'interface,
C les instructions et les cas documentaires. Le changement du contrat partagé
reste à coordonner à trois, selon `AGENTS.md`. Une installation réussie n'ajoute
pas automatiquement le mode Pipelex à `app.py`.

**En cas d'erreur**

| Symptôme | Vérification utile |
|---|---|
| `pipelex: command not found` | Réactiver `xia-hackathon`, puis vérifier l'installation avec `python -m pip show pipelex`. |
| Conflit autour de `requests` | Vérifier que la ligne a bien été remplacée, et non ajoutée en double. |
| Demande d'une clé Gateway ou de ses conditions | Contrôler le profil `all_openai`, les backends activés et les éventuels overrides. |
| Modèle introuvable | Vérifier Pipelex 0.67.0 et le nom `gpt-4o-mini` dans l'exemple. |
| `PipelexSetupError` avec `OPENAI_API_KEY` manquante | Renseigner cette variable dans le `.env` du projet, puis lancer depuis la racine. Aucun appel OpenAI n'a encore été effectué. |
| Erreur 401 | Vérifier manuellement la clé, son organisation et sa validité. |
| Erreur 429 | Lire le type d'erreur : quota, solde ou débit. Ne pas acheter de crédits pour contourner le blocage. |
| Timeout | Ne pas supposer que l'exécution distante est annulée et ne pas relancer immédiatement. |
| Streamlit affiche encore Dust | Relancer `app.py` depuis le bon dossier pour charger l'interface de l'équipe et son mode Pipelex. |

Pour demander de l'aide, transmettre uniquement le message d'erreur expurgé des
secrets, la version Python et la version Pipelex.

**Ce qui a été vérifié et exécuté**

- Métadonnées et configuration publiques du paquet Pipelex 0.67.0 consultées.
- Simulation avec les dépendances actuelles : échec à cause de `requests==2.32.5`.
- Simulation avec `requests==2.33.0` et `pipelex[cli]==0.67.0` : résolution réussie.
- `python -m pip install -r requirements.txt` : installation effectuée avec succès
  dans l'environnement Conda de l'équipe.
- `python -m pip check` : aucune dépendance incompatible.
- `python -m pytest -q` : 41 tests réussis après installation.
- `pipelex-agent init` : configuration locale `.pipelex/` créée, profil `all_openai`,
  OpenAI comme seul fournisseur distant activé. Le backend `internal`, sans IA
  distante, reste disponible.
- `private` ajouté aux exclusions de scan dans `.pipelex/pipelex.toml`, en plus
  des exclusions de `.venv`, `.git` et des caches fournies par Pipelex.
- `pipelex validate bundle docs/exemples_pipelex/verification.mthds` : réussi.
- `pipelex run bundle docs/exemples_pipelex/verification.mthds --dry-run
  --no-save-main-stuff --no-save-working-memory --no-graph` : réussi.
- Pour ces commandes hors ligne, un lanceur temporaire a désactivé le chargement dotenv
  (`PYTHON_DOTENV_DISABLED=1`), désactivé la télémétrie (`DO_NOT_TRACK=1`), retiré
  les variables de clés pertinentes de son processus et bloqué par un contrôle
  Python les ouvertures de fichiers de secrets et les connexions réseau.
- Relances automatiques désactivées dans `.pipelex/pipelex.toml` ; validation
  de l'exemple réussie à nouveau après cette modification.
- Test réel autorisé par l'utilisateur : commande `pipelex run bundle
  docs/exemples_pipelex/verification.mthds --no-save-main-stuff
  --no-save-working-memory --no-graph` lancée via un diagnostic temporaire qui
  capture les journaux sans afficher les identifiants. Les premiers démarrages
  échouaient avant l'inférence, faute de variable `OPENAI_API_KEY` disponible.
  Après correction locale de cette configuration par l'utilisateur, l'exécution
  a réussi.
- Les traces d'usage du 27 septembre 2026 à 11:27:09 et 11:28:05 UTC, dans
  `.pipelex/traces/`, confirment **deux appels réels** à `gpt-4o-mini`, chacun
  avec 25 tokens d'entrée et 10 de sortie, soit **70 tokens au total**. Le
  compteur temporaire affichait à tort zéro : il interceptait `httpx`, tandis
  que le SDK installé utilise `httpx2` et l'API Responses. Le second diagnostic
  a donc produit un appel supplémentaire involontaire. Aucun autre appel réel
  n'a été effectué après ce constat.
- Le diagnostic temporaire a été corrigé pour intercepter les deux transports,
  traiter Responses, contrôler le modèle et la limite de sortie, et refuser un
  succès sans réponse HTTP observée. La configuration Pipelex conserve les
  relances et changements automatiques de modèle désactivés.
- Vérification de la correction hors ligne : le SDK OpenAI installé a été
  exécuté avec un `httpx2.MockTransport`. La première réponse simulée a été
  comptée et lue correctement ; la seconde requête a été bloquée avant le
  transport. Ce contrôle n'a utilisé ni le réseau ni les identifiants réels.
- Aucun contenu de `.env` ni aucune valeur de clé n'a été affiché. La
  consommation éventuelle de Codex dépend séparément de sa connexion.
- L'authentification et un petit parcours texte Pipelex sont vérifiés. Le nouveau
  parcours web et l'intégration Streamlit sont implémentés et vérifiés hors ligne
  uniquement ; leur test réel et la relecture des sources restent à faire.
