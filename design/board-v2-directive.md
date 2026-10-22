# JARVIS BOARD V2 — MASTER IMPLEMENTATION DIRECTIVE

## Rôle et mandat

Tu es le responsable conjoint **Principal Frontend Engineer, Interaction Designer, Creative Technologist, Web Performance Engineer, Security Engineer et Visual QA Lead** de JarvisAgent.

**Mission :** transformer le Board local actuel en éditeur spatial multimédia de qualité premium en prenant comme référence visuelle OBLIGATOIRE `design/references/JARVIS_BOARD_V2_REFERENCE.png` (image 1672 × 941). La maquette doit devenir une interface réelle et interactive, non une page statique décorative. Ne commence pas avec un tableau vide. Les éléments d'exemple sont autorisés UNIQUEMENT en mode démo explicitement identifié, jamais comme fausses missions actives.

Le dépôt existe déjà. **Travaille sur `claude/jarvis-next-m1` ou une branche fille**, après inspection de l'état Git actuel ; ne fusionne pas et ne remplace pas le moteur agentique existant. Lis `AGENTS.md`, `CLAUDE.md`, `docs/jarvis-next/`, et `skills/jarvis-design/SKILL.md`. Les fichiers actuellement observés (vérifie qu'ils sont toujours là) sont : `lib/jarvis/studio_board.html`, `studio_board.css`, `studio_board.js`, `studio_api.py`, `missions.py`. Le Board existant est en HTML/CSS/JS natif ; les missions et cartes sont liées à SQLite, alors qu'un module PostgreSQL distinct est apparu. **Ne présume pas que toutes les données du Board sont déjà sur PostgreSQL.**

## 1. Référence visuelle — contrat de fidélité

L'image fournie est la référence de direction artistique et de composition ; pas seulement une inspiration libre. Reproduis au plus près les **proportions, rythmes, contrastes, typographies, bordures, couleurs, ombres, densité, iconographie et structure** à la taille de référence 1672 × 941. Le rendu réel peut différer pour les contenus variables ou détails purement illustratifs, mais tout écart volontaire doit être documenté. Ne reproduis pas les erreurs éventuelles de texte, dates factices ou marques de démonstration comme de vraies données.

Découpage spatial attendu :
- Barre supérieure sombre, navigation `Board / Missions / Agents / Connaissances / Fichiers / Analytique / Configuration`, recherche globale, notifications et profil.
- Seconde rangée : nom du projet, catégories/compteurs, contrôles de zoom, bouton principal « Lancer une mission ».
- Barre d'outils flottante verticale à gauche : Ajouter, Coller, Importer, Lien, Texte, Image, Vidéo, Audio, Document, Mind map.
- Canvas central infini sur grille pointillée, avec déplacement et zoom fluides, minimap en bas à gauche.
- Cartes richement composées : photographie, lien avec preview, PDF avec vignettes, note enrichie, mission avec progression, équipe d'agents avec avatars, audio avec waveform, vidéo avec thumbnail et lecture, dossier de ressources.
- Connexions courbes et étiquettes « Inspire », « Alimente », « Utilisé par » entre cartes.
- Panneau contextuel à droite avec onglets Détails / Activité / Commentaires, statut et priorité, tâches, agents, approbations et activité réelle.
- Palette de marque charbon très sombre, indigo/cobalt, touches cyan, violet et vert sémantique. Éclats lumineux mesurés sur sélection et événements, pas de glow partout.
- Une interface dense et lisible. Aucun composant générique gris sans personnalité ; aucune icône emoji à la place d'un pictogramme système.

Crée `design/board-v2/tokens.json`, `design/board-v2/visual-contract.md` et `design/board-v2/component-inventory.md` avec une première mesure des géométries, des styles, des états et de l'espace réservé à chaque composant. Les couleurs peuvent être approximées depuis l'image puis stabilisées en tokens ; jamais dispersées sous forme de constantes arbitraires.

## 2. Sélection technologique raisonnée

**Proposition par défaut :** TypeScript strict + React + `@xyflow/react` (React Flow) pour les nœuds, arêtes, minimap, panoramique et zoom ; `motion` pour micro-interactions ; `lucide-react` pour les icônes système ; composants accessibles basés sur Radix/shadcn si utile. Next.js ou Vite selon le mode de déploiement : justifie le choix après audit, sans ajouter un serveur Next.js si une application React séparée plus légère est préférable.

Fais une matrice comparative **React Flow vs tldraw** : React Flow sait faire les nœuds personnalisés, liens et redimensionnement ; tldraw a une expérience canvas/clipboard plus complète mais sa licence de production commerciale doit être vérifiée et son coût approuvé. Par défaut, privilégie React Flow si les besoins sont réalisables sans dette excessive. L'implémentation ne doit pas casser les contrats de mission et d'événements Python.

**Rust n'est pas requis pour le rendu UI**. Le goulot typique est dans le navigateur : DOM, React rerenders, médias, décodage et réseau. N'introduis Rust/WASM qu'après des mesures avec profilage indiquant une opération CPU isolée réellement pénalisante ; soumets une ADR et un benchmark. Réutilise les outils natifs du navigateur, `ffmpeg`/workers pour les previews serveur si justifié, et les API Python existantes.

## 3. Ingestion multimédia : ce que l'utilisateur doit pouvoir faire

Le Board doit prendre en charge, par **Ctrl+V / Cmd+V**, glisser-déposer, fichiers sélectionnés, collage d'URL et création depuis la toolbar :

1. **Images** : PNG, JPEG, WebP, GIF et captures du presse-papiers ; aperçu fidèle, dimensions, titre, zoom/ouvrir, image contenue et cadrage propre, image glissable dans le canvas.
2. **Liens** : détecter URL(s), normaliser, afficher preview sécurisée (favicon réel, titre, hostname, image OG et description si disponibles), action « Ouvrir le site ». Toujours fournir fallback si extraction indisponible.
3. **PDF et documents** : fichier avec nom, taille, nombre de pages si détecté, aperçu des premières pages et ouverture complète. Pas de rendu de PDF comme HTML arbitraire non sécurisé.
4. **Audio** : MP3, WAV, M4A, OGG si pris en charge ; lecteur natif avec play/pause, seek, durée, vitesse et waveform optionnelle réelle. Aucune fausse forme d'onde présentée comme issue du fichier.
5. **Vidéo** : MP4, WebM et formats pris en charge par le navigateur ; vraie miniature extraite, lecture/pause, scrub, plein écran, durée et taille ; jamais toutes les vidéos démarrées en même temps.
6. **Texte et notes** : mise en forme raisonnable, listes, liens, édition inline, sauvegarde, historique minimal et rendu sécurisé.
7. **Missions** : état obtenu depuis le backend, étapes, progrès fondé sur des tâches réelles ; actions soumises au Policy Engine.
8. **Agents** : avatars, rôle, fournisseur, statut réel, relation à la mission ; ne jamais inventer d'agent en cours.
9. **Collections / dossiers** : regrouper des ressources, les déplier, les déplacer et les relier à un projet.

Coller plusieurs éléments doit créer plusieurs objets intelligemment positionnés, pas concaténer tous les contenus dans un textarea. Une image copiée depuis le navigateur doit produire une carte image avec vrai contenu, non un chemin temporaire cassé. Les liens partagés doivent conserver une carte riche sans exécuter le HTML du site distant.

Construis un pipeline `ingest -> validate -> upload/store -> metadata -> thumbnail/preview -> index -> create board object -> emit event`. Prévoyez MIME sniffing, tailles limites configurables, rejets compréhensibles, contrôle antivirus si l'environnement le permet, URLs signées ou endpoints authentifiés, stockage local puis abstraction S3, quotas et nettoyage des fichiers orphelins. Aucune lecture de fichier arbitraire via chemin fourni par l'utilisateur.

Pour les previews de liens : protection SSRF (réseaux privés, loopback, métadonnées cloud, redirections, DNS rebinding), timeouts, limites de taille, filtrage de protocoles et rendu HTML jamais directement injecté. Évite l'iframe libre pour les liens inconnus. Les lecteurs audio/vidéo affichent explicitement les erreurs de codec et de chargement.

## 4. Canvas : vrai comportement d'éditeur spatial

Le canvas doit gérer :
- Pan au pointeur/espace + glisser ; zoom molette/pincement, Fit-to-view et reset ; mini-map fiable.
- Déplacement libre de cartes avec feedback d'élévation, snapping facultatif et option de verrouillage.
- Redimensionnement par poignées ; dimensions min/max spécifiques au type de carte ; conservation du ratio des médias au besoin.
- Sélection simple/multiple, duplication, suppression avec confirmation appropriée, Undo/Redo, copier/coller interne.
- Groupes, alignement, distribution, z-index, « Amener devant », repères de placement, recherche/filtres.
- Priorité P1/P2/P3 via métadonnée métier indépendante de la position visuelle, tri et filtres par priorité.
- Connecteurs directionnels entre cartes, libellés de relation, suppression/édition de relations, persistance.
- Zoom stable : les contrôles interactifs (play, scrub, menus, édition) ne doivent pas involontairement déplacer ou zoomer le canvas.
- Clavier : focus visible, Tab, Entrée, Échap, flèches pour déplacer l'objet sélectionné, raccourcis documentés.
- Multi-sélection, tactile et trackpad testés ; `prefers-reduced-motion` respecté.

**Schéma nécessaire**, tenant-aware : `board_object` (id, workspace_id, type, x, y, width, height, z_index, priority, metadata, artifact_id, mission_id, created_at, updated_at, version), `board_edge` (id, workspace_id, source_id, target_id, label, style), `board_group`, `board_asset` ou équivalents documentés. Les informations existantes et les identifiants de mission doivent être migrés sans perte. Un backend actuel SQLite peut rester en service si le plan de migration n'est pas encore validé ; spécifie son interface et sa trajectoire PostgreSQL. Opérations idempotentes, validation serveur, contrôle tenant, gestion des conflits ; pas d'objet média stocké en base64 dans les événements SSE.

Persiste les coordonnées et tailles après chaque action, avec debounce approprié et sauvegarde finale garantie. Une fermeture/réouverture doit conserver exactement la disposition, et les cartes doivent survivre au rechargement ou changement de session.

## 5. Interactivité et vie des agents

La maquette montre une équipe d'agents avec avatars et un panneau d'activité. Ce sont des représentations de données vraies :
- L'avatar n'est pas une photo d'un fournisseur ni un logo officiel déguisé en personne. Crée un set d'avatars originaux, cohérents, pouvant évoluer en status rings et accents, avec attribution fixe par agent_instance_id.
- Les logos Claude, Codex, GitHub, Linear, Telegram et autres services proviennent de leurs actifs officiels autorisés ou d'ensembles SVG à jour (vérifier marques/licences). Aucun logo de marque inventé ou fausse affiliation.
- Icônes d'outils/missions/settings cohérentes (`lucide-react` en priorité), traits, tailles, alignement optique stables.
- État `waiting/running/review/succeeded/failed` déterminé par les événements réels ; pas d'activité factice sans label `DÉMO`.
- Aperçu d'une mission au clic : progressions, étapes, sous-agents, dépendances, journaux, livrables et approbations.
- Panneau contextuel à droite : onglets fonctionnels, possibilité d'édition de métadonnées autorisées, historique d'activité vrai.
- SSE existant conservé, reprise Last-Event-ID lorsque disponible, état rechargé après reconnexion, nettoyage des subscriptions et écouteurs.

N'effectue aucune action L3/L4 à partir d'un collage de contenu. Une page web, un lien ou un PDF est une **source non fiable**, pas un ordre adressé à Jarvis.

## 6. Motion design et performance mesurable

Animations discrètes et réactives : apparition 140–220 ms, hover 100–160 ms, ouverture panneau 180–260 ms, drag lift performant, sélection et focus visibles. Animate `transform` et `opacity` principalement ; ne fais pas une animation perpétuelle sur chaque carte ni des ombres animées coûteuses.

Objectifs à **mesurer**, non à déclarer sans preuve :
- Pan/zoom/drag ressentis comme fluides, cible 60 FPS sur ASUS pour 100 cartes de données de démonstration, avec mesure des frames et rapport p95.
- 250 cartes de types mixtes en mode test : aucune interaction gelée, rendu uniquement des contenus coûteux visibles, médias différés.
- Interaction majeure responsive à moins de 100 ms sur machine de référence quand possible ; capturer les cas qui excèdent la cible.
- Audio/vidéo chargés à la demande, `preload=metadata` par défaut, images responsive et thumbnails mis en cache.
- Pas d'imports géants ni de re-render intégral du Board à chaque `pointermove`; memoize les nœuds, les callbacks et les sélecteurs ; ne copie pas tout le graphe dans chaque composant.
- Tester avec le profiler React, Chrome Performance, Lighthouse et mesures de bundle ; livrer chiffres réels, environnement et limites.

Si 250 cartes dégradent les performances, ajoute une stratégie de virtualisation/visible-elements si compatible avec le moteur de canvas et les liens. Documente les compromis.

## 7. QA VISUELLE — obligatoire, itérative

L'objectif est une **haute fidélité visuelle mesurée** à l'image de référence, à la résolution de capture 1672 × 941 en Chromium avec viewport et deviceScaleFactor stabilisés, polices chargées, fixtures contrôlées, animations figées pour les screenshots.

- Stocke la maquette à `design/references/JARVIS_BOARD_V2_REFERENCE.png`.
- Construis un jeu de données *démo* déterministe qui reproduit les **types et la composition** de l'image : image paysage, lien Claude (simple ressource avec preview), PDF, note, mission, équipe d'agents, audio, vidéo et groupe de ressources. Toute mission/agent de démonstration doit être clairement signalée dans le code et isolée de l'état réel.
- Écris des tests Playwright : captures initiales et après interactions, pan, zoom, drag, resize, collage image, import audio/vidéo, URL, PDF, lecture, sélection, priorité, liens, persistence après reload, rendu des événements SSE, mode réduit.
- Compare capture vs référence avec une **image diff/overlay** enregistrée. Utilise `toHaveScreenshot()` pour les régressions contre des baselines réelles stabilisées ; ajoute un outil de comparaison à la maquette générée pour la direction artistique, mais ne fais pas de la maquette un snapshot binaire obligatoire puisqu'elle contient des pixels générés et des actifs illustratifs non identiques.
- Passe au moins **trois cycles** : capture -> critique des écarts -> correction -> nouvelle capture. Vérifie également 1440 × 900, 1280 × 800 et une largeur mobile raisonnable. L'interface dense peut proposer un mode mobile simplifié, sans masquer les fonctionnalités essentielles.
- Produis `reports/board-v2/` : captures `before.png`, `after.png`, `overlay.png`, `diff.png`, tests, métriques, écarts connus et captures des états hover/drag/sidebar/média.
- Interdiction de déclarer « pixel-perfect » ou « terminé » sans avoir ouvert et inspecté les captures et vérifié les comportements. Les différences impossibles à supprimer sont expliquées explicitement.

## 8. Skills et outils de travail

Lire d'abord le skill interne `skills/jarvis-design/SKILL.md`. Examiner la présence de ces compléments ; si absents, proposer leur installation vérifiée, au **périmètre projet**, après revue du code et des scripts :

- Plugin officiel Anthropic `frontend-design` (direction artistique et qualité de réalisation).
- `vercel-react-best-practices` de `vercel-labs/agent-skills`.
- `web-design-guidelines` de `vercel-labs/agent-skills`.
- `ui-ux-pro-max` de `nextlevelbuilder/ui-ux-pro-max-skill` (tiers : revue préalable).
- Motion AI Kit (`npx motion-ai`) pour documenter les interactions Motion.
- Playwright Test pour e2e et visuel (bibliothèque et outillage, pas un skill magique).

Ne charge pas plusieurs plugins redondants sans gain observé. Ne laisse aucun skill installé modifier des permissions système ou lancer des scripts imprévus sans inspection.

## 9. Découpage de livraison sans casser Jarvis

Travaille sur une branche fille dédiée `feat/jarvis-board-v2` si elle est libre, sinon un nom distinct. Ne pousse pas dans `main`, ne fusionne pas. Préserve l'accès au Studio actuel pendant la migration ; ajoute une entrée `Board V2` ou feature flag si nécessaire.

**Lot A — Design foundation / architecture** : audit réel, design tokens, composants, choix canvas/licences, schéma, fixtures, prototype React fonctionnel affichant la composition de référence avec des cartes réellement déplaçables.

**Lot B — Canvas editing** : pan/zoom, resize, relations, priorités, groupes, sérialisation, Undo/Redo, raccourcis, tests de persistance.

**Lot C — True multimedia** : presse-papiers, drag-drop, upload, previews, players audio/vidéo, PDF, liens sécurisés, stockage et contrôle d'accès.

**Lot D — Missions et agents réels** : consommation des API et événements existants, panneau contextuel, vraie chronologie, permissions/approbations, identification des avatars.

**Lot E — Visual/performance hardening** : Playwright, captures diff, animations, accessibilité, benchmarks, réglage du rendu et audits sécurité.

Chaque lot doit aboutir à un produit qui démarre et des tests qui passent. Tu peux poursuivre les lots dans la même session seulement si le précédent est vérifié. Si l'installation des dépendances est impossible, conserve un résultat utile (documentation, composants indépendants, fixtures et tests) et décris le blocage.

## 10. Définition stricte de terminé

Ne dis pas « terminé » tant que :

1. Le Board est visuellement proche de la maquette et les écarts ont été inspectés et documentés.
2. Images, URL, PDF, audio, vidéo, notes, missions et agents ont tous des composants fonctionnels — pas uniquement des blocs décoratifs.
3. Copier/coller, drag-drop, déplacer, redimensionner, prioriser, grouper, relier et persister sont testés.
4. Les workflows de mission, approbations et événements SSE de Jarvis ne sont pas cassés.
5. Les données tenant et ressources sont protégées ; les contenus externes restent non fiables.
6. Les performances ont des mesures et un rapport ; les cibles non atteintes sont transparentes.
7. Les snapshots visuels et tests fonctionnels Playwright ont été exécutés dans un environnement contrôlé.
8. Des captures avant/après et des comparaisons sont incluses dans la livraison.
9. Les changements sont documentés et isolés dans une branche, sans merge.

**Rapport final en français :** fichiers modifiés, décision technologique, comportements réellement testés, métriques, captures, limites, risques, branche, commits, liens de PR obtenus et prochaines actions.

**Commence maintenant par ouvrir les fichiers réels du Board et la référence PNG, produire le contrat visuel et un prototype fonctionnel. Ne t'arrête pas à un plan ou à une page HTML statique.**
