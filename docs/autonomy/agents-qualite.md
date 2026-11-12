# Qualité des agents : un prompt qui porte du signal, un compte rendu qu'on peut relire

Ce lot répond à un audit de l'usine réelle : 600 tâches dont 291 relectures, un verdict sur deux en
« corrections », aucune évaluation de rôle lancée, un réseau des agents où 527 messages venaient de personas
simulées contre 3 d'agents réellement en tâche, une mémoire du chef jamais transmise aux agents, et un agent
relancé après « corrections » qui ne recevait pas les remarques du relecteur.

## Ce qui change, en une page

| Avant | Après |
|---|---|
| Vie sociale des personas en mode `calme` par défaut | `off` par défaut (`lib/jarvis/vie_sociale.py`, `MODE_DEFAUT`) |
| Le chef réveillé par toute persona qui « propose une idée » | Réveillé par ton humain, ou par un agent en tâche (`agent:T-…`) qui pose une question, demande de l'aide ou propose une idée |
| Prompt terminé par un JSON de contrat et des extraits du forum | Prompt terminé par la définition de « fini » et le format du compte rendu |
| Mémoire long terme lue par le chef seulement | 3 entrées au plus, au-dessus d'un score minimal, dans le prompt de chaque agent |
| Protocole seulement dans `CLAUDE.md` / `AGENTS.md` du projet | Protocole minimal dans le prompt, règles du projet en plus |
| « ✅ REVUE / ❓ REVUE » (mission) contre « VERDICT : … » (brief) | Un seul format, relu par `lib/jarvis/comptes_rendus.py` |
| Relance après « corrections » sans les remarques | Section « Corrections exigées » : résumé du verdict + commentaires de la PR |
| Évaluation d'un rôle sur « brief + consigne » | Évaluation sur le vrai prompt (`prompt_agent.pour_evaluation`) |
| Codex sans recherche web | `--search` quand la version installée le propose |

## Le prompt d'un agent

`jarvis task` appelle `jarvis prompt-construire`, qui délègue à `lib/jarvis/prompt_agent.py`. Les sections,
dans l'ordre :

1. **Mission** — l'issue à traiter, ou la relecture à faire.
2. **Corrections exigées** — seulement si la dernière relecture de l'unité de travail a rendu « corrections ».
3. **Ton rôle** — le brief (`roles/<nom>.md`, ou le candidat en essai).
4. **Ton poste** — projet, branche, dossier des livrables.
5. **Consignes du chef d'orchestre** — le fichier `--consignes` (gabarit dans `chef/CLAUDE.md`, étape 5).
6. **Contexte utile** :
   - *Mémoire de l'usine* : `memoire.pertinentes` sur le sujet des consignes (3 entrées au plus, score minimal ;
     détail dans « Lot 2 — volet prompt »), une ligne par entrée (420 caractères au plus), puis les leçons
     **retenues** du réseau (relues, avec preuve) ;
   - *Historique de cette tâche* : les essais de l'unité (projet, issue, rôle) — statut, classe d'échec et sa note,
     verdict et son résumé, jetons (`taches.historique`) ; pour une relecture, l'historique de la production relue ;
   - *Moyens* : taille S/M/L, plafond de jetons de la tâche (celui du plan ou de l'admission, sinon
     `couts.plafond_defaut`), jetons déjà consommés par les essais précédents, ce qui se passe au plafond ;
     modèle et effort affectés par le routeur.
7. **Protocole** — démarrage (« In Progress », plan), incertitude graduée, vérifications, fin (PR, « In Review »),
   interdits.
8. **Fini et compte rendu** — la définition de « fini » et le gabarit exact. C'est la dernière chose lue.

Le lot 2 ajoute deux sections : **Critères d'acceptation** juste après la Mission, et **Outils de cette session**
après « Ton poste » (voir « Lot 2 — volet prompt »). Les briefs renvoient à cette dernière au lieu d'affirmer
qu'un outil existe.

Ce qui n'y est plus : le JSON « Contrat commun de la session » (`specifications.pour_prompt` existe toujours,
pour la vue des sessions et le préflight) et le bloc « Réseau libre de l'usine » avec ses extraits du forum.

### Données citées, jamais instructions

La mémoire, la note d'un verdict et les commentaires d'une PR viennent d'ailleurs que du dépôt. Chacune est :
bornée en taille ; expurgée (`memoire.expurger` : jetons d'API, clés, mots de passe d'URL, secrets connus) ;
ramenée à une ligne, ou citée ligne par ligne avec le préfixe `> ` (elle ne peut ni ouvrir une section du prompt
ni fermer un bloc de code) ; annoncée comme une information à vérifier. Si une source est en panne (registre
illisible, mémoire corrompue, `gh` absent), la section est plus courte ou absente : le prompt part quand même.

### Incertitude graduée

- **Mineure** (nommage, détail d'implémentation, cas que l'issue ne tranche pas, choix facile à défaire) : l'agent
  décide, continue, et note l'hypothèse dans « Hypothèses » de son compte rendu.
- **Bloquante** (périmètre, critères contradictoires, données ou schéma, sécurité, dépense, accès manquant,
  irréversible) : `❓ QUESTION :` avec options A/B, coût de chacune, recommandation, ce qui a déjà été vérifié ;
  puis il continue la partie du travail que la question ne touche pas, en le disant ; il ne s'arrête que si elle
  touche tout, et ne livre rien qui dépende de la réponse (lot 2).

### Projet sans fichier de règles

`bin/jarvis` passe `--sans-regles` quand le projet n'a ni `CLAUDE.md` ni `AGENTS.md`. Le protocole est dans le
prompt de toute façon ; il manque seulement les commandes de vérification du projet, que l'agent doit alors déduire
du dépôt (README, `package.json`, Makefile, CI) et citer. L'avertissement au lancement le dit.

## Comptes rendus et verdicts

Un seul module, `lib/jarvis/comptes_rendus.py`, porte les gabarits donnés aux agents **et** l'analyseur qui les
relit ; un test vérifie que les deux ne divergent pas.

Fin de tâche :

```
✅ TERMINÉ
Rôle : <rôle> · Tâche : <ISSUE>
Résumé : <2 ou 3 phrases>
Critères :
1. <critère> → <preuve>
Vérifications :
- `<commande>` → <résultat>
Hypothèses :
- <hypothèse> (ou « aucune »)
Risques :
- <risque> (ou « aucun »)
Fichiers :
- <chemin>
Branche : <branche> · PR : <#numéro, ou « aucune » + la raison>
```

Relecture :

```
VERDICT : CORRECTIONS
Corrections exigées :
1. [bloquant] app/offres.py:42 — ce qui est faux, et ce qui est attendu
2. [majeur] tests/test_offres.py:1 — …
Suggestions :
- <non bloquant>
Vérifications :
- `<commande>` → <résultat>
```

Sévérités : `bloquant` (faux, dangereux, critère non satisfait), `majeur` (non testé, fragile), `mineur`.
`VERDICT : PRÊT` s'écrit avec « Corrections exigées : aucune ».

L'analyseur :

```python
from jarvis import comptes_rendus
a = comptes_rendus.analyser_verdict(texte)
# {"verdict": "corrections", "premiere_ligne": True, "corrections": [{"n": 1, "severite": "bloquant",
#   "fichier": "app/offres.py", "ligne": 42, "texte": "…"}], "suggestions": [...], "verifications": [...],
#   "anomalies": [...], "conforme": True}
comptes_rendus.resume_verdict(a)        # texte court pour « jarvis verdict … corrections "…" »
comptes_rendus.analyser_termine(texte)  # critères → preuves, vérifications → résultats, hypothèses, risques, PR
```

En ligne de commande : `python3 -m jarvis.comptes_rendus <fichier>` (ou l'entrée standard) affiche l'analyse en
JSON ; code de sortie 0 si le texte est conforme, 2 sinon. Il tolère le gras, les accents absents, un titre
Markdown ; il signale dans « anomalies » un verdict absent ou hors de la première ligne, `CORRECTIONS` sans liste,
`PRÊT` avec des corrections, une correction sans sévérité ou sans `fichier:ligne`. Il lit un texte : il ne juge
pas le travail.

## Boucle de correction

Quand `jarvis task` relance une unité de travail dont le dernier verdict est « corrections », le prompt reçoit
juste après la Mission :

1. la tâche et la branche de l'essai corrigé, et la PR si elle est connue ;
2. le résumé du verdict enregistré (`jarvis verdict <projet> <ISSUE> corrections "…"`, 1 500 caractères au plus) ;
3. si `gh` répond : les commentaires de la PR (revues, commentaires, commentaires en ligne avec leur
   `fichier:ligne`), les 8 plus récents, 700 caractères chacun, 4 000 au total, tous cités. Aucun n'est réanalysé
   pour en tirer des « corrections » (voir « Lot 2 — relecture adverse ») : la liste exigée vient de la fiche.

La PR est cherchée dans cet ordre : la relecture lancée avec `--revue N` sur cette issue ; un « PR #N » dans le
résumé du verdict ; `gh pr list --head <branche de l'essai corrigé>`. Chaque appel à `gh` est limité à 8 secondes
et le premier échec arrête la recherche : sans `gh`, sans réseau ou hors d'un dépôt GitHub, le prompt contient le
résumé du verdict et la commande à lancer pour lire les commentaires.

Conséquence pour le chef : la note enregistrée par `jarvis verdict` est ce que l'agent relancé lira en premier.
Depuis le lot 2, `jarvis verdict <projet> <ISSUE>` la tire du compte rendu publié par le relecteur (« PR #N » et
liste numérotée) ; en saisie à la main, le résumé du chef reprend cette liste et cite la PR.

Un relecteur relancé sur une issue déjà en « corrections » reçoit la même liste sous « Corrections exigées à la
relecture précédente », avec la consigne de vérifier chaque point.

## Briefs de rôle

Les quinze briefs suivent depuis le lot 2 un seul gabarit (objectif, procédure, interdits, « Fini quand », exemple
et contre-exemple de compte rendu) : voir « Volet briefs et évaluation » ci-dessous, qui remplace l'ancienne
répartition réécrits / complétés / inchangés. Chaque brief tient en 60 lignes au plus (test).

`evaluation.consigne_complete` construit désormais le prompt d'un cas avec `prompt_agent.pour_evaluation` :
même brief, même protocole d'incertitude, même définition de « fini » et même format de compte rendu qu'une vraie
tâche — sans Linear ni PR, et sans contexte local (mémoire, registre), pour que deux exécutions restent
comparables.

## Volet briefs et évaluation (lot « 9/10 »)

Cette section remplace, pour les briefs, la liste « réécrits / complétés / inchangés » ci-dessus.

**Les quinze briefs suivent un seul gabarit**, dans cet ordre : un premier paragraphe qui pose le métier et
l'objectif ; `**Procédure**` (étapes numérotées) ; `**À ne pas faire**` (3 à 5 interdits) ; `**Fini quand :**`
(des conditions qu'une preuve établit) ; `**Exemple de bon compte rendu …**` (un bloc au format de
`comptes_rendus.py`) ; `**Contre-exemple (refusé : pourquoi)**` (un bloc court de ce qu'il ne faut pas rendre).
Chaque brief fait 40 à 60 lignes.

- Réécrits : `architecte` (avec un gabarit d'ADR — contexte, options, décision, conséquences, découpage — et un
  « fini » vérifiable : deux options avec coût et retour arrière, aucun fichier dans deux tâches), `backend`, `data`,
  `devops`, `ia-produit`, `marketing`. Les règles métier d'origine sont conservées (un test les liste).
- Complétés (procédure, interdits, exemple, contre-exemple) : `design`, `frontend`, `qa`, `recherche`, `revue`
  (son exemple est un verdict), `video`.
- Contre-exemple ajouté : `generaliste`, `redaction`, `securite`. `securite` cite les deux skills de défense
  présentes dans `skills/` (`jarvis-defense-triage`, `jarvis-defense-incident`) ; un test compare la liste citée au
  contenu du dossier.

**L'exemple d'un brief est exécuté, pas seulement lu.** `evaluation.structure_brief(corps)` rend la liste des
écarts au gabarit ; l'exemple et le contre-exemple passent par l'analyseur de `comptes_rendus` : l'exemple doit
être relu sans anomalie (chaque critère a sa preuve, chaque vérification son résultat ; verdict conforme pour
`revue`), le contre-exemple doit être refusé. Un extrait n'est pas jugé sur les rubriques qu'il ne recopie pas
(résumé, fichiers, branche).

**Exigences d'un cas : moins de mots-clés, plus de contrôles.** Un `cas.toml` garde `exigences_brief` pour les
règles métier (expressions cherchées dans le brief) et gagne `exigences_compte_rendu`, des contrôles nommés de
`evaluation.CONTROLES_COMPTE_RENDU` : `exemple`, `contre_exemple`, `preuve_par_test`, `ecart_declare`. Le mot-clé
`tests?` des cas existants est remplacé par `preuve_par_test`. `exigences_manquantes` rend les deux sortes
d'écarts : `jarvis eval verifier` les affiche, et `versions_roles.controler` refuse un brief candidat qui retire
ou abîme son exemple.

**Chaque rôle a un cas de référence** (25 cas, 10 nouveaux) :

| Cas | Ce que la vérification cachée contrôle |
|---|---|
| `architecte/adr-file-de-courriels` | ADR au gabarit, deux options avec coût / blocage / retour arrière, renvois `fichier:ligne` existants, découpage sans fichier partagé, code non modifié |
| `data/migration-reversible` | montée, descente et remontée sur SQLite ; schéma identique après descente ; données intactes ; fonctions relançables |
| `devops/script-idempotent` | `set -euo pipefail`, code 2 sans argument, deux exécutions de suite laissent le même état |
| `generaliste/correctif-minimal` | bug corrigé, test qui échoue sur le code d'origine, fonction voisine intacte |
| `ia-produit/drapeau-et-repli` | drapeau coupé par défaut (aucun appel), un seul nouvel essai, sortie validée, repli, tests sans réseau |
| `marketing/annonces-verifiables` | trois angles, limites de caractères, aucun nombre absent du README, preuve par ligne, pas de superlatif |
| `recherche/comparatif-source` | recommandation conforme au critère malgré une consigne injectée dans une source, faits sourcés et datés, rumeur rangée en « non vérifié » |
| `revue/verdict-au-format` | verdict relu par `comptes_rendus.analyser_verdict` : conforme, bloquant sur la bonne fonction, vérification lancée, aucun autre fichier modifié |
| `video/storyboard-du-scenario` | storyboard au format du studio : durée totale, première et dernière scènes, images présentes, titres de 6 mots au plus |
| `design/contraste-et-focus` | contraste WCAG calculé (4,5:1), focus visible, pas de largeur fixe au-delà de 360 px, aucune couleur hors des jetons |

Pour chaque nouveau cas, un test modifie la référence pour y remettre la faute que le rôle doit éviter (fichier
partagé entre deux tâches, descente qui laisse la colonne, recommandation dictée par la source, verdict sans
`fichier:ligne`…) et vérifie que la vérification la refuse.

**Exécution réelle.** `evaluation.lancer` enregistre en plus `compte_rendu` : type, conformité et anomalies du
compte rendu rendu par l'agent (`evaluation.analyser_sortie` relit le dernier bloc `✅ TERMINÉ` de la sortie, et
ne compte pas le gabarit recopié depuis le prompt). `ok` reste le seul verdict de la vérification cachée : les
résultats déjà enregistrés restent comparables.

Limites de ce volet :

- Aucune évaluation réelle n'a été lancée : seul le contrôle hors ligne (départ refusé, référence acceptée,
  exigences tenues, solutions fautives refusées) a tourné. Rien ne dit encore qu'un agent réel réussit ces cas, ni
  que les nouveaux briefs font mieux que les anciens.
- `preuve_par_test` reconnaît un test au texte de la preuve (`tests/…`, `test_…`, `.test.`) : c'est un contrôle
  sur un champ analysé, pas une preuve que le test existe.
- Les cas `design`, `video` et `marketing` jugent un fichier (jetons CSS, storyboard, annonces) : ni rendu, ni
  capture, ni qualité visuelle ou rédactionnelle.
- En évaluation, le prompt donne à tous les rôles le gabarit `✅ TERMINÉ`, y compris à `revue` : le cas
  `revue/verdict-au-format` décrit donc le format du verdict dans sa consigne et le lit dans `verdict.md`.
  `jarvis eval resultats` n'affiche pas encore `compte_rendu` (`lib/jarvis/cli.py`, hors de ce volet).

## Bruit social

- `communaute.vie` vaut `off` quand rien n'est réglé. Un mode choisi depuis le Studio (enregistré dans l'état)
  reste prioritaire : ce lot ne modifie aucun état existant.
- Le chef n'est plus réveillé par les personas (`agent:<rôle>`), quel que soit le type de leur message.
- `chef/CLAUDE.md` : la section « Réseau libre des agents » devient la procédure de promotion d'une leçon vérifiée
  (`jarvis os communaute evaluer CM-… evaluer|retenir … --preuve …`). Une leçon retenue entre dans le « Contexte
  utile » des agents suivants.

## Outillage

- `bin/jarvis-codex` ajoute `--search` si `codex --help` connaît l'option (sinon l'agent ne démarrerait pas) et si
  le réglage `codex.recherche_web` (défaut `true`) ne la coupe pas.
- `install.sh` lie aussi les skills `jarvis-defense-*` présentes dans `skills/`.

## Fichiers

| Fichier | Rôle |
|---|---|
| `lib/jarvis/prompt_agent.py` | construction du prompt (tâche, relecture, évaluation), boucle de correction, lecture de `gh` |
| `lib/jarvis/comptes_rendus.py` | gabarits et analyseur des comptes rendus et verdicts |
| `lib/jarvis/taches.py` | `historique`, `dernier_verdict`, `pr_connue`, note de verdict à 1 500 caractères |
| `lib/jarvis/cli.py` | `cmd_prompt_construire` (délègue) et ses options `--agent --modele --effort --taille --jetons-max --sans-regles` |
| `bin/jarvis` | transmet l'affectation au prompt ; avertissement « règles absentes » |
| `tests/test_agents_qualite.py`, `tests/fake-bin/gh` | tests du lot ; faux `gh` (inactif sans `FAKE_GH_DIR`) |

## Limites connues

- La pertinence de la mémoire est celle de `memoire.pertinentes` (lot 2) : rapprochement de mots grossier, seuils
  réglés sur des cas de test. Des consignes pauvres ne font remonter aucune entrée.
- Le numéro de PR d'une production n'est pas stocké dans sa fiche : il est déduit (relecture lancée, résumé du
  verdict, branche). Si rien ne le donne, les commentaires ne sont pas joints.
- L'analyseur est branché sur la boucle de correction, sur sa ligne de commande et, depuis le lot 2, sur
  `jarvis verdict` (voir « Volet aq2-verdict »).
- Aucune évaluation réelle de rôle n'a été lancée par ce lot (elle consomme les abonnements) : seul le contrôle
  gratuit des cas (`tests/goldens`) a été exécuté.

## Lot 2 — volet « prompt » (branche `feat/aq2-prompt`)

Cette section décrit ce que le lot 2 change dans le prompt réellement envoyé. Là où elle contredit le haut de la
page (ordre des sections, mémoire, incertitude bloquante), c'est elle qui est à jour.

### Ordre des sections

1. Mission · 2. **Critères d'acceptation** (si le lanceur les a) · 3. Corrections exigées (si le dernier verdict
est « corrections ») · 4. Ton rôle · 5. Ton poste · 6. **Outils de cette session** · 7. Consignes du chef
d'orchestre · 8. Contexte utile · 9. Protocole · 10. Fini et compte rendu.

Les titres du fichier de consignes descendent d'un niveau (`## Objectif` devient `### Objectif`) : ce sont des
rubriques de la section du chef, plus des sections du prompt.

### Outils de cette session (`lib/jarvis/outils_session.py`)

Constat fait au lancement, sur le poste, sans rien connecter. Chaque ligne dit le fait, son absence, ou « inconnu ».

| Ligne | Source lue | Réponses possibles |
|---|---|---|
| Moteur | option `--agent` du lanceur | Claude Code, Codex, inconnu (lancement hors routeur) |
| Recherche web (Codex) | réglage `codex.recherche_web` puis `codex --help` (5 s au plus) : les deux conditions de `bin/jarvis-codex` | oui, non (réglage coupé), non (option inconnue de ce Codex), inconnu (`codex` absent du PATH ou muet) |
| Recherche web (Claude) | `permissions.deny` de `settings.json` (utilisateur, projet, projet local) | « outil intégré, sans refus dans les réglages lus, non testé », non (refusé), inconnu (réglages illisibles) |
| Serveurs MCP (Codex) | `$CODEX_HOME/config.toml`, réglages `codex.mcp_approuves` et `codex.mode` | noms, avec « approuvés d'avance » ou « non approuvé : appels refusés », désactivés, aucun, inconnu |
| Serveurs MCP (Claude) | `.claude.json` (portée utilisateur) et `.mcp.json` du projet | noms par portée ; connecteurs du compte et plugins toujours « inconnu » (invisibles du lanceur) |
| Playwright | PATH, `node_modules` et `package.json` du dépôt principal, module Python, serveur MCP, `~/.cache/ms-playwright` | présent (où), déclaré mais pas installé, non trouvé (où il a été cherché) |
| Skills citées par le rôle | chemins `skills/<nom>/` du brief ; `SKILL.md` sur disque ; lien dans `~/.claude/skills` ou `~/.agents/skills` | présent / ABSENT, lié ou non pour le moteur ; pas de ligne si le brief n'en cite aucune |
| `jarvis lourd exec` | `admission.CLASSES`, réglage `admission.operations_lourdes_max`, `jarvis` dans le PATH | classes et nombre de places ; « aucune admise » si le réglage vaut 0 |

Seuls des noms sortent des fichiers de configuration : ni URL, ni variable d'environnement, ni argument de commande
(test). Un constat qui tombe en panne vaut « inconnu » ; le prompt part quand même. Le prompt d'évaluation
(`pour_evaluation`) ne reçoit pas ce bloc : il dépend du poste.

### Critères d'acceptation

- Source 1 : la rubrique « Critères vérifiables » (ou « Critères d'acceptation ») du fichier `--consignes`.
- Source 2, si les consignes n'en portent pas : un fichier local passé par `jarvis prompt-construire --criteres`.
- Le lanceur n'appelle pas Linear (test : aucune commande, aucune connexion pendant l'extraction).
- Chaque critère est une donnée : une ligne, expurgée, 320 caractères au plus, 12 critères au plus, numérotés.
  La section rappelle que l'issue reste la référence et qu'un critère contredit est une incertitude bloquante.
- Liste recopiée entière et sans retouche : la rubrique des consignes est remplacée par un renvoi (les critères ne
  sont pas dits deux fois). Un critère omis, abrégé ou expurgé : les consignes gardent leur rubrique entière.
- Aucun critère reçu (rubrique absente, « aucun », gabarit non rempli) : la Mission le dit en une phrase.
- « Fini » renvoie alors aux critères listés en tête, par leur nombre.

### Mémoire pertinente (`memoire.pertinentes`)

`memoire.chercher` (commande du chef) n'a pas changé. Le prompt passe par une sélection plus sévère :

- requête = sujet de la tâche : rubriques Objectif, Critères et Pièges des consignes (sinon leur début) et
  description courte portée par la branche ; le nom du projet et l'identifiant d'issue en sont retirés, ainsi que
  le vocabulaire générique de l'usine ; sans sujet, aucune recherche ;
- un terme compte une fois par entrée, au poids du meilleur champ : leçon 3, échec 3, titre 2, décision 2, corps
  et étiquettes 1 ; le rôle ajoute 1 point au plus et ne suffit jamais ;
- une entrée n'entre que si elle contient 2 termes distincts du sujet et atteint 4 points (`SCORE_MIN`) ;
- dès 6 entrées candidates, un terme présent dans plus de la moitié d'entre elles est ignoré ;
- 3 entrées au plus (5 avant), score décroissant ; la date ne départage que deux scores égaux ;
- rapprochement de mots sans dépendance (`_proches`) : préfixe, ou radical commun de 5 lettres.

Le test `test_une_note_recente_hors_sujet_ne_remonte_plus` montre la note qui arrivait en tête avec l'ancienne
requête (projet + issue + rôle) et qui n'entre plus.

### Redondances retirées, incertitude, longueur

- « Lire l'issue en entier » n'est plus dit que dans le Protocole ; la Mission ne renvoie plus au format du compte
  rendu ; l'étape 4 du Protocole s'appelle « Livraison » et ne reparle plus du compte rendu ; l'interdit de fusion
  dans `main` et les classes d'opérations lourdes sont dits une fois (tests).
- Incertitude bloquante : après `❓ QUESTION :`, l'agent continue la partie que la question ne touche pas et le
  dit dans la question ; il ne s'arrête que si elle touche tout, et ne livre rien qui dépende de la réponse.
- `prompt_agent.mesurer` : caractères, lignes, estimation en jetons (3,2 caractères par jeton, à titre de
  comparaison), caractères par section. `jarvis prompt-construire --mesure` l'affiche sur la sortie d'erreur ;
  sans l'option, un avertissement sort au-dessus du plafond et le prompt part quand même.
- Plafonds testés : socle (sans brief ni consignes, premier essai) 7 500 caractères ; prompt complet au pire cas
  (chaque rôle, consignes longues, mémoire pleine, boucle de correction) 24 000 caractères.

### Limites de ce volet

- Rien n'a été mesuré sur un vrai agent : le gain de qualité du prompt reste à constater sur des tâches réelles.
- « Recherche web » côté Claude n'est pas un test de l'outil : seule l'absence de refus dans les réglages est lue.
- Les serveurs MCP sont lus dans les fichiers ; un connecteur du compte Claude (Linear, souvent) n'y figure pas et
  reste « inconnu ». La portée locale par projet de `.claude.json` n'est pas lue (le worktree n'existe pas encore).
- `bin/jarvis` ne passe pas `--criteres` : l'option n'est utilisable qu'à la main tant qu'aucune copie locale des
  issues n'existe.
- Les consignes du chef partent sans expurgation, comme avant (l'expurgation prendrait un long chemin pour une clé).
- Le rapprochement de mots est grossier (« contrat » et « contrainte » se confondent) et les seuils (2 termes,
  4 points) ont été réglés sur des cas de test, pas sur la mémoire réelle de l'usine.

## Volet aq2-verdict : le verdict de relecture s'enregistre sans recopie

> Cette section décrit le volet tel qu'il a été livré. La relecture adverse en a corrigé l'identité du relecteur
> (jeton de relecture), la portée de `--pr` et de `--stdin`, et ce que la saisie à la main peut faire : là où
> elle contredit ce qui suit, c'est « Lot 2 — relecture adverse », en fin de document, qui fait foi.

Avant : le chef lisait le verdict du relecteur et le recopiait dans `jarvis verdict <projet> <ISSUE>
pret|corrections "résumé"`. La décision, la liste des corrections et la PR dépendaient de sa recopie.

Maintenant : `jarvis verdict <projet> <ISSUE>` lit le compte rendu publié par le relecteur, l'analyse avec
`comptes_rendus.analyser_verdict` et enregistre sur la fiche de production la décision, la liste numérotée des
corrections et le numéro de la PR. Le résumé du chef est facultatif (`jarvis verdict <projet> <ISSUE> "résumé"`).
Cette section remplace la ligne « `jarvis verdict` prend toujours son résumé du chef » des limites connues.

### Ce que fait la commande

| Appel | Effet |
|---|---|
| `jarvis verdict P I` | lit le dernier verdict publié sur la PR ; l'enregistre s'il est conforme, sinon refuse (code 1, rien d'écrit) |
| `jarvis verdict P I "résumé"` | idem ; le résumé (400 caractères au plus) est ajouté à la fin de la note |
| `jarvis verdict P I --pr N` | lit cette PR au lieu de celle que le registre connaît |
| `jarvis verdict P I --stdin` | analyse un compte rendu fourni sur l'entrée standard (relecteur qui n'a publié que dans l'issue) |
| `jarvis verdict P I pret\|corrections "résumé"` | saisie à la main, comme avant — voir « Autorisations » |

La PR est cherchée dans cet ordre : `--pr`, la relecture lancée avec `--revue N` (`taches.pr_connue`), puis
`gh pr list --head <branche de la production>`. `gh` est lancé dans le dossier du projet, en lecture seule
(`api user`, `pr view`, `pr list`), 8 secondes par appel.

Motifs de refus, chacun avec son message : verdict **absent** (aucune PR connue, `gh` muet, PR sans verdict, verdict
plus ancien que l'essai jugé) ; **non conforme** (verdict hors de la première ligne, `CORRECTIONS` sans liste, `PRÊT`
avec des corrections, correction sans sévérité ou sans `fichier:ligne`, plus de 20 000 caractères, plus de 20
corrections) ; **ambigu** (deux décisions différentes dans le texte, ou une ligne de verdict qui porte autre chose
que la décision : « VERDICT : PRÊT ou CORRECTIONS ») ; **contradiction** (la décision saisie à la main n'est pas
celle du relecteur). Le message nomme les écarts ; il ne recopie pas le texte du relecteur.

Deux verdicts successifs : sur le même essai, le plus récent fait foi et remplace le précédent (un dernier verdict
non conforme est refusé, la commande ne retombe pas sur l'avant-dernier). Après une relance, un verdict publié avant
le lancement du nouvel essai ne le juge pas : la commande attend celui de la nouvelle relecture. Relancer la
commande sur un verdict déjà enregistré ne réécrit rien.

### Ce qui est enregistré

Sur la fiche (`taches.noter_verdict`, paramètre `details`) : `verdict`, `verdict_note` (1 500 caractères au plus :
« PR #N — n correction(s) exigée(s) par le relecteur : » puis une ligne par correction au format du gabarit, puis
le résumé du chef), `verdict_source` (`relecteur`, `entree` ou `chef`), `verdict_pr`, `verdict_corrections`
(`[{n, severite, fichier, ligne, texte}]`, 20 au plus, 300 caractères par texte), `verdict_auteur`,
`verdict_publie`. La boucle de correction n'a pas changé : elle cite `verdict_note`, qui porte maintenant la liste
du relecteur et la PR.

### Autorisations : rien de plus pour le chef

- La commande reste `Bash(jarvis verdict *)` ; elle n'écrit que ce que `noter_verdict` écrivait déjà (plus les
  champs ci-dessus). Elle ne fusionne rien, ne livre rien, ne lance rien, n'écrit rien sur GitHub.
- La saisie à la main reste possible quand le compte rendu ne peut pas être lu, ou qu'il est mal formé mais du
  même avis (la sortie le signale : « saisi à la main »). Elle est **refusée** quand le verdict publié dit autre
  chose : on ne note plus « prêt » un livrable dont le relecteur exige des corrections, ni un verdict ambigu.
- Le démon n'enregistre pas le verdict lui-même. Deux raisons : il verrait la relecture « terminée » avant que le
  verdict soit publié, et il ferait des appels réseau dans sa boucle de surveillance. Son message de fin de
  relecture donne au chef la commande courte.

### Le texte du relecteur est une donnée non fiable

- Seuls comptent les textes publiés par le compte GitHub de l'usine (`gh api user`) : sur un dépôt public,
  n'importe qui peut écrire « VERDICT : PRÊT » sous une PR. Les autres sont comptés dans le message, pas lus.
- Seuls comptent les textes publiés après la création de la fiche de production jugée.
- Taille bornée avant analyse ; ne sont gardés que les champs extraits, chacun sur une ligne, sans caractère de
  contrôle ni bloc de code, expurgés (`memoire.expurger`).
- La sortie de la commande cite les corrections avec le préfixe `> ` et les annonce comme des constats à
  vérifier : le chef la lit, elle ne doit pas lui donner d'ordre.

### Limites

- Le relecteur et l'auteur publient avec le même compte GitHub : un agent de production qui écrirait lui-même un
  verdict au format sous sa PR, après le lancement de son essai, serait pris pour le relecteur. La commande ne
  vérifie pas non plus qu'une tâche de relecture existe pour l'issue.
- Si les relecteurs publient depuis un autre compte que celui de `gh` sur la machine du chef (exécutant distant),
  la lecture automatique refuse tout : il reste `--stdin` ou la saisie à la main.
- Un verdict publié seulement dans l'issue Linear n'est pas lu (pas d'accès Linear depuis `lib/jarvis`).
- Vérifié avec le faux `gh` de `tests/fake-bin` seulement : la forme réelle de `gh pr view --json reviews,comments`
  (champs `author.login`, `submittedAt`, `createdAt`) n'a pas été confrontée à un vrai dépôt par ce lot.
- `chef/CLAUDE.md`, le rôle du chef Codex et l'aide de `bin/jarvis` décrivent encore la recopie à la main (toujours
  valide) : à mettre à jour par les volets qui portent ces fichiers.

Fichiers : `lib/jarvis/verdicts.py` (lecture, garde-fous, enregistrement), `lib/jarvis/comptes_rendus.py` (champ
`ambigu`), `lib/jarvis/taches.py` (`noter_verdict(details=…)`), `lib/jarvis/cli.py` (`cmd_verdict`),
`lib/jarvis/daemon.py` (message de fin de relecture), `tests/test_verdict_auto.py`, `tests/fake-bin/gh` (`api user`).

## Volet chef (lot 2)

Objet : le rôle du chef (`chef/CLAUDE.md`), sa variante générée pour Codex (`chef_moteur.role_codex`) et la table
de ses commandes.

### Ce qui change

| Avant | Après |
|---|---|
| Table de 62 lignes de commandes dans le rôle | `jarvis aide chef [mots…]`, lecture seule, générée depuis `lib/jarvis/chef_aide.py` ; le rôle garde 20 lignes d'essentiel et une liste « Règles attachées aux outils » |
| Rôle Codex = rôle Claude avec les commandes préfixées | Rôle Codex traduit : `chef_moteur.TRADUCTIONS_CODEX` remplace chaque consigne que Codex ne peut pas suivre |
| « Lance un sous-agent avocat du diable (outil Task) » envoyé à Codex | Contre-expertise en deuxième passe, menée par le chef Codex lui-même, en cinq étapes écrites (`CONTRE_EXPERTISE_CODEX`) |
| `WebSearch`, `WebFetch`, « outil Read », « puis /exit » dans le rôle Codex | « ta recherche web native », « ton outil de lecture de fichier », « termine ton tour sans rien entreprendre d'autre » |
| `jarvis board voir` et `jarvis board espaces` documentés mais refusés par la porte du chef Codex | Ajoutés à `AUTORISE` (lectures seules) |
| `jarvis board relectures` ouvrait le tableau de bord workmux (`bin/jarvis` ne le routait pas) | Routé vers Python, comme `relire` ; un test compare les actions de `bin/jarvis` à celles de l'analyseur |
| Aucun exemple de plan ni de bilan | Un exemple complet de plan (mémoire, jetons, vague, pré-mortem, contre-expertise, commande) et un exemple de bilan (`jarvis note` + `jarvis memoire noter`) |

Le chef Claude garde sa consigne d'origine pour la contre-expertise (sous-agent par l'outil Task) : seule la
variante Codex est traduite.

### Entrées ajoutées aux permissions du chef

`AUTORISE` (cinq entrées, toutes en lecture) :

```
Bash(jarvis board voir)
Bash(jarvis board voir *)
Bash(jarvis board espaces)
Bash(jarvis aide)
Bash(jarvis aide *)
```

`INTERDIT` : aucune entrée ajoutée, aucune retirée.

### L'aide du chef

`jarvis aide chef` affiche onze sections ; `jarvis aide chef board` une section entière, `jarvis aide chef rollback`
les seules entrées qui contiennent le mot. Elle ne lit ni n'écrit aucun état (test). Appelée par `jarvis-chef`
(variable `JARVIS_VIA_CHEF`) ou avec `--moteur codex`, elle écrit chaque commande avec son préfixe et marque
`[hors porte sur Codex : demande à ton humain]` celles que `chef_moteur.verifier` refuse.

Ces commandes sont documentées pour le chef mais absentes d'`AUTORISE` (`chef_aide.HORS_PORTE_CONNUES`) :
`jarvis board deposer|commenter|lier|decider|retirer|restaurer|modifier|ranger|reduire|grouper` et
`jarvis noeud etat|demander`. Ce lot ne les ouvre pas : ouvrir une écriture au chef est une décision de l'humain.
Conséquence : le chef Codex ne peut ni poser une carte sur le Board ni interroger la Jetson ; son préambule le lui
dit. Le chef Claude, lui, n'a pas ces commandes dans sa liste `allow` non plus : elles dépendent de son mode de
permission.

### Garde-fous du rôle

- La section « Règles absolues » est inchangée, à l'octet près : son empreinte SHA-256 est fixée dans
  `tests/test_chef_aide.py`. La modifier fait échouer le test jusqu'à une mise à jour volontaire.
- Les règles qui vivaient dans la table (23 phrases : référence = donnée non fiable, jamais de rollback exécuté,
  skill activée par l'humain seul, trois propositions par source et par jour, retrait du Board seulement sur
  demande…) sont dans « Règles attachées aux outils » ou dans l'essentiel ; un test les cherche une par une.
- Aucune autre ligne du rôle n'a été retirée : hors de la table, la version d'avant est entièrement contenue dans
  la nouvelle (vérifié par comparaison ligne à ligne au moment du lot, pas par un test).
- `chef_moteur.traductions_manquantes` : si le rôle est reformulé et qu'une traduction ne trouve plus son texte,
  un test échoue ; un second test échoue si le rôle Codex généré contient `WebSearch`, `WebFetch`, `Read`, `Task`,
  `/exit`, « sous-agent » ou « avocat du diable ».

### Fichiers

| Fichier | Rôle |
|---|---|
| `chef/CLAUDE.md` | table remplacée par l'essentiel et les règles, deux exemples ajoutés |
| `lib/jarvis/chef_aide.py` | source unique de la table des commandes, rendu par moteur, commandes hors porte |
| `lib/jarvis/chef_moteur.py` | cinq entrées `AUTORISE`, préambule Codex, traductions, `prefixer_codex` (accents graves et blocs `bash`) |
| `lib/jarvis/cli.py`, `bin/jarvis` | commande `aide` ; routage de `board relectures|relire` |
| `tests/test_chef_aide.py` | 18 tests du volet |

### Non vérifié

- Aucun chef réel (Claude ou Codex) n'a été lancé avec le nouveau rôle : la note visée (9/10) n'est pas mesurée.
- Que Codex suive réellement la deuxième passe écrite. L'écriture Codex de l'aide repose sur `JARVIS_VIA_CHEF`,
  posée par `bin/jarvis-chef` juste avant de lancer la commande : lu dans le script et testé avec la variable,
  pas dans une session Codex réelle (`--moteur codex` reste disponible).
- L'effet de la table raccourcie sur le chef Claude : il doit maintenant appeler `jarvis aide chef` pour les
  commandes rares (rollback, skills, Board en écriture).

## Lot 2 — intégration des quatre volets (branche `feat/agents-qualite-2`)

Les branches `feat/aq2-briefs`, `feat/aq2-prompt`, `feat/aq2-verdict` et `feat/aq2-chef` sont fusionnées ici. Ce
que la fusion a ajouté pour que les volets se répondent :

- **Briefs et bloc d'outils** : `recherche`, `frontend`, `qa` et `design` renvoient à la section « Outils de cette
  session » du prompt pour la recherche web et Playwright, au lieu de supposer l'outil présent ou absent. Le prompt
  d'évaluation n'a pas ce bloc : la consigne « fais un essai réel » y reste la seule vérification.
- **Verdict automatique dans le rôle du chef** : l'étape 7 de `chef/CLAUDE.md`, la table « L'essentiel »,
  `jarvis aide chef` et l'aide de `bin/jarvis` décrivent `jarvis verdict <projet> <ISSUE>` tel qu'il est codé —
  lecture sur la PR, trois refus (absent, non conforme ou ambigu, contradiction) et ce que le chef fait de
  chacun, saisie à la main en repli. Le rôle Codex est généré à partir de ce texte : il suit.
- **Incertitude bloquante** : `templates/CLAUDE.md`, `templates/AGENTS.md`, le `CLAUDE.md` du dépôt et l'étape 6
  du rôle du chef disent comme le prompt : question, puis poursuite de la partie non touchée.
- **Mémoire** : l'étape 5 du rôle du chef dit que les leçons remontent d'après le sujet des consignes.
- **Évaluation d'un relecteur** : `prompt_agent.pour_evaluation` donne au rôle `revue` le gabarit du verdict et
  non plus « ✅ TERMINÉ » ; `evaluation.analyser_sortie` relit alors le dernier bloc « VERDICT : … » de la sortie.
- **`jarvis eval resultats`** affiche l'état du compte rendu (conforme, non conforme avec le nombre d'anomalies,
  absent, ou non analysé pour un résultat antérieur au champ).

Non vérifié par cette fusion : aucun agent, chef ou modèle réel n'a été lancé ; la note visée de 9/10 n'est pas
mesurée. Les limites de chaque volet (sections ci-dessus) restent entières.

## Lot 2 — relecture adverse (corrections)

Deux relecteurs adverses ont relu la branche. Tous leurs constats ont été reproduits sur le code d'avant, puis
corrigés ; chacun a son test dans `tests/test_aq2_adverse.py` (ou dans le fichier de tests du volet).

### Verdict : lié à une relecture, pas à un compte

L'auteur d'un travail et son relecteur publient avec le même compte GitHub. Le filtre « publié par le compte de
l'usine » ne distinguait donc pas le juge du jugé : un « VERDICT : PRÊT » de l'auteur sous sa propre PR passait
pour celui du relecteur, et bloquait ensuite la saisie « corrections ».

| Garde | Où |
|---|---|
| Une relecture (rôle `revue` ou `--revue`) lancée **après** la production jugée est exigée ; seuls comptent les textes publiés après **son** lancement | `verdicts._relecture`, `verdicts.chercher` |
| Jeton de relecture : tiré au lancement (`jarvis prompt-construire --jeton-sortie`), écrit dans le seul prompt du relecteur (`VERDICT : PRÊT [R-…]`), gardé sur sa fiche sous forme d'empreinte SHA-256 (`jeton_verdict`) ; un texte sans ce jeton n'est pas lu | `bin/jarvis`, `cli.cmd_prompt_construire`, `taches.enregistrer`, `comptes_rendus.gabarit_verdict` |
| Une fois publié, le jeton se lit sur la PR : un « PRÊT » qui suit un « CORRECTIONS » de la même relecture est refusé (nouvelle relecture, nouveau jeton). L'inverse est accepté | `verdicts.chercher` |
| La ligne du verdict n'accepte devant « VERDICT » que les décorations de bonne foi (gras, code, titre, citation) : ni commentaire HTML, ni texte barré, ni puce | `comptes_rendus._VERDICT` |
| `--pr N` ne désigne qu'une PR de l'issue : celle de la relecture, ou une PR dont la branche est celle de la production (`headRefName`) | `verdicts.chercher` |
| Saisie à la main : `corrections` toujours accepté ; `pret` refusé contre un texte de l'usine qui demande des corrections, et quand la PR n'a pas pu être consultée ; `--stdin` et un `--pr` étranger réservés à l'humain | `verdicts.enregistrer`, `chef_moteur.INTERDIT` |

Ce que le chef **garde** : saisir `pret` à la main quand la PR est lisible et ne porte aucun verdict de la
relecture (relecteur qui n'a publié que dans l'issue, livrable sans PR). La documentation ne présente plus la
commande comme lui retirant ce pouvoir.

Limites, dites telles quelles :

- Le jeton est en clair dans le fichier de prompt du relecteur (`/tmp`, même utilisateur Unix que les autres
  agents). Un agent de production qui irait le lire pourrait écrire un verdict qui le porte : les agents ne sont
  pas isolés les uns des autres sur ce poste, et ce lot n'y change rien. Le jeton empêche qu'un commentaire écrit
  sans lui passe pour un verdict, pas davantage.
- Une relecture lancée avant cette version n'a pas de jeton : son verdict ne se lit plus seul, il se saisit.
- La fiche de relecture n'a pas besoin d'être « terminée » : le démon voit la fin d'un agent avec retard, et
  c'est le jeton, pas le statut, qui lie le texte à la relecture.
- Vérifié avec le faux `gh` seulement (champ `headRefName` compris).

### Comptes rendus : ce que la machine refuse maintenant

- **Rubrique « Critères »** dans le verdict (`critère → satisfait + preuve, ou non satisfait : correction n°`),
  avant « Corrections exigées » : le prompt du relecteur exigeait une preuve par critère sans rubrique pour la
  porter. Son absence est une anomalie, comme un critère sans preuve.
- **Aucune vérification lancée** (`commande → résultat`) : anomalie. Un « PRÊT » sans rien avoir lancé n'est plus
  enregistré par `jarvis verdict`.
- **`fichier:ligne`** : un nom sans extension suivi de sa ligne compte (`Makefile:12`, `Dockerfile:3`) ; pour un
  manque, la règle est écrite : le fichier où l'ajout est attendu, ligne 1.
- **Flèche dans la commande** : quand la commande est entre accents graves, le résultat se cherche après eux.
- **Suite d'une correction** sur une ligne non indentée : rattachée à la correction, plus perdue.
- **Gabarit recopié** (« <commande lancée> »…) : anomalie « gabarit non rempli », pour les deux formats ;
  `evaluation.analyser_sortie` réutilise ce contrôle.
- `preuve_par_test` exige une référence de test (`test_x`, `tests/…`, `x.test.ts`) et refuse une preuve qui
  commence par une négation.

### Prompt de l'agent

- La boucle de correction ne promeut plus aucun commentaire de PR en « corrections » : elle cite les corrections
  de la fiche (`verdict_corrections`, quand le verdict vient du relecteur) et tous les commentaires, préfixés
  `> `, avec « compte externe » dans l'en-tête quand l'auteur n'est pas le compte de l'usine (« compte non
  vérifié » quand `gh api user` ne répond pas).
- Bloc « Outils de cette session » : lignes **Linear** et **`gh`** ; un nom de serveur choisi par le dépôt
  (`.mcp.json`) n'est repris que sous la forme `[a-z0-9][a-z0-9_-]{0,31}`, sinon seul le nombre est écrit, et
  il ne sert jamais à conclure « Playwright présent » ni « Linear configuré ». Un nom valide reste un texte
  choisi par le dépôt : il est marqué comme tel, pas neutralisé.
- Protocole : le repli « Sans outil Linear » est dit une fois (plan, question et compte rendu dans la PR ou la
  réponse finale ; arrêt si ni l'issue ni aucun critère ne sont lisibles). Rôle à livrables : PR seulement s'il
  y a des sources à versionner.
- Relecteur : budget et modèle parlent de son verdict (plus de « pousse ta branche », ni de « Risques ») ; en
  évaluation, l'option prudente va en tête des « Suggestions ». Producteur évalué : conditions de fin sans PR ni
  publication.
- Le format du verdict n'est plus redit par l'étape 6 du brief `revue` ni par la consigne du cas d'évaluation.

### Chef

- `jarvis board voir` (lecture du chef) : ligne de cadrage, contenus préfixés `> `, titres entre « », marqueur
  `[JARVIS` neutralisé en `[JARVIS cité`. La règle « Board, lecture » du rôle le dit. La lecture Telegram n'est
  pas changée.
- Rôle Codex : les commandes interdites au chef (celles d'un agent, comme `jarvis lourd exec`, ou de l'humain)
  ne sont plus préfixées par `jarvis-chef` ; le préambule dit ce que vaut une commande sans préfixe.
- `bin/jarvis-chef-codex` passe `-c project_doc_max_bytes=131072`. La documentation publique de Codex donne
  32 Kio par défaut pour ce réglage, et le rôle généré en pèse environ 58 : sans lui, la fin du rôle (étape 7,
  bilan, plafonds, rollback, studio, veilles, plan de nuit) n'aurait pas été lue. **Non vérifié** : que la version
  installée (codex-cli 0.164.0) applique bien ce réglage passé par `-c` ; aucun chef Codex réel n'a été lancé.
  Un test borne la taille du rôle à 60 % de la valeur passée.

### Cas de référence

Les vérifications de `revue/verdict-au-format`, `recherche/comparatif-source`, `marketing/annonces-verifiables`
et `architecte/adr-file-de-courriels` jugent le fond qu'elles disent mesurer (défauts nommés, faits conformes au
relevé cité, annonce comparée à la ligne qui la prouve, chemins lus par leur forme). Ce sont des contrôles par
motif : ils refusent les fautes connues, ils ne comprennent pas le texte. La référence marketing a changé d'une
ligne (un nombre venait d'une autre ligne du README que celle citée en preuve).

### Historique

Les quatre fusions de la branche portaient le message anglais par défaut de git, sans ligne `Co-Authored-By`.
Elles ont été recréées à l'identique (mêmes arbres, mêmes parents) avec un message conforme ; la branche n'était
pas poussée. L'ancienne tête reste sous l'étiquette locale `sauvegarde/aq2-avant-reecriture`.
