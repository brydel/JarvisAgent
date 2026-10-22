# Jarvis Next — index de l'architecture

Jarvis Next fait évoluer JarvisAgent vers un système d'exploitation agentique hybride : Jarvis Studio Cloud
(expérience, identité, orchestration, approbations) + exécutants locaux et hébergés (travail réel). Ce dossier
décrit l'existant vérifié, la cible, et la première tranche réellement implémentée (jalon M1).

Branche : `claude/jarvis-next-m1`, empilée sur `claude/vague-3-leadership` (pile de PR #1 → #5 encore ouvertes).

## Statuts utilisés partout

| Statut | Sens |
| --- | --- |
| **CURRENT** | existe dans le dépôt avant Jarvis Next (vérifié en lisant le code et en lançant les tests) |
| **PROPOSED** | proposé par l'agent ; **aucune** décision humaine |
| **APPROVED** | validé par le fondateur — rien n'est APPROVED dans ce lot : un agent ne peut pas approuver sa propre proposition |
| **IMPLEMENTED** | code présent sur la branche |
| **VERIFIED** | code présent et preuve d'exécution (tests, commande) citée |
| **BLOCKED** | impossible sans une action ou une autorisation précisée |

## Documents

| Document | Contenu | Statut |
| --- | --- | --- |
| [VISION.md](VISION.md) | mission, décisions confirmées, ce qui fait la différence | décisions : fournies par le fondateur |
| [CURRENT_STATE_AUDIT.md](CURRENT_STATE_AUDIT.md) | audit du dépôt, carte des sous-systèmes, KEEP/EXTEND/REFACTOR/REPLACE/DEPRECATE, baseline | CURRENT / VERIFIED |
| [TARGET_ARCHITECTURE.md](TARGET_ARCHITECTURE.md) | trois plans (expérience, contrôle, exécution), monolithe modulaire | PROPOSED |
| [HYBRID_DEPLOYMENT.md](HYBRID_DEPLOYMENT.md) | Studio Cloud + exécutants, profils de déploiement | PROPOSED |
| [RUNNER_PROTOCOL.md](RUNNER_PROTOCOL.md) | identité, enrôlement, enveloppes v1, baux, idempotence | v1 local : VERIFIED ; transport réseau : PROPOSED |
| [MISSION_ENGINE.md](MISSION_ENGINE.md) | machine d'états, transitions, reprise, schéma | VERIFIED (SQLite et PostgreSQL) |
| [POLICY_ENGINE.md](POLICY_ENGINE.md) | niveaux L0–L4, approbations, délégation bornée | VERIFIED (M1) |
| [PROVIDER_COMPATIBILITY.md](PROVIDER_COMPATIBILITY.md) | matrice de capacités Claude Code / Codex / factice | partiellement VERIFIED |
| [COMMERCIAL_COMPLIANCE.md](COMMERCIAL_COMPLIANCE.md) | sources officielles datées, règles par profil | sources consultées le 21 octobre 2026 |
| [BUDGET_GOVERNANCE.md](BUDGET_GOVERNANCE.md) | budget avant envoi, inconnu ≠ zéro | VERIFIED (inférence) / PROPOSED (reste) |
| [TENANT_SECURITY.md](TENANT_SECURITY.md) | modèle multi-tenant, RLS, tests d'isolation | VERIFIED (applicatif et RLS PostgreSQL) |
| [THREAT_MODEL.md](THREAT_MODEL.md) | menaces, mesures, résidu | PROPOSED |
| [AGENT_HIERARCHY.md](AGENT_HIERARCHY.md) | organisation dynamique, définitions versionnées | PROPOSED (bornes de délégation : VERIFIED) |
| [MEMORY_ARCHITECTURE.md](MEMORY_ARCHITECTURE.md) | mémoires, récupération sans 3ᵉ fournisseur | PROPOSED |
| [STUDIO_PRODUCT_SPEC.md](STUDIO_PRODUCT_SPEC.md) | vues du Studio, choix techniques à évaluer | Board local : VERIFIED ; reste PROPOSED |
| [BOARD_VERTICAL_SLICE.md](BOARD_VERTICAL_SLICE.md) | la tranche verticale, critère par critère | voir le tableau du document |
| [OBSERVABILITY.md](OBSERVABILITY.md) | corrélation, événements, audit séparé | PROPOSED (journal d'événements : VERIFIED) |
| [MIGRATION_ROADMAP.md](MIGRATION_ROADMAP.md) | M0 → M7, critères de sortie, compatibilité | PROPOSED |
| [RISK_REGISTER.md](RISK_REGISTER.md) | risques suivis | PROPOSED |
| [OPEN_DECISIONS.md](OPEN_DECISIONS.md) | ce que le fondateur doit trancher | en attente |
| [adr/](adr/) | décisions d'architecture avec alternatives rejetées (0001 à 0007) | PROPOSED |
| [../../design/board-v2/](../../design/board-v2/) | Board V2 : jetons, contrat visuel, inventaire ; preuves dans `reports/board-v2/` | VERIFIED |
