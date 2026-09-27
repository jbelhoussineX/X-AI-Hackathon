# Installer Pipelex pour Sed Lex

L’installation reproductible est désormais décrite dans le **[guide du testeur](TESTER.md)**.
Elle convient à un nouvel ordinateur macOS, Linux ou Windows avec Python 3.12.

Le parcours recommandé installe le moteur Pipelex **localement** et utilise l’API
OpenAI avec la clé renseignée dans le `.env` de cette installation. Il ne nécessite
pas de compte Pipelex hébergé. Les dépendances sont dans `requirements-ui.txt`
et la configuration `.pipelex/` est déjà livrée : ne pas relancer `pipelex init`.

Les anciens chemins personnels, journaux de consommation et instructions de
configuration Google ont été retirés du guide de livraison.

- [Installer, configurer et démarrer](TESTER.md)
- [Comprendre les étapes IA et leurs limites](ANALYSE_AGENTIQUE.md)
- [Développer et exécuter les tests hors ligne](DEVELOPPEMENT.md)

`PIPELEX_EXECUTION_MODE=hosted` reste une alternative technique. Elle demande une
véritable clé `PIPELEX_API_KEY` et les droits API correspondants. La présence d’une
clé n’en garantit pas les droits, et aucun repli automatique n’est effectué.
