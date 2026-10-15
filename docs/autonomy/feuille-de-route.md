# Feuille de route restante

Principe : la mesure qui compte est le **travail utile et vérifié par unité de coût et d'intervention
humaine**, puis la rentabilité des produits. Pas de nouveaux agents sans preuve de résultat.

## Lot 2 — à terminer

- Classification des échecs d'agent (bloqué, erreur d'outil, hors périmètre, quota, régression) à partir
  des événements existants (`taches.json`, `jarvis verdict`, captures), avec reprise bornée par tâche
  (2 essais, puis changement d'approche/modèle, puis escalade) — conçu.
- Secrets minimaux par tâche (variables autorisées par rôle, injectées par les lanceurs) — conçu
  (`securite.md`).
- Import périodique des propositions GitHub par le démon (réglage `propositions.github_depot`) — conçu,
  volontairement manuel pour le premier essai.
- Bilan quotidien automatique (livré, prouvé, échoué, dépensé, risques, décisions demandées) envoyé sur
  Telegram le matin : agrège `jarvis bilan`, `jarvis budget`, `jarvis politique exceptions`, `jarvis audit` —
  conçu.
- Dépendances explicites entre éléments de plan (A avant B) — conçu.

## Lot 3 — un parcours commercial pour un seul produit, en simulation

- Modèle d'opportunité (problème, client cible, preuves datées, alternatives, canal, volonté de payer,
  difficulté, dépendances, risques, coûts, critère d'abandon, hypothèses et incertitude de la note) sous
  forme de fiche versionnée dans le dépôt du produit, produite par le rôle `recherche`, contre-relue.
- Pipeline : détection → qualification → validation commerciale → prototype → MVP → lancement autorisé →
  acquisition → exploitation → amélioration/pivot/arrêt, avec critères d'entrée/sortie, preuves et budget par
  étape ; une étape = un état dans `travaux.py` étendu.
- Preuves distinguées : vues, liste d'attente, entretiens, engagements, paiements ; expériences
  d'invalidation limitées ; aucun concurrent, citation ou client inventé (vérification par sources datées).
- Publication et dépenses : désactivées sans délégation ni enveloppe (déjà en place) ; staging distinct ;
  retour arrière applicatif ≠ retour des données.

## Lot 4 — exploitation autonome, amélioration mesurée, migration

- Amélioration des agents : hypothèse, version stable, candidate, jeux d'essai dont une partie protégée et
  non utilisée pour optimiser, budget, mesures, décision, déploiement progressif, rollback ; le candidat ne
  modifie ni les tests protégés ni la définition du succès (politique `protection`, niveau 3).
- Supervision des produits (incidents, support, sauvegardes, restauration testée, coûts) hors du poste.
- Verrou de bail d'orchestrateur et exécutants multi-machines ; migration vers la station
  (`exploitation.md` §6) ; augmentation de la concurrence après mesures sur place seulement.

## Prochaine action concrète

1. Sur ton PC : procédure de relance (`exploitation.md` §1), puis `jarvis diagnostic` et une journée
   d'usage normal avec le profil `laptop-conservative`. Lis `jarvis audit` et `jarvis admission etat` le soir.
2. Dis-moi ce que le diagnostic affiche (mémoire WSL, `.wslconfig`, plafonds imposables) : c'est ce qui
   décidera des valeurs réelles du profil et de l'activation éventuelle de cgroups.
3. Si tu veux l'essai Dots : crée le dépôt de propositions, autorise l'app GitHub dans ChatGPT, et donne au
   dot la consigne décrite dans `fournisseurs-et-dots.md`.
