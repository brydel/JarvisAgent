# Architecture cible — PROPOSED

Trois plans, **un monolithe modulaire** tant qu'aucun besoin mesuré de mise à l'échelle ou de déploiement séparé
ne justifie un découpage (ADR-0001). Les contrats entre modules sont des fonctions Python typées et des enveloppes
JSON versionnées ; ils deviendront des API réseau seulement là où un exécutant distant l'exige (M3).

```
┌────────────────────── PLAN D'EXPÉRIENCE (Jarvis Studio, M2) ──────────────────────┐
│ Board · Command Center · Mission Inspector · Graphe d'exécution · Approbations     │
│ Explorateur d'artefacts et de connaissances · Notifications · Budget et fournisseurs│
│   ↕ API authentifiée + flux d'événements (SSE) — jamais de shell, jamais de secret  │
├────────────────────── PLAN DE CONTRÔLE (cloud à terme, local aujourd'hui) ─────────┤
│ Compilateur de missions → Registre d'agents → Planificateur d'organisation          │
│ Ordonnanceur (missions.py) · Moteur de politique · Routeur de fournisseurs          │
│ Registre d'exécutants · Gouverneur de budget · Connaissance · Audit                 │
│   ↕ protocole d'exécutant v1 : connexions SORTANTES de l'exécutant, baux, résultats │
├────────────────────── PLAN D'EXÉCUTION ───────────────────────────────────────────┤
│ Exécutant local WSL2 · Linux natif · conteneur hébergé (futur)                      │
│ Adaptateurs Claude Code / Codex / factice · worktrees git · workmux · limites      │
└────────────────────────────────────────────────────────────────────────────────────┘
```

## Modules du plan de contrôle et état

| Module | Contrat | Où | Statut |
| --- | --- | --- | --- |
| Ordonnanceur / moteur de missions | `missions.creer_mission`, `reclamer`, `demarrer`, `battement`, `rendre_resultat`, `recuperer`, `annuler_mission` | `lib/jarvis/missions.py` | VERIFIED |
| Moteur de politique (missions) | niveaux L0–L4, approbations liées à l'empreinte, délégation bornée | `missions.py` | VERIFIED ; unification avec `politique.py` : PROPOSED |
| Routeur de fournisseurs | `_router` : connexion déclarée, profil, budget, disponibilité | `missions.py` | VERIFIED |
| Registre d'exécutants | `enroler_executant`, `revoquer_executant`, authentification par secret haché | `missions.py` | VERIFIED (local) |
| Gouverneur de budget | budget d'inférence payante par tenant, zéro par défaut, contrôlé avant l'envoi | `missions.py` + `budgets.py` existant | partiel |
| Compilateur de missions | intention → spécification (objectif, graphe, critères, risque, approbations, estimation) | — | PROPOSED (M4) ; M1 n'a qu'un modèle : « analyse_document » |
| Registre d'agents / planificateur | définitions versionnées, composition d'équipes | `roles/`, `roles.py`, `versions_roles.py` (CURRENT) | PROPOSED |
| Connaissance | voir `MEMORY_ARCHITECTURE.md` | `memoire.py` (CURRENT, mémoire du chef) | PROPOSED (M5) |
| Audit | `journal.py` (chaîné) + journal d'événements des missions (ordonné) | les deux | CURRENT + VERIFIED |

## Pourquoi pas tout de suite des microservices, PostgreSQL et Temporal

- Une seule machine, un seul utilisateur, un seul exécutant : la complexité opérationnelle coûterait plus qu'elle
  ne protège. Le schéma porte déjà `tenant_id` partout pour que le passage à PostgreSQL soit un changement de
  moteur, pas de modèle (ADR-0002, ADR-0003).
- PostgreSQL n'est pas installé sur le poste ; l'installer est réversible mais c'est une décision d'environnement
  (OPEN_DECISIONS D-2).
