# ADR-0001 : PostgreSQL comme seule base de données
Statut : accepté · Date : 2026-09-02 · Issue : CAR-3

## Contexte
L'application enregistre des commandes et des clients (app/commandes.py:7). Moins de 500 commandes par jour.
Budget d'hébergement : un seul serveur, aucun service payant supplémentaire.

## Options
### Option A — PostgreSQL
Coût : déjà installé sur le serveur, aucune dépense.
Bloque : rien.
Retour arrière : export SQL standard.

### Option B — SQLite
Coût : nul.
Bloque : les écritures concurrentes de plusieurs processus.
Retour arrière : réimporter le fichier dans PostgreSQL.

## Décision
Option A. Les écritures concurrentes sont déjà nécessaires ; l'option B est écartée pour cette raison.

## Conséquences
Les sauvegardes passent par pg_dump. Toute nouvelle persistance utilise cette base tant qu'un ADR ne dit pas autre chose.

## Découpage
| tâche | rôle conseillé | fichiers | critère vérifiable |
| --- | --- | --- | --- |
| Schéma initial | data | migrations/0001_initial.sql | la migration monte et redescend |
| Accès aux commandes | backend | app/commandes.py | tests de création et de lecture |
