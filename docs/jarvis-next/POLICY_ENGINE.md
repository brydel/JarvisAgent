# Moteur de politique

Principe : les prompts ne sont pas une frontière de sécurité. Les autorisations sont du code, hors du contrôle des
agents qui exécutent.

## Niveaux d'autonomie (VERIFIED dans `missions.py`)

| Niveau | Contenu | Par défaut |
| --- | --- | --- |
| L0 Observer | lire l'information autorisée | automatique |
| L1 Produire | notes, analyses, brouillons internes | automatique |
| L2 Ingénierie réversible | branches isolées, code, tests, PR préparées | **approbation** tant que le tenant ne l'active pas |
| L3 Effets externes | messages, publications, candidatures, argent, comptes | **toujours** approbation humaine |
| L4 Contrôle critique | politiques, permissions, identifiants, facturation, gouvernance | **toujours** approbation humaine |

`JAMAIS_AUTO = ("L3", "L4")` est une constante : un réglage de tenant qui demande L3/L4 automatiques est filtré
(test `test_L3_L4_jamais_automatiques_meme_configures`). Le risque se juge sur les effets réels : une action
réversible mais qui expose des données ou touche une autre personne est L3.

## Approbations

- Créées par le moteur, liées à l'**empreinte du travail** : si le travail change après la demande, l'accord est
  refusé et une nouvelle demande est nécessaire.
- Décidées seulement par un acteur de type `humain`, différent du demandeur ; jamais par un exécutant ou un agent.
- Refus → CANCELLED ; accord → QUEUED. Journalisées (`approbation`).
- Une demande encore en attente devient **caduque** dès que sa tâche atteint un état terminal (annulée, expirée) :
  elle ne peut plus être accordée (`test_annulation_rend_l_approbation_caduque`).

## Délégation bornée

Une sous-tâche ne dépasse ni le niveau ni les capacités de son parent ; profondeur ≤ 3, largeur ≤ 8, ≤ 50 tâches
par mission (`test_delegation_bornee`).

## Arrêts d'urgence

- Plan de contrôle : `jarvis mission arret on` (par tenant) — plus aucune tâche confiée.
- Machine locale : `jarvis pause poser humain` (existant) ou fichier `~/.local/state/jarvis/coureur/STOP`.

## Lien avec la politique existante (`config/politique.toml`, CURRENT)

Correspondance proposée : niveau 1 ↔ L0/L1 ; niveau 2 (délégation datée) ↔ L2 ; niveau 3 ↔ L3/L4. Unifier les deux
moteurs (une seule source, la politique versionnée qui ne peut être que durcie) est PROPOSED pour M4 ; d'ici là,
les missions n'ouvrent que L0/L1 automatiquement.

## Limite

Sur un poste, tout tourne sous le même utilisateur Linux : un agent qui écrit dans `missions.db` contourne le
moteur. L'indépendance réelle arrive avec le plan de contrôle séparé (M3), où l'exécutant n'a plus accès à la base.
