# Intégration locale du Board V3 — 13 novembre 2026

La version active partait de `79986c0` sur `integration/jetson-live`. Le worktree `board-v3`, sur
`integration/board-v3` (`d2bf945`), contenait 53 commits supplémentaires, sans divergence. Les trois
modifications locales de code du poste correspondaient exactement au correctif `cb5248e`, déjà inclus.
La branche de validation est `codex/board-v3-integration`.

## Comportement livré

Cette intégration apporte les fondations de données du Board, le tableau blanc, les relations à effet réel,
la bibliothèque de références, la direction visuelle « Salle de rédaction », le chef multi-moteur et
les deux lots de qualité des consignes et des comptes rendus. Voir les dossiers de ces lots pour leur périmètre.

La validation a permis de corriger trois défauts supplémentaires :

- La remise d'un message au chef cible désormais un volet vivant et son PID, même si une autre fenêtre
  « chef » est restée sur un shell ou si le volet sélectionné est un shell. La remise garde cette cible
  et revérifie son activité avant Entrée. Un arrêt ou un refus de tmux conserve le message dans la file.
- Un panneau d'activité qui change de hauteur pendant un tracé ne modifie plus ses dimensions : le geste
  conserve son repère de départ. Zoom et déplacement au bouton du milieu restent disponibles entre les tracés.
- Le premier dessin ne déclenche plus de cadrage automatique après le retour de l'outil à « sélection ».
  Cette décision utilise le type des objets reçus plutôt que l'outil au moment de la réponse réseau.

Les parcours navigateur attendent le premier relevé d'activité et la stabilité des poignées avant un geste.
Le parcours du chef utilise la commande de cadrage lorsque ses nouvelles cartes ont déplacé la source hors champ.
Aucune attente arbitraire supplémentaire ni augmentation de délai ne masque un défaut.

## Preuves de régression

`tests/test_chef_cible.py` couvre deux fenêtres homonymes, un dialogue dans le vrai chef, un volet shell
sélectionné, un arrêt pendant la saisie et un volet terminé. Les trois premiers cas échouaient avant correction.
`tests/test_activite.py` conserve le contrôle du message en file après un refus de saisie par tmux.

Le parcours ajouté dans `canevas.spec.ts` agrandit le panneau de 80 pixels pendant un tracé de 240 × 160 pixels
à 80 % de zoom. Avant correction : forme de 300 × 100 unités. Après : 300 × 200 unités, zoom resté à 80 %.
Les parcours de création/redimensionnement et d'autonomie du chef passent également après correction.

## Mesures locales

Même script `outils/mesurer_board.py` et mêmes jeux synthétiques isolés sur les deux versions. Chaque jeu
contient 10 % de missions et une relation pour deux cartes. Médianes locales ; ces mesures ne constituent
pas une garantie de délai sur d'autres machines.

| Cartes | Requêtes SQL avant | Après | Lecture avant | Après |
| --- | ---: | ---: | ---: | ---: |
| 500 | 852 | 13 | 16,215 ms | 6,872 ms |
| 5 000 | 8 502 | 13 | 867,256 ms | 55,225 ms |

Sur 5 000 cartes, la lecture ciblée d'un seul objet prend 3,444 ms. Le sondage à vide par le nouveau lecteur
d'événements prend environ 0,002 ms, contre 0,419 ms pour la lecture historique sur la version active initiale.

## Exploitation

Les modifications locales, la configuration, le dossier du chef et les deux bases SQLite sont sauvegardés
hors du dépôt. Les bases sont copiées par l'API de sauvegarde SQLite pour inclure leur état WAL.
La branche `codex/avant-board-v3-20261113` conserve le commit de départ. Les captures locales préexistantes
sont conservées lors de l'intégration. L'intégration est locale ; aucune publication distante n'est effectuée.

## Validation finale

- Python : 1 159 tests exécutés, 7 ignorés, aucun échec (dont PostgreSQL réel).
- Studio : 172 tests unitaires ; TypeScript et compilation de production réussis.
- Navigateur : 76 parcours réussis, 1 mesure optionnelle ignorée ; captures de référence inchangées.
- Syntaxe shell, aide CLI, absence d'erreurs de diff et égalité des deux modèles d'instructions vérifiées.
  ShellCheck n'était pas installé sur le poste.
- Copie des données réelles : 17 tables vérifiées sans baisse du nombre de lignes, intégrité SQLite OK ;
  lecture du Board d'accueil réussie avec ses 34 objets et 13 relations.

Les 7 cas Python ignorés sont quatre contrôles propres à SQLite rejoués sur PostgreSQL et trois essais
RedTeam nécessitant une image Docker ou Semgrep configurés. Les modèles des parcours automatisés sont
factices ; cette validation ne mesure pas la qualité de réponses d'un fournisseur en production.
