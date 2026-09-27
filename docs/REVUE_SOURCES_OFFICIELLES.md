# Revue du connecteur de l'équipe — 27 septembre 2026

Après `git fetch origin`, le travail se trouve sur `origin/feat/pipelex-comparison`,
commit `f5d79fc` (« integrate official data with team Pipelex and Streamlit workflow »),
après `fcbd7a3` (« prepare official Senate and Assembly data for Pipelex »).
Cette revue lit le code distant ; aucun changement de branche ni fusion n'a été fait.

## Ce qui existe

- [assembly.py](https://github.com/jbelhoussineX/X-AI-Hackathon/blob/f5d79fc/backend/data_sources/assembly.py)
  télécharge l'archive JSON publique de la 17e législature de l'Assemblée. Aucune
  clé API n'est demandée. Les dates de dépôt, publication et mise en ligne sont distinctes.
- [official.py](https://github.com/jbelhoussineX/X-AI-Hackathon/blob/f5d79fc/backend/data_sources/official.py)
  combine cet inventaire avec le CSV DOSLEG du Sénat, sélectionne au plus trois
  notices par institution, puis collecte des pages HTML/PDF. Le corpus transmis
  est limité à 60 000 caractères ; les troncatures et indisponibilités sont signalées.
- Dans le mode local de cette branche, `POLITICAL_DATA_SOURCE=official` remplace
  la recherche web IA par cette collecte. Le code prévoit un appel de rédaction
  et aucun appel IA si le corpus est vide ; il contrôle les extraits contre le corpus.
  L'évaluation LLM des manques et le complément sont désactivés dans ce mode.
- L'API Légifrance/PISTE n'est pas implémentée. Les identifiants mentionnés dans
  cette documentation concernent cette API, pas les exports publics de l'Assemblée.

## Points à traiter lors d'une intégration

1. La branche choisit `PIPELEX_EXECUTION_MODE=hosted` par défaut. Pour conserver
   l'architecture locale utilisant les crédits OpenAI, adapter explicitement cette
   sélection et l'activation `ENABLE_PIPELEX_CALLS`, plutôt que fusionner aveuglément.
2. Conserver les corrections locales récentes : modèle web, diagnostics détaillés,
   champs non vides et gestion du complément tronqué. Elles sont postérieures au
   commit `70ab834` repris par la branche.
3. Le repérage est lexical et filtre le dépôt initial. Ce n'est pas une recherche
   exhaustive par date de publication : le contrôle final de publication ne récupère
   pas les documents exclus en amont. La 17e législature seule couvre l'Assemblée.
4. Préserver une décision agentique utile si ce parcours devient le mode principal
   du hackathon : le mode officiel court-circuite actuellement `review()`.
5. Vérifier les dépendances supplémentaires et tester l'intégration hors ligne.
   Plusieurs passages de `backend/INTEGRATION.md` et du README des collecteurs
   décrivent encore l'ancien parcours PipeSearch ; le code donne l'état effectif.

La revue n'a pas exécuté le collecteur ni la suite de tests de la branche distante.
Les chiffres d'essais réels consignés par l'équipe dans son README n'ont pas été
reproduits ici. La collecte seule n'appelle pas de modèle ; sa synthèse IA reste
facturée par le fournisseur configuré.
