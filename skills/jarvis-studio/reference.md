# Jarvis Studio — référence du storyboard

Un storyboard est un fichier JSON. Les chemins d'images et de clips sont relatifs à ce fichier ;
`"$JARVIS_LIVRABLES/…"` désigne un fichier du dossier des livrables.

## Sommaire

- [Structure](#structure)
- [Marque](#marque)
- [Scène `titre`](#scène-titre)
- [Scène `capture`](#scène-capture)
- [Scène `points`](#scène-points)
- [Scène `chiffre`](#scène-chiffre)
- [Scène `fin`](#scène-fin)
- [Rythme et lisibilité](#rythme-et-lisibilité)

## Structure

```json
{ "format": "16:9", "marque": { … }, "scenes": [ { "type": "titre", "duree": 3, … }, … ] }
```

`format` (facultatif) : `16:9`, `9:16`, `1:1`, `4:5`. L'option `--format` de `rendre.cjs`
l'emporte. Types de scène : `titre`, `capture`, `points`, `chiffre`, `fin` (tout autre type est refusé). `duree` est en secondes (0,8 au minimum). Chaque scène apparaît, joue, puis s'efface
dans ses 0,4 dernières secondes ; la dernière reste à l'écran.

## Marque

| Champ | Rôle | Défaut |
| --- | --- | --- |
| `nom` | Affiché sur l'écran de fin s'il n'y a pas de logo | — |
| `accent` | Couleur de la marque (boutons, repères, sur-titres) | `#5B8CFF` |
| `fond` | Couleur de fond, sombre de préférence | `#0B0D12` |
| `texte` | Couleur du texte | `#F4F6FA` |
| `logo` | Image du logo (PNG ou SVG à fond transparent) | — |
| `police` | Police installée sur le poste | Inter, puis police du système |

Un fond clair fonctionne (`"fond": "#F6F7FB", "texte": "#0B0D12"`), mais vérifie le contraste
des sous-titres sur la planche-contact.

## Scène `titre`

Grand titre qui apparaît mot à mot. Pour l'accroche et les transitions.

| Champ | Rôle |
| --- | --- |
| `titre` | 2 à 6 mots |
| `sur_titre` | Petite ligne au-dessus, en capitales (facultatif) |
| `sous_titre` | Une phrase courte (facultatif) |

## Scène `capture`

Le produit dans un cadre de navigateur, avec un texte à côté (au-dessus en format vertical).

| Champ | Rôle |
| --- | --- |
| `image` | Capture d'écran (faite avec l'action `capture` d'`enregistrer.cjs`) |
| `video` | À la place de `image` : un film du produit (webm ou mp4), joué dans le cadre |
| `debut` | Avec `video` : instant de départ dans le film, en secondes |
| `url` | Adresse affichée dans la barre du navigateur |
| `titre`, `sous_titre`, `sur_titre` | Texte à côté du cadre. Sans titre, le cadre prend toute la place |
| `proportions` | `[largeur, hauteur]` de la zone visible (défaut `[16, 10]`, ou celles du film) |
| `zoom` | Avec `image` : `{"de": 1, "a": 1.12, "vers": [x, y], "depart": 0.6}`. `vers` est le point visé, en pourcentage de l'image. Un zoom lent vers l'élément dont on parle |
| `reperes` | Avec `image` : `[{"x": 17, "y": 27, "texte": "…", "a": 1.3}]`. Un anneau et une étiquette à `x`, `y` (pourcentage de l'image), apparus à `a` secondes après le début de la scène |

Les repères suivent le zoom. Deux repères par scène au plus : au-delà, plus rien n'est lu.
Pour placer un repère, rends une image (`--image`) et corrige les coordonnées à l'œil.

## Scène `points`

Un titre et une liste d'arguments qui arrivent l'un après l'autre.

| Champ | Rôle |
| --- | --- |
| `titre` | 2 à 5 mots |
| `points` | 2 à 4 arguments de 3 à 6 mots |
| `sur_titre` | Facultatif |

Prévois 1 seconde par argument, plus 1,5 seconde.

## Scène `chiffre`

Un grand nombre qui se compte, avec sa légende. Uniquement pour un chiffre vrai et vérifiable.

| Champ | Rôle |
| --- | --- |
| `valeur` | Le nombre (`12`, `4.8`) |
| `prefixe`, `suffixe` | `"×"`, `" %"`, `" h"`… |
| `libelle` | Ce que le chiffre mesure, en une ligne |

## Scène `fin`

Logo (ou nom), phrase de clôture, bouton et adresse.

| Champ | Rôle |
| --- | --- |
| `titre` | La phrase de clôture |
| `bouton` | L'action attendue, en 2 ou 3 mots |
| `url` | L'adresse, sans `https://` |

Garde-la au moins 3 secondes : c'est le seul plan que le spectateur doit pouvoir relire.

## Rythme et lisibilité

- Une personne lit environ 3 mots par seconde à l'écran. Durée d'un plan ≥ (nombre de mots ÷ 3) + 1,5 s.
- `rendre.cjs` avertit au-delà de 8 secondes pour un plan de texte et de 15 pour une capture. Le
  contrôle technique, lui, ne voit pas qu'une scène animée traîne : c'est à toi de le voir sur la
  planche-contact. Donne un `zoom` aux captures.
- Format vertical : les textes sont plus gros et les lignes plus courtes. Relis la planche-contact
  de chaque format, pas seulement du 16:9.
- Les 3 premières secondes décident si la vidéo est regardée : le bénéfice d'abord, le nom ensuite.
