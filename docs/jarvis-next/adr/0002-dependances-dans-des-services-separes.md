# ADR-0002 — Nouvelles dépendances dans des services séparés

Statut : PROPOSED · 21 octobre 2026

## Contexte
`AGENTS.md` impose : Python ≥ 3.11, bibliothèque standard uniquement dans `lib/jarvis`. Jarvis Next aura besoin
de PostgreSQL (`psycopg`), d'un serveur web et d'un frontend TypeScript.

## Décision
Le cœur `lib/jarvis` reste sans dépendance. PostgreSQL, l'API web et le Studio vivent dans des dossiers de service
séparés (`services/controle/`, `studio/`), avec leurs propres dépendances verrouillées, et appellent le cœur
par ses contrats. M1 n'ajoute aucune dépendance.

## Alternatives rejetées
- Ajouter `psycopg`/un framework dans `lib/jarvis` : rompt le contrat d'installation (`install.sh` sans pip).
- Réécrire le cœur dans un autre langage : sans limite mesurée, interdit par le mandat (voir ADR-0004).
