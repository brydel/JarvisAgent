# Validation du lot défensif

Validation cloud du 24 octobre 2026, exemples exclusivement synthétiques.
Base : `12a620909ce5feca9337c67933a0918db8fe87ab`. Aucune validation PC/Jetson.

## Traçabilité des tests ciblés

Commande : `python3 -m unittest discover -s tests -p test_defense.py -v`.
14 tests réussis sur la version finale.

| Exigence | Tests de `test_defense.py` |
| --- | --- |
| Seuil, preuves, signal ≠ intrusion | `test_seuil_et_succes_non_intrusion` |
| Faux positifs, corrélation et frontière temporelle | `test_fenetre_et_correlation` |
| Succès antérieur ou simultané | `test_succes_avant_ou_simultane`, `test_succes_et_echec_simultanes_apres_seuil` |
| Tri et fuseaux | `test_tri_et_fuseaux` |
| Répétitions et dédoublonnage | `test_dedoublonnage_repetition_et_rejeu` |
| SSH strict, injection sans exécution | `test_ssh_strict_et_injection` |
| Secrets et identifiants supprimés | `test_redaction_tous_champs_et_erreurs` |
| Absence de données, formats, tailles, encodage | `test_malformes_vides_limites`, `test_json_espaces_autour` |
| CLI intégrée, FIFO et liens refusés | `test_cli_et_fichier_special` |
| Contrat AgentSpec et épinglage skills | `test_contrat_et_skills` |
| Mandat, catalogue, rejeu, stockage expurgé, réseau/commandes interdits | `test_catalogue_mandat_rejeu_et_stockage_expurge`, `test_refus_mandat_et_arguments` |

Une revue indépendante a exécuté les skills sur l'exemple, un lot vide, des répétitions
et une injection. Elle a relevé un échec simultané masquant le succès après cinq échecs
antérieurs ; correction et test des deux ordres ajoutés. Aucun autre défaut bloquant
signalé. Les espaces autour des objets JSONL sont également acceptés et testés.

## Contrôles complémentaires

- Suite finale `python3 -m unittest discover -s tests -v` sur le commit de code
  `71319007768b25c3b686f4455b994bcccbe7cae2` : **772 tests, 667 réussis,
  105 ignorés, aucun échec** (140,343 s). Les 14 tests défensifs,
  dont les deux derniers ajoutés, sont inclus et réussissent. Les cas ignorés
  concernent PostgreSQL, des outils multimédia/navigateur et les intégrations réelles
  RedTeam non configurées. Aucun de ces prérequis n’a été installé ou activé.
  Ce bilan remplace le résultat intermédiaire de 770 tests ; seule la documentation
  a été mise à jour après cette exécution, sans modification du code testé.

- Passerelle `test_outils.py` : 34 tests réussis.
- Board `test_board_v2.py` : 64 tests réussis sur la base propre et sur ce lot.
  L'échec CI signalé sur « Plan de la semaine » n'est pas reproduit dans cet environnement.
  Aucun changement Board effectué ; cela ne démontre pas que sa CI est réparée.
- Model Bridge : 11 tests réussis.
- Temporal : 17 tests réussis avec le SDK déjà disponible dans l'environnement cloud.
- Syntaxe shell, compilation Python `lib/jarvis services`, `bin/jarvis help`,
  `git diff --check` et égalité des deux templates : réussis.
- Les deux skills passent `quick_validate.py` et le contrôle d'empreinte du registre.
- ShellCheck : code 1, 15 diagnostics préexistants (SC2015 et SC2088), comparés à la
  base par fichier/code/message ; aucun nouveau diagnostic. Aucun correctif hors périmètre.
- Aucun des fichiers supprimés par PR12 n'est réintroduit.

## Vérification des restrictions et du périmètre public

Relecture du bilan : uniquement résultats de tests synthétiques du code, contrôles
statiques et limites ; aucun inventaire, chemin personnel, adresse, configuration
ou résultat matériel du Lab. Aucun journal brut de test n'est ajouté au dépôt.

La CLI passe par `lire_fichier()` puis `analyser()`, comme l'outil pour cette dernière
fonction : mêmes limites, normalisation et suppression des identifiants/messages.
Un contrôle en répertoire temporaire confirme l'identité du rapport avec le moteur,
l'absence de fichier persistant créé et le refus d'une entrée trop volumineuse sans
reproduire son chemin. Aucun chemin d'exécution de remédiation n'est exposé.

L'outil exige un mandat existant ; il ne crée ni droit, ni connexion, ni service,
ni accès persistant. La passerelle conserve les traces d'opération et le rapport
expurgé, et consomme le quota du mandat : cette persistance de suivi n'est pas un
accès au poste. Il n'y a ni collecte, ni surveillance continue, ni déploiement.

Seules deux règles existent : AUTH-001 (cinq échecs uniques au moins dans 300 secondes
pour un même triplet source/compte/hôte) et AUTH-002 (ces échecs strictement antérieurs
à un succès, tous dans les 300 secondes terminées par ce succès). AUTH-002 remplace
AUTH-001 pour ce groupe. Les signaux restent à vérifier, jamais des intrusions
confirmées. Détection et dédoublonnage restent limités au lot fourni ; formats non
reconnus, attaques lentes/distribuées et faux positifs restent des limites connues.

## Non exécuté et limites

Pas de build Studio ni Playwright : dépendances frontend absentes, aucune modification
frontend. Pas de scan Gitleaks : binaire absent ; revue manuelle des nouveaux fichiers
et contrôle des suppressions PR12 réalisés, sans prétendre remplacer un scan de secrets.
Aucun appel fournisseur, modèle téléchargé, scan actif, installation, déploiement ou
remédiation. Les tests restent synthétiques et ne prouvent pas une protection réelle.
Les journaux techniques des tests restent hors dépôt ; seul ce bilan est public.

## Publication et combinaison avec le banc #13

Références testées dans un worktree cloud distinct, sans modification des branches
concurrentes ni fusion des PR :

- Base commune : `12a620909ce5feca9337c67933a0918db8fe87ab`.
- Défense [PR #14](https://github.com/brydel/JarvisAgent/pull/14) :
  `5dd777a4c2abb439a459e1c11e84edfc651a2724`.
- Banc [PR #13](https://github.com/brydel/JarvisAgent/pull/13) :
  `ce72978387b029550cb7656e1a016703a9bb6f09`.
- Commit combiné exclusivement local : `98f49145964d1145cd25544e4241e68bc89c363d`.

La fusion locale de test est sans conflit textuel. Le banc ajoute seulement ses
modifications sur trois fichiers ; aucun fichier privé retiré par PR12 n'est restauré.
Le code des deux lots reste identique à ces SHA ; les ajouts suivants à la PR #14
ne modifient que le guide et ce bilan.

Suite générale combinée : **772 tests, 667 réussis, 105 ignorés,
aucun échec** (140,150 s), incluant les 14 tests Défense. Les tests
synthétiques existants Board, agents/runtime, passerelle/mandats, transports,
communauté, stockage et intégration du nœud passent dans cette suite, sous réserve
des cas ignorés (PostgreSQL et dépendances optionnelles, dont intégrations réelles).

La suite du service `services/noeud_jetson/tests` passe : 35 tests, dont 15 du banc.
Model Bridge : 11 tests réussis ; Temporal : 17. Syntaxe shell/Python, aide CLI,
égalité des templates et contrôle du diff passent. Aucun vrai modèle, conteneur
RedTeam, équipement ou accès Jetson n'est utilisé pour cette validation combinée.
La disponibilité de `tmux` dans cet environnement permet les tests généraux ; les
échecs faute de `tmux` rapportés dans l'environnement du banc sont une différence
de prérequis, pas une régression attribuable à cette combinaison.

CI de la PR #14 au SHA `5dd777a4c2abb439a459e1c11e84edfc651a2724` :
[exécution 40067427285](https://github.com/brydel/JarvisAgent/actions/runs/40067427285),
terminée en échec. Build Studio et syntaxe réussis ; job Temporal réussi. Le job
`verify` échoue sur `test_le_chef_lit_et_alimente_le_board`, argument
« Plan de la semaine » non reconnu, identique au défaut CI préexistant signalé.
Les tests navigateur suivants ne sont pas exécutés. Le test et le parseur Board
sont inchangés par ce lot ; seul le nouveau parseur `defense` est enregistré dans
le CLI commun. Aucun correctif hors périmètre n'est apporté. Le résultat local
ne doit pas être présenté comme une CI verte.

Les fonctions existantes sont évaluées par leurs tests synthétiques, pas par un
parcours du poste réel. Le checkout installé, les changements privés et les services
WSL/Jetson restent inconnus : aucune garantie d'absence de conflit ou de maintien
opérationnel sur ces machines. Suivre [REPRISE_WSL.md](REPRISE_WSL.md) avant de
proposer une bascule ; aucune installation ou activation n'a été effectuée ici.
