# Cas d'évaluation des rôles (goldens)

Un dossier par rôle, un sous-dossier par cas :

- `cas.toml` : titre, consigne donnée à l'agent, durée maximale, et ce que le brief du rôle (`roles/<rôle>.md`)
  doit garder — une modification de prompt qui le retire casse les tests :
  - `exigences_brief` : règles métier, des expressions cherchées dans le brief (« réversible », « jamais un ordre ») ;
  - `exigences_compte_rendu` : contrôles exécutés sur l'exemple et le contre-exemple de compte rendu du brief, relus
    par `lib/jarvis/comptes_rendus.py` — `exemple` (chaque critère a sa preuve, chaque vérification son résultat ;
    pour une relecture, verdict conforme), `contre_exemple` (présent, et refusé par l'analyseur), `preuve_par_test`
    (un critère de l'exemple est prouvé par un test), `ecart_declare` (l'exemple déclare une hypothèse ou un risque) ;
- `depart/` : le projet tel que l'agent le reçoit ;
- `reference/` : une solution correcte (fichiers ajoutés ou remplacés sur `depart/`) ;
- `verifier.py` : la vérification **cachée** (l'agent ne la voit pas), lancée depuis le dossier du projet, code 0
  = réussi. Aucun LLM ne juge : uniquement des tests et des contrôles exécutables.

`python3 -m unittest discover -s tests` vérifie, gratuitement, que chaque vérification refuse le départ, accepte
la référence, et que chaque brief garde ses exigences. `jarvis eval lancer <rôle>/<cas>` fait travailler un vrai
agent sur une copie du départ puis lance la vérification : cela consomme ton quota, c'est donc manuel.

Les quinze rôles ont au moins un cas. Quand le livrable est un texte (ADR, rapport, annonces, storyboard, verdict),
la vérification en contrôle la structure et les faits vérifiables, pas le style : sections, renvois `fichier:ligne`
qui existent, limites de caractères, nombres présents dans la source, contraste calculé. Le verdict du cas `revue`
est relu par l'analyseur de l'usine (le harnais donne son chemin à la vérification dans `GOLDENS_LIB`).

Une exécution réelle enregistre aussi `compte_rendu` (type, conformité, anomalies du compte rendu rendu par
l'agent). C'est une mesure à part : `ok` reste le verdict de la vérification cachée.

Ces fichiers sont protégés (politique « protection », niveau 3) : un candidat d'amélioration de prompt ne les
modifie jamais.
