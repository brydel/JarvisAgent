# OAuth Google et courriel Gmail

Cette livraison ajoute une connexion OAuth PKCE et des outils Gmail derrière la passerelle de mandats.
Le code utilise uniquement la bibliothèque standard. Les tests n'utilisent aucun compte Google, aucun
identifiant réel et n'envoient aucun courriel. La configuration et le consentement d'un compte réel restent
nécessaires avant de revendiquer une intégration Gmail vérifiée.

## Configuration propriétaire

Créer une application OAuth Google adaptée à l'utilisation locale et autoriser les scopes Gmail voulus.
La console Google impose ses propres règles de type d'application, de retour loopback, d'utilisateurs de
test et, selon les scopes et l'usage, de vérification de l'application. Jarvis ne contourne pas ces règles.

Le propriétaire ajoute une configuration dans **Intégrations** ou avec :

```bash
jarvis os oauth configurer google.json
jarvis os oauth commencer gmail-personnel
jarvis os oauth liste
jarvis os oauth revoquer gmail-personnel
```

Exemple de fichier sans secret ni adresse personnelle :

```json
{
  "id": "gmail-personnel",
  "nom": "Gmail personnel",
  "provider": "google_gmail",
  "client_id": "CLIENT_PUBLIC_GOOGLE.apps.googleusercontent.com",
  "client_secret_env": "JARVIS_GOOGLE_CLIENT_SECRET",
  "redirect_uri": "http://localhost:7718/api/v2/oauth/callback",
  "scopes": [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send"
  ],
  "adresse_expediteur": "expediteur@example.test"
}
```

Adapter l'identifiant public, le retour et l'adresse au compte. `client_secret_env` est facultatif pour les
types de client qui n'en demandent pas ; lorsqu'il est renseigné, il désigne une variable du service. Sa valeur
ne passe ni dans le JSON, ni dans l'interface, ni dans les prompts. L'adresse expéditrice est déclarée par le
propriétaire et doit correspondre au compte ou à un alias autorisé par Gmail ; Jarvis ne la considère pas
comme vérifiée avant un contrôle réel fournisseur. Elle est obligatoire pour les brouillons et envois.

Les scopes acceptés sont explicites :

| Scope | Outils du connecteur |
| --- | --- |
| `https://www.googleapis.com/auth/gmail.readonly` | Profil, recherche, lecture et rapprochement des reçus |
| `https://www.googleapis.com/auth/gmail.compose` | Création de brouillon |
| `https://www.googleapis.com/auth/gmail.send` | Envoi |

Même si le scope Google `compose` permet aussi certains envois côté fournisseur, Jarvis exige le scope
`send` explicite pour son outil d'envoi. Il ne demande pas un droit de lecture implicitement pour envoyer.
Pour pouvoir rapprocher un envoi incertain depuis Jarvis, choisir `readonly` et `send` lors du consentement.
Un consentement limité à `send` peut envoyer, mais son outil de rapprochement reste refusé faute de lecture.

La configuration d'un identifiant est immuable. Une nouvelle configuration utilise un nouvel identifiant.
Un nouveau consentement sur un identifiant existant invalide ses anciens flux et ses anciens jetons locaux ;
les opérations préparées pour l'ancienne génération ne partent pas avec le nouveau compte.

## Flux OAuth et coffre

`commencer()` est appelé par le propriétaire authentifié. L'URL de consentement contient un état opaque
de 256 bits et un challenge PKCE S256. Le vérificateur reste dans le coffre. L'état expire après dix minutes
et est acquis une seule fois, avant tout échange réseau : une réponse perdue ne provoque pas un second
échange du même code. Relancer un consentement génère un nouveau flux.

Le callback dédié exige un unique `state` et un unique `code`. Il ignore les métadonnées Google
`scope`, `authuser`, `prompt`, `hd` et `iss` ; elles ne changent ni les droits ni le compte configuré.
Les autres paramètres et les paramètres répétés sont refusés. Il ne permet pas de modifier une configuration. L'état
serveur le lie au lancement propriétaire, à la connexion et à sa génération ; il fonctionne avec le retour
Google même lorsque le cookie Studio `SameSite=Strict` n'est pas renvoyé lors de cette navigation. Le serveur
ne doit jamais journaliser la requête complète ou afficher code, état, jeton ou erreur brute fournisseur.

Routes du Studio, derrière sa session propriétaire sauf le callback dédié :

- `GET /api/v2/oauth`
- `POST /api/v2/oauth`
- `POST /api/v2/oauth/{id}/commencer`
- `POST /api/v2/oauth/{id}/revoquer`
- `GET /api/v2/oauth/callback?state=…&code=…`

Les jetons vivent dans `JARVIS_STATE_DIR/oauth_prive/registre.json`, fichier régulier en mode `0600`, dans un
répertoire `0700`. Le fichier est remplacé atomiquement et synchronisé sur disque. Un registre corrompu ou
aux permissions trop larges est refusé et conservé. Le coffre reste un fichier local protégé par Linux,
sans chiffrement au repos ni isolation entre agents partageant le même utilisateur ; il ne constitue pas
encore le service de secrets isolé prévu par l'architecture.

Le renouvellement est sérialisé par connexion. La révocation n'attend pas le verrou de renouvellement :
elle supprime les jetons et ferme la génération locale avant d'appeler Google. Un reçu tardif ne réactive
pas la connexion. La rotation d'un refresh token remplace l'ancien ; une réponse de renouvellement sans
nouveau refresh token conserve l'ancien. Une réponse sans `scope` conserve les scopes effectivement accordés,
et ne les élargit pas aux droits demandés mais non consentis.

## Outils Gmail sous mandat

| Outil | Arguments principaux | Destination du mandat |
| --- | --- | --- |
| `courriel.profile` | `connexion_id` | `gmail.googleapis.com` |
| `courriel.search` | `connexion_id`, `requete`, `maximum` facultatif | `gmail.googleapis.com` |
| `courriel.read` | `connexion_id`, `message_id` | `gmail.googleapis.com` |
| `courriel.draft` | `connexion_id`, `destinataire`, `objet`, `texte` | Adresse du destinataire exacte |
| `courriel.send` | `connexion_id`, `destinataire`, `objet`, `texte` | Adresse du destinataire exacte |
| `courriel.reconcile` | `connexion_id`, `operation_id` d'origine | `gmail.googleapis.com` |

Les appels utilisent `jarvis os outils executer demande.json` ou la route de passerelle du Studio.
Le modèle ne fournit ni URL Gmail, ni Authorization, ni message MIME brut, ni From, Cc, Bcc ou Reply-To.
Un seul destinataire simple est accepté. Le corps reste du texte ; les caractères de contrôle dans les
en-têtes sont refusés. Le connecteur construit les en-têtes RFC, dont From propriétaire, Date et Message-ID.
Les jetons sont résolus au dernier moment et les droits sont revérifiés avant chaque requête.

Exemple de demande, à adapter à un mandat créé par le propriétaire :

```json
{
  "operation_id": "projet-exemple:courriel-1",
  "mandat_id": "MA_IDENTIFIANT_REEL",
  "project": "projet-exemple",
  "tool": "courriel.send",
  "arguments": {
    "connexion_id": "gmail-personnel",
    "destinataire": "destinataire@example.test",
    "objet": "Résultat du projet",
    "texte": "Voici le résultat vérifié."
  }
}
```

La lecture retourne du texte et des en-têtes bornés, explicitement marqués comme source non fiable. Le HTML
actif et les pièces jointes ne sont pas exécutés ou récupérés. Les messages trop volumineux peuvent être
refusés par la borne de transport ; cette première tranche n'est pas une synchronisation complète de boîte.

## Envoi incertain et rapprochement

La passerelle persiste l'identité d'opération avant l'appel. Le connecteur dérive un Message-ID stable de
la connexion et de cette identité. Ce Message-ID est une clé de recherche : **Gmail ne garantit pas une
déduplication sur cet en-tête**. Une réponse perdue ou un reçu invalide après le départ d'une écriture reste
`unknown` dans le journal, et un rejeu de la même opération ne renvoie pas le courriel.

`courriel.reconcile` recherche le Message-ID, puis relit les métadonnées de chaque résultat. Il ne confirme
que s'il obtient exactement un reçu avec l'en-tête Message-ID exact et le label Gmail `SENT`, sans page
supplémentaire. Un brouillon, une absence, une autre identité, plusieurs messages ou une recherche partielle
ne prouvent pas l'envoi. L'absence de reçu ne prouve pas non plus que l'envoi n'a pas eu lieu.

Le résultat fournit `confirme`, `statut`, `message_id_rfc`, `recus_confirmes` et, pour un reçu unique, les
identifiants Gmail. Ce connecteur n'efface pas lui-même l'état `unknown` d'une autre opération et ne lance
jamais un second envoi après rapprochement. Une révocation ou annulation ne peut pas retirer un courriel
déjà accepté par Gmail.

## Réseau et preuves

Les destinations nécessaires sont `accounts.google.com` pour le navigateur, `oauth2.googleapis.com` pour
les jetons/révocations et `gmail.googleapis.com` pour Gmail. Configurer le réseau de l'environnement et,
si utilisé, le proxy explicite à hôtes exacts. Aucun domaine, secret ou compte n'est ajouté implicitement.

```bash
python3 -m unittest discover -s tests -p test_oauth.py -v
python3 -m unittest discover -s tests -p test_courriel.py -v
```

Les 23 tests ciblés couvrent PKCE, usage unique concurrent, expiration, générations, fichier privé,
rotation/portée des refresh tokens, révocation et réponse tardive, MIME, scopes, annulation, mandat du
destinataire, envoi incertain sans rejeu et rapprochement positif/négatif. Le transport est contrôlé dans
ces tests. Le consentement, le compte, l'adresse/alias et les quotas réels de Google restent à vérifier.
