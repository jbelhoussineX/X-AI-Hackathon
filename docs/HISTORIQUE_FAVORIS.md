# Historique, favoris et questionnaire

La connexion Google existante fournit l’identité vérifiée. Toutes les lectures,
écritures et suppressions sont rattachées à cette identité côté serveur, jamais à
une adresse ou à un identifiant saisi dans un formulaire.

- **Historique** : chaque collecte réussie, même vide, est enregistrée pour un
  utilisateur connecté. Fenêtre glissante de sept jours, en UTC. Les entrées
  expirées sont supprimées au prochain accès à la collection, pas par une tâche
  planifiée. Rouvrir une recherche restitue le résultat de l’époque sans appel
  réseau ni IA. Les contrôles de fraîcheur de la synthèse restent actifs.
- **Favoris** : le bouton d’une fiche enregistre cet événement avec son lien et
  sa provenance. Un même événement n’est enregistré qu’une fois par compte.
  Les favoris persistent jusqu’au retrait ou à la suppression du profil.
- **Profil** : questionnaire facultatif (genre, couple, activité, enfants,
  animaux et logement), choix de sujets et période habituelle. Toutes les
  réponses proposent « Je préfère ne pas répondre ». Le questionnaire est
  enregistré uniquement ; il ne classe pas les résultats, n’infère aucune
  opinion politique et n’est pas transmis au fournisseur IA.
- **Suppression** : supprimer le profil supprime aussi questionnaire,
  historique et favoris. Un utilisateur peut retirer chaque élément séparément.
  Effacer la session depuis l’aide ne supprime pas les données du compte.

## Stockage et déploiement

Les nouvelles tables sont créées sans modifier les profils existants dans
`data/local/profiles.sqlite3`, ignoré par Git. Le fichier persiste entre les
sessions et les redémarrages sur le même serveur. Pour un hébergement à disque
éphémère, il faut prévoir un stockage persistant avant de promettre la conservation
après redéploiement. Sous Windows, les droits du fichier dépendent des ACL du
dossier ; les permissions POSIX `0600` ne constituent pas un contrôle Windows.

La sauvegarde de l’historique conserve le corpus collecté, pas une nouvelle
génération de synthèse. Les exports permettent de conserver une copie locale.
Sans connexion, les mêmes fonctions sont disponibles dans la session invitée :
profil, questionnaire, historique et favoris. Aucune base de comptes n’est créée
pour un invité. Une nouvelle session peut perdre ces données ; les exports
permettent de les conserver. À la connexion ou au changement de compte, les
données de session sont effacées et ne sont pas transférées automatiquement.

## Vérification hors ligne

`python -m pytest -q` teste l’isolation de deux utilisateurs, la persistance,
l’expiration, les retraits, la suppression du profil, le questionnaire, et
l’ouverture d’un historique sans relancer la collecte ou l’IA.
Les identités sont simulées ; le parcours Google réel doit être vérifié dans
une installation disposant de sa configuration OAuth.
