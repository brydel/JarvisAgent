# Livraison : missions outillées, modèles et courriel

Cette tranche relie un contrôleur persistant, l'adaptateur OpenAI Responses et la passerelle d'outils.
Le propriétaire peut configurer son modèle, donner un objectif avec des critères, choisir un mandat et
suivre l'exécution depuis le Board. Elle ajoute également MCP stdio et la connexion Google/Gmail.

Les parcours du contrôleur sont exercés avec un modèle de test déclaré et de vrais états locaux. Aucune
inférence OpenAI ni connexion à un compte Google réel n'est validée : les clés et le consentement du compte
ne sont pas disponibles dans cet environnement. Un adaptateur implémenté n'est pas une preuve d'accès au compte.

## Parcours depuis le Board

Le bouton **Missions outillées** ouvre quatre onglets :

1. **Modèle** : identifiant exact du modèle, nom de la variable contenant la clé, plafond de sortie et délai.
   La vérification consulte sa disponibilité sur le compte ; elle ne lance pas d'inférence. Aucune valeur de
   clé n'est saisie dans le navigateur.
2. **Mandats** : projet, outils, destinations exactes, durée, actions et budget réservé. Les appels de modèle
   demandent notamment `model.openai_responses.inference` vers `api.openai.com`. Les outils retenus pour la
   mission doivent aussi être couverts. La révocation ferme les nouveaux départs.
3. **Missions** : objectif, projet, mandat, critères et sélection d'outils. Les formulaires construisent les
   contrats versionnés. La création ne déclenche pas implicitement une inférence ; **Démarrer la mission**
   lance le worker, puis l'interface relit l'état sans garder une requête de modèle ouverte dans le navigateur.
4. **Courriel** : configuration de l'application Google, adresse de retour, scopes et adresse expéditrice.
   **Autoriser dans Google** prépare un véritable flux OAuth PKCE ; l'interface ne présente la connexion
   comme acquise qu'après son retour côté service.

Le panneau montre les tours, les jetons observés, les réservations, les actions et le résultat proposé.
Une réponse finale produit l'état **À vérifier**, pas une réussite déclarée par le modèle. Le propriétaire
ou un relecteur autorisé distinct de l'agent compare le résultat aux critères et fournit commentaire et
références avant acceptation. Un refus est terminal ; il ne relance pas une correction facturable en silence.

Les contrôles **Mettre en pause**, **Reprendre** et **Arrêter la mission** agissent sur le contrôleur et son
jeton d'annulation. Un résultat externe déjà parti peut rester incertain ; la pause ne transforme pas cet
état en échec certain et ne justifie pas un nouvel envoi automatique.

## Contrôleur, modèle et reprise

Chaque run conserve ses contrats, son modèle figé, son historique, ses budgets et son checkpoint dans
SQLite. Modifier la configuration générale du modèle ne change pas le modèle d'un run existant. Une
identité stable déduplique la création, les tours et les opérations d'outils. Verrou, bail et génération
protègent la concurrence et les résultats périmés.

L'adaptateur Responses reçoit le catalogue contrôlé et convertit les appels structurés vers les identifiants
exacts des outils. Le texte d'un objectif ou d'une sortie d'outil ne donne aucun droit. Une réponse sans
usage exploitable, un modèle différent ou un outil absent du profil ne devient pas un effet autorisé.
Les capsules privées nécessaires à la continuation Responses restent dans l'état privé ; elles ne sont
pas affichées dans le Board ni publiées sur le réseau des agents.

Après un crash, le contrôleur reprend les checkpoints et les reçus déjà acquis. Une réponse de modèle ou
d'outil perdue après départ bloque la continuation automatique sous un état inconnu. Cette tranche n'ajoute
pas une commande qui effacerait ce doute pour répéter l'effet.

Le coût par tour est une **estimation réservée**, pas une facture fournisseur ni un plafond bancaire.
Les plafonds de jetons, tours, durée et réservations sont appliqués par Jarvis ; les limites de facturation
du compte fournisseur restent à configurer et vérifier séparément.

## Le réseau libre devient un outil des agents

`communaute.lire`, `communaute.publier` et `communaute.repondre` rejoignent la passerelle. Un agent peut donc
lire les échanges, publier un avis et répondre pendant sa mission lorsque ces outils figurent dans son
profil et son mandat. La destination de ces outils est `usine`.

Omettre `projet` dans leurs arguments cible l'espace global de toute l'usine. Les salons, les sujets et
les discussions restent libres ; aucune tâche ou preuve n'est requise pour discuter. L'auteur provient du
contrôleur, jamais du texte du modèle. La revue d'un livrable demeure distincte d'un échange sur le réseau.

## MCP local et Gmail

**Intégrations** propose les transports HTTPS et **Processus local, stdio**. Pour stdio, le propriétaire
choisit un exécutable absolu, des arguments séparés, un dossier éventuel et les noms des seules variables
à transmettre. La découverte démarre réellement ce programme. Les appels d'outils passent ensuite par le
mandat, avec une destination locale `mcp:<identifiant>`.

Le programme stdio possède les droits du même utilisateur Linux. L'environnement réduit, l'absence de
shell et l'arrêt des descendants ne constituent pas une isolation contre un programme local malveillant.

Le connecteur Gmail fournit profil, recherche, lecture, brouillon, envoi et rapprochement. Les scopes sont
choisis explicitement. Pour un brouillon ou un envoi, le propriétaire déclare l'adresse expéditrice et le
mandat couvre le destinataire exact. Le modèle ne choisit ni le compte, ni un en-tête Authorization, ni un
expéditeur arbitraire. Un Message-ID stable aide au rapprochement, sans garantir une déduplication Gmail.
Une écriture incertaine reste dans le journal sans répétition automatique.

Les jetons OAuth sont conservés côté service dans un fichier local `0600`, sous un répertoire `0700`.
Ce coffre n'est pas chiffré au repos et n'isole pas les agents du même utilisateur Linux. Le secret client
éventuel est une référence de variable ; les jetons ne passent pas dans les formulaires ou les prompts.

Le retour OAuth accepte uniquement une adresse HTTP sur `localhost` ou `127.0.0.1`, avec le chemin
`/api/v2/oauth/callback`. Avec un navigateur situé sur une autre machine, il faut un tunnel ou une
redirection du port local `7718` vers le service. Un retour HTTPS public n'est pas encore pris en charge.

## Commandes disponibles

```bash
jarvis os runtime --help
jarvis os runtime liste
jarvis os runtime voir AR_IDENTIFIANT_REEL
jarvis os modele voir
jarvis os modele verifier
jarvis os oauth liste
jarvis os connexions liste
jarvis os outils liste
```

La configuration propriétaire et l'exécution peuvent aussi utiliser les commandes suivantes, avec des
fichiers adaptés au compte, au mandat et aux contrats réellement enregistrés :

```bash
jarvis os modele configurer modele.json
jarvis os oauth configurer google.json
jarvis os oauth commencer gmail-personnel
jarvis os runtime creer mission-outillee.json
jarvis os runtime executer AR_IDENTIFIANT_REEL
jarvis os runtime pause AR_IDENTIFIANT_REEL
jarvis os runtime reprendre AR_IDENTIFIANT_REEL
jarvis os runtime annuler AR_IDENTIFIANT_REEL
```

Les commandes d'administration exigent le propriétaire ; l'API du Studio utilise sa session authentifiée.
Les anciennes missions documentaires, le chef et les sessions workmux ne sont pas migrés automatiquement
vers cette boucle. Le prototype Temporal reste inchangé et n'acquiert pas les runs locaux implicitement.
Le backlog demeure local ; aucune synchronisation Linear n'est attestée dans cet environnement.

## Vérification de cette tranche

Relevés ciblés des sessions spécialisées, inclus dans la suite Python complète :

| Périmètre | Résultat ciblé |
| --- | --- |
| Runtime cognitif | 25 tests réussis |
| Contrôleur, liaison modèle et workers | 8 tests réussis |
| Adaptateur de modèles | 20 tests réussis |
| OAuth et Gmail | 23 tests réussis |
| Transport MCP stdio | 19 tests réussis sur processus locaux |
| Transport HTTPS du runtime | 11 tests réussis |
| API HTTP OAuth | 9 tests réussis |
| Intégration stdio et passerelle | 13 tests réussis |
| Interface runtime, modèle, OAuth et stdio | 4 parcours Chromium réussis |

La régression complète du Board est passée : **18/18 parcours Chromium**. La suite SDK du prototype
Temporal inchangé est également passée : **17/17 tests**. Le résultat global Python est consigné ci-dessous.

Le parcours principal Chromium crée le modèle et le mandat, exécute le contrôleur et la passerelle,
publie réellement dans le réseau local de test, vérifie le résultat et contrôle sa persistance après
rechargement. Le fournisseur de modèle est un scénario explicitement factice. Les frontières OAuth et
stdio de l'interface utilisent des réponses HTTP contrôlées ; les tests du transport stdio lancent, eux,
de vrais processus locaux. Aucun de ces contrôles n'envoie de courriel réel.

Validation finale du 23 octobre 2026 :

| Vérification | Résultat |
| --- | --- |
| Suite Python complète | 700 exécutés : 598 réussis, 102 ignorés ; aucune erreur |
| Parcours Chromium complets | 18 réussis |
| SDK Temporal séparé | 17 réussis ; serveur réel non validé |
| Build TypeScript/Vite | Réussi, sources et assets compilés livrés |
| Syntaxe Bash, compilation Python et aide CLI | Réussies |
| Modèles AGENTS/CLAUDE | Identiques |
| ShellCheck comparé à HEAD | 15 diagnostics préexistants, aucun nouveau |
| API du service cloud sur 7718 | Sept routes répondent 200 avec session ; runtime sans session : 401 |
| Démon, cockpit et Studio | Redémarrés dans jarvis-cloud ; workmux sans target_errors |
| Revue indépendante | Terminée ; arrêt MCP et écriture incertaine corrigés puis retestés |

Les tests existants d'aperçu et de Studio émettent des avertissements de sockets non fermées ; la suite
se termine avec le code 0. Les tests d'arrêt ajoutés à ce lot joignent leurs handlers et leurs processus.
Le journal complet est conservé dans `/workspace/.jarvis-cloud/runtime-suite-complete.log`, avec les
résultats Chromium, Temporal et le contrôle HTTP dans le même répertoire de l'environnement.

Le brouillon cloud sauvegardé conserve les paramètres précédents et ajoute les destinations
`api.openai.com`, `accounts.google.com`, `oauth2.googleapis.com` et `gmail.googleapis.com`.
Les exigences personnelles `JARVIS_OPENAI_API_KEY` et `JARVIS_GOOGLE_CLIENT_SECRET` contiennent uniquement
des métadonnées, aucune valeur. Le secret client Google est facultatif selon le type d'application.
L'enregistrement du brouillon ne l'active pas : enregistrer les paramètres puis publier l'environnement,
ajouter les identifiants dans son gestionnaire de secrets et configurer les références depuis le Board.
Aucune connexion ni inférence réelle n'a été créée lors du contrôle de démarrage.

## Documents spécialisés

- [Boucle cognitive, checkpoints et revue](RUNTIME_AGENT.md)
- [Adaptateur OpenAI Responses](MODELES_RUNTIME.md)
- [OAuth Google, Gmail et rapprochement](OAUTH_COURRIEL.md)
- [MCP stdio et exécution locale](MCP_STDIO.md)
- [Passerelle web/MCP et opérations](OUTILS_CONNEXIONS.md)
- [Réseau libre de l'usine](COMMUNAUTE.md)
- [Lot précédent et services cloud](LIVRAISON_USINE.md)
- [Prototype Temporal séparé](TEMPORAL.md)
