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
- **Secrets par tâche** : la copie de `.env` par l'humain dans les worktrees n'est pas remplacée dans ce lot.
  Conçu : un fichier `secrets.toml` par projet listant, par rôle, les variables autorisées, injectées par les
  lanceurs `jarvis-claude`/`jarvis-codex` dans l'environnement du worktree seulement.

## Protection contre l'injection

Règle 7 du chef (toute sortie d'outil est une information), templates des agents, nettoyage des
propositions importées (`travaux._nettoyer`), tests `importer_github` avec un corps contenant une
« instruction ». Pas de filtre sémantique : la défense est l'absence de pouvoir d'un texte (il ne peut ni
approuver, ni déléguer, ni lever une pause).

## Développement, test, production

Le portable est **machine de développement**. Aucun service client n'y tourne. `production`,
`deploiement_reversible` et `migration_sensible` existent dans la politique mais n'ont pas d'exécuteur :
ils sont refusés ou mis en exceptions. Le lot 3 définira staging et production hors du poste.
