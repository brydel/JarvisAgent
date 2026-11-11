# Board « tableau blanc » — commandes, outils, cartes intelligentes, modes d'affichage

Lot `feat/board-canevas`, posé sur `feat/board-fondations` (couche de données : store, écritures optimistes versionnées,
flux — voir `BOARD_FONDATIONS.md`). Objet : faire du Board un tableau blanc utilisable, sans changer de moteur
(React Flow 12, MIT) et sans dépense : toutes les briques ajoutées sont sous licence permissive.

Tout ce qui suit est exécuté et testé sur ce poste ; les chiffres sont ceux relevés, les manques sont listés à la fin.

## 1. Registre de commandes unique — `studio/board-v2/src/commandes/`

Une commande = `{ id, libellé, icône, raccourci, catégorie, niveau, disponible(contexte), exécuter(contexte), annuler? }`
(`types.ts`). **109 commandes** sont déclarées une fois (`catalogue/*.ts`, assemblées par `index.ts`) :

| Fichier | Contenu |
|---|---|
| `catalogue/outils.ts` | les 13 outils et leur touche |
| `catalogue/edition.ts` | annuler, rétablir, copier, couper, coller, dupliquer, supprimer, tout sélectionner, verrouiller, devant / derrière, grouper, encadrer |
| `catalogue/disposition.ts` | aligner (6), répartir (2) |
| `catalogue/cartes.ts` | actions par type de carte, priorité, couleur, épaisseur, type de relation, export PNG |
| `catalogue/affichage.ts` | thèmes, plein écran, zen, concentration, présentation, minicarte, grille, guides, zoom |
| `catalogue/ajout.ts` | note, lien, fichiers, dossier, presse-papiers, mission |
| `catalogue/navigation.ts` | aller à l'objet voisin (Alt+flèches) |

Tout passe par `Registre.executer(id, contexte, origine)` :

- **boutons** : barre d'outils (`outils/BarreModes.tsx`), barre d'ajout et seconde rangée (`components/Coque.tsx`), menu « … » des
  cartes (`nodes/CardShell.tsx`), barre de présentation — via `BoutonCommande` ou `executer` ;
- **raccourcis** : un seul écouteur (`board/useClavier.ts`) demande au registre « quelle commande pour cette touche, dans ce
  contexte ? ». Un raccourci partagé (Échap, Entrée) va à la première commande disponible ; un test vérifie que ce sont les
  seuls partages ;
- **menu contextuel** (`MenuContextuel.tsx`, clic droit ou Maj+F10) et **barre flottante** (`BarreFlottante.tsx`) : les
  commandes proposées à cet emplacement et disponibles pour la cible ;
- **palette Ctrl/⌘+K** (`Palette.tsx`) : recherche floue sans accents (`recherche.ts`), « Récents » en tête, raccourci
  affiché, navigation au clavier, rôles ARIA (`combobox` / `listbox`).

Niveaux : `lecture`, `ecriture`, `sensible`. Une commande sensible, ou qui le déclare pour ce contexte (supprimer dix objets
ou plus), demande confirmation ; sans réponse explicite, refus.

**Journal d'usage local** (`journal.ts`, `localStorage`) : par commande, nombre d'exécutions, chemin (bouton, raccourci,
palette, menu, barre flottante), nombre d'annulations, dernière exécution. `exporter()` rend une structure versionnée
`{ version: 1, depuis, genere, commandes: [...] }` ; la commande « Exporter mon journal d'usage » la télécharge. **Rien n'est
envoyé au serveur aujourd'hui** ; le journal ne contient que des identifiants de commandes, aucun contenu de carte.

Ce qui ne passe pas par le registre : les filtres de la seconde rangée (état d'affichage, pas une action), la mise en forme
dans une note (gras, italique), et les formulaires du panneau droit (approuver, commenter, réglages de Jarvis).

À noter : dans le Board, **Ctrl+K ouvre la palette** ; la recherche de cartes, qui avait ce raccourci, répond à `/` et `Ctrl+F`.

Preuves : `registre.test.ts` (17 tests), `catalogue.test.ts` (18 tests : le catalogue réel exécuté contre un double des
services), `tests/e2e/canevas.spec.ts` (« palette Ctrl+K… », « menu contextuel et barre flottante… »).

## 2. Annuler / rétablir — `commandes/historique.ts`

Pile de commandes inverses. Chaque service d'écriture (`board/useServices.ts`) dépose `{ annuler, refaire }` dont les deux
faces passent par la file d'écritures optimistes existante (`donnees/ecritures.ts`) : versions envoyées, conflit 409 géré.

- l'entrée est posée **au moment du geste** (Ctrl+Z fonctionne avant la réponse du serveur) et retirée si le serveur refuse ;
- **une opération à la fois** : dix Ctrl+Z rapides s'exécutent dans l'ordre ;
- **gestes groupés** : dupliquer cinq cartes, « tâche inspirée » (note + relation), « grouper » = un seul pas ;
- **annulation en conflit** : si la carte a changé ailleurs, l'annulation est refusée (rien n'est écrasé), l'entrée est
  abandonnée, un message le dit, et les entrées suivantes restent annulables ;
- supprimer puis annuler restaure la carte **et ses relations** (inchangé, re-testé) ;
- l'annulation est comptée dans le journal de la commande d'origine.

L'inverse d'une modification est lu dans le store au moment du geste (`inverseDe`) : plus besoin de l'écrire à la main à
chaque appel, ce qui a retiré une source d'erreurs de `Board.tsx`.

Preuves : `historique.test.ts` (9 tests, dont trois contre la vraie file d'écritures et un faux serveur à versions),
`board.spec.ts` (« supprimer puis annuler »), `canevas.spec.ts` (formes, trait effacé puis restauré, cadre et son contenu
remis en place par un seul Ctrl+Z).

## 3. Outils de tableau blanc

Barre à modes en haut du canevas, une touche par outil :

| Touche | Outil | Touche | Outil |
|---|---|---|---|
| V | sélection | R / O / D | rectangle / ellipse / losange |
| H | main | A | flèche |
| L | lasso | P | crayon |
| N | note adhésive | S | surligneur |
| T | texte | E | gomme |
| F | cadre | Échap | retour à la sélection |

- **Formes** (`nodes/Tableau.tsx`) : SVG dessiné à la taille réelle du nœud (trait non déformé), redimensionnables, couleur
  et épaisseur ; texte centré éditable.
- **Texte et notes adhésives** : édités dans une **surcouche non transformée** (`outils/EditeurTexte.tsx`). Le canevas est mis
  à l'échelle par `transform` ; un champ éditable placé dedans a un curseur flou. Le `<textarea>` vit hors du calque, sa
  boîte et sa taille de police sont calculées à l'écran. Tout ce qui est saisi ou collé reste du texte (testé avec
  `<img onerror>` et `javascript:`).
- **Dessin libre** (`outils/CoucheOutils.tsx`, `outils/dessin.ts`) : `setPointerCapture`, `getCoalescedEvents`, pression du
  stylet, `touch-action: none` ; aperçu mis à jour sans React ; au relâchement le geste est simplifié
  (Ramer-Douglas-Peucker), borné à 700 points, enregistré en coordonnées relatives à sa boîte ; le chemin SVG
  (perfect-freehand) est calculé une fois par trait et mis en cache. Le trait reste affiché jusqu'à la confirmation du
  serveur (pas de clignotement).
- **Gomme** : efface traits, formes, notes adhésives, textes libres et flèches — jamais une carte ni un cadre. Test fin sur
  les segments d'un trait.
- **Lasso** : sélectionne les objets dont le centre est entouré.
- **Cadres** : un cadre glissé emporte ce dont le centre est dedans ; une seule écriture, un seul Ctrl+Z. Seuls son titre et
  son liseré se saisissent : l'intérieur laisse passer les clics.
- **Guides magnétiques** (`outils/espace.ts::accrocher`, `board/useGlisser.ts`) : accroche sur les bords et les centres des
  voisins à 6 px écran, lignes affichées pendant le glisser. Désactivables ; cèdent la place à la grille quand elle est active.
- **Aligner / répartir** (`outils/disposition.ts`), **copier / couper / coller / dupliquer** (copie fidèle des objets, y compris
  après suppression de l'original), **zoom de 5 % à 800 %**, **minicarte** (affichable / masquable).
- **Index spatial** (`outils/espace.ts`, rbush) : un index par instantané du store, partagé par le lasso, la gomme, les
  guides, les cadres et l'ancrage des flèches.

Choix assumé : avec l'outil de sélection, glisser sur le fond **déplace la vue** (comportement existant, conservé) ; la
sélection par zone se fait au lasso (L) ou avec Maj+glisser.

### Modèle côté serveur

Six types ajoutés à `missions.TYPES_BOARD` : `adhesif`, `texte_libre`, `forme`, `trait`, `cadre`, `fleche`. Leur apparence vit
dans `meta`, **bornée** par `lib/jarvis/board_tableau.py` à la création et à chaque modification :

- couleurs = noms de jetons (`indigo`, `jaune`…), jamais une couleur CSS libre ;
- forme ∈ rectangle, ellipse, losange ; épaisseur 0–64 ; taille de police 8–400 ; libellé ≤ 200 caractères ;
- trait : 2 à 1 500 points `(x, y, pression)`, nombres finis ≤ 100 000, boîte d'origine obligatoire — jamais un chemin SVG libre ;
- flèche : deux extrémités normalisées (0–1) et, au besoin, deux ancres `{ id, nx, ny }` normalisées sur l'objet visé ;
- la borne générale de `meta` (20 000 caractères) s'applique toujours ; mêmes contrôles d'API (session, en-tête) qu'avant.

Ces objets ne sont **jamais** envoyés à un modèle (ni analyse, ni contextualisation). Versions, événements, deltas,
suppression douce et conflits : comme pour les cartes, par la même couche de données.

Preuves : `tests/test_board_tableau.py` (12 tests, dont 6 rejoués sur PostgreSQL réel), `outils/outils.test.ts` (26 tests),
`canevas.spec.ts` (7 scénarios d'outils sur le Board réel).

## 4. Cartes intelligentes

- **Actions par type**, déclarées dans le registre (`catalogue/cartes.ts`) et proposées dans la barre flottante et le menu
  contextuel :
  - toute carte : ouvrir les détails, relier à…, priorité (touches 1, 2, 3, 0), dupliquer, verrouiller, exporter ;
  - lien, capture, image, PDF, média, note : **« Créer une tâche inspirée de ceci »** — pose une note « Tâche : … » reliée
    à sa source par une relation « Inspire ». Rien n'est confié à un agent (le message le dit) ;
  - toute carte : **« Trouver des cartes proches »** — proximité de **vocabulaire** (titre, description, étiquettes, texte,
    site), calculée dans le navigateur, **sans modèle** : c'est dit tel quel à l'utilisateur ;
  - livrable (carte portant des artefacts, ou `meta.livrable_de`) : **« Faire relire »** — pose `meta.relecture`
    `{ demandee, par }` et un commentaire. **Aucun agent n'est lancé** et rien côté serveur ne consomme encore cette demande ;
  - cadre : se concentrer, présenter, exporter le cadre.
- **État** (`cartes/etat.ts`, pastilles au-dessus de la carte), tiré uniquement des données :
  - *attend ta décision* : approbations en attente sur la mission, plan `en_attente`, propositions de Jarvis sans réponse,
    relecture demandée ;
  - *bloquée* : tâche de la mission en échec / annulée / expirée, tâche sans exécutant, statut de travail déclaré par le chef ;
  - *analyse périmée* : la note a été modifiée (`meta.historique[0].ts`) après le lancement de l'analyse dont elle affiche
    le résumé (`mission.cree`).
- **Provenance** (`cartes/Provenance.tsx`, sous la carte, visible au survol / à la sélection / au focus) : auteur humain ou
  agent, modèle ou fournisseur du dernier livrable s'il est connu, date, version, nombre de sources liées. Une carte « créée
  par toi, jamais modifiée, sans source » n'affiche rien.

Preuves : `catalogue.test.ts` (5 tests de cartes, 4 tests d'état et de provenance), `canevas.spec.ts` (« menu contextuel et
barre flottante… »).

## 5. Modes d'affichage

- **Thèmes nuit / jour / automatique** : `design/board-v2/tokens.json` porte maintenant `themes.nuit` et `themes.jour`
  (162 jetons chacun). `scripts/jetons.mjs` génère `src/styles/themes.css` ; `app.css` et la nouvelle `tableau.css` n'écrivent
  **plus aucune couleur en dur** (129 littéraux remplacés dans `app.css`, valeurs du thème nuit conservées). Un test vérifie :
  miroir exact JSON → CSS, mêmes jetons dans les deux thèmes, **contraste AA** sur 82 paires texte / fond par thème
  (4,5:1 pour le texte, 3:1 pour traits et grands textes), aucune couleur en dur dans les deux feuilles.
  Le test a trouvé un vrai défaut d'origine : blanc sur le haut du dégradé de marque à 4,15:1 ; corrigé (`#5165FB`, 4,56:1).
- **Plein écran** (API Fullscreen, Maj+F), **zen** (Ctrl+. : barres et panneau masqués, outils atténués), **concentration**
  sur un cadre (Maj+C : le reste s'estompe), **présentation** (Maj+P : les cadres deviennent des diapositives dans l'ordre de
  lecture, flèches / Espace / Entrée, Échap ; aucune écriture possible pendant la présentation).
- **Préférences mémorisées** (`etat/ui.ts`, `localStorage`) : thème, minicarte, grille, guides, couleur et épaisseur du tracé.
- **`prefers-reduced-motion`** : durées des jetons à 0, animations de la palette et de la barre flottante coupées,
  déplacements de vue instantanés.

Limite : le thème jour couvre le Board (canevas, cartes, barres, panneau, palette, menus). Les dialogues « Réseau des
agents », « Intégrations », « Missions outillées » et les autres pages du produit gardent leur habillage sombre.

## 6. Performance

- `onlyRenderVisibleElements` (au-delà de 80 objets, inchangé) ;
- **niveau de détail** (`board/detail.ts`) : sous 35 % une carte devient un rectangle titré (médias, lecteurs, iframes
  démontés) ; sous 12 % un simple bloc de couleur, sans poignée, et les relations ne sont plus tracées ;
- le niveau est calculé **une fois** dans le canevas et distribué par contexte React : les objets n'ont plus d'abonnement
  au store de React Flow pour cela ;
- **aucun composant ne s'abonne au tableau des nœuds** ; les surcouches s'abonnent à la transformation, à un booléen ou à
  un entier, et seulement quand elles sont montées (barre flottante, éditeur de texte) ;
- `Board.tsx` ne se re-rend plus pendant un glisser : l'état des nœuds vit dans `board/Canevas.tsx` ;
- index spatial rbush : 1 000 requêtes de zone sur 5 000 objets en moins de 250 ms (seuil large du test ; quelques
  millisecondes en pratique).

### Mesures (5 009 objets)

`JARVIS_PERF_CHARGE=5000 npx playwright test perf-charge` — mode démo `?charge=5000` (le même jeu de cartes mixtes avant et
après), Chromium 156 de Playwright **sans GPU** sous WSL2, fenêtre 1672 × 941, durée de chaque image relevée par
`requestAnimationFrame` pendant des gestes réels (panoramique au bouton du milieu, 90 déplacements ; 24 crans de molette).
Avant : une passe, sur `e564d7d`. Après : trois passes à la suite, poste au repos, sur le build livré. Données brutes :
`docs/jarvis-next/mesures/board-canevas-perf.json`.

| Vue | Avant (1 passe) | Après (3 passes) |
|---|---|---|
| Travail, zoom 80 %, 11 objets rendus — panoramique | 60 ips, p95 16,8 ms | 59,4 / 59,4 / 59,2 ips, p95 16,7–16,8 ms |
| Travail, zoom 80 % — zoom molette | 60 ips | 60 / 60 / 60 ips |
| Zoom 15 % (l'ancien minimum), ≈ 230 objets rendus — panoramique | 58,6 ips, geste 4 844 ms | 59,3 / 59,8 / 60 ips, geste 4 528–4 581 ms |
| Zoom 15 % — zoom molette | 60 ips | 58,3 / 58,2 / 58,7 ips |
| **Vue d'ensemble, zoom 5 %, 1 989 objets rendus** — panoramique | impossible (zoom minimal 15 %) | 53,5 / 52,7 / 52,1 ips, p95 33,3 ms, max 33,5 ms, aucune image > 50 ms |
| Vue d'ensemble, zoom 5 % — zoom molette | impossible | 55,6 / 55,5 / 57,1 ips, max 50 ms |
| Chargement jusqu'au premier objet | 2,8 s | 2,7 / 2,6 / 2,6 s |

Lecture honnête :

- aux échelles qui existaient déjà, **rien ne change de façon mesurable** : le test plafonne à 60 images/s et le Board y
  était déjà. Le gain du lot est ailleurs : on peut maintenant dézoomer jusqu'à voir tout le Board (2 000 objets à l'écran),
  et il reste au-dessus de 50 images/s en panoramique sans GPU ;
- **la mesure est bruitée** : la même version a donné 54,7 ips à 5 % dans une passe isolée, et 45,9 ips dans une passe
  lancée juste après la suite Playwright complète. Une version intermédiaire (niveau de détail lu par chaque objet dans le
  store, une poignée par bloc) avait donné 46,5 ips en une seule passe : le gain du passage par contexte est plausible
  mais **non démontré**, l'écart étant de l'ordre du bruit ;
- **non mesuré** : un vrai navigateur avec GPU, un écran tactile ou un stylet, le thème jour, un Board réel de 5 000
  objets servi par l'API (la mesure est en mode démo, données en mémoire), un Board riche en traits (`?tableau=1` existe pour
  cela, non mesuré), le glisser d'un objet à 5 %.

## 7. Flèches et relations

- **Relations entre cartes** (`edges/RelationEdge.tsx`) : l'extrémité s'arrête sur le **périmètre réel** d'une forme
  (ellipse, losange), plus sur sa boîte ; **type** (simple, inspire, alimente, utilisé par, dépend de) choisi au menu
  contextuel, annulable, avec un rendu distinct par la couleur **et** le tracé (plein, pointillé, tirets, tiret-point) ;
  étiquette éditable par double-clic (existant).
- **Flèche libre** (`nodes/Fleche.tsx`, `outils/fleche.ts`) : tirée d'un point à un autre ; chaque extrémité est libre ou
  **ancrée** à un objet par une position normalisée sur sa boîte — elle suit l'objet quand il bouge ou change de taille,
  sans réécrire la flèche ; les extrémités se déplacent à la main quand la flèche est sélectionnée ; libellé éditable.
- Tirer une flèche **d'une carte à une autre** crée une relation (typée, nommable), pas un dessin.

Les types de relation n'ont **aucun effet métier** dans ce lot (ni blocage, ni relais de livrable) : seule l'interface est
prête. Les ancres normalisées concernent les flèches libres ; les relations entre cartes restent « du bord le plus proche ».

## 8. Export PNG — `board/exportPng.ts`

Sélection ou cadre (Ctrl+Maj+E, menu, barre flottante), échelle 2 bornée à 4 096 px, détail complet forcé pendant la
capture, vue remise en place ensuite. Iframes et vidéos sont remplacées le temps de la capture par un substitut statique
(vignette de la vidéo si elle vient du Board, sinon un bloc étiqueté). Testé : fichier téléchargé, signature PNG, dimensions
exactes (576 × 416 pour une forme de 240 × 160). Non testé : un export contenant réellement une iframe ou une vidéo.

## Qualité de code

- `Board.tsx` : **710 → 275 lignes**. Les interactions sont dans `board/` (`Canevas`, `useGlisser`, `useServices`,
  `useIngestion`, `useClavier`, `noeuds`, `detail`, `exportPng`), les outils dans `outils/`, les commandes dans `commandes/`.
- TypeScript strict, aucun `any`, aucun `innerHTML` ; `textContent` pour les substituts d'export.
- Accessibilité : barres en `role="toolbar"` avec flèches ← →, boutons nommés et `aria-pressed`, palette et menus au clavier,
  objets focalisables et nommés, focus visible, Alt+flèches pour aller à l'objet voisin, Maj+F10 pour le menu contextuel.

## Dépendances ajoutées (licence lue dans leur `package.json` et leur fichier `LICENSE`)

| Paquet | Version | Licence |
|---|---|---|
| perfect-freehand | 1.2.3 | MIT |
| rbush | 4.0.1 | MIT |
| quickselect (dépendance de rbush) | 3.0.0 | ISC |
| modern-screenshot | 4.7.0 | MIT |
| @types/rbush (développement) | 4.0.0 | MIT |

Ni tldraw, ni code des exemples « React Flow Pro » : lasso, gomme, guides, annuler / rétablir, copier / coller, formes et
dessin libre sont écrits ici sur l'API MIT.

## Captures

Produites par `canevas.spec.ts` dans `reports/board-v2/captures/` et copiées dans `docs/jarvis-next/captures/board-canevas/` :
`theme-nuit.png`, `theme-jour.png` (Board démo), `tableau-blanc-nuit.png`, `tableau-blanc-jour.png` (un tableau blanc réel,
enregistré par l'API, en mode zen), `mode-presentation.png`, `palette-commandes.png`, `export-selection.png` (le PNG exporté).

Les quatre captures de référence du Board démo (`tests/e2e/__captures__/board.spec.ts/`) ont été **régénérées
volontairement** : barre d'outils en haut du canevas, barre flottante au-dessus de la carte sélectionnée, pastille d'état
sur la carte mission, deux boutons de plus dans la seconde rangée, raccourci `/` dans la recherche.

## Note de design (grille de `skills/jarvis-design`)

Notée sur les captures jour, nuit, palette et présentation.

| Axe | Note | Pourquoi |
|---|---|---|
| Hiérarchie | 4 | la carte mission reste le foyer ; la barre d'outils recouvre le haut des cartes à l'ouverture de la démo |
| Typographie | 4 | Inter, chiffres tabulaires, échelle tenue ; les lettres-raccourcis de la barre d'outils sont très petites |
| Couleur | 4 | jetons, deux thèmes, AA vérifié ; le thème jour est neuf et s'arrête au Board |
| Densité | 4 | dense et lisible ; seconde rangée serrée en mode réel à 1672 px |
| États | 4 | vide, erreur, conflits, états de carte, commandes indisponibles ; pas de squelette de chargement du canevas |
| Mouvement | 3 | retours d'action sobres, mouvement réduit respecté ; rien de propre aux outils (pose d'une note, trait fini) |
| Signature | 4 | carte mission lumineuse et relations typées ; les objets de tableau blanc sont génériques |
| Face au meilleur concurrent | 3 | au niveau sur les bases, en dessous de Miro et tldraw sur l'étendue (voir limites) |

**Le seuil de la grille n'est pas atteint** : il demande 4 sur « Face au meilleur concurrent » pour un écran clé. Ce lot
pose les bases d'un tableau blanc ; il n'en fait pas encore l'égal des meilleurs.

## Tests exécutés

Sur ce poste (WSL2, Python 3.14, Node 22, PostgreSQL local), sur l'état final de la branche et le build livré :

| Suite | Commande | Résultat |
|---|---|---|
| Python | `python3 -m unittest discover -s tests` | 859 tests, 0 échec, 0 erreur, 5 ignorés (841 au départ ; + 12 dans `test_board_tableau.py`, + 6 rejoués sur PostgreSQL) |
| Front, unitaires | `npm test` | 139 tests, 9 fichiers, tous verts (61 au départ) |
| Front, types et build | `npm run build` | sans erreur ; build régénéré dans `lib/jarvis/studio_v2/` |
| Front, Playwright | `npx playwright test` | 66 tests : 65 verts, 1 ignoré (`perf-charge`, lancé à la demande), 0 rouge (50 au départ) |
| Mesure de charge | `JARVIS_PERF_CHARGE=5000 npx playwright test perf-charge` | vert, 4 passes « après » (voir Mesures) |
| Shell | `bash -n install.sh bin/jarvis`, `bin/jarvis help` | sans erreur |

Précisions :

- les 16 tests Playwright ajoutés sont dans `tests/e2e/canevas.spec.ts` (15) et `tests/e2e/perf-charge.spec.ts` (1) ;
- `tests/test_controle_pg.py` utilise maintenant une base jetable **unique par copie de travail**
  (`jarvis_<empreinte du chemin>_test`, surchargeable par `JARVIS_TEST_PG_BASE`), supprimée à la fin du module et à la sortie
  du processus : deux copies de travail peuvent tester en même temps ;
- Playwright a tourné sur le port 7763 (`JARVIS_E2E_PORT`) ;
- `shellcheck` n'est pas installé sur ce poste : non exécuté ;
- non exécuté : essai sur l'installation en service, sur un vrai appareil tactile, dans Firefox ou Safari (Playwright ne
  lance ici que Chromium).

## Limites connues et suite recommandée

Non fait, ou fait à moitié :

- **pas de rotation**, pas de connecteurs coudés, pas de courbe réglable, pas de texte riche (gras, listes) dans les
  objets de tableau blanc, pas de recadrage d'image, pas de bibliothèque de gabarits ;
- **pas de collaboration visible** (curseurs, sélections des autres) : le flux et les versions gèrent les conflits, pas la présence ;
- la sélection par zone demande le lasso ou Maj+glisser (glisser sur le fond déplace la vue) ;
- répartition : horizontale et verticale seulement ; pas de « même taille », pas de grille automatique ;
- le pied « provenance » ne connaît le modèle que s'il figure dans les artefacts ou dans `meta` ; le serveur n'enregistre
  pas encore de source par carte ;
- « faire relire » et les types de relation n'ont aucun effet côté serveur (lot ultérieur) ;
- « cartes proches » est un calcul de vocabulaire local, pas une recherche sémantique ;
- le journal d'usage reste sur le poste : l'envoi au serveur et l'apprentissage des préférences restent à faire ;
- les formulaires du panneau droit et les filtres ne passent pas par le registre ;
- le thème jour ne couvre pas les dialogues hors Board ni les autres pages ;
- export PNG : non essayé avec de vraies iframes ou vidéos, ni sur un très grand cadre ;
- tactile et stylet : le code suit les événements pointeur (pression, capture, `touch-action`), mais **aucun essai sur un
  vrai appareil** ; le pincement pour zoomer pendant qu'un outil de dessin est actif n'est pas géré ;
- mobile (390 px) : la barre d'outils défile sur une rangée ; le tableau blanc n'y a pas été travaillé au-delà ;
- Studio V1 (`/`) affiche les nouveaux types comme des cartes génériques ;
- performance : mesures sans GPU, bruitées ; un Board de plusieurs milliers de **traits** n'a pas été mesuré ;
- navigateurs : seul Chromium a été essayé (`field-sizing` pour le texte libre et `color-mix` y sont pris en charge ;
  Firefox et Safari non vérifiés).

Suite recommandée, dans l'ordre : (1) essai réel sur tablette avec stylet et correction de ce qu'il révèle ; (2) présence
et curseurs par le flux existant ; (3) effets métier des relations et de la relecture côté serveur ; (4) envoi du journal
d'usage et premières préférences apprises (ordre de la palette, outils épinglés) ; (5) rotation, connecteurs coudés, texte
riche ; (6) thème jour pour le reste du produit.
