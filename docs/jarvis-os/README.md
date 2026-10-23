# Jarvis OS personnel

Le projet vise un assistant personnel capable de réaliser un projet de bout en bout avec un mandat initial,
des connexions réelles, des workflows durables et des preuves de résultat.

- [Plan, diagnostic et phases](PLAN.md)
- [Première tranche implémentée et commandes](IMPLEMENTATION.md)
- [Livraison usine : réseau libre, fiabilité et intégrations](LIVRAISON_USINE.md)
- [Livraison du runtime outillé, OpenAI, OAuth/Gmail et MCP local](LIVRAISON_RUNTIME.md)
- [Boucle cognitive et garanties de reprise](RUNTIME_AGENT.md)
- [Adaptateur OpenAI Responses](MODELES_RUNTIME.md)
- [Connexion OAuth Google et outils Gmail](OAUTH_COURRIEL.md)
- [Transport MCP stdio](MCP_STDIO.md)
- [Architecture et choix Temporal/LangGraph](ARCHITECTURE.md)
- [Backlog détaillé — 30 tickets](BACKLOG.md)
- [Spécialistes et briefs de session](SESSIONS.md)
- [Manifeste structuré pour Linear](linear-project.json)
- [CSV à mapper dans l'import Linear](linear-issues.csv)
- [Création depuis une session connectée à Linear](LINEAR_HANDOFF.md)

État : socle F0, fiabilité F1, réseau libre de l'usine et passerelle web/MCP HTTP/stdio implémentés localement.
Le nouveau runtime durable, l'adaptateur OpenAI Responses, OAuth Google/Gmail et les contrôles du Board sont
livrés avec des tests contrôlés. Aucun compte OpenAI ou Google réel n'est connecté ici. Le prototype SDK
Temporal est livré ; son serveur réel, l'ordonnanceur de projet et la migration des anciennes missions
restent à réaliser ou valider.
Création distante Linear non effectuée faute de connexion disponible. Les limites et preuves figurent dans
les livraisons ; une connexion déclarée ne vaut pas connexion vérifiée.
