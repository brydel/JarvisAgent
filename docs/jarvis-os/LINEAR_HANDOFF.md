# Créer le projet dans une session connectée à Linear

La création du projet et des tickets est autorisée par le propriétaire. Ce fichier pallie l'absence d'accès
Linear dans la session de préparation ; il ne constitue pas une preuve de création. Ne jamais demander un
jeton dans le chat ni remplir le manifeste avec des identifiants inventés.

Le fichier `linear-issues.csv` peut être importé en mappant ses colonnes dans Linear. Cet import ne pose pas
automatiquement les relations de dépendance : leur source est `linear-project.json`. Pour créer le projet,
ses phases et ses relations de façon complète, utiliser le brief suivant dans Claude Code/Codex avec un
serveur MCP Linear déjà connecté, ou dans une conversation disposant du connecteur Linear.

```text
Crée dans Linear le projet personnel décrit dans docs/jarvis-os/linear-project.json.
L'utilisateur a expressément autorisé le projet et les tickets ; ne redemande pas cette autorisation.

1. Lis AGENTS.md puis docs/jarvis-os/PLAN.md, ARCHITECTURE.md, SESSIONS.md et linear-project.json.
   Vérifie que Linear est réellement connecté et identifie les équipes accessibles. Réutilise une équipe
   Jarvis existante ou l'unique équipe accessible ; si plusieurs équipes restent plausibles, demande
   seulement l'équipe cible. Aucun secret ni jeton dans le chat ou les fichiers du dépôt.
2. Recherche le projet exact « Jarvis OS personnel — autonomie de bout en bout ». S'il existe, réutilise-le.
   Sinon, crée-le avec objectif, portée personnelle et phases F0 à F6. Ne crée pas un produit commercial.
3. Pour chacun des 30 tickets du manifeste, recherche dans ce projet le marqueur stable [JOS-xxx]. Crée
   seulement les tickets manquants avec objectif, critères, responsable agent et relecteur dans la description.
   Les clés JOS-xxx sont locales : conserve-les comme marqueurs et enregistre les vrais IDs Linear à part.
   Mappe la priorité : 1 urgent, 2 haut, 3 normal. Les rôles agents sont des étiquettes/attributions de session,
   pas des utilisateurs Linear fictifs ; n'invente pas d'assigneeId. Choisis un utilisateur uniquement si une
   correspondance réelle et autorisée est disponible.
4. Crée les relations bloque/est bloqué par d'après depends_on et les jalons si le connecteur les supporte.
   Si une opération n'est pas supportée, conserve précisément la liste des relations à compléter.
5. Relis le projet, les tickets et leurs dépendances après écriture. Mets à jour project_id/project_url,
   team_id, linear_issue_id/linear_url seulement avec les valeurs réellement retournées et vérifiées.
   N'annonce pas la création complète tant qu'une partie reste en échec. Préserve les travaux existants.
6. Retourne le lien du projet, le nombre de tickets créés/réutilisés et les éventuels blocages. Les trois
   premiers tickets sont prêts pour des sessions spécialisées : JOS-001 architecture agentique,
   JOS-002 politique d'autonomie personnelle, JOS-003 SRE/capacités. Les suivants attendent leurs dépendances.

Cette action crée le plan dans Linear. Les 30 sessions de réalisation ne sont pas lancées d'un seul coup.
Leur responsable, relecteur, spécialité et critères figurent dans SESSIONS.md et chaque ticket.
```

Après création vérifiée, passer le statut du manifeste à `created_in_linear` ; si certaines écritures ou
relations restent manquantes, conserver un état partiel documenté. Une relance doit réconcilier l'existant,
pas dupliquer le projet, ses tickets ou ses dépendances.
