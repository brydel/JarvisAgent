# Direction produit — Jarvis Studio

## Intention

Une équipe que l'on comprend, un espace que l'on maîtrise. Prolonger le Board approuvé en un environnement utilisable, avec une identité nocturne précise et des retours d'action immédiats.

Conserver : fonds bleu nuit, surfaces structurées, accents indigo, avatars existants et icônes Lucide. Refuser : tableaux de métriques inventées, faux agents actifs, animations permanentes, badges de récompense artificiels et onglets sans action.

## Contrat d'interaction

L'accueil propose une intention, pas une promesse d'exécution intégrale. Les cartes d'agents ouvrent un vrai atelier. Les termes utilisateur sont consignes, proposition, essai limité et version stable ; les mécanismes techniques restent explicables dans le détail.

La progression vient du travail accompli et de l'état réel, pas de streaks, de fausse urgence ou de récompenses aléatoires. Les changements sensibles demandent une décision claire et les erreurs donnent une action utile.

## Système visuel

Jetons `--p-*` dans `src/styles/product.css` : fond #0b0e15, surface #121721, surface élevée #181f2c, trait #293244, texte #f3f5ff, secondaire #9daabd, accent #93a2ff, action #6268ed, confirmation #95e3ca. Réutiliser Inter auto-hébergée déjà présente ; ne pas ajouter de police externe.

Le visuel mémorable est la constellation de rôles autour de Jarvis. Elle est statique au repos, sans boucle de rendu ; chaque carte ouvre un rôle. Le reste privilégie la lisibilité et des hiérarchies nettes.

## Responsive et mouvement

Bureau : accueil à deux colonnes, catalogue en grille, éditeur adjacent. Mobile : navigation défilable, sections empilées, éditeur avant le catalogue. Les déplacements de survol restent légers (140–170 ms) ; `prefers-reduced-motion` les désactive.

## Preuves attendues

Captures réelles 1440×1000 et 390×844 ; navigation, brouillon conservé, comparaison, modal de consentement, recherche, ouverture d'une ressource et retour au Board. Aucun débordement horizontal du document ni erreur JavaScript. Le contrôle visuel humain complète les tests, il n'est pas remplacé par un simple build réussi.
