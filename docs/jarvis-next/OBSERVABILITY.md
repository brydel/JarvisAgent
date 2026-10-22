# Observabilité

## Corrélation

`tenant_id → mission_id → tache_id → tentative_id (attempt) → agent_instance_id → trace_id`.
M1 porte déjà tenant, mission, tâche, tentative et un `correlation_id` par mission dans chaque enveloppe ;
`agent_instance_id` et `trace_id` arrivent avec M4.

## VERIFIED

Journal d'événements ordonné par tenant (`evenements`) : créations, transitions d'état (de → vers, raison),
artefacts, approbations, résultats périmés, arrêts d'urgence, enrôlements/révocations. Écrit dans la même
transaction que l'état. Ne contient ni document analysé ni secret.

## CURRENT réutilisé

`observabilite.py` exporte les tâches de code en traces OTLP/JSON (sans dépendance) ; `journal.py` = audit chaîné.

## PROPOSED

- Exporter aussi les missions en spans OTLP (`mission` → `tache` → `tentative`), envoi seulement si
  `observabilite.otlp_endpoint` est réglé.
- Séparer télémétrie (agrégats, durées, taux d'échec) et audit sensible (décisions, approbations) ; expurgation
  des secrets connus (`secrets.valeurs_connues`, CURRENT).
- Évaluations IA : exactitude, fidélité aux sources, respect des consignes et des permissions, efficacité de
  délégation, qualité de recherche et de relecture, récupération mémoire, reprise. Suite déterministe sans modèle
  payant + tests réels opt-in (comme `outils/verifier_mission_reelle.py`).
- Injection de pannes : exécutant interrompu, messages dupliqués, baux périmés, fournisseur indisponible — déjà
  couverts en M1 par des tests déterministes.
