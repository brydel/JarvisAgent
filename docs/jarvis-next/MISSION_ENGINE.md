# Moteur de missions durable — VERIFIED (SQLite, poste unique)

Code : `lib/jarvis/missions.py`. Tests : `tests/test_missions.py`. Base : `~/.local/state/jarvis/missions.db`
(SQLite, WAL, `BEGIN IMMEDIATE`), créée au premier usage de `jarvis mission`. Le démon appelle `recuperer()` à
chaque tour **seulement si la base existe** : une installation qui n'utilise pas Jarvis Next ne change pas.

## Comparaison des options (ADR-0003)

| Critère | A. Python existant + PostgreSQL | B. File transactionnelle + outbox (retenu, SQLite puis PostgreSQL) | C. Temporal |
| --- | --- | --- | --- |
| Migration | moyenne | **faible** : module neuf, aucun existant cassé | forte (SDK, serveur, réécriture) |
| Exploitation | serveur PG | **aucune** en local ; PG ensuite | cluster Temporal + base |
| Fiabilité | dépend du code | transactions + baux à jeton de clôture + idempotence, testés | excellente |
| Débogage | moyen | **journal d'événements ordonné**, état lisible en SQL | très bon (UI) |
| Local d'abord | oui | **oui** (bibliothèque standard) | lourd sur un portable |
| Coût | faible | **nul** | infra |
| Reprise | à écrire | écrite et testée (6 scénarios) | native |

Temporal reste une option si les workflows deviennent longs et nombreux (critère de réévaluation : > 1 000 tâches
actives ou besoin de minuteries complexes).

## États et transitions légales (appliquées par `_transition`)

```
CREATED → VALIDATED → QUEUED → LEASED → RUNNING → REVIEW → SUCCEEDED
              └→ WAITING_APPROVAL → QUEUED | CANCELLED | EXPIRED
QUEUED → WAITING_PROVIDER → QUEUED          (aucun fournisseur admis : l'essai n'est pas consommé)
LEASED|RUNNING → RETRY_SCHEDULED → QUEUED   (échec, bail expiré)   → FAILED si essais épuisés
LEASED|RUNNING → WAITING_PROVIDER           (quota / indisponibilité déclarée)
REVIEW → RETRY_SCHEDULED | FAILED           (revue déterministe refusée)
tout état non terminal → CANCELLED ; SUCCEEDED, FAILED, CANCELLED, EXPIRED sont terminaux
```

Une transition illégale lève `TransitionInterdite` et la transaction est annulée (test
`test_transition_illegale_refusee_sans_effet`). Chaque transition écrit un événement `tache_etat` dans la même
transaction : l'état et son journal ne peuvent pas diverger.

## Reprise — scénarios démontrés par les tests

| Scénario | Mécanisme | Test |
| --- | --- | --- |
| Exécutant tué après le travail, avant l'envoi | résultat écrit dans `coureur/<id>.json` avant l'envoi, renvoyé au redémarrage, accepté s'il a encore le bail ; **aucune réexécution** | `test_plantage_avant_envoi_sans_reexecution` |
| Exécutant muet (plantage, coupure réseau) | bail expiré → nouvel essai ; résultat tardif de l'ancien titulaire refusé (jeton de clôture) | `test_bail_expire_resultat_perime_puis_reprise_par_un_autre` |
| Message rejoué | clé d'idempotence `tache:jeton` → acquitté, aucun effet | idem |
| Redémarrage du plan de contrôle | aucun état en mémoire : tout est relu de la base | `test_redemarrage_du_plan_de_controle` |
| Quota épuisé | `fournisseur_indisponible` → WAITING_PROVIDER, essai rendu, routage vers l'autre fournisseur | `test_bascule_claude_vers_codex_sans_essai_perdu`, `test_tous_indisponibles_la_tache_attend` |
| Fermeture du navigateur | le navigateur n'est pas une source de vérité ; le flux reprend à `evenements(apres=seq)` | `test_board_note_vers_artefact_affiche` |
| Délai dépassé | délai du CLI → échec borné ; échéance de tâche → EXPIRED | `test_echecs_bornes` ; échéance : code, non testée isolément |

« Exactement une fois » n'est **pas** promis pour un effet externe : le moteur garantit au plus un artefact accepté
par tâche et le refus des résultats périmés. Un effet externe (envoi, publication) exigera une clé d'idempotence
côté fournisseur et une réconciliation (M4), et reste de toute façon L3 (approbation humaine).

## Points de reprise sans relecture de transcript

Pour M1, l'unité de reprise est la tâche entière (analyse courte). Pour les tâches longues (L2, code), le point de
reprise sera le worktree git + commits + fiche de tâche existants (`taches.py`) : un nouvel essai repart de l'état
du dépôt, pas de la conversation (PROPOSED, M4). Les sessions workmux orphelines sont déjà réconciliées par
`admission.reconcilier` et `poste.reprendre` (CURRENT) ; M4 les reliera aux baux.

## Passage à PostgreSQL (PROPOSED, M2)

Même schéma : chaque table porte `tenant_id` ; `UNIQUE (tenant_id, cle_idempotence)` ; séquence d'événements →
`BIGSERIAL` ; `BEGIN IMMEDIATE` → `SELECT … FOR UPDATE SKIP LOCKED` pour la réclamation concurrente ; RLS par
`current_setting('jarvis.tenant_id')`. Le module PostgreSQL vivra dans un service séparé (dépendance `psycopg`),
pas dans `lib/jarvis` (ADR-0002).
