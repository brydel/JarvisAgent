# JarvisAgent

Une **usine à produits numériques** sur ton PC : des agents IA **spécialisés** (architecte, back-end, front-end, DevOps, sécurité, qualité, design, marketing, vidéo…) travaillent en parallèle sur **plusieurs SaaS à la fois**, exécutés par Claude Code ou Codex avec **le modèle qui convient à chaque tâche**. Un **chef d'orchestre** IA planifie, lance, surveille et fait contre-relire. Tu valides depuis ton terminal ou depuis ton téléphone (Telegram), et tu reçois les livrables finis : pull requests, vidéos de produit, dossiers de campagne.

```
 Toi ── Telegram / cockpit / web ──▶ démon Jarvis ──▶ CHEF D'ORCHESTRE (Claude, rôle chef/CLAUDE.md)
  ▲        ✅ Approuver / ✋ Refuser       │                │ propose des plans → tu valides
  │                                       │                │ jarvis task --plan …
  │                                       ▼                ▼
  │            surveillance, jetons, PC ◀─┤   ROUTEUR : rôle + taille + jetons → fournisseur, modèle, effort
  │                                       │                │
  │                                       ▼                ▼
  │        Conception · Fabrication · Exploitation · Qualité · Studio · Veille
  │        (1 spécialiste = 1 worktree + 1 fenêtre tmux, Claude ou Codex)
  │                                       │
  └── PR à fusionner (GitHub) · vidéos et dossiers (Telegram) ◀── contre-relecture par l'autre fournisseur
```

## Ce que fait l'usine

- **Spécialise** : chaque tâche part avec un rôle. L'agent reçoit le brief de son métier (ses règles, sa définition de « fini »), et tu vois dans le cockpit quel atelier travaille : DevOps, front-end, vidéo…
- **Choisit le modèle** : un routeur affecte à chaque tâche un fournisseur (Claude ou Codex), un modèle et un effort de raisonnement, selon le rôle, la taille de la tâche, les atouts de chaque modèle et les jetons qu'il reste. Le choix est expliqué, et tu le valides avec le plan.
- **Planifie** : le chef lit tes projets et leurs issues Linear, puis prépare des **vagues** de tâches indépendantes.
- **Se remet en question** : pré-mortem et « avocat du diable » avant chaque plan, bilan avec causes racines après chaque vague.
- **Te demande la permission** : chaque plan t'arrive sur Telegram avec des boutons **Approuver / Refuser**. Le chef ne peut lancer **que** ce que tu as approuvé, une seule fois par tâche, avec le modèle validé : ce n'est pas une consigne, `jarvis task` le refuse techniquement.
- **Fait contre-relire** : ce que Claude produit, Codex le relit, et inversement. Le verdict est enregistré ; le bilan liste ce qui n'a pas été relu.
- **Produit plus que du code** : le **studio** filme le produit, anime une présentation, monte la vidéo, la contrôle et te l'envoie sur Telegram, avec le dossier de campagne.
- **Gère les jetons et le PC** : consommation réelle des deux abonnements, prévision d'épuisement, bascule sur l'autre fournisseur, capacité adaptée à la mémoire et à la batterie.
- **Travaille la nuit** : le **plan de nuit** est une liste ordonnée que tu valides avant de dormir. Bilan le matin.
- **Garde-fous** : le chef ne code pas, ne fusionne pas, ne pousse rien, ne lit pas les `.env`, ne publie rien à l'extérieur. Il respecte la capacité et la **pause** (`/pause` sur Telegram).

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

Le script installe tmux, gh, Node 22, Claude Code, Codex, workmux et le studio vidéo (ffmpeg, Playwright, Chromium ; `--no-studio` pour s'en passer), active le suivi des agents et branche Linear. Il ignore les versions Windows de `claude` et `codex` qui traînent dans le PATH de WSL. Tu peux le relancer autant de fois que tu veux.

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

**6. Les modèles** : `jarvis modele verifier` essaie chaque modèle du catalogue avec tes abonnements (une courte requête par modèle). Le démon le refait seul chaque semaine.

**7. Vérifier** : `jarvis doctor`. Tout doit être vert.

**Mise à jour** : `git pull` dans le dépôt, `./install.sh` (idempotent), puis `jarvis relancer --chef`. Le démon, le cockpit et le chef repartent avec la nouvelle version ; les agents déjà lancés ne sont pas touchés et finissent leur tâche.

> Garde tes projets dans Linux (`~/projets/...`), jamais dans `/mnt/c/...`.

## Utilisation

```bash
jarvis start      # session « jarvis » : cockpit (fenêtre 1) + démon (fenêtre 2)
jarvis chef       # lance le chef d'orchestre (fenêtre « chef ») : il propose son premier plan
```

Ensuite, tu pilotes depuis le **cockpit** ou depuis **Telegram**.

### Le cockpit

```
 ◆ J A R V I S  ·  usine                                          ● démon  ● chef  ● Telegram    10:14:17
 Agents 5/5   ? 1 attend   ✓ 1 terminé   ◇ 2 à valider   ▣ 2 livrables
 ● Claude 5h █████░░░  62%  sem ███░░░░░  41%  ↗23%/h ⚠ 1 h 24    ● Codex 5h ██░░░░░░  22%     ▪ 7.3 Go libres
╭─ ATELIERS ──────────────────────────────────── 5 au travail · v : vue ─╮╭─ À VALIDER ─────────────── 2 ─╮
│ CONCEPTION · libres : DSG                                              ││ ◇ P-0001 Vague auth [vague]   │
│  ARC  Architecte ▶ repriceo     bis-90-adr-auth   Claude · fable · high ││    FRT  BIS-82 → Codex · sol  │
│ FABRICATION · libres : DAT DEV                                         ││    SEC  BIS-83 → Codex · astra│
│  BCK  Back-end   ? repriceo     bis-71-guardrails Codex · sol · high    ││ ◈ M-0001 modèle sol (codex)   │
│  FRT  Front-end  ▶ jobpilot-ia  jp-12-onboarding  Codex · sol · high    │╰───────────────────────────────╯
│ EXPLOITATION · libres : SEC                                            │╭─ LIVRABLES ─────────────── 2 ─╮
│  OPS  DevOps     ▶ repriceo     bis-77-pipeline   Codex · sol · high    ││ ▶ L-0002 Teaser 15 s   09:53  │
│ STUDIO · libres : MKT RED                                              ││ ≡ L-0001 Dossier       08:43  │
│  VID  Vidéo      ▶ jobpilot-ia  jp-20-video       Claude · opus · high  │╰───────────────────────────────╯
╰────────────────────────────────────────────────────────────────────────╯
╭─ FIL D'ACTIVITÉ ─────────────────────────────────────────────── p : aperçu · d : fiche · b : bilan ─╮
│ 10:13 » repriceo BIS-77 lancé → codex · sol · high [devops] (P-0001)                                 │
```

Chaque agent porte la pastille colorée de son rôle. Les postes libres de chaque équipe tiennent sur la ligne d'en-tête.

| Touche | Action |
| --- | --- |
| **Tab** | Passer du panneau Ateliers au panneau À valider |
| **↑ ↓** | Choisir un agent, un plan ou une proposition de modèle |
| **Entrée** | Ouvrir la fenêtre de l'agent (Ctrl+B puis 1 pour revenir) |
| **o** / **x** | Approuver / refuser le plan ou la proposition sélectionnés |
| **p** | Aperçu en direct de la sortie de l'agent sélectionné |
| **d** | Fiche de la tâche : rôle, modèle et pourquoi ce choix, plan d'origine, jetons, verdict |
| **b** | Bilan des 7 derniers jours (par fournisseur, rôle et modèle) |
| **v** | Basculer entre la vue par ateliers et la liste simple |
| **m** | Écrire au chef |
| **e** | Écrire directement à l'agent sélectionné |
| **c** | Ouvrir la fenêtre du chef |
| **P** | Pause / reprise : plus aucun nouveau lancement |
| **q** | Quitter le cockpit |

### Le tableau de bord web

`jarvis web` (ou http://localhost:7717 dès que le démon tourne) ouvre le **plan de l'usine** dans ton navigateur Windows : une travée par équipe, un poste par spécialité, les postes occupés allumés à la couleur de leur rôle, les réservoirs de jetons, les plans en attente, et les livrables avec leur lecteur vidéo.

Il est en **lecture seule** et ne répond qu'à ce PC : approuver un plan reste réservé au cockpit, au terminal et à Telegram. `jarvis regler web.actif false` le coupe.

### Telegram

| Message | Effet |
| --- | --- |
| Boutons ✅ / ✋ sous un plan | Approuver ou refuser |
| `/etat` | Agents et plans en cours |
| `/usine` | Les ateliers : quel spécialiste travaille sur quoi, avec quel modèle |
| `/plans` | Plans et propositions de modèles à valider, avec boutons |
| `/livrables` | Vidéos, visuels et rapports produits |
| `/modeles` | Catalogue des modèles et leur disponibilité |
| `/bilan` | Ce que l'usine a produit sur 7 jours |
| `/jetons` | Consommation Claude et Codex, rythme et prévision |
| `/sante` | État du PC : mémoire, disque, Docker, batterie, redémarrage Windows en attente |
| `/pause` · `/reprendre` | Bloquer ou relancer les lancements |
| N'importe quel texte | Transmis au chef (« Priorise JobPilot cette nuit ») |
| Une **image** ou un **fichier** (avec légende) | Enregistré dans le dossier du chef, qui l'ouvre (maquette, direction artistique, capture, PDF) |

Tu reçois aussi les questions du chef (❓), ses bilans (📝) et les **livrables** (🎬 vidéos, 🖼 visuels, 📄 documents), avec une notification Windows quand tu es sur ton PC.

### Une journée type

1. **Matin** : lis le bilan de nuit sur Telegram, puis relis et fusionne les PR prêtes.
2. **Journée** : le chef propose des vagues, tu approuves en un clic, tu réponds à ses questions. Tu peux lui écrire « prépare la campagne de lancement de JobPilot » : il découpe, fait produire, contrôle, et t'envoie la vidéo et le dossier.
3. **Soir** : écris « je vais dormir » au chef. Il propose un **plan de nuit**, tu l'approuves, et l'équipe travaille pendant que tu dors.

## Commandes

| Commande | Rôle |
| --- | --- |
| `jarvis start [--fond]` | Session `jarvis` : cockpit + démon. Après un redémarrage du PC, reprend les agents qui travaillaient et le chef |
| `jarvis chef` | Lance ou rejoint le chef d'orchestre |
| `jarvis cockpit` · `jarvis web` | Interface plein écran · tableau de bord dans le navigateur |
| `jarvis etat` · `jarvis usine` | État complet (agents, plans, projets, capacité) · les ateliers |
| `jarvis plan liste` · `voir P-1` · `ok P-1` · `non P-1 raison` | Gérer les plans depuis le terminal |
| `jarvis fil [n]` · `jarvis journal` | Événements récents · journal du chef |
| `jarvis voir projet:worktree` | Sortie récente d'un agent |
| `jarvis fermer projet:worktree` · `jarvis fermer --termines` | Ferme la fenêtre d'agents terminés (worktree, branche et conversation conservés) |
| `jarvis reprendre [--essai]` | Relance les agents interrompus par un redémarrage |
| `jarvis sante` | État du PC |
| `jarvis autostart installer\|retirer\|etat` | Démarrer Jarvis tout seul à l'ouverture de session Windows |
| `jarvis reparer-git <projet>` | Après un arrêt brutal : sauvegarde `.git`, recrée les références distantes cassées, `fetch` et `fsck` |
| `jarvis task [--projet P] [--plan ID] <ISSUE> <claude\|codex\|auto> [desc] [--role R] [--taille S\|M\|L] [--modele M] [--consignes f.md] [--revue N°PR]` | Lancer un agent spécialisé sur une issue (`--revue` : relecture seule d'une PR). Hors terminal interactif, un plan approuvé est obligatoire et fixe le rôle et le modèle |
| `jarvis role` · `jarvis role voir <nom>` | Les spécialités et le brief de chacune |
| `jarvis modele` · `choisir --role R` · `verifier` · `ok\|non M-1` | Catalogue des modèles · ce que le routeur choisirait · essai avec tes abonnements · décider d'une proposition du chef |
| `jarvis tache [n]` · `jarvis bilan [--jours 7]` | Registre des tâches (rôle, modèle, jetons, verdict) · bilan par fournisseur, rôle et modèle |
| `jarvis verdict <projet> <ISSUE> pret\|corrections [note]` | Enregistrer le verdict d'une contre-relecture |
| `jarvis studio verifier <fichier>` | Contrôle technique d'une vidéo ou d'un visuel + planche-contact |
| `jarvis livrer <fichier> [--titre T] [--legende L]` | Contrôler un livrable puis te l'envoyer sur Telegram |
| `jarvis livrables [<projet> <ISSUE>]` | Livrables récents, ou dossier d'une issue |
| `jarvis projet ajouter\|liste` | Registre des projets |
| `jarvis telegram config\|test` | Liaison Telegram |
| `jarvis regler <clé> <valeur>` | Réglages (voir ci-dessous) |
| `jarvis board` · `jarvis status` | Tableau de bord workmux · tâches du projet courant |
| `jarvis init-project [dossier]` | Protocole Linear dans un projet |
| `jarvis doctor` | Diagnostic complet |
| `jarvis relancer [--chef]` | Après une mise à jour : relance le démon et le cockpit (et le chef), sans toucher aux agents (pause « maintenance » le temps de l'opération) |
| `jarvis pause [poser\|lever <cause> [note]]` | Pauses à causes indépendantes : humain, batterie, quota, ressources, incident, maintenance |
| `jarvis admission etat` | Réservations de lancement en attente et opérations lourdes déclarées |
| `jarvis lourd debut\|fin\|exec\|liste` | Déclarer une opération lourde (compilation, tests, navigateur, vidéo) ; `exec` attend sa place puis lance la commande à priorité réduite |
| `jarvis politique [verifier <action>\|deleguer\|revoquer\|exceptions\|exception E-1 accordee\|refusee]` | Politique de délégation (niveaux 1/2/3), délégations plafonnées, file d'exceptions |
| `jarvis budget [definir\|verifier\|engager\|encaisser]` | Enveloppes de dépense (non renseignée = zéro) et mouvements réels |
| `jarvis fournisseurs` | Capacités déclarées de Claude et Codex : CLI, modèles vérifiés, quotas et fraîcheur |
| `jarvis proposition [soumettre\|accepter\|rejeter\|confier\|terminer\|importer]` | File de travaux partagée (ton dot, GitHub, toi) : identifiants stables, un exécutant, une preuve |
| `jarvis audit [n] [--verifier]` | Journal d'audit des décisions, chaîne d'empreintes |
| `jarvis diagnostic` | Inventaire léger du poste (rapport expurgé sous `~/.local/share/jarvis/diagnostics/`) |
| `jarvis profil [liste\|voir\|appliquer <nom>]` | Profils `laptop-conservative` et `workstation` (settings.toml sauvegardé avant) |
| `jarvis tache voir\|echec <T>` · `jarvis tache relancer <T> --autoriser` | Détail d'un essai (classe d'échec, essais, jetons) · classer un échec · débloquer un essai après escalade (toi seulement) |
| `jarvis budget-jetons voir <T>` | Jetons consommés par une unité de travail face à son plafond |
| `jarvis cout [tache <T>\|projet <P> --periode 7j\|semaine]` | Équivalent API des tâches (tarifs publics) : pas une dépense, tu es à l'abonnement |
| `jarvis memoire noter\|chercher\|liste` | Mémoire du chef : décisions, échecs, leçons, recherche pondérée |
| `jarvis bilan quotidien [--envoyer]` | Le bilan du matin (envoyé seul sur Telegram à `bilan.heure`) |
| `jarvis secrets verifier --projet P` | Secrets que recevrait chaque rôle (noms seuls) |
| `jarvis eval liste\|verifier\|resultats` · `jarvis eval lancer <role/cas> --agent claude --confirmer` | Harnais d'évaluation des rôles (15 cas jugés par scripts) · un vrai essai d'agent (consomme du quota, toi seulement) |
| `jarvis rejouer <T> [--depuis N]` | Chronologie d'une tâche : plan, admission, tours, verdict, fin (reconstruction, rien n'est relancé) |
| `jarvis traces [exporter\|envoyer]` | Dernières exécutions avec durée, jetons, équivalent API · export OpenTelemetry (fichier ou collecteur) |
| `jarvis rollback proposer\|demander\|executer <T>` | Défaire par `git revert` les commits d'une tâche : proposition, demande Telegram (bouton Revert), exécution (toi seulement) |
| `jarvis proxy voir\|config` | Configuration LiteLLM pour les fonctions IA des produits (désactivée, jamais pour les agents) |
| `jarvis skill auditer\|installer <source>` · `jarvis skill approuver\|epingler <nom>` | Registre des skills : audit, quarantaine · activation et épinglage (toi seulement) |
| `jarvis role candidats\|proposer` · `jarvis role approuver\|promouvoir RB-…` | Briefs candidats (optimiseur ou chef) · essai sur 10 % puis promotion (toi seulement) |
| `jarvis stockage etat\|migrer\|revenir` | État en JSON (défaut) ou SQLite : migration vérifiée, démon arrêté |
| `jarvis executant liste` | Exécutants déclarés (capacité mesurée) et bail d'orchestrateur |

### Réglages

| Clé | Défaut | Rôle |
| --- | --- | --- |
| `general.max_agents` | `3` | Agents occupés en même temps, au maximum |
| `general.poll_seconds` | `20` | Fréquence de surveillance du démon |
| `general.workspace` | `~/projets` | Dossier des projets (le chef n'a pas le droit d'y écrire) |
| `general.chef_permission_mode` | `auto` | Mode de permission du chef |
| `general.chef_remote_control` | `false` | `true` : tu peux aussi parler au chef depuis l'app Claude |
| `general.battement_min` | `30` | Réveille le chef s'il reste de la place et des jetons après N min de calme (0 = jamais ; l'intervalle double tant qu'il ne trouve rien, jusqu'à 4 h) |
| `general.fermeture_auto_min` | `60` | Ferme la fenêtre d'un agent terminé depuis N min (0 = jamais) |
| `general.reprise_auto` | `true` | Après un redémarrage, `jarvis start` relance les agents qui travaillaient et le chef |
| `general.chef_relance_auto` | `true` | Relancer le chef s'il s'arrête alors qu'il reste du travail (3 fois par heure au plus) |
| `general.blocage_min` · `general.duree_max_min` | `45` · `240` | Prévenir le chef quand un agent n'affiche plus rien depuis N min, ou travaille depuis plus de N min |
| `codex.mode` | `bac-a-sable` | `complet` : Codex sans bac à sable (dernier recours si `jarvis doctor` dit qu'il ne peut pas committer) |
| `sante.active` · `sante.disque_min_go` · `sante.memoire_min_pct` | `true` · `10` · `10` | Surveillance du PC et seuils d'alerte |
| `sante.capacite_auto` · `sante.memoire_par_agent_mo` | `true` · `1200` | Moins d'agents quand la mémoire manque ; aucun lancement sur batterie faible, disque plein ou processeur saturé |
| `sante.batterie_min_pct` · `sante.batterie_arret_pct` | `30` · `12` | Sur batterie : plus de lancement sous le premier seuil ; sous le second, les agents committent et Jarvis se met en pause |
| `notifications.windows` | `true` | Notifications Windows |
| `jetons.alerte` · `jetons.arret` | `80` · `95` | Seuils d'alerte et d'arrêt (en % d'une fenêtre) |
| `jetons.arret_agents` | `true` | À l'arrêt, demander aux agents de committer et de s'arrêter |
| `jetons.pause_auto` | `true` | Pause automatique si les deux abonnements sont épuisés |
| `jetons.semaine_prudence` | `70` | Au-delà de ce % de la fenêtre semaine, les modèles coûteux sont réservés aux tâches de taille L |
| `modeles.verification` · `modeles.verification_jours` | `true` · `7` | N'utiliser un modèle qu'après un essai réussi avec ton abonnement ; fréquence du nouvel essai |
| `veille.modeles_jours` | `14` | Fréquence de la veille des modèles (0 = désactivée) |
| `studio.taille_max_mo` | `49` | Taille maximale d'un livrable envoyé sur Telegram |
| `web.actif` · `web.port` | `true` · `7717` | Tableau de bord web (lecture seule, ce PC uniquement) |
| `veille.jours` | `7` | Fréquence de la veille concurrentielle (0 = désactivée) |
| `plans.validation` | `humain` | `auto` : les plans sont approuvés sans attendre ta validation (pauses, capacité, jetons, politique et admission restent) |
| `admission.operations_lourdes_max` | `1` | Opérations lourdes simultanées (compilation, tests, navigateur, vidéo) |
| `admission.reservation_min` | `15` | Une réservation de lancement jamais confirmée expire après N min |
| `admission.charge_max_par_coeur` · `admission.memoire_reserve_mo` | `2.5` · `1500` | Charge par cœur au-delà de laquelle rien ne part ; mémoire gardée pour Windows et le chef |
| `admission.pression_memoire_pct` · `admission.hysterese_min` | `25` · `5` | Pause « ressources » sur pression mémoire soutenue ; délai de retour au calme |
| `jetons.peremption_h` | `6` | Une mesure de quota plus vieille que N h vaut « prudence », jamais « feu vert » |
| `propositions.max_par_jour` · `propositions.github_depot` | `3` · vide | Plafond d'acceptations par source et par jour ; dépôt GitHub dont les issues `jarvis-proposition` sont importées |
| `budget_jetons.multiplicateur` · `budget_jetons.estimation_s/m/l` | `3` · `300000/800000/2000000` | Plafond de jetons par unité de travail = multiplicateur × estimation (médiane de l'historique dès 5 tâches) |
| `couts.devise` · `couts.taux` | `EUR` · `0` | Affichage de l'équivalent API ; 0 = en dollars US |
| `bilan.actif` · `bilan.heure` | `true` · `08:00` | Bilan quotidien sur Telegram |
| `optimisation.hebdo` · `optimisation.roles` · `optimisation.jour` · `optimisation.heure` | `false` · 5 rôles · `7` · `02:00` | Optimisation hebdomadaire d'un brief (un rôle par semaine, sur tes abonnements, candidat soumis à ta décision) |
| `optimisation.canari_pct` | `10` | Part des tâches d'un rôle qui essaient un brief candidat approuvé |
| `stockage.backend` | `json` | `sqlite` après `jarvis stockage migrer` (ne pas changer à la main) |
| `observabilite.otlp_endpoint` | vide | Collecteur OpenTelemetry (ex. `http://localhost:4318`) pour `jarvis traces envoyer` ; vide = rien ne sort |

Par projet, `execution = "e2b"` dans `projects.toml` choisit le backend E2B (service payant : refusé sans SDK, clé `E2B_API_KEY` et budget `infrastructure`) ; par défaut `workmux`.

Exemple : `jarvis regler general.max_agents 4`. Les réglages vivent dans `~/.config/jarvis/settings.toml` (permissions 600, jamais dans le dépôt).

### Raccourcis tmux (préfixe Ctrl+B)

| Touches | Action |
| --- | --- |
| Ctrl+B puis 1 | Revenir au cockpit |
| Ctrl+B puis Ctrl+S | Tableau de bord workmux |
| Ctrl+B puis L | Agent qui a fini ou qui attend |
| Ctrl+B puis D | Se détacher sans rien arrêter (`jarvis start` pour revenir) |

## Les rôles : une équipe de spécialistes

| Équipe | Rôles (`jarvis role`) |
| --- | --- |
| Conception | `architecte` · `design` (direction artistique, porte qualité visuelle) |
| Fabrication | `backend` · `frontend` · `data` · `ia-produit` (fonctions intelligentes dans le produit) · `generaliste` |
| Exploitation | `devops` · `securite` |
| Qualité | `qa` · `revue` (contre-relecture, aucun commit) |
| Studio | `marketing` · `video` · `redaction` |
| Veille | `recherche` |

### Veille approfondie, design et IA produit

Trois compétences (skills) liées pour Claude Code et Codex par `./install.sh` :

- **`jarvis-veille`** : la veille concurrentielle démonte au lieu de résumer. Matrice de parité sourcée (40 fonctionnalités au moins), captures côte à côte des pages publiques des concurrents et de notre produit (`capturer.cjs` : bureau et mobile, `robots.txt` respecté, une page toutes les 3 s, planche de comparaison), démontage écran par écran, décisions imiter / dépasser / ignorer, une fonctionnalité signature, et un backlog avec captures et critères visuels. On imite des fonctionnalités et des motifs d'interface, jamais le code, les textes ou l'identité visuelle d'un concurrent.
- **`jarvis-design`** : une direction artistique écrite dans le dépôt (`design/direction.md` + jetons), proposée en 2 à 3 variantes que tu choisis, puis une grille de notation sur captures que l'auteur ET le relecteur remplissent. Un écran clé sous le seuil repart en corrections.
- **`ia-produit`** (rôle) : ajoute de l'intelligence au produit (analyse expliquée, recherche en langage naturel, alertes, résumés) derrière un drapeau désactivé par défaut, avec couche fournisseur, jeu d'essai, coût par 1 000 utilisateurs, et un fournisseur simulé tant qu'aucun budget d'API n'existe.

Le chef lance désormais la veille comme une vraie tâche (`@recherche+L`), te livre les planches, met une tâche `@design+L` en tête si l'écart visuel est net, et réserve au moins un élément sur trois de chaque vague à ce qui se voit (parité, signature, design, IA).

Un rôle est un fichier `roles/<nom>.md` : un en-tête (titre, équipe, couleur, niveau attendu, fournisseur préféré) et le **brief** que l'agent reçoit en plus des consignes du chef. Pour adapter un rôle ou en créer un, dépose un fichier du même format dans `~/.config/jarvis/roles/` : il remplace ou complète ceux du dépôt, sans toucher au code.

Dans un plan, une tâche s'écrit `projet:ISSUE:agent[/modèle][@rôle][+taille][%jetons][:description]` (`%3M` : plafond de jetons imposé) :

```bash
jarvis plan nouveau --titre "Vague auth" --pourquoi "…" \
  --item repriceo:BIS-82:auto@frontend+M:auth-2fa \
  --item repriceo:BIS-83:auto@securite+L:audit-sessions \
  --item repriceo:BIS-82:auto@revue:revue-pr-41
```

```
P-0007 — Vague auth  [vague, ⏳ en attente]
  · repriceo BIS-82 → Codex · sol · high  [🖥️ Développeur front-end, taille M] — auth-2fa
      secours si codex est épuisé : Claude · sonnet · medium
  · repriceo BIS-83 → Claude · fable · xhigh  [🛡️ Ingénieur sécurité, taille L] — audit-sessions
      secours si claude est épuisé : Codex · astra · xhigh
```

## Le routeur de modèles

`agent` vaut `claude`, `codex` ou **`auto`**. Avec `auto`, le routeur choisit, et explique son choix (`jarvis modele choisir --role frontend --taille M`). Il tient compte :

1. du **niveau** visé : celui du rôle, ajusté par la taille (`S` −1, `M`, `L` +1). Un modèle trop faible est pénalisé plus fort qu'un modèle trop puissant ;
2. des **atouts** de chaque modèle (les rôles pour lesquels il est préféré) et du fournisseur préféré du rôle ;
3. des **jetons** : marge de chaque abonnement, alerte, prévision d'épuisement avant la remise à zéro, fenêtre semaine (au-delà de 70 %, les modèles coûteux sont gardés pour les tâches `L`) ;
4. de la **disponibilité réelle** : un modèle n'est utilisé qu'après un essai réussi avec ton abonnement. Un identifiant retiré ou absent de ton forfait est ignoré, et le modèle par défaut du CLI prend le relais.

L'**effort de raisonnement** suit la taille. Chaque tâche reçoit aussi un **secours** chez l'autre fournisseur, utilisable seulement si le premier est épuisé au lancement : la nuit ne s'arrête pas parce qu'un abonnement est vide.

Le catalogue vit dans `config/modeles.toml` (valeurs du dépôt) et `~/.config/jarvis/modeles.toml` (tes ajustements). Il évolue de deux façons :

- **Veille des modèles** : tous les 14 jours, le chef cherche les nouveautés de Claude Code et de Codex dans les sources officielles, croise avec le bilan de l'usine, et **propose** des changements (`jarvis modele proposer … --source <URL>`). Tu acceptes ou refuses (Telegram, cockpit, `jarvis modele ok M-0001`). Un modèle accepté est essayé avant d'être utilisé.
- **À la main** : édite `~/.config/jarvis/modeles.toml`, puis `jarvis modele verifier`.

> Les identifiants de `config/modeles.toml` ont été relevés dans la documentation officielle le 13 octobre 2026. Ils changent tous les quelques mois : `jarvis modele` montre ce qui est vérifié chez toi.

## Le studio : vidéos, visuels, campagnes

Demande au chef « prépare la campagne publicitaire de JobPilot » : tu n'obtiens pas un texte, tu reçois sur Telegram une **vidéo de produit** et le **dossier de campagne**.

```
 stratège marketing ──▶ brief, angles, annonces, scénario
 motion designer   ──▶ filme l'application (enregistrer.cjs) ─▶ scènes animées (rendre.cjs)
                       ─▶ montage (monter.py) ─▶ contrôle + planche-contact (verifier.py) ─▶ corrige, recommence
 relecteur (autre fournisseur) ──▶ regarde la planche-contact, vérifie chaque promesse contre le produit
 chef ──▶ jarvis studio verifier ─▶ regarde ─▶ jarvis livrer ──▶ ton Telegram
```

- `skills/jarvis-studio/` contient la méthode (`SKILL.md`) et les scripts. Tout est local et gratuit : Chromium filme et dessine, ffmpeg monte.
- **Filmer** : un scénario JSON décrit le parcours dans l'application lancée en local, avec un curseur visible et des zones sensibles floutées.
- **Animer** : un storyboard JSON décrit titres, captures mises en scène (zoom, repères), arguments et écran de fin, aux couleurs de la marque. Le rendu est calculé image par image : fluide et identique à chaque fois, en 16:9, 9:16, 1:1 ou 4:5.
- **Contrôler** : durée, définition, fluidité, compatibilité, taille, écrans noirs, images figées, plus une planche-contact que l'agent, le relecteur et le chef regardent.
- **Livrer** : `jarvis livrer` refuse une vidéo qui échoue au contrôle. Les fichiers vivent dans `~/.local/share/jarvis/livrables/<projet>/<ISSUE>/`, jamais dans git.
- La **diffusion** (publier, payer une publicité, écrire à des clients) reste ta décision : l'usine prépare, tu déclenches.

Pas de voix ni de musique générées : une musique n'est ajoutée que si tu fournis le fichier.

## Structure

```
install.sh                    Installation complète, idempotente
bin/jarvis                    Point d'entrée (bash) : start, chef, task, doctor…
bin/jarvis-claude             Claude Code en mode auto, avec le modèle de la tâche
bin/jarvis-codex              Codex en mode autonome (bac à sable + règles), avec le modèle de la tâche
config/modeles.toml           Catalogue des modèles
config/codex/jarvis.rules     Règles d'exécution des agents Codex
roles/                        Un fichier par spécialité : en-tête + brief de l'agent
skills/jarvis-studio/         Studio : méthode et scripts (filmer, animer, monter, contrôler)
lib/jarvis/                   Superagent en Python (bibliothèque standard uniquement)
  roles.py · modeles.py       Rôles, catalogue, routeur, propositions du chef
  plans.py                    Plans, approbations, verrou « une tâche = un lancement », secours
  taches.py                   Registre des tâches : rôle, modèle, durée, jetons, verdict, bilan
  usage.py                    Jetons : fenêtres 5 h et semaine, rythme, prévision, jetons par tâche
  cockpit.py                  Interface plein écran par ateliers (curses)
  web.py · usine.html         Tableau de bord web en lecture seule
  daemon.py                   Surveillance, chiens de garde, battement, ménage, santé + pont Telegram
  poste.py                    Reprise après redémarrage, santé et capacité du PC, réparation git
  studio.py · livrables.py    Contrôle des vidéos, registre des livrables, envoi Telegram
  agents.py                   Lecture workmux, messages au chef (file d'attente si dialogue ouvert)
  notify.py · telegram.py     Telegram (messages et fichiers), notifications Windows
chef/CLAUDE.md                Rôle du chef d'orchestre
config/                       tmux et workmux
templates/                    Protocole Linear pour les projets (AGENTS.md / CLAUDE.md)
tests/                        Tests de bout en bout (faux workmux, faux Telegram, faux CLI, tmux isolé)
```

Données locales : `~/.config/jarvis/` (réglages, projets, catalogue et rôles personnels), `~/.local/state/jarvis/` (plans, registre des tâches, fil, journal du chef), `~/.local/share/jarvis/` (dossier de travail du chef, livrables).

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

**Prévision.** Le démon mesure le rythme de consommation de la fenêtre 5 heures. Quand il mène au seuil d'arrêt avant la remise à zéro, tu es prévenu 45 minutes avant (et le chef aussi), et le routeur évite ce fournisseur pour les nouvelles tâches :

```
🟢 Claude   5 h ██████░░░░ 62 %  ·  semaine ████░░░░░░ 41 %
          rythme 24 %/h → seuil d'arrêt dans 1 h 22 (avant la remise à zéro)
```

**Par tâche.** À la fin de chaque tâche, Jarvis lit dans les journaux de Claude Code et de Codex les jetons qu'elle a consommés. `jarvis bilan` les additionne par fournisseur, par rôle et par modèle : tu vois ce que coûte chaque atelier et ce qu'il livre.

Le routeur tient compte de ces marges à chaque affectation. Les jauges sont en haut du cockpit, sur le tableau de bord web, et sur Telegram avec `/jetons`.

## Linear et veille concurrentielle

- Le chef **crée et met à jour les issues Linear seul**, sans validation (étiquette `jarvis`). Le lancement d'agents, lui, passe toujours par un plan.
- Tous les `veille.jours` jours (7 par défaut), le démon lui rappelle la **veille concurrentielle** de chaque projet. Il fait rechercher les concurrents (sources à l'appui), écrit un document Linear, crée les issues des meilleures opportunités (étiquette `veille`) et t'envoie un résumé.
- Envie de plus d'autonomie ? `jarvis regler plans.validation auto` : les plans sont approuvés automatiquement (tu en es informé), toujours dans les limites de capacité, de jetons et de pause. Pour revenir en arrière : `jarvis regler plans.validation humain`.

## Agents autonomes (aucun « Yes » à cliquer)

Les agents lancés par Jarvis travaillent sans te solliciter, et sans perdre leurs garde-fous.

| | Comment | Ce qui reste bloqué |
| --- | --- | --- |
| **Claude Code** | `bin/jarvis-claude` : mode `auto` (un classifieur valide les actions sûres), modèle et effort de la tâche | actions jugées risquées, règles `deny` |
| **Codex** | `bin/jarvis-codex` : bac à sable `workspace-write`, `--ask-for-approval never`, réseau autorisé, caches de paquets inscriptibles | tout ce qui sort du worktree, sauf les commandes autorisées par les règles |
| **Règles Codex** (`config/codex/jarvis.rules` → `~/.codex/rules/`) | autorisé : `git add/commit/push` de sa branche, `gh pr create/view/review…`, `pnpm/npm/uv install` | **interdit** : `git push --force`, push sur `main`, `gh pr merge/close`, `git reset/clean` |
| **Confiance des dossiers** | `jarvis task` pré-accepte chaque nouveau worktree (Claude : `~/.claude.json`, Codex : `~/.codex/config.toml`) | — |

Pourquoi Codex demandait sans arrêt : en bac à sable, `.git` est protégé en écriture, y compris le vrai `.git` d'un worktree. Chaque commit sortait donc du bac à sable et déclenchait une demande. Les règles autorisent maintenant d'avance exactement ce dont un agent a besoin, et `jarvis-codex` ouvre aussi en écriture le dépôt git du projet (objets, références, métadonnées du worktree).

Avec `--ask-for-approval never`, Codex refuse aussi les **outils MCP** (Linear) qui demandent une approbation. `jarvis-codex` les approuve d'avance (`default_tools_approval_mode = "approve"`) pour chaque serveur déjà déclaré dans `~/.codex/config.toml`. `jarvis doctor` teste un vrai commit dans le bac à sable ; si Codex ne peut toujours pas committer, `jarvis regler codex.mode complet` le lance sans bac à sable (ses règles « interdit » restent actives).

Un agent que workmux ne suit pas encore (souvent Codex avant la fin de son premier tour) apparaît comme **🌀 actif ?** dans le cockpit et `jarvis etat`. Il compte comme occupé, et `jarvis voir projet:worktree` affiche sa sortie.

## Redémarrages et santé du PC

- **Redémarrage imprévu** (mise à jour Windows, coupure) : le démon mémorise en continu les agents au travail. Au prochain `jarvis start`, seuls ceux-là sont rouverts **avec leur conversation** (`workmux open --continue`), puis le chef repart en sachant ce qui s'est passé. Les agents déjà terminés ne sont pas rouverts.
- **Démarrage automatique** : `jarvis autostart installer` place un petit lanceur invisible dans le dossier Démarrage de Windows. À l'ouverture de session, WSL démarre et Jarvis reprend tout seul. Active aussi « Start Docker Desktop when you sign in » dans Docker Desktop.
- **Santé** : toutes les 5 minutes, le démon vérifie la mémoire, le disque, Docker, la batterie et la présence d'un **redémarrage Windows en attente** (le signe qu'une mise à jour risque de redémarrer le PC pendant la nuit). Tu es prévenu sur Telegram quand un indicateur se dégrade. Jarvis ne modifie jamais ton système lui-même.
- **Dépôt abîmé** par un arrêt brutal (`bad object`, objets vides) : `jarvis reparer-git <projet>`. Le chef peut aussi le lancer.
- Les fenêtres des agents terminés se ferment seules au bout d'une heure : la capacité n'est jamais bloquée par de vieilles fenêtres.
- **Capacité adaptée au PC** : `max_agents` est un plafond. Jarvis le réduit quand la mémoire libre ne permet pas un agent de plus (1,2 Go par agent, 1,5 Go gardés pour le reste), et ne lance rien sur batterie faible, disque presque plein ou processeur saturé. Le cockpit dit pourquoi.
- **Batterie critique** : sous 12 % sans secteur, les agents reçoivent l'ordre de committer leur travail, Jarvis se met en pause et te prévient. La pause se lève quand tu rebranches. Le niveau est relu toutes les deux minutes sur batterie, toutes les dix sur secteur.
- **Chiens de garde** : le démon est relancé s'il plante ; le chef est relancé s'il s'arrête alors qu'il reste du travail (jamais s'il n'avait pas été lancé) ; un agent qui n'affiche plus rien depuis 45 minutes ou travaille depuis 4 heures est signalé au chef ; un lancement interrompu avant le démarrage de l'agent rend son élément au plan. Le cockpit affiche un voyant par service.

## Autonomie : admission, pauses, politique

Le lot 1 de l'autonomie (voir `docs/autonomy/`) ajoute un **point d'admission commun** : tout départ d'agent — plan approuvé, `jarvis task` à la main, reprise après redémarrage, relance du chef — passe sous le même verrou, qui vérifie configuration, pauses, observation, capacité (agents occupés + réservations en attente), opérations lourdes, doublons, jetons, puis le plan. Les **pauses** ont des causes indépendantes (humain, batterie, quota, ressources, incident, maintenance) : la fin d'une cause ne lève jamais les autres. Un agent muet mais vivant est **silencieux**, pas terminé. La **politique de délégation** (`config/politique.toml`) classe chaque action en automatique, déléguée ou à approuver ; dépense et publication sont refusées sans enveloppe ni délégation, et les refus s'empilent dans une file d'exceptions que tu lis groupée. Tout est journalisé (`jarvis audit`). Point de départ pour un portable : `jarvis profil appliquer laptop-conservative`, puis `jarvis diagnostic` pour mesurer avant d'augmenter.

## Sécurité et coûts

- Dépôt **public** : aucun secret ici. Le jeton Telegram reste dans `~/.config/jarvis/settings.toml`.
- Le chef a des règles **deny** dans Claude Code : pas d'écriture dans tes projets ni dans les fichiers de Jarvis, pas de fusion, pas de push, pas de lecture des `.env`, pas d'accès direct à `workmux add` ni à Python.
- Le chef **propose** les changements du catalogue des modèles, avec leur source ; lui seul ne peut pas les appliquer.
- `jarvis livrer` n'envoie que vers **ta** conversation Telegram, et seulement des fichiers qui vivent réellement dans le dossier des livrables. Rien n'est publié ni envoyé à un tiers par l'usine. C'est le chef qui livre, après contrôle et contre-relecture ; un agent qui s'y essaie est refusé. Comme pour les approbations, c'est un garde-fou contre l'erreur, pas une barrière étanche : chef et agents tournent sous ton compte.
- Le tableau de bord web écoute sur `127.0.0.1`, refuse les requêtes qui ne visent pas ce PC, n'affiche aucun secret et n'accepte aucune action. Il ne sert que des fichiers revérifiés à chaque lecture comme de vrais livrables ; un document écrit par un agent se télécharge, il ne s'ouvre jamais comme une page.
- Approuver un plan et modifier les réglages exigent un **terminal interactif** (ou le cockpit, ou Telegram) : un agent ne peut pas s'auto-approuver.
- Telegram n'accepte que **ta** conversation privée appairée ; les groupes sont refusés.
- Les messages tapés au chef attendent en file si une demande de permission est affichée : une touche Entrée ne valide jamais une permission à ta place.
- Commence avec `max_agents = 2` ou `3`. Au-delà, tu atteins les limites des abonnements, et tu dois pouvoir relire tout ce qui sort.

## Défense en observation

`bin/jarvis defense triage <fichier>` analyse uniquement un lot explicitement fourni,
sans collecte ni remédiation. Le moteur déterministe, les deux skills et leurs limites
sont décrits dans [le guide Défense](docs/defense/README.md). Les exemples sont synthétiques ;
ce premier lot ne promet pas une protection opérationnelle.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

## Feuille de route

- [x] Phase 1 : installation, configurations, CLI `jarvis`, protocole Linear
- [x] Phase 2 : chef d'orchestre, plans approuvés, cockpit, démon, Telegram, plan de nuit
- [x] Phase 2.5 : reprise après redémarrage, démarrage automatique, santé du PC, battement du chef, images Telegram
- [x] Phase 3 : l'usine — rôles spécialisés, routeur de modèles, secours, registre des tâches et bilan, studio vidéo et livrables, cockpit par ateliers, tableau de bord web, prévision des jetons, capacité adaptée au PC, chiens de garde
- [x] Autonomie, lot 0–1 et fondations du lot 2 : admission commune, pauses indépendantes, agents silencieux, profils, diagnostic, politique de délégation, budgets, journal d'audit, adaptateurs fournisseurs, file de travaux partagée (`docs/autonomy/`)
- [x] Prompt maître, vague 3 : registre de skills avec confiance, briefs auto-améliorés (canari), SQLite facultatif, bail d'orchestrateur, exécutants (`docs/autonomy/vague-3.md`)
- [x] Prompt maître, vagues 1–2 : plafonds de jetons, coûts, mémoire, bilan quotidien, échecs bornés, secrets par rôle ; évaluation par goldens, backend d'exécution, replay, traces, rollback assisté (`docs/autonomy/vague-*.md`)
- [ ] Autonomie, lots 3–4 : parcours commercial d'un produit en simulation, exploitation, amélioration mesurée des agents, migration vers la station (`docs/autonomy/feuille-de-route.md`)
- [ ] Phase 4 : PR fusionnées par jour et par projet dans le bilan, voix off et sous-titres dans le studio, approbation des plans depuis le tableau de bord web
