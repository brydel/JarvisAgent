---
name: jarvis-design
description: Direction artistique et porte qualité visuelle de l'usine Jarvis — définir ou relever le niveau visuel d'un produit (direction, jetons de design, typographie, couleur, mouvement), concevoir un écran qui ne fait pas « gabarit par défaut », et critiquer une interface avec une grille notée avant de la déclarer finie. À utiliser pour toute tâche d'interface (design, front-end, page d'accueil, tableau de bord), toute relecture de PR qui touche l'interface, ou quand ton humain trouve le produit « fade ».
---

# Jarvis Design : un produit qu'on a envie d'ouvrir

« Fonctionnel » ne suffit pas : un utilisateur juge un produit en trois secondes, sur son écran. Un
écran fade vient presque toujours de la même cause : personne n'a décidé à quoi le produit doit
ressembler, et chaque agent a pris les valeurs par défaut de sa bibliothèque. Ici on décide d'abord,
on construit ensuite, et on vérifie avec des captures.

## 1. La direction artistique (une fois par produit, revue à chaque veille)

Elle vit dans le dépôt : `design/direction.md` + les jetons dans le code (variables CSS, thème
Tailwind…). Si elle n'existe pas, ou si ton humain trouve le produit fade, **c'est la première tâche**
(rôle `design`, taille L) et rien d'autre dans l'interface ne doit partir avant.

Contenu de `design/direction.md` :

1. **L'intention en une phrase** (« un poste de trading sérieux, dense et vivant, qu'un pro ouvre à 6 h
   du matin »). Trois adjectifs, et trois qu'on refuse.
2. **Références** : 3 à 5 captures (planches de la veille : `$JARVIS_LIVRABLES/veille/captures/`) avec,
   pour chacune, ce qu'on prend (la densité, la typographie, une transition) et ce qu'on laisse.
   S'inspirer, jamais reproduire : ni leur identité, ni leurs couleurs signature, ni leurs mises en page.
3. **Typographie** : deux familles au plus (titres, texte) + une monospace ou des chiffres tabulaires
   pour les données ; une échelle (ex. 12/14/16/20/28/40) ; graisses utilisées. Polices sous licence
   libre (Google Fonts, Fontsource) et auto-hébergées.
4. **Couleur** : fond et surfaces (3 niveaux d'élévation), texte (3 niveaux), **un** accent de marque,
   couleurs sémantiques (succès, alerte, erreur ; hausse/baisse pour la finance, avec un second repère
   que la couleur pour les daltoniens). Thèmes sombre et clair si le produit les sert. Contraste AA
   vérifié.
5. **Espacement et grille** : une base (4 ou 8 px), rayons, ombres ou bordures (un seul langage).
6. **Mouvement** : durées (120–250 ms), courbes, ce qui s'anime (retour d'action, mises à jour en
   direct, ouverture de panneaux) et ce qui ne s'anime jamais. Respect de `prefers-reduced-motion`.
7. **La signature** : un ou deux éléments qu'on reconnaît au premier coup d'œil (un traitement du
   logo repris dans les graphiques, une manière d'afficher les variations, une transition propre au
   produit). Sans signature, le produit ressemble à tous les autres.

Processus : propose **2 à 3 directions** sous forme d'un même écran clé rendu dans chacune
(captures), mets-les sur une planche, et laisse ton humain choisir (le chef la lui livre). Puis
traduis la direction retenue en jetons dans le code, et refais l'écran clé pour preuve.

## 2. Construire un écran

- Lis `design/direction.md` et utilise ses jetons. Aucune couleur, taille ou ombre en dur.
- Commence par la **hiérarchie** : quelle est l'information numéro un ? Elle doit dominer (taille,
  graisse, position). Tout le reste se range derrière.
- Une bibliothèque de composants (shadcn/ui, Radix, MUI…) est un point de départ : **thématise-la**.
  Des cartes grises identiques sur fond gris, c'est le signe qu'on ne l'a pas fait.
- Tous les états : chargement (squelettes à la forme du contenu), vide (une phrase utile et une action,
  pas « Aucune donnée »), erreur (ce qui s'est passé, quoi faire), succès.
- Données réelles ou réalistes en démonstration : jamais de « Lorem ipsum », jamais 3 lignes là où
  l'écran en montrera 300.
- Mobile (390 px) et bureau (1440 px). Clavier : focus visible, raccourcis pour les actions
  fréquentes dans un outil professionnel.

### Applications denses en données (trading, analytique, tableaux de bord)

- Chiffres en `font-variant-numeric: tabular-nums`, alignés à droite, unités et signes cohérents.
- Hausse/baisse : couleur + flèche ou signe ; un changement de valeur en direct se signale par un bref
  éclair de fond (≤ 300 ms), pas par un saut de mise en page.
- Densité réglable (compacte / confortable) ; thème sombre soigné en premier si les utilisateurs
  restent des heures devant.
- Graphiques : bibliothèque solide (vérifie sa licence et ses conditions d'attribution avant de
  l'ajouter), axes lisibles, info-bulle au survol, état de chargement, pas de 3D décorative qui gêne la
  lecture. Les animations 3D se réservent aux pages marketing.

## 3. La porte qualité : prouver, puis noter

Avant de déclarer fini, capture l'écran (avant / après, bureau et mobile) :

```bash
jarvis lourd exec --duree 15 navigateur -- node "$JARVIS_HOME/skills/jarvis-veille/scripts/capturer.cjs" captures.json "$JARVIS_LIVRABLES/design"
```

(`captures.json` : même format que les cibles de veille, avec le nom `nous` et tes adresses locales ;
ajoute les mêmes écrans d'un concurrent pour une planche de comparaison.)

Puis **regarde** les captures (outil Read) et note-les avec la grille ci-dessous dans la PR. Le
relecteur (autre fournisseur) refait la notation indépendamment.

| Axe | 1 — à refaire | 3 — correct | 5 — remarquable |
| --- | --- | --- | --- |
| Hiérarchie | tout a le même poids | l'essentiel se trouve | l'œil va droit au but |
| Typographie | police système, une taille | échelle cohérente | caractère propre, chiffres impeccables |
| Couleur | gris uniforme ou criard | sobre et lisible | identité reconnaissable, sémantique claire |
| Densité | vide ou entassé | lisible | dense ET respirant, comme un outil pro |
| États | page blanche possible | états présents | états soignés et utiles |
| Mouvement | aucun ou gênant | retours d'action | vivant sans distraire |
| Signature | interchangeable | un détail propre | reconnaissable au premier coup d'œil |
| Face au meilleur concurrent | nettement en dessous | au niveau | au-dessus |

**Seuil :** aucun axe sous 3, et « Hiérarchie », « Typographie » et « Face au meilleur concurrent » à 4
au moins pour un écran clé (accueil, tableau de bord, fonction phare). Sinon : corrections, avec la
liste précise de ce qui manque.

## 4. Ce qu'on ne fait pas

- Copier l'interface d'un concurrent pixel pour pixel, reprendre ses illustrations ou ses textes.
- Empiler des effets (dégradés partout, verre dépoli, 3D) pour masquer une hiérarchie absente.
- Changer la direction artistique dans une PR de fonctionnalité : on la propose dans une tâche `design`.
