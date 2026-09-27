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

1. Télécharger les inventaires Sénat/Assemblée et les pages officielles (mode par défaut).
2. Faire déterminer par un LLM si des dates, statuts ou preuves manquent.
3. Exécuter au plus une collecte complémentaire avec un autre mot-clé si le LLM le décide.
4. Produire le rapport selon `schemas/report.schema.json` et le contrôler.

La signature `search(topic, start, end, mode)` et l'enveloppe de résultats restent
les mêmes. Les modes historiques `demo` et `dust` restent disponibles dans le
service ; l'interface propose `demo` et le nouveau mode `pipelex`. Le schéma du
rapport et `CONTRACT.md` n'ont pas été modifiés.

## Modèles et limites de consommation

| Étape | Modèle | Limites applicatives |
|---|---|---|
| Collecte officielle initiale et complément | Aucun modèle | 60 000 caractères pour le corpus réuni |
| Recherche en mode `web` seulement | `gpt-5-mini`, raisonnement `low` | 4 000 tokens de sortie par réponse ; au plus 3 appels d’outil web |
| Évaluation des manques | `gpt-4o-mini` | 700 tokens de sortie |
| Rapport final | `gpt-4o-mini` | 6 000 tokens de sortie |

Le mode officiel comporte deux requêtes de modèle, ou zéro si le corpus initial
est vide. Le mode `web` comporte 3 ou 4 requêtes. Le code refuse une
cinquième requête. Le SDK utilise `max_retries=0` et ne suit pas les redirections.
En mode `web`, les appels de recherche imposent l'outil web ; un récit sans appel d'outil
authentifié dans la réponse ne suffit pas. Les domaines sont limités à
`assemblee-nationale.fr`, `senat.fr`, `legifrance.gouv.fr` et `vie-publique.fr`.

Ces limites ne fixent pas un montant en euros : les tokens d'entrée et les outils
web comptent aussi. Le client attend au plus 70 secondes par appel ; le processus
local est limité à 420 secondes pour laisser place aux téléchargements officiels. Un arrêt local ne garantit pas l'annulation du
traitement distant. Ne pas relancer immédiatement après un timeout.

Les réponses OpenAI demandent `store=False`. Cela ne constitue pas une promesse
sur l'ensemble de la conservation technique du fournisseur. Le sujet et le
corpus sont transmis à OpenAI ; aucun compte Pipelex hébergé n'est utilisé.

Référence API consultée : [recherche web OpenAI](https://developers.openai.com/api/docs/guides/tools-web-search).
Le réglage `low` suit la [documentation GPT-5](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5) ;
le niveau `minimal` n'est pas compatible avec la recherche web.
Le SDK OpenAI 3.3.0 est fixé dans les dépendances et utilise `httpx2` ; les tests
simulent ce transport réel du SDK.

## Contrôles et limites documentaires

La structure, les dates, les relations entre identifiants et la présence des URL
de preuve dans les sources renvoyées par l'outil sont contrôlées. Une date connue
hors période entraîne le refus du rapport ; une date inconnue est signalée.
En mode officiel, chaque extrait est recherché dans le texte collecté, sans
nouveau téléchargement lors de la vérification. En mode web, une URL présente dans la trace de recherche n'atteste ni de l'exactitude d'une
affirmation, ni de la fidélité mot à mot d'un extrait. Relire les pages avant la
démo. Le corpus limité peut exclure des organismes ou associations pertinents.

## Validation réellement effectuée

```bash
PYTHON_DOTENV_DISABLED=1 DO_NOT_TRACK=1 python -m pytest -q
```

153 tests réussis : contrôles historiques, vrai moteur Pipelex avec réponses HTTP
simulées (avec et sans complément), refus des sources non consultées, limite
d'appels, erreurs sans repli, absence d'appel pendant la navigation Streamlit,
recherche sur clic et absence de répétition au rafraîchissement.

Les tests du moteur bloquent les connexions réseau et emploient un identifiant
factice. Cette suite hors ligne n'utilise pas les crédits API. Le mode web a
fonctionné lors d'un essai utilisateur ; le nouveau parcours officiel reste
à vérifier en réel. Les diagnostics ci-dessous documentent les corrections précédentes.

## Diagnostic des échecs

Un échec affiche maintenant un code contrôlé et, lorsqu'ils sont disponibles,
l'étape, le statut HTTP, le type d'erreur, le code API et le paramètre concerné.
Seules des valeurs techniques prédéfinies sont autorisées ; les messages bruts,
les en-têtes et la clé ne sont jamais affichés. Aucun nouvel essai automatique.

- HTTP 400/422 : requête, paramètre ou schéma refusé ; transmettre le diagnostic
  avant de modifier au hasard le modèle ou les limites.
- HTTP 404 : modèle introuvable ou inaccessible pour ce projet.
- HTTP 429 : vérifier quota ou débit.
- HTTP 5xx : erreur du service distant.
- Une erreur locale est distinguée d'un refus OpenAI.

Les champs facultatifs `sources` et `annotations` renvoyés à `null` par le SDK
sont désormais traités comme des listes vides. Les URL réellement présentes
restent soumises aux mêmes contrôles ; aucune source n'est inventée.

Après ce correctif, **66 tests hors ligne réussissent**, dont les erreurs API
simulées à travers le véritable moteur Pipelex, l'absence de relance et le
filtrage des détails sensibles.

Le 27 septembre 2026, un diagnostic réel autorisé a envoyé une seule requête
de recherche avec `gpt-4.1-mini`, sans relance : HTTP 400, `BadRequestError`,
paramètre `tools`. Le refus indique une incompatibilité avec ce modèle pour
la requête envoyée. La recherche a été passée à `gpt-5-mini` avec un effort
`low`, sans augmenter les limites d'appels ou de sortie. Aucun second appel
réel n'a été effectué : la compatibilité effective du nouveau modèle avec le
compte et la réussite documentaire restent à vérifier. Aucun décompte de
tokens n'a été reçu pour la réponse HTTP 400 ; son coût n'est pas confirmé.

### Rapport rejeté à l'étape `rediger`

Un essai utilisateur a ensuite atteint la rédaction avec le nouveau modèle,
mais le rapport a été rejeté. L'ancien message ne conservait pas la règle qui
avait échoué ; il ne permet pas de retrouver la cause de cet essai.

Le diagnostic transmet maintenant un motif issu d'une liste fermée : schéma,
date invalide, publication hors période, preuve manquante, référence de contact,
réponse tronquée à la limite de tokens, refus du modèle, etc. Aucun extrait du
rapport, message brut du fournisseur ou secret n'est affiché ni enregistré.
Les consignes de rédaction précisent les dates partielles, le filtrage des
publications et les relations entre preuves, statuts et contacts.

Les contrôles du contrat sont inchangés ; aucune correction de fait ni suppression
silencieuse n'est effectuée par le validateur. Les limites de consommation restent
identiques et aucun appel supplémentaire de réparation n'est ajouté.

Les **153 tests hors ligne** incluent les échecs simulés de rédaction jusqu'au
message public, sans relance et sans fuite du contenu brut. Pour contrôler depuis
Streamlit, utiliser le mode Pipelex et lancer volontairement une recherche réelle
(consomme des crédits), puis relever le champ « Motif » en cas de refus. Cette
dernière correction n'a pas été testée avec un appel réel.

### Champs obligatoires vides

Le schéma de génération précédent acceptait des chaînes vides pour des champs
que le validateur local exigeait déjà non vides. Une copie du schéma envoyée
uniquement à OpenAI applique désormais `pattern: "\\S"` à `topic`, `scope`,
`documents.id/title/summary` et `contacts.name/role/relation`. Le schéma partagé
et les critères du validateur restent inchangés. Cette contrainte est documentée
dans les [sorties structurées OpenAI](https://developers.openai.com/api/docs/guides/structured-outputs).

Les consignes demandent d'omettre les documents ou interlocuteurs insuffisamment
documentés en expliquant l'omission, sans inventer de contenu. Aucun remplissage
automatique des champs textuels n'est ajouté. Un rejet résiduel
indique le nom contrôlé du champ (par exemple `champ=contacts.role`), sans sa valeur.
Les tests couvrent les huit champs, les chaînes vides ou composées d'espaces,
les valeurs null autorisées et les rapports sans résultat. Aucun appel API réel
n'a été effectué pour valider ce changement.

Le format de génération applique aussi `maxItems: 4` à `documents` et
`maxItems: 3` à `contacts`. Ces limites existaient déjà dans le validateur ;
elles sont désormais partagées par le code de génération pour éviter cette
divergence. Elles portent sur tout le rapport, complément compris. Les consignes
demandent de signaler une sélection partielle si davantage de résultats existent.
Aucun résultat surnuméraire n'est supprimé silencieusement après génération.
Les tests vérifient les limites exactes, leur dépassement et la conservation du
contrat partagé. L'acceptation de ces contraintes par l'API n'a pas été testée
avec une requête réelle lors de ce correctif.

### Complément tronqué

Si seul le complément facultatif atteint `max_output_tokens`, le parcours utilise
le corpus initial déjà obtenu et ajoute une limite explicite au rapport. Le texte
et les sources de la réponse partielle sont écartés. La rédaction doit conserver
les incertitudes ; ses validations habituelles restent actives. Aucun nouvel essai
de recherche ni augmentation du budget n'est effectué (au plus quatre requêtes).
Le complément reçoit aussi une consigne de recherche ciblée sur le manque indiqué.

Une troncature de la collecte initiale ou du rapport, un timeout, un filtre du
fournisseur ou toute autre erreur continue d'arrêter le parcours. Ce comportement
a été testé avec le moteur Pipelex et des réponses HTTP simulées, sans appel réel.

Le travail de collecte directe de l'équipe est maintenant intégré : voir
[le collecteur officiel](../backend/data_sources/README.md). La
[revue initiale](REVUE_SOURCES_OFFICIELLES.md) conserve les constats avant intégration.

### Page de contact sans preuve dédiée

Après contrôle de la structure JSON, la préparation du rapport remplace uniquement
une URL HTTPS publique de contact sans preuve `contact` portant exactement sur
cette URL par `null`. Elle ajoute une limite explicite identifiant le numéro de
l'interlocuteur. Le document, l'interlocuteur, ses références et ses preuves ne
sont ni supprimés ni réécrits ; aucune autre URL n'est substituée.

Le validateur partagé conserve toutes ses règles. Une preuve de relation ou de
contenu manquante, un extrait vide, une URL non publique ou une preuve absente des
sources consultées fait toujours échouer le rapport. Une preuve dédiée existante
ne garantit pas à elle seule l'exactitude factuelle du contact.

Les tests couvrent le parcours complet avec et sans complément, la conservation
des liens étayés, l'omission signalée du lien sans preuve et le refus des autres
anomalies. Aucun appel IA supplémentaire ni test API réel n'a été effectué.
