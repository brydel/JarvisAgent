# Registre des risques

| # | Risque | Probabilité | Impact | Mesure | Propriétaire |
| --- | --- | --- | --- | --- | --- |
| R1 | Même utilisateur Linux pour agents, base et plan de contrôle : la politique est contournable localement | élevée | élevé | M3 sépare l'exécutant de la base ; d'ici là, documenté et L3/L4 jamais automatiques | architecture |
| R2 | Usage d'abonnements hors conditions des fournisseurs en commercial | moyenne | très élevé | routeur refuse l'abonnement en `COMMERCIAL_HOSTED` ; confirmation écrite avant conception dépendante | fondateur |
| R3 | Codex inutilisable dans WSL → un seul fournisseur réel | certain aujourd'hui | moyen | D-1 : réinstaller Codex côté Linux | fondateur |
| R4 | Pile de 5 PR non fusionnées + une 6ᵉ : dérive et conflits | élevée | moyen | Jarvis Next isolé dans des modules neufs ; fusion par ordre de pile | fondateur |
| R5 | Revue déterministe qui valide une forme correcte mais un fond faux | moyenne | moyen | contre-relecture par l'autre fournisseur (M4), évaluations | évaluation |
| R6 | Licence d'un canevas incompatible avec un SaaS | moyenne | moyen | D-4 avant toute dépendance | produit |
| R7 | Promesse implicite de disponibilité des modèles | moyenne | moyen | WAITING_PROVIDER explicite, documentation honnête | produit |
| R8 | Coûts cachés (API, cloud) | faible (bloqué par code) | élevé | budget zéro par défaut, contrôle avant envoi | budget |
| R9 | Données personnelles dans les artefacts | moyenne | élevé | tenant, rétention et suppression (M2), pas d'envoi externe | sécurité |
| R10 | Le chef (agent) qui pilote via `jarvis mission` sans terminal humain | faible | moyen | décisions, enrôlement et exécution réservés à `_human_only` (test) | sécurité |
