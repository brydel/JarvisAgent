# CAR-18 — La création d'une commande attend le courriel

Créer une commande prend jusqu'à 3 secondes : le courriel de confirmation part pendant la requête. Quand le serveur
SMTP est en panne, la commande échoue.

Contraintes : un seul serveur, aucun service payant ni service supplémentaire à exploiter si on peut l'éviter ;
PostgreSQL est déjà en place (ADR-0001) ; environ 200 courriels par jour.

Attendu : une décision d'architecture écrite (ADR), et un découpage en tâches.
