# Board « sans latence » — fondations de données

Lot `feat/board-fondations`. Objet : corriger les défauts de données relevés par l'audit du Board (canevas de cartes),
**sans changer le moteur de canevas** (React Flow reste tel quel). Chaque point ci-dessous cite le test qui le prouve.
Les chiffres viennent de `outils/mesurer_board.py`, lancé sur ce poste avant et après le lot (voir « Mesures »).

Base du lot : commit `57de096` (`feat/chef-multi-moteur`), le seul où la suite compte 788 tests verts au départ.

## Ce qui change, point par point

### 1. Synchronisation incrémentale (plus de rechargement complet à chaque événement)

Avant : `Board.tsx` relisait tout le Board à chaque événement SSE, de n'importe quel espace, et toutes les 10 s.

Maintenant :

- Chaque événement `board_*` du journal porte de quoi appliquer un delta : `objet_id` (ou `objets`, ou `lien_id`),
  `espace`, et la `version` après l'écriture (`lib/jarvis/missions.py::_evenement`, colonne `evenements.espace`).
- Nouvelle lecture ciblée `GET /api/v2/objets?ids=BO-…,BO-…&liens=BL-…&espace=…` (`board.lire`) : les objets demandés,
  les relations qui les touchent, et `absents` (ce qui n'est plus dans ce Board). 200 identifiants au plus,
  identifiants validés, même session exigée que le reste de l'API.
- Le client (`studio/board-v2/src/donnees/synchro.ts`) décide par événement : rien (autre espace, version déjà
  connue = écho de sa propre écriture), retrait local (suppression), ou relecture d'UNE carte ; les relectures
  proches sont regroupées en une requête (60 ms). L'avancement d'une mission ne relit que les cartes de cette mission.
- Relecture complète seulement : au démarrage ; trou détecté dans le flux ; resynchronisation demandée par le
  serveur ; reconnexion après coupure franche. **Mode dégradé** : tant que le flux n'est pas connecté (réseau ou
  proxy qui bloque le SSE), le Board est relu toutes les 10 s, onglet visible — c'était le comportement d'avant en
  permanence, c'est maintenant l'exception. Flux connecté : aucune relecture périodique.

Preuves : `tests/test_board_fondations.py` (`VersionsTest.test_chaque_evenement_du_board_porte_identifiant_espace_et_version`,
`DeltaTest`, `ApiFondationsTest.test_lecture_ciblee_par_l_api`), `src/donnees/synchro.test.ts`,
`tests/e2e/fondations.spec.ts` (« un seul chargement complet… » : une seule requête `/api/v2/board` en plus de 11 s
d'activité, créations / modifications / suppressions distantes comprises).

### 2. Le flux ne rejoue plus l'historique

- `GET /api/v2/board` rend `curseur` : le numéro du dernier événement, lu **avant** les données.
- Le client ouvre `/api/flux?apres=<curseur>&espace=<espace>` ; à la reconnexion le navigateur envoie
  `Last-Event-ID`, qui l'emporte sur `?apres=`.
- Filtre par espace **côté serveur** (`evenements.espace`, NULL = événement qui concerne tous les Boards : missions,
  tâches, réglages).
- Chaque message d'un flux filtré porte `prec` (numéro du message précédent du flux) : le client vérifie la
  continuité (`src/donnees/flux.ts`). Des messages `event: curseur` font avancer le point de reprise quand tout ce
  qui est récent concernait d'autres Boards ; `event: resync` demande une relecture quand la reprise est impossible
  (curseur au-delà du journal) ou trop lointaine (plus de 2 000 événements de retard).
- Le sondage est gardé (les écritures viennent aussi du démon, des exécutants et de la CLI, dans d'autres
  processus) mais ne coûte presque plus rien : une connexion par flux, et sur SQLite un tour à vide ne lit aucune
  table (`PRAGMA data_version`, `missions.LecteurEvenements`). L'intervalle passe de 0,5 s à 0,25 s.
- L'activité récente affichée dans le panneau est lue une fois (`GET /api/evenements?dernier=200&espace=…`).
- Rétrocompatibilité : sans `espace`, `/api/flux?apres=0` rend exactement le format d'avant (Studio V1).
  `apres=fin` = « à partir de maintenant » (utilisé par les vues produit, qui rejouaient tout le journal).

Preuves : `ApiFondationsTest.test_chargement_avec_curseur_et_flux_qui_ne_rejoue_pas_l_historique`,
`…test_flux_filtre_par_espace_cote_serveur_avec_curseur_et_chaine_prec`,
`…test_flux_reprise_par_last_event_id_resync_et_fin`, `…test_studio_v1_inchange`,
`LecteurTest.test_tour_a_vide_sans_requete_puis_reprise`, `src/donnees/flux.test.ts`.

### 3. Requêtes N+1

`board.objets()` faisait un COUNT de commentaires par carte et six requêtes par carte mission. Il fait maintenant
un nombre **constant** de requêtes (11 sur le jeu de mesure), par agrégats groupés (`board._completer`,
`board._resumes_missions`). Même contenu qu'avant, vérifié champ par champ. `missions.board()` (Studio V1) et
`board.lire()` sont constants aussi.

Preuves : `RequetesConstantesTest` (trace SQLite : même nombre de requêtes pour 10 et 500 cartes ; contenu identique).

### 4. Schéma appliqué une fois, index

- `BackendSQLite.connecter` n'exécute plus `executescript(_SCHEMA)` à chaque connexion. Le schéma est préparé une
  fois par processus et par fichier (`_preparer`), sous verrou ; les `ALTER TABLE` et les index passent sous
  `BEGIN IMMEDIATE` après relecture de l'état réel de la base : sûr quand plusieurs processus démarrent ensemble.
  Un fichier remplacé dans le dos du processus est détecté (cookie de schéma) et repréparé.
- En cherchant, un défaut plus ancien est apparu : `PRAGMA journal_mode=WAL` n'attend pas les verrous, et huit
  processus ouvrant ensemble une base d'avant échouaient (« database is locked »). Il est réessayé.
- Index ajoutés : `board_objets (tenant_id, espace, supprime)`, `(tenant_id, mission_id)`, `(tenant_id, travail_ref)` ;
  `board_liens (tenant_id, espace, supprime)`, `(tenant_id, source_id)`, `(tenant_id, cible_id)` ;
  `board_commentaires (tenant_id, objet_id, cree)` ; `evenements (tenant_id, mission_id, type)` (celui sur
  `(tenant_id, seq)` existait) ; `taches`, `tentatives`, `artefacts`, `approbations` par mission ou tâche.
- Les mêmes colonnes et index sont dans `services/controle_pg/controle_pg/schema.sql`.
- **Retour arrière possible** : ces ajouts sont compatibles avec le code plus ancien (colonnes facultatives, index).
  `SCHEMA_VERSION` reste 4 ; ils sont suivis à part (`meta.schema_ajouts`). Une version antérieure de Jarvis rouvre
  la même base sans refus.

Preuves : `SchemaTest` (une préparation pour 25 connexions ; aucune instruction DDL sur une connexion ordinaire ;
index présents et utilisés d'après `EXPLAIN QUERY PLAN` ; migration d'une base existante sans perte ; huit processus
concurrents sur une base v1 ; parité SQLite / PostgreSQL), `tests/test_controle_pg.py` rejoue les classes du lot
sur PostgreSQL réel.

### 5. Conflits : plus de « dernière écriture gagne »

Serveur :

- `missions.board_deplacer` incrémente la version et accepte `version` (409 si périmée).
- Les relations ont une version (`board_liens.version`) ; `board.modifier_lien(version=…)` refuse une version périmée.
- `board.supprimer_detail(versions={id: version})` : si une carte a changé depuis, **rien** n'est supprimé (409).
- `mettre_a_jour_lot` rend `code: "conflit"` pour que le client distingue un conflit d'un refus métier.
- Sans `version`, tout se comporte comme avant (Studio V1, `jarvis board …`).

Front (`src/donnees/ecritures.ts`) : toutes les écritures passent par une file. Chacune est appliquée tout de suite à
l'écran, envoyée avec la version connue, une à la fois (deux gestes rapides sur la même carte s'enchaînent). Sur 409 :
la carte est relue. Si les champs que l'on voulait changer n'ont pas bougé côté serveur (quelqu'un a changé autre
chose), l'écriture est rejouée **une fois** sur la nouvelle version ; sinon elle est annulée, la carte reprend
l'état du serveur et un message le dit. Suppression et relations suivent la même règle.

Preuves : `VersionsTest`, `ApiFondationsTest.test_conflits_409_objets_deplacement_relations_suppression`,
`src/donnees/ecritures.test.ts` (17 cas), `tests/e2e/fondations.spec.ts` (« conflit… »).

### 6. `travail_board.py` : plus de `meta LIKE '%…%'`

Colonne `board_objets.travail_ref`, indexée `(tenant_id, travail_ref)`, tenue à jour à chaque écriture de `meta`
(`board_ajouter`, `board.mettre_a_jour`, `travail_board._carte`). Migration douce des cartes existantes : sur SQLite
à la préparation du schéma, sur PostgreSQL au premier passage du module (`travail_board.migrer_references`).
Effet de bord corrigé : avec `LIKE`, une référence contenant `%` ou `_` pouvait trouver une autre carte.

Preuves : `ReferenceTest`, `SchemaTest.test_migration_d_une_base_existante…`, `tests/test_travail_social.py` (inchangé, vert).

### 7. Monolithe front

`Board.tsx` (763 → 710 lignes : la vue et ses interactions) ne parle plus au réseau pour ses cartes. Couche de données dans
`studio/board-v2/src/donnees/`, sans React (sauf le branchement) :

| Module | Rôle |
|---|---|
| `store.ts` | store normalisé (objets et relations par id) ; vue = état serveur ⊕ écritures en attente |
| `ecritures.ts` | file d'écritures optimistes versionnées, retour arrière, résolution des conflits |
| `flux.ts` | client SSE : reprise au curseur, continuité, réouverture, mode dégradé |
| `synchro.ts` | d'un événement au plus petit changement ; lectures regroupées et ordonnées |
| `useBoard.ts` | branchement sur React (`useSyncExternalStore`) |
| `essais.ts` | doubles de test (faux serveur à versions, faux flux, horloge) |

Tests unitaires : vitest ajouté (`npm test`), 61 tests. Non-régression visuelle : captures Playwright existantes.

### 8. Bouton « Mind map »

Il créait un dossier. Il s'appelle maintenant « Dossier » (icône dossier) ; le comportement ne change pas.

## Mesures

`python3 outils/mesurer_board.py --cartes 10 500 5000 --json` — base SQLite temporaire, jeu réaliste (10 % de
cartes mission avec tâche, 10 % avec fichier, 20 % commentées, une relation pour deux cartes). Médianes, même poste.

| Mesure | Avant (`57de096`) | Après |
|---|---|---|
| `board.objets()`, 10 cartes | 0,61 ms · 19 requêtes | 0,70 ms · 11 requêtes |
| `board.objets()`, 500 cartes | 12,0 ms · 852 requêtes | 4,6 ms · 11 requêtes |
| `board.objets()`, 5 000 cartes | 603 ms · 8 502 requêtes | 44 ms · 11 requêtes |
| Ouvrir puis fermer une connexion | 0,29 à 0,31 ms (schéma réexécuté) | 0,07 à 0,08 ms |
| Un tour de sondage du flux, rien de neuf | 0,32 ms (connexion, schéma, requête) | 0,002 ms (`LecteurEvenements`) |
| Relire une carte après un événement, Board de 5 000 cartes | 603 ms (le Board entier, 3,2 Mo) | 2,1 ms · 10 requêtes (lecture ciblée d'une carte mission) |
| Retrouver une carte de travail par sa référence, 500 / 5 000 cartes | 0,053 / 0,431 ms (`meta LIKE`) | 0,005 / 0,007 ms (index) |
| Taille de la réponse complète, 500 / 5 000 cartes | 315 Ko / 3 163 Ko | 318 Ko / 3 197 Ko (inchangée, + `curseur` et `version`) |

Lecture honnête de ces chiffres :

- Le gain vient surtout du nombre de requêtes et des index : sans index, le COUNT de commentaires par carte
  parcourait la table entière, d'où le coût plus que proportionnel à 5 000 cartes (603 ms).
- À 10 cartes, la lecture est un peu plus lente qu'avant (0,70 contre 0,61 ms) : onze requêtes fixes au lieu de
  dix-neuf petites. Sans importance à cette taille.
- Un second passage de la mesure donne 6,9 ms à 500 cartes et 43 ms à 5 000 : l'ordre de grandeur est stable, la
  décimale ne l'est pas (poste partagé avec d'autres travaux pendant la mesure).
- Côté navigateur, ce qui change le plus n'est pas dans ce tableau : avant, **chaque** événement et chaque tranche
  de 10 s coûtaient une relecture complète (ligne « `board.objets()` » + transfert + reconstruction de tous les
  nœuds) ; maintenant un événement coûte la lecture d'une carte, et rien du tout s'il vient d'un autre Board ou de
  sa propre écriture. Le test Playwright compte une seule requête `/api/v2/board` sur plus de 11 s d'activité.
- Non mesuré : le temps de rendu de React Flow, le débit réseau réel, PostgreSQL (le script mesure SQLite).

## Tests exécutés

Exécutés sur ce poste (WSL2, Python 3.14, Node 22, PostgreSQL local disponible), sur l'état final de la branche :

| Suite | Commande | Résultat |
|---|---|---|
| Python | `python3 -m unittest discover -s tests` | 841 tests, 0 échec, 0 erreur, 5 ignorés (788 tests, 3 ignorés au départ) |
| Front, unitaires | `cd studio/board-v2 && npm test` | 61 tests, 4 fichiers, tous verts |
| Front, types et build | `npm ci && npm run build` | sans erreur ; build régénéré dans `lib/jarvis/studio_v2/` |
| Front, Playwright | `npx playwright test` | 50 tests, tous verts (47 existants dont les captures visuelles, 3 nouveaux) |
| Shell | `bash -n install.sh bin/jarvis`, `bin/jarvis help` | sans erreur |

Précisions :

- Les 53 tests Python ajoutés : 30 dans `tests/test_board_fondations.py`, et 23 de ces tests rejoués sur
  PostgreSQL réel par `tests/test_controle_pg.py`. Les 2 ignorés en plus sont des tests propres à SQLite (trace des
  requêtes) qui n'ont pas de sens sur PostgreSQL.
- Playwright a tourné sur le port 7741 (`JARVIS_E2E_PORT`), le port 7721 étant occupé par un autre processus du
  poste ; d'où les deux variables d'environnement ajoutées à la configuration. Les captures de référence n'ont pas
  été modifiées : le changement de libellé « Mind map » → « Dossier » reste sous le seuil de tolérance existant.
- Deux régressions ont été attrapées par les tests existants pendant le lot, puis corrigées : la carte ajoutée
  « même si le SSE est coupé » (d'où le mode dégradé du point 1) et « supprimer puis annuler » enchaînés sans
  attendre (l'entrée d'historique est maintenant posée au moment du geste).
- `shellcheck` n'est pas installé sur ce poste : non exécuté.
- Non exécuté : un essai sur une vraie installation en service (base réelle, démon, Telegram) ; un essai à deux
  navigateurs réels (le conflit est simulé dans Playwright par une écriture faite par l'API pendant que la page est
  privée de flux) ; une mesure de charge sur PostgreSQL.

## Limites connues

- **PostgreSQL** : le schéma doit être réappliqué (`cd services/controle_pg && python3 -m controle_pg preparer`)
  avant d'utiliser ce code, sinon les écritures échouent (colonnes `evenements.espace`, `board_liens.version`,
  `board_objets.travail_ref`). Sur PostgreSQL, deux transactions peuvent valider leurs événements dans le désordre
  des numéros : un événement validé en retard peut échapper à un flux déjà passé (le sondage d'avant avait la même
  faille). SQLite n'est pas concerné (un seul écrivain à la fois).
- **Détection de trou** : `prec` détecte une chaîne rompue entre le serveur et le client (message perdu, reprise au
  mauvais endroit), pas un événement que le serveur n'aurait jamais lu (cas PostgreSQL ci-dessus).
- **Processus restés sur l'ancien code** (démon non redémarré) : leurs événements n'ont ni espace ni version. Le
  client relit alors la carte citée (le serveur tranche) ; c'est correct mais moins économe. Redémarrer le démon.
- **Studio V1** (`/`, `studio_board.js`) : inchangé par contrainte de compatibilité ; il ouvre toujours le flux à
  `?apres=0` et rejoue le journal.
- **Autres `meta LIKE`** : `missions._poser_livrable` et `vie_sociale` cherchent encore `livrable_de` dans `meta`
  (hors du périmètre demandé ; même correction possible avec une colonne).
- **Rejeu automatique sur conflit** : comparaison champ par champ ; `meta` est un seul champ (hors clés du chef).
  Deux personnes qui modifient des étiquettes différentes de la même carte au même instant : la seconde est annulée
  et doit refaire son geste.
- **Annuler / rétablir** : l'historique rejoue les écritures par la même file versionnée ; si la carte a changé
  ailleurs entre-temps sur les mêmes champs, l'annulation est refusée (message), elle n'écrase rien.
- **`Board.tsx` reste gros** (710 lignes) : les données en sont sorties, pas encore les interactions (glisser,
  ingestion, raccourcis), qui pourraient devenir des hooks séparés.
- **Moteur de canevas** : inchangé. 5 000 cartes sont maintenant servies en un temps raisonnable, mais leur rendu
  par React Flow n'a pas été travaillé dans ce lot.
- **Réponse complète** : le chargement initial envoie toujours tout le Board (contenu des artefacts compris) ;
  pas de pagination ni de chargement par zone visible.
