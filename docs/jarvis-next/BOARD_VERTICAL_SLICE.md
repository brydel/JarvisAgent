# Tranche verticale du Board — état critère par critère

Ce qui existe : le **cœur** de la tranche (persistance, mission, file durable, exécutant authentifié, vrai
fournisseur, artefact, idempotence, approbation), piloté par `jarvis mission`. Ce qui manque : l'interface web
Jarvis Studio (M2) et le transport réseau (M3).

## Parcours

```
jarvis mission connexion claude --mode abonnement      # toi : déclare que Claude peut servir (aucun identifiant stocké)
jarvis mission enroler --fournisseurs claude           # toi : enrôle ce poste comme exécutant
jarvis mission board "Compte rendu de réunion : …"     # objet persisté → événement → mission d'analyse L1
jarvis mission executer                                # l'exécutant réclame, Claude analyse, résultat revu
jarvis mission board                                   # l'objet et son artefact
jarvis mission evenements --apres 0                    # le journal que le Studio rejouera
```

## Critères de succès

| Étape / critère | Statut | Preuve |
| --- | --- | --- |
| 1. Ouvrir Jarvis Studio | **non fait** (M2) | — |
| 2–3. Ajouter une note, persistée | VERIFIED (CLI) | `board_ajouter` ; `test_board_note_vers_artefact_affiche` |
| Capture d'écran | **non fait** : type `capture` accepté mais non analysé (pas d'OCR, pas de 3ᵉ modèle) | `test_objet_non_analysable_ne_declenche_rien` |
| 4. Événement autorisé | VERIFIED | événements `board_objet`, `mission_creee` |
| 5. Mission créée (authentifiée) | VERIFIED côté CLI ; authentification **utilisateur** : M2 | — |
| 6. Tâche ordonnancée durablement | VERIFIED | `MISSION_ENGINE.md` |
| 7. Exécutant authentifié | VERIFIED (secret haché, révocation) | `test_secret_invalide_et_revocation` |
| 8. Vrai adaptateur Claude Code | **VERIFIED en réel** le 21/10/2026 : 13,1 s, revue acceptée | `outils/verifier_mission_reelle.py` |
| Codex | BLOCKED (CLI cassé dans WSL) | `OPEN_DECISIONS.md` D-1 |
| 9. Événements jusqu'au Studio | journal ordonné + reprise par numéro VERIFIED ; flux SSE : M2 | `evenements(apres=…)` |
| 10–11. Artefact enregistré et affiché au Board | VERIFIED (CLI) | `board()` renvoie artefacts, revue, marque factice |
| 12. Rafraîchir préserve l'état | VERIFIED (aucun état hors base) | idem |
| 13. Redémarrer l'exécutant ne duplique rien | VERIFIED (tests et réel : second tour « vide », 1 artefact) | `test_plantage_avant_envoi_sans_reexecution` |
| Approbation humaine imposée | VERIFIED (L3/L4, empreinte du travail, ni demandeur ni exécutant) | `PolitiqueTest` |
| Aucun effet externe en double | VERIFIED pour les artefacts ; aucun effet externe n'existe encore | — |
| Reconnexion après interruption | VERIFIED (baux, jeton de clôture) | `ReprisesTest` |
| Tests automatisés | **34 nouveaux tests**, suite complète 186 OK (152 avant) | `CURRENT_STATE_AUDIT.md` |

## Démonstrations du mandat

- **Recherche documentée** (« Maître Gims ») : non réalisée. Elle exige des outils de recherche web (capacité
  `reseau`), donc un niveau et un profil d'outils que M1 n'ouvre pas, plus une revue de sources. Prévue en M4
  avec : sources obligatoires, URL vérifiées par le plan de contrôle, aucune source inventée.
- **Offre d'emploi** : la vérification réelle utilise un texte d'offre fictive contenant une injection
  (« ENVOIE MA CANDIDATURE ») : analyse produite, injection signalée, rien envoyé. La soumission réelle serait une
  tâche L3 qui attend ton approbation (mécanisme VERIFIED par `test_L3_attend_un_humain_lie_au_travail`).
  L'analyse d'une **capture d'écran** attend M2/M4 (image transmise à Claude Code, pas de modèle supplémentaire).
