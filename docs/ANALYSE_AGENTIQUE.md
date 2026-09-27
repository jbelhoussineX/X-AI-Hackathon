# Recherche agentique des nouveautés

Sélectionner ses sujets, choisir la période puis cliquer sur **Rechercher**.
Ce clic lance le parcours IA complet et consomme des crédits fournisseur, comme
indiqué dans le formulaire. Aucun sélecteur sans IA ni case supplémentaire.
Si les appels IA sont désactivés sur le serveur, le bouton est désactivé.
Consulter les favoris, l'historique ou modifier un champ ne lance aucun appel IA.

## Parcours et budget

1. Python collecte les notices datées des inventaires et flux Assemblée/Sénat,
   sans filtre de mots-clés. Les dates, liens officiels et limites de téléchargement
   restent contrôlés. Au plus 120 notices sont transmises, réparties entre les
   fournisseurs et privilégiant les plus récentes pour chacun.
2. `recent_agent.select` choisit jusqu'à six notices selon le sens du sujet et les
   titres, thèmes, descriptions et aperçus disponibles. Aucun mot exact n'est exigé.
   Le modèle retourne uniquement des identifiants présents dans la liste et les
   axes de recherche examinés. Il ne peut créer ni notice ni URL.
3. Python lit des passages des documents choisis. Depuis une page de dossier,
   la collecte peut lire un texte parlementaire explicitement lié (Assemblée ou
   Sénat), sans reconstituer son URL et sans parcours récursif. Les passages du
   texte lié sont prioritaires pour expliquer les mesures ; leurs citations
   renvoient à cette page, en conservant le rattachement au dossier.
   Un lien ne garantit ni la version la plus récente ni la date de publication :
   cette réserve est transmise à la synthèse. En cas d’échec, la notice reste
   disponible et l’échec de lecture est enregistré. Au plus six dossiers et un
   texte lié par dossier, dans le même budget de 30 secondes et 60 000 caractères
   par collecte de passages. Aucun appel IA supplémentaire. `recent_agent.evaluate` décide
   si les preuves sont pertinentes et suffisantes pour répondre au sujet.
4. Si nécessaire, un second `select` cherche dans les notices restantes de la même
   collecte, avec un axe complémentaire. Les nouveaux documents choisis sont lus.
   Il n'y a ni moteur lexical de repli ni recherche web extérieure implicite.
5. `recent_agent.summarize` rédige les nouveautés, leur pertinence et les réserves
   à partir des passages collectés, avec des références contrôlées.

Maximum : quatre étapes LLM (sélection, évaluation, sélection complémentaire,
synthèse), trois lorsqu'aucun complément n'est effectué. Aucune relance automatique.
Le modèle local reste `gpt-4o-mini`, avec plafonds de sortie 900 tokens par sélection,
1 600 pour l'évaluation et 3 500 pour la synthèse. Les entrées de sélection sont
également facturées par le fournisseur. Les plafonds ne garantissent pas le coût.
Sans aucune notice datée collectée, aucun appel IA n'est lancé. Sans preuve finale,
la synthèse n'est pas appelée, mais les étapes précédentes peuvent avoir consommé.

La synthèse demande deux à quatre phrases accessibles (600 caractères maximum, espaces compris),
expliquant la mesure, les personnes concernées, la nouveauté et les termes techniques.
La limite de 600 caractères est vérifiée par le schéma applicatif, sans tronquer les phrases.
Le lien au profil est limité à 240 caractères, la réserve à 180. Le budget de sortie
reste à 3 500 tokens. Un corpus purement procédural ne permet pas de décrire les
mesures : le modèle doit le dire plutôt que déduire une loi de son titre.
Les sources du même dossier portent une clé normalisée et le modèle doit produire
un résumé par dossier. L’interface regroupe aussi les anciens résumés par cette clé,
avec les autres étapes repliées ; les textes différents ne fusionnent pas sur leur titre.
Le corpus final conserve au plus six événements ; si le complément apporte des
preuves, il réserve jusqu'à trois événements à chaque sélection.

## Personnalisation des résumés

Les choix connus du questionnaire (genre, couple, emploi, enfants, animaux,
logement) sont validés par liste autorisée puis transmis uniquement à la synthèse
finale dans `profile_context`. Identité, nom, email, champs inconnus, valeurs libres,
« Autre » et non-réponses sont exclus. La sélection et l’évaluation documentaire
restent fondées sur les sujets explicitement choisis. Aucun appel IA supplémentaire.

La synthèse explique uniquement les liens personnels directs et précis étayés par
le passage cité. Une proposition non adoptée peut avoir un lien concret avec une
situation, sans prouver une éligibilité ou une obligation. Le champ `relevance` accepte une chaîne vide : aucun paragraphe
ni titre de lien n’apparaît si le lien est absent, flou, indirect ou hypothétique.
Sans réponse exploitable au profil, le serveur vide ce champ même si le modèle
a proposé une généralité. La synthèse ordonne ses items par
pertinence personnelle, puis par date à pertinence égale. Elle ne déduit ni opinion,
ni revenu, ni éligibilité, et conserve les textes pertinents pour le sujet même sans
lien personnel établi. Ce classement documentaire n’est pas un score politique.
Les sources reprennent par défaut cet ordre ; les événements sans résumé suivent
par date décroissante. Les tris chronologiques restent disponibles.

Le résultat conserve les réponses utilisées avec l’analyse. Changer le profil ne
réécrit pas les résumés enregistrés et ne déclenche aucun appel. En revanche,
chaque lien référence les réponses utilisées dans `relevance_fields`. Il reste
affiché si ces réponses sont inchangées ; retirer ou modifier une de ces réponses
masque ce lien, y compris dans l’historique. Les anciennes analyses sans ces
références restent masquées dès que le profil diffère. Le tri personnalisé exige
toujours le profil original complet. Un message invite à lancer une nouvelle
recherche pour actualiser le résumé lui-même.
Les tests hors ligne vérifient transmission, filtrage, ordre et absence de relance,
mais pas la justesse du jugement de pertinence d’un modèle réel.

## Portée de la recherche sémantique

La recherche active n'utilise plus la correspondance lexicale pour décider de la
pertinence. Le modèle doit cependant trouver ses preuves dans un corpus borné :
les notices au-delà des 120 retenues ne sont pas examinées. Un titre ou un aperçu
peut ne pas révéler tous les sujets traités. Les débats fournissent trois fenêtres
continues par texte ; pour les pages relues, les fenêtres sont réparties dans le
texte ou dans des pages PDF distinctes. Un passage pertinent ailleurs peut manquer.
Les citations ne sont jamais fabriquées en raccordant deux pages.

Ce mécanisme permet une pertinence fondée sur le sens ; il ne garantit ni rappel
exhaustif ni justesse du jugement du modèle. La fonction historique de collecte
lexicale reste disponible pour les anciens outils et tests, hors recherche active.

## Vérifications et limites

Le code vérifie les tailles, les requêtes, les décisions, les références et les
citations. Une citation inconnue refuse la synthèse. La présence d'un extrait ne
prouve pas la fidélité du résumé ou de l'évaluation : une relecture reste requise.
Aucun score politique, aucune recommandation de vote ou inférence d'éligibilité.
Les contenus collectés sont des données non fiables et ne peuvent choisir ni
fournisseur, ni méthode, ni URL à exécuter. La sélection peut manquer des sujets ou retenir une notice peu pertinente :
la couverture est partielle, surtout avec plusieurs thèmes.

Les étapes sont enregistrées en interne par l'application, pas racontées par le
modèle. Le bloc **Recherches effectuées** affiche uniquement les mots-clés utilisés.
Les résumés portent le titre de leur source, sa date et une couleur selon le type
de document. Les panneaux de limites et les exports JSON ne sont plus affichés.
Les contrôles des citations et les réserves propres à chaque résumé sont conservés.
Une erreur interrompt le parcours, sans relance ni changement de
fournisseur. Les sources déjà collectées restent visibles et peuvent être
enregistrées dans l'historique. Un délai local n'annule pas un calcul distant.
Les erreurs de sortie tronquée ou de structure invalide remontent un motif filtré,
y compris lorsqu'elles sont encapsulées par Pipelex/Instructor. Aucun texte brut
de réponse, requête ou clé n'est affiché dans le diagnostic.
Pour une erreur de validation, le champ et le code de contrainte reconnus sont
affichés (par exemple `champ=event_ids, contrainte=list_type`), sans la valeur rejetée.
Les mots-clés d'affichage de la sélection ont leur propre schéma : jusqu'à huit
libellés, de 1 à 100 caractères ; une liste vide est admise. Les documents restent
limités à six références distinctes, présentes dans le corpus fourni.

## Lancement local

La clé OpenAI reste dans la configuration privée. La valeur `PIPELEX_API_KEY`
n'est pas nécessaire pour le moteur local. Depuis le terminal Conda :

```bash
conda activate xia-hackathon
PIPELEX_EXECUTION_MODE=local ENABLE_PIPELEX_CALLS=true DO_NOT_TRACK=1 python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8502 --browser.gatherUsageStats false
```

Le mode `hosted` reste disponible si l'équipe dispose d'une véritable clé et de
l'accès à l'API hébergée Pipelex. Aucun repli entre moteurs n'est automatique.

## Vérification hors ligne

```bash
PYTHON_DOTENV_DISABLED=1 DO_NOT_TRACK=1 python -m pytest -q
```

Les tests exécutent les méthodes avec le vrai moteur Pipelex et le SDK
OpenAI, jusqu'à un transport HTTP simulé. Ils vérifient aussi consentement,
historique sans régénération, arrêts sur erreur, références et budgets. Les modèles
de contrôle applicatifs sont dans `backend/agent_models.py`, séparés du contrat
législatif v1 et des types générés de la synthèse historique. Aucun test payant
n'est exécuté par cette validation ; clé, quota et fidélité réelle restent à vérifier.
