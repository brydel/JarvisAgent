# JarvisAgent

Poste de pilotage pour faire travailler plusieurs agents IA de code en parallèle (Claude Code et Codex), en direct dans un terminal noir, avec Linear comme canal de tâches partagé.

```
 Toi ⇄ Claude (claude.ai) ─── crée et lit ───▶ Linear (issues, statuts, questions)
  │                                              ▲            ▲
  │ jarvis task …                                │            │
  ▼                                              │            │
┌─ Ton PC — WSL + tmux, session « jarvis » ──────┼────────────┼─┐
│  workmux dashboard  ⇄  Agent Claude Code (worktree BIS-82)  │ │
│                        Agent Codex       (worktree BIS-90) ─┘ │
└──────────────────────────────┬────────────────────────────────┘
                               ▼
                 GitHub — PR ouvertes par les agents, fusionnées par toi
```

Chaque agent travaille dans son propre **worktree git** et sa propre fenêtre **tmux**, géré par [workmux](https://github.com/raine/workmux). Il lit sa tâche dans Linear, y écrit son plan, ses questions (❓) et son résultat (✅), puis ouvre une pull request. Toi seul fusionnes dans `main`.

## Installation (Windows + WSL)

**1. WSL + Ubuntu** (une seule fois). Dans PowerShell **en administrateur** :

```powershell
wsl --install -d Ubuntu
```

Redémarre, puis crée ton utilisateur Ubuntu quand la fenêtre s'ouvre.

**2. Cloner et installer.** Dans Ubuntu :

```bash
sudo apt update && sudo apt install -y git
mkdir -p ~/projets && cd ~/projets
git clone https://github.com/brydel/JarvisAgent.git
cd JarvisAgent
./install.sh
```

Le script installe tmux, gh, Node 22, pnpm, Claude Code, Codex et workmux, lie les configurations, active les statuts des agents et branche Linear. Il est **idempotent** : relance-le autant de fois que tu veux.

**3. Les connexions** (une seule fois). À la fin, le script affiche une liste numérotée « À faire maintenant » : connexion à Claude, à Codex, à GitHub et autorisation Linear dans le navigateur. Fais-les dans l'ordre.

**4. Vérifier.** Ouvre un nouveau terminal :

```bash
jarvis doctor
```

Tout doit être vert.

> Garde tes projets dans Linux (`~/projets/...`), jamais dans `/mnt/c/...` : sur le disque Windows, git et les agents sont beaucoup plus lents.

## Utilisation

```bash
jarvis start                              # ouvre la session « jarvis »
cd ~/projets/repriceo
jarvis init-project                       # une fois par projet : AGENTS.md + CLAUDE.md
jarvis task BIS-82 claude auth-avancee    # agent Claude sur l'issue BIS-82
jarvis task BIS-90 codex landing          # agent Codex sur l'issue BIS-90
jarvis board                              # tableau de bord en direct
```

| Commande | Rôle |
| --- | --- |
| `jarvis start` | Ouvre ou rejoint la session tmux `jarvis` |
| `jarvis task <ISSUE> <claude\|codex> [desc]` | Crée le worktree, la branche et lance l'agent avec le bon prompt |
| `jarvis board` | Tableau de bord workmux : aperçu en direct, diff, saisie vers l'agent |
| `jarvis status` | Liste des tâches et état de chaque agent |
| `jarvis init-project [dossier]` | Copie le protocole Linear dans un projet |
| `jarvis doctor` | Vérifie outils, configurations et connexions |

### Raccourcis tmux (préfixe Ctrl+B)

| Touches | Action |
| --- | --- |
| Ctrl+B puis Ctrl+S | Tableau de bord des agents |
| Ctrl+B puis Ctrl+T | Barre latérale des statuts |
| Ctrl+B puis L | Aller à l'agent qui a fini ou qui attend |
| Ctrl+B puis Tab | Basculer entre les deux derniers agents |
| Ctrl+B puis D | Se détacher sans rien arrêter (`jarvis start` pour revenir) |

Dans le tableau de bord : **1 à 9** pour sauter à un agent, **p** pour jeter un œil, **i** pour écrire à l'agent, **d** pour son diff, **q** pour quitter.

## La boucle avec Claude

1. Tu décris l'objectif à Claude dans claude.ai.
2. Claude crée ou réécrit les issues Linear avec un brief d'agent précis et l'étiquette `agent:claude` ou `agent:codex`.
3. Tu lances `jarvis task …` pour chaque issue.
4. Les agents commentent leur plan, leurs questions et leurs résultats dans Linear.
5. Tu demandes « fais le point » à Claude : il lit Linear, répond aux questions des agents et prépare la vague suivante.
6. Tu relis les PR et tu fusionnes.

## Structure

```
install.sh                    Installation complète, idempotente
bin/jarvis                    La CLI de pilotage
config/tmux.conf              tmux : souris, look noir/cyan, raccourcis agents
config/workmux/config.yaml    workmux : profils cc (Claude) et cx (Codex), disposition
templates/AGENTS.md           Protocole Linear pour Codex
templates/CLAUDE.md           Protocole Linear pour Claude Code (même contenu)
```

## Sécurité et coûts

- Ce dépôt est **public** : n'y mets jamais de clé, de jeton ni de `.env`.
- Garde les permissions par défaut des agents. N'utilise `--dangerously-skip-permissions` ou `--yolo` que dans le bac à sable de workmux.
- Commence avec **2 agents en parallèle**, 3 au maximum : au-delà, tu atteins les limites des abonnements et tu ne peux plus tout relire.

## Feuille de route

- [x] Phase 1 — installation, configurations, CLI `jarvis`, protocole Linear
- [ ] Phase 2 — `jarvis brief` : résumé terminal de l'état Linear de chaque agent
- [ ] Phase 3 — envoi automatique : surveiller les issues `prêt-pour-agent` et lancer `jarvis task` tout seul
