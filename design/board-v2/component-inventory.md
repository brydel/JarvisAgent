# Inventaire des composants — Board V2

| Composant | Fichier | États | Données | Interactions |
| --- | --- | --- | --- | --- |
| Barre supérieure | `src/components/TopBar.tsx` | onglet actif, focus | session | navigation (seul Board actif en V2), recherche (filtre des cartes), Ctrl K |
| Seconde rangée | `src/components/SubBar.tsx` | filtre actif, zoom | compteurs par type | filtres par type et priorité, zoom −/+ / ajuster, « Lancer une mission » (crée une mission L1 via l'API, politique appliquée côté serveur) |
| Barre d'outils | `src/components/Toolbar.tsx` | survol, actif, désactivé | — | créer note, lien, coller (presse-papiers), importer (fichiers), image/vidéo/audio/document (sélecteur typé), mind map (dossier) |
| Canevas | `src/Board.tsx` (React Flow) | vide, chargement, erreur, démo | objets + liens | pan, zoom, sélection multiple, déplacement, redimensionnement, connexion, copier/coller, glisser-déposer, annuler/rétablir, clavier |
| Coque de carte | `src/nodes/CardShell.tsx` | repos, survol, sélection, glisser, verrouillée | priorité, titre | menu « … », poignées de redimensionnement, priorité P1–P3 |
| Image | `src/nodes/ImageNode.tsx` | chargement, erreur | asset (dimensions) | ouvrir en grand, recadrage `object-fit` |
| Lien | `src/nodes/LinkNode.tsx` | aperçu, repli sans aperçu | aperçu serveur (titre, hôte, OG, favicon) | ouvrir le site (nouvel onglet, `noopener`) |
| PDF / document | `src/nodes/DocNode.tsx` | vignettes, repli | taille, pages, vignettes serveur | ouvrir le fichier |
| Note | `src/nodes/NoteNode.tsx` | lecture, édition | texte (Markdown restreint) | édition en place, B / I / liste, sauvegarde temporisée |
| Mission | `src/nodes/MissionNode.tsx` | en file, en cours, revue, réussie, échouée | inspection réelle (tâches, tentatives) | ouvrir dans le panneau |
| Équipe d'agents | `src/nodes/AgentsNode.tsx` | actif, en attente, terminé | tentatives réelles de la mission | — |
| Audio | `src/nodes/AudioNode.tsx` | arrêt, lecture, erreur codec | asset (durée) | lecture, avance, vitesse ; forme d'onde calculée du fichier |
| Vidéo | `src/nodes/VideoNode.tsx` | vignette, lecture, erreur | asset (durée, vignette ffmpeg) | lecture, avance, plein écran ; une seule vidéo à la fois |
| Dossier | `src/nodes/FolderNode.tsx` | replié | éléments rattachés | regrouper, ouvrir |
| Connecteur | `src/edges/RelationEdge.tsx` | repos, sélection | libellé, style | créer, renommer, supprimer |
| Panneau droit | `src/components/Inspector.tsx` | Détails, Activité, Commentaires | mission/objet sélectionné | priorité, approbations (humain), activité réelle (SSE) |
| Avatars | `src/components/Avatar.tsx` | anneau de statut | `agent_instance_id` → teinte fixe | — |
| Minimap | React Flow `MiniMap` | — | nœuds | navigation |
