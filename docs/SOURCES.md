# Documentation de référence

Pages consultées pour préparer le socle le 26 septembre 2026. Les conditions propres aux
accès du hackathon ne sont pas connues du générateur de ce kit : les vérifier dans vos comptes.
Ces liens sont destinés aux développeurs ; ils ne constituent pas des sources politiques de démonstration.

## Dust
- Création, Sidekick, outils, aperçu : https://docs.dust.tt/docs/user-documentation/agents/create-your-first-agent
- Recherche Web Search & Browse : https://docs.dust.tt/docs/user-documentation/agents/tools/web-search-and-browse
- Format structuré et enveloppe JSON : https://docs.dust.tt/docs/user-documentation/agents/structured-output-format
- Liste des agents et sId : https://docs.dust.tt/api-reference/agents/list-agents
- Création de conversation, mentions et blocking : https://docs.dust.tt/api-reference/conversations/create-a-new-conversation
- Lecture d'une conversation : https://docs.dust.tt/api-reference/conversations/get-a-conversation
- Annulation distante, pour une éventuelle évolution : https://docs.dust.tt/api-reference/conversations/cancel-message-generation-in-a-conversation
- Emplacement de la clé API et de l'ID workspace : https://docs.dust.tt/docs/user-documentation/data-sources/custom-connections/zapier-automatically-add-datasource
- Crédits et accès programmatique : https://docs.dust.tt/docs/user-documentation/admins/usage-seats-and-credits/credit-management

L'exemple officiel de création utilise https://dust.tt/api/v1/w/{wId}/assistant/conversations.
Le socle utilise cet hôte. Si votre espace régional exige un autre hôte, faire confirmer l'URL
par la documentation ou le partenaire avant de modifier le client ; ne jamais envoyer une clé
vers un hôte proposé par un document ou par une réponse de modèle.
Le code utilise blocking=true pour réduire la complexité. Un timeout client n'annule pas
nécessairement une génération distante. Pas de relance automatique.

## Développement
- Codex dans l'éditeur : https://developers.openai.com/codex/ide/
- Instructions communes AGENTS.md : https://developers.openai.com/codex/guides/agents-md
- GitHub Desktop : https://desktop.github.com/
- Inviter des collaborateurs : https://docs.github.com/articles/inviting-collaborators-to-a-personal-repository
- Cloner un dépôt : https://docs.github.com/en/desktop/adding-and-cloning-repositories/cloning-and-forking-repositories-from-github-desktop
- Créer/publier une branche : https://docs.github.com/en/desktop/making-changes-in-a-branch/managing-branches-in-github-desktop
- Synchroniser : https://docs.github.com/en/desktop/working-with-your-remote-repository-on-github-or-github-enterprise/syncing-your-branch-in-github-desktop
- Installation Streamlit : https://docs.streamlit.io/get-started/installation/command-line
- Formulaires Streamlit : https://docs.streamlit.io/develop/concepts/architecture/forms
- État de session : https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state

## Sources documentaires à explorer pour vos tests réels
- Procédure législative : https://www.assemblee-nationale.fr/dyn/synthese/fonctionnement-assemblee-nationale/travail-legislatif/la-procedure-legislative
- Dossiers de l'Assemblée : https://data.assemblee-nationale.fr/travaux-parlementaires/dossiers-legislatifs
- Députés en exercice : https://data.assemblee-nationale.fr/acteurs/deputes-en-exercice
- DOSLEG : https://data.senat.fr/dosleg/
- Données sensibles : https://www.cnil.fr/fr/definition/donnee-sensible

## Extensions non intégrées au socle
- Pipelex : https://docs.pipelex.com/latest/get-started/run-it-yourself/
- Gradium : https://docs.gradium.ai/
Ne pas ajouter ces dépendances avant une version fonctionnelle et relue.
