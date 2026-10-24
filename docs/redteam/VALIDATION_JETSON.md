# Validation du parcours Jetson réel — 24 octobre 2026 UTC

Cette validation complète les [mesures WSL](VALIDATION_WSL.md). Le propriétaire a donné au compte SSH
l'accès Docker, puis a créé le mandat de laboratoire depuis son terminal interactif. Le code déployé est
celui de `reprise/redteam` au commit `1ac26cb`, sans import d'une autre branche.

## Installation et préservation

Docker répond dans une nouvelle session SSH : moteur `29.4.1`, architecture `aarch64`.
L'image Semgrep `1.141.1` a été construite **sur la Jetson ARM64** en 141,461 s :

```text
sha256:e812d30543dda62a6d786462444d01c0abc05611d8d9211d657da23b4c397b0d
```

L'installateur ciblé a ajouté `jarvis_redteam.py`, le moteur et la configuration séparée `redteam.env`.
La clé Jarvis dédiée utilise maintenant le nouveau répartiteur, avec `restrict` conservé et sauvegarde
d'`authorized_keys`. Le module MCP original, `service.py` et la configuration audio sont restés identiques.
Aucun redémarrage du service GPU n'a été demandé.

La vraie clé SSH à commande forcée retrouve les six outils précédents et `redteam_auditer` ; `sante` répond,
une commande inconnue est refusée et le service GPU reste actif après le scan. La préservation est vérifiée
par les fichiers, la découverte et la santé ; aucune nouvelle transcription audio ou lecture d'image n'est
revendiquée dans cet essai. Voir la [preuve de déploiement et d'intégrité](preuves/deploiement-jetson-20261024.json).

## Essais natifs ARM64

Le moteur, lancé sur la Jetson avec le même bac à sable Docker que MCP, a produit :

| Essai | Résultat | Durée du scan |
| --- | --- | --- |
| Fixtures `fixed.py` et `vulnerable.py` | Un constat dans `vulnerable.py`, ligne 6 | 5,613 s |
| Fixture corrigée seule | Aucun constat | 4,983 s |
| Rejeu de la même demande dans un autre processus | Rapport identique | Vérifié |

Les trois étapes utilisent des cibles synthétiques fixes ; aucun code cible n'est exécuté.
Le contrôle Docker ne retrouve aucun conteneur `jarvis-rt-*` après les essais.
Voir la [preuve des scans et du rejeu](preuves/scan-arm64-20261024.json).
Le champ `rejeu_duree_s` de cette preuve inclut aussi le contrôle final des conteneurs.

## Parcours Jarvis → mandat → SSH/MCP → Docker → communauté

Le registre Jarvis, sa configuration et ses données de laboratoire sont isolés sous
`/tmp/jarvis-redteam-reprise/ssh-lab`. Le registre du Jarvis actif n'a pas été modifié.
Le propriétaire a exécuté le script d'autorisation depuis son terminal : un mandat d'une heure,
dix appels au plus, zéro coût API, outil unique `mcp.jetson-redteam-lab.redteam_auditer` et destination exacte
`mcp:jetson-redteam-lab`. La vérification de terminal humain de la CLI est conservée.

Deux appels CLI dans deux processus distincts ont donné le même rapport et le même fil :

- premier appel : **5,821 s**, dont **5,037 s** de scan sur la Jetson ;
- second appel : **0,087 s**, résultat idempotent de la passerelle ; une seule action consommée au total ;
- opération `succeeded`, rapport `reported`, étapes PLAN/EXECUTE/OBSERVE/VERIFY/REFLECT/DELEGATE/REPORT complètes ;
- un constat Semgrep, réseau Docker `none`, racine du conteneur en lecture seule, utilisateur 65534,
  768 Mo, un CPU et 128 PID selon la politique fixe du moteur ;
- fil de revue publié et relu dans la communauté **de laboratoire**, statut `pending` ;
- préflight d'un appel audio avec ce mandat RedTeam refusé sans effet.

La preuve conserve les résultats et les quotas, sans identifiant de connexion personnel ni adresse SSH :
[parcours complet](preuves/parcours-ssh-20261024.json).
L'état du nœud est privé (`0700`). Les deux sources et la règle stockées sous leurs empreintes ont été
relues sur la Jetson et hachées ; l'empreinte du rapport a été recalculée et aucun conteneur résiduel n'a été trouvé.

## Périmètre opérationnel et limites

Le parcours SAST distant est **validé pour le laboratoire synthétique configuré**. La clé forcée expose l'outil,
mais la connexion du Jarvis actif ne reçoit aucun nouveau mandat ni sélection d'outil automatiquement.
Le mandat de laboratoire expire ; une utilisation ultérieure exige un mandat propriétaire encore valide.
La configuration de cible et d'état reste sur le nœud, hors de la demande du modèle.

Un constat Semgrep reste un résultat d'outil : `lab_reproduced=false`, `impact_confirmed=false`.
La publication d'une demande de revue ne prouve pas qu'un worker indépendant l'a traitée. L'inférence Gemma
réussie lors de la reprise précédente est séparée de ce scan ; aucune inférence n'est nécessaire au moteur SAST.
Pas de battement permanent, d'arbitrage GPU avec Whisper ou de nettoyage après SIGKILL validé par cet essai.

Le code n'a pas changé depuis la suite locale de **755 tests, un ignoré**, documentée dans la reprise WSL.
Pour cet incrément de déploiement : syntaxe bash, aide CLI, identité des deux modèles AGENTS/CLAUDE, empreintes
des modules déployés et cohérence des preuves vérifiées ; shellcheck reste absent.

Suite du [backlog](ARCHITECTURE.md) : revue indépendante active, annulation et récupération après mort brutale,
quotas et rétention des preuves, disponibilité mémoire et coordination audio/LLM, puis outils et labs supplémentaires.
