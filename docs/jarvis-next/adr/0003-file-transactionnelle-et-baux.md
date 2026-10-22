# ADR-0003 — File transactionnelle, journal d'événements et baux à jeton de clôture

Statut : PROPOSED (implémenté et vérifié sur SQLite) · 21 octobre 2026

## Décision
Le moteur de missions est une file transactionnelle : état + événement écrits dans la même transaction ; les
tâches sont confiées par baux expirables numérotés (jeton de clôture) ; les résultats portent une clé
d'idempotence `tache:jeton`. SQLite (WAL, `BEGIN IMMEDIATE`) en M1, PostgreSQL (`FOR UPDATE SKIP LOCKED`, RLS) en M2,
même schéma.

## Alternatives
- Étendre `taches.py`/`plans.py` (JSON) : pas de transactions multi-objets ni de requêtes ; rejeté.
- Temporal : fiable mais lourd pour un portable et pour un seul développeur ; **réévalué** si > 1 000 tâches
  actives ou workflows à minuteries complexes.

## Preuves
`tests/test_missions.py` : 34 tests (transitions, reprises, rejeu, périmés, isolation, politique, routage).
Vérification réelle : `outils/verifier_mission_reelle.py` avec Claude Code.
