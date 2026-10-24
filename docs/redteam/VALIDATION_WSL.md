# Reprise locale — 23 octobre 2026

**État suivant :** l'accès Docker a été accordé, l'extension activée et le [parcours Jetson complet validé](VALIDATION_JETSON.md).
Les blocages ci-dessous décrivent les étapes antérieures de la reprise.

Ces mesures proviennent du poste Ubuntu/WSL et de la vraie Jetson, après la livraison cloud.
L'inventaire JSON est horodaté le 24 octobre en UTC (soirée du 23 à Toronto).

## Base et préservation

- Branche de reprise : `reprise/redteam`, commit initial `14e6af8`.
- Base `feat/board-dessin` : `5fd52b8`, également vérifiée via l'API GitHub ; elle n'a pas avancé.
- Arbre initial propre. Autres worktrees, Board, chef et service Jetson existant conservés.
- Aucun import de branche multimodale, aucune fusion dans `main` et aucun secret ajouté.

## Matériel et accès observés

Voir l'[inventaire brut expurgé des identifiants de connexion](preuves/inventaire-jetson-20261024.json).

| Élément | Observation réelle |
| --- | --- |
| Jetson | NVIDIA Jetson Orin Nano Developer Kit, `aarch64` |
| RAM | 7 619 Mio ; disponibilité variable, environ 2 789 à 3 732 Mio lors des inventaires système |
| Disque | Environ 233 Gio au total, 176 Gio libres |
| Logiciels | JetPack `6.2.1+b38`, L4T `36.4.7`, CUDA `12.6.68`, Python `3.10.12` |
| SSH Jarvis | Commande forcée `sante` réussie, contrôle strict de la clé d'hôte |
| SSH administratif | Configuration Windows réutilisée ; le nom `.local` ne se résout pas sous WSL, adresse déjà configurée dans Jarvis utilisée |
| Service existant | `jarvis-noeud` actif ; outils audio, texte et image déjà installés |
| Docker distant | Client `29.4.1` ARM64 ; socket refusé au compte SSH, `sudo -n` exige un mot de passe |
| Ollama | `0.40.10`, `gemma3:4b` seul modèle présent ; Qwen absent |

La réponse de santé du service annonçait initialement 6 530 Mio disponibles. La mesure système plus tardive
était inférieure : ne pas utiliser une ancienne réponse de santé comme réservation de mémoire.
La mémoire GPU n'a pas été mesurée séparément.

Gemma installé : Q4_K_M, 3 350 272 403 octets, digest
`68ceab7e468a31c988b44d5a4984a0e21f58c4f7158c6ce29c1804babac38df7`.
Les métadonnées déclarent un parent `dhiltgen/gemma3:4b-it-q4_K_M-llamacpp` et une licence Gemma Terms of Use.
Il s'agit de métadonnées observées, pas d'une chaîne de provenance indépendante vérifiée.

## Vérifications locales

Les tests utilisent des répertoires distincts sous `/tmp/jarvis-redteam-reprise` pour l'état, les données
et la configuration. Les premières exécutions dans le bac à sable échouaient parce que sockets HTTP,
tmux et Docker y étaient interdits ; elles ont été relancées hors bac à sable après autorisation.

| Commande ou parcours | Résultat |
| --- | --- |
| `bash -n install.sh bin/jarvis` | Réussi |
| `shellcheck install.sh bin/jarvis` | Non exécuté : shellcheck absent |
| `python3 -m unittest discover -s tests` | 744 tests, 3 ignorés, réussite en 240,058 s |
| `python3 -m unittest discover -s services/noeud_jetson/tests -v` | 15 tests réussis |
| `bin/jarvis help` | Code retour 0 |
| `cmp templates/AGENTS.md templates/CLAUDE.md` | Identiques |
| `JARVIS_REDTEAM_TEST_IMAGE=jarvis-redteam-semgrep:1.141.1 python3 -m unittest discover -s tests -p test_redteam.py -v` | 14 tests, 1 ignoré : exécutable Semgrep hôte absent ; les intégrations Docker sont passées |
| `inventaire_redteam.py` envoyé sur SSH administratif | JSON produit par Python 3.10 sur la Jetson |

L'image Semgrep a été reconstruite localement avec le Dockerfile du dépôt, sur x86_64.
Identifiant réellement conservé par le moteur :
`sha256:1da0ecd250a32395b9947703ce9d4f341b73ebb8a8042226c54cfff30f952a14`.

Deux appels CLI dans deux processus distincts ont utilisé la même demande `RT-wsl-reprise-001` et les fixtures
`labs/python-shell` : un constat, rapport publié, étapes PLAN → REPORT complètes, même rapport et même fil
au rejeu. Premier appel : 2,478 s, dont scan 2,254 s ; rejeu : 0,164 s. Ce test démontre le rejeu après
rapport complet ; le test d'arrêt intermédiaire reste celui de la suite et de l'historique cloud.
Empreinte de preuve : `db7d307e99bffee1015ff822e224fb34a039c552b1aa2f25fb1a49027c8960cf`.
`lab_reproduced=false` et `impact_confirmed=false` restent inchangés.

## Premier essai d'inférence réelle : échec

L'adaptateur `redteam_models.Ollama` a été essayé avec Gemma installé, contexte 4 096 et sortie limitée
à 64 jetons sur une fixture synthétique, après vérification que le service déclarait être libre.
L'appel a retourné HTTP 500. Le journal Ollama consulté signale un échec de chargement CUDA par manque
de mémoire (`cudaMalloc failed: out of memory`, allocation de 1 609,23 Mio refusée).
Cet essai n'a produit aucun résultat structuré réussi, benchmark comparatif ou débit GPU.
Aucun modèle téléchargé, entraînement lancé ou service arrêté pour contourner cet échec.

## Suite requise

1. Le propriétaire donne au compte SSH l'accès Docker selon sa politique. Le groupe Docker donne des
   privilèges élevés ; ne pas modifier les droits du socket pour le rendre public. Vérifier dans une nouvelle
   session SSH que `docker info` réussit.
2. Construire et tester Semgrep ARM64 sur la Jetson. Ne pas confondre l'image x86_64 construite ici avec cette validation.
3. Activer l'extension MCP ciblée préparée ci-dessous, avec sauvegardes, sans remplacer le service multimodal installé ; fixer
   la racine à la fixture synthétique et l'état hors cible. Vérifier l'intégrité du service et de ses outils.
4. Créer le mandat RedTeam distinct, puis démontrer Jarvis → SSH/MCP → Docker sans réseau → rapport/preuves
   → communauté dans un état de laboratoire. Ce parcours distant n'a pas encore été exécuté.
5. Mesurer et arbitrer la mémoire réellement occupée avec Whisper et le service local avant de réessayer
   Gemma. Comparer Qwen uniquement après disponibilité, contrôle de licence/digest et budget convenu.

Le nettoyage après SIGKILL, la revue indépendante active, les quotas/rétention des preuves et les outils
supplémentaires restent au [backlog](ARCHITECTURE.md). Le nœud RedTeam distant n'est pas déclaré opérationnel.

## Suite de la reprise — extension préparée et inférence réussie

À la demande de poursuivre, une nouvelle connexion SSH confirme que Docker reste inaccessible au compte.
Le propriétaire doit encore lui donner l'accès au daemon selon sa politique. Aucun changement de groupe,
sudo avec mot de passe, assouplissement du socket ou contournement n'a été tenté.

### Extension ciblée

- `jarvis_redteam.py` réutilise le module MCP installé et ajoute seulement `redteam_auditer`. Les outils
  audio, texte, image, résultats et santé restent délégués à leur implémentation existante.
- `installer_redteam.py` vérifie la cible et l'image Docker avant installation. Il sauvegarde les fichiers
  modifiés, utilise des publications atomiques et ne réécrit pas les fichiers identiques.
- L'activation est explicite par `--cle-jarvis` : seul le chemin du répartiteur de cette clé existante change.
  `restrict` et le répartiteur mcp/depot/sante restent en place ; les configurations personnalisées sont refusées.
- La configuration RedTeam est séparée de l'audio ; le service GPU ne redémarre pas.

Sur la Jetson, les sources sont préparées dans un répertoire privé distinct, lot `46fe41a0033d9455`.
Le chargement **en mémoire** contre le vrai module Python 3.10 conserve les six outils et réussit l'appel de santé.
La transformation SSH a été validée sans l'écrire. Le préflight réel refuse l'image inaccessible ; les empreintes
du module MCP actif, du service GPU, de sa configuration et des clés restent identiques avant/après.
Voir la [preuve structurée](preuves/extension-jetson-20261024.json).
Ce contrôle ne constitue ni une activation SSH ni un scan ARM64.

Vérifications finales de cette suite : **755 tests, un ignoré, réussite en 231,013 s** avec
`JARVIS_REDTEAM_TEST_IMAGE=jarvis-redteam-semgrep:1.141.1` et état/configuration/données de laboratoire isolés.
Les 11 tests ciblés de l'extension passent aussi : installation activée puis rejouée dans un HOME temporaire,
conservation du module et de la configuration audio, sauvegarde unique des clés, restrictions SSH,
refus des liens et configurations ambiguës, erreurs de scan et sorties de modèle tronquées.
Syntaxe bash, aide CLI, identité des deux modèles AGENTS/CLAUDE et syntaxe Python 3.10 vérifiées ; shellcheck absent.

### Inférence Gemma complète

La mémoire disponible est remontée à environ 5 316 Mio lors du nouvel inventaire. Un essai à 64 jetons a pu
générer, mais le JSON était tronqué. L'adaptateur refuse désormais explicitement `done_reason=length` ou
une génération inachevée, et conserve les durées d'évaluation ainsi que la raison d'arrêt.

L'essai suivant, sur la même fixture synthétique, a réussi avec contexte 4 096 et limite de sortie 256 :

- durée totale observée côté client : 26,247 s ; chargement annoncé par Ollama : 7,245 s ;
- 70 jetons d'entrée, 219 jetons de sortie ; durée d'évaluation de sortie : 18,610 s ;
- arrêt `stop`, JSON conforme au contrat, résultat conservé au niveau `hypothesis` ;
- modèle/digest inchangés, aucun téléchargement ni entraînement, déchargement demandé par `keep_alive=0`.

Voir les [paramètres, empreintes, réponse et métriques](preuves/inference-gemma-20261024.json).
La mémoire GPU n'a pas été mesurée, l'arbitrage avec Whisper reste à intégrer et aucun benchmark Qwen n'est
revendiqué. La réussite de cet échantillon ne garantit pas la disponibilité mémoire des appels suivants.
