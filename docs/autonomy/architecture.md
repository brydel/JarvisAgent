# Architecture cible et implémentation légère

Cinq responsabilités séparées **logiquement**, dans le même processus Python et le même dépôt : pas de
microservices, pas de base distribuée, pas de Kubernetes. Chaque dépendance ajoutée se justifie ; ce lot
n'en ajoute **aucune** (bibliothèque standard, tmux/workmux existants).

| Responsabilité | Rôle | Modules aujourd'hui | Manque |
| --- | --- | --- | --- |
| Stratégie et portefeuille | opportunités, priorités, budgets, poursuivre/arrêter | `travaux.py` (file de propositions), `budgets.py`, `config.projects` (priorités), chef (`chef/CLAUDE.md`) | modèle d'opportunité et pipeline SaaS (lot 3) |
| Orchestration | plans, dépendances, affectations, files, reprises | `plans.py`, `modeles.py` (routeur), `roles.py`, `taches.py`, `poste.reprendre` | dépendances explicites entre tâches |
| Exécution | agents et outils en environnements isolés | workmux + worktrees, `bin/jarvis-claude`, `bin/jarvis-codex` (bac à sable Codex), skills | isolation forte (VM/conteneur par agent), plafonds de processus |
| Contrôle indépendant | permissions, quotas, budgets, secrets, audit, arrêt | `admission.py`, `pauses.py`, `politique.py`, `budgets.py`, `journal.py`, `usage.py`, `config.valider` | indépendance réelle : tout tourne sous le même utilisateur (voir `securite.md`) |
| Évaluation | vérification des livrables et des améliorations | contre-relecture croisée, `jarvis verdict`, `studio.verifier`, `travaux.terminer` (preuve + vérificateur ≠ exécutant) | jeux d'essai protégés et promotion de candidats (lot 4) |

## Le chef ne détient pas seul le pouvoir

- **Proposer** : le chef (plans, propositions de modèles, propositions de travaux).
- **Autoriser** : l'humain (plans, délégations, budgets, profils, pauses) ; la politique versionnée ;
  l'admission (automatique, mécanique).
- **Exécuter** : agents dans leurs worktrees, un exécutant par travail.
- **Déclarer réussi** : un vérificateur différent de l'exécutant (contre-relecture, `travaux.terminer`,
  `jarvis verdict`), jamais l'agent lui-même ni le chef seul pour un livrable externe.

## Flux d'un départ (lot 1)

```
plan approuvé / jarvis task / reprise / relance du chef
        │
        ▼
admission.demander  ── verrou unique ──  config.valider → pauses.actives → agents.status_all (fail closed)
        │                                → capacité (poste.capacite + réservations) → opérations lourdes
        │                                → doublons → jetons → plans.authorize_launch
        ▼
réservation R-xxxxx (compte comme occupée, expire à 15 min)
        │
        ▼
tache-enregistrer (confirme) → workmux add → fenêtre visible → réservation « démarrée »
        │ échec → admission.liberer (+ plan relâché)         │ jamais visible → expirée, plan relâché, chef prévenu
```

## Chemin vers plusieurs machines

Commencé en vague 3 (`vague-3.md`), sur un poste : stockage SQLite facultatif derrière `store.py` (migration
vérifiée et retour), bail d'orchestrateur (un seul démon, numéro de clôture), exécutants déclarés avec capacité
mesurée. Reste conçu : un état partagé sur un serveur (SQLite ne se partage pas par le réseau), des exécutants
distants qui reçoivent du travail de l'admission, le bail dans cette base partagée.

## Persistance

Fichiers JSON sous `~/.local/state/jarvis/`, écrits de façon atomique (fichier temporaire + `replace`)
sous verrou `fcntl` par fichier, plus un verrou global `admission`. Journal d'audit en JSONL ajout seul,
chaîné par empreintes. Suffisant pour un poste ; une migration vers SQLite n'est justifiée qu'avec
plusieurs exécutants (voir ci-dessus) et se ferait avec import des JSON existants.
