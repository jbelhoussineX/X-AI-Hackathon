# Données récentes et synthèse — 27 septembre 2026

Dans Recherche, saisir un sujet dans **Actualités récentes**, choisir la période (3 mois calendaires par défaut, 1 à 12 mois ou 1 à 90 jours),
puis cliquer **Consulter les actualités officielles**. La collecte se fait au clic,
sans clé ni IA. Les résultats précédents et leur synthèse sont effacés à chaque
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

Au plus 20 événements affichés. Première page de chaque index de débats, six séances
au plus par chambre, 25 secondes de budget réseau par chambre, 4 Mo par page.
Les RSS ne garantissent pas une couverture historique complète. Amendements :
listes d'aujourd'hui et d'hier, 12 fichiers au plus. Les pannes et troncatures sont
signalées, sans recherche web de remplacement et sans contenu fictif.

## Synthèse Pipelex

Après collecte, cocher l'autorisation de crédits puis cliquer
**Synthétiser les nouveautés avec Pipelex**. `ENABLE_PIPELEX_CALLS=true` est requis.
`PIPELEX_EXECUTION_MODE=hosted` utilise l'API Pipelex ; `local` exécute la même
méthode PipeLLM avec le moteur local, configuré pour OpenAI. Aucun changement
automatique de fournisseur. La méthode demande `gpt-4o-mini`.

Six premiers événements affichés au maximum. Les pages liées sont relues si le
collecteur ne dispose pas déjà du texte (débat/amendement). Trois passages par
événement au maximum, 4 000 caractères chacun. Une source illisible ou sans passage
pertinent n'alimente pas la synthèse. Un corpus vide ne déclenche aucun appel IA.
Une collecte de plus d'une heure doit être actualisée avant génération.

Une méthode, `recent_brief.summarize`, produit des résumés avec identifiants de
passage et de citation. Les citations sont découpées par le code dans les passages
collectés ; le modèle sélectionne un identifiant et ne recopie aucun extrait.
Le texte affiché provient directement du corpus, ce qui évite les erreurs de recopie. Le code refuse les identifiants inconnus, les citations absentes
du passage. Les répétitions du même événement sont retirées après vérification,
avec un compteur visible ; la première synthèse vérifiée est conservée. Liens, catégories et dates affichés viennent
du collecteur, pas du modèle. La présence d'un extrait ne certifie pas la fidélité
de la synthèse : relecture humaine nécessaire. Pas de relance automatique ; un délai
local ne garantit pas l'annulation d'une génération distante.

Le contrat législatif v1 reste inchangé. La synthèse récente est un résultat séparé,
exportable en JSON depuis le même bloc. Pas de sauvegarde durable ni de tâche
programmée ajoutée : l'utilisateur actualise au clic.

## Validation

Méthode validée par Pipelex, types `python-pydantic` générés dans
`backend/generated/recent_brief/`. Contrôle de dérive :

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

État de livraison : prototype, génération réelle à revalider après ces correctifs.
Les tests automatisés utilisent des réponses IA simulées ; ils ne certifient pas
la fidélité des résumés politiques. Aucun push sur main ni déploiement public.
