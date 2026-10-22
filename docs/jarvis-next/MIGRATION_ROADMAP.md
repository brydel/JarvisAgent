# Feuille de route de migration

| Jalon | Livrables | Critère de sortie | Statut |
| --- | --- | --- | --- |
| M0 Audit et baseline | audit, carte, menaces, ADR, baseline | comportement compris, base de non-régression | **fait** (152 tests verts avant changement) |
| M1 Plan de contrôle local durable | machine d'états, journal d'événements, file durable, baux, idempotence, politique minimale, adaptateurs, exécutant local, CLI | une mission survit à la panne de l'exécutant et au redémarrage sans corrompre son état | **atteint sur SQLite** (tests + vérification réelle Claude) ; PostgreSQL : reporté à M2 (D-2) |
| M2 Studio + Board | service web, authentification, espace par tenant, Board persistant, flux d'événements, artefacts ; PostgreSQL + RLS | un utilisateur authentifié crée une mission et suit une vraie tâche locale depuis le navigateur | à faire |
| M3 Exécutants hybrides | enrôlement par code d'appairage, transport sortant authentifié, baux réseau, transfert d'artefacts | une mission s'exécute sur un exécutant autorisé sans accès illimité à l'hôte | à faire |
| M4 Fournisseurs et agents | compilateur de missions, registre d'agents, délégation, dépendances, recherche sourcée, Codex réparé, tâches L2 via admission/workmux | une tâche compatible traverse un changement de fournisseur sans perte ni doublon | à faire (bascule de fournisseur déjà VERIFIED au niveau moteur) |
| M5 Connaissance | ingestion, provenance, mémoire de projet, recherche par tenant, évaluation | citer une décision antérieure sans fuite inter-tenant | à faire |
| M6 Amélioration continue | évaluation, revue indépendante, canari, rollback testé | une amélioration permise testée, déployée en environnement isolé, annulée automatiquement si elle échoue | bases CURRENT (goldens, canari de briefs, rollback assisté) |
| M7 Préparation commerciale | politique d'authentification commerciale, facturation fournisseurs, exécutants hébergés, administration, sauvegarde/reprise, documentation, revue de licences | chaque bloqueur commercial a une preuve de résolution — **pas** une autorisation de lancer | à faire |

## Compatibilité de l'installation existante (M1)

- Rien n'est migré : `missions.db` est une base **nouvelle et séparée**, créée seulement par `jarvis mission`.
- Démon : nouvelle étape `missions_check`, sans effet tant que la base n'existe pas (test
  `test_daemon_ne_cree_pas_la_base`).
- Aucune commande existante ne change ; `jarvis mission` s'ajoute ; aucune dépendance pip.
- Retour arrière : revenir au commit précédent et supprimer `~/.local/state/jarvis/missions.db*` et
  `~/.local/state/jarvis/coureur/`.

## Prochaine tâche concrète (M2, première partie)

Service `studio/` séparé : API HTTP locale (authentifiée, 127.0.0.1) au-dessus de `missions.py` — `POST /board`,
`GET /board`, `GET /missions/:id`, `GET /evenements?apres=` (SSE), `POST /approbations/:id` — puis la page Board.
Dépendances : D-2 (PostgreSQL ou SQLite d'abord), D-4 (canevas). Acceptation : depuis le navigateur, une note
ajoutée produit un artefact réel visible sans recharger, et un rechargement montre le même état.
