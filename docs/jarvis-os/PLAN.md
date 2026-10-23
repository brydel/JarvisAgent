# Jarvis OS personnel — plan de réalisation

Date : 23 octobre 2026. Base auditée : `feat/jarvis-board-v2` (`81a875a`) avec les corrections locales de
visibilité du travail. Mandat : assistant personnel du propriétaire, sans objectifs SaaS, vente ni facturation.

## Résultat recherché

Une intention donnée dans le Board devient un projet suivi jusqu'à son résultat : comprendre, rechercher,
planifier, déléguer, produire, tester, corriger, livrer, communiquer et surveiller. Le propriétaire connecte ses
services et définit une fois le mandat du projet. Jarvis exécute ensuite les étapes couvertes, y compris les
actions externes déléguées, sans redemander la même autorisation à chaque outil.

L'autonomie est mesurée sur des projets réels. « Connecté à tout » signifie une architecture ouverte aux
protocoles MCP, API, webhooks et navigateur ; cela ne signifie pas que toutes les intégrations existent déjà.
Une connexion absente, un état externe incertain ou une demande hors mandat doit produire une cause visible
et une stratégie de récupération. Aucun prompt ne peut supprimer ces prérequis.

## Diagnostic issu de trois audits spécialisés

| Constat vérifié | Conséquence | Emplacement |
| --- | --- | --- |
| Deux chemins d'agents : chef/workmux et missions du Board | Le même avatar ne désigne pas la même capacité d'exécution | `lib/jarvis/cli.py:697`, `lib/jarvis/adaptateurs.py:121` |
| Les missions Claude du Board désactivent outils, MCP et persistance | Une mission Board ne peut pas devenir autonome en améliorant seulement son prompt | `lib/jarvis/adaptateurs.py:212` |
| Les missions Codex du Board sont éphémères, en lecture seule, sans configuration utilisateur | Pas de session de projet outillée et persistante par cette voie | `lib/jarvis/adaptateurs.py:261` |
| Le vrai chef autorise WebSearch, WebFetch et Linear | Diagnostiquer la voie et la connexion avant de conclure à une absence générale d'Internet | `lib/jarvis/cli.py:1149` |
| Le Board crée une analyse L1 pour le bouton de mission | Le bouton ne compile pas encore un projet avec dépendances et livraisons | `lib/jarvis/studio_api.py:501` |
| L'interface Configuration est informative | Connexion MCP/OAuth, test réel et affectation d'outils restent à construire | `studio/board-v2/src/product/ProductStudio.tsx:226` |
| États, transactions, baux, backoff et idempotence de résultat existent | Réutiliser ces garanties ; le moteur actuel n'est pas Temporal | `lib/jarvis/missions.py:295`, `:643`, `:746`, `:841` |
| La perte du bail ne stoppe pas l'adaptateur en cours | Une ancienne tentative peut continuer à produire des effets | `lib/jarvis/coureur.py:198` |
| Des effets sont exécutés après commit sans outbox durable | Un crash peut perdre une action automatique ou une notification | `lib/jarvis/missions.py:762` |
| Accepter une proposition traverse plusieurs transactions | Risque de cartes doublonnées ou d'état partiel | `lib/jarvis/missions.py:1055` |
| La file du chef est vidée avant remise au terminal | Perte possible lors d'un crash ; pas d'acquittement applicatif | `lib/jarvis/agents.py:409` |
| La revue de mission vérifie principalement la forme Markdown | Un artefact conforme n'est pas une preuve d'achèvement métier | `lib/jarvis/missions.py:729` |

Le prompt du chef contient déjà observation, budgets, pré-mortem, contre-relecture et mémoire. Il vise surtout
une usine de développement avec des décisions réservées à l'humain. Les 15 rôles existants sont utiles,
mais leur injection concerne workmux et n'unifie pas les missions du Board. La mémoire actuelle est une
recherche lexicale locale ; un index sémantique opérationnel n'a pas été trouvé.

## Choix d'architecture

- **Temporal pour les projets longs** : dépendances, attentes externes, minuteries, signaux, reprise et versions
  de workflow. Introduction progressive dans un service séparé, après une preuve de reprise. Pour une mission
  migrée, Temporal possède les reprises ; le moteur local ne la replanifie pas simultanément.
- **Pas de migration générale vers LangChain.** Cela ne résout ni les connexions ni les effets externes.
  LangGraph reste une option pour la boucle cognitive d'un agent, à évaluer sur le même scénario qu'une boucle
  typée simple. LangGraph a sa propre persistance : si retenu, son périmètre de reprise est explicitement borné
  à une exécution cognitive, sans devenir un second ordonnanceur du projet.
- **Passerelle d'intégrations indépendante du modèle** : API natives, MCP HTTP/stdio, OAuth et navigateur
  passent par le même contrôle de mandat, le même journal d'opérations et les mêmes reçus.
- **Un contrat commun** `AgentSpec` / `TaskSpec` / `RunSpec` pour Board, chef, spécialistes et exécutants.
- **Modèles selon preuves** : modèle OpenAI le plus capable réellement disponible pour planification complexe
  et contre-revue, après test de capacités du compte ; choix des autres modèles sur succès, coût et délai.
  Aucun identifiant de modèle non vérifié ne devient une dépendance du projet.
- Les nouveaux SDK restent dans `services/agent_runtime`, `services/integrations` et `services/workflows`.
  Le cœur `lib/jarvis` garde son contrat de bibliothèque standard Python. Ces dossiers sont une cible, pas des
  services déjà livrés. Voir `ARCHITECTURE.md`.

## Phases et portes de sortie

| Phase | Livraison concrète | Porte de sortie |
| --- | --- | --- |
| F0 — Contrat personnel | Mandat d'autonomie, contrats communs, inventaire de capacités effectives | La même tâche et les mêmes outils sont compris par le chef, le Board et le runner ; aucun outil absent n'est annoncé disponible |
| F1 — Effets fiables | Outbox/inbox, acceptation atomique, annulation réelle, registre d'opérations et réconciliation | Crash avant/après chaque frontière : pas d'action oubliée ; un effet incertain n'est pas rejoué aveuglément |
| F2 — Connexions utiles | Coffre/OAuth, MCP, recherche web, navigateur, email, Git/Linear et staging | Connexion → test réel → affectation → exécution → reçu → révocation fonctionne par API/CLI ; interface livrée en F5 |
| F3 — Agents capables | Boucle d'outils typés, prompts compilés, mémoire sourcée, dispatch spécialisé, preuves | Une mission choisit des spécialistes, utilise ses outils, corrige ses erreurs et prouve son résultat |
| F4 — Projet durable | Temporal, DAG, fan-out/fan-in, attentes externes, reprise et versionnement | Projet interrompu puis repris après arrêt complet, sans doublon et avec un seul propriétaire des reprises |
| F5 — Commande visuelle | Intégrations éditables, graphe chef/sessions/outils, éditeur de mandat et diagnostic | Toute connexion et relation affichée correspond à une autorisation et une exécution persistées |
| F6 — Preuve end to end | Projet pilote réel, essais de panne, évaluations, exploitation et restauration | Livraison vérifiée sans intervention dans le mandat initial, avec coûts, preuves et journal complet |

Les phases décrivent les livraisons, pas un tunnel séquentiel. Après les contrats F0, les prototypes Temporal,
passerelle et interface peuvent avancer en parallèle. Les actions externes en écriture attendent les garanties
F1 et leur mandat. Les dépendances exactes sont dans `linear-project.json`.

## Premier projet pilote

« Construire un petit outil interne à partir d'un besoin déposé sur le Board, le mettre en staging autorisé
et envoyer le compte rendu à mon adresse déléguée. »

1. Le propriétaire connecte GitHub, Linear, une API de recherche, un navigateur isolé, un environnement de
   staging et un compte email. Il fixe dépôt, domaine, destinataire, enveloppes de dépenses et échéance.
2. Jarvis vérifie les connexions, recherche et cite ses sources, formalise les critères d'acceptation.
3. Il crée le projet et les tickets, distribue le travail, implémente, teste et fait relire une version précise.
4. Il déploie en staging, vérifie le résultat par requête et navigateur, corrige puis envoie le compte rendu.
5. On coupe un worker pendant l'exécution et après un effet externe. Jarvis reprend et rapproche l'état réel.

Le test email utilise une API fournisseur et un destinataire de test délégué. Un timeout après envoi peut
signifier « envoyé, réponse perdue ». Temporal ne garantit pas un email exactement une fois : conserver
identifiant d'opération, brouillon/message fournisseur et reçu, puis réconcilier avant un nouvel envoi.
Si le fournisseur ne permet pas de lever l'incertitude, cet état doit rester explicite.

## Critères de réception proposés

- 10 exécutions contrôlées du pilote : au moins 9 atteignent les critères métier sans intervention après le
  mandat initial ; chaque échec restant est expliqué, conservé et reproductible. C'est un objectif, pas un score acquis.
- Aucune action externe en double dans la matrice d'essais de panne ; tout effet impossible à confirmer est
  marqué inconnu et rapproché, sans réussite déclarée sur la seule réponse du modèle.
- Annulation : aucun nouvel appel d'outil après révocation ; processus locaux arrêtés dans le délai du contrat.
  Les effets déjà acceptés par un fournisseur sont réconciliés ou compensés quand il le permet.
- Chaque résultat livré porte les tests et le SHA/empreinte relus, l'identifiant de déploiement ou le reçu fournisseur.
- Dépenses et quotas respectés, aucune clé dans prompts/événements/navigateur, restauration depuis sauvegarde testée.
- Mesures : succès vérifié, interventions par projet, durée, coût, tentatives par étape, reprises, opérations
  inconnues, doublons observés et temps de résolution. Comparer à la base actuelle sur les mêmes scénarios.

Les fournisseurs factices valident la mécanique. Les comptes de test connectés valident les intégrations.
Le pilote réel mesure l'autonomie sur ce scénario borné ; ces trois preuves restent distinctes. Même neuf
réussites sur dix ne prouvent pas une autonomie générale à 100 % sur des objectifs et services inconnus.

## Sessions et exécution

Trois agents spécialisés ont effectivement audité, en parallèle : orchestration/durabilité, prompts/rôles/mémoire,
et intégrations/interface. Les sessions de réalisation sont préparées dans `SESSIONS.md` et dans chaque ticket.
Elles ne sont pas présentées comme déjà lancées ni comme des assignations Linear effectives.

Départ recommandé : JOS-001, JOS-002 et JOS-003, chacun avec son relecteur ; puis le lot fiabilité.
Jusqu'à trois sessions de réalisation en parallèle selon le diagnostic JOS-003, les quotas et les budgets ;
le profil actuel peut limiter à deux exécutants. Augmenter après mesure de la capacité réelle. Une session
possède un ticket et un périmètre de fichiers ; éviter deux auteurs sur le même module sans découpage explicite.
Le scheduler déclenche les tâches et les reprises ; le LLM décide des plans et des exceptions utiles. Une revue
de code indépendante porte sur le livrable exact, pas seulement le résumé du premier agent.

## Livraison Linear

Projet préparé : **Jarvis OS personnel — autonomie de bout en bout**. `linear-project.json` contient objectifs,
phases, tickets, dépendances, responsable agent, relecteur et critères. `linear-issues.csv` offre une version à
mapper dans l'import Linear ; les rôles d'agents figurent dans les descriptions et ne sont pas de faux utilisateurs.

État au moment de la préparation : **création distante non effectuée**. Aucun outil Linear, serveur MCP Linear
configuré ni variable d'authentification Linear n'est disponible dans cette session. L'autorisation utilisateur
est acquise ; la connexion et l'équipe cible restent manquantes. Ne pas inventer d'URL ou d'identifiant Linear.
`LINEAR_HANDOFF.md` donne l'action exacte à exécuter dans une session où Linear est connecté.

## Périmètre de cette livraison

Le dossier livre l'audit, les décisions d'architecture proposées, le backlog et les briefs spécialisés. Il ne
déclare pas Temporal, les connecteurs, le nouveau runtime ou les mandats externes déjà implémentés. Les correctifs
du Board de la livraison précédente sont conservés ; aucun débridage global des outils n'est effectué ici.
