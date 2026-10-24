# Reprise WSL : préparer une intégration sans remplacer l'installation

Ce guide prépare une revue locale le matin. Il ne garantit pas l'absence de conflits
sur un PC qui n'a pas été inspecté et n'autorise ni installation, ni bascule, ni
redémarrage de service. Le lot Défense est un triage ponctuel, sans surveillance
continue. Garder les constatations et sauvegardes dans un emplacement privé hors Git.

## 1. Identifier ce qui fonctionne réellement

Dans WSL, examiner sans lancer Jarvis :

```bash
type -a jarvis
command -v jarvis
```

Résoudre le chemin de l'exécutable et ses éventuels liens ou wrappers, puis retrouver
le dépôt réellement utilisé. Depuis ce dépôt, relever en privé :

```bash
git branch --show-current
git rev-parse HEAD
git status --short --untracked-files=all
git worktree list
git diff --stat
git diff --cached --stat
```

Une branche détachée, des fichiers modifiés ou une autre installation doivent être
explicités avant de continuer. Noter les fonctions à conserver : commandes, Board,
agents, transports, skills et intégrations effectivement utilisés. Identifier leurs
points d'entrée et réglages sans publier de configuration ni appeler de service.
Ne pas supposer que le checkout installé correspond à la base distante de cette PR.

## 2. Sauvegarder avant toute intégration

Choisir un **nouveau dossier privé hors de tous les dépôts**, avec accès restreint.
Y enregistrer le SHA installé, la branche et la résolution de la commande. Conserver :

- Un bundle Git des références et de HEAD (`git bundle create … --all HEAD`) et
  vérifier sa lisibilité (`git bundle verify …`).
- Les modifications suivies, séparément : `git diff --binary` et
  `git diff --cached --binary`, redirigés vers deux fichiers privés distincts.
- Une copie de travail complète conservant les fichiers non suivis **et ignorés**,
  liens et permissions, dans une destination neuve ; ne pas se limiter aux patches
  ou au bundle. Inclure les cibles externes nécessaires des liens après inspection.
- Les répertoires réels de configuration, données, états, secrets et personnalisations
  identifiés localement, hors dépôt. Ne pas afficher les secrets ni les ajouter à Git.

Pour les bases actives, utiliser une sauvegarde cohérente propre au moteur, pas une
copie brute pendant les écritures. Si cela requiert un arrêt ou un verrouillage,
obtenir l'accord avant ; en attendant, ne pas poursuivre la bascule. Vérifier les
archives, leurs permissions et une restauration dans un autre dossier privé neuf.
Une sauvegarde non vérifiée ne suffit pas. Ne pas supprimer ni déplacer l'original.

## 3. Construire un candidat dans un worktree isolé

Après sauvegarde, récupérer uniquement les références nécessaires, sans changer le
checkout installé. Comparer le SHA de la PR au SHA publié et vérifier sa base :

```bash
git fetch origin integration/redteam-live feat/defense-observation-lot1
git ls-remote --heads origin integration/redteam-live feat/defense-observation-lot1
```

Noter les SHA exacts. Choisir un nom de branche locale et un chemin de worktree neufs.
Depuis le dépôt, utiliser `git worktree add -b NOM_NOUVEAU CHEMIN_NOUVEAU SHA_INSTALLE`.
Les trois valeurs sont à remplacer après inspection ; ne pas réutiliser un dossier.
Dans ce worktree seulement, examiner `git log --left-right --oneline
SHA_INSTALLE...SHA_DEFENSE` et `git diff --stat SHA_INSTALLE SHA_DEFENSE`.

Préparer l'intégration avec `git merge --no-commit --no-ff SHA_DEFENSE` dans ce seul
worktree de préparation. Une intégration en conflit s'arrête pour revue, sans choix
automatique d'un côté. Vérifier la présence du nettoyage PR12 et ne pas réintroduire
ses fichiers privés, même si l'installation ancienne les contient. Conserver ces
preuves uniquement dans la sauvegarde privée.

Les patches locaux ne sont pas transportés par le worktree : les examiner un par un,
tester leur application avec `git apply --check` et conserver leurs fonctionnalités
ou justifier chaque remplacement. Les fichiers non suivis/ignorés restent dans la
sauvegarde et le checkout original ; réintroduire uniquement ceux nécessaires dans
le candidat privé, sans les publier. L'autre lot sera évalué après réception de sa
branche et de son SHA exacts, dans ce même cadre isolé, jamais par fusion aveugle.

## 4. Tester avant de proposer une bascule

Utiliser des répertoires temporaires de configuration/état/données et des fixtures
synthétiques, sans partager les bases actives, clés, sessions ou services du poste.
Exécuter les commandes depuis le candidat avec `bin/jarvis`, pas le raccourci installé :

```bash
bash -n install.sh bin/jarvis
bin/jarvis help
python3 -m unittest discover -s tests -p test_defense.py -v
python3 -m unittest discover -s tests -v
bin/jarvis defense triage docs/defense/exemples/auth-synthetique.jsonl
git diff --check
```

Vérifier les prérequis avant les tests ; une dépendance manquante ne donne pas accord
pour l'installer. Exécuter ShellCheck s'il est disponible. Comparer à la version
installée dans un environnement de test équivalent et isolé ; distinguer échecs
préexistants, tests ignorés et régressions. Vérifier notamment que les fonctions
recensées à l'étape 1 restent présentes et couvertes, puis planifier avec l'humain
les essais réels qui exigent un accès externe. Une CI verte ne prouve pas cette
compatibilité. Relire le diff complet et garder un candidat identifié par commit.

## 5. Décision humaine et retour arrière

Présenter le SHA installé, le SHA candidat, les conflits résolus, les fonctions
préservées, les tests et leurs limites avant de demander l'accord de bascule.
Ne lancer ni installateur, ni démon, ni activation de skill automatiquement.

Préparer le retour vers l'ancien point d'entrée et son SHA sans supprimer le nouveau
worktree ni les nouvelles données. Conserver les sauvegardes et les deux versions.
Si une migration d'état est envisagée, elle nécessite un plan séparé : préserver
l'état après bascule, restaurer la copie antérieure vers un emplacement distinct et
vérifier la compatibilité avant de reconnecter l'ancien code. Ne pas écraser une
base active avec une sauvegarde ancienne. Les changements de raccourci, processus
et service nécessitent eux aussi un accord explicite.
