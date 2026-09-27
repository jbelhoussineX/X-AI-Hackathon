# Contrôle des extraits Dust

`src.service.search` filtre les documents par période, puis appelle
`verify_sources(report)` avant toute synthèse Pipelex. Aucun outil Dust à ajouter :
ce contrôle s'exécute dans le backend Python après réception du rapport JSON.
Il ne s'agit pas d'un connecteur à une API gouvernementale : ce sont des lectures
HTTP des pages citées, sans clé gouvernementale.

Domaines acceptés en HTTPS, avec et sans `www` : `assemblee-nationale.fr`,
`senat.fr`, `legifrance.gouv.fr`. Les autres domaines sont non confirmés, sans
requête réseau. Les redirections sont vérifiées à chaque étape. Ajouter une
nouvelle source nécessite une modification explicite de la liste `HOSTS`.

Le collecteur extrait le texte HTML (sans scripts, styles ni en-tête), lit du
texte brut ou extrait la couche texte des PDF avec pypdf. Il recherche l'extrait exact, puis essaie en normalisant uniquement
les espaces et la composition Unicode. Aucun mot, montant, date ou ponctuation
n'est corrigé pour fabriquer une concordance. Une URL partagée est téléchargée
une seule fois par recherche ; pas de cache persistant.

Limites : huit URL sources au maximum, trois redirections par URL, 2 Mo de contenu
décompressé par réponse, délais réseau bornés et budget temporel d'environ 30 s.
Le budget est vérifié entre lectures ; une lecture réseau en cours peut le dépasser
jusqu'à son timeout. Aucun contournement de captcha ou de restriction d'accès.
Le rendu JavaScript et l'OCR ne sont pas pris en charge. Les PDF sans texte
extractible, chiffrés ou invalides restent non confirmés. L'extraction PDF se fait
dans un processus séparé arrêté après huit secondes au plus (ou le budget restant).
Elle est limitée à 40 pages, 2 Mo de contenu décompressé par page avant extraction
et 500 000 caractères de sortie. Ces seuils et le timeout ne constituent pas une
limite dure de mémoire du processus pendant le décodage.
Les pages sont conservées séparément : on ne fabrique pas de citation en
concaténant la fin d'une page avec le début de la suivante. `pdf_page` indique le
numéro physique de la page où un passage a été retrouvé, à partir de 1 ; ce n'est
pas nécessairement le numéro imprimé. Une couche OCR déjà présente peut contenir
des erreurs : le programme ne vérifie pas visuellement le PDF.

Chaque vérification expose URL initiale/finale, horodatage, type d'entité, numéro
d'extrait et statut dans `source_checks` du résultat du service. La page existante
ignore ce champ supplémentaire, mais affiche les avertissements ajoutés dans
`limitations` et `uncertainties`, sans changer son contrat `citoyen_report`.

Statuts : `matched`, `matched_whitespace`, `not_found`, `domain_not_allowed`,
`unavailable`, `http_error`, `unsupported_format`, `empty_page`, `too_large`,
`budget_exceeded`, `redirect_limit`, `invalid_pdf`, `encrypted_pdf`, `pdf_no_text`,
`pdf_page_limit`, `pdf_content_limit`, `pdf_timeout`, `pdf_extraction_error`.
Un échec ne prouve ni que le document n'existe
pas, ni que la citation est inventée : sa présence n'a pas pu être confirmée.

Si tous les extraits sont retrouvés et les appels sont activés, la synthèse Pipelex
peut commencer. Sinon, le rapport Dust reste affichable avec ses réserves et
Pipelex n'est pas appelé. Ce choix conservateur porte aussi sur les preuves de
statut et de contact. Un corpus vide n'entraîne pas d'appel Pipelex.

Retrouver une citation ne prouve pas son interprétation, la véracité du résumé,
la pertinence du document ou l'actualité d'une étape de procédure. Les champs
Dust ne deviennent donc pas des informations certifiées par ce contrôle.

## Vérifier un export de Dust

Par défaut, cette commande vérifie uniquement le format, sans réseau :

```powershell
.\.venv\Scripts\python.exe -m backend.summary_cli data/local/rapport-dust.json --topic "Logement étudiant"
```

Avec `--run --output data/local/synthese.json`, elle vérifie d'abord les pages,
puis exécute Pipelex uniquement si les sources sont confirmées et l'environnement
autorise les appels. Le dossier doit exister et le fichier de sortie doit être
nouveau. Ce mode consomme des crédits si Pipelex est exécuté. Le module ne charge
pas `.env` automatiquement. Ne jamais mettre de clé dans le terminal partagé ou Git.

Les tests réseau utilisent exclusivement des réponses HTTP simulées : concordance,
normalisation des espaces, domaines trompeurs, redirections locales interdites,
script HTML, HTTP 403/404, PDF avec texte, PDF chiffré/vide/invalide, taille
excessive et timeout. Une validation sur les pages d'un véritable rapport Dust
reste à faire quand ce rapport sera disponible.

## Contrôle manuel sur une source réelle

Le 27 septembre 2026, le collecteur a récupéré le texte du Sénat
[`ppl24-303.html`](https://www.senat.fr/leg/ppl24-303.html) et son
[`PDF`](https://www.senat.fr/leg/ppl24-303.pdf). L'extrait technique choisi a été
retrouvé en HTML et dans la couche texte de la page physique 12 du PDF, après
normalisation des espaces. Une citation volontairement inventée a été refusée
dans les deux formats. Les quatre vérifications sont conservées localement dans
`data/local/source-smoke-check.json`, ignoré par Git.
Ce contrôle n'a appelé ni Dust ni Pipelex, et n'établit pas le statut actuel du texte.
Il ne constitue pas un test de l'ensemble des sites officiels.
