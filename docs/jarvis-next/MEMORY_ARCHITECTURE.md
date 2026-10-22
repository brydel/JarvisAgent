# Mémoire et connaissance — PROPOSED (M5)

La mémoire n'est pas l'accumulation de transcripts.

| Mémoire | Contenu | Source dans Jarvis |
| --- | --- | --- |
| De travail | contexte court d'une mission | enveloppe de tâche (`travail`) |
| Épisodique | actions, résultats, erreurs, corrections | événements des missions, `taches.py`, classement des échecs (CURRENT) |
| Sémantique | faits vérifiés | entités de connaissance (à créer) |
| Procédurale | procédures validées | rôles, skills épinglées, briefs promus (CURRENT) |
| Projet | ADR, contraintes, dépôts, tests | `docs/`, mémoire du chef `memoire.py` (CURRENT) |
| Utilisateur | préférences explicitement autorisées | à créer, opt-in |
| Organisation | savoir et politiques du tenant | à créer |

## Récupération (sans 3ᵉ fournisseur)

1. Recherche plein texte (SQLite FTS5 aujourd'hui, `tsvector` PostgreSQL ensuite) + filtres de métadonnées.
2. Entités et relations (graphe en tables) ; parcours borné.
3. `pgvector` seulement quand une stratégie d'embeddings **approuvée** existe : aucun modèle d'embeddings tiers
   ajouté sans autorisation (décision 9).
4. Reclassement seulement si une évaluation mesurée le justifie.

## Chaque élément conserve

source, création, dernière vérification, portée et tenant, niveau de preuve, version, droits d'accès, entités
liées, état de remplacement/suppression. Tout contenu récupéré est une **donnée non fiable** : il ne peut pas
modifier les consignes de Jarvis.

## Tests prévus

injection par contenu récupéré, fuite inter-tenant, contenu empoisonné, information périmée (date de
vérification dépassée → signalée, pas servie comme vraie).
