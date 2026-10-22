# Jarvis Product Studio — livraison sur la branche produit

## Périmètre

Ce lot prolonge `feat/jarvis-board-v2` sans réécrire le Board ni son moteur. Il transforme les onglets décoratifs en parcours utiles : accueil, atelier des agents, missions du Board, ressources, activité et lecture de la configuration. Le noyau conserve Python standard-library-only ; le frontend conserve ses dépendances verrouillées.

## Utilisation

Depuis le dépôt, après sauvegarde de ton travail courant :

```bash
git fetch origin
git worktree add ../jarvis-product-studio origin/codex/jarvis-product-studio
cd ../jarvis-product-studio/studio/board-v2
npm ci
npm run build
cd ../..
JARVIS_HOME="$PWD" ./bin/jarvis mission studio
```

Le build est nécessaire : les anciens fichiers compilés présents dans le dépôt ne sont pas une preuve de la nouvelle version. Utiliser le lien **V2** affiché par la commande puis l'onglet **Accueil**. Le démarrage peut nécessiter de fermer l'ancien serveur Studio s'il occupe déjà le port ; ne pas arrêter les agents en cours pour ce seul motif. Les données existantes ne sont ni effacées ni migrées par cette commande.

Pour découvrir uniquement les données fictives : `/v2/?demo=1&vue=accueil` sur ton serveur local. La démo n'exécute aucune mission réelle et n'enregistre pas de modification d'agent.

## Atelier des agents

Le catalogue provient des vrais fichiers de rôles. Un rôle disponible n'est pas une session IA active.

1. Choisir un rôle et modifier son texte de consignes, pas ses permissions.
2. Vérifier les règles structurelles et lire la comparaison.
3. Expliquer le bénéfice attendu et enregistrer une proposition.
4. Ouvrir cette proposition, relire le diff et autoriser explicitement un essai limité.
5. Retirer le candidat pour revenir à la version stable. La promotion définitive reste au terminal.

Le mécanisme de canari préexistant est réutilisé ; il n'est pas remplacé par une note inventée. Un contrôle structurel sans appel de modèle ne démontre pas une amélioration de qualité. Les propositions sont liées à une empreinte de la version stable ; une version périmée ou modifiée après revue est refusée.

Les brouillons restent en mémoire pendant la navigation et déclenchent un avertissement avant fermeture. Ils ne sont pas une sauvegarde durable après crash du navigateur. Une proposition enregistrée est, elle, persistée par le mécanisme existant.

## Frontières de sécurité

Toutes les nouvelles routes `/api/v2/atelier` passent par les mêmes contrôles de session, origine et en-tête que le Board. Les rôles étant encore globaux dans cette installation, l'atelier refuse les tenants autres que le tenant local. Ce lot ne constitue pas une isolation SaaS complète.

Aucun accès shell supplémentaire, aucune suppression des validations, aucune modification des fournisseurs par défaut. La vue Configuration est volontairement en lecture seule. Les événements sont ceux du moteur et non un générateur d'activité visuelle.

## Ce qui reste limité

- Le bouton de mission crée toujours un **cadrage L1 sans outils**. Il ne promet pas une recherche web, un développement ou une candidature automatiques déjà implémentés.
- La vue Missions montre celles reliées au Board, pas nécessairement tous les travaux historiques du CLI.
- Connaissances est un navigateur de notes et liens, pas encore un RAG ni un graphe sémantique.
- Activité montre les effectifs actuels par état, pas des performances historiques ou des scores IA.
- Les déploiements commerciaux, comptes multi-utilisateurs et runners distants restent les jalons architecturaux précédents.

## Futur modèle open source

`services/model_bridge/` fournit un contrat HTTP local testable, **désactivé et non enregistré dans le routeur**. Aucun modèle n'est téléchargé et aucune dépense ni inférence n'est déclenchée. Voir son README pour les limites et l'activation future. Claude Code et Codex restent les deux fournisseurs par défaut.

## Performance

Le Board et React Flow sont chargés à l'ouverture de cette vue. Les vues produit ne créent aucun canvas WebGL et aucune animation permanente. Le rafraîchissement des événements est regroupé, et les préférences de mouvement réduit sont respectées. Pas de nouvelle bibliothèque ; pas de réécriture Rust sans profilage.

Les tailles de bundles et résultats de tests doivent venir du build exact. Aucun nombre de FPS sur l'ASUS n'est garanti par les tests fonctionnels.

## Vérification reproductible

```bash
npm --prefix studio/board-v2 run build
python3 -m unittest discover -s tests -p 'test_missions.py' -v
python3 -m unittest discover -s tests -p 'test_studio*.py' -v
python3 -m unittest discover -s services/model_bridge/tests -v
cd studio/board-v2
npx playwright install chromium
npx playwright test product.spec.ts
```

Playwright utilise son propre état/configuration/dossier de données temporaire et un fournisseur factice. Les tests vérifient aussi un parcours HTTP authentifié de proposition, canari et retrait sans modèle réel. Les captures sont dans `reports/product-studio/`. Le workflow `Jarvis product quality` publie ces preuves, pas un déploiement.

La suite existante complète, les essais sur les abonnements personnels et le profilage sur la machine cible doivent être distingués de ces vérifications ciblées.
