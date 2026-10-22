# Contrat visuel — Jarvis Board V2

Référence obligatoire : `design/references/JARVIS_BOARD_V2_REFERENCE.png` (1672 × 941). Capture de contrôle :
Chromium, viewport 1672 × 941, deviceScaleFactor 1, Inter auto-hébergée chargée, animations figées, jeu de données
**démo** (`studio/board-v2/src/demo/fixture.ts`, affiché avec le bandeau « DÉMO »).

## Intention

Un poste de travail spatial sombre, dense et vivant, qu'on ouvre pour piloter des agents réels. Adjectifs retenus :
précis, dense, lumineux par touches. Refusés : décoratif, néon partout, gabarit SaaS gris.
Signature : la **carte mission** comme foyer lumineux (bordure dégradée indigo → cyan, halo mesuré) d'où partent
des connecteurs courbes colorés par relation (Inspire violet, Alimente vert, Utilisé par cyan).

## Géométrie mesurée (pixels écran à 1672 × 941, canevas à 80 %)

| Zone | Boîte (x, y, l × h) | Notes |
| --- | --- | --- |
| Barre supérieure | 0, 0, 1672 × 56 | logo + « Jarvis Studio » à x 24 ; onglets dès x 200, actif en pastille 87 × 37, soulignement indigo ; recherche 1153–1426 (273 × 38, rayon 8, « Ctrl K ») ; cloche 1535 ; avatar 1590 |
| Seconde rangée | 0, 60, 1672 × 60 | projet x 22 ; filtres 402–1018 (pastilles, compteurs) ; zoom 1120–1240 « − 80 % + » ; plein écran 1251 ; bouton principal 1454–1652 (198 × 38, indigo plein) |
| Barre d'outils | 16, 136, 68 × 724 | Ajouter (bouton indigo 48 × 40) puis Coller, Importer, Lien, Texte, Image, Vidéo, Audio, Document, Mind map, « … » ; pas de 66 px ; libellé 11–12 px sous l'icône |
| Canevas | 0, 120, 1300 × 821 | grille pointillée 20 px, points #232838 |
| Panneau droit | 1305, 120, 367 × 821 | onglets Détails / Activité / Commentaires ; sections séparées par filets |
| Minimap | 96, 838, 124 × 92 | rectangles des cartes, cadre de vue |
| Carte image | 135, 163, 393 × 247 | image 16:9 pleine largeur, P2 en haut à gauche, menu « … » en haut à droite |
| Carte lien | 566, 148, 347 × 285 | aperçu OG, icône lien, titre, URL, description, étiquettes |
| Carte PDF | 981, 155, 278 × 254 | icône document, titre, « PDF · 1.2 MB », description, deux vignettes de pages, étiquettes |
| Carte note | 146, 455, 326 × 313 | barre B / I / U / liste / … ; texte riche ; étiquettes |
| Carte mission | 598, 475, 362 × 290 | foyer : bordure dégradée + halo ; statut « En cours », barre de progression, étapes cochées, échéance, avatars |
| Équipe d'agents | 1016, 466, 265 × 274 | 2 × 2 avatars 64 px avec anneau de statut, nom + rôle |
| Audio | 246, 789, 370 × 142 | bouton lecture rond indigo 40 px, forme d'onde, temps, vitesse |
| Vidéo | 636, 789, 302 × 142 | vignette plein cadre, bouton lecture central, titre en surimpression |
| Dossier | 964, 808, 302 × 122 | icône dossier, nombre d'éléments, 3 vignettes + « +2 » |

Tailles des nœuds dans le canevas = taille écran ÷ 0,8 (zoom initial 80 %, affiché « 80 % »).

## Typographie

Inter Variable (OFL, auto-hébergée) ; titres de carte 15–16 px écran semi-gras ; texte 13–14 px ; méta 12 px
secondaire ; titre mission 18 px gras ; chiffres tabulaires pour durées, tailles, pourcentages.

## Écarts volontaires (documentés)

1. Données : en mode réel, seules les missions, tâches, tentatives et objets de la base apparaissent ; les dates,
   noms et avatars de la maquette ne sont jamais présentés comme réels. Mode démo signalé « DÉMO ».
2. Avatars : jeu SVG original (bustes stylisés, teinte par rôle) au lieu des portraits 3D générés de la maquette.
3. Logo Codex/OpenAI : absent de `simple-icons` (retiré à la demande d'OpenAI) ; aucun logo inventé — badge texte.
4. Attribution React Flow visible en bas à droite (licence MIT ; la retirer exige l'abonnement Pro).
5. Images de démonstration : découpées de la maquette fournie par le fondateur (aucune image tierce ajoutée).
