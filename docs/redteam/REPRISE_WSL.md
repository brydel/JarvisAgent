# Reprise de Jarvis RedTeam Node sous Ubuntu WSL

Ce fichier transmet le contexte d'une session Codex cloud à une nouvelle session locale. La branche de transfert
contient un premier incrément SAST, basé sur `feat/board-dessin` au commit `5fd52b8`. L'utilisateur demande de
continuer sur cette famille de code, sans reprendre d'une branche Board plus ancienne ni importer automatiquement
`feat/jetson-extension`. Aucune refonte du Board ou du design n'est demandée.

## Commencer par le dépôt réel

Lis `AGENTS.md`, `docs/redteam/README.md` et `docs/redteam/ARCHITECTURE.md`. Vérifie la branche, l'historique récent,
les worktrees et toutes les modifications locales. Préserve le travail existant ; aucun reset/clean destructif,
stash forcé ou remplacement aveugle de fichiers. Si `feat/board-dessin` a avancé, intègre ces changements dans un
worktree distinct après comparaison. Ne reviens pas artificiellement à l'ancienne révision pour éviter un conflit.

Les changements de cette branche sont déjà intégrés : n'applique pas une seconde fois un patch de l'ancienne
archive. La branche de transfert isole la livraison ; elle n'est pas une fusion dans `main` ni dans la branche
source de l'utilisateur.

## Ce qui a été validé dans le cloud

- Bibliothèque standard côté Jarvis ; client et CLI `jarvis redteam` dans `lib/jarvis/redteam.py`.
- Une règle Semgrep Python pour `subprocess` avec `shell=True`, sur des fixtures synthétiques.
- Parcours réel local : passerelle Jarvis → mandat → MCP stdio → Docker sans réseau → rapport → communauté.
  C'était un transport MCP par processus local, pas une connexion SSH à une Jetson.
- Collecte bornée, politique côté propriétaire, preuves sources/règles hachées et publiées atomiquement,
  checkpoints SQLite PLAN/EXECUTE/OBSERVE/VERIFY/REFLECT/DELEGATE/REPORT et reprise idempotente.
- Arrêt réel d'un processus après EXECUTE puis reprise dans un autre processus : rapport terminé sans refaire
  le scan enregistré. Le scan Docker de cet essai durait environ 9,454 s sur x86_64.
- Suite complète : 744 tests, dont 102 ignorés, réussie. Tests du service : 15 réussis. Tests RedTeam ciblés :
  14 réussis, avec Semgrep et Docker réels. QA indépendante effectuée ; shellcheck n'était pas installé.

Ces chiffres sont l'historique cloud, pas les résultats de cette machine. L'image Docker, le venv et les chemins
`/workspace/...` du cloud ne sont pas transférés par Git. Les prérequis doivent être vérifiés ou reconstruits ici.

## Prochaine priorité : vraie Jetson et chaîne distante

1. Réutilise les accès SSH réellement configurés sur l'ASUS, sans afficher de clé privée ni de secret. La clé Jarvis
   à commande forcée peut ne permettre que `mcp`, `depot` et `sante` ; elle n'accorde pas un shell administratif.
2. Commence en lecture seule : modèle Jetson exact, architecture, RAM/mémoire disponible, GPU, L4T/JetPack, CUDA,
   disque, Docker/ARM64, Ollama et modèles réellement présents. Le cloud n'a pu vérifier aucun de ces éléments.
3. Relance les tests localement avec un état de laboratoire distinct du Jarvis actif. Les variables
   `JARVIS_REDTEAM_TEST_SEMGREP` et `JARVIS_REDTEAM_TEST_IMAGE` activent les intégrations réellement installées.
4. Prépare puis teste le moteur sur la Jetson en préservant ses fichiers et les fonctions audio existantes.
   Le mandat de sécurité est distinct de celui de l'audio. Démontrer un appel depuis Jarvis via SSH/MCP avec
   retour du rapport et preuves avant de déclarer le déploiement opérationnel.
5. Vérifie une vraie inférence Ollama et compare Gemma3:4b/Qwen3:4b seulement après mesures matérielles et contrôle
   des modèles/licences/digests. Le banc initial est fourni ; son exécution et les mesures GPU restent à faire.

## Limites à garder explicites

Un résultat Semgrep n'est pas une exploitabilité reproduite ni un impact confirmé. La vérification actuelle porte
sur l'exécution de l'outil. Une demande de revue est publiée et relisible, mais aucun worker indépendant actif,
budget LLM débité ou heartbeat permanent n'a été livré. L'adaptateur Ollama et son banc sont préparés, sans
inférence réelle validée. Trivy/Gitleaks/ZAP/Nuclei, laboratoire IDOR et confirmation d'impact restent au backlog.

Un arrêt avant le commit EXECUTE peut refaire le scan. Un SIGKILL du parent peut empêcher son `finally` : la
récupération des conteneurs et temporaires orphelins reste à compléter. L'état de preuves est privé ; rétention,
archivage et chiffrement sont à administrer. Aucun entraînement, test de production ou déploiement matériel
n'a été réalisé dans le cloud. Ne lance pas d'entraînement coûteux sans validation et ne teste aucune cible
hors du périmètre explicitement autorisé. Aucun droit de fusion automatique n'est accordé.

## Consigne à donner au nouveau Codex

> Lis AGENTS.md puis docs/redteam/REPRISE_WSL.md, README.md et ARCHITECTURE.md dans le même dossier. Vérifie
> d'abord l'état Git et préserve mes modifications. Reprends Jarvis RedTeam Node sur la base demandée
> feat/board-dessin ; commence par reconnaître les vrais accès SSH et la Jetson en lecture seule, puis poursuis
> l'intégration et les tests autorisés. Distingue les validations cloud de tes nouvelles preuves locales.

Présente brièvement branche/commit, modifications à préserver et accès vérifiés, puis continue les opérations
non destructives nécessaires. Les décisions techniques courantes n'exigent pas une nouvelle confirmation à
chaque étape. Termine avec fichiers, décisions, commandes/résultats, fonctions opérationnelles, limites et backlog.
