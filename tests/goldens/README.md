# Cas d'évaluation des rôles (goldens)

Un dossier par rôle, un sous-dossier par cas :

- `cas.toml` : titre, consigne donnée à l'agent, durée maximale, et `exigences_brief` (expressions que le brief
  du rôle, `roles/<rôle>.md`, doit contenir : une modification de prompt qui les retire casse les tests) ;
- `depart/` : le projet tel que l'agent le reçoit ;
- `reference/` : une solution correcte (fichiers ajoutés ou remplacés sur `depart/`) ;
- `verifier.py` : la vérification **cachée** (l'agent ne la voit pas), lancée depuis le dossier du projet, code 0
  = réussi. Aucun LLM ne juge : uniquement des tests et des contrôles exécutables.

`python3 -m unittest discover -s tests` vérifie, gratuitement, que chaque vérification refuse le départ, accepte
la référence, et que chaque brief garde ses exigences. `jarvis eval lancer <rôle>/<cas>` fait travailler un vrai
agent sur une copie du départ puis lance la vérification : cela consomme ton quota, c'est donc manuel.

Ces fichiers sont protégés (politique « protection », niveau 3) : un candidat d'amélioration de prompt ne les
modifie jamais.
