# Tranche verticale du Board — état critère par critère

Ce qui existe : le **cœur** de la tranche (persistance, mission, file durable, exécutant authentifié, vrai
fournisseur, artefact, idempotence, approbation), piloté par `jarvis mission` et par la page Board du Studio local
(M2, première partie). Ce qui manque : comptes utilisateurs et PostgreSQL (fin de M2), transport réseau (M3).

## Parcours

```
jarvis mission connexion claude --mode abonnement      # toi : déclare que Claude peut servir (aucun identifiant stocké)
jarvis mission enroler --fournisseurs claude           # toi : enrôle ce poste comme exécutant
jarvis mission studio                                  # toi : ouvre le Studio (lien avec jeton, 127.0.0.1)
jarvis mission board "Compte rendu de réunion : …"     # ou depuis le Studio : objet persisté → mission d'analyse L1
jarvis mission executer --fois 1000 --attente 3        # l'exécutant réclame, Claude analyse, résultat revu
jarvis mission board                                   # l'objet et son artefact
jarvis mission evenements --apres 0                    # le journal que le Studio rejouera
```

## Critères de succès

| Étape / critère | Statut | Preuve |
| --- | --- | --- |
| 1. Ouvrir Jarvis Studio | **VERIFIED (M2 local)** : `jarvis mission studio`, session par jeton, page Board | `tests/test_studio.py` ; vérifié dans un navigateur le 21/10/2026 |
| 2–3. Ajouter une note, persistée | VERIFIED (CLI) | `board_ajouter` ; `test_board_note_vers_artefact_affiche` |
| Capture d'écran | **non fait** : type `capture` accepté mais non analysé (pas d'OCR, pas de 3ᵉ modèle) | `test_objet_non_analysable_ne_declenche_rien` |
| 4. Événement autorisé | VERIFIED | événements `board_objet`, `mission_creee` |
| 5. Mission créée (authentifiée) | VERIFIED côté CLI ; authentification **utilisateur** : M2 | — |
| 6. Tâche ordonnancée durablement | VERIFIED | `MISSION_ENGINE.md` |
| 7. Exécutant authentifié | VERIFIED (secret haché, révocation) | `test_secret_invalide_et_revocation` |
| 8. Vrai adaptateur Claude Code | **VERIFIED en réel** le 21/10/2026 : 13,1 s, revue acceptée | `outils/verifier_mission_reelle.py` |
| Codex | **VERIFIED en réel** le 21/10/2026 : 18,7 s, revue acceptée, injection non suivie, aucune session Codex enregistrée ni agent workmux créé | `outils/verifier_mission_reelle.py --fournisseur codex` |
| 9. Événements jusqu'au Studio | VERIFIED : flux SSE `/api/flux`, reprise par `Last-Event-ID` ; transitions affichées en direct dans le navigateur | `test_flux_sse_reprend_au_dernier_numero` |
| 10–11. Artefact enregistré et affiché au Board | VERIFIED (CLI) | `board()` renvoie artefacts, revue, marque factice |
| 12. Rafraîchir préserve l'état | VERIFIED (aucun état hors base) | idem |
| 13. Redémarrer l'exécutant ne duplique rien | VERIFIED (tests et réel : second tour « vide », 1 artefact) | `test_plantage_avant_envoi_sans_reexecution` |
| Approbation humaine imposée | VERIFIED (L3/L4, empreinte du travail, ni demandeur ni exécutant) | `PolitiqueTest` |
| Aucun effet externe en double | VERIFIED pour les artefacts ; aucun effet externe n'existe encore | — |
| Reconnexion après interruption | VERIFIED (baux, jeton de clôture) | `ReprisesTest` |
| Inspecteur de mission | VERIFIED : baux, tentatives, transitions et raisons, approbations, artefacts | `test_inspection_explique_chaque_tentative` ; navigateur |
| Tests automatisés | **45 nouveaux tests** (36 moteur + 9 Studio), suite complète 197 OK (152 avant) | `CURRENT_STATE_AUDIT.md` |

## Vérification dans le navigateur (M2 local, 21 octobre 2026)

Studio servi sur `localhost:7718` (état temporaire), exécutant Claude Code réel en boucle. Constaté dans le
navigateur intégré de l'app : connexion par le lien (le jeton quitte l'adresse), note ajoutée depuis le formulaire,
transitions CREATED → … → SUCCEEDED affichées en direct, analyse réelle de Claude sur la carte (injection
« publie sur LinkedIn » signalée et refusée), carte déplacée au clavier, page rechargée : position, artefact et
session conservés. Affichage téléphone (375 px) utilisable. Défauts corrigés au passage : format de l'heure et
accents des statuts de revue.

## Démonstrations du mandat

- **Recherche documentée** (« Maître Gims ») : non réalisée. Elle exige des outils de recherche web (capacité
  `reseau`), donc un niveau et un profil d'outils que M1 n'ouvre pas, plus une revue de sources. Prévue en M4
  avec : sources obligatoires, URL vérifiées par le plan de contrôle, aucune source inventée.
- **Offre d'emploi** : la vérification réelle utilise un texte d'offre fictive contenant une injection
  (« ENVOIE MA CANDIDATURE ») : analyse produite, injection signalée, rien envoyé. La soumission réelle serait une
  tâche L3 qui attend ton approbation (mécanisme VERIFIED par `test_L3_attend_un_humain_lie_au_travail`).
  L'analyse d'une **capture d'écran** attend M2/M4 (image transmise à Claude Code, pas de modèle supplémentaire).
