# Premier essai réel : rapport fictif

Exécution : `run_79d300f8-68bb-4bfa-addc-e79de46994d4`, terminée le
27 septembre 2026. Entrée : `inputs.json`, dérivée du rapport entièrement fictif
`test_report.json`. Aucun appel Dust ni recherche documentaire réelle.

Pipelex rapporte 1 appel, 1 579 tokens et un coût de 0,005288 USD.
Ce montant d'inférence ne prouve ni un débit bancaire ni la gratuité du compte.

La sortie conserve : l'aide proposée de 100 euros, les étudiants boursiers
locataires, le seuil de ressources inférieur à 12 000 euros, l'exclusion des
propriétaires et la condition d'adoption/publication avant application.
Elle explique le lien au logement étudiant et ne présente pas la mesure comme
déjà applicable. Les références e1/e2 sont celles du rapport d'entrée.

Les contrôles de `validate_summary`, l'assemblage en `citoyen_report` et le
validateur de l'interface ont accepté le résultat. Cet essai unique ne démontre
pas la qualité générale ni le fonctionnement d'une recherche Dust réelle.

La sortie brute a été téléchargée par le plugin dans le dossier de conversation
`runs/run_79d300f8-68bb-4bfa-addc-e79de46994d4/main_stuff.json` puis copiée,
sans modification, dans le même chemin `runs/` du dépôt (ignoré par Git).
Le rapport assemblé est à côté, dans `interface_report.json`.

Prochaine vérification : rapport réel du coéquipier Dust, concordance des extraits
avec les pages citées, puis synthèse et affichage. Aucun nouvel essai n'est lancé
automatiquement et l'environnement de l'application reste désactivé par défaut.
