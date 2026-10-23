# Première tranche implémentée — socle F0

Les contrats et le diagnostic sont maintenant utilisables dans le code. Le registre des mandats est une
fondation locale ; l'exécution d'outils externes et l'harmonisation complète des politiques restent des lots suivants.

Ce document décrit la première tranche. La [livraison usine suivante](LIVRAISON_USINE.md) ajoute le réseau
libre des agents, la passerelle web/MCP, l'outbox et l'annulation ; ses preuves et limites sont à lire séparément.

## Ce qui fonctionne

- `contrats.py` publie et valide AgentSpec, TaskSpec et RunSpec v1. Types stricts, copies indépendantes,
  empreintes canoniques et distinction `null` (inconnu) / zéro (zéro explicite).
- Le moteur ajoute ces contrats à ses enveloppes. Le runner refuse une extension incohérente avec son profil
  documentaire avant de démarrer la tâche ; les enveloppes v1 historiques sans extension restent acceptées.
- Les prompts de sessions workmux et les observations du Board utilisent les mêmes schémas. Le rôle/modèle
  observé vient du registre des tâches. Une session non identifiée reste telle ; un statut workmux « done »
  ne devient pas à lui seul une réussite métier prouvée dans le nouveau contrat.
- `mandats.py` conserve des mandats à périmètre exact : projet, outils, destinations, expiration, budget,
  nombre d'actions. Révocation, réservation atomique et idempotence d'operation_id sont disponibles.
  Les états JSON et SQLite sont testés. Un registre corrompu est refusé et conservé.
- `capacites.py` distingue les CLI observés, les permissions déclarées et les connexions/inférences non vérifiées.
  Aucun appel de modèle n'est lancé par le diagnostic. MCP est lu comme métadonnées, sans commandes ni secrets.
- Le Studio expose les schémas, capacités et mandats en lecture sous sa session authentifiée. Une corruption
  du registre de mandats renvoie 503 ; aucune autorisation n'est déduite.

## Commandes

Depuis le dépôt installé et son environnement habituel :

```bash
bin/jarvis os diagnostic
bin/jarvis os schemas
bin/jarvis os valider agent docs/jarvis-os/exemples/contrats/agent-documentaire.json
bin/jarvis os preflight docs/jarvis-os/exemples/contrats/agent-outille.json docs/jarvis-os/exemples/contrats/tache-outille.json
bin/jarvis os mandat liste
bin/jarvis os mandat --help
```

Le préflight retourne 2 quand des prérequis manquent, avec leurs raisons en JSON. Dans cette première tranche,
une inférence réelle n'est pas testée : CLI installé et modèle utilisable sont deux preuves différentes.
Les exemples outillés demandent des connecteurs futurs et un mandat fictif ; leur refus est donc attendu.

`bin/jarvis os diagnostic --reseau` fait une sonde explicite HEAD HTTPS vers `pypi.org`, avec TLS vérifié et
sans redirection. Ce résultat n'atteste ni recherche web générale ni accès aux services privés.

Un propriétaire devant son terminal peut créer/révoquer un mandat avec `os mandat creer <fichier>` et
`os mandat revoquer <id>`. Adapter d'abord le projet, les outils et une expiration proche dans l'exemple.
L'agent chef et les appels sans terminal ne peuvent pas créer ou révoquer via cette commande.
`os mandat verifier <id> <demande.json>` n'exécute rien et ne consomme aucun quota.

## API de lecture

- `GET /api/v2/os/schemas`
- `GET /api/v2/os/capacites` (aucune sonde réseau implicite)
- `GET /api/v2/os/mandats`
- Les sessions de `GET /api/v2/activite` incluent leur projection `contrats`.

Ces routes exigent la session du Studio. Aucune route HTTP de création/révocation de mandat ou de lancement
d'outil n'est ajoutée à ce lot. La page de connexion MCP/OAuth reste à réaliser en F5 avec les services F2.

## Frontières importantes

`autoriser()` est un préflight, `reserver()` consomme le quota prévu une fois, et aucune des deux fonctions
n'envoie de message ou ne déploie de code. Une réservation n'est pas un reçu fournisseur. La passerelle
devra recontrôler le mandat avant l'effet et gérer les résultats incertains.

Les fichiers d'état restent sous le même utilisateur Linux. Les champs `par` et `owner` ne sont pas une
authentification système ; l'isolation du coffre et du plan de contrôle est encore à construire. Les contrôles
historiques L3/L4 restent actifs : la création d'un mandat n'ouvre pas les anciennes voies d'exécution.

Les inconnues de budget des anciennes sessions restent `null`. Un contrat ne fait pas respecter à lui seul
une nouvelle limite de tokens, de temps ou de dépenses. La revue documentaire historique reste une revue de
forme ; les preuves d'acceptation métier sont prévues en JOS-018.

## Vérification

```bash
python3 -m unittest discover -s tests
python3 -m unittest discover -s tests -p 'test_contrats.py' -v
python3 -m unittest discover -s tests -p 'test_mandats.py' -v
python3 -m unittest discover -s tests -p 'test_capacites.py' -v
python3 -m unittest discover -s tests -p 'test_os_runtime.py' -v
```

Le lot est intégré au workflow CI existant. Les tests de runtime vérifient notamment une vraie transition de
mission avec fournisseur factice, le refus d'un contrat élargi, la compatibilité v1, le spécialiste du registre,
un fournisseur personnalisé et le mandat local sans destination. Les tests factices ne prétendent pas valider
une connexion réelle Claude, OpenAI, email ou MCP.

Résultats dans l'environnement cloud lors de cette livraison :

- Suite Python complète : 453 tests exécutés, 351 réussis, 102 ignorés.
- Parcours Chromium `activite.spec.ts` et `product.spec.ts` : 9 réussis.
- Serveur Studio démarré sur un port éphémère : refus sans session (401), puis lecture authentifiée
  des trois routes OS (200, JSON valide). L'inférence reste explicitement non vérifiée.
- Syntaxe Bash, compilation Python, aide CLI et `git diff --check` : réussis.
- ShellCheck : 15 diagnostics déjà présents sur `HEAD`, aucun nouveau diagnostic sur les scripts modifiés.
- Relecture indépendante : les défauts d'intégration relevés ont été corrigés et couverts par les tests.

Suite du chantier : outbox/inbox durable (JOS-004), acceptation atomique des propositions (JOS-005), puis
annulation réelle du processus et des outils à la perte de bail (JOS-006), avant les écritures externes.
