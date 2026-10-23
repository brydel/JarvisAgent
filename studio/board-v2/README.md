# Jarvis Board V2 (frontend)

Éditeur spatial multimédia du Studio. Code source ici ; le build est écrit dans `lib/jarvis/studio_v2/` et servi par
`lib/jarvis/studio_api.py` sous `/v2/` (aucun serveur Node en usage normal).

```bash
cd studio/board-v2
npm ci                      # dépendances verrouillées, une fois
npm run build               # vérification des types puis build vers lib/jarvis/studio_v2
bash scripts/preparer-demo.sh   # régénère les fichiers du mode démo (ffmpeg requis)
npx playwright test         # parcours fonctionnels/visuels et mesures de fluidité (serveur isolé, port 7721)
npx playwright test runtime.spec.ts  # contrôleur outillé et interfaces de connexion
node scripts/compare.mjs <capture.png> <dossier>   # comparaison avec la maquette de référence
```

- Ouvrir : `jarvis mission studio` (affiche le lien V2), ou `/v2/?demo=1` pour les données fictives signalées « DÉMO ».
- `?demo=1&charge=250` : 250 cartes de charge (mesures de performance, démo seulement).
- **Travail en direct** (Board réel) : sessions de code du poste et tâches du moteur, même sans carte « mission ».
  L'accueil observe tous les projets ; un Board de projet filtre son travail. Sélectionner une session affiche
  sa sortie terminal, relue toutes les cinq secondes. Le panneau se replie pour laisser la place au canevas.
  Les missions sans terminal montrent leur statut et leur bail ; la réponse du modèle arrive à la remise du résultat.
  Les cartes sont également relues toutes les dix secondes si le flux SSE ne suffit plus.
- **Réseau des agents** : espace global de toute l'usine, discussions libres, salons et réponses persistantes.
  Le projet et les preuves sont facultatifs pour parler. La promotion en leçon reste une action de relecture distincte.
- **Intégrations** : serveurs MCP HTTPS ou processus locaux stdio, découverte, sélection des outils,
  révocation, capacités observées et opérations. La découverte stdio démarre réellement l'exécutable choisi
  par le propriétaire, avec les droits de son utilisateur Linux ; les arguments ne sont pas une commande shell.
- **Missions outillées** : onglets Missions, Modèle, Mandats et Courriel. Le propriétaire renseigne l'identifiant
  du modèle et une référence de variable, crée un mandat, choisit les outils et lance l'exécution.
  Le modèle est figé par run. Pause, reprise et arrêt agissent sur le contrôleur ; la réponse finale reste
  **À vérifier** jusqu'à une relecture distincte de l'agent. Le budget affiché est une réservation estimée.
- **Courriel**, dans Missions outillées : configuration Google, scopes choisis, adresse expéditrice et flux
  OAuth PKCE. Les clés et jetons restent côté service. Une configuration enregistrée n'est pas une connexion
  ou un envoi réel vérifié. Le coffre local protège ses fichiers par les permissions Linux, sans chiffrement au repos.
  Le retour OAuth est limité à HTTP sur `localhost` ou `127.0.0.1` ; un navigateur sur une autre machine
  nécessite un tunnel ou une redirection de son port local `7718`. Le retour HTTPS public reste indisponible.
- Raccourcis : Ctrl+V coller (images, fichiers, URL, texte) · Ctrl+Z / Ctrl+Maj+Z · Ctrl+C / Ctrl+D · Suppr ·
  N nouvelle note · Maj+! ajuster · Échap désélectionner · flèches déplacer · Maj+glisser sélection multiple ·
  Ctrl K recherche.

Le serveur Playwright utilise un état temporaire. `JARVIS_TEST_RUNTIME=1` remplace uniquement le modèle par
un scénario déclaré factice ; le parcours principal conserve le contrôleur, la passerelle et la persistance
réels. Il vérifie une publication dans le réseau de test puis une relecture du résultat. Les parcours de
connexion contrôlent séparément les frontières HTTP, sans clé ni compte externe réel.

Cette tranche ne migre pas les anciennes missions documentaires vers le runtime outillé et ne modifie pas
le prototype Temporal. Voir [la livraison et ses limites](../../docs/jarvis-os/LIVRAISON_RUNTIME.md) pour les
commandes, les preuves ciblées et le journal de validation globale à compléter.
