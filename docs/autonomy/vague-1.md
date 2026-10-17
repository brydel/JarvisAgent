# Vague 1 — plafonds de jetons, coûts, mémoire, bilan quotidien, échecs bornés, secrets par rôle

Branche `claude/vague-1-budgets-memoire` (sur `claude/autonomie-lot1`). Statuts : **implémenté/testé** =
code et tests déterministes verts dans le conteneur de développement ; **non vérifié sur ton PC** = le
comportement réel avec Claude Code, Codex et workmux reste à constater chez toi.

## Deux principes rappelés

- **Équivalent API ≠ dépense.** Les agents tournent sur tes abonnements : une tâche consomme du quota, pas
  d'argent en plus. `jarvis cout` affiche ce que la tâche aurait coûté au tarif API public, pour comparer et
  repérer les dérapages. Les vraies dépenses restent dans `jarvis budget`.
- **Les jetons se lisent après coup** (journaux des CLI). L'admission refuse une relance au-delà du plafond ;
  pendant le travail, le démon relit la consommation toutes les 5 minutes et demande à l'agent qui dépasse de
  committer et de s'arrêter. Il ne coupe pas un agent au milieu d'une commande.

## P1.1 — Plafond de jetons par unité de travail — implémenté/testé

- **Unité de travail** = (projet, issue, rôle). Toutes les relances d'une même unité partagent son plafond.
- Plafond d'un élément de plan : imposé (`projet:ISSUE:auto@backend+L%3M`) ou calculé à la création du plan :
  `budget_jetons.multiplicateur` (3) × estimation. L'estimation est la médiane des tâches terminées de même rôle
  et taille sur 60 jours dès qu'il y en a 5 ; sinon `budget_jetons.estimation_s|m|l` (300k / 800k / 2M). Le plan
  affiche « ≤ 2.4 M jetons » : l'humain valide le plafond en même temps que le plan.
- Admission (`admission.demander`) : jetons déjà consommés par l'unité ≥ plafond → refus `budget_jetons`
  (sortie 8), l'élément de plan reste lançable, le chef est prévenu, le refus est journalisé.
- Démon (`jetons_check`) : une tâche ouverte qui atteint le plafond reçoit l'ordre de committer et de
  s'arrêter, une seule fois ; le chef est prévenu ; journal « budget/plafond_jetons ».
- Commandes : `jarvis budget-jetons voir <T>`, `jarvis budget-jetons defaut --role R --taille M`.
- Limites : mesure Claude = entrée + sortie + écriture de cache ; Codex = entrée non cachée + sortie (formats des
  CLI). Une tâche manuelle (hors plan) reçoit le plafond par défaut de son rôle et de sa taille.

## P1.2 — `jarvis cout` — implémenté/testé (tarifs à revérifier pour Codex)

- Tarifs `prix_in`, `prix_out`, `prix_cache_lecture`, `prix_cache_ecriture` (dollars US par million de jetons)
  dans `config/modeles.toml`, avec `prix_source` et `prix_date` (2026-10-17). Claude : tableau officiel
  (entrée/sortie de tous les modèles, cache de Fable). Codex : source tierce citant la page officielle, marquée
  « à revérifier ». Un cache non publié est estimé (0,1 × et 1,25 × le prix d'entrée), un modèle sans tarif
  utilise celui de référence du fournisseur (sonnet, sol) : la ligne est marquée « estimation ».
- `jarvis cout tache <T>`, `jarvis cout projet <P> --periode 7j`, `jarvis cout semaine` (tâches les plus
  coûteuses, total par projet).
- Monnaie : dollars US tant que `couts.taux` n'est pas réglé ; `jarvis regler couts.taux 0.86` (taux du jour,
  à toi de le fixer) affiche en euros (`couts.devise`, EUR par défaut).

## P1.3 — Mémoire du chef — implémenté/testé

- `memoire.jsonl` (ajout seul, 5 000 entrées au plus) : titre, corps, décisions, échecs, leçons, projet, étiquettes.
- `jarvis memoire noter --titre … --decisions "a ; b" --echecs … --lecons … --projet P`,
  `jarvis memoire chercher <mots>` (titre × 3, leçons × 2, le reste × 1 ; préfixes de 4 lettres ; 90 jours ;
  à score égal, la plus récente), `jarvis memoire liste`.
- `jarvis note` alimente aussi la mémoire (le journal reste la référence).
- Expurgation de ce qui ressemble à un secret (clés `sk-…`, jetons GitHub/Slack/Telegram, longues chaînes
  mêlant majuscules, minuscules et chiffres) ; les chemins et empreintes git sont gardés.
- `recherche_semantique` : point d'extension pour Mem0, inactif tant que `memoire.semantique` n'est pas réglé et
  la bibliothèque absente — **conçu**, aucune donnée ne quitte le poste.
- `chef/CLAUDE.md`, section « Mémoire » : chercher avant chaque plan, noter après chaque vague.

## P1.4 — Bilan quotidien Telegram — implémenté/testé (envoi réel non vérifié sur ton PC)

- `jarvis bilan quotidien [--envoyer]` : en tête « livré · échoué · équivalent API » (24 h), puis livré, prouvé
  (relectures « prêt », travaux terminés avec preuve), échoué (avec classe), consommé (jetons par fournisseur,
  dépenses réelles, quotas en alerte ou périmés), risques (pauses, exceptions), décisions demandées (plans,
  exceptions, escalades, propositions).
- Le démon l'envoie une fois par jour à partir de `bilan.heure` (08:00, heure locale du PC) ; `bilan.actif = false`
  le coupe ; rattrapage le jour même si le PC était éteint à 08:00.

## P1.5 — Échecs classés et reprise bornée — implémenté/testé

- Classes : `quota` et `bloque` constatées par le démon (arrêt pour jetons épuisés ; attente d'une réponse plus
  longue que `general.blocage_min`) ; `erreur_outil`, `hors_perimetre`, `regression` déclarées par le chef, le
  relecteur ou toi (`jarvis tache echec <T> <classe> [note]`), jamais par l'agent concerné. Une classe déclarée
  n'est pas écrasée par une constatée.
- Essais comptés par unité : ni les lancements jamais démarrés, ni les arrêts pour quota.
- **2 essais automatiques au plus** : au 3e, l'admission refuse `escalade` (sortie 9), l'élément de plan reste
  lançable ; `jarvis tache relancer <T> --autoriser` (humain, terminal) débloque **un** essai de plus.
- Après `erreur_outil`, `hors_perimetre` ou `regression`, le 2e essai doit changer d'approche : même fournisseur,
  même modèle et mêmes consignes (empreinte du fichier) → refus `meme_approche`. Vérifié pour les lancements par
  plan (modèle connu) ; un lancement manuel par un humain n'est pas contraint.
- Une reprise après redémarrage continue le même essai : pas comptée.
- `jarvis tache voir <T>` : classe d'échec, essais comptés / autorisés, jetons de l'unité face au plafond,
  équivalent API.

## P1.6 — Secrets minimaux par tâche — implémenté/testé (Codex réel non vérifié sur ton PC)

- `~/.config/jarvis/secrets/<projet>.toml` : `[role.backend] vars = ["STRIPE_KEY"]`, `[role."*"]` pour tous.
  `~/.config/jarvis/secrets/<projet>.env` : les valeurs, **permissions 600 exigées** (sinon rien n'est injecté et
  le fil le signale).
- Les lanceurs injectent dans l'environnement de l'agent seulement les noms autorisés pour le rôle de la tâche.
  Noms interdits : variables système et de Jarvis (`PATH`, `HOME`, `LD_*`, `JARVIS_*`, proxys…).
- Codex retire par défaut de ses sous-processus toute variable dont le nom contient KEY, SECRET ou TOKEN : quand
  une tâche reçoit des secrets, `jarvis-codex` désactive ce filtre et exclut nommément les autres variables
  sensibles présentes (noms sur la ligne de commande, jamais de valeur). Syntaxe des réglages Codex relevée dans
  une source tierce citant la documentation officielle : à constater sur ton PC.
- `jarvis secrets verifier --projet P` : par rôle, les noms qui seraient injectés et s'ils sont définis.
- Valeurs : jamais dans le prompt, les fichiers d'état, le fil, le journal d'audit ; seuls les noms sont tracés.
- **Limite** : un agent voit les variables qu'il reçoit. Ce mécanisme réduit ce qui peut fuiter d'une tâche ;
  il n'isole pas un agent de ses propres secrets et n'empêche pas un `.env` que tu copies toi-même dans un worktree.

## Tests

`tests/test_vague1.py` : 11 tests (plafonds, refus et notification, arrêt démon unique, coûts et estimations,
mémoire pondérée et expurgée, bilan et envoi quotidien unique, classes et borne d'essais, droits de
classement et « bloque » constaté, secrets par rôle et jamais stockés, refus si fichier trop ouvert, lanceur
Codex). Suite complète : 124 tests verts.

## Réglages ajoutés

| Clé | Défaut | Rôle |
| --- | --- | --- |
| `budget_jetons.actif` · `.multiplicateur` | `true` · `3` | Plafond par unité de travail |
| `budget_jetons.estimation_s/m/l` | `300000` · `800000` · `2000000` | Estimation tant que l'historique manque |
| `budget_jetons.verification_min` | `5` | Fréquence de relecture par le démon |
| `couts.devise` · `couts.taux` | `EUR` · `0` | Affichage de l'équivalent API (0 = dollars US) |
| `bilan.actif` · `bilan.heure` | `true` · `08:00` | Bilan quotidien Telegram |

`jarvis regler` refuse désormais une valeur qui rendrait la configuration invalide, et accepte les nombres
décimaux (`couts.taux`, `budget_jetons.multiplicateur`).
