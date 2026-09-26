# Cas fictifs pour la comparaison

Tous les textes, dates et URLs sont fictifs. Les URLs `example.org` ne sont pas consultées. Chaque dossier contient un `inputs.json` prêt pour la méthode et un `expected.json` écrit avant toute exécution, qui sert de corrigé humain et non de résultat observé.

| Cas | Entrée | Résultat attendu |
|---|---|---|
| `new_document` | Aucun ancien état ; consultation récupérée. | `new_document`, preuve actuelle, aucune différence historique inventée. |
| `modified` | Clôture le 10 octobre puis le 20 octobre 2026. | `modified`, report du 10 au 20 avec citations des deux états. |
| `unchanged` | Même contenu complet, dates de récupération différentes. | `unchanged`, aucune modification déduite des horodatages. |
| `unconfirmed` | Ancien contenu conservé ; récupération actuelle impossible. | `unconfirmed`, aucune citation actuelle inventée, limite explicite. |

Les formulations ne doivent pas être comparées mot à mot avec le corrigé. Pour réussir un cas, le type doit être exact, chaque affirmation doit être justifiée, chaque citation doit exister dans la version indiquée et aucune date, source ou différence ne doit être inventée. Pour `modified`, la bonne différence doit être reconnue, pas seulement le bon type.

État initial : **0/4 essais avec un modèle exécutés**. Les fichiers ont été préparés pour ces essais ; ils ne prouvent pas encore la qualité de la méthode.

Les 22 tests de `tests/test_comparison.py` utilisent ces corrigés comme réponses
fictives, puis en altèrent certains champs pour vérifier les rejets du validateur.
Ils se lancent avec `python -m unittest discover -s tests -v`, sans accès réseau.
Aucun essai Pipelex ne doit être lancé sans nouvelle demande de l'utilisateur.

Avant une démonstration réelle, compléter avec des cas limites : extraits identiques mais incomplets, récupération partielle, changement de mise en page seul, ancienne version indisponible, document contenant une instruction malveillante, deux passages non comparables et plusieurs différences simultanées.
