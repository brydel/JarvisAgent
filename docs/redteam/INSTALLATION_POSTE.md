# Installation dans le Jarvis habituel du poste

L'intégration combine la branche locale `integration/jetson-live` au commit `b73f618` avec
`reprise/redteam` au commit `8d14c7a`, dans un worktree de préparation distinct.
Elle conserve les commandes et le service multimodaux, le contexte 4 096 déjà configuré et le rôle du chef.
Le seul conflit de fusion concernait le test du catalogue MCP : il conserve les six outils existants
et vérifie aussi `redteam_auditer`.

Validation de la version combinée, avec état, configuration et données de test isolés :

- suite du poste : **758 tests, un ignoré**, réussite en 214,301 s avec l'image Docker réelle ;
- suite du service multimodal : **20 tests réussis** ;
- syntaxe bash, aide générale, aides `redteam` et `noeud demander`, identité des deux modèles
  AGENTS/CLAUDE et intégrité du diff vérifiées ; shellcheck absent.

Après validation, le dossier Jarvis déjà présent dans le PATH reçoit cette intégration par avance rapide
sur `integration/jetson-live`. Aucun changement de lien, réinstallation générale ou redémarrage du démon
n'est nécessaire : chaque invocation CLI charge les modules du dossier habituel.
Les fichiers suivis remplacés sont archivés avant l'opération sous
`~/.local/share/jarvis-sauvegardes/avant-redteam-*`, avec les commits avant/après.
Le contenu des fichiers locaux non suivis est vérifié avant et après installation.

Commandes disponibles :

```bash
jarvis redteam --help
jarvis redteam liste
jarvis noeud demander --help
```

La configuration personnelle, les données existantes, les mandats audio et les autorisations d'outils
restent ceux de l'installation habituelle. L'installation du client ne crée pas de nouveau mandat.
Un audit distant exige toujours un mandat RedTeam propriétaire distinct pour la connexion et le projet
choisis. Le mandat et les rapports de validation déjà produits restent dans leur état de laboratoire isolé.

Le [parcours distant sur la Jetson](VALIDATION_JETSON.md) conserve sa configuration de cible synthétique fixe.
Cette installation sur le poste ne redéploie pas le service Jetson et n'élargit pas cette cible.
