# ADR-0006 — PostgreSQL avec RLS, dans un service séparé, derrière le même moteur

Statut : PROPOSED (implémenté et vérifié sur PostgreSQL 18.6 de l'ASUS) · 21 octobre 2026

## Décision
- Un seul moteur (`lib/jarvis/missions.py`), deux backends : SQLite par défaut (inchangé, sans dépendance) et
  PostgreSQL si `JARVIS_MISSIONS_PG` est défini. Le backend PostgreSQL et l'administration vivent dans
  `services/controle_pg/` (psycopg par le paquet Ubuntu `python3-psycopg`, pas de pip).
- Deux rôles : le **propriétaire** (ton utilisateur, connexion locale « peer », jamais superutilisateur) pour le
  schéma et l'administration ; **jarvis_app** (LOGIN, NOSUPERUSER, NOBYPASSRLS, non propriétaire) pour le moteur.
  La RLS s'applique donc à chaque requête du moteur ; son mot de passe est dans un fichier pgpass (600).
- Contexte de tenant `jarvis.tenant_id` posé à chaque connexion ; sans contexte, rien n'est visible.
- Quatre fonctions SECURITY DEFINER pour ce qui doit traverser les tenants : tenant d'un exécutant, liste des
  tenants (balayage), connexion d'un compte, organisations d'un compte.
- Journal d'événements en ajout seul pour jarvis_app (ni UPDATE, ni DELETE) ; aucune suppression accordée.
- Concurrence : `FOR UPDATE SKIP LOCKED` à la réclamation et transition conditionnelle (une seule ligne modifiée,
  sinon rien n'est écrit) — six réclamations simultanées sur une tâche donnent un seul bail (test).

## Alternatives rejetées
- Moteur PostgreSQL séparé du moteur SQLite : deux logiques à maintenir et à faire diverger.
- Connexion propriétaire + `SET ROLE` : l'application pourrait revenir au propriétaire (`RESET ROLE`).
- `FORCE ROW LEVEL SECURITY` : rendrait les fonctions SECURITY DEFINER inopérantes ; le moteur n'utilise de
  toute façon jamais le propriétaire.
- PostgreSQL par Docker Desktop : plus lourd sur le portable ; le paquet Ubuntu suffit.

## Limites
Le moteur choisit le tenant qu'il pose : la RLS protège contre un oubli de filtre et contre les requêtes sans
contexte, pas contre un plan de contrôle compromis. Les comptes existent en base mais le Studio se connecte
encore par jeton (prochaine étape).
