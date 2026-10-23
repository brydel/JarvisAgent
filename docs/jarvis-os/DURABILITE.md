# Reprises des décisions et des remises — F1

## Changements livrés

La décision d'une proposition du Board écrit désormais sa mission, sa tâche, sa carte, sa relation, le statut
de la proposition, les événements et l'intention de notification dans une seule transaction. Dix décisions
concurrentes créent une seule mission, une seule carte et une seule relation ; les autres reçoivent un conflit.
Un arrêt avant le commit annule tout le changement. Une action proposée L2/L3 reste une préparation L1.

Les résultats de contextualisation et les livrables écrivent leurs intentions dans `effets_outbox` avec leur
résultat métier. Les fonctions à appeler ne sont plus conservées en mémoire : seules des destinations connues
et des charges JSON bornées sont persistées. La file mémoire de notifications de `synchro.py` est supprimée.

Le répartiteur prend un effet sous bail, ferme la transaction avant sa remise, puis conserve son acquittement.
Une intention locale interrompue est reprise après expiration du bail. Les reprises utilisent des clés stables,
un reçu inbox pour les décisions et une marque persistée pour les ajouts mémoire. Une ancienne génération
d'analyse ne lance jamais les propositions de la nouvelle ; désactiver les actions automatiques empêche aussi
les anciennes intentions de les lancer.

Le producteur et le consommateur vérifient tous deux la mission courante de la carte. Une ancienne analyse
terminée après sa relance conserve son artefact sans écraser la nouvelle projection. Les notifications gardent
un instantané borné du contexte et de la décision ; leurs titres ne sont pas relus depuis un index mutable.
Une action automatique annoncée comme lancée est rapprochée de son reçu de décision de la même génération.

La file du chef est persistée avant chaque tentative et acquittée une entrée à la fois après `tmux send-keys`.
Les anciens fichiers contenant une liste de textes sont conservés. Les messages d'outbox portent un identifiant
stable ; leurs reçus restent dans la file et dédoublonnent les reprises du producteur. Un fichier corrompu est
refusé et conservé. Les états JSON et SQLite sont vérifiés.

## Exploitation et états

`missions.traiter_outbox(tenant_id=None, limite=20, now=None, sortes=None, interrompu=None)` exécute un passage
borné et retourne `remis`, `replanifies`, `echecs`, `inconnus`, `traites`. Le démon l'appelle depuis un fil dédié.
Les passages du moteur traitent seulement les projections locales pour ne pas attendre Telegram. Le callback
`interrompu` est vérifié avant la prochaine prise et avant sa remise ; une prise non expédiée est rendue sans
consommer d'essai.

`missions.etat_outbox(tenant_id, limite=100)` retourne les comptes et descriptions sans le contenu des messages.
Après cinq échecs sûrs, un effet reste inspectable en `echec`. Une relance explicite passe par
`missions.relancer_effet(tenant_id, effet_id, par=..., confirmer_inconnu=False)` et écrit un événement d'audit.

Un échec ou une interruption après une tentative Telegram laisse l'état `inconnu` : le fournisseur a pu agir.
Aucune répétition automatique n'est faite. Vérifier le destinataire avant de demander une relance avec
`confirmer_inconnu=True`. Une réponse réussie conserve seulement le reçu minimal `message_id`, sans recopier
le profil Telegram. Une absence de configuration, avant tout appel, est un échec sûr pouvant être réessayé.

## Limites des garanties

L'acquittement du chef signifie « remis à la file durable / tapé dans tmux », pas « compris par le modèle ».
Un arrêt après la frappe mais avant l'écriture du reçu peut encore répéter la ligne. Les entrées du fil d'activité
peuvent également apparaître plusieurs fois après une interruption. Les identifiants d'opération les relient.
Aucune garantie de remise externe exactement une fois n'est revendiquée.

Les créations initiales d'objets et de contextualisations du Board utilisent encore leurs anciennes frontières
de transaction ; cette tranche corrige l'acceptation des propositions et les effets des résultats, pas ces autres
chemins. Les écritures externes générales et leurs rapprochements fournisseur relèvent de JOS-007.

Le schéma 4 ajoute seulement les tables `effets_outbox` et `effets_inbox`. SQLite les crée à l'ouverture.
PostgreSQL exige l'application du schéma du service `controle_pg` par son rôle d'administration ; ses tables
portent les mêmes politiques RLS. La suite locale valide SQLite ; aucune connexion PostgreSQL réelle n'a été
utilisée pour cette tranche.

## Preuves reproductibles

```bash
python3 -m unittest discover -s tests -p 'test_durabilite.py'
python3 -m unittest discover -s tests -p 'test_board_v2.py'
python3 -m unittest discover -s tests -p 'test_missions.py'
python3 -m unittest discover -s tests -p 'test_jarvis.py'
```

Résultats ciblés : 30 tests de durabilité, 64 tests Board et 39 tests missions réussis ; suite Jarvis historique
84 exécutés, 81 réussis et 3 ignorés. Les envois Telegram sont simulés dans ces tests.
