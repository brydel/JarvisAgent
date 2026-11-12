# Chef multi-moteur : Claude Code ou Codex, relève automatique

## Pourquoi

Le chef était lancé en dur avec `claude`. Abonnement Claude épuisé ou panne côté Anthropic : l'usine restait
sans direction alors que Codex avait de la marge. Les agents, eux, basculaient déjà d'un fournisseur à l'autre.

## Ce qui a changé

| Élément | Rôle |
| --- | --- |
| `lib/jarvis/chef_moteur.py` | choix du moteur, permissions partagées, garde des commandes, relève |
| `bin/jarvis-chef-codex` | lance le chef sur Codex (bac à sable, sans réseau, aucune demande) |
| `bin/jarvis-chef` | seule sortie du bac à sable : vérifie l'appelant, puis la commande |
| `jarvis chef-moteur` | ordre, état des abonnements, prochain lancement |
| `chef_releve_check` (démon) | relève en deux temps quand le moteur du chef est épuisé |
| `<dossier du chef>/AGENTS.md` | rôle du chef réécrit pour Codex (commandes préfixées par `jarvis-chef`, consignes propres à Claude Code traduites : voir « Volet chef » dans `agents-qualite.md`) |
| `jarvis aide chef` | table des commandes du chef, lecture seule ; sur Codex, marque celles que la porte refuse |
| `<dossier du chef>/.codex/rules/chef.rules` | la règle qui laisse sortir `jarvis-chef`, visible du chef seul |

## Équivalence des garde-fous

| Garde-fou | Chef Claude | Chef Codex |
| --- | --- | --- |
| Ne lance que l'approuvé | `jarvis task` + `JARVIS_ROLE=chef` | identique (posé par `jarvis-chef`) |
| N'approuve pas, ne règle pas, ne lève pas de pause | règles `deny` | `chef_moteur.verifier` : mêmes listes, interdits d'abord |
| Ne modifie ni code, ni état, ni réglages | `deny` Edit/Write par dossier | bac à sable : écriture limitée au dossier du chef |
| Pas de contournement (`python`, `env`, `workmux add`) | règles `deny` | hors liste = refus ; le reste tourne dans le bac à sable |
| Réservé au chef | sans objet | l'appelant doit descendre de la fenêtre « chef » |
| Ne lit pas les `.env` | règles `deny` Read | **non tenu par la technique** ; pas de réseau dans le bac à sable |

## Vérifié en réel le 11 novembre 2026 (Codex 0.164.0, session tmux et état Jarvis isolés)

- démarrage sans boîte de dialogue, rôle `AGENTS.md` lu ;
- `jarvis-chef jarvis note …` écrit bien l'état (hors bac à sable) ; `jarvis-chef jarvis plan ok` et
  `jarvis-chef workmux add` refusés ; `touch` hors du dossier refusé (« Read-only file system ») ;
- `JARVIS_ROLE=chef jarvis-chef …` (variable devant) tourne dans le bac à sable et échoue : refus par défaut ;
- messages du démon remis au chef Codex. Défaut trouvé et corrigé : Codex prend une saisie immédiatement
  suivie d'Entrée pour un collage, d'où une courte pause avant Entrée (`agents.CODEX_PAUSE_SAISIE`).

## Non vérifié

- une relève réelle sur abonnement réellement épuisé (testée avec de faux quotas et de faux CLI) ;
- une vague complète dirigée par le chef Codex (Linear, plans, contre-relecture) : à observer une nuit avant
  de s'y fier ;
- le retour automatique au moteur préféré : volontairement absent, il se fait au prochain lancement du chef.

## Mise en service

`./install.sh` (droits d'exécution des nouveaux binaires), puis `jarvis relancer --chef`. Pour revenir à
l'ancien comportement : `jarvis regler general.chef_moteurs claude`.
