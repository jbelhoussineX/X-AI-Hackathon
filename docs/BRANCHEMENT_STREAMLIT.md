# Interface de l'équipe et moteur Pipelex local

## Git et interface retenue

`git fetch origin` a récupéré les nouvelles références du dépôt de l'équipe.
`main` pointe sur `980d225` ; `frontend/interface_b.py` était déjà présent et
identique à sa version distante. L'interface existante est réutilisée : styles,
cartes, preuves, export, historique et veilles de session sont conservés.

La branche `origin/feat/pipelex-comparison` pointe sur `4239adf`. Elle apporte
un backend avec Dust et un client de l'API hébergée Pipelex. Ce backend n'a pas
été fusionné dans la migration locale : il exige d'autres accès et son arbre
ne contient pas plusieurs fichiers du socle actuel. Aucun changement de branche
ni push n'a été effectué.

## Lancer

Depuis la racine du projet, sur ce Mac :

```bash
conda activate xia-hackathon
python -m pip install -r requirements.txt
python -m streamlit run app.py --server.address 127.0.0.1 --server.fileWatcherType none
```

Python attendu : `/Users/maison/anaconda3/envs/xia-hackathon/bin/python`.
L'installation Pipelex et sa configuration locale sont décrites dans
[INSTALLATION_PIPELEX.md](INSTALLATION_PIPELEX.md). Ne pas réinitialiser une
configuration existante. La clé `OPENAI_API_KEY` reste dans le `.env` local ;
aucune clé n'est demandée par l'interface ni nécessaire en démonstration.

1. Commencer en **Démonstration · sans IA**. Saisir un sujet et afficher l'exemple,
   qui reste explicitement fictif. Essayer les filtres, l'export et les veilles.
2. Pour une recherche réelle, sélectionner **Pipelex + OpenAI** et confirmer
   l'utilisation des crédits dans le menu. Seul le bouton de recherche ou
   d'actualisation déclenche le service.
3. Lire les sources et les limites avant d'utiliser un résultat. Une erreur
   efface le résultat courant ; aucun exemple fictif ne le remplace.

L'historique et les veilles sont conservés en session uniquement. Pas de SQLite,
de comparaison automatique ni de planification quotidienne dans cette version.

## Chemin d'exécution

```text
app.py → frontend/interface_b.py
       → src.service.search(..., mode="pipelex")
       → src.pipelex_client → processus Python isolé
       → src.pipelex_worker → PipeSequence de recherche_citoyenne/main.mthds
       → actions src/pipelex_steps.py et src/openai_research.py
       → validation du rapport existant → affichage Streamlit
```

Le processus séparé évite de partager l'état global Pipelex entre les sessions
Streamlit. Ses journaux ne sont pas affichés par l'interface. Le parent reçoit
uniquement un rapport JSON contrôlé ou un code d'erreur public.

Le parcours Pipelex possède quatre étapes :

1. Chercher des textes et des preuves avec l'outil web OpenAI.
2. Faire déterminer par un LLM si des dates, statuts ou preuves manquent.
3. Exécuter au plus un complément si la décision structurée le demande.
4. Produire le rapport selon `schemas/report.schema.json` et le contrôler.

La signature `search(topic, start, end, mode)` et l'enveloppe de résultats restent
les mêmes. Les modes historiques `demo` et `dust` restent disponibles dans le
service ; l'interface propose `demo` et le nouveau mode `pipelex`. Le schéma du
rapport et `CONTRACT.md` n'ont pas été modifiés.

## Modèles et limites de consommation

| Étape | Modèle | Limites applicatives |
|---|---|---|
| Recherche initiale et éventuel complément | `gpt-4.1-mini` | 4 000 tokens de sortie par réponse, au plus 3 appels d'outil web par réponse |
| Évaluation des manques | `gpt-4o-mini` | 700 tokens de sortie |
| Rapport final | `gpt-4o-mini` | 6 000 tokens de sortie |

Une recherche réussie comporte 3 ou 4 requêtes de modèle. Le code refuse une
cinquième requête. Le SDK utilise `max_retries=0` et ne suit pas les redirections.
Les appels de recherche imposent l'outil web ; un récit sans appel d'outil
authentifié dans la réponse ne suffit pas. Les domaines sont limités à
`assemblee-nationale.fr`, `senat.fr`, `legifrance.gouv.fr` et `vie-publique.fr`.

Ces limites ne fixent pas un montant en euros : les tokens d'entrée et les outils
web comptent aussi. Le client attend au plus 70 secondes par appel ; le processus
local est limité à 240 secondes. Un arrêt local ne garantit pas l'annulation du
traitement distant. Ne pas relancer immédiatement après un timeout.

Les réponses OpenAI demandent `store=False`. Cela ne constitue pas une promesse
sur l'ensemble de la conservation technique du fournisseur. Le sujet et le
corpus sont transmis à OpenAI ; aucun compte Pipelex hébergé n'est utilisé.

Référence API consultée : [recherche web OpenAI](https://developers.openai.com/api/docs/guides/tools-web-search).
Le SDK OpenAI 3.3.0 est fixé dans les dépendances et utilise `httpx2` ; les tests
simulent ce transport réel du SDK.

## Contrôles et limites documentaires

La structure, les dates, les relations entre identifiants et la présence des URL
de preuve dans les sources renvoyées par l'outil sont contrôlées. Une date connue
hors période entraîne le refus du rapport ; une date inconnue est signalée.
Une URL présente dans la trace de recherche n'atteste ni de l'exactitude d'une
affirmation, ni de la fidélité mot à mot d'un extrait. Relire les pages avant la
démo. Le corpus limité peut exclure des organismes ou associations pertinents.

## Validation réellement effectuée

```bash
PYTHON_DOTENV_DISABLED=1 DO_NOT_TRACK=1 python -m pytest -q
```

60 tests réussis : contrôles historiques, vrai moteur Pipelex avec réponses HTTP
simulées (avec et sans complément), refus des sources non consultées, limite
d'appels, erreurs sans repli, absence d'appel pendant la navigation Streamlit,
recherche sur clic et absence de répétition au rafraîchissement.

Les tests du moteur bloquent les connexions réseau et emploient un identifiant
factice. Aucun test de ce branchement n'a utilisé les crédits API. Le nouveau
parcours web réel reste à vérifier avec autorisation ; le diagnostic texte
précédent ne le remplace pas.
