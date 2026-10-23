# Premier prototype Temporal — JOS-019

Le code du service est disponible sous `services/workflows_temporal/`. Le SDK `temporalio==1.34.0` et ses
dépendances sont isolés et épinglés. Le moteur local conserve toutes ses missions : aucun transfert de
propriété vers Temporal n'est activé dans cette tranche.

## Ce que le service exécute

Un projet fourni explicitement contient jusqu'à 32 étapes, chacune avec ses dépendances, son outil,
son mandat et son délai. Le tri du DAG est déterministe. Trois activités au maximum sont lancées par
vague. Les appels HTTP, l'authentification et les outils restent dans les activités ; le workflow ne
lit ni variable d'environnement, ni fichier, ni réseau, ni horloge système.

Le workflow accepte les signaux `suspendre`, `reprendre`, `annuler` et la requête `etat`. Une pause
empêche les prochains départs. Une annulation demande l'arrêt des activités et bloque les étapes
dépendantes. Un effet externe déjà parti nécessite toujours un rapprochement côté passerelle.
Le client HTTP local est borné à 15 secondes par requête ; l'annulation ne garantit pas qu'un serveur
externe a interrompu une écriture déjà reçue.

Chaque activité appelle `POST /api/v2/outils/executer`, avec une identité dérivée du projet et de
l'étape, stable lors des retries et redémarrages. La passerelle applique le mandat et journalise
l'opération. Un état `unknown` bloque le workflow sans répétition aveugle. Les erreurs transitoires
du transport et les opérations en cours peuvent être interrogées à nouveau avec la même identité,
au plus trois tentatives. Le client refuse la réutilisation d'un identifiant de workflow terminé.

## Lancer explicitement

Depuis le dépôt, après installation du venv décrite dans le README du service :

```bash
source /workspace/.jarvis-cloud/activate.sh
export PYTHONPATH="$PWD/services/workflows_temporal"

# Studio Jarvis déjà démarré ; son jeton reste dans son fichier de configuration.
export JARVIS_STUDIO_URL=http://127.0.0.1:7717

# Serveur Temporal dev persistant et worker. Le CLI officiel doit être téléchargeable.
/workspace/.jarvis-cloud/temporal-venv/bin/python -m jarvis_temporal dev
```

Si un CLI Temporal officiel est déjà installé et vérifié, `JARVIS_TEMPORAL_CLI` peut indiquer son chemin.
La commande `worker` se connecte à un serveur déjà démarré (`TEMPORAL_ADDRESS`, défaut `127.0.0.1:7233`).
Le namespace vaut `default` et la file de tâches `jarvis-prototype-v1`. Le serveur dev utilise une base
persistée sous `$JARVIS_STATE_DIR/temporal-prototype/`, séparée des missions locales.

Dans un autre terminal avec le même `PYTHONPATH` :

```bash
# Remplacer d'abord le mandat fictif dans une copie de l'exemple.
/workspace/.jarvis-cloud/temporal-venv/bin/python -m jarvis_temporal valider services/workflows_temporal/exemples/projet.json
/workspace/.jarvis-cloud/temporal-venv/bin/python -m jarvis_temporal lancer services/workflows_temporal/exemples/projet.json
/workspace/.jarvis-cloud/temporal-venv/bin/python -m jarvis_temporal etat jarvis-prototype-recherche-documentation
/workspace/.jarvis-cloud/temporal-venv/bin/python -m jarvis_temporal signal jarvis-prototype-recherche-documentation suspendre
/workspace/.jarvis-cloud/temporal-venv/bin/python -m jarvis_temporal signal jarvis-prototype-recherche-documentation reprendre
```

Les quatre noms de phases n'ajoutent aucune capacité cognitive. L'exemple effectue deux lectures de
documentation si le mandat les autorise ; il ne démontre pas une recherche, une production ou une
revue métier autonome.

## Authentification et historique

Le worker utilise le Studio local et ouvre une session authentifiée avec `X-Jarvis-Studio: 1`.
Le jeton est lu au dernier moment dans `$JARVIS_CONFIG_DIR/studio_jeton` (ou dans le fichier référencé
par `JARVIS_STUDIO_TOKEN_FILE`). Il reste hors du payload et de l'historique du workflow. Le client
de ce prototype accepte uniquement HTTP en boucle locale ; le déploiement distant avec TLS et
identité de service reste à construire.

Ne pas placer de secret dans les arguments d'outils. Les clés de secret usuelles sont refusées par
le contrat, mais cette validation ne saurait reconnaître tous les secrets possibles. Les résultats
d'outils font partie de l'historique Temporal : la passerelle doit les expurger et le stockage de
l'historique doit rester personnel. Les références de mandat sont des identifiants, jamais des jetons.

## Vérification réalisée et limite de l'environnement

- Installation du SDK depuis PyPI avec TLS : réussie.
- 17 tests réussis dans le venv : contrat strict, DAG et identité stable, vrai HTTP local authentifié,
  refus après annulation, erreurs de transport, exécution des activités dans le SDK et préparation
  de la définition par le sandbox Temporal.
- Tentative de démarrage du serveur officiel par le SDK : non réussie. Le proxy renvoie
  `Tunnel connection failed: 403 Forbidden` pour `https://temporal.download`.
- Reprise d'un vrai serveur, replay d'un historique réel et évolution de version : non validés dans
  cet environnement tant que ce téléchargement reste bloqué. Aucun test factice n'est présenté
  comme une validation de cette propriété.

Le script explicite suivant échoue si le serveur ne démarre pas. Avec un vrai serveur, il vérifie la
pause, le remplacement du worker, un retry conservant son identité d'opération, l'annulation et le
replay SDK de l'historique enregistré ; ses activités restent factices et ne contactent aucun modèle.

```bash
PYTHONPATH=services/workflows_temporal /workspace/.jarvis-cloud/temporal-venv/bin/python services/workflows_temporal/verifier_reprise.py
# Ou --adresse 127.0.0.1:7233 pour un serveur de test existant.
```

Pour rejouer un historique conservé :

```bash
/workspace/.jarvis-cloud/temporal-venv/bin/python -m jarvis_temporal historique IDENTIFIANT /tmp/historique.json
/workspace/.jarvis-cloud/temporal-venv/bin/python -m jarvis_temporal replay IDENTIFIANT /tmp/historique.json
```

JOS-019 reste en cours : il faudra enregistrer puis rejouer des historiques avec une version suivante
compatible du workflow, démontrer la continuation d'une ancienne exécution et mesurer la reprise
d'un serveur redémarré. JOS-020 devra ensuite établir le handoff durable `local → handoff_pending → temporal`
par outbox, avec propriétaire unique et rapprochement des accusés perdus.
