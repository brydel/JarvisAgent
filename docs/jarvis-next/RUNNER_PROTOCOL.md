# Protocole d'exécutant v1

Code : `lib/jarvis/protocole_executant.py` (enveloppes), `missions.py` (côté plan de contrôle), `coureur.py`
(côté exécutant). Transport M1 : **local** (`TransportLocal`, appels directs). Transport réseau : PROPOSED (M3).

Un exécutant est un service de la machine, **pas un shell distant**. Il n'a aucun accès direct à la base : il
appelle quatre opérations étroites, toujours authentifiées.

## Identité et enrôlement — VERIFIED (local)

- `enroler_executant(tenant, nom, capacites, fournisseurs, profil, version, systeme)` → `(RU-…, secret)` ; le
  secret n'est montré qu'une fois, seule son empreinte SHA-256 est gardée ; comparaison à temps constant.
- Lancé par le propriétaire de la machine (`jarvis mission enroler`, terminal humain seulement).
- **Le tenant est fixé à l'enrôlement.** Rien de ce qu'envoie l'exécutant ne le change (test
  `test_enveloppe_ne_choisit_pas_le_tenant`, `test_tenants_etanches`).
- Révocation immédiate (`revoquer_executant`) ; rotation = nouvel enrôlement + révocation de l'ancien.
- Manifeste : capacités, fournisseurs, profil (`PERSONAL_LOCAL`, `CUSTOMER_OWNED_RUNNER`, `COMMERCIAL_HOSTED`),
  version, système, dernier signe de vie.

## Opérations

| Opération | Effet | Refus |
| --- | --- | --- |
| `reclamer` | plus ancienne tâche QUEUED du tenant dont les capacités sont couvertes, routée vers un fournisseur admis ; bail de 120 s, jeton +1, tentative créée | arrêt d'urgence du tenant ; secret invalide ; exécutant révoqué |
| `demarrer` | LEASED → RUNNING | bail périmé |
| `battement` | prolonge le bail ; `{"continuer": false}` si annulée ou bail perdu | — |
| `rendre_resultat` | applique le résultat (artefact, revue, nouvel essai, attente fournisseur) | bail périmé (événement `resultat_perime` journalisé), tâche d'un autre tenant (`inconnue`, sans révéler son existence) |

## Enveloppe de tâche v1 (champs obligatoires)

`version, tenant_id, mission_id, tache_id, tentative_id, correlation_id, capacites, niveau, fournisseur, travail,
delai_s, limites, bail_jeton, bail_expire, cle_idempotence, decision_politique`.

Validée par l'exécutant comme une **donnée** (`valider_tache`) : version connue, types stricts (un booléen n'est
pas un entier), niveau connu, délai borné. Un champ inconnu est ignoré (évolution compatible) ; une version majeure
inconnue est refusée.

## Résultat v1

`version, tache_id, tentative_id, bail_jeton, cle_idempotence, issue (reussi | echec | fournisseur_indisponible)`,
plus `contenu` (≤ 200 000 caractères), `erreur`, `fournisseur`, `factice`. Une réussite sans contenu est refusée.

## Garanties de livraison

- Messages en double ou désordonnés : la clé `tache:jeton` rend `rendre_resultat` idempotent ; le jeton de clôture
  rejette un résultat d'un bail plus ancien.
- Au plus **un artefact par tentative** (contrainte d'unicité) et au plus un artefact **accepté** par tâche (la
  machine d'états n'atteint SUCCEEDED qu'une fois).
- Pas d'« exactement une fois » pour un effet externe (voir `MISSION_ENGINE.md`).

## Transport réseau — PROPOSED (M3)

- Connexions **sortantes** uniquement de l'exécutant vers le plan de contrôle (HTTPS, longue interrogation ou
  WebSocket) : aucun port entrant, aucun SSH exposé.
- Authentification : mTLS avec certificat client court (24 h) émis à l'enrôlement par un code d'appairage à usage
  unique saisi par le propriétaire ; à défaut, jeton signé court + secret d'enrôlement. Rotation automatique,
  révocation par liste côté plan de contrôle.
- Contre-pression : l'exécutant ne réclame qu'à capacité libre ; le plan de contrôle limite les réclamations par
  exécutant et par tenant.
- Artefacts volumineux : envoi par URL présignée liée à la tentative, empreinte vérifiée côté serveur.
- Compatibilité : en-tête `version` ; le serveur sert v1 et v(n) pendant une période de transition annoncée.
