# ADR-0002 : les courriels partent d'une file en base, hors de la requête
Statut : proposé · Date : 2026-11-11 · Issue : CAR-18

## Contexte
`creer_commande` envoie le courriel pendant la requête HTTP (app/commandes.py:8) et `envoyer_courriel` attend le
serveur SMTP jusqu'à 3 secondes (app/notifications.py:11). Volume : 200 courriels par jour. Contraintes de
l'issue : aucun service payant, un seul serveur, PostgreSQL déjà en place (ADR-0001).

## Options
### Option A — table `courriels_a_envoyer` dans PostgreSQL, vidée par un processus séparé
Coût : une table, une boucle d'envoi, aucun service nouveau.
Bloque : rien au volume annoncé ; à revoir au-delà de quelques milliers d'envois par heure.
Retour arrière : rebrancher l'appel direct dans app/commandes.py, la table peut rester vide.

### Option B — Redis et une bibliothèque de tâches
Coût : un service de plus à installer, surveiller et sauvegarder.
Bloque : contredit la contrainte « un seul serveur, aucun service supplémentaire ».
Retour arrière : retirer le service et la dépendance.

### Option C — ne rien changer
Coût : nul.
Bloque : chaque commande attend le serveur SMTP ; une panne SMTP fait échouer la commande.
Retour arrière : sans objet.

## Décision
Option A. Elle retire l'attente de la requête sans ajouter de service, et l'enregistrement de la commande et celui
du courriel à envoyer se font dans la même transaction. Les options B et C sont écartées : B pour son coût
d'exploitation au regard de 200 envois par jour, C parce qu'elle laisse le défaut en place.

## Conséquences
Un courriel peut partir quelques secondes après la commande. Il faut surveiller la taille de la file et les envois
en échec (nombre d'essais borné). Le processus d'envoi doit être relancé avec le serveur.

## Découpage
| tâche | rôle conseillé | fichiers | critère vérifiable |
| --- | --- | --- | --- |
| Table de la file | data | migrations/0002_courriels_a_envoyer.sql | la migration monte et redescend en local |
| Mise en file à la création | backend | app/commandes.py, tests/test_commandes.py | créer une commande n'ouvre aucune connexion SMTP (test) |
| Boucle d'envoi | backend | app/envoi.py, tests/test_envoi.py | un envoi en échec est réessayé 3 fois au plus (test) |
| Lancement du processus | devops | deploiement/envoi.service | le service redémarre seul après un arrêt |
