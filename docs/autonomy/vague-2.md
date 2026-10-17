# Vague 2 — évaluation, backend d'exécution, replay, proxy produits, observabilité, rollback

Branche `claude/vague-2-differenciation` (sur `claude/vague-1-budgets-memoire`). Statuts : **implémenté/testé** =
code et tests déterministes verts dans le conteneur de développement ; **non vérifié sur ton PC** = le
comportement réel avec Claude Code, Codex, workmux et Telegram reste à constater chez toi ; **conçu** = la
configuration existe, rien ne s'exécute.

## Trois choix rappelés

- **Rien de payant ne s'allume seul.** E2B (bacs à sable distants) est un service facturé : refusé sans SDK, sans
  clé `E2B_API_KEY` et sans enveloppe `infrastructure` dans `jarvis budget`. promptfoo et GEPA appellent des
  modèles : seule leur configuration est livrée, aucun appel n'est fait.
- **LiteLLM ne concerne pas les agents.** Claude Code et Codex restent sur tes abonnements ; un proxy les ferait
  passer sur des clés d'API payantes. Le proxy sert aux applications que l'usine construit (rôle `ia-produit`).
- **Les cas d'évaluation sont jugés par des scripts**, pas par un modèle : un résultat est reproductible et ne
  coûte rien à vérifier.

## P2.1 — Harnais d'évaluation — implémenté/testé ; exécution réelle non vérifiée sur ton PC

- `tests/goldens/<role>/<cas>/` : 15 cas, 3 par rôle (backend, frontend, qa, securite, redaction). Chaque cas :
  `cas.toml` (titre, consigne, durée max, règles que le brief du rôle doit garder), `depart/` (le projet donné à
  l'agent), `reference/` (une solution correcte) et `verifier.py`, caché à l'agent, qui sort `VERDICT: OK`.
- `jarvis eval verifier [--role R]` : sans agent, contrôle que chaque vérification **refuse** le départ,
  **accepte** la référence, et que le brief du rôle (`roles/<role>.md`) contient toujours les règles exigées.
  À lancer avant et après toute modification d'un brief : un brief appauvri casse le contrôle.
- `jarvis eval lancer <role/cas> --agent claude|codex [--modele M] --confirmer` : lance un vrai agent en mode
  non interactif sur une copie du départ, puis la vérification. Passe par l'admission (pauses, quota, capacité,
  une réservation projet `jarvis-eval`), consomme du quota, d'où `--confirmer`. Interdit au chef et aux agents.
  Résultats dans `jarvis eval resultats` et le journal d'audit. La réservation est prolongée de la durée du cas
  (l'essai n'apparaît pas dans workmux) et toujours rendue à la fin.
- Anti-triche : la vérification reçoit un jeton aléatoire avant de charger le code évalué et doit le réimprimer
  (un code qui affiche « VERDICT: OK » et quitte échoue) ; Claude reçoit l'interdiction de lire `tests/goldens/` ;
  une sortie d'agent qui cite les cas est marquée **suspecte**. **Limite honnête** : Codex (`workspace-write`) peut
  lire tout le disque, donc les références ; et un code qui lirait la vérification pourrait retrouver le jeton.
  L'évaluation mesure un agent coopératif, elle ne prouve rien contre un agent qui cherche à tricher.
- `jarvis eval promptfoo` régénère `outils/promptfoo/promptfooconfig.yaml` (fournisseur `exec:` = `jarvis eval
  lancer`) : **conçu, non exécuté**. GEPA (optimisation de prompts) : non intégré ; les goldens protégés seront
  son garde-fou au lot 4 (le candidat ne modifie ni les cas ni leurs vérifications).

## P2.2 — Backend d'exécution — implémenté/testé (workmux) ; E2B testé par une doublure uniquement

- `lib/jarvis/execution.py` : interface `ExecBackend` (`lancer`, `statut`, `capturer`, `fermer`).
- `WorkmuxBackend` reprend exactement la commande d'avant (`workmux add <branche> -a <profil> -b -P <prompt>`) :
  `jarvis task` lance désormais par `jarvis execution lancer`, qui exige une réservation d'admission active pour
  cette branche (sinon code 4) — aucun lancement ne contourne l'admission. Toute la suite existante reste verte.
- `jarvis execution lancer` n'accepte qu'une réservation **confirmée** (fiche de tâche créée), active, du même
  projet et du même worktree, **une seule fois** ; refusé à un agent (`JARVIS_METIER`).
- `E2BBackend` : désactivé. Activable par projet (`execution = "e2b"` dans `projects.toml`) seulement avec le SDK
  `e2b` installé, la clé et un budget `infrastructure`. Chaque lancement engage une dépense estimée
  (`e2b_cout_estime`, 1 $ par défaut) : l'enveloppe baisse et finit par refuser. Un échec après création arrête le
  bac à sable ; l'arrêt (`fermer`) n'exige jamais de budget. **Les vrais appels au SDK E2B n'ont jamais été faits** :
  noms de méthodes repris de la documentation publique, à vérifier avant tout usage.

## P2.3 — Événements et replay — implémenté/testé

- `evenements.jsonl` : `admis`, `lance`, `tour_agent` (l'agent attend ou a fini), `reprise`, `echec`, `verdict`,
  `plafond`, `termine`, `perdue`, écrits par l'admission, le registre des tâches et le démon. Rotation à 10 Mo.
- `jarvis rejouer <T> [--depuis N]` : chronologie numérotée, complétée par la proposition et l'approbation du plan.
  **Reconstruction, pas réexécution** : aucun modèle n'est rappelé. Les tâches antérieures à cette vague n'ont que
  le plan et leur fiche.

## P2.4 — Proxy LiteLLM pour les produits — implémenté/testé (configuration) ; jamais lancé

- `api_id` ajouté au catalogue (`config/modeles.toml`) ; table `[proxy]` (`actif = false`, port 4000, 2 nouvelles
  tentatives, délai 120 s).
- `jarvis proxy voir` / `jarvis proxy config` (humain seulement) : écrit `~/.config/jarvis/litellm.yaml` (JSON,
  YAML valide) : un modèle par entrée active, replis (`repli` puis niveau inférieur du même fournisseur). Les clés
  ne sont **jamais** écrites : `os.environ/ANTHROPIC_API_KEY`, `os.environ/OPENAI_API_KEY`.
- Installer et lancer LiteLLM reste ton choix : c'est une dépense d'API, à couvrir par un budget `services`.

## P2.5 — Observabilité — implémenté/testé ; envoi vers un vrai collecteur non vérifié

- `jarvis traces` : 20 dernières exécutions (rôle, modèle, durée, jetons, équivalent API). Tableau de bord web :
  section « Dernières exécutions ».
- `jarvis traces exporter` : fichier OTLP/JSON (`resourceSpans`) dans `~/.local/share/jarvis/traces/`. Une trace
  par tâche, spans `admission`, `agent.tour.N`, `verdict`, attributs `jarvis.jetons`, `jarvis.equivalent_api_usd`.
- `jarvis traces envoyer` : POST `/v1/traces` vers `observabilite.otlp_endpoint` (Jaeger, Tempo, Langfuse en
  OTLP…). Vide par défaut : rien ne quitte le poste. Aucun SDK requis (bibliothèque standard), donc aucun plantage
  si OpenTelemetry n'est pas installé.

## P2.6 — Rollback assisté — implémenté/testé ; bouton Telegram non vérifié sur ton PC

- `jarvis rollback proposer <T>` (niveau 1) : commits de la branche de la tâche depuis sa base, diffstat et commande
  exacte. Rien ne bouge.
- `jarvis rollback demander <T>` (niveau 2) : la proposition part sur Telegram avec « ↩ Revert » / « Garder ».
  Seul ton clic (valable 24 h) ou `jarvis rollback executer <T>` dans ton terminal fait le `git revert`.
- Base exacte : le commit du dépôt principal noté au lancement de la tâche (sinon `main` local avant
  `origin/main`) : des commits de main non poussés ne sont jamais défaits. Au-delà de 30 commits, pas de bouton
  (revert à faire au terminal) ; le message Telegram montre toujours la liste complète.
- Refusé si un agent travaille dans le worktree, si des modifications ne sont pas commitées, si la branche a bougé
  ou si la liste des commits diffère de celle approuvée. Un revert en conflit ou trop long est annulé et le
  worktree remis à la tête proposée. Si Telegram est injoignable, `demander` le dit (code 1) au lieu d'« Envoyé ». Le revert crée des commits :
  rien n'est effacé, rien n'est poussé.

## Tests

`tests/test_vague2.py` : 9 tests (goldens et protection des briefs, évaluation via admission et anti-triche,
backends et usage unique des réservations, replay, proxy, traces et collecteur local, rollback approuvé, base et
liste approuvée, rollback refusé). Une relecture indépendante a trouvé 10 problèmes, tous corrigés. Suite complète : voir `tests.md`.

## Ce qui reste

- Vérifier sur ton PC : `jarvis eval verifier`, un `jarvis eval lancer backend/pagination --confirmer` par
  fournisseur, un `jarvis rejouer` sur une vraie tâche, un rollback approuvé depuis Telegram.
- E2B réel, promptfoo exécuté, GEPA : à décider avec un budget, au lot 4.
