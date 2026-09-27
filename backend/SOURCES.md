# Collecte et contrôle des sources

Le backend récupère des pages publiques indiquées par PipeSearch avant de demander
le rapport Pipelex. Il s’agit de lectures HTTP de pages, pas encore d’un connecteur
aux API gouvernementales. Aucune clé gouvernementale n’est nécessaire.

Domaines HTTPS autorisés, avec et sans `www` : `assemblee-nationale.fr`, `senat.fr`,
`legifrance.gouv.fr`. Les redirections sont contrôlées à chaque étape. Les autres
domaines sont refusés sans requête. Les réponses et snippets du moteur ne sont
jamais utilisés comme texte source.

Le corpus contient au plus six résultats, 15 000 caractères par source et 60 000
au total. Une troncature est signalée au modèle et à l’utilisateur. Le contrôle
porte exactement sur les caractères envoyés au modèle. Une citation portant sur
une partie coupée est refusée. Les URL sont dédupliquées dans une recherche.

Chaque téléchargement est limité à 2 Mo, trois redirections, huit secondes par
requête et un budget de collecte de 30 secondes contrôlé entre lectures. Une lecture
en cours peut dépasser ce budget jusqu’à son timeout. Pas de contournement des
restrictions d’accès ni de rendu JavaScript.

HTML : suppression des scripts/styles/en-têtes. PDF : couche texte extraite avec
pypdf dans un processus séparé, huit secondes au plus, 40 pages, 2 Mo de contenu
décompressé par page et 500 000 caractères. Ces seuils ne sont pas une limite dure
de mémoire pendant le décodage. Pas d’OCR ni de validation visuelle. Les citations
ne peuvent pas traverser les pages PDF ; `pdf_page` est le numéro physique dès 1.

`verify_sources(report, fetched_sources=corpus)` vérifie le cache transmis sans
nouvelle lecture réseau. Une URL non collectée reçoit `not_in_corpus`. Les espaces
et la composition Unicode peuvent être normalisés ; mots, nombres et ponctuation
ne le sont pas. Une citation manquante fait refuser tout le rapport dans le parcours
actif. Des pages inaccessibles sont signalées ; un corpus vide produit un rapport
vide honnête sans deuxième appel Pipelex.

Les contrôles retournent URL initiale/finale, date du contrôle, entité, extrait et
statut (`matched`, `matched_whitespace`, `not_found`, `not_in_corpus`, ou erreur de
collecte). L’interface affiche les limites textuelles. Retrouver un extrait ne
prouve pas son interprétation, la date de publication ou l’actualité d’une étape.
Ces points restent à relire ; les résultats ne sont pas certifiés exhaustifs.

La variante `verify_sources(report)` sans cache reste disponible pour les outils
historiques : elle télécharge au plus huit URL et signale les réserves au rapport.
Elle n’est pas utilisée par la nouvelle recherche.

Les tests HTTP automatisés sont simulés. Le nouveau parcours Pipelex complet
n’a pas encore fait l’objet d’un essai réel.

## Contrôle manuel sur une source réelle

Le 27 septembre 2026, le collecteur a récupéré le texte du Sénat
[`ppl24-303.html`](https://www.senat.fr/leg/ppl24-303.html) et son
[`PDF`](https://www.senat.fr/leg/ppl24-303.pdf). L'extrait technique choisi a été
retrouvé en HTML et dans la couche texte de la page physique 12 du PDF, après
normalisation des espaces. Une citation volontairement inventée a été refusée
dans les deux formats. Les quatre vérifications sont conservées localement dans
`data/local/source-smoke-check.json`, ignoré par Git.
Ce contrôle n'a appelé ni Dust ni Pipelex, et n'établit pas le statut actuel du texte.
Il ne constitue pas un test de l'ensemble des sites officiels.
