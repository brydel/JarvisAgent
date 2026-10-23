# Exemples de contrats v1

Les fichiers `agent-*`, `tache-*` et `run-*` décrivent respectivement un AgentSpec, un TaskSpec et un RunSpec.
Les identifiants d'artefact et de mandat sont des exemples, pas des objets créés ni des preuves de connexion.
Le profil documentaire ne demande aucun outil. Le profil outillé exprime les besoins d'une recherche ;
il n'affirme pas que `web.search` et `web.read` sont implémentés ou disponibles sur ce poste.

Un contrat est une donnée à valider avec `jarvis.contrats`. Il n'accorde pas d'autorisation, ne résout pas
les références et n'applique pas les budgets par sa seule présence. Le contrôle de mandat, le diagnostic
fonctionnel et les limites effectives du runner restent des vérifications distinctes.

- Les champs `version`, `id`, `role`, `profile` sont obligatoires pour un agent.
- Les champs `version`, `id`, `agent_id`, `objective`, `project`, `acceptance` sont obligatoires pour une tâche.
- Les champs `version`, `id`, `agent_id`, `task_id`, `status`, `source` sont obligatoires pour un run.
- Les validateurs ajoutent les défauts, renvoient une copie et refusent les champs inconnus, y compris
  les champs d'authentification. Les clés et jetons doivent rester dans un service de connexion.
- `null` pour un plafond signifie « inconnu », pas « illimité ». `0` est une limite explicite à zéro.
  Pour une nouvelle demande, une durée absente prend la valeur 300 secondes ; une projection historique
  dont la durée n'est pas connue doit fournir explicitement `null`.
- Les dépendances d'une tâche sont des références. L'auto-dépendance est refusée ici ; le planificateur
  doit vérifier l'existence et les cycles entre plusieurs tâches.
- `execution_engine: temporal` désigne le moteur souhaité, sans prétendre que Temporal est installé.
- Le statut d'un run n'est pas une preuve métier. Les reçus et résultats vérifiés restent nécessaires.

Les schémas publiables sont disponibles via `contrats.schemas()` : `version`, `agent`, `task`, `run`.
`contrats.empreinte()` calcule le SHA-256 d'un objet JSON canonique ; valider avant de figer un contrat.
