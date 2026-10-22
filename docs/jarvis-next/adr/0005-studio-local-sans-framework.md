# ADR-0005 — Premier Studio local sans framework ni dépendance

Statut : PROPOSED (implémenté et vérifié) · 21 octobre 2026

## Contexte
M2 doit montrer une mission réelle depuis le navigateur. Le cœur est en Python sans dépendance ; Node 22 existe
dans WSL mais aucun outillage frontend n'est installé ; la licence du canevas (D-4) n'est pas tranchée.

## Décision
Première version servie par `http.server` (bibliothèque standard) et une page HTML/CSS/JS sans framework ni étape
de construction, sur 127.0.0.1. API JSON + SSE stables, pour qu'un futur frontend (Next.js/React) les réutilise
sans changer le serveur.

## Alternatives
- Next.js + React Flow tout de suite : outillage npm, dépendances à verrouiller et licence de canevas à vérifier
  avant d'avoir prouvé le parcours ; reporté.
- Étendre le tableau de bord `web.py` (lecture seule, port 7717) : il est volontairement sans action ni
  authentification ; mélanger les deux affaiblirait ses garanties. Gardé séparé.

## Conséquences
Pas de dépendance ajoutée. Le Board est un canevas borné (3 000 × 2 000 px), pas un canevas infini. Une seule
session utilisateur, gardée en mémoire : un redémarrage du Studio demande de rouvrir le lien.
