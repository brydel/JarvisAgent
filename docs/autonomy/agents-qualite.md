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
| Mémoire long terme lue par le chef seulement | 3 à 5 entrées pertinentes dans le prompt de chaque agent |
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
   - *Mémoire de l'usine* : `memoire.chercher(projet + issue + rôle + mots des consignes, projet=…, limite=5)`,
     une ligne par entrée (420 caractères au plus), puis les leçons **retenues** du réseau (relues, avec preuve) ;
   - *Historique de cette tâche* : les essais de l'unité (projet, issue, rôle) — statut, classe d'échec et sa note,
     verdict et son résumé, jetons (`taches.historique`) ; pour une relecture, l'historique de la production relue ;
   - *Moyens* : taille S/M/L, plafond de jetons de la tâche (celui du plan ou de l'admission, sinon
     `couts.plafond_defaut`), jetons déjà consommés par les essais précédents, ce qui se passe au plafond ;
     modèle et effort affectés par le routeur.
7. **Protocole** — démarrage (« In Progress », plan), incertitude graduée, vérifications, fin (PR, « In Review »),
   interdits.
8. **Fini et compte rendu** — la définition de « fini » et le gabarit exact. C'est la dernière chose lue.

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
  puis il s'arrête et attend.

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
3. si `gh` répond : les corrections extraites du dernier verdict au format, puis les commentaires de revue
   (revues, commentaires, commentaires en ligne avec leur `fichier:ligne`), les 8 plus récents, 700 caractères
   chacun, 4 000 au total.

La PR est cherchée dans cet ordre : la relecture lancée avec `--revue N` sur cette issue ; un « PR #N » dans le
résumé du verdict ; `gh pr list --head <branche de l'essai corrigé>`. Chaque appel à `gh` est limité à 8 secondes
et le premier échec arrête la recherche : sans `gh`, sans réseau ou hors d'un dépôt GitHub, le prompt contient le
résumé du verdict et la commande à lancer pour lire les commentaires.

Conséquence pour le chef : le résumé passé à `jarvis verdict` est ce que l'agent relancé lira en premier. Il
reprend la liste numérotée du relecteur et cite la PR.

Un relecteur relancé sur une issue déjà en « corrections » reçoit la même liste sous « Corrections exigées à la
relecture précédente », avec la consigne de vérifier chaque point.

## Briefs de rôle

- Réécrits : `generaliste` (rôle par défaut), `redaction`, `securite` — objectif, procédure, 5 choses à ne pas
  faire, critères de « fini » vérifiables, extrait d'un bon compte rendu. `securite` cite OWASP Top 10 et ASVS,
  donne le format du rapport (`$JARVIS_LIVRABLES/securite.md`) et les outils d'audit de dépendances.
- Complétés d'une ligne : `frontend`, `qa`, `design` (Playwright sous `jarvis lourd exec navigateur`), `video`
  (où trouver `scenario-video.md`), `recherche` (pas de recherche web : le dire), `revue` (format unique).
- Inchangés : `architecte`, `backend`, `data`, `devops`, `ia-produit`, `marketing`.
- Chaque brief tient en 60 lignes au plus (test).

`evaluation.consigne_complete` construit désormais le prompt d'un cas avec `prompt_agent.pour_evaluation` :
même brief, même protocole d'incertitude, même définition de « fini » et même format de compte rendu qu'une vraie
tâche — sans Linear ni PR, et sans contexte local (mémoire, registre), pour que deux exécutions restent
comparables.

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

- La pertinence de la mémoire est celle de `memoire.chercher` (plein texte) : une entrée du projet remonte dès
  qu'elle partage un mot avec la requête. Le prompt en montre cinq au plus.
- Le numéro de PR d'une production n'est pas stocké dans sa fiche : il est déduit (relecture lancée, résumé du
  verdict, branche). Si rien ne le donne, les commentaires ne sont pas joints.
- L'analyseur n'est branché que sur la boucle de correction (extraction du verdict d'une revue de PR) et sur sa
  ligne de commande. `jarvis verdict` prend toujours son résumé du chef.
- Aucune évaluation réelle de rôle n'a été lancée par ce lot (elle consomme les abonnements) : seul le contrôle
  gratuit des cas (`tests/goldens`) a été exécuté.
