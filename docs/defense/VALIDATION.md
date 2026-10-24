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

- Suite `python3 -m unittest discover -s tests` : 770 tests, 665 réussis et
  105 ignorés, aucun échec (139,823 s). Cette exécution avait chargé les 12 premiers
  tests défensifs ; les corrections de revue et les deux tests supplémentaires ont
  ensuite été validés par les 14 tests ciblés de la version finale. Les cas ignorés
  concernent PostgreSQL, des outils multimédia/navigateur et les intégrations réelles
  RedTeam non configurées. Aucun de ces prérequis n’a été installé ou activé.

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

## Non exécuté et limites

Pas de build Studio ni Playwright : dépendances frontend absentes, aucune modification
frontend. Pas de scan Gitleaks : binaire absent ; revue manuelle des nouveaux fichiers
et contrôle des suppressions PR12 réalisés, sans prétendre remplacer un scan de secrets.
Aucun appel fournisseur, modèle téléchargé, scan actif, installation, déploiement ou
remédiation. Les tests restent synthétiques et ne prouvent pas une protection réelle.
Les journaux techniques des tests restent hors dépôt ; seul ce bilan est public.
