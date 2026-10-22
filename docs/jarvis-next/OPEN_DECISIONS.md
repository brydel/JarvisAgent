# Décisions ouvertes — à trancher par le fondateur

| # | Décision | Options | Recommandation de l'agent (non approuvée) |
| --- | --- | --- | --- |
| D-1 | ~~Réparer Codex sous WSL~~ **résolu le 21/10/2026** | cause : le Codex Linux (`~/.npm-global/bin/codex`, 0.162.1) est installé et connecté, mais `~/.bashrc` n'ajoute ce dossier au PATH que pour les shells interactifs : sans terminal, c'est le Codex Windows (`/mnt/c/nvm4w/nodejs/codex`) qui était trouvé. Côté Jarvis : l'adaptateur ignore les binaires `/mnt/…` (VERIFIED). Côté poste (facultatif) : ajouter `~/.npm-global/bin` au PATH dans `~/.profile` | fait ; vérification réelle Codex réussie |
| D-2 | Base de M2 | a) PostgreSQL dans WSL (`apt`) ; b) PostgreSQL via Docker Desktop ; c) rester sur SQLite jusqu'à M3 | a) : léger, sans Docker, RLS testable tôt |
| D-3 | Ordre de fusion | Jarvis Next est empilé sur la PR #5 ; fusionner la pile #1 → #5 d'abord, ou rebaser Jarvis Next sur `main` | fusionner la pile dans l'ordre ; le rebasage dupliquerait du travail |
| D-4 | Canevas du Board | tldraw (licence commerciale à vérifier) ou canevas maison (React Flow/Konva, MIT) | vérifier la licence tldraw avant tout ; à défaut, maison |
| D-5 | Résidence des données | hébergement au Canada ou non pour le futur cloud | à évaluer avant le premier client |
| D-6 | Activer L2 automatique pour le tenant personnel | non (défaut) / oui avec bornes | non tant que M4 ne relie pas L2 à l'admission et à workmux |
| D-7 | Budget d'inférence payante | 0 $ (défaut) ou montant mensuel | 0 $ tant qu'aucune fonction ne l'exige |
