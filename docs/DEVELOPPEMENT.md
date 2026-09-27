# Repères de développement

## Parcours présenté au hackathon

`app.py` charge la configuration locale puis affiche `frontend/interface_b.py`.
La recherche de `frontend/recent_activity.py` appelle `backend.recent_agent.research`.
Les méthodes dans `methods/recent_agent/main.mthds` sont exécutées par le moteur
Pipelex, avec les modèles de contrôle de `backend/agent_models.py`.

Les données publiques sont collectées dans `backend/data_sources/`. Le corpus et
les citations sont préparés et vérifiés dans `backend/recent_brief.py`. Le profil
actif est en session (`frontend/guest.py`) ; aucun compte Google n’est requis.
Voir [l’architecture et les budgets](ANALYSE_AGENTIQUE.md).

## Tests

Depuis l’environnement Python installé avec `requirements-ui.txt` :

```bash
PYTHON_DOTENV_DISABLED=1 DO_NOT_TRACK=1 python -m pytest -q
python -m pip check
git diff --check
```

Les tests UI neutralisent la lecture des secrets Streamlit. Les tests du moteur
Pipelex passent par un transport fournisseur simulé. Aucun appel IA payant n’est
nécessaire. Pour des commandes macOS/Linux et PowerShell complètes, voir
[TESTER.md](TESTER.md).

La qualité d’un résumé réel doit être contrôlée séparément à partir de la source.
[Grille de relecture](TESTS_MANUELS.md).

## Compatibilité conservée

Le dépôt contient aussi des parcours précédents :

| Composants | Raison de leur présence |
| --- | --- |
| `src/service.py`, rapports v1 et `schemas/` | Contrat historique et tests d’intégration |
| `backend/dust/`, `src/dust_client.py`, `tools/check_dust.py` | Adaptateurs historiques, hors interface actuelle |
| `methods/political_*`, `backend/generated/` | Méthodes précédentes et types générés utilisés par leurs tests |
| `backend/storage.py`, `backend/profiles.py` | Stockage historique et fonctions réutilisées par le profil de session |
| Catalogue parlementaire et comparaison | Outils indépendants conservés, sans actualisation programmée dans l’application |

Ces composants ne constituent pas des fonctionnalités supplémentaires promises
pour la démonstration. Les supprimer nécessite un travail distinct de retrait des
imports et contrats. Les fichiers générés ne doivent pas être modifiés à la main.

Pour vérifier leurs empreintes :

```bash
python scripts/codegen_check.py backend/generated/political_search backend/generated/political_report backend/generated/political_summary backend/generated/political_watch backend/generated/recent_brief
```

## Configuration et publication

`.env.example` présente uniquement les paramètres utiles au lancement. Le fichier
`.env`, les secrets Streamlit, les bases locales et les journaux restent ignorés.
Ne pas transmettre de clé dans un commit, une vidéo ou un diagnostic.

La branche préparée est `feat/pipelex-comparison`. Après publication, le lien de
remise doit pointer vers la branche ou le commit effectivement testé, et non vers
une ancienne version sur `main`. Voir [la fiche de remise](SOUMISSION.md).
