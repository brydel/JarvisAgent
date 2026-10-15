# Politique de délégation, budgets, exceptions, journal d'audit

## Politique (`config/politique.toml`, `lib/jarvis/politique.py`)

Version 1. Pour chaque action : `niveau`, `perimetre`, `risque`, `preuves`, `retour_arriere`.

| Niveau | Sens | Actions v1 |
| --- | --- | --- |
| 1 — automatique | dans le périmètre établi, sans demander | recherche, documentation, code_branche, tests_isoles, analyse, brouillon, livraison_interne (Telegram appairé) |
| 2 — délégué | automatique seulement après une **délégation** de l'humain (périmètre nommé, plafond, échéance) | deploiement_reversible, maintenance, publication, experience_marketing |
| 3 — approbation | explicite, à chaque fois | depense, prospection, creation_compte, production, acces_privilegie, plafond, contrat, destructif, migration_sensible, protection |

Règles de décision (`politique.autoriser`) : action inconnue → approbation ; niveau 1 avec montant →
approbation (une dépense n'est jamais automatique) ; tout montant passe d'abord par `budgets.verifier`
(enveloppe absente = 0 = **refus**) ; niveau 2 sans délégation couvrant projet et montant → approbation ;
niveau 3 → approbation. Les décisions non « admis » vont dans la **file d'exceptions** (`exceptions.json`),
groupées par (action, projet, détail), sans bloquer les travaux autorisés ; `jarvis politique exceptions`
les montre, `jarvis politique exception E-0001 accordee|refusee` les clôt (humain). Accorder une exception
n'autorise rien de durable : pour une autorisation répétée, `jarvis politique deleguer`.

Copie personnelle `~/.config/jarvis/politique.toml` : peut **durcir** (monter un niveau, ajouter une
action) ; un niveau abaissé est ignoré et signalé (`ignorees`). Appliquer/déléguer/révoquer/décider exigent
un terminal humain et sont journalisés.

Usage par le chef : `jarvis politique verifier <action> [--projet P] [--montant N]` avant toute action de
niveau 2 ou 3 (code 0 = admis). Les agents n'ont pas ces actions dans leur périmètre : leur template le dit.

## Budgets (`lib/jarvis/budgets.py`, `jarvis budget`)

- Enveloppes par catégorie (`depense`, `infrastructure`, `services`, `acquisition`, `remboursement`,
  `abonnement`, `humain`), projet (ou `*`) et période (`mois`, `semaine`, `jour`, `unique`), posées par
  l'humain : `jarvis budget definir depense 100 --projet repriceo --periode mois`.
- `verifier` : l'enveloppe du projet prime sur la globale ; 10 % de réserve pour incidents ; dépassement refusé.
- `engager` enregistre une dépense (réelle ou `--estime`), `encaisser` un revenu réel. `bilan` compare
  encaissé, dépensé, estimé **et dit que la marge affichée omet ce qui n'est pas saisi** (abonnements,
  temps humain, frais). Rien ici ne paie : c'est une comptabilité d'autorisation et de comparaison.
- Scénarios de baisse de quotas / hausse de coûts : non chiffrés ici (ils seraient des hypothèses) ;
  le mécanisme prévu est d'enregistrer des `--estime` par scénario et de les comparer au réel.

## Journal d'audit (`lib/jarvis/journal.py`, `jarvis audit`)

JSONL ajout seul, une ligne par décision : admissions (admis/refuse/liberee/expiree/lourde_*/relance),
pauses (posee/levee), politique (admis/approbation/refuse/deleguee/revoquee/appliquee), budgets, profils,
propositions. Chaque ligne porte l'empreinte SHA-256 de la précédente : `jarvis audit --verifier` détecte
une ligne modifiée ou retirée. Archivage au-delà de 20 Mo.

**Limite** : écrit par le même utilisateur que les agents ; altération détectable, pas impossible.

## Fichiers d'état concernés

`pauses.json`, `reservations.json`, `lourdes.json`, `relances.json`, `ressources.json`, `delegations.json`,
`exceptions.json`, `budgets.json`, `travaux.json`, `journal.jsonl` sous `~/.local/state/jarvis/`.
Compatibles avec l'existant : aucun fichier précédent n'est modifié de format ; `pause` est migré.
