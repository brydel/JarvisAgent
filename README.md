# JarvisAgent

Poste de pilotage pour faire travailler **plusieurs agents IA de code en parallèle** (Claude Code et Codex) sur **plusieurs SaaS à la fois**, dirigés par un **chef d'orchestre** IA qui planifie, lance, surveille, fait contre-relire et se remet en question. Tu valides depuis ton terminal ou depuis ton téléphone (Telegram).

```
 Toi ── Telegram / cockpit ──▶ démon Jarvis ──▶ CHEF D'ORCHESTRE (Claude, rôle chef/CLAUDE.md)
  ▲        ✅ Approuver / ✋ Refuser    │              │ propose des plans → tu valides
  │                                     │              │ jarvis task --plan …
  │                                     ▼              ▼
  │                       surveillance workmux    Agents Claude / Codex (1 worktree + 1 fenêtre tmux chacun)
  │                                                    │ lisent leur issue Linear, codent, ouvrent une PR
  └──────────── GitHub : tu relis et tu fusionnes ◀────┘
```

## Ce que fait le superagent

- **Planifie** : il lit tes projets (registre Jarvis) et leurs issues Linear, puis prépare des **vagues** de tâches indépendantes.
- **Se remet en question** : avant chaque plan, il fait une pré-mortem et le fait attaquer par un sous-agent « avocat du diable ». Après chaque vague, il écrit un bilan avec les causes racines dans son journal, qui lui sert de mémoire.
- **Te demande la permission** : chaque plan t'arrive sur Telegram avec des boutons **Approuver / Refuser**. Il ne peut lancer **que** ce que tu as approuvé, une seule fois par tâche : ce n'est pas une consigne, `jarvis task` le refuse techniquement.
- **Dirige l'équipe** : il lance les agents avec des consignes précises, répond à leurs questions techniques, les relance s'ils bloquent, et fait relire le travail de Claude par Codex et inversement.
- **Travaille la nuit** : le **plan de nuit** est une liste ordonnée que tu valides avant de dormir. Il l'exécute au fil des places libres, puis t'envoie un bilan le matin.
- **Garde-fous** : il ne code pas, ne fusionne pas, ne pousse rien, ne lit pas les `.env`. Il respecte un plafond d'agents simultanés et la **pause** (`/pause` sur Telegram).

## Installation (Windows + WSL)

**1. WSL + Ubuntu** (une seule fois). Dans PowerShell **en administrateur** :

```powershell
wsl --install -d Ubuntu
```

Redémarre, ouvre **Ubuntu** et crée ton utilisateur en minuscules.

**2. Cloner et installer.** Dans Ubuntu :

```bash
sudo apt update && sudo apt install -y git
mkdir -p ~/projets && cd ~/projets
git clone https://github.com/brydel/JarvisAgent.git
cd JarvisAgent && ./install.sh
```

Le script installe tmux, gh, Node 22, Claude Code, Codex et workmux, active le suivi des agents et branche Linear. Il ignore les versions Windows de `claude` et `codex` qui traînent dans le PATH de WSL. Tu peux le relancer autant de fois que tu veux.

**3. Les connexions** (une seule fois) : suis la liste « À faire maintenant » affichée à la fin (Claude, Codex, GitHub, Linear).

**4. Tes projets** : enregistre chaque SaaS piloté :

```bash
jarvis projet ajouter repriceo ~/projets/repriceo --linear "Repriceo" --priorite 1 \
  --description "Plateforme de trading : sécurité et données financières d'abord"
jarvis projet ajouter jobpilot-ia ~/projets/jobpilot-ia --linear "JobPilot" --priorite 2
cd ~/projets/repriceo && jarvis init-project      # protocole Linear des agents
```

**5. Telegram** (recommandé) :

```bash
jarvis telegram config
```

Suis les étapes : tu crées un bot avec **@BotFather**, tu colles son jeton, puis tu envoies au bot le code à 6 chiffres affiché. Seule **ta** conversation est acceptée ; tout autre expéditeur est refusé.

**6. Vérifier** : `jarvis doctor`. Tout doit être vert.

> Garde tes projets dans Linux (`~/projets/...`), jamais dans `/mnt/c/...`.

## Utilisation

```bash
jarvis start      # session « jarvis » : cockpit (fenêtre 1) + démon (fenêtre 2)
jarvis chef       # lance le chef d'orchestre (fenêtre « chef ») : il propose son premier plan
```

Ensuite, tu pilotes depuis le **cockpit** ou depuis **Telegram**.

### Le cockpit

```
 ◆ J A R V I S  ·  poste de pilotage                                         22:35:08
 Agents 2/3   ? 1 en attente   ✓ 1 terminés   ◇ 1 plan(s) à valider   ● chef actif   ● Telegram
╭─ AGENTS ───────────────────────────────────────────────╮╭─ À VALIDER ───────────────────╮
│ ?  repriceo     bis-71-guardrails-couts  Codex  attend  ││ ◇ P-0002 Nuit : auth [nuit]   │
│ ▶  jobpilot-ia  jp-12-onboarding         Claude travail…││   repriceo BIS-72 → claude    │
│ ✓  repriceo     bis-69-adr-architecture  Claude terminé ││   jobpilot-ia JP-14 → codex   │
╰─────────────────────────────────────────────────────────╯╰───────────────────────────────╯
╭─ FIL D'ACTIVITÉ ────────────────────────────────────────────────────────────────────────╮
│ 22:34 ◇ P-0001 proposé : Vague docs architecture (2 tâche(s), vague)                    │
│ 22:34 ✓ P-0001 approuvé (Telegram)                                                       │
```

| Touche | Action |
| --- | --- |
| **Tab** | Passer du panneau Agents au panneau À valider |
| **↑ ↓** | Choisir un agent ou un plan |
| **Entrée** | Ouvrir la fenêtre de l'agent (Ctrl+B puis 1 pour revenir) |
| **o** / **x** | Approuver / refuser le plan sélectionné |
| **p** | Aperçu en direct de la sortie de l'agent sélectionné |
| **m** | Écrire au chef |
| **e** | Écrire directement à l'agent sélectionné |
| **c** | Ouvrir la fenêtre du chef |
| **P** | Pause / reprise : plus aucun nouveau lancement |
| **q** | Quitter le cockpit |

### Telegram

| Message | Effet |
| --- | --- |
| Boutons ✅ / ✋ sous un plan | Approuver ou refuser |
| `/etat` | Agents et plans en cours |
| `/plans` | Plans à valider, avec boutons |
| `/jetons` | Consommation Claude et Codex |
| `/pause` · `/reprendre` | Bloquer ou relancer les lancements |
| N'importe quel texte | Transmis au chef (« Priorise JobPilot cette nuit ») |

Tu reçois aussi les questions du chef (❓) et ses bilans (📝), avec une notification Windows quand tu es sur ton PC.

### Une journée type

1. **Matin** : lis le bilan de nuit sur Telegram, puis relis et fusionne les PR prêtes.
2. **Journée** : le chef propose des vagues, tu approuves en un clic, tu réponds à ses questions.
3. **Soir** : écris « je vais dormir » au chef. Il propose un **plan de nuit**, tu l'approuves, et l'équipe travaille pendant que tu dors.

## Commandes

| Commande | Rôle |
| --- | --- |
| `jarvis start` | Session `jarvis` : cockpit + démon |
| `jarvis chef` | Lance ou rejoint le chef d'orchestre |
| `jarvis cockpit` | Interface plein écran |
| `jarvis etat` | État complet (agents, plans, projets, capacité) |
| `jarvis plan liste` · `voir P-1` · `ok P-1` · `non P-1 raison` | Gérer les plans depuis le terminal |
| `jarvis fil [n]` · `jarvis journal` | Événements récents · journal du chef |
| `jarvis task [--projet P] [--plan ID] <ISSUE> <claude\|codex> [desc] [--consignes f.md] [--revue N°PR]` | Lancer un agent sur une issue (`--revue` : relecture seule d'une PR). Hors terminal interactif, un plan approuvé est obligatoire |
| `jarvis projet ajouter\|liste` | Registre des projets |
| `jarvis telegram config\|test` | Liaison Telegram |
| `jarvis regler <clé> <valeur>` | Réglages (voir ci-dessous) |
| `jarvis board` · `jarvis status` | Tableau de bord workmux · tâches du projet courant |
| `jarvis init-project [dossier]` | Protocole Linear dans un projet |
| `jarvis doctor` | Diagnostic complet |

### Réglages

| Clé | Défaut | Rôle |
| --- | --- | --- |
| `general.max_agents` | `3` | Agents occupés en même temps, au maximum |
| `general.poll_seconds` | `20` | Fréquence de surveillance du démon |
| `general.workspace` | `~/projets` | Dossier des projets (le chef n'a pas le droit d'y écrire) |
| `general.chef_permission_mode` | `auto` | Mode de permission du chef |
| `general.chef_remote_control` | `false` | `true` : tu peux aussi parler au chef depuis l'app Claude |
| `notifications.windows` | `true` | Notifications Windows |
| `jetons.alerte` · `jetons.arret` | `80` · `95` | Seuils d'alerte et d'arrêt (en % d'une fenêtre) |
| `jetons.arret_agents` | `true` | À l'arrêt, demander aux agents de committer et de s'arrêter |
| `jetons.pause_auto` | `true` | Pause automatique si les deux abonnements sont épuisés |
| `veille.jours` | `7` | Fréquence de la veille concurrentielle (0 = désactivée) |
| `plans.validation` | `humain` | `auto` : les plans sont approuvés sans attendre ta validation |

Exemple : `jarvis regler general.max_agents 4`. Les réglages vivent dans `~/.config/jarvis/settings.toml` (permissions 600, jamais dans le dépôt).

### Raccourcis tmux (préfixe Ctrl+B)

| Touches | Action |
| --- | --- |
| Ctrl+B puis 1 | Revenir au cockpit |
| Ctrl+B puis Ctrl+S | Tableau de bord workmux |
| Ctrl+B puis L | Agent qui a fini ou qui attend |
| Ctrl+B puis D | Se détacher sans rien arrêter (`jarvis start` pour revenir) |

## Structure

```
install.sh                    Installation complète, idempotente
bin/jarvis                    Point d'entrée (bash) : start, chef, task, doctor…
bin/jarvis-codex              Codex en mode autonome (bac à sable + règles)
config/codex/jarvis.rules     Règles d'exécution des agents Codex
lib/jarvis/                   Superagent en Python (bibliothèque standard uniquement)
  cockpit.py                  Interface plein écran (curses)
  daemon.py                   Surveillance des agents + pont Telegram
  plans.py                    Plans, approbations, verrou « une tâche = un lancement »
  agents.py                   Lecture workmux, messages au chef (file d'attente si dialogue ouvert)
  notify.py · telegram.py     Telegram, notifications Windows
chef/CLAUDE.md                Rôle du chef d'orchestre
config/                       tmux et workmux
templates/                    Protocole Linear pour les projets (AGENTS.md / CLAUDE.md)
tests/                        Tests de bout en bout (faux workmux, faux Telegram, tmux isolé)
```

Données locales : `~/.config/jarvis/` (réglages, projets), `~/.local/state/jarvis/` (plans, fil, journal du chef), `~/.local/share/jarvis/chef/` (dossier de travail du chef).

## Surveillance des jetons

Jarvis lit la **consommation réelle** des deux abonnements, sur les fenêtres de 5 heures et de la semaine :

- **Claude Code** : `bin/jarvis-statusline`, installée comme barre d'état, enregistre les `rate_limits` que Claude Code fournit aux abonnés Max ;
- **Codex** : les événements `token_count` de ses fichiers de session (`~/.codex/sessions`).

```
🟢 Claude   5 h ██████░░░░ 62 %  ·  semaine ████░░░░░░ 41 %
🔴 Codex    5 h ██████████ 97 %  ·  semaine ██████░░░░ 55 %
          → épuisé jusqu'à 00:13
```

| Seuil (réglable) | Ce qui se passe |
| --- | --- |
| **Alerte** (`jetons.alerte`, 80 %) | Telegram + notification ; le chef bascule le travail vers l'autre agent |
| **Arrêt** (`jetons.arret`, 95 %) | Les agents de cet abonnement **committent leur travail et s'arrêtent** ; `jarvis task` refuse de leur assigner de nouvelles tâches |
| **Les deux épuisés** | **Pause automatique**, levée dès qu'un abonnement est remis à zéro (une pause décidée par toi n'est jamais levée automatiquement) |

Avant chaque vague, le chef répartit les tâches selon la marge restante de chaque côté. Les jauges sont en haut du cockpit, et sur Telegram avec `/jetons`.

## Linear et veille concurrentielle

- Le chef **crée et met à jour les issues Linear seul**, sans validation (étiquette `jarvis`). Le lancement d'agents, lui, passe toujours par un plan.
- Tous les `veille.jours` jours (7 par défaut), le démon lui rappelle la **veille concurrentielle** de chaque projet. Il fait rechercher les concurrents (sources à l'appui), écrit un document Linear, crée les issues des meilleures opportunités (étiquette `veille`) et t'envoie un résumé.
- Envie de plus d'autonomie ? `jarvis regler plans.validation auto` : les plans sont approuvés automatiquement (tu en es informé), toujours dans les limites de capacité, de jetons et de pause. Pour revenir en arrière : `jarvis regler plans.validation humain`.

## Agents autonomes (aucun « Yes » à cliquer)

Les agents lancés par Jarvis travaillent sans te solliciter, et sans perdre leurs garde-fous.

| | Comment | Ce qui reste bloqué |
| --- | --- | --- |
| **Claude Code** | mode `auto` : un classifieur valide les actions sûres | actions jugées risquées, règles `deny` |
| **Codex** | `bin/jarvis-codex` : bac à sable `workspace-write`, `--ask-for-approval never`, réseau autorisé, caches de paquets inscriptibles | tout ce qui sort du worktree, sauf les commandes autorisées par les règles |
| **Règles Codex** (`config/codex/jarvis.rules` → `~/.codex/rules/`) | autorisé : `git add/commit/push` de sa branche, `gh pr create/view/review…`, `pnpm/npm/uv install` | **interdit** : `git push --force`, push sur `main`, `gh pr merge/close`, `git reset/clean` |
| **Confiance des dossiers** | `jarvis task` pré-accepte chaque nouveau worktree (Claude : `~/.claude.json`, Codex : `~/.codex/config.toml`) | — |

Pourquoi Codex demandait sans arrêt : en bac à sable, `.git` est protégé en écriture, y compris le vrai `.git` d'un worktree. Chaque commit sortait donc du bac à sable et déclenchait une demande. Les règles autorisent maintenant d'avance exactement ce dont un agent a besoin.

Un agent que workmux ne suit pas encore (souvent Codex avant la fin de son premier tour) apparaît comme **🌀 actif ?** dans le cockpit et `jarvis etat`. Il compte comme occupé, et `jarvis voir projet:worktree` affiche sa sortie.

## Sécurité et coûts

- Dépôt **public** : aucun secret ici. Le jeton Telegram reste dans `~/.config/jarvis/settings.toml`.
- Le chef a des règles **deny** dans Claude Code : pas d'écriture dans tes projets ni dans les fichiers de Jarvis, pas de fusion, pas de push, pas de lecture des `.env`, pas d'accès direct à `workmux add` ni à Python.
- Approuver un plan et modifier les réglages exigent un **terminal interactif** (ou le cockpit, ou Telegram) : un agent ne peut pas s'auto-approuver.
- Telegram n'accepte que **ta** conversation privée appairée ; les groupes sont refusés.
- Les messages tapés au chef attendent en file si une demande de permission est affichée : une touche Entrée ne valide jamais une permission à ta place.
- Commence avec `max_agents = 2` ou `3`. Au-delà, tu atteins les limites des abonnements, et tu dois pouvoir relire tout ce qui sort.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

## Feuille de route

- [x] Phase 1 : installation, configurations, CLI `jarvis`, protocole Linear
- [x] Phase 2 : chef d'orchestre, plans approuvés, cockpit, démon, Telegram, plan de nuit
- [ ] Phase 3 : tableau de rentabilité (PR fusionnées par jour, temps d'agent utilisé par abonnement)
