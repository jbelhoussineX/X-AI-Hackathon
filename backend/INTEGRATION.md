# Intégration Python / Streamlit

Le parcours actif appelle :

```python
from backend.recent_agent import research
# Appel réel uniquement après configuration et clic explicite :
# result = research(["logement"], months=3, profile_context={"logement": "Locataire"})
```

La recherche utilise Pipelex et le fournisseur configuré. Le mode local recommandé
nécessite `OPENAI_API_KEY`, `PIPELEX_EXECUTION_MODE=local` et
`ENABLE_PIPELEX_CALLS=true`. L’interface assure le clic explicite et l’historique ;
modifier le profil ou consulter un favori ne lance pas la recherche.

Le résultat applicatif comprend les événements collectés, les informations de
collecte et `agent_analysis` : évaluation, résumés vérifiés, mots-clés et état du
parcours. Les traces enregistrent les étapes réellement exécutées ; elles ne
contiennent pas de raisonnement interne du modèle.

- [Architecture et contrôles](../docs/ANALYSE_AGENTIQUE.md)
- [Installation du testeur](../docs/TESTER.md)
- [Sources récentes](../docs/ACTUALITES_RECENTES.md)

## Contrat historique

`src.service.search(topic, start, end, mode='pipelex')`, `report_schema.json` et
les adaptateurs des rapports v1 restent disponibles pour leurs tests et outils.
Ils ne sont pas le point d’entrée de la recherche présentée dans l’interface.
Le [contrat v1](../CONTRACT.md) est conservé sans modification.
