# Déploiement hybride — PROPOSED

Décision 13 du fondateur : **Jarvis Studio Cloud + exécutants locaux + exécutants hébergés**. Ce document est une
architecture, pas une permission de provisionner quoi que ce soit de payant.

## Répartition

| Hébergé par Jarvis Cloud | Sur l'exécutant |
| --- | --- |
| identité, organisations, membres, sessions web | CLI officiels Claude Code / Codex et **leurs** authentifications |
| missions, tâches, baux, approbations, budgets, audit | worktrees, dépôts, fichiers de travail |
| métadonnées d'artefacts, connaissance du tenant | exécution, limites de ressources, journal local des résultats |
| routage, politique, gouverneur de budget | aucun secret d'un autre tenant ; aucun accès à la base |

## Trajectoire

1. **Aujourd'hui (M1)** : tout sur l'ASUS — plan de contrôle = module Python + SQLite, exécutant = même processus.
2. **M2** : Studio + API + PostgreSQL **locaux** (Docker ou paquets WSL, à décider : D-2), toujours sur l'ASUS.
3. **M3** : exécutant séparé par le protocole réseau (connexion sortante) — d'abord sur la même machine, puis une
   station Linux. Le plan de contrôle peut alors quitter le portable.
4. **M7** : hébergement cloud et exécutants hébergés (conteneurs), seulement après autorisation et budget.

## Contraintes tenues dès maintenant

- Un exécutant n'expose aucun port ; il appelle le plan de contrôle.
- Le profil de déploiement de chaque exécutant (`PERSONAL_LOCAL`, `CUSTOMER_OWNED_RUNNER`, `COMMERCIAL_HOSTED`)
  conditionne les connexions fournisseurs utilisables (`COMMERCIAL_COMPLIANCE.md`).
- Disponibilité honnête : le service peut être disponible alors que Claude ou Codex ne le sont pas ; l'état des
  missions est durable, une conversation de modèle interrompue ne se récupère pas — on reprend la tâche, pas la
  conversation. Aucun « 100 % de disponibilité » n'est promis.
