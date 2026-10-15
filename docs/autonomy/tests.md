# Tests : ce qui est prouvé, et comment

Commande : `python3 -m unittest discover -s tests` (tmux requis ; workmux, Claude et Codex sont des doubles
dans `tests/fake-bin/`). Résultat obtenu dans le conteneur de développement : **108 tests, OK, ~108 s**
(84 préexistants dans `tests/test_jarvis.py`, 24 nouveaux dans `tests/test_autonomie.py`). Une revue
indépendante du code (second agent, sans contexte de production) a relevé 14 points, tous corrigés et
couverts : enveloppe globale non consommée, catégorie de budget ignorée, `jarvis lourd debut` sans effet,
chaîne d'audit rompue à la rotation, garde humaine affaiblie sur `jarvis pause`, action ajoutée au niveau 1,
délégation de projet appliquée hors projet et consommation non atomique, `--sans-windows` ignoré,
auto-vérification non détectée dans la file de travaux, réservation non libérée d'une tâche jamais démarrée,
chemin d'abandon tardif dans `bin/jarvis`, pause maintenance levée à tort par `jarvis relancer`.

## Trois niveaux

- **Unitaires** (Python pur, état isolé dans un dossier temporaire) : `pauses`, `admission`, `politique`,
  `budgets`, `journal`, `travaux`, `config.valider`, `usage.perime`.
- **Intégration simulée** (faux workmux, tmux privé, faux Telegram HTTP, `bin/jarvis` réellement exécuté) :
  `jarvis task` avec plan, droits insuffisants via le binaire, Telegram `/reprendre`, cockpit/rapport.
- **Vérifications réelles sur ton poste** : *non faites ici*. À faire : `jarvis diagnostic`, un `jarvis task`
  réel, `jarvis lourd exec tests -- pnpm test` dans un agent, une nuit avec `jarvis audit` au matin.

## Couverture des critères du mandat (§16)

| Critère | Test | Niveau |
| --- | --- | --- |
| Lancement concurrent au-delà du plafond | `test_concurrent_launches_never_exceed_the_cap` (6 fils, plafond 2) | unitaire |
| Opération lourde hors admission | `test_heavy_operation_outside_admission_is_refused` | unitaire |
| Reprise pendant une pause | `test_resume_after_reboot_goes_through_admission` | intégration simulée |
| Coexistence des pauses humain/batterie/quota | `test_pauses_humain_batterie_quota_coexistent`, `test_quota_pause_never_lifts_human_pause`, `test_battery_pause_is_its_own_cause` | unitaire |
| Observation indisponible | `test_admission_fails_closed_without_observation` | unitaire |
| Tâche silencieuse encore vivante | `test_long_idle_untracked_window_frees_its_slot` (tmux réel : `cat` vivant → silencieux ; shell seul → inactif) | intégration |
| Interruption pendant un lancement | `test_interrupted_launch_expires_and_frees_the_plan_item`, `test_confirmed_reservation_is_released_by_abort` | unitaire |
| Relances bornées | `test_bounded_restarts`, `test_chef_is_not_restarted_during_any_pause`, `test_chef_watchdog_restarts_only_when_work_remains` | unitaire |
| Droits insuffisants | `test_insufficient_rights_are_refused` (6 commandes via `bin/jarvis`, code 4) | intégration simulée |
| Quotas périmés | `test_stale_quota_means_prudence_not_green_light` | unitaire |
| Configuration invalide | `test_invalid_configuration_closes_admission` | unitaire |
| Refus de dépense ou publication non autorisée | `test_spending_and_publication_are_refused_without_envelope_or_delegation` | unitaire |
| Séparation des secrets | `test_secrets_stay_out_of_reports`, `test_reglage_lire_never_prints_the_token` (existant) | unitaire + intégration |
| Candidat ne peut pas modifier ses protections | `test_candidate_cannot_weaken_its_own_protections` (politique perso ignorée si elle assouplit ou ajoute une action automatique ; journal altéré détecté), `test_audit_chain_survives_rotation` | unitaire |
| Opération lourde déclarée à la main | `test_heavy_operation_declared_manually_counts` (via `bin/jarvis`) | intégration simulée |
| Pression ressources avec hystérésis | `test_resource_pressure_uses_sustained_measure_and_hysteresis` | unitaire |
| File partagée : doublons, exécutant unique, preuve, plafond, import | `test_shared_queue_dedups_single_executor_verified_result` | unitaire |
| Visibilité (rapport, web, Telegram) | `test_state_shows_pause_causes_reservations_and_exceptions` | intégration simulée |

Non couvert par un test : le rendu curses du cockpit (vérifié visuellement dans le lot précédent, pas
re-capturé ici), `gh issue list` réel, `codex cloud`, PowerShell.
