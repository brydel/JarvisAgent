# ADR-0004 — Rust pour l'exécutant : pas maintenant

Statut : PROPOSED · 21 octobre 2026

## Contexte
Rust est candidat pour la supervision d'exécutant (processus longs, client de protocole typé, mesures de
ressources, service multiplateforme).

## Décision
L'exécutant M1 est en Python (`coureur.py`, ~170 lignes, bibliothèque standard). Aucune limite mesurée ne justifie
Rust aujourd'hui.

## Critères de réévaluation (M3)
Prototype Rust comparé au Python sur : mémoire au repos, fiabilité de supervision (sous-processus orphelins après
`kill -9`), latence de reprise après coupure, facilité de distribution aux clients (binaire unique), sécurité du
parsing du protocole. Migration seulement avec prototype, tests comparatifs, gain démontré et plan de retour.

## Alternatives
Réécriture immédiate en Rust : rejetée (pas de limite identifiée, coût de deux langages pour un seul développeur).
