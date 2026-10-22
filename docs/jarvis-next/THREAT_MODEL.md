# Modèle de menaces — PROPOSED

Hypothèse : tout exécutant peut être compromis ; le plan de contrôle et l'exécutant local sont deux cibles
distinctes ; un modèle peut être manipulé par le contenu qu'il lit.

| Menace | Mesure en place (M1) | Résidu / prochaine mesure |
| --- | --- | --- |
| Injection de prompt par le contenu analysé | document délimité comme donnée, délimiteur non fermable ; **aucun outil** ; niveau L1 sans effet externe ; revue déterministe ; vérifié en réel (injection signalée, non suivie) | un modèle peut quand même mal résumer : la revue vérifie la forme, pas la vérité |
| Instructions malveillantes dans un dépôt | CURRENT : worktrees, règles deny, bac à sable Codex | exécutants en conteneur (M3) |
| Outil compromis | analyse sans outils ; skills épinglées (CURRENT) | inventaire signé des outils (M4) |
| Exécutant compromis | API étroite, secret haché, révocable, tenant fixé, résultat validé et borné, jeton de clôture | sur l'ASUS il partage l'utilisateur Linux avec la base : séparation réelle en M3 |
| Accès inter-tenant | filtres par tenant + tests | RLS PostgreSQL (M2) |
| Exfiltration d'identifiants | aucun identifiant stocké par les missions ; clés payantes retirées en mode abonnement ; secrets par rôle (CURRENT) | coffre de secrets côté exécutant (M3) |
| Empoisonnement d'artefacts | empreinte SHA-256, revue, marque « factice » | provenance signée (M5) |
| Chaîne d'approvisionnement | aucune dépendance ajoutée | verrouillage des versions pour les services M2 |
| Exécution de code non autorisée | L2+ jamais automatique sans politique | — |
| Délégation récursive | profondeur, largeur, total bornés | budget de délégation par mission (M4) |
| Ressources excessives | délai par tâche, bail, contenu ≤ 200 000 caractères, 50 tâches/mission | plafonds de processus (BLOCKED, `docs/autonomy/securite.md`) |
| Usurpation d'approbation | acteur humain exigé, ≠ demandeur, empreinte du travail | approbation signée côté Studio (M2) |
| Rejeu, doublons | clé d'idempotence, jeton de clôture, unicité par tentative | idempotence des effets externes (M4) |
| Configuration générée par un agent | les réglages L3/L4 automatiques sont ignorés par le code | politique signée (M4) |
| Fuite par les journaux | événements sans contenu de document ni secret | expurgation systématique (OBSERVABILITY) |
| Déploiement non autorisé | aucun déploiement dans M1 | M6, environnements jetables seulement |
| Compromission du plan de contrôle | — (local) | sauvegardes, audit externe, rotation des certificats (M3/M7) |
