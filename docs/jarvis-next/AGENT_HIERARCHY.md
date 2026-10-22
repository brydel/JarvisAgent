# Organisation des agents — PROPOSED (bornes de délégation : VERIFIED)

Hiérarchie logique, pas des sessions de modèle toujours actives :

```
Fondateur (humain)
 └─ Planificateur exécutif Jarvis   ← aujourd'hui : le chef (chef/CLAUDE.md)
     └─ Directions (ingénierie, architecture, sécurité, recherche, marketing, produit, QA, documentation, opérations)
         └─ Spécialistes                ← aujourd'hui : roles/*.md (15 rôles)
             └─ Exécutants de tâches et sous-agents
```

## Définition d'agent (versionnée)

identité, rôle, capacités déclarées, outils approuvés, niveau maximal (L0–L4), contraintes de fournisseur,
références de contexte, budget, parent, historique d'évaluation. Base existante : `roles/*.md`, `roles.py`,
`versions_roles.py` (briefs versionnés avec canari), `evaluation.py` (goldens).

## Règles

- Délégation par identifiants explicites parent/enfant (`missions.deleguer`) ; un enfant ne dépasse jamais le
  niveau ni les capacités du parent ; profondeur, largeur et total bornés (VERIFIED).
- L'ordonnanceur peut refuser une délégation redondante (même type + même empreinte de travail dans la mission) :
  PROPOSED (M4).
- Jamais deux agents sur le même espace de travail mutable sans stratégie de concurrence : un worktree par tâche
  de code (CURRENT), contre-relecture par l'autre fournisseur (CURRENT).
- Un spécialiste peut **proposer** un nouveau rôle ; son enregistrement passe par la politique et l'humain.
