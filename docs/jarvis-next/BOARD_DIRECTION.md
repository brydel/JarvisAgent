# Board — direction visuelle « Salle de rédaction »

Ce document décrit le système de design du Studio (Board, accueil, références, dialogues) : la direction, la palette, la typographie, les jetons et leurs règles d'usage. Il sert à quiconque écrit ou retouche une feuille de style du produit.

La source unique est `design/board-v2/tokens.json`. `npm run jetons` (dans `studio/board-v2`) en tire trois fichiers, à ne jamais modifier à la main :

| Fichier | Contenu |
| --- | --- |
| `studio/board-v2/src/styles/themes.css` | couleurs et ombres des deux thèmes, puis les synonymes |
| `studio/board-v2/src/styles/tokens.css` | typographie, espacement, hauteurs, rayons, icônes, mouvement, gabarit |
| `design/board-v2/planche.html` | planche de contrôle, à ouvrir depuis le dépôt après `npm ci` (`?theme=jour` pour le thème clair) |

`src/styles/jetons.test.ts` vérifie que ces fichiers sont à jour, contrôle le contraste AA dans les deux thèmes et garde les règles d'échelle décrites plus bas. `node scripts/jetons.mjs --usage` compte les emplois de chaque jeton.

## Direction

- **Produit.** Jarvis Studio est un poste de pilotage d'agents de code : sur un canevas (le Board) on pose notes, liens et fichiers, on les relie par des flèches à effet réel, on confie une mission à des rôles d'agents, et on relit avant tout envoi.
- **Caractère.** Posé, typographique, sourcé : tout ce qui est affiché dit qui l'a fait, avec quoi et quand.
- **Monde.** La salle de rédaction et l'imprimerie. Les surfaces restent grises (graphite à peine chaud). Le monde passe par l'encre, le vermillon de rubrique et les titres à empattements.
- **Moments.** La carte Mission, traitée comme l'article de une ; sur l'accueil, le plan de situation du Board réel (les vraies cartes à leur vraie place, les relations dans la couleur de leur type, la jauge de la mission). La richesse va là, le reste de l'interface se tait.
- **Signature.** La ligne de crédit : une ligne en mono discret qui dit qui, quoi, quand, précédée d'un court filet vermillon. Une seule signature, posée là où une provenance a du sens, nulle part ailleurs.

## Palette

Trois familles seulement dans le chrome : la rampe grise, l'encre, le vermillon. Les couleurs de sens (états, flèches) ne portent que du sens.

### Rampe

| Jeton | Nuit | Jour | Emploi |
| --- | --- | --- | --- |
| `bg-bar` | `#100F0F` | `#FBFAF8` | barre du haut, surface la plus profonde |
| `bg-app` | `#151514` | `#F6F5F2` | fond des pages |
| `bg-canvas` | `#131312` | `#F3F2EE` | fond du canevas |
| `surface-panel` | `#171716` | `#FBFAF8` | panneau latéral, pied de dialogue |
| `surface-card` | `#1B1A19` | `#FFFFFF` | carte, barre d'outils, note, mission |
| `surface-card-raised` | `#1F1E1D` | `#FFFFFF` | menu, dialogue, ce qui flotte |
| `surface-inset` | `#121211` | `#F1F0EC` | creux : puits, bloc de code |
| `surface-field` | `#121211` | `#FFFFFF` | champ de saisie |
| `surface-hover` | `#252423` | `#ECEAE5` | survol, ligne active, étiquette |
| `surface-more` | `#2D2C2A` | `#E6E4DE` | palier le plus haut, piste de jauge |

Filets : l'encre du thème en transparence, pour qu'un filet reste juste sur n'importe quel palier.

| Jeton | Nuit | Jour | Emploi |
| --- | --- | --- | --- |
| `border-subtle` | encre à 8 % | encre à 8 % | séparateur dans un bloc |
| `border-card` | encre à 10 % | encre à 12 % | contour d'une carte ou d'un panneau |
| `border-strong` | encre à 16 % | encre à 20 % | contour d'un contrôle (champ, bouton secondaire) |

Texte : trois rôles, pas davantage.

| Jeton | Nuit | Jour | Emploi |
| --- | --- | --- | --- |
| `text-primary` | `#EDEBE6` | `#1A1917` | titres, corps, valeurs |
| `text-secondary` | `#A8A59E` | `#55524C` | libellés, descriptions, icônes |
| `text-muted` | `#8F8C85` | `#6B6861` | méta, légendes, crédits (AA 4,5 sur page, carte et panneau) |

### Encre et accent

| Jeton | Nuit | Jour | Emploi |
| --- | --- | --- | --- |
| `encre` | `#EDEBE6` | `#1A1917` | bouton principal, sélection, progression, coche, trait du dessin |
| `encre-survol` | `#D9D6CF` | `#34322E` | survol du bouton principal |
| `sur-encre` | `#151514` | `#FFFFFF` | texte posé sur l'encre |
| `accent` | `#EE5A3A` | `#C2381B` | vermillon : filet de la ligne de crédit, étape en cours, guide d'alignement |
| `accent-texte` | `#F0704F` | `#B23216` | vermillon quand il sert de texte (AA 4,5) |
| `sur-accent` | `#1A0D08` | `#FFFFFF` | texte posé sur le vermillon |

Rôles nommés, à préférer dans une feuille neuve : `selection` et `focus` (l'encre), `credit` (le texte atténué) et `credit-filet` (le vermillon).

Règles :

- Une action principale par écran, en encre. Les autres boutons sont secondaires : `surface-card-raised`, filet `border-strong`, texte primaire.
- Le vermillon couvre quelques pour cent de l'écran, jamais un bouton ni une sélection : il est voisin du rouge d'erreur et du rose des flèches bloquantes.
- Sélection : anneau net de 2 px (`shadow-selection`), sans flou. Focus clavier : `outline: 2px solid var(--focus); outline-offset: 2px`.
- État actif : un palier de surface et un filet, pas de bord teinté.

### Couleurs de sens

| Sens | Remplissage | Texte | Fond |
| --- | --- | --- | --- |
| Positif | `success` | `text-success` | `success-bg` |
| Attention | `warning` | `text-warning` | — |
| Négatif | `danger` | `text-danger`, `text-danger-soft` sur `danger-bg` | `danger-bg` |

Les flèches gardent leurs couleurs de sens (`edge-inspire`, `edge-alimente`, `edge-utilise`, `edge-depend`, `edge-bloquante`, `edge-debloquee`, `edge-default`) : chacune atteint 3:1 sur le canevas et 4,5:1 sur son étiquette. Les teintes de carte (`teinte-*`) et d'adhésif (`adhesif-*`) sont des choix de l'utilisateur, pas du chrome.

### Ombres

Nuit : la profondeur vient des paliers de surface et des filets, aucune ombre sur les cartes (`shadow-card` est nulle). Jour : `shadow-card` est une ombre courte et neutre. `shadow-lift` est réservée à ce qui flotte au-dessus du canevas (menu, palette, dialogue), `shadow-adhesif` aux adhésifs. Aucune ombre colorée, aucune lueur, aucun flou d'arrière-plan.

### Interdits

Dégradé d'une teinte vers une autre, texte en dégradé, lueur, lavis radial, verre flouté, bordure néon, couleur écrite en dur dans une feuille ou un composant (le test l'interdit : jetons seulement).

## Typographie

| Famille | Jeton | Emploi |
| --- | --- | --- |
| Instrument Sans | `--font-sans` | toute l'interface |
| Newsreader | `--font-serif` | grands titres seulement, à partir de 28 px : titre d'accueil, titre de page, titre de la carte Mission. Jamais un libellé ni un bouton |
| IBM Plex Mono | `--font-mono` | chiffres, durées, comptes, provenance, touches, code |

Échelle de l'interface (pixels écran), taille et interligne par paire :

| Jetons | Valeur | Emploi |
| --- | --- | --- |
| `--fs-meta` / `--lh-meta` | 12 / 16 | méta, comptes, crédits, touches |
| `--fs-sm` / `--lh-sm` | 13 / 20 | texte secondaire, légendes |
| `--fs-base` / `--lh-base` | 14 / 20 | corps, navigation, boutons |
| `--fs-lg` / `--lh-lg` | 16 / 24 | mot-symbole, titre de section |
| `--fs-xl` / `--lh-xl` | 18 / 24 | titre de carte ou de panneau |
| `--fs-2xl` / `--lh-2xl` | 22 / 28 | titre de dialogue |
| `--fs-figure` / `--lh-figure` | 28 / 32 | chiffre de carte, en mono |
| `--fs-title`, `--fs-title-lg` / `--lh-title` | 28, 36 / 1,15 | titre de page, en Newsreader (26 et 30 sous 760 px) |
| `--fs-display` / `--lh-display` | 60 / 1,05 | titre d'accueil, avec `--tracking-display` (40 sous 760 px) |

Les cartes du Board sont dessinées en unités du canevas (0,8 px écran au zoom de référence) et ont leur propre échelle : `--fsc-meta` 15, `--fsc-sm` 16, `--fsc-base` 18, `--fsc-lg` 20, `--fsc-xl` 24, `--fsc-title` 30.

Règles :

- Rien sous 12 px à l'écran (11 px au plus petit en mobile) ; sur le canevas, rien sous 15 unités.
- Deux graisses : `--fw-regular` (400) et `--fw-medium` (500). `--fw-strong` (600) pour le mot-symbole et la lettre de raccourci de la barre d'outils, rien d'autre. La hiérarchie vient de la taille et du rôle de texte.
- Casse de phrase partout, pas de capitales espacées, pas d'italique d'emphase.
- Interlettrage 0 ; seul le titre d'accueil prend `--tracking-display`.
- Chiffres : `font-variant-numeric: tabular-nums`, un seul format par écran.
- Paragraphe : `max-width: var(--measure)`.

### La ligne de crédit

`font: var(--type-credit)` (Plex Mono 400, 12 / 16), couleur `var(--credit)`, chiffres tabulaires, précédée d'un filet `var(--credit-filet)` de 12 px sur 2 px, à 8 px du texte. Elle dit qui, quoi, quand, sans point final : « Mission · 4 rôles d'agents · en cours depuis 12 min ». Elle se pose sur une provenance (carte, mission, référence, chapeau de page), pas comme décoration.

### Licences des polices

Les trois familles sont sous **SIL Open Font License 1.1**, embarquées par les paquets `@fontsource` en version exacte et servies depuis `/v2/assets` : aucune police distante (la CSP l'interdit), aucune licence payante. Le fichier `LICENSE` de chaque paquet porte le texte de la licence et les droits d'auteur.

| Paquet | Version | Droits d'auteur | Fichiers embarqués |
| --- | --- | --- | --- |
| `@fontsource-variable/instrument-sans` | 5.3.0 | The Instrument Sans Project Authors | axe de graisse 400 à 700, latin et latin étendu |
| `@fontsource-variable/newsreader` | 5.3.0 | The Newsreader Project Authors | axe de taille optique, graisses 200 à 800, romain seulement |
| `@fontsource/ibm-plex-mono` | 5.3.0 | IBM Corp. | 400 et 500, latin |

Les icônes viennent de `lucide-react` (licence ISC).

## Espacement

Grille de 4 px : `--space-N` vaut N × 4 px (`--space-1` 4, `--space-2` 8, `--space-3` 12, `--space-4` 16, `--space-5` 20, `--space-6` 24, `--space-8` 32, `--space-10` 40, `--space-12` 48, `--space-16` 64, `--space-20` 80, `--space-24` 96). `--space-half` (2 px) ne sert qu'à un ajustement dans un petit contrôle.

| Jeton | Valeur | Emploi |
| --- | --- | --- |
| `--pad-control` | 12 | marge latérale d'un contrôle |
| `--pad-panel` | 16 | panneau, barre latérale |
| `--pad-card` | 20 | carte |
| `--pad-page` | 24 (16 sous 760 px) | bord de page |
| `--gap-row` | 4 | entre deux lignes d'une liste |
| `--gap-group` | 16 | entre deux groupes |
| `--gap-section` | 32 | entre deux sections |
| `--control-h-sm`, `--control-h`, `--control-h-lg` | 32, 36, 44 | hauteur d'un contrôle |
| `--row-h-compact`, `--row-h` | 32, 36 | hauteur d'une ligne de liste |
| `--touch-min` | 44 | cible minimale au doigt |

Règles : même chose, même taille ; l'espace dans un groupe est plus petit que l'espace entre deux groupes ; une étiquette de section est plus près de ses éléments que de la section d'avant ; aucune valeur isolée hors grille.

## Rayons

| Jeton | Valeur | Emploi |
| --- | --- | --- |
| `--radius-2xs` | 4 | plancher d'un élément imbriqué, touche |
| `--radius-xs` | 6 | étiquette, petit bouton |
| `--radius-sm` | 8 | ligne, champ, bouton |
| `--radius-card` | 12 | carte |
| `--radius-panel` | 16 | panneau, dialogue |
| `--radius-pill` | 999 | point d'état, avatar, interrupteur, rien d'autre |

Rayon imbriqué : rayon du parent moins l'écart qui les sépare, jamais sous 4. Un bouton à 4 px du bord d'une carte prend `calc(var(--radius-card) - var(--space-1))`, soit 8 ; une carte à 4 px du bord d'un panneau prend 12.

## Icônes

Un seul jeu, lucide. Taille 16 et trait 1,5 par défaut, posés une fois par `LucideProvider` dans `src/main.tsx` (valeurs de `src/styles/systeme.ts`, miroir de `--icon-size` et `--icon-stroke`). Une icône écrite sans `size` ni `strokeWidth` les reçoit ; ne passer `size` que pour une illustration d'état vide. Une icône prend la couleur de son rôle de texte, jamais la sienne, et se tient à `--icon-gap` (8 px) de son libellé.

## Mouvement

Une seule courbe, `--ease-standard` (`cubic-bezier(0.22, 1, 0.36, 1)`).

| Jeton | Valeur | Emploi |
| --- | --- | --- |
| `--dur-lift` | 120 ms | prise d'une carte |
| `--dur-hover` | 140 ms | survol, appui, bascule |
| `--dur-appear` | 180 ms | menu, infobulle |
| `--dur-panel` | 220 ms | panneau, dialogue |
| `--dur-enter` | 320 ms | entrée d'un contenu, une seule par chargement |
| `--stagger` | 40 ms | décalage entre six éléments au plus |
| `--rise` | 8 px | montée à l'entrée |
| `--press-scale` | 0,98 | échelle à l'appui |

Règles :

- Transiter seulement `color`, `background-color`, `border-color`, `opacity` et `transform`, nommés. `transition: all` est refusé par le test, écrit ou sous-entendu.
- Ne jamais animer largeur, hauteur, position ou marge.
- Aucune boucle hors indicateur d'attente ; pas de rebond, pas de soulèvement de carte au survol.
- Sous `prefers-reduced-motion`, toutes les durées valent 0 et `tokens.css` coupe aussi les animations écrites sans jeton.

## Marque

Un anneau ouvert et son point, à plat, d'une seule couleur : l'encre du thème. Le composant `src/components/Marque.tsx` suit `currentColor` ; `public/jarvis-mark.svg` (favicon) suit le thème du système. Le mot-symbole « Jarvis Studio » est en Instrument Sans, 16 px, graisse 600. Ni dégradé, ni lueur, ni tuile.

## Synonymes

`tokens.json` porte sous `synonymes.roles` les noms d'usage de la direction (`selection`, `focus`, `credit`, `credit-filet`, `statut-neutre`) : chacun renvoie à un jeton de la palette. `synonymes.herites` est vide : les anciens noms (`brand-indigo`, `text-p2`, `surface-menu`…) ont été remplacés par leur cible dans toutes les feuilles à la réunion des zones. Un nom n'y revient que le temps d'une migration.

## Crédit

La méthode de relecture (direction, puis neuf passes : espacement, couleur, icônes, textes, typographie, mise en page, détails, visuels, mouvement) est celle du skill unslop de Damir Sokolovsky (@heydamir), sous licence CC BY 4.0.
