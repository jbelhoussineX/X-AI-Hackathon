# Données récentes et synthèse — 27 septembre 2026

Dans Recherche, sélectionner des sujets ou utiliser **Autres sujets**, choisir la période (période du profil, 1 à 12 mois ou 1 à 90 jours),
puis cliquer **Rechercher**. Le clic lance le [parcours agentique](ANALYSE_AGENTIQUE.md),
qui sélectionne les notices selon leur sens, évalue, complète si utile et résume avec les crédits fournisseur.
L'interface ne propose plus de mode sans IA ni de génération séparée après la collecte.
Les résultats précédents et leur synthèse sont effacés à chaque
nouvelle collecte pour ne pas afficher une ancienne réponse sous un nouveau sujet.

## Sources utilisées

| Nature | Source | Date retenue |
|---|---|---|
| Étape législative | Dossiers JSON Assemblée, 17e législature | `dateActe`, même si dépôt ancien |
| Dépôt / promulgation | Export CSV DOSLEG du Sénat | Date initiale ou date de promulgation |
| Publication parlementaire | RSS textes, rapports et logement du Sénat | Mise en ligne déclarée par le flux |
| Actualité institutionnelle | RSS communiqués de presse du Sénat | Mise en ligne, pas nécessairement date de l'événement décrit |
| Amendement | Liste des publications Assemblée et fichier XML lu | Publication / republication, sans inférer adoption |
| Débat / intervention | Comptes rendus des séances de l'Assemblée | Date de séance, confirmée dans la page |
| Débat / intervention | Dernier compte rendu analytique du Sénat | Date de séance ; résumé institutionnel, pas verbatim oral |

Les sources sont officielles. Elles ne couvrent pas toute l'actualité politique,
les médias, tous les discours publics, ni les réunions de commission. Vie-publique
n'est pas raccordé à ce parcours. Aucune API Légifrance/PISTE n'est appelée.

Références des producteurs :
- https://data.assemblee-nationale.fr/foire-aux-questions
- https://www.assemblee-nationale.fr/dyn/17/comptes-rendus/seance
- https://www.senat.fr/seances/comptes-rendus.html
- https://www.senat.fr/flux-rss.html

## Bornes et fraîcheur

La fenêtre est inclusive et porte sur la date explicitement affichée avec sa nature.
La date de récupération ne remplace jamais une date de publication ou de séance.
Dates inconnues et futures exclues. Le bloc affiche la dernière séance repérée dans
chaque index : un index ancien ou vide ne prouve pas l'absence de débats.

Au plus 120 notices candidates, réparties entre les fournisseurs. L’IA sélectionne
jusqu’à six événements, puis éventuellement six autres dans les notices restantes.
La synthèse finale retient au plus six événements ; les répétitions et les étapes
d’un même dossier sont regroupées à l’affichage.
Première page de chaque index de débats, six séances
au plus par chambre, 25 secondes de budget réseau par chambre, 4 Mo par page.
Les RSS ne garantissent pas une couverture historique complète. Amendements :
listes d'aujourd'hui et d'hier, 12 fichiers au plus. Les pannes et troncatures sont
signalées, sans recherche web de remplacement et sans contenu fictif.

## Synthèse Pipelex

La synthèse fait désormais partie du parcours lancé par **Rechercher**.
`ENABLE_PIPELEX_CALLS=true` est requis. `PIPELEX_EXECUTION_MODE=hosted` utilise
l'API Pipelex ; `local` exécute les étapes PipeLLM avec OpenAI. Aucun changement
automatique de fournisseur. Le modèle est `gpt-4o-mini`.

L’IA choisit jusqu’à six événements parmi 120 notices datées, sans filtre lexical.
Leurs passages sont ensuite préparés pour l’évaluation.
Les pages liées sont relues si le collecteur ne dispose pas déjà du texte.
Trois passages par événement au maximum, 4 000 caractères chacun. Une source
illisible ou sans passage pertinent n'alimente pas la synthèse. Sans corpus final
exploitable, la synthèse n'est pas appelée ; préparation et évaluation peuvent
avoir déjà consommé des crédits. Voir les budgets et le complément dans
[le guide agentique](ANALYSE_AGENTIQUE.md).

La méthode `recent_agent.summarize` sélectionne des identifiants de passage et
citation. Les citations sont découpées par le code dans les passages collectés.
Les extraits ne sont plus affichés, mais leur présence dans le corpus reste
contrôlée. Le code refuse les identifiants inconnus et citations absentes du
passage. Les répétitions d'un événement sont retirées après vérification.
Liens, titres, catégories et dates affichés viennent du collecteur.
La présence d'un extrait ne certifie pas la fidélité de la synthèse : relecture
humaine nécessaire. Pas de relance automatique ; un délai local ne garantit pas
l'annulation d'une génération distante. La méthode historique
`recent_brief.summarize` reste disponible dans le backend, hors interface.

Le contrat législatif v1 reste inchangé. La synthèse récente est un résultat séparé,
sans export JSON dans l’interface. L'historique conserve désormais sept jours
de recherches, avec l'analyse agentique ou son erreur partielle. Aucune tâche programmée : l'utilisateur actualise au clic.

## Validation

Les étapes actives de `methods/recent_agent/main.mthds` sont testées avec le moteur
Pipelex et un transport fournisseur simulé. Les types générés de la synthèse
historique restent utilisés pour le contrôle des citations. Contrôles hors ligne :

```powershell
.\.venv\Scripts\python.exe scripts/codegen_check.py backend/generated/recent_brief
.\.venv\Scripts\python.exe -m pytest -q
```

Tests des dates, domaines, contenus réellement lus, citations inventées, références
inconnues, corpus vide, péremption, consentement et absence de répétition sur rerender.
Le graphe Pipelex local est exécuté avec génération simulée ; l'appel hébergé est
simulé. Aucun essai IA payant de cette nouvelle synthèse n'a été lancé.

Contrôle réseau public : les deux index de débats ont été lus. Sur une fenêtre de
contrôle historique du 22 juin au 21 juillet 2026, trois comptes rendus contenaient
des passages liés au logement, dont un au Sénat. Ces résultats historiques ne sont
pas présentés comme des actualités des 30 derniers jours.

Une plage élargie ne garantit pas une collecte exhaustive sur toute cette durée :
les limites des flux et du nombre de séances examinées restent affichées.

État de livraison : prototype, génération réelle à relire avant la démonstration.
Les tests automatisés utilisent des réponses IA simulées ; ils ne certifient pas
la fidélité des résumés politiques. Le mode de remise recommandé est un dépôt accessible avec instructions de test local.
