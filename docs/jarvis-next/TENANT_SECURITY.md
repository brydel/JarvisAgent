# Isolation multi-tenant

## Ce qui est VERIFIED (M1, couche applicative)

- Chaque table du moteur porte `tenant_id` ; chaque lecture filtre par tenant (`mission`, `missions`, `board`,
  `evenements`, `approbations_en_attente`).
- Le tenant d'un exécutant est fixé à l'enrôlement ; une tâche n'est confiée qu'à un exécutant du même tenant.
- Un exécutant qui vise la tâche d'un autre tenant reçoit « tâche inconnue », sans fuite d'existence.
- Tests : `IsolationTest` (exécutant B sans tâche de A, résultat de B sur une tâche de A refusé, mission/Board/
  événements de A invisibles pour B).

## Entités et propriété (schéma M1, `missions.py`)

| Entité | Propriétaire | Cycle de vie |
| --- | --- | --- |
| Organisation (`ORG-…`) | — | créée par l'installation (`ORG-personnel`) ou l'administration (M7) |
| Exécutant (`RU-…`) | tenant | enrôlé → actif → révoqué |
| Connexion fournisseur | tenant | déclarée → active ; indisponible temporairement ; sans identifiant |
| Mission (`MI-…`) | tenant | OPEN → SUCCEEDED / FAILED / CANCELLED |
| Tâche (`TA-…`), tentative (`AT-…`) | tenant | voir `MISSION_ENGINE.md` |
| Approbation (`AP-…`) | tenant | en_attente → accordee / refusee |
| Artefact (`AR-…`) | tenant | revue en_cours → acceptee / refusee |
| Objet du Board (`BO-…`) | tenant | créé ; lié à une mission |
| Événement (séquence) | tenant | ajout seul |

À ajouter (PROPOSED, M2/M5) : User, Membership, Workspace, Project, AgentDefinition, AgentInstance,
TaskDependency, Policy, Document, KnowledgeEntity, KnowledgeRelation, UsageRecord, AuditEvent (le journal chaîné
existant tient ce rôle localement).

## PostgreSQL et RLS — PROPOSED (M2)

`ALTER TABLE … ENABLE ROW LEVEL SECURITY` + `FORCE`, politique `tenant_id = current_setting('jarvis.tenant_id')`
posée par connexion ; le rôle applicatif n'est pas propriétaire des tables ; un rôle d'administration distinct
pour les migrations. Tests automatiques d'isolation exécutés contre PostgreSQL réel (aujourd'hui absent du poste).

## Données sensibles

Chiffrement en transit (M3) et au repos (disque chiffré / PG), rétention et export par tenant, suppression avec
preuve, sauvegardes chiffrées et restauration **testée** : PROPOSED. La résidence canadienne des données est à
évaluer avant tout client (D-5). Aucune conformité n'est revendiquée.

## Migration de l'installation personnelle

L'existant (JSON/SQLite de `store.py`) reste la vérité pour les agents de code. Les missions vivent dans une base
séparée sous le tenant `ORG-personnel`. Le passage à PostgreSQL importera `missions.db` table par table avec
comparaison valeur par valeur, sur le modèle de `jarvis stockage migrer` (CURRENT). Aucun enregistrement fictif
imitant un client réel n'est créé.
