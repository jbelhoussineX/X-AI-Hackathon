# Historique, favoris et questionnaire

Le profil actif est accessible sans connexion. Préférences, questionnaire,
historique et favoris sont conservés dans la session du navigateur. Aucune
identité Google n'est lue et aucune création de compte n'est nécessaire.

- **Historique** : chaque collecte réussie, même vide, est enregistrée pour un
  profil de session. Une recherche sur plusieurs sujets crée une seule entrée.
  Fenêtre glissante de sept jours, en UTC. Les entrées
  expirées sont supprimées au prochain accès à la collection, pas par une tâche
  planifiée. Rouvrir une recherche restaure les sujets sélectionnés, la période
  et le résultat de l'époque sans appel réseau ni IA. Les contrôles de fraîcheur
  de la synthèse restent actifs.
- **Favoris** : cliquer l'étoile blanche d'une fiche enregistre cet événement
  avec son lien et sa provenance ; l'étoile devient jaune. Un second clic le
  retire. Un même événement n’est enregistré qu’une fois par session.
  Les favoris persistent jusqu'au retrait. Le clic est traité une seule fois
  avant le rendu de la page, sans seconde relance explicite ni appel IA.
  L'identifiant du bouton dépend de l'événement, pas de sa position après tri.
- **Profil** : questionnaire facultatif (genre, couple, activité, enfants,
  animaux et logement) et période habituelle. Les sujets se choisissent dans Recherche. Toutes les
  réponses proposent « Je préfère ne pas répondre ». Les choix renseignés sont
  transmis uniquement à la synthèse IA pour adapter les résumés et ordonner les
  textes selon leur lien avec la situation déclarée, sans inférer d’opinion politique.
  Le nom, l’identité, les champs inconnus, « Autre » et les non-réponses sont exclus.
  Modifier le profil ne relance rien : seuls les prochains clics sur Rechercher
  utilisent ces changements. L’historique conserve les réponses utilisées à la génération.
- **Retrait** : un utilisateur peut retirer chaque entrée d'historique ou favori
  séparément. La page du profil ne propose pas d'export ou de suppression du
  profil. Le bouton de l'aide efface les résultats affichés mais conserve les préférences et favoris de session.

## Rechercher plusieurs sujets

Dans **Recherche → Sujets**, sélectionner des bulles parmi les sujets courants.
La ligne **Autres sujets** accepte des thèmes libres séparés par des virgules,
seuls ou en complément des bulles. Cliquer **Rechercher** lance la collecte pour
une à huit thématiques au total. Le profil ne propose plus de liste de sujets ;
les anciennes préférences stockées restent intactes, sans filtrer les bulles proposées.

Les résultats réunissent les thèmes sélectionnés : un événement peut correspondre
à un seul de ces thèmes. Les sujets ne sont pas concaténés en une requête exigeant
leur présence simultanée. La sélection, l'enregistrement du profil et la navigation
ne lancent aucun appel réseau ni IA ; seule une recherche explicite collecte les
sources. Le bouton Rechercher lance la sélection sémantique IA, l'évaluation,
le complément si utile et le résumé. Voir [le parcours agentique](ANALYSE_AGENTIQUE.md).

Dans **Sources législatives**, une seule carte est affichée par URL officielle normalisée (http/https, www,
ancre et paramètres de suivi regroupés ; les paramètres de version restent distincts).
Ses autres étapes ou versions restent consultables dans **Autres étapes et versions**,
avec leurs dates et favoris. Les métadonnées de provenance et libellés d’actes
restent dans les données internes, sans le panneau « Détails et provenance » à l’écran. Les répétitions du même contenu
et de la même étape sont regroupées malgré des identifiants de collecteurs différents,
avec un compteur visible. Les résumés du même dossier sont également regroupés :
un résumé principal et les autres étapes repliées, sans supprimer les données originales.
Un changement de contenu, d'acte ou de version reste conservé ; un titre identique
ne suffit jamais à fusionner deux sources. L'historique original n'est pas modifié.

## Stockage et durée

Le parcours actif ne crée ni ne lit de compte dans SQLite. Une nouvelle session
ou un redémarrage du serveur peut perdre le profil, l'historique et les favoris.
Deux sessions de navigateur ne partagent pas leurs préférences.
Les anciens comptes dans `data/local/profiles.sqlite3` ne sont ni supprimés ni
importés automatiquement. Leur backend reste conservé pour compatibilité.

La sauvegarde d'une recherche dans la session inclut son analyse IA ou son erreur
partielle. Rouvrir l'historique ne déclenche aucune recherche ni génération.
Les exports JSON ne sont plus proposés.

## Vérification hors ligne

`python -m pytest -q` teste l'absence de connexion, le profil de session, son
isolation, les favoris, l'historique sans relance IA et le regroupement des sources.
Les tests de stockage historiques couvrent aussi les anciens comptes conservés.
