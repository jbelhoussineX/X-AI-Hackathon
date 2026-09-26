# Comparaison des documents avec Pipelex

Responsable : Jihane. Cette partie reçoit des contenus collectés par Dust et propose une analyse structurée. Elle ne fait aucune recherche et n'écrit pas dans la base.

## Méthode

Le bundle contient un seul opérateur `PipeLLM`, avec quatre consignes successives : extraire les faits, comparer, qualifier et expliquer. Ce ne sont pas quatre appels distincts.

```text
Dust : collecte des passages sources
  → Python : ajoute l'ancien contenu enregistré et l'identifiant stable
  → political_watch.compare_document(request)
  → ChangeReport : type, bilan, différences, citations, limites
  → Python : vérifie le résultat avant stockage et affichage
```

La validation Pipelex confirme `is_valid=true`, `is_runnable=true` et aucune signature en attente. Aucun essai avec un modèle n'a encore été exécuté : la précision reste à évaluer. Le modèle est celui configuré par défaut dans l'environnement Pipelex.

## Contrat à partager avec la personne qui développe Dust

Un appel porte sur **un document**. Le programme fournit l'objet d'entrée suivant :

```json
{
  "request": {
    "document_id": "identifiant-stable-de-l-application",
    "watch_topic": "Accessibilité des transports en France",
    "current": {
      "source_url": "https://example.org/document-fictif",
      "retrieved_at": "2026-09-26T09:00:00Z",
      "retrieval_status": "ok",
      "scope": "full_document",
      "text": "Texte source récupéré, sans résumé généré."
    }
  }
}
```

Cet exemple illustre le format, pas un résultat de collecte réel. La projection d'entrée a été obtenue avec `mthds_inputs_template(explicit=false)`. Le champ facultatif `request.previous` utilise exactement la même structure que `current`. Il est absent ou null pour un document jamais enregistré.

| Champ | Responsabilité et règle |
|---|---|
| `document_id` | Python attribue un identifiant stable et associe les versions du même document. |
| `watch_topic` | Sujet explicitement choisi ; aucune opinion politique déduite. |
| `source_url` | URL de provenance ; une URL sans texte n'est pas une preuve suffisante. |
| `retrieved_at` | Date de récupération ISO 8601 avec fuseau ; distincte de la date de publication. |
| `retrieval_status` | `ok`, `partial` ou `unavailable`. Une erreur est transmise explicitement. |
| `scope` | `full_document` seulement si le texte intégral a été récupéré, sinon `excerpts`. |
| `text` | Texte brut ou passages exacts, jamais seulement la synthèse de Dust. Vide si indisponible. |

Python fournit `previous` depuis la dernière version conservée ; Dust fournit les éléments de `current`. Les URLs sont du texte de provenance, pas des ressources que cette méthode télécharge.

## Sortie

`ChangeReport` contient `document_id`, `change_type`, `description`, `changes`, `evidence` et `limitations`. Les quatre derniers types structurés sont définis dans `main.mthds`.

| `change_type` | Signification |
|---|---|
| `new_document` | Nouveau dans la veille, sans assertion sur la date de publication. |
| `modified` | Au moins une différence factuelle appuyée par les deux versions. |
| `unchanged` | Deux contenus complets comparables, sans différence factuelle constatée. |
| `unconfirmed` | Source indisponible/incomplète, ancien état inexploitable ou preuves insuffisantes. |

Chaque citation contient `version` (`previous` ou `current`), `source_url`, `retrieved_at` et `quote`. Chaque différence dans `changes` contient une `description` et des citations des deux versions.

Avec seulement des extraits, une modification précise peut être prouvée ; l'absence de différence dans ces extraits ne permet pas d'affirmer que le document entier est inchangé. La méthode est volontairement prudente et ne déduit pas de suppression à partir d'un passage manquant.

## Contrôles à intégrer côté Python

Les contrôles de structure et de provenance sont implémentés dans `backend/comparison_validation.py` et testés sans API. La pertinence sémantique des citations et la comparaison des faits restent à évaluer avec le modèle :

1. Vérifier le schéma de la réponse et l'égalité de `document_id` avec l'entrée.
2. Pour chaque citation, vérifier l'existence de sa version, l'égalité de l'URL et de la date, et la présence exacte de `quote` (non vide) dans `text`.
3. Pour `modified`, exiger une liste `changes` non vide et des preuves des deux versions pour chaque différence ; refuser des textes strictement identiques. La pertinence sémantique n'est pas garantie par ces contrôles : la présence d'une citation ne prouve pas à elle seule le raisonnement.
4. Refuser `unchanged` si les deux versions ne sont pas complètes et récupérées avec succès. Leur comparabilité sémantique reste à évaluer. Refuser `new_document` si `previous` est déjà présent.
5. En cas de récupération échouée ou partielle, imposer `unconfirmed`. Conserver l'ancien contenu et la dernière date de récupération réussie ; enregistrer séparément l'échec de la tentative.
6. En cas de sortie invalide ou d'erreur d'appel, conserver les données précédentes et signaler un échec. Ne jamais considérer l'absence de résultat comme `unchanged`.

Les consignes au modèle ne remplacent pas ces vérifications. Le modèle ne décide pas des écritures SQL et ne reçoit aucune clé API dans son entrée.

## Raccordement Python préparé

`backend/comparison_service.py` expose `compare_for_refresh(request, analyze)`.
`request` est la demande sans enveloppe. `analyze` est une fonction à fournir par
l'intégration future : elle reçoit `{"request": request}` et renvoie un `ChangeReport`
sans enveloppe. Cette fonction n'est pas un client Pipelex et ne masque aucun appel API.

Le service vérifie les entrées avant l'appel, puis les sorties. Il renvoie un objet
contenant `report` et `snapshot_to_store`. Ce dernier vaut `None` pour `unconfirmed`,
afin de ne pas proposer d'écraser la dernière version vérifiée. Les erreurs remontent
au programme appelant, qui devra conserver les données précédentes et journaliser
l'échec. La persistance, les transactions et l'affichage restent à raccorder.

Le collecteur Dust n'est pas encore disponible dans le dépôt. L'équipe devra
confirmer le format réel de sa réponse, fournir l'adaptateur vers `Snapshot`,
ajouter le client Pipelex, puis brancher SQLite et l'interface. Aucune actualisation
réelle de bout en bout n'est annoncée comme fonctionnelle à ce stade.

## Tests locaux sans API

Depuis la racine du dépôt, avec Python 3.11 ou ultérieur :

```bash
python -m unittest discover -s tests -v
```

La suite utilise uniquement la bibliothèque standard et des réponses fictives.
Elle couvre 22 tests, dont la distinction entre `retrieval_status=partial`
(récupération incomplète) et `scope=excerpts` avec `retrieval_status=ok`
(extraits correctement collectés). Elle n'utilise aucune clé ni aucun crédit.
Ces tests prouvent les contrôles locaux, pas la qualité des réponses d'un modèle.

## Quatre exemples de départ

Voir [les cas fictifs et leurs réponses attendues](../../tests/fixtures/political_watch/README.md). Ils utilisent uniquement du texte synthétique et ne nécessitent aucun upload de document.

Pour essayer la méthode avec le plugin Pipelex, sélectionner `main.mthds`, puis le `inputs.json` du cas désiré. Le pipe à exécuter est `political_watch.compare_document`. Les fichiers `expected.json` sont des corrigés à comparer après l'appel, jamais des entrées du modèle.

Les exécutions consomment des crédits Pipelex. Aucun essai Pipelex n'a été lancé ; l'utilisateur a demandé de ne pas en faire. Les corrigés restent des réponses attendues, jamais des résultats observés. L'intégration SDK/API avec Dust et SQLite, le choix du modèle, la mesure du coût et la planification quotidienne restent des étapes distinctes.

`PIPELEX_API_KEY` reste dans l'environnement local ou le gestionnaire de secrets. Ne jamais placer sa valeur dans Git, les exemples ou la documentation.
