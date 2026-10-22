# Jarvis Studio — spécification produit — PROPOSED (M2)

Un poste de travail d'ingénierie dans le navigateur, sobre et précis : il montre le comportement **réel** du
système. Pas de dégradés décoratifs, pas de métriques sans source, pas d'activité simulée présentée comme réelle.

## Vues

| Vue | Données réelles (déjà disponibles en M1 côté moteur) |
| --- | --- |
| Board (canevas persistant) | `board_objets` : identité durable, position x/y, lien mission/artefacts |
| Organisation en direct | tâches, parents, fournisseur choisi, statut, durée, erreurs, approbations requises |
| Graphe de mission | tâches et dépendances (parent/enfant aujourd'hui ; dépendances explicites M4) |
| Inspecteur d'agent / de tâche | tentatives, bail, décision de politique, artefacts, revue |
| Centre d'approbation | action proposée, effets attendus, niveau, empreinte du travail approuvé |
| Explorateur de connaissance | M5 |
| Moniteur d'exécution | exécutants (dernier signe), connexions fournisseurs (indisponibilité), budget, échecs, événements |

## Contrats

- Le navigateur ne commande jamais un shell, des droits élevés ou des identifiants de fournisseur ; toute action
  passe par une API authentifiée qui appelle le moteur de politique.
- Flux : SSE sur `evenements(apres=seq)` ; à la reconnexion, le client renvoie le dernier `seq` reçu.

## Technologies à évaluer (aucune adoptée)

Next.js + React (TypeScript) ; React Flow (licence MIT) pour graphes ; canevas infini : tldraw (licence SDK
commerciale à vérifier pour un usage SaaS) contre une implémentation React Flow/Konva (MIT) — **licence à valider
avant tout engagement** (D-4) ; Three.js / React Three Fiber pour des avatars optionnels qui reflètent un état
réel et ne bloquent jamais les contrôles ; composants accessibles (Radix UI), animations légères, mouvement
réduit, navigation clavier, mise en page responsive.

Le Studio vivra dans un service séparé (`studio/`), pour ne pas imposer Node au cœur Python (ADR-0002).

## Implémenté en local (M2, première partie) — VERIFIED

`jarvis mission studio` sert sur 127.0.0.1:7718 (`lib/jarvis/studio_api.py`, bibliothèque standard) une page Board
sans framework ni dépendance (`studio_board.html/.css/.js`) : canevas à cartes déplaçables (souris, ou clavier :
flèches, Maj pour un grand pas), ajout de note, statut de mission, artefacts avec revue et marque FACTICE,
approbations, moniteur d'exécution, flux d'activité en direct. Thème clair/sombre selon le système, mouvement
réduit respecté, affichage téléphone en une colonne. Sécurité : voir l'en-tête de `studio_api.py` et
`tests/test_studio.py`. Next.js, React Flow et le canevas infini restent à évaluer (ADR-0005).
