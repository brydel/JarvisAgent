# JarvisAgent — règles pour les agents qui travaillent sur ce dépôt

## Projet

JarvisAgent est un poste de pilotage d'agents IA de code : scripts bash pour Ubuntu/WSL, configurations tmux et workmux, et modèles de protocole Linear. Voir `README.md`.

- Langue : tout le texte destiné à l'utilisateur (messages, README, commentaires) est en **français**.
- Shell : bash, `set -euo pipefail`, scripts **idempotents** (relançables sans effet de bord).
- Vérifier avant « TERMINÉ » :
  - `bash -n install.sh bin/jarvis`
  - `shellcheck install.sh bin/jarvis` (si installé)
  - `bin/jarvis help` s'affiche sans erreur

## Règles

- Ce dépôt est public : aucun secret, jeton ou adresse personnelle.
- `templates/AGENTS.md` et `templates/CLAUDE.md` doivent rester identiques.
- Ne jamais écraser un fichier de l'utilisateur sans le sauvegarder d'abord (voir `link()` dans `install.sh`).

## Protocole Linear

1. Lis en entier l'issue Linear citée dans ton prompt avant de coder.
2. Au démarrage, passe-la à « In Progress » et commente `🤖 [agent] Démarré — plan :` + 3 à 5 étapes.
3. Bloqué : commente `❓ QUESTION :` avec les options et ta recommandation, puis attends.
4. À la fin : commente `✅ TERMINÉ` (résumé, fichiers, vérifications, branche), ouvre une PR avec `gh pr create`, passe l'issue à « In Review ».
5. Ne fusionne jamais dans `main`.
