# Bibliothèque de références du Board

Le premier RAG de Jarvis, **local d'abord**. Tu captures des sites (et des textes), Jarvis en garde les captures
d'écran, le texte découpé par sections, la palette, les polices et la structure, puis retrouve des **passages
cités** : référence, adresse d'origine, section, extrait surligné, date de capture, lien vers la zone de la capture.

Tout reste sur ton poste : base des missions (SQLite par défaut), fichiers dans le magasin d'assets du Board.
La recherche par mots fonctionne **sans aucun fournisseur d'IA**. Les vecteurs sont une option, calculée par un
modèle local, et tout se ré-indexe si tu changes de modèle.

## En deux minutes

```bash
jarvis reference ajouter https://exemple.com --collection inspiration --etiquette saas sombre
jarvis reference chercher "tarifs affichés sans astérisque" --collection inspiration -n 5
jarvis reference liste
jarvis reference voir RF-…            # fiche : palette, polices, structure, sections, fichiers
jarvis reference voir FR-…            # un fragment entier, pour citer plus long que l'extrait
jarvis reference ajouter --texte notes.md --titre "Charte" --collection marque
jarvis reference reindexer [RF-…]     # après un changement de découpage ou de modèle de vecteurs
jarvis reference supprimer RF-… · jarvis reference restaurer RF-…
```

Dans le Studio (`jarvis mission studio`), l'onglet **Références** remplace l'ancien écran « Connaissances »
(l'adresse `?vue=connaissances` y mène toujours) : grille avec vignette, palette et polices ; filtres par collection
et étiquette ; recherche à la frappe ; fiche avec captures bureau et mobile côte à côte ; bouton **Poser sur le
Board**, qui crée une carte reliée à la référence (`meta.reference_id`).

La sortie de `chercher` est faite pour être citée par un agent :

```
[1] FR-9510b57d02df · Typographie — Wikipédia (RF-d3b9f976c848) · section « Caractères »
    source : https://fr.wikipedia.org/wiki/Typographie · capturé le 2026-11-11 · collection « typographie »
    extrait : … Les premiers **caractères** **mobiles** utilisés en Corée et en Chine étaient fabriqués en terre cuite …
    capture : /api/v2/fichiers/AS-cb3c510df9a5 (zone y=2522, hauteur=952)
    à citer : [RF-d3b9f976c848#FR-9510b57d02df] Typographie — Wikipédia — https://fr.wikipedia.org/wiki/Typographie (capturé le 2026-11-11)
```

`--json` rend la même chose en JSON (`resultats[].fragment_id`, `.citation`, `.extrait.surlignages`).

## Architecture

| Fichier | Rôle |
| --- | --- |
| `lib/jarvis/rag.py` | Briques pures : normalisation, découpage, requête FTS5, BM25 de repli, `Embarqueur`, vecteurs, RRF, extraits |
| `lib/jarvis/capture_site.py` | Garde anti-SSRF, mandataire local, lancement du pilote, validation de ce que la page renvoie |
| `outils/capturer_site.cjs` | Pilote node + Playwright : captures d'écran, extraction dans la page, palette |
| `lib/jarvis/references.py` | Tables, états, indexation, recherche hybride, carte du Board |
| `lib/jarvis/references_api.py` | Routes `/api/v2/references…`, aiguillées par deux blocs de `studio_api.py` |
| `lib/jarvis/references_cli.py` | `jarvis reference …` |
| `studio/board-v2/src/references/` | Vue React (grille, recherche, fiche), styles, jeu de démonstration |
| `tests/test_references.py`, `studio/board-v2/tests/e2e/references.spec.ts` | Tests |

### Ce qu'une capture contient

- quatre images JPEG : vue initiale et page entière, bureau 1440 × 900 et mobile 390 × 844 (page entière bornée à
  12 000 px, signalée « tronquée » au-delà) ;
- titre, description, langue, adresse finale après redirections, date de capture ;
- texte lisible découpé par **sections** : chaque titre h1 à h3 ouvre une section, avec sa position verticale dans
  la capture bureau (le « renvoi vers la zone ») ;
- palette dominante (six couleurs au plus, avec leur part de la vue initiale) et couleurs déclarées (fond, texte,
  accent, liens) ;
- polices réellement appliquées (texte, titres, sous-titres, boutons, code) et polices chargées par le site ;
- structure : en-tête, héros (titre et appel à l'action), contenu principal, pied, nombre d'images, de boutons, de
  formulaires ; quarante liens sortants au plus, ceux du menu et les liens externes d'abord ;
- l'empreinte sha256 de chaque fichier et une empreinte de l'ensemble.

### Stockage

Trois tables, `tenant_id` partout, créées au premier usage sur SQLite et décrites dans
`services/controle_pg/controle_pg/schema.sql` pour PostgreSQL (RLS par tenant, comme le reste) :

- `board_references` : source, type (`site`, `texte`, `carte`), collection, étiquettes, méta (palette, polices,
  structure, liens), contenu par sections, état, raison, suppression douce, version ;
- `board_reference_fragments` : texte découpé, position, section, zone de capture, et pour le vecteur éventuel
  `vecteur` (BLOB float32), `modele`, `dimension`, `version_index` ;
- `board_reference_fichiers` : rôle (`bureau_vue`, `bureau_page`, `mobile_vue`, `mobile_page`) → asset du Board.

Les images passent par `board.enregistrer_fichier` : reconnaissance par les octets, dédoublonnage sha256, service
par `/api/v2/fichiers/AS-…` (authentifié, `nosniff`, CSP `sandbox`).

États : `en_attente → capture → indexation → prete`, ou `echec` avec la raison. Une capture restée « en cours »
plus de dix minutes (Studio arrêté en plein travail) est déclarée en échec à la lecture suivante ; « Recapturer » la
relance. Vingt captures au plus attendent en file ; une seule tourne à la fois.

### Recherche hybride

1. **Mots** : index SQLite FTS5 (`unicode61 remove_diacritics 2`, préfixes 2-3-4) sur le texte désaccentué, la
   section et le titre ; classement `bm25()` pondéré (section × 2, titre × 1,5). La question est réduite à ses
   racines (mots vides retirés, pluriels et e muet coupés) cherchées **en préfixe** et reliées par OR : aucune syntaxe
   FTS venue de l'utilisateur n'est interprétée. Si FTS5 manque (ou sur PostgreSQL), un BM25 en Python pur prend le
   relais avec les mêmes règles, sur 5 000 fragments au plus.
2. **Vecteurs** (optionnels) : la question est vectorisée, comparée par cosinus en Python pur aux fragments du même
   `modele` et de la même `dimension` (5 000 au plus, les plus récents).
3. **Fusion RRF** (`k = 60`) des deux classements. Chaque résultat indique son rang dans chaque moteur.

Sans embarqueur, ou s'il tombe en panne, la réponse arrive quand même : `mode: "bm25"`, `vecteurs: "desactive"`
ou `"indisponible"`. Après une panne, l'embarqueur n'est plus sollicité pendant 60 secondes (la recherche à la
frappe ne paie pas le délai d'attente à chaque touche).

### API (derrière la session du Studio)

Même sécurité que le reste : hôte local, cookie de session, et pour toute écriture l'en-tête `X-Jarvis-Studio: 1`
et une `Origin` locale.

| Méthode et route | Effet |
| --- | --- |
| `GET /api/v2/references[?collection=&etiquette=&q=&corbeille=1]` | Liste, facettes, état du moteur |
| `GET /api/v2/references/recherche?q=…[&collection=&etiquette=&n=]` | Passages classés avec citation |
| `GET /api/v2/references/RF-…` | Fiche et état de la capture |
| `GET /api/v2/references/fragments/FR-…` | Un fragment entier |
| `POST /api/v2/references` `{url \| texte \| objet_id, titre?, collection?, etiquettes?}` | 202 (site : capture lancée hors du fil de la requête), 201 (texte, carte), 200 (déjà présent) |
| `POST /api/v2/references/RF-…` `{titre?, collection?, etiquettes?}` | Modifie |
| `POST /api/v2/references/RF-…/supprimer` `{restaurer?}` | Suppression douce, ou restauration |
| `POST /api/v2/references/RF-…/reindexer` `{recapturer?}` | Ré-indexe, ou relance la capture (202) |
| `POST /api/v2/references/reindexer` | Ré-indexe toutes les références prêtes |
| `POST /api/v2/references/RF-…/poser` `{espace?, x?, y?}` | Crée la carte du Board reliée |

## Sécurité de la capture

Une page web est une source **non fiable**. Trois barrières, indépendantes :

1. **Avant tout lancement** : `http` et `https` seulement, pas d'identifiants dans l'adresse, ports 80 et 443, et
   l'hôte résolu ici doit n'avoir **que** des adresses publiques (ni boucle locale, ni réseau privé, ni lien local,
   ni métadonnées cloud `169.254.169.254`, ni IPv4 encapsulée dans IPv6 — le prédicat est celui de `apercus.py`).
2. **Pendant la capture** : Chromium ne parle qu'à un mandataire local tenu par Jarvis (`MandataireGarde`,
   127.0.0.1, port éphémère). Chaque connexion — page, redirection, image, script, XHR, WebSocket — y est revérifiée
   avec les mêmes règles, puis ouverte **vers l'adresse vérifiée** (résolution épinglée : pas de seconde résolution,
   donc pas de DNS rebinding). Chromium est lancé avec `--host-resolver-rules="MAP * ~NOTFOUND"` (il ne résout
   plus rien lui-même), sans contournement du mandataire pour localhost (`<-loopback>`), sans QUIC, sans UDP WebRTC
   hors mandataire. L'interception des requêtes par Playwright refuse en plus les schémas autres que http(s), les
   hôtes privés écrits en clair, les médias, et tout ce qui dépasse 600 requêtes.
3. **Bornes** : 25 s pour naviguer, 120 s pour tout le pilote (tué avec son groupe de processus au-delà), 80 Mo de
   trafic, 600 connexions, 20 Mo par image, 300 000 caractères de texte, 200 sections, 40 liens.

Isolation du JavaScript de la page : contexte de navigation neuf par gabarit (aucun stockage persistant, aucun
cookie conservé), téléchargements refusés, service workers bloqués, fenêtres surgissantes fermées, dialogues
rejetés, aucune permission. Le bac à sable de Chromium est activé s'il est disponible sur le poste. Le pilote reçoit
un environnement minimal : aucun secret du poste ne lui est transmis.

**Donnée, jamais consigne.** Ce que la page renvoie (titres, textes, liens, couleurs) est revalidé et borné côté
Python, champ par champ. Chaque résultat de recherche, chaque fiche et chaque sortie de la CLI porte
`nature: "donnee_non_fiable"` et un avertissement explicite : un agent cite ce contenu, il ne l'exécute pas. « Poser
sur le Board » ne lance aucune mission sur le contenu capturé.

## Brancher des embeddings locaux (bge-m3 par Ollama)

Désactivé par défaut. Rien n'est téléchargé par Jarvis : le modèle doit déjà être présent sur la machine qui fait
tourner Ollama (par exemple `ollama pull bge-m3`, à lancer toi-même).

Dans `~/.config/jarvis/settings.toml` :

```toml
[references]
embarqueur = "ollama"
ollama_url = "http://127.0.0.1:11434"   # ou l'adresse de ta machine GPU
modele = "bge-m3"
```

ou par variables : `JARVIS_REFERENCES_EMBARQUEUR=ollama`, `JARVIS_REFERENCES_OLLAMA_URL`,
`JARVIS_REFERENCES_MODELE`. Puis `jarvis reference reindexer` : chaque fragment reçoit son vecteur, avec le nom du
modèle et sa dimension (1024 pour bge-m3). Changer de modèle = modifier le réglage et relancer `reindexer` ; les
anciens vecteurs ne sont jamais comparés à ceux d'un autre modèle.

Si Ollama tourne sur une autre machine (la Jetson), `ollama_url` doit être joignable depuis ce poste — par exemple
par un tunnel SSH vers `127.0.0.1:11434`. Ce lot ne configure aucune machine distante.

L'interface `rag.Embarqueur` (un attribut `modele`, une méthode `embarquer(textes) -> vecteurs`) accepte toute
autre source : `references.utiliser_embarqueur(objet)`.

## Passer à PostgreSQL et pgvector

Le schéma PostgreSQL existe (`schema.sql`, RLS, droits du rôle applicatif) et les tests du stockage et de l'API y
sont rejoués. Sur PostgreSQL, aujourd'hui :

- la recherche par mots passe par le **repli Python** ; la colonne `recherche` (tsvector généré, index GIN) est
  déjà là pour une requête native `recherche @@ to_tsquery('simple', …)` avec `ts_rank_cd` ;
- les vecteurs restent en `BYTEA` et sont comparés en Python.

Pour pgvector : `CREATE EXTENSION vector`, ajouter `embedding vector(1024)` à `board_reference_fragments`, le
remplir depuis le `BYTEA` existant (même ordre float32), créer un index HNSW (`vector_cosine_ops`), puis remplacer
`references._par_vecteurs` par `ORDER BY embedding <=> $1 LIMIT 50` quand le backend est PostgreSQL. La fusion RRF
et les citations ne changent pas. La dimension étant fixée par colonne, un changement de modèle demandera une
nouvelle colonne (ou une table de vecteurs par modèle).

## Limites connues

- **Une seule page par référence** : pas d'exploration du site (ajoute chaque page qui compte).
- **Pas de recherche sémantique sans embarqueur** : BM25 trouve ce qui est écrit. Une question en français ne
  trouve pas un site en anglais, ni un synonyme absent du texte. C'est précisément ce que les vecteurs ajoutent.
- **Cosinus en Python pur**, borné à 5 000 fragments : suffisant pour une bibliothèque personnelle (quelques
  centaines de sites), pas pour un grand corpus — c'est là que pgvector prend le relais.
- **Texte de menu** : la première section (« introduction ») contient souvent la navigation du site ; les sections
  viennent des titres h1 à h3, pas d'une analyse de mise en page. Dans une page à colonnes, la zone d'une section
  est approximative.
- **Sites protégés** (mur de cookies, anti-robots, connexion requise) : la capture montre ce qu'un visiteur anonyme
  voit. Aucun contournement.
- **Ports** : seuls 80 et 443 sont acceptés (comme les aperçus de liens).
- **Fichiers** : seuls un texte collé, un fichier texte ou Markdown (CLI) et une carte existante du Board sont
  indexables. Le texte d'un PDF ou d'une image n'est pas extrait dans ce lot.
- **Migration SQLite → PostgreSQL** : `controle_pg migrer` ne copie pas encore les trois tables de références.
- **Suppression** : douce uniquement. Les fichiers d'une référence supprimée restent dans le magasin d'assets.
- **Recapture** : remplace le contenu et les images de la référence ; l'historique des captures n'est pas conservé
  (les anciennes images restent dans le magasin, sans lien).
- **Édition** : collection, étiquettes et titre se modifient par l'API ; l'interface ne propose pas encore de
  formulaire pour cela.
- Le bac à sable de Chromium dépend du poste (souvent absent en conteneur) ; la fiche l'indique dans sa méta
  (`bac_a_sable`). Le filtrage réseau, lui, ne dépend pas du bac à sable.
