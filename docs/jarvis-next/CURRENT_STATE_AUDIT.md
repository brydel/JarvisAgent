# Audit de l'existant (M0) — vérifié le 21 octobre 2026

Méthode : lecture des fichiers, de l'historique git et des PR GitHub ; exécution des vérifications prescrites par
`AGENTS.md` dans un worktree séparé. Rien n'a été modifié dans le dossier principal du dépôt : le démon, le cockpit
et le chef de l'installation réelle y tournent (session tmux `jarvis`, processus observés avec `pgrep`).

## 1. État du dépôt

| Élément | Constat |
| --- | --- |
| Dossier | `~/projets/JarvisAgent` sous WSL2 Ubuntu (pas sous Windows) ; worktrees dans `~/projets/JarvisAgent__worktrees` |
| Branche du dossier principal | `claude/autonomie-lot1` (1dd488b), arbre propre, **utilisée par l'installation en service** |
| Pile de PR ouvertes | #1 `usine` → `main` ; #2 `autonomie-lot1` → #1 ; #3 `vague-1` → #2 ; #4 `vague-2` → #3 ; #5 `vague-3` → #4. Rien n'est fusionné dans `main` |
| Base de Jarvis Next | sommet de la pile, `origin/claude/vague-3-leadership` (c34ba95) : c'est le code le plus récent, et Jarvis Next réutilise son bail, ses exécutants et son stockage |
| Règles | `AGENTS.md` = `CLAUDE.md` (identiques, vérifié par `diff`) : français, bash idempotent, **Python bibliothèque standard uniquement (≥ 3.11)**, dépôt public sans secret, ne jamais fusionner dans `main` |
| Outils sur le poste | Python 3.14.4, tmux, workmux, gh, Claude Code 2.1.307, Node 22 ; **pas** de shellcheck, **pas** de PostgreSQL, Docker Desktop arrêté |
| Codex dans WSL | constaté d'abord comme cassé (« Missing optional dependency @openai/codex-linux-x64 ») ; diagnostic : le Codex Linux (`~/.npm-global/bin/codex`, 0.162.1) est installé et connecté, mais `~/.bashrc` n'ajoute ce dossier au PATH que pour les shells interactifs : sans terminal, c'est le Codex Windows (`/mnt/c/nvm4w/nodejs/codex`) qui était trouvé. Corrigé dans l'adaptateur, vérifié en réel (voir `PROVIDER_COMPATIBILITY.md`) |

## 2. Baseline (VERIFIED)

Commandes lancées dans le worktree, avant toute modification :

```
bash -n install.sh bin/jarvis          → OK
bin/jarvis help                        → OK
python3 -m unittest discover -s tests  → Ran 152 tests in 73.2s — OK
shellcheck                             → non installé (non exécuté)
```

Après le lot M1 : **186 tests OK** (152 + 34 nouveaux ; la vérification réelle avec Claude est dans `outils/verifier_mission_reelle.py`), voir `BOARD_VERTICAL_SLICE.md`.

## 3. Carte des sous-systèmes

| Sous-système | Fichiers | Rôle et comportement actuel | Persistance | Tests | Frontière de sécurité | Modes de défaillance / limites | Classement |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CLI | `bin/jarvis` (bash), `lib/jarvis/cli.py` | point d'entrée unique, ~70 sous-commandes ; garde `_human_only` (terminal interactif exigé) | — | `test_jarvis.py` | garde applicative, même utilisateur Linux | un agent avec un pseudo-terminal pourrait contourner | **KEEP** (+ `jarvis mission`) |
| Lanceurs d'agents | `bin/jarvis-claude`, `bin/jarvis-codex` | lancent les CLI officiels, injectent les secrets du rôle | — | oui | bac à sable Codex, règles deny Claude | `bin/jarvis-codex` fait `exec codex` : correct dans les fenêtres tmux (shells interactifs) | **KEEP** |
| Exécution workmux | `execution.py` (`WorkmuxBackend`), `config/workmux` | worktree git + fenêtre tmux par agent | état workmux/tmux | oui | isolation par worktree, pas par utilisateur | une fenêtre tmux n'est pas une source de vérité durable | **EXTEND** : devient un adaptateur d'exécutant (M3/M4) |
| Admission | `admission.py` | point unique de départ d'agent : pauses, capacité, réservations expirables, doublons, jetons, plan | JSON/SQLite (`store`) | oui | décision mécanique, verrou unique | local uniquement | **KEEP**, à appeler depuis le moteur de missions pour les tâches L2 (M4) |
| Démon | `daemon.py` | boucle de surveillance (agents, quotas, chef, santé, bail, canari…) | état local | oui | bail d'orchestrateur (jeton de clôture) | un seul poste | **EXTEND** (étape `missions_check` ajoutée) |
| Chef d'orchestre | `chef/CLAUDE.md` | superagent Claude Code qui propose des plans ; l'humain approuve | conversation + état | partiel | ne peut ni approuver ni lever une pause | la conversation n'est pas durable | **KEEP**, deviendra « Executive Planner » branché sur le compilateur de missions (M4) |
| Plans et tâches | `plans.py`, `taches.py` | plans approuvés, fiches de tâches, reprise bornée, classement d'échecs | JSON/SQLite | oui | approbation humaine | pas de dépendances explicites ni de machine d'états formelle | **REFACTOR** progressif vers `missions.py` (M1→M4) |
| Politique | `politique.py`, `config/politique.toml` | niveaux 1–3, délégations datées, file d'exceptions | TOML + état | oui | la copie personnelle ne peut que restreindre | même utilisateur Linux | **KEEP** ; L0–L4 de Jarvis Next s'y aligne (voir `POLICY_ENGINE.md`) |
| Budgets / coûts / quotas | `budgets.py`, `couts.py`, `usage.py`, `fournisseurs.py` | enveloppes monétaires (non renseigné = 0), jetons, quotas publiés avec fraîcheur | JSON/SQLite | oui | refus avant dépense | estimations, pas une facturation | **KEEP** |
| Journal d'audit | `journal.py` | JSONL chaîné par empreintes | fichier | oui | altération détectable, pas impossible | même utilisateur | **KEEP** ; séparé du journal d'événements des missions |
| Stockage | `store.py`, `stockage.py` | JSON atomique sous verrou, SQLite facultatif avec migration vérifiée | `~/.local/state/jarvis` | oui (deux modes) | — | SQLite non partageable par le réseau | **KEEP** |
| Bail / exécutants déclarés | `bail.py`, `executants.py` | un seul démon ; capacité mesurée du poste | état local | oui | jeton de clôture | local | **EXTEND** → registre d'exécutants authentifiés (`missions.py`, M1/M3) |
| Telegram | `telegram.py`, `notify.py` | notifications et décisions (boutons) depuis le chat appairé | état | oui (faux serveur) | chat appairé | dépend d'un service tiers | **KEEP** ; futur canal d'approbation du Studio |
| Linear | `templates/`, `AGENTS.md` | protocole de commentaires d'agent | Linear | — | — | serveur MCP non authentifié dans cette session | **KEEP** |
| Web (lecture seule) | `web.py`, `usine.html` | tableau de bord sur 127.0.0.1 | — | oui | aucune action possible | pas d'authentification (local seulement) | **REPLACE** à terme par Jarvis Studio (M2) ; garder tant que Studio n'existe pas |
| Évaluation, skills, briefs, rollback, traces | `evaluation.py`, `skills.py`, `versions_roles.py`, `rollback.py`, `observabilite.py` | goldens, skills épinglées, canari de briefs, revert assisté, OTLP JSON | fichiers | oui | humain pour activer/promouvoir | 3 cas par rôle | **KEEP** ; base du jalon M6 |
| Proxy produits | `proxy.py` | config LiteLLM pour les produits | — | oui | désactivé sans budget | — | **KEEP** (hors périmètre M1) |
| E2B | `execution.E2BBackend` | bac à sable payant, désactivé | — | oui (double) | budget infrastructure requis | payant | **DEPRECATE** pour l'exécution hébergée tant qu'un ADR ne le choisit pas |

Aucun composant n'est classé REPLACE immédiatement : la contrainte « bibliothèque standard » et l'installation en
service rendent tout remplacement brutal plus risqué qu'utile.

## 4. Contrainte « bibliothèque standard »

Respectée par M1 : `missions.py`, `protocole_executant.py`, `adaptateurs.py`, `coureur.py` n'importent que la
bibliothèque standard. PostgreSQL, un framework web ou le Studio TypeScript iront dans des **services séparés**
(`services/` ou dépôt dédié, voir ADR-0002) pour ne pas casser le contrat de dépendances du cœur.

## 5. Écarts avec la cible (résumé)

1. Pas de machine d'états formelle ni de source de vérité durable pour une mission → **comblé par M1** (SQLite).
2. Pas de notion de tenant → **comblé au niveau du schéma et de l'API** (M1) ; RLS PostgreSQL : M2.
3. Pas d'exécutant authentifié distinct du démon → **comblé localement** (M1) ; transport réseau : M3.
4. Pas de Studio ni d'authentification utilisateur → M2.
5. Isolation réelle : tout tourne sous le même utilisateur Linux (déjà documenté dans `docs/autonomy/securite.md`).
6. Codex : résolu (PATH des shells non interactifs ; l'adaptateur ignore désormais les binaires Windows).
