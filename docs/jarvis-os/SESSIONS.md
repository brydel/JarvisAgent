# Sessions spécialisées — Jarvis OS personnel

Les trois audits ont été réalisés. Pour la première tranche F0, trois sessions spécialisées ont implémenté
les contrats (`f0_contracts`), les mandats (`f0_mandates`) et le diagnostic (`f0_capabilities`). Une quatrième,
`review_f0_policy`, a relu le lot indépendamment ; la session principale a intégré et vérifié le runtime.
Ces sessions de développement sont terminées. Elles ne sont pas des agents déployés dans Jarvis.

La tranche suivante a réparti le travail entre `runtime_cognitif` (boucle durable), `modeles_runtime`
(OpenAI Responses et transport), `oauth_courriel` (PKCE et Gmail), `mcp_stdio` (processus MCP),
`interface_runtime` (Board et parcours Chromium) et `revue_runtime` (revue indépendante puis tests du
contrôleur). La session principale a relié les modules, les mandats, le réseau interne, les routes et
l'arrêt des services. Ces spécialistes sont des sessions de développement terminées ; ils ne constituent
pas un essaim de modèles déployé. Voir [LIVRAISON_RUNTIME.md](LIVRAISON_RUNTIME.md).
Les autres affectations restent préparées. Voir [les preuves et limites de la tranche](IMPLEMENTATION.md).

## Contrat de lancement commun

Lire AGENTS.md puis le ticket entier et ses dépendances. Ne prendre que des tâches prêtes. Mettre le ticket en cours et publier son plan lorsque Linear est connecté. Définir le périmètre de fichiers et les contrats avant d’éditer. Conserver les modifications existantes. Chaque tâche reçoit les outils réellement vérifiés et le mandat nécessaire ; un rôle ne donne pas de droits. Respecter le cœur Python sans dépendance externe ; les SDK vont dans des services séparés. La session de relecture ne modifie pas le travail de l’auteur et contrôle la version exacte.

## Affectations préparées

| Ticket | Phase | Responsable agent | Relecteur | Prérequis |
| --- | --- | --- | --- | --- |
| JOS-001 | F0 | Architecte agentique | Ingénieur runtime agentique | Aucun |
| JOS-002 | F0 | Ingénieur politique d’autonomie | QA indépendante des agents | Aucun |
| JOS-003 | F0 | SRE des exécutants | QA indépendante des agents | Aucun |
| JOS-004 | F1 | Ingénieur fiabilité distribuée | Ingénieur workflows Temporal | JOS-001 |
| JOS-005 | F1 | Ingénieur fiabilité distribuée | QA indépendante des agents | JOS-001 |
| JOS-006 | F1 | Ingénieur runtime agentique | SRE des exécutants | JOS-001, JOS-003 |
| JOS-007 | F1 | Ingénieur fiabilité distribuée | Ingénieur courriel et effets externes | JOS-002, JOS-004, JOS-006 |
| JOS-008 | F2 | Ingénieur MCP et OAuth | Ingénieur politique d’autonomie | JOS-002, JOS-003 |
| JOS-009 | F2 | Ingénieur MCP et OAuth | QA indépendante des agents | JOS-008 |
| JOS-010 | F2 | Ingénieur runtime agentique | Ingénieur fiabilité distribuée | JOS-001, JOS-002, JOS-007, JOS-008 |
| JOS-011 | F2 | Ingénieur recherche et navigateur | QA indépendante des agents | JOS-009, JOS-010 |
| JOS-012 | F2 | Ingénieur courriel et effets externes | Ingénieur fiabilité distribuée | JOS-007, JOS-008, JOS-010 |
| JOS-013 | F2 | Ingénieur MCP et OAuth | SRE des exécutants | JOS-009, JOS-010 |
| JOS-014 | F3 | Ingénieur runtime agentique | Architecte agentique | JOS-001, JOS-002, JOS-003, JOS-010 |
| JOS-015 | F3 | Ingénieur prompts et évaluations | QA indépendante des agents | JOS-001, JOS-002, JOS-014 |
| JOS-016 | F3 | Ingénieur mémoire et contexte | QA indépendante des agents | JOS-001, JOS-008 |
| JOS-017 | F3 | Architecte agentique | SRE des exécutants | JOS-014, JOS-015 |
| JOS-018 | F3 | QA indépendante des agents | Ingénieur prompts et évaluations | JOS-014, JOS-015, JOS-016 |
| JOS-019 | F4 | Ingénieur workflows Temporal | Ingénieur fiabilité distribuée | JOS-001, JOS-003 |
| JOS-020 | F4 | Ingénieur workflows Temporal | Architecte agentique | JOS-004, JOS-006, JOS-007, JOS-019 |
| JOS-021 | F4 | Ingénieur workflows Temporal | QA indépendante des agents | JOS-011, JOS-012, JOS-013, JOS-014, JOS-017, JOS-018, JOS-020 |
| JOS-022 | F5 | Ingénieur frontend intégrations | Designer et ingénieur observabilité | JOS-008, JOS-009, JOS-010 |
| JOS-023 | F5 | Designer et ingénieur observabilité | Ingénieur frontend intégrations | JOS-014, JOS-020, JOS-022 |
| JOS-024 | F5 | Ingénieur frontend intégrations | Ingénieur politique d’autonomie | JOS-002, JOS-021, JOS-022, JOS-023 |
| JOS-025 | F6 | QA indépendante des agents | Architecte agentique | JOS-011, JOS-012, JOS-013, JOS-016, JOS-018, JOS-021, JOS-024 |
| JOS-026 | F6 | Ingénieur fiabilité distribuée | QA indépendante des agents | JOS-007, JOS-020, JOS-025 |
| JOS-027 | F6 | Ingénieur prompts et évaluations | QA indépendante des agents | JOS-015, JOS-018, JOS-025 |
| JOS-028 | F6 | SRE des exécutants | Ingénieur fiabilité distribuée | JOS-026, JOS-027 |
| JOS-029 | F3 | Ingénieur runtime agentique | Ingénieur prompts et évaluations | JOS-014 |
| JOS-030 | F3 | Ingénieur runtime agentique | QA indépendante des agents | JOS-001 |

## Brief de chaque spécialité

### Architecte agentique

Identité de session : `architecte-agentique`. Tickets : JOS-001, JOS-017.

Mission : Contrats communs, séparation des responsabilités et migration mesurable.

Entrées : ticket, contrats versionnés, preuves des prérequis, état actuel du projet et mandat. Sorties : changement limité au ticket, critères démontrés, preuves reproductibles, limites restantes et résumé de passage. Terminer avec les commandes exécutées, la version relue et les liens d’artefacts ; ne pas confondre plan, simulation et résultat réel.

### Ingénieur politique d’autonomie

Identité de session : `politique-autonomie`. Tickets : JOS-002.

Mission : Mandats personnels persistés, autorisations effectives et révocation sans demandes répétées.

Entrées : ticket, contrats versionnés, preuves des prérequis, état actuel du projet et mandat. Sorties : changement limité au ticket, critères démontrés, preuves reproductibles, limites restantes et résumé de passage. Terminer avec les commandes exécutées, la version relue et les liens d’artefacts ; ne pas confondre plan, simulation et résultat réel.

### SRE des exécutants

Identité de session : `sre-execution`. Tickets : JOS-003, JOS-028.

Mission : Disponibilité, capacités, processus, reprise, exploitation et restauration.

Entrées : ticket, contrats versionnés, preuves des prérequis, état actuel du projet et mandat. Sorties : changement limité au ticket, critères démontrés, preuves reproductibles, limites restantes et résumé de passage. Terminer avec les commandes exécutées, la version relue et les liens d’artefacts ; ne pas confondre plan, simulation et résultat réel.

### Ingénieur fiabilité distribuée

Identité de session : `fiabilite-distribuee`. Tickets : JOS-004, JOS-005, JOS-007, JOS-026.

Mission : Transactions, outbox/inbox, effets incertains, idempotence et concurrence.

Entrées : ticket, contrats versionnés, preuves des prérequis, état actuel du projet et mandat. Sorties : changement limité au ticket, critères démontrés, preuves reproductibles, limites restantes et résumé de passage. Terminer avec les commandes exécutées, la version relue et les liens d’artefacts ; ne pas confondre plan, simulation et résultat réel.

### Ingénieur runtime agentique

Identité de session : `runtime-outils`. Tickets : JOS-006, JOS-010, JOS-014, JOS-029.

Mission : Sessions effectives, outils typés, streaming d’événements, annulation et budgets.

Entrées : ticket, contrats versionnés, preuves des prérequis, état actuel du projet et mandat. Sorties : changement limité au ticket, critères démontrés, preuves reproductibles, limites restantes et résumé de passage. Terminer avec les commandes exécutées, la version relue et les liens d’artefacts ; ne pas confondre plan, simulation et résultat réel.

### Ingénieur MCP et OAuth

Identité de session : `integrations-mcp-oauth`. Tickets : JOS-008, JOS-009, JOS-013.

Mission : Connexions, secrets côté service, découverte, scopes, tests réels et renouvellement.

Entrées : ticket, contrats versionnés, preuves des prérequis, état actuel du projet et mandat. Sorties : changement limité au ticket, critères démontrés, preuves reproductibles, limites restantes et résumé de passage. Terminer avec les commandes exécutées, la version relue et les liens d’artefacts ; ne pas confondre plan, simulation et résultat réel.

### Ingénieur recherche et navigateur

Identité de session : `recherche-navigateur`. Tickets : JOS-011.

Mission : Recherche sourcée, navigation isolée, preuves et reprise d’étapes web.

Entrées : ticket, contrats versionnés, preuves des prérequis, état actuel du projet et mandat. Sorties : changement limité au ticket, critères démontrés, preuves reproductibles, limites restantes et résumé de passage. Terminer avec les commandes exécutées, la version relue et les liens d’artefacts ; ne pas confondre plan, simulation et résultat réel.

### Ingénieur courriel et effets externes

Identité de session : `courriel-fiable`. Tickets : JOS-012.

Mission : Graph/Gmail API, brouillons, envois délégués et réconciliation fournisseur.

Entrées : ticket, contrats versionnés, preuves des prérequis, état actuel du projet et mandat. Sorties : changement limité au ticket, critères démontrés, preuves reproductibles, limites restantes et résumé de passage. Terminer avec les commandes exécutées, la version relue et les liens d’artefacts ; ne pas confondre plan, simulation et résultat réel.

### Ingénieur workflows Temporal

Identité de session : `workflow-temporal`. Tickets : JOS-019, JOS-020, JOS-021.

Mission : DAG durable, signaux, timers, replay, versions et migration à propriétaire unique.

Entrées : ticket, contrats versionnés, preuves des prérequis, état actuel du projet et mandat. Sorties : changement limité au ticket, critères démontrés, preuves reproductibles, limites restantes et résumé de passage. Terminer avec les commandes exécutées, la version relue et les liens d’artefacts ; ne pas confondre plan, simulation et résultat réel.

### Ingénieur mémoire et contexte

Identité de session : `memoire-contextes`. Tickets : JOS-016.

Mission : Index hybride, provenance, invalidation, isolation et contexte utile.

Entrées : ticket, contrats versionnés, preuves des prérequis, état actuel du projet et mandat. Sorties : changement limité au ticket, critères démontrés, preuves reproductibles, limites restantes et résumé de passage. Terminer avec les commandes exécutées, la version relue et les liens d’artefacts ; ne pas confondre plan, simulation et résultat réel.

### Ingénieur prompts et évaluations

Identité de session : `prompts-evaluations`. Tickets : JOS-015, JOS-027.

Mission : Prompts compilés, tests métier, comparaison de modèles, canaris et coûts.

Entrées : ticket, contrats versionnés, preuves des prérequis, état actuel du projet et mandat. Sorties : changement limité au ticket, critères démontrés, preuves reproductibles, limites restantes et résumé de passage. Terminer avec les commandes exécutées, la version relue et les liens d’artefacts ; ne pas confondre plan, simulation et résultat réel.

### Ingénieur frontend intégrations

Identité de session : `frontend-integrations`. Tickets : JOS-022, JOS-024.

Mission : Parcours OAuth/MCP réels, états de connexion et commandes persistées.

Entrées : ticket, contrats versionnés, preuves des prérequis, état actuel du projet et mandat. Sorties : changement limité au ticket, critères démontrés, preuves reproductibles, limites restantes et résumé de passage. Terminer avec les commandes exécutées, la version relue et les liens d’artefacts ; ne pas confondre plan, simulation et résultat réel.

### Designer et ingénieur observabilité

Identité de session : `ux-observabilite`. Tickets : JOS-023.

Mission : Graphe lisible des runs, outils, preuves, dépendances et causes d’attente.

Entrées : ticket, contrats versionnés, preuves des prérequis, état actuel du projet et mandat. Sorties : changement limité au ticket, critères démontrés, preuves reproductibles, limites restantes et résumé de passage. Terminer avec les commandes exécutées, la version relue et les liens d’artefacts ; ne pas confondre plan, simulation et résultat réel.

### QA indépendante des agents

Identité de session : `qa-independante`. Tickets : JOS-018, JOS-025.

Mission : Vérification métier, défauts adversariaux, pannes et preuves reproductibles.

Entrées : ticket, contrats versionnés, preuves des prérequis, état actuel du projet et mandat. Sorties : changement limité au ticket, critères démontrés, preuves reproductibles, limites restantes et résumé de passage. Terminer avec les commandes exécutées, la version relue et les liens d’artefacts ; ne pas confondre plan, simulation et résultat réel.

## Ordre de départ

JOS-001, JOS-002 et JOS-003 sont les premières tâches, en parallèle dans la limite de capacité réelle. Le prototype Temporal JOS-019 peut suivre les contrats pendant que JOS-004/005/006 établissent la fiabilité. La passerelle et l’interface avancent sur les mêmes schémas. Le pilote attend toutes ses dépendances ; les effets externes en écriture attendent le journal, la cancellation, le mandat et les connexions vérifiées.

Limiter initialement à au plus trois sessions selon JOS-003, les quotas et les budgets (le profil actuel peut n’admettre que deux exécutants). La relecture consomme aussi cette capacité ; la planifier quand un lot est prêt. Ajuster après mesure. Chaque module mutable a un auteur à la fois ou un découpage de propriété explicite.


## Sessions de cette livraison usine

Six sessions de réalisation ont travaillé en parallèle : `f1_durabilite`, `f1_annulation`,
`communaute_backend`, `communaute_frontend`, `passerelle_outils` et `workflow_temporal`.
`review_f0_policy` a assuré une relecture indépendante ; l'auteur de l'annulation a aussi relu l'outbox.
La session principale a raccordé API, CLI, prompts, notifications, arrêt du démon et services cloud.
Ces sessions de développement sont terminées. Les services actifs et les blocages des modèles/Temporal
sont décrits dans [LIVRAISON_USINE.md](LIVRAISON_USINE.md).

Affectation ajoutée à la demande du propriétaire : JOS-030 (F3), réseau libre de toute l'usine,
responsable Ingénieur runtime agentique, relecteur QA indépendante, prérequis JOS-001.
