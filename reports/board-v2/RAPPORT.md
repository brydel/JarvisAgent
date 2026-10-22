# Board V2 — rapport de QA visuelle, fonctionnelle et de performance (22 octobre 2026)

Branche `feat/jarvis-board-v2` (sur `claude/jarvis-next-m1`). Environnement de mesure : ASUS, Intel Core i9-13900H
(20 fils), WSL2 Ubuntu 26.04, Chromium 156 de Playwright **sans GPU** (rendu logiciel), viewport 1672 × 941, DPR 1.

## Fidélité visuelle à la maquette

| Fichier | Contenu |
| --- | --- |
| `before.png` | ancien Board (Studio V1) avec trois objets réels |
| `after.png` | Board V2, mode démo, mission sélectionnée (1672 × 941) |
| `overlay.png` / `diff.png` | superposition 50 % et carte des différences (pixelmatch, seuil 0,15) avec la maquette |
| `comparaison.json`, `avant-vs-reference/` | mesures chiffrées |
| `after-1440x900.png`, `after-1280x800.png`, `after-mobile-390x844.png` | autres tailles |
| `etat-survol.png`, `etat-glisser.png`, `etat-media-lecture.png` | états |
| `iterations/c1…c6.png`, `iterations/cmp-*` | les six cycles capture → critique → correction |

Écart à la maquette (pixels différents / écart de couleur moyen sur 255) :
**avant 87,3 % / 196,9 → après 12,0 % / 16,5.** Par zone (après) : barre haute 12,8 · seconde rangée 13,9 · outils
15,9 · panneau 19,1 · image 11,3 · lien 19,1 · PDF 34,4 · note 18,2 · mission 19,7 · agents 25,2 · audio 18,7 ·
vidéo 23,0 · dossier 18,5. Cycles : c1 13,4 % → c4 15,4 % (panneau rempli) → c5 12,3 % → c6 12,2 % → final 12,0 %.

La maquette n'est pas un instantané binaire : les écarts restants sont l'anticrénelage du texte et des décalages
de quelques pixels, plus les écarts **volontaires** ci-dessous.

### Écarts volontaires ou non résolus
1. Progression de la mission : **50 %** (2 tâches sur 4, calculé) au lieu de 65 % (valeur illustrative de la maquette).
2. Avatars : jeu SVG original (teinte par rôle, anneau de statut) au lieu des portraits 3D générés.
3. Logo Codex : absent de `simple-icons` (retiré à la demande d'OpenAI) — badge « CX » ; logo Claude officiel (CC0).
4. Vignettes PDF : rendu réel par pdf.js du fichier de démo (texte) au lieu des images de la maquette.
5. Vignette vidéo : extraite de la vidéo de démo (générée à partir de la maquette).
6. Attribution « React Flow » visible (MIT ; la retirer exige l'abonnement Pro).
7. Dossier : « 4 éléments » avec « +1 » (cohérent) — la maquette affiche « +2 ».
8. Poignées de redimensionnement visibles sur la carte sélectionnée (interaction réelle).
9. Panneau : décalage vertical résiduel d'environ 10 à 15 px vers le bas.

## Tests

- Python : **310 tests** verts (`python3 -m unittest discover -s tests`), dont 34 du Board V2, et la suite PostgreSQL
  (77 tests, Board V2 compris) rejouée sur **PostgreSQL 18.6** (RLS, nouvelles tables, droits du rôle applicatif).
- Playwright (`studio/board-v2`) : **22 tests** verts (dont dialogue de mission et état dans l'URL) — 5 visuels (4 tailles + états, `toHaveScreenshot`), 12
  fonctionnels sur base réelle isolée (note éditée et persistée ; image collée ; plusieurs URL collées avec repli
  d'aperçu ; audio lu avec forme d'onde calculée ; vidéo WebM lue et avancée ; MP4 : message de codec explicite dans ce
  Chromium sans H.264 ; PDF rendu par pdf.js et HTML déguisé refusé ; déplacer / redimensionner / prioriser persistés ;
  relation créée et persistée ; supprimer puis Ctrl+Z ; zoom ; mission réelle suivie en direct par SSE jusqu'à
  « Réussie » ; mouvement réduit et en-têtes de sécurité), 3 mesures de fluidité.

Défauts réels trouvés par ces tests et corrigés : boucle de rendu infinie au début d'une connexion (`onSelectionChange`
non mémoïsé — la page devenait blanche) ; collage visant la fenêtre qui plantait ; cartes créées empilées au même
endroit ; poignées de connexion recouvertes par la carte ; MP4 non décodable qui échouait sans message ; deux
signalements pour une seule connexion.

## Performance (`perf.json`)

Avec le niveau de détail (vignette légère sous 45 % de zoom) et la virtualisation de React Flow :

| Cartes | Panoramique (ips · p95) | Zoom molette | Glisser une carte | Images > 50 ms | Clic « Ajouter » → carte |
| --- | --- | --- | --- | --- | --- |
| 9 (vue détaillée, 80 %) | 48 · 33,4 ms | 57 · 33,2 ms | 49 · 33,4 ms | 1 | 123 ms |
| +100 (vue d'ensemble) | 60 · 16,8 ms | 60 · 16,8 ms | 57 · 33,3 ms | 0 | 142 ms |
| +250 (vue d'ensemble) | 59 · 16,8 ms | 59 · 16,7 ms | 57 · 16,8 ms | 0 | 159 ms |

Avant le niveau de détail (`perf-avant-lod.json`) : +250 cartes → panoramique 23 ips, p95 100 ms, 88 images longues.
Variation d'une exécution à l'autre : environ ±2 ips (dernier passage complet : panoramique 50 / 58 / 58 ips).
Limites : rendu logiciel (Chrome/Edge avec GPU non mesurés) ; « clic → carte » inclut l'aller-retour de Playwright
(> 100 ms, cible non démontrée) ; la vue détaillée à 80 % reste à ~48 ips (ombres, images, halos) ; profils React
et Lighthouse non exécutés.

## Sécurité
CSP V2 sans `eval` ; fichiers reconnus par leurs octets, servis en `nosniff` + `CSP: sandbox`, SVG refusé ; aperçus
de liens sans SSRF (testé : boucle locale, réseaux privés, 169.254.169.254, IPv4 dans IPv6, rebinding, redirection) ;
aucun contenu collé ne déclenche d'action L3/L4 ; un lien collé n'est pas analysé automatiquement.

## Revue « Web Interface Guidelines » (règles récupérées le 22/10/2026)
Respecté : libellés ARIA, focus visible, `aria-live`, « … », chiffres tabulaires, mouvement réduit, animations
`transform`/`opacity`, annulation des suppressions, `color-scheme` et `theme-color`, **état dans l'URL** (filtre,
priorité, recherche, carte sélectionnée — `replaceState`, valeurs inconnues ignorées), **dialogue modal accessible**
pour « Lancer une mission » (`<dialog>`, focus sur l'objectif puis rendu au bouton, Échap, Ctrl+Entrée, envoi
indiqué, erreur dans le dialogue, rappel de la politique L1 ; capture `etat-dialogue-mission.png`). Non fait : lien
d'évitement.
