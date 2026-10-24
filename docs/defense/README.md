# Jarvis Défense — premier lot en observation

Ce lot fournit un moteur déterministe utilisable sur un fichier explicitement fourni,
une commande CLI et un outil sous mandat. Il ne constitue pas une protection opérationnelle.
Il ne collecte rien, ne lance aucun modèle et ne modifie aucun système.

## Base et intégration

Base : `integration/redteam-live`, commit `12a620909ce5feca9337c67933a0918db8fe87ab`.
Cette base conserve les extensions agents/outils et le nettoyage public PR12 ; `main`
ne les contient pas toutes. Aucun fichier de preuves privées supprimé n'est réintroduit.
Les skills de cette base se trouvent dans `skills/` ; `.agents/skills` est absent.

`lib/jarvis/defense.py` est le moteur. Le CLI existant l'expose via :

```bash
bin/jarvis defense triage docs/defense/exemples/auth-synthetique.jsonl
python3 -m unittest discover -s tests -p test_defense.py -v
```

Le catalogue `outils.catalogue()` expose `security.auth_triage`, schéma
`{"journal":"texte du lot"}`. `outils.executer()` conserve les contrôles de mandat,
les quotas et le rejeu idempotent par `operation_id`. Le mandat doit autoriser cet outil,
le projet exact et `destinations: []` (calcul local sans destination). Aucun mandat
n'est créé automatiquement. La passerelle stocke son empreinte de requête et le rapport
expurgé, pas les arguments bruts. Ne placer aucune donnée privée dans les métadonnées
de contrôle (projet, acteur, identifiant d'opération).

`agent.json` réutilise AgentSpec v1 : rôle défensif, un seul outil, coût et jetons nuls,
aucune délégation. Ce descripteur n'active pas une boucle cognitive et ne donne aucun
droit. La capacité déclarée désigne uniquement le calcul sur le lot fourni : elle
n'atteste aucune disponibilité d'un poste réel. Le runtime LLM n'est pas invoqué.
Le RedTeam garde son rôle d'audit et de revue indépendante ; aucune duplication de
son transport, de sa collecte ou de sa publication communautaire.

## Entrées et normalisation

UTF-8, 64 000 octets maximum, 200 lignes maximum, 2 048 octets par ligne.
Fichier ordinaire uniquement (pas de lien, FIFO ou périphérique). CLI : code 1 en cas
de fichier illisible, encodage invalide ou limite globale dépassée ; code 0 pour un
rapport, même incomplet. Vérifier toujours `couverture` et `statut`.

Deux formats peuvent coexister :

- JSONL : champs obligatoires `timestamp`, `kind`, `host`, `source`, `account` ;
  `message` facultatif et ignoré. Aucun autre champ ni clé JSON dupliquée.
- Ligne SSH stricte : date ISO avec fuseau, hôte, `sshd[pid]: Failed password for … from … port … ssh2`
  (également `Accepted`, `publickey`, `invalid user`, pid et suffixe ssh2 facultatifs).

Dates ISO avec fuseau converties en UTC ; types autorisés `auth_failure` et
`auth_success`. Identifiants non vides, sans espaces/contrôles, 128 caractères maximum.
Les lignes non reconnues sont comptées invalides et ne deviennent jamais des preuves.
Le syslog historique sans année/fuseau n'est pas interprété. Aucun shell, template,
interpréteur de commandes ou fournisseur ne reçoit le texte des journaux.

## Règles et preuves

- AUTH-001 : au moins cinq échecs uniques dans une fenêtre inclusive de 300 secondes,
  pour le même triplet source/compte/hôte. Gravité moyenne.
- AUTH-002 : mêmes échecs puis succès strictement ultérieur, tous dans la fenêtre de
  300 secondes terminée par le succès. Gravité élevée ; remplace AUTH-001 pour ce groupe.

Tri chronologique avant détection. Un événement est unique par date UTC, type et
triplet ; `message` n'entre pas dans l'identité. Une alerte au plus par groupe et par
lot ; pas de mémoire entre fichiers. Deux événements réellement distincts mais
identiques à la même date seront fusionnés : limite explicite de cette version.
Les références `E-<ligne>` pointent dans le lot original (numérotation à partir de 1).
Les alias source/compte/hôte ne sont valables que dans ce rapport. Dates, messages,
secrets et identifiants bruts sont supprimés par projection sur des champs contrôlés,
pas par une liste fragile de motifs de secrets. Les originaux restent privés.

Chaque alerte exprime justification, preuves, incertitude et recommandations à valider.
`intrusion_confirmee` reste toujours faux. Les entrées sont déclaratives et peuvent
être forgées. Une faute de saisie ou une tâche légitime peut déclencher le seuil ;
un attaquant lent, distribué ou hors format peut échapper aux règles. Une absence
d'alerte ne prouve pas l'absence d'intrusion.

## Skills et périmètre futur

`jarvis-defense-triage` guide le moteur ; `jarvis-defense-incident` guide la qualification
et la décision humaine. Les dossiers sont épinglés par le registre existant, non signés,
sans installation ni activation sur un poste. La protection des secrets est intégrée
à la sortie du moteur. La dérive de configuration est différée : aucune baseline
fiable fournie, et aucun accès aux configurations réelles dans ce lot.

Avant un déploiement futur, obtenir un accord distinct sur la machine, les sources,
la collecte minimale, les accès en lecture, la conservation privée et les seuils.
Valider les formats réels et faux positifs sur un lot privé, puis les ressources et
la visibilité du rapport. Examiner séparément toute installation persistante,
automatisation, connexion Jetson, intégration modèle ou remédiation. Rien de cela
n'est activé ici. Ne jamais publier inventaire, versions installées ou preuves du Lab.

Préparer une reprise locale avec le [guide WSL](REPRISE_WSL.md), sans remplacer
le checkout installé ni promettre l’absence de conflits sur un poste non inspecté.
