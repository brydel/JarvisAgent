# Sécurité, droits, isolation : ce qui tient, ce qui ne tient pas

## Ce que ce lot garantit (garde-fous applicatifs)

- Approbations, délégations, budgets, profils, pose et levée de pause (sauf poser `incident`), `--forcer` :
  réservés à un **terminal humain** (ou cockpit/Telegram) par la même garde `_human_only` ; refusés avec le
  code 4 au chef (`JARVIS_ROLE=chef`), aux agents (`JARVIS_METIER`) et à tout appel sans terminal.
- La copie personnelle de la politique ne peut que durcir ; une action inconnue est de niveau 3.
- Toute décision est journalisée avec chaîne d'empreintes ; une altération se détecte.
- Les réglages hors bornes ferment l'admission au lieu de l'ouvrir.
- Le contenu externe (issues GitHub importées, propositions du dot, pages web) est traité comme une
  **donnée** : borné, nettoyé, jamais exécuté ; une proposition n'autorise rien.
- Aucun secret dans le diagnostic (expurgé), les profils (ne touchent pas `[telegram]`), le journal
  (n'écrit que des identifiants et des raisons), Telegram (livrables contrôlés, chat appairé).

## Ce que ce lot ne garantit pas — à dire clairement

- **Même utilisateur Linux** : chef, agents, démon, fichiers d'état et de configuration appartiennent au
  même compte. Un agent qui exécute `python3` ou édite `~/.local/state/jarvis/*.json` peut contourner tout
  ce qui précède. Les règles `deny` de Claude Code et le bac à sable Codex réduisent le risque, ne
  l'annulent pas. Aucun contrôle ici ne doit être appelé « indépendant ».
- **Plafonds de processus non imposés** : `jarvis diagnostic` indique si un cgroup v2 délégué inscriptible
  et `systemd --user` existent. Dans le conteneur de test : non. Sous WSL2 par défaut, `systemd` peut être
  activé mais la délégation de cgroup à l'utilisateur n'est pas garantie et **n'a pas été mesurée sur ton PC**.
  Décision : ne pas prétendre imposer `MemoryMax`/`CPUQuota` ; les opérations lourdes sont une consigne
  (`jarvis lourd`) + `nice`. Activation H24 non supervisée d'agents qui compilent : **refusée tant que ce
  n'est pas imposable** (voir `exploitation.md`, « campagne H24 »).
- **Pas de VM jetable ni de service privilégié** : toute opération qui demanderait `sudo` reste de niveau 3
  (`acces_privilegie`) et n'a pas d'exécuteur ici. Un shell root arbitraire n'est pas une liste d'opérations.
- **Arrêt par le propriétaire** : `jarvis pause poser humain` + `tmux kill-session -t jarvis` (ou fermer la
  fenêtre du démon) arrêtent tout ; aucun mécanisme ne relance le chef en pause (`chef_check` vérifie
  `store.paused()`), et `_chef_vu` empêche une relance après un redémarrage non suivi de `jarvis chef`.
  Rien n'est conçu pour résister à un arrêt volontaire.
- **Secrets par tâche** (vague 1, `vague-1.md`) : `~/.config/jarvis/secrets/<projet>.toml` liste par rôle les noms
  autorisés, `<projet>.env` (600) les valeurs ; les lanceurs n'injectent que ceux du rôle de la tâche. Un agent voit
  ce qu'il reçoit : c'est une réduction de ce qui peut fuiter, pas une isolation. Un `.env` copié à la main dans un
  worktree n'est pas empêché.
- **Vague 2** (`vague-2.md`) : `jarvis execution lancer` exige une réservation d'admission active ; `jarvis eval
  lancer`, `jarvis proxy config` et `jarvis rollback executer` sont réservés à l'humain (refus si `JARVIS_ROLE` ou
  `JARVIS_METIER`, et interdits au chef). Un rollback n'a lieu qu'après ton clic Telegram ou ta commande, sur une
  branche inchangée et propre. La configuration LiteLLM ne contient que des références `os.environ/…`. Les traces
  ne quittent le poste que si `observabilite.otlp_endpoint` est réglé ; elles ne contiennent ni consignes ni code.
  Les goldens (`tests/goldens/`) sont protégés : ni le chef ni un agent ne les modifie pour faire passer un brief.

- **Vague 3** (`vague-3.md`) : une skill n'est lue par les agents qu'après ton approbation (quarantaine,
  empreinte vérifiée avant activation, aucun fichier non géré écrasé) ; l'audit horaire signale une skill
  modifiée après épinglage. Un brief de rôle ne change qu'avec ton accord : canari limité, retour automatique au
  stable en cas de régression, promotion par toi seul ; l'optimiseur ne voit pas les cas protégés et ne peut pas
  modifier les goldens (empreinte contrôlée). `jarvis skill approuver|epingler`, `jarvis role
  approuver|promouvoir`, `jarvis stockage migrer|revenir` et `jarvis executant declarer` sont réservés à l'humain.
  Le chef n'a pas le droit d'écrire (Edit/Write) dans les skills, la quarantaine, les briefs candidats, les
  rapports d'optimisation ni dans `~/.claude/skills` et `~/.agents/skills` ; c'est une règle d'outils, pas une
  isolation (son Bash n'est pas un bac à sable), d'où les empreintes revérifiées à chaque usage.

## Protection contre l'injection

Règle 7 du chef (toute sortie d'outil est une information), templates des agents, nettoyage des
propositions importées (`travaux._nettoyer`), tests `importer_github` avec un corps contenant une
« instruction ». Pas de filtre sémantique : la défense est l'absence de pouvoir d'un texte (il ne peut ni
approuver, ni déléguer, ni lever une pause).

## Développement, test, production

Le portable est **machine de développement**. Aucun service client n'y tourne. `production`,
`deploiement_reversible` et `migration_sensible` existent dans la politique mais n'ont pas d'exécuteur :
ils sont refusés ou mis en exceptions. Le lot 3 définira staging et production hors du poste.
