# Handoff — reprendre la session sans tout réanalyser

**Branche de travail** : `claude/autonomie-lot1` (dérivée de `claude/usine-roles-modeles-studio` @ b8296b7,
elle-même en PR #1 vers `main` @ 5e62e10). Rien n'a été fusionné dans `main`. L'instance qui tourne sur le
PC de l'utilisateur n'a pas été touchée (l'agent n'avait pas accès au PC).

**Environnement de l'agent** : conteneur Linux cloud, 2 cœurs, 8 Go, Python 3.13, tmux présent, workmux,
Codex et shellcheck absents, Claude Code 2.1.300 présent. Les mesures de `jarvis diagnostic` faites ici ne
valent pas pour l'ASUS.

## Décisions prises

- Un seul point d'admission (`admission.py`) avec verrou et réservations expirables, plutôt que des
  vérifications dispersées ; `plans.authorize_launch` garde la logique de plan/secours mais ne compte plus la
  capacité quand il est appelé par l'admission.
- Pauses par cause dans `pauses.json` ; `store.paused()` / `store.set_paused()` conservés comme façade
  (cause `humain`) pour ne pas casser cockpit, Telegram, tests.
- État `silent` ajouté aux agents (programme vivant sans sortie) ; `BUSY` l'inclut.
- Politique en TOML versionné dans le dépôt, copie personnelle qui ne peut que durcir ; exceptions groupées.
- Budget monétaire séparé des jetons ; non renseigné = 0.
- Journal d'audit JSONL chaîné, distinct du fil d'activité.
- Dots : aucune API inventée ; file partagée par issues GitHub (`travaux.py`), MCP conçu seulement.
- Plafonds de processus : non activés (non mesurables ici) ; consigne `jarvis lourd` + `nice`.
- Aucune dépendance ajoutée ; aucun service permanent ; aucun changement de format des états existants.

## Fichiers nouveaux / modifiés (code)

Nouveaux : `lib/jarvis/{admission,pauses,journal,politique,budgets,fournisseurs,travaux,diagnostic}.py`,
`config/politique.toml`, `config/profils/{laptop-conservative,workstation}.toml`, `tests/test_autonomie.py`,
`docs/autonomy/*`.
Modifiés : `store.py` (façade pauses), `config.py` (bornes, validation, profils, défauts `admission`,
`propositions`), `agents.py` (état `silent`, `pane_pid`), `taches.py` (statuts `silencieuse`/`inconnue`, champs
`classe`/`reservation`), `poste.py` (reprise via admission, réserve/charge depuis les réglages), `daemon.py`
(causes quota/batterie, `ressources_check`, réconciliation des réservations, relances bornées, Telegram
`/pauses`), `usage.py` (péremption), `plans.py` inchangé, `cli.py` (nouvelles commandes, admission dans
`plan verifier`), `bin/jarvis` (admission pour les deux chemins de `task`, maintenance dans `relancer`,
dispatch), `report.py`/`cockpit.py`/`web.py`/`usine.html` (visibilité), `chef/CLAUDE.md`,
`templates/{AGENTS,CLAUDE}.md`, `README.md`, `tests/test_jarvis.py` (3 tests adaptés, imports).

## État des lots et risques

Voir `README.md` (tableau) et `audit.md`. Risques ouverts : comportement réel de `workmux status` avec
l'état `silent` sur le PC ; charge de `/proc` parcouru à chaque `status_all` quand des fenêtres non suivies
existent (mesurer) ; `jarvis lourd` dépend de la discipline des agents ; PowerShell lent (déjà borné à 40 s
et mis en cache).

## Dépendances externes à l'action de l'utilisateur

Relance propre (`exploitation.md` §1) ; `jarvis diagnostic` sur l'ASUS ; décision sur le profil ; dépôt
GitHub et consigne du dot pour l'essai Dots ; éventuelle fusion de la PR #1 puis de celle de ce lot.

## Prochaine action

`exploitation.md` §1, puis renvoyer la sortie de `jarvis diagnostic` et `jarvis audit 50` après une journée.
