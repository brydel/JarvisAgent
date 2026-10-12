# Règles des agents

Ce fichier est lu par Codex (`AGENTS.md`) et par Claude Code (`CLAUDE.md`). Les deux fichiers ont le même contenu.

## Projet

<!-- À adapter : une ou deux phrases sur le projet, la stack, les commandes utiles. -->
- Nom : NOM_DU_PROJET
- Stack : à compléter
- Installer : `pnpm install`
- Vérifier avant « TERMINÉ » : `pnpm lint && pnpm typecheck && pnpm test`

## Protocole Linear (obligatoire)

1. Ta tâche est l'issue Linear citée dans ton prompt (ex. BIS-82). Lis-la en entier avec l'outil Linear avant d'écrire du code.
2. **Au démarrage** : passe l'issue à « In Progress » et commente :
   `🤖 [claude|codex] Démarré — plan :` suivi de 3 à 5 étapes.
3. **Bloqué ou décision à prendre** : commente `❓ QUESTION :` avec les options A/B et ce que tu recommandes, puis **arrête-toi et attends** une réponse.
4. **À la fin** : commente `✅ TERMINÉ` avec :
   - un résumé en 2 ou 3 phrases ;
   - les fichiers modifiés ;
   - les commandes de vérification lancées et leur résultat ;
   - le nom de la branche.
   Puis ouvre une PR avec `gh pr create` (titre préfixé par l'ID de l'issue) et passe l'issue à « In Review ».

## Interdits

- Ne jamais fusionner dans `main`, ne jamais forcer un push.
- Ne jamais lire, afficher, copier ou modifier des secrets (`.env`, clés API, jetons).
- Ne toucher qu'aux fichiers nécessaires à **ton** issue. Un autre agent travaille peut-être à côté.
- Ne pas ajouter de dépendance sans l'expliquer dans le commentaire final.

## Qualité

- Lance les vérifications de la section « Projet » avant `✅ TERMINÉ`. Si elles échouent, corrige ou explique pourquoi.
- Petits commits clairs, préfixés par l'ID de l'issue : `BIS-82: ajoute la vérification 2FA`.
- Pas de code mort ni de `console.log` oubliés.
