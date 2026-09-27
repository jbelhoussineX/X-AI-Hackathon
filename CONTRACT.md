# Contrat d'intégration — version 1.0

Le schéma de référence est `schemas/report.schema.json`.
`schemas/dust_response_format.json` ajoute l'enveloppe attendue dans Dust.
Toute modification doit être répercutée dans les deux fichiers et décidée à trois.

L'interface appelle uniquement :
```python
search(topic: str, start: str, end: str, mode: str = "demo") -> dict
```
`mode="demo"` : fixture explicitement fictive, aucun réseau, résultat fixe.
`mode="dust"` : un appel de génération Dust, sans relance automatique.
Les dates sont YYYY-MM-DD ; elles filtrent la date de publication et non celle du statut.
La date de statut peut être postérieure à la période de publication. Si la date de publication
reste inconnue, la limite doit être signalée dans `uncertainties` : la période n'est pas confirmée.

Résultat applicatif : `mode`, `run_at_utc`, `duration_seconds`, `conversation_id`, `validation`, `report`.
`report` est la sortie de l'agent : `schema_version`, `topic`, `scope`, `documents`, `contacts`, `limitations`.

Au plus 4 documents et 3 interlocuteurs. Les inconnues valent `null`, pas une supposition.
Chaque document a au moins une preuve `contenu`. Tout statut non nul possède une preuve `statut`.
Chaque contact cite un document existant et possède une preuve `relation`.
Une page de contact non nulle correspond exactement à l'URL de sa preuve `contact`.
Une preuve contient `purpose`, `url`, `excerpt`, `location` (ou null).
Les tableaux vides sont acceptés ; une recherche vide doit expliquer ses limites.

## Parcours Pipelex actif (27 septembre 2026)

Le rapport JSON v1 et la signature sont conservés. `mode="pipelex"` choisit
`PIPELEX_EXECUTION_MODE=hosted|local` (défaut hosted).
`ENABLE_PIPELEX_CALLS=true` est nécessaire. `POLITICAL_DATA_SOURCE=official`
est le défaut : inventaires Sénat/Assemblée, pages collectées, synthèse et contrôle
des citations dans le corpus exact transmis. Aucun repli web automatique.
Le repérage dans les inventaires filtre le dépôt initial ; le rapport filtre
la publication. Cette distinction limite la couverture et est signalée.
Le parcours hébergé ajoute le champ applicatif facultatif `source_checks`.
Le mode local officiel refuse lui aussi une citation absente, sans exposer ce tableau.
La recherche web reste une option explicite `POLITICAL_DATA_SOURCE=web` ;
en local ses extraits ne sont pas revérifiés indépendamment.
Dust reste un mode historique de compatibilité, absent de l'interface active.

## Limites du socle historique
Les règles vérifient structure, liens syntaxiques, références et dates. Elles NE VÉRIFIENT PAS
que les pages ont été lues, que les extraits y figurent ou que la synthèse est fidèle.
Le code ne télécharge pas automatiquement des URLs proposées par l'agent.
C doit contrôler les documents réels avant la démonstration, en conservant la source et la date.
Les assertions d'action du modèle ne sont pas un journal d'outil authentifié.
La réponse peut contenir des erreurs même lorsqu'elle respecte ce contrat.

Pas de traitement silencieux des doublons : deux versions d'un texte peuvent être distinctes.
Évolution proposée : même identifiant officiel ET même version = doublon potentiel,
à grouper sans supprimer des étapes distinctes de procédure.
