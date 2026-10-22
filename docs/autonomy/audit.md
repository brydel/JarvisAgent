# Audit priorisé (pistes du mandat, vérifiées dans le code réel)

Méthode : lecture de `plans.py`, `taches.py`, `agents.py`, `daemon.py`, `poste.py`, `store.py`, `cli.py`,
`bin/jarvis`, puis tests. « Constaté » = lu dans le code et reproduit par un test ; « non reproduit » =
hypothèse raisonnable non confirmée.

| # | Piste | Constat avant | Après ce lot | Statut |
| --- | --- | --- | --- | --- |
| 1 | Agent silencieux déclaré terminé | Constaté : une fenêtre non suivie par workmux et sans activité depuis 20 min passait `idle` → fiche `terminee`, place libérée, même si Claude/Codex tournait encore | `agents.status_all` vérifie le programme du volet via `/proc` : vivant → `silent` (occupé, fiche `silencieuse`) ; shell seul → `idle` (terminé). `menage_check` ne ferme que `done`/`idle` | implémenté/testé |
| 2 | Reprise après redémarrage hors admission | Constaté : `poste.reprendre` rouvrait toute la vague sans vérifier pause, capacité ni jetons | Chaque reprise passe par `admission.demander(origine="reprise")` ; les refusés restent dans `reprise.json` avec leur raison, le chef est informé | implémenté/testé |
| 3 | Pauses concurrentes ambiguës | Constaté : un seul fichier `pause` ; la batterie posait une pause « jarvis » ou « humain » selon un drapeau, le quota une autre ; une levée pouvait effacer la pause de l'humain | `pauses.py` : six causes indépendantes ; migration de l'ancien fichier | implémenté/testé |
| 4 | Course entre deux lancements | Constaté : la capacité était comptée dans `authorize_launch` (plan) avec « lancements récents < 5 min » ; rien pour `jarvis task` manuel ; deux `jarvis task` simultanés hors plan pouvaient dépasser `max_agents` | Verrou unique `admission`, réservations comptées jusqu'à l'apparition de l'agent, expiration à 15 min avec libération de l'élément de plan | implémenté/testé (6 fils, plafond 2 → exactement 2 admis) |
| 5 | Lancement partiel → doublon ou tâche perdue | Constaté partiellement : un échec entre `authorize_launch` et `tache-enregistrer` laissait l'élément de plan « lancé » pour toujours (seul le ledger relâchait, et il n'existait pas encore) | La réservation porte le plan : expirée sans fiche, elle rend l'élément ; même issue redemandée avant expiration → refus `doublon` | implémenté/testé |
| 6 | Opérations lourdes non comptées | Constaté : rien ne distinguait un agent qui édite d'un agent qui compile ou rend une vidéo | Classes de charge, plafond `operations_lourdes_max`, `jarvis lourd exec` pour les agents, tâches de classe lourde en attente à l'admission | implémenté/testé ; **non imposable** aux commandes des agents (voir `securite.md`) |
| 7 | Quotas périmés | Constaté : `usage.summary` ne regardait pas l'âge de la mesure | `perime` + `age_s` ; une mesure > 6 h vaut « alerte » (prudence) | implémenté/testé |
| 8 | Configuration invalide | Constaté : `max_agents = -1` ou `plans.validation = "oui"` étaient acceptés silencieusement | `config.valider` ; admission fermée tant que la configuration est invalide ; cockpit/web l'affichent | implémenté/testé |
| 9 | Relances en boucle | Constaté : relance du chef bornée (3/h) mais compteur propre au chef | Compteur générique `admission.relance_autorisee`, journalisé ; aucune relance en pause | implémenté/testé |
| 10 | Observation indisponible | Déjà « fail closed » dans le démon ; `cmd_plan_verifier` refusait aussi | Idem à l'admission (`code observation`) ; état « illisible » affiché | implémenté/testé |
| 11 | Collisions projets/worktrees | Non reproduit ; l'existant résout le projet par chemin d'abord | Refus `doublon` si le worktree est déjà visible ou réservé | implémenté/testé partiellement |
| 12 | Coût des rafraîchissements du cockpit | Non mesuré ici (pas de workmux) ; `report.snapshot` appelle `workmux status` à chaque tour, le web met en cache 2 s | Inchangé ; mesure à faire sur ton PC (`jarvis diagnostic` pendant le cockpit) | à mesurer |
| 13 | Autorisation ≠ terminal/variable d'environnement | Constaté : `jarvis task` hors plan repose sur « terminal interactif » et `JARVIS_ROLE` | Inchangé mais documenté comme garde-fou applicatif ; les nouvelles commandes humaines suivent la même règle, journalisées | limite documentée |
| 14 | Dépense/publication | Rien n'existait : la règle vivait dans le prompt du chef | Politique versionnée, budgets, exceptions, refus testés | implémenté/testé |
| 15 | Secrets | Déjà : `.env` interdits au chef, `reglage-lire` masque le jeton | Diagnostic expurgé, profil ne touche pas aux secrets ; gestion par tâche de secrets minimaux : **conçu** | partiel |

Pistes **non traitées** dans ce lot (volontairement) : cgroups/limites de processus (bloqué sans mesure
sur WSL, voir `securite.md`), classification fine des échecs d'agent (conçu, `feuille-de-route.md`),
format des fenêtres de quota autre que 5 h/semaine côté Claude (le CLI ne publie que celles-là ; Codex
donne `window_minutes` déjà exploité).
