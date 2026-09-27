# Sed Lex — fiche de remise X-IA

**Hackathon :** Rise of Agents X

**Équipe :** Arseniy, Jihane et Ryane

**Échéance du règlement fourni :** 27 septembre 2026 à 23 h 59

## Description courte à copier

> Sed Lex est un assistant de recherche documentaire citoyenne sur la France.
> À partir de sujets et d’une période, il collecte des sources parlementaires
> officielles. Un parcours agentique Pipelex sélectionne les documents avec un LLM,
> évalue les preuves, décide d’un éventuel complément et rédige des résumés accessibles
> de 600 caractères maximum. Un questionnaire facultatif permet d’expliciter les
> liens avec la situation de l’utilisateur, sans profil politique ni recommandation
> de vote. Chaque résultat renvoie à une source consultable.

## Livrables

| Élément demandé | À remettre |
| --- | --- |
| Vidéo, 2 minutes maximum | **Lien à ajouter avant la remise** |
| Description courte | Texte ci-dessus |
| Dépôt et README de test | [Branche de livraison](https://github.com/jbelhoussineX/X-AI-Hackathon/tree/feat/pipelex-comparison), après publication des derniers changements |
| Membres de l’équipe | Arseniy, Jihane et Ryane |

Le règlement fourni ne demande ni hébergement en ligne ni API propre au projet.
Le test local nécessite une clé API OpenAI avec des crédits. La clé privée de
l’équipe n’est pas livrée ; ce prérequis est expliqué dans le [README](../README.md)
et le [guide du testeur](TESTER.md).

## Origine du projet

Selon la déclaration de l’équipe, le projet a été créé pendant le hackathon et
aucun projet préexistant n’a été repris. Python, Streamlit, Pipelex et les autres
paquets installés sont des dépendances tierces. Cette déclaration distingue la
création du projet de l’utilisation de bibliothèques existantes.

## Déroulé proposé pour la vidéo — 1 min 55

| Temps | Montrer et expliquer |
| --- | --- |
| 0:00–0:15 | Le problème : retrouver et comprendre un texte qui concerne sa vie quotidienne |
| 0:15–0:30 | Choisir un sujet et une période ; montrer brièvement le profil facultatif |
| 0:30–0:55 | Présenter les étapes réelles : sélection IA, évaluation, complément si nécessaire, synthèse |
| 0:55–1:25 | Montrer une recherche réelle préparée, lire une mesure concrète et ouvrir sa source |
| 1:25–1:40 | Montrer un lien pertinent avec le profil, puis un favori ou l’historique |
| 1:40–1:55 | Expliquer la couverture partielle, annoncer le dépôt et citer les membres |

Préparer la recherche avant l’enregistrement. Si la vidéo utilise un montage ou
un résultat enregistré, le dire ; ne pas présenter un temps d’attente raccourci
comme une mesure de performance. Ne montrer ni `.env` ni clé API.

## Points utiles pour les critères du jury

| Critère | Élément concret du projet à montrer |
| --- | --- |
| Impact / utilité — 30 % | Une mesure expliquée clairement sur un sujet de la vie quotidienne |
| Innovation — 20 % | La décision de complément et la personnalisation factuelle |
| Réalisation — 20 % | Sources effectivement collectées, contrôles des citations et tests hors ligne |
| UX — 15 % | Sujets en bulles, résumés courts, sources et favoris accessibles |
| Démo — 15 % | Un parcours réel simple, sourcé et compréhensible en moins de deux minutes |

## Dernière vérification avant dépôt

- [ ] Publier les derniers changements sur la branche livrée.
- [ ] Vérifier que le lien remis affiche le nouveau README et `backend/recent_agent.py`.
- [ ] Ajouter le lien de la vidéo et vérifier son accès ainsi que sa durée.
- [ ] Relire un résultat réel et sa source ; les tests simulés ne suffisent pas.
- [ ] Indiquer au testeur le prérequis d’accès API décrit dans le README.
- [ ] Déposer la description, le dépôt, la vidéo et les trois noms avant l’échéance.

Aucun de ces éléments n’est soumis automatiquement par ce document.
