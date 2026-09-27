# Connexion Google et profil Sed Lex

Sed Lex propose une connexion avec un compte Google personnel et un profil local.
La recherche reste accessible sans connexion. Les identifiants Google ne sont pas
inclus dans le dépôt : la connexion réelle nécessite la configuration ci-dessous.
Aucun projet Google, compte OAuth ou secret réel n'est créé par l'application.

## 1. Préparer Google Auth Platform

Dans la [console Google Cloud](https://console.cloud.google.com/), choisir ou créer
un projet pour Sed Lex. Cette procédure ne demande pas d'activer une facturation,
d'ajouter une carte ou de souscrire un service payant.

Ouvrir **Google Auth Platform → Branding** (ou **Commencer / Get Started**), puis :

1. Nommer l'application **Sed Lex** et renseigner les adresses de support et de contact.
2. Choisir **Audience → External / Externe** pour accepter les comptes Gmail personnels.
3. Si le projet est en **Testing / Test**, ajouter les comptes des testeurs dans
   **Audience → Test users / Utilisateurs test**.
4. Dans **Data Access / Accès aux données → Add or Remove Scopes**, conserver
   uniquement `openid`, l'adresse e-mail (`userinfo.email`) et le profil de base
   (`userinfo.profile`). Ne sélectionner aucun accès Gmail ou Drive.

Ces rubriques sont décrites dans le [guide officiel de configuration du consentement](https://developers.google.com/workspace/guides/configure-oauth-consent).

Ouvrir ensuite **Google Auth Platform → Clients → Create Client / Créer un client** :

1. Choisir **Web application / Application Web**.
2. Donner un nom, par exemple **Sed Lex local**.
3. Ajouter cette **Authorized redirect URI / URI de redirection autorisée**, exactement :
   `http://localhost:8502/oauth2callback`.
4. Créer le client et conserver son **Client ID** et son **Client secret** localement.

Streamlit utilise le retour serveur : les origines JavaScript ne sont pas utilisées
dans cette intégration. Voir le [guide officiel des clients OAuth](https://developers.google.com/workspace/guides/create-credentials).

## 2. Remplir la configuration locale

Depuis la racine du dépôt, préparer le fichier sans écraser une configuration existante :

```bash
conda activate xia-hackathon
umask 077
mkdir -p .streamlit
cp -n .streamlit/secrets.toml.example .streamlit/secrets.toml
chmod 600 .streamlit/secrets.toml
```

Ouvrir **localement dans l'éditeur** `.streamlit/secrets.toml`, puis remplacer les
trois valeurs `REMPLACER_…` :

- `client_id` : identifiant du client OAuth de l'étape précédente ;
- `client_secret` : secret de ce même client ;
- `cookie_secret` : valeur aléatoire produite dans votre terminal avec la commande suivante.

```bash
python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Copier la valeur uniquement dans `cookie_secret`, entre guillemets, puis fermer ce
résultat de terminal. Ne pas la joindre à un message de support, une capture ou un
commit. `.streamlit/secrets.toml` est déjà ignoré par Git ; seul le fichier
`secrets.toml.example` doit être partagé. Les identifiants ne vont pas dans `.env`.

L'exemple utilise le fournisseur nommé `google` : `st.login("google")` lit
`[auth.google]`, tandis que `[auth]` contient l'URL de retour et le secret du cookie.
Conserver `server_metadata_url` tel quel. Aucun jeton d'accès n'est exposé au code
du profil ; ne pas ajouter `expose_tokens`. Voir [la configuration de `st.login`](https://docs.streamlit.io/develop/api-reference/user/st.login).

## 3. Lancer et vérifier

Les dépendances d'authentification sont déclarées dans `requirements.txt` :

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8502 --browser.gatherUsageStats false
```

Si l'application tourne déjà, l'arrêter dans son terminal avant de la relancer.
Ouvrir **http://localhost:8502**, puis utiliser la connexion Google de l'interface.
Conserver `localhost` dans le navigateur : passer alternativement par `127.0.0.1`
utilise un autre hôte pour les cookies. Le port `8502`, le protocole et le chemin
`/oauth2callback` doivent correspondre à la configuration Google et à celle de
Streamlit, sans barre oblique supplémentaire. Google exige une correspondance
exacte, détaillée dans sa [documentation OpenID Connect](https://developers.google.com/identity/openid-connect/openid-connect).

Après connexion, modifier une préférence du profil, enregistrer, se déconnecter
puis se reconnecter pour vérifier sa persistance. Un autre compte Google doit
retrouver ses propres préférences. Choisir **Sans synthèse** dans le menu pour
consulter les actualités officielles sans génération IA payante ; la collecte
utilise le réseau. Le menu propose **Recherche**, **Mon profil** et **Aide**.

## Profil et confidentialité

Le profil contient un nom d'affichage modifiable, initialisé avec le nom Google,
l'e-mail Google vérifié en lecture seule, jusqu'à huit sujets saisis volontairement
(100 caractères chacun) et une période récente préférée de 1 à 12 mois
(2 mois par défaut). Il ne déduit aucune opinion politique. Il n'accède pas aux messages Gmail, fichiers Drive,
contacts ou agenda, et n'envoie aucun e-mail. Aucune clé Google personnelle n'est
requise pour chaque utilisateur : le client OAuth appartient à l'application,
chaque personne choisit ensuite son compte Google.

Les préférences sont stockées dans `data/local/profiles.sqlite3`, sur la machine
qui exécute Sed Lex. La clé du profil dépend de l'identifiant stable du compte
Google (`issuer` et `sub`), pas de son adresse e-mail ; aucun jeton n'est stocké
dans cette base. Elles ne sont pas synchronisées dans Google.

**Préparer la recherche** depuis un sujet du profil préremplit le sujet et la
période en mois, puis ouvre **Recherche**. Cliquer ensuite **Rechercher** pour
consulter les actualités. Aucune collecte ni aucun appel IA ne sont automatiques.
Les anciens résultats, filtres et consentement à la synthèse sont effacés quand
un sujet est préparé. Les résultats restent liés à la session ; ils ne sont pas
enregistrés dans le profil.
Après confirmation, supprimer le profil efface ses données locales et déconnecte
Sed Lex ; cela ne supprime ni ne modifie le compte Google. Une nouvelle connexion
permet de recréer un profil sans les anciennes préférences.

La déconnexion Sed Lex termine la session de l'application. Elle ne déconnecte
pas le compte Google du navigateur. Les autres onglets déjà ouverts peuvent garder
leur session : les fermer après utilisation sur un ordinateur partagé. Voir
[la documentation de déconnexion Streamlit](https://docs.streamlit.io/develop/api-reference/user/st.logout)
et [le fonctionnement des sessions d'authentification](https://docs.streamlit.io/develop/concepts/connections/authentication).

## Dépannage

| Problème | Vérification |
| --- | --- |
| Connexion Google non configurée | Compléter les trois valeurs d'exemple, vérifier les sections `[auth]` et `[auth.google]`, puis redémarrer Streamlit. |
| `redirect_uri_mismatch` | Comparer l'URI Google à `http://localhost:8502/oauth2callback` ; vérifier port, protocole et barre finale. |
| Compte refusé | Vérifier l'audience External et, si nécessaire, les utilisateurs test du projet. |
| `invalid_client` | Vérifier localement que l'identifiant et le secret appartiennent au même client OAuth de type Web. |
| Retour à l'application sans connexion | Utiliser `localhost` dès le départ, autoriser les cookies et recommencer après avoir fermé les anciens onglets. |

Cette procédure concerne le prototype local. Une adresse accessible publiquement
demanderait un déploiement HTTPS et une nouvelle URI autorisée, avec configuration
des secrets et du stockage sur cet hébergement. Ce déploiement n'est pas inclus.

Les tests automatiques simulent l'identité et les échanges. Ils ne remplacent pas
un essai du parcours Google réel, qui nécessite les identifiants du projet et une
connexion volontaire dans le navigateur.

Validation locale après intégration de l'interface `48c3807` : **365 tests et 28 sous-tests réussis** avec
`PYTHON_DOTENV_DISABLED=1 DO_NOT_TRACK=1 python -m pytest -q`, en Python 3.12.11
dans l'environnement `xia-hackathon`. Ils vérifient notamment la séparation des
comptes, le changement d'adresse pour un même compte, la persistance, la suppression,
le nettoyage de la session et l'absence de recherche automatique depuis le profil.
`tests/conftest.py` remplace le chargement des secrets Streamlit par un dictionnaire
vide avant les tests : les fichiers OAuth réels ne sont pas consultés.
