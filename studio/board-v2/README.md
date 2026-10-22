# Jarvis Board V2 (frontend)

Éditeur spatial multimédia du Studio. Code source ici ; le build est écrit dans `lib/jarvis/studio_v2/` et servi par
`lib/jarvis/studio_api.py` sous `/v2/` (aucun serveur Node en usage normal).

```bash
cd studio/board-v2
npm install                 # dépendances exactes (package.json), une fois
npm run build               # vérification des types puis build vers lib/jarvis/studio_v2
bash scripts/preparer-demo.sh   # régénère les fichiers du mode démo (ffmpeg requis)
npx playwright test         # 17 tests fonctionnels/visuels + 3 mesures de fluidité (serveur isolé, port 7721)
node scripts/compare.mjs <capture.png> <dossier>   # comparaison avec la maquette de référence
```

- Ouvrir : `jarvis mission studio` (affiche le lien V2), ou `/v2/?demo=1` pour les données fictives signalées « DÉMO ».
- `?demo=1&charge=250` : 250 cartes de charge (mesures de performance, démo seulement).
- Raccourcis : Ctrl+V coller (images, fichiers, URL, texte) · Ctrl+Z / Ctrl+Maj+Z · Ctrl+C / Ctrl+D · Suppr ·
  N nouvelle note · Maj+! ajuster · Échap désélectionner · flèches déplacer · Maj+glisser sélection multiple ·
  Ctrl K recherche.
