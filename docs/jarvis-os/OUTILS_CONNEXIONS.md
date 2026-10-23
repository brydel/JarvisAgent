# Passerelle d'outils et connexions MCP HTTP

Cette tranche ajoute un outil de lecture HTTPS et un client MCP Streamable HTTP réellement exécutables.
Le cœur reste en bibliothèque standard Python. Le registre des connexions et le journal d'opérations
utilisent des tables dédiées dans `jarvis.db`, également lorsque les états historiques sont en JSON.

## Contrats Python

```python
from jarvis import connexions, outils

connexion = connexions.enregistrer({
    "id": "recherche",
    "nom": "Mon serveur de recherche",
    "type": "mcp_http",
    "url": "https://mcp.example.invalid/mcp",
    "token_env": "JARVIS_RECHERCHE_TOKEN",
    "outils_autorises": [],
}, par="proprietaire")

catalogue = connexions.decouvrir("recherche")
# Après lecture du catalogue, le propriétaire sélectionne des noms exacts déjà découverts.
connexion = connexions.configurer_outils("recherche", ["chercher"], par="proprietaire")
```

`token_env` nomme une variable injectée dans le service. Sa valeur n'est jamais persistée, renvoyée au
navigateur ou ajoutée au prompt. L'URL et la référence sont immuables : révoquer puis créer un autre
identifiant pour changer de serveur. Les fonctions d'administration supposent que l'appelant authentifie
le propriétaire. `par` seul n'est pas une authentification.

`lister()`, `get(id)`, `decouvrir(id)`, `configurer_outils(id,noms,par=...)` et `revoquer(id,par=...)`
retournent des métadonnées publiques sans URL complète, nom de variable de credential ni token.
La découverte réalise `initialize`, `notifications/initialized`, puis `tools/list` avec pagination bornée.
Les réponses JSON et SSE sont prises en charge. Les sessions et versions négociées sont transmises ;
aucune capacité sampling, roots ou exécution de commandes n'est annoncée au serveur.

## Un appel sous mandat

```python
resultat = outils.executer({
    "operation_id": "projet-demo:recherche:etape-1",
    "mandat_id": "MA-identifiant-fourni-par-le-proprietaire",
    "project": "projet-demo",
    "tool": "web.fetch",
    "arguments": {"url": "https://pypi.org/", "maximum": 64000, "timeout": 10},
    "cost_cents": 0,
}, par="agent:recherche")
```

Le mandat doit nommer exactement le projet, l'outil et l'hôte. Pour un outil MCP, l'identifiant est
`mcp.<connexion>.<nom_exact>` ; le périmètre de destination est l'hôte du serveur MCP. Cela ne remplace
pas une politique sémantique sur les arguments du fournisseur : un connecteur courriel devra contrôler
séparément les destinataires avant de proposer `email.send`.

`outils.catalogue()` ne lance aucune découverte réseau. Il publie `web.fetch` et les outils MCP déjà
découverts et sélectionnés. La passerelle valide un sous-ensemble explicite de JSON Schema : objets,
tableaux, types, champs requis, propriétés supplémentaires, énumérations, constantes et bornes simples.
Une contrainte non prise en charge, notamment `$ref`, les combinateurs ou les expressions régulières,
fait refuser l'appel avant consommation. Le fournisseur conserve sa validation complète.

Le journal lie `operation_id` à l'empreinte de la requête entière, sans conserver les arguments bruts.
Les statuts sont `prepared`, `in_progress`, `succeeded`, `failed`, `unknown`. Une opération existante ne
redémarre pas son effet ; seuls les préparatifs interrompus avant tout départ peuvent continuer. Après
un départ sans reçu durable, elle devient `unknown`. Un timeout MCP peut cacher une écriture réussie :
aucun rejeu automatique n'est effectué. `operation(id)` et `operations(project,limite=100)` permettent
l'inspection. Le rapprochement fournisseur des résultats inconnus reste à construire.

Les verrous d'opération empêchent deux départs concurrents ; ils sont libérés par le noyau après un
crash. Le mandat est réservé puis recontrôlé avant le départ et de nouveau avant `tools/call`, après
l'initialisation MCP. Les révocations bloquent les prochains appels. Aucun réseau n'est effectué sous
transaction SQL. Une réservation représente un coût prévu, pas une facture ou un plafond fournisseur
prouvé ; elle n'est pas remboursée implicitement après panne.

## Réseau

En accès direct, la passerelle refuse les IP privées, locales et réservées et les résolutions mixtes.
Le socket utilise exactement l'adresse publique validée, avec SNI et certificat du nom d'origine.
Les redirections, credentials d'URL, paramètres d'URL contenant des clés usuelles de secrets, ports
autres que 443 et contenus compressés sont refusés. Les lectures sont bornées en taille et délai.
Chaque requête réseau s'exécute dans un sous-processus arrêté à échéance monotone, DNS, TLS, en-têtes
et corps compris. Un serveur qui envoie quelques octets sans terminer ne remet pas le délai à zéro.
Pour SSE, la lecture s'arrête dès l'événement JSON-RPC corrélé complet, même si le flux reste ouvert.
Les textes retournés sont marqués `source_non_fiable` ; ils ne sont pas des instructions de contrôle.

Un environnement cloud peut nécessiter son proxy d'egress. Celui-ci n'est jamais hérité implicitement.
Le propriétaire peut injecter `JARVIS_HTTPS_PROXY` (proxy HTTP CONNECT de confiance) et
`JARVIS_PROXY_HOTES_AUTORISES` (noms exacts séparés par des virgules). L'hôte cible doit être présent
dans cette liste ; aucun joker, hôte local ou adresse littérale n'est accepté. Le TLS de la cible reste
vérifié. Dans ce mode, **le proxy est la frontière de confiance pour la résolution et le filtrage des IP
finales** : son adresse de destination n'est pas observable par le client CONNECT. Il doit refuser
l'accès aux réseaux privés et réservés. Les credentials éventuels du proxy ne sont jamais affichés.

Dans l'environnement de développement, une lecture réelle de `https://pypi.org/` via ce proxy configuré
explicitement a renvoyé HTTP 200, 27 884 octets, avec vérification TLS active. Cela prouve cette lecture
seulement ; aucun compte MCP, accès général à Internet, fournisseur email ou cycle OAuth n'est déclaré
vérifié par ce résultat. Le client MCP a été testé sur un serveur TCP local contrôlé, en JSON et SSE,
y compris un flux qui reste ouvert après sa réponse. Les 34 tests ciblés vérifient aussi le watchdog
DNS, les retraits d'outils pendant un handshake, la sélection modifiée pendant une découverte,
l'idempotence concurrente et les réponses perdues, avec mandats JSON et SQLite.

Le service de coffre isolé, OAuth, MCP stdio, les connecteurs de courriel et le rapprochement des reçus
restent des lots suivants. Aucun courriel n'a été envoyé et aucun appel de modèle payant n'a été lancé.
