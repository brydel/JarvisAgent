# ADR-0007 — Board V2 : React + React Flow, construit en fichiers statiques servis par le Studio Python

Statut : PROPOSED (implémenté et vérifié) · 22 octobre 2026

## Contexte
La directive `design/board-v2-directive.md` demande un éditeur spatial multimédia fidèle à
`design/references/JARVIS_BOARD_V2_REFERENCE.png`, relié aux vraies missions, sans casser le Studio existant.

## Décision
- **React 19 + TypeScript strict + `@xyflow/react` 12 (React Flow)** pour nœuds, arêtes, mini-carte, pan/zoom,
  redimensionnement et connexions ; `motion` pour les transitions du panneau ; `lucide-react` pour les icônes ;
  `simple-icons` (CC0) pour les logos officiels disponibles ; Inter auto-hébergée (OFL) ; `pdf.js` (Apache-2.0)
  chargé à la demande pour les vignettes PDF.
- **Vite** (pas de Next.js) : une application client servie par `studio_api.py` sous `/v2/`. Le build est versionné
  dans `lib/jarvis/studio_v2/` : l'installation n'a besoin ni de Node ni d'un serveur supplémentaire.
- **Pas de Rust/WASM** : les mesures (rapport de performance) montrent que le coût est le rendu DOM ; il est réglé par
  la virtualisation de React Flow et un niveau de détail sous 45 % de zoom.

## Comparaison React Flow / tldraw (sources consultées le 21 octobre 2026)
| Critère | React Flow | tldraw |
| --- | --- | --- |
| Licence | MIT ; retirer l'attribution exige l'abonnement Pro | licence propre : clé requise en production ; licence hobby non commerciale avec filigrane |
| Nœuds personnalisés, liens, redimensionnement | oui | oui |
| Presse-papiers / dessin libre | à construire (fait ici pour images, URL, texte, fichiers) | plus complet |
| Coût | 0 | à négocier |
Choix : React Flow (aucune dépense, compatible SaaS), attribution laissée visible.

## Sécurité
CSP de la page V2 : scripts `self` uniquement, aucun `eval` ; styles en ligne autorisés (React Flow positionne les
nœuds par attributs `style`). Fichiers servis avec leur type reconnu par les octets, `nosniff`, `CSP: sandbox`.
SVG refusé au téléversement. Aperçus de liens sans SSRF et sans HTML distant.

## Conséquences
Un build à refaire (`npm run build`) après toute modification de `studio/board-v2/src`. Le Studio V1 reste servi sur `/`.
