# ADR-0001 — Monolithe modulaire plutôt que microservices

Statut : PROPOSED · 21 octobre 2026

## Contexte
Un poste, un utilisateur, un exécutant ; dix modules logiques au plan de contrôle.

## Décision
Les modules du plan de contrôle restent dans `lib/jarvis` comme fonctions à contrats explicites. Un module ne
devient un service que si une exigence mesurée l'impose (mise à l'échelle indépendante, frontière de confiance,
langage différent).

## Alternatives rejetées
- Microservices dès M1 : coût d'exploitation et de débogage sans bénéfice mesurable.
- Tout dans le Studio (Node) : casserait la contrainte bibliothèque standard et l'existant Python.

## Conséquences
L'exécutant sera le premier composant séparé (M3), car c'est une frontière de confiance.
