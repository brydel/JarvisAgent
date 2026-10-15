# Admission commune, réservations, opérations lourdes, pauses, états d'agents

## Point d'admission (`lib/jarvis/admission.py`)

Tout départ passe par `admission.demander(origine=…)` avec `origine` ∈ plan, cli, reprise, relance, chef,
sous-agent. Sous le verrou `admission`, dans l'ordre :

1. `config.valider()` — une configuration hors bornes ferme l'admission (code `config`, sortie 6) ;
2. `pauses.actives()` — une cause suffit (code `pause`, sortie 3) ;
3. `agents.status_all()` — observation impossible = refus (code `observation`) ;
4. capacité : agents occupés (`BUSY`, dont `silent`) + réservations actives ≥ `poste.capacite()["max"]` → refus
   (code `capacite`) ; `--forcer` (humain devant un terminal seulement) passe outre **cette seule** vérification ;
5. opérations lourdes : si la classe est lourde, `operations lourdes en cours + réservations lourdes + agents
   de classe lourde ≥ admission.operations_lourdes_max` → refus (code `lourde`) ;
6. doublons : réservation active pour le même (projet, issue, agent) ou le même worktree ; worktree déjà
   visible (sauf reprise) → refus (code `doublon`) ;
7. jetons : fournisseur épuisé → refus (code `budget`, sortie 5) ; avec un plan, `plans.authorize_launch`
   gère le secours ;
8. réservation `R-xxxxx` écrite (expire après `admission.reservation_min`, 15 min), journal « admis ».

Appelants : `jarvis plan verifier` (plan), `jarvis admission demander` (lancement manuel dans `bin/jarvis`
`cmd_task`), `poste.reprendre` (reprise), `daemon.chef_check` via `relance_autorisee` (relance du chef).
Les réservations sont **confirmées** par `tache-enregistrer`, **libérées** par `abandon()` dans `bin/jarvis`,
et **réconciliées** par le démon à chaque tour (`admission.reconcilier`) : visibles → démarrées ; expirées →
place rendue, élément de plan relâché si aucune fiche de tâche n'existe, fil et journal informés.

Classes de charge : `recherche`, `orchestration`, `edition` (légères) ; `compilation`, `tests`,
`navigateur`, `video` (lourdes). Un rôle donne sa classe (`video`→video, `qa`→tests, `design`→navigateur,
`recherche`→recherche, autres→edition).

## Opérations lourdes (`jarvis lourd`)

- `jarvis lourd exec <classe> -- <commande>` : attend une place (15 s entre deux essais, `--attente` 30 min),
  déclare l'opération, lance la commande avec `nice -n 10`, libère à la fin. `debut`/`fin` pour un usage manuel.
- Une opération déclarée par `exec` est oubliée quand son processus disparaît ; une opération déclarée par
  `debut` n'a pas de processus à suivre : seule `--duree` (120 min, 4 h au plus) ou `jarvis lourd fin` la clôt.
  Les options (`--duree`, `--attente`, `--worktree`) se placent avant la classe.
- Les opérations lourdes sont rangées dans `~/.local/state/jarvis/lourdes/` avec leur propre verrou : c'est le
  seul coin de l'état de Jarvis que le bac à sable de Codex peut écrire (`bin/jarvis-codex` l'ajoute aux
  racines inscriptibles). Un agent Codex peut donc déclarer sa compilation sans pouvoir toucher aux plans,
  pauses, budgets ni au journal (le journal n'est alors pas écrit pour cet événement : limite connue).
- **Limite honnête** : c'est une consigne (templates/CLAUDE.md, AGENTS.md, rôle du chef) vérifiée a
  posteriori (`jarvis lourd liste`, `jarvis audit`). Une commande lancée hors de ce cadre n'est pas bloquée.
  Voir `securite.md` pour les plafonds système et pourquoi ils ne sont pas activés.

## Pauses (`lib/jarvis/pauses.py`, `jarvis pause`)

| Cause | Posée par | Levée par |
| --- | --- | --- |
| `humain` | toi (cockpit P, Telegram /pause, `jarvis pause poser humain`) | toi seulement |
| `batterie` | démon (≤ `sante.batterie_arret_pct` sans secteur) | démon quand le secteur revient |
| `quota` | démon (Claude et Codex épuisés) | démon dès qu'un abonnement revient |
| `ressources` | démon : pression mémoire PSI `some avg60` ≥ `admission.pression_memoire_pct` sur deux lectures consécutives (1 min d'écart), ou mémoire disponible < réserve/2 | démon après `admission.hysterese_min` minutes sous la moitié du seuil |
| `incident` | toi, le chef ou un agent (`jarvis pause poser incident "…"`) | toi |
| `maintenance` | `jarvis relancer` le temps de l'opération, ou toi | `jarvis relancer` à la fin, ou toi (`jarvis pause lever maintenance`) |

Jarvis est en pause tant qu'il reste **une** cause. Les agents en cours continuent ; seuls les nouveaux
départs (et la relance automatique du chef) attendent. Une mesure absente (pas de PSI, pas de PowerShell)
ne pose ni ne lève rien. L'ancien fichier `pause` est migré en cause `humain` au premier accès.

## États d'agents et de tâches

| Observé | Fenêtre workmux/tmux | Programme dans le volet | Statut agent | Fiche | Compte dans la capacité |
| --- | --- | --- | --- | --- | --- |
| travaille | suivi, `working` | — | `working` | `en_cours` | oui |
| attend | suivi, `waiting` | — | `waiting` | `attente` | oui |
| démarre / non suivi | fenêtre `wm-*` non suivie, activité < 20 min | — | `untracked` | `en_cours` | oui |
| **silencieux** | non suivi, activité ≥ 20 min | vivant (Claude/Codex) | `silent` | `silencieuse` | **oui** |
| inactif | non suivi, activité ≥ 20 min | shell seul | `idle` | `terminee` | non (fenêtre fermable) |
| terminé | suivi, `done` | — | `done` | `terminee` | non |
| interrompu | fenêtre disparue ≥ 120 s pendant le travail | — | — | `perdue` | non |
| jamais démarré | aucune fenêtre 15 min après le lancement | — | — | `perdue` + plan relâché | réservation expirée |
| inconnu | `workmux status` en échec | — | — | inchangée (rien n'est conclu) | admission fermée |

`blocage_check` (existant) prévient le chef d'un agent `working` muet depuis `general.blocage_min` ou qui
dure plus de `general.duree_max_min` ; il ne conclut jamais seul.
