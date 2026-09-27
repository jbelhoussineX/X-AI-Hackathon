# Plan d'équipe — 26 et 27 septembre 2026

## Décision de départ
Application locale Python/Streamlit, un agent Dust avec recherche web, Codex sur les trois ordinateurs.
Première version : textes parlementaires français, étape de procédure sourcée, pages de contact publiques.
Pas de compte utilisateur, d'hébergement, d'envoi automatique, de classement politique ou de reconnaissance vocale.
Le nom de l’application est « Sed Lex ».

## Responsabilités
| Personne | Responsabilité | Livrable observable |
|---|---|---|
| A | Connexion Dust, modules Python, intégration Git | Un appel réel qui produit un rapport valide ; branche main lançable |
| B | Interface Streamlit | Formulaire, fiches, sources, contacts et erreurs lisibles |
| C | Agent Dust, sources, tests manuels, vidéo | Instructions testées ; cas réels vérifiés ; démonstration |

A et C travaillent ensemble pour le premier appel réel. C n'a pas à partager de clé personnelle :
utiliser un accès autorisé au même espace ou recréer la configuration dans l'espace autorisé de A.
Les changements de schéma se font avec l'accord de tous. A est le seul intégrateur de main.

## Aujourd'hui — 30 à 60 minutes utiles
1. Désigner A/B/C, choisir un sujet provisoire de test, confirmer le canal de dépôt.
2. A crée/réutilise le dépôt partagé, invite les autres et y place le contenu du kit, fichiers cachés inclus.
3. A commit/push le socle ; B et C récupèrent cette version avant de créer leurs branches.
4. Tous ouvrent le même projet dans VS Code, installent Codex officiel et lisent AGENTS.md.
5. C vérifie la création d'agent, Web Search & Browse et le format structuré ; A vérifie le droit API.
6. Vérifier que les accès restent dans les crédits offerts, sans carte ou recharge payante.

## Demain — exemple si vous commencez vers 9 h
| Période | Objectif commun |
|---|---|
| 09 h–10 h | Dépendances, mode fictif, configuration Dust et diagnostic API |
| 10 h–12 h | A connecte ; B améliore l'interface ; C teste l'agent et les sources |
| 12 h | Première recherche réelle affichée dans l'application |
| 13 h–15 h | Corriger les erreurs factuelles/techniques sur plusieurs cas |
| 15 h–17 h | Améliorer uniquement ce qui sert le parcours de démonstration |
| 17 h | Gel des fonctionnalités ; corrections seulement |
| 17 h–20 h | Test depuis un clone propre, README, courte description, vidéo |
| 20 h–21 h 30 | Relecture et dépôt avec marge |

L'échéance du règlement est le 27 septembre à 23 h 59, pas après minuit.
Les heures sont un planning proposé, pas une estimation garantie de développement.
Si vous commencez plus tard : réduire le produit, pas supprimer la vérification et le dépôt.

## Cycle de travail Git simplifié
- Départ : main à jour puis branche a-integration, b-interface ou c-agent-tests.
- Petites modifications avec Codex dans son périmètre.
- Contrôle des fichiers changés ; tests hors ligne ; commit puis push de sa branche.
- Pull request vers main, relue et fusionnée par A après test.
- Tous repassent sur main, Fetch/Pull origin, puis créent une nouvelle branche courte pour la tâche suivante.
- Pas de force-push, reset ou suppression de .git pour résoudre un blocage.

## Points de contrôle
- Une interface fictive qui s'affiche ne démontre pas une recherche réelle.
- Un diagnostic API réussi ne démontre pas la qualité des sources.
- Un JSON valide ne démontre pas la justesse d'un statut ou d'un extrait.
- Une réponse vide honnête est préférable à un document inventé.
- Aucune dépense supplémentaire ne doit être déclenchée pour débloquer le prototype.

## Solutions de repli
API bloquée : vérifier permissions/identifiants avec l'organisateur, ne pas changer toute l'architecture.
Si aucun accès API autorisé n'est disponible à temps, démontrer l'agent réellement fonctionnel dans Dust
et indiquer explicitement que l'interface Python n'est pas connectée ; conserver ses instructions,
schémas et tests dans le dépôt. Ne pas faire passer une fixture pour une recherche.
Recherche trop large : limiter à deux documents, un interlocuteur et un thème précis.
Temps dépassé : retirer les options, pas les preuves et la vérification humaine.
