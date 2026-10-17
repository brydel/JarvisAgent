# Vague 3 — skills de confiance, briefs auto-améliorés, vers plusieurs machines

Branche `claude/vague-3-leadership` (sur `claude/vague-2-differenciation`). Statuts : **implémenté/testé** = code
et tests déterministes verts dans le conteneur de développement ; **non vérifié sur ton PC** = le comportement
réel (Claude, Telegram, ta clé SSH, ton démon) reste à constater chez toi ; **conçu** = rien ne s'exécute.

## Trois choix rappelés

- **Rien de payant.** L'optimisation des briefs utilise tes abonnements (`claude -p` pour réfléchir, `jarvis eval
  lancer` pour mesurer). GEPA via DSPy (clés d'API) : conçu, non branché.
- **SQLite en option.** Mêmes fonctions de `store.py` ; JSON reste le défaut ; le journal d'audit chaîné n'est
  jamais converti.
- **Un seul poste pour l'instant.** Bail et exécutants sont réels mais locaux : plusieurs machines demanderont un
  état partagé sur un serveur (conçu).

## P3.2 — Registre de skills avec confiance — implémenté/testé ; vraie signature SSH non vérifiée

- `skill.lock` dans chaque skill : nom, version, empreinte SHA-256 de tout le dossier (chemins + contenus, lock
  exclu ; les droits d'exécution ne comptent pas, ils varient sous WSL), auteur, signature facultative.
- Les 3 skills du dépôt sont épinglées. **Après une modification volontaire d'une skill du dépôt**, lance
  `jarvis skill epingler <nom>` (sinon l'audit et un test la signalent).
- `jarvis skill installer <dossier|https://…git>` : copie en quarantaine (`~/.local/share/jarvis/skills-quarantaine`,
  hors des dossiers lus par Claude et Codex). Refus si le lock fourni ne correspond pas au contenu, si la
  signature est invalide, ou si le nom est celui d'une skill du dépôt. Liens symboliques refusés.
- Activation seulement par toi : bouton Telegram « Activer » ou `jarvis skill approuver <nom>` au terminal
  (niveau 3). La copie doit être identique à celle annoncée ; un fichier existant non géré par Jarvis n'est jamais
  écrasé ; une ancienne version est sauvegardée. Le chef peut proposer une installation, jamais l'approuver.
- `jarvis skill auditer` : épinglée, modifiée, non épinglée, signature invalide, quarantaine, et **hors registre**
  (lue par les agents sans être passée par Jarvis — tes autres skills, par exemple). Le démon audite toutes les
  heures et te prévient **une seule fois** par problème nouveau ; il ne désactive rien.
- Signature : `jarvis skill epingler <nom> --signer ~/.ssh/id_ed25519` (ssh-keygen -Y sign) ; auteurs de confiance
  dans `~/.config/jarvis/skills_signataires` (format allowed_signers d'OpenSSH). Testé avec un faux ssh-keygen :
  la plomberie est vérifiée, pas l'outil réel.

## P3.1 — Briefs de rôles auto-améliorés — implémenté/testé ; mode abonnement non vérifié sur ton PC

- `outils/optimiser_prompts.py --role R` : boucle à la GEPA (réfléchir sur les échecs, réécrire, mesurer, garder
  le meilleur sans perdre un cas réussi). Données : goldens du rôle et échecs classés du registre (expurgés).
- Garde-fous : cas coupés en **entraînement** et **protégés** (jamais montrés à l'optimiseur, servent seulement à
  décider ; candidat rejeté s'il fait moins bien que le stable sur eux) ; empreinte de `tests/goldens` relevée
  avant et après (tout annulé si elle change) ; le candidat doit garder les règles exigées et ne touche pas
  l'en-tête du rôle ; **rien n'est jamais écrit dans `roles/`**.
- Modes : `fixtures` (défaut, simulation déterministe pour vérifier la boucle, jamais soumise), `abonnement`
  (`--confirmer`, vrais agents via l'admission), `dspy` (conçu, refusé).
- `--appliquer` soumet le candidat (`jarvis role proposer`) : message Telegram avec le diff et les scores.
- Ton accord (bouton ou `jarvis role approuver RB-…`) : **canari** sur 10 % des unités de travail du rôle
  (`optimisation.canari_pct`), tirage déterministe par (projet, issue, rôle) ; la fiche de tâche note la version
  reçue (`brief`). Le démon compare chaque heure : ≥ 3 tâches du candidat et 25 points d'échec de plus que le
  stable → **retour automatique au brief stable** (aucune nouvelle approbation : c'est revenir à ce que tu as
  validé). Brief stable modifié pendant l'essai → candidat périmé.
- `jarvis role promouvoir RB-…` (toi seulement) : écrit le brief dans `~/.config/jarvis/roles/<rôle>.md` (en-tête
  conservé, ancien fichier sauvegardé). Le dépôt n'est pas modifié.
- Hebdomadaire : `jarvis regler optimisation.hebdo true` — désactivé par défaut. La nuit de `optimisation.jour`
  (7 = dimanche) après `optimisation.heure`, un rôle par semaine à tour de rôle (`optimisation.roles`), en
  arrière-plan ; chaque mesure passe par l'admission (pause, quota, capacité). Journal :
  `~/.local/share/jarvis/optimisation/`.
- Limites : 3 cas par rôle, c'est peu (2 d'entraînement, 1 protégé) : un gain mesuré reste fragile, d'où le canari.
  Le retrait compare des tâches réelles différentes : signal statistique faible sur peu de tâches.

## P3.3 — Vers plusieurs machines — implémenté/testé (poste unique) ; partage entre machines conçu

- **Stockage SQLite** (`stockage.backend`) : table `etat` (nom → JSON) dans `~/.local/state/jarvis/jarvis.db`,
  WAL, transactions `BEGIN IMMEDIATE` (imbriquées : même transaction), reconnexion si la base est remplacée.
  Restent des fichiers : `*.jsonl` (journal d'audit chaîné, fil, événements, mémoire), marqueurs, `lourdes/`.
  Toute la suite de tests passe dans les deux modes (`JARVIS_STOCKAGE=sqlite`).
- `jarvis stockage migrer` (toi, démon arrêté) : import de chaque JSON, relecture et comparaison valeur par valeur,
  puis bascule ; copie des JSON dans `sauvegardes/json-…`. `jarvis stockage revenir` : export, vérification,
  bascule. Refusé tant qu'un démon tient le bail.
- **Bail d'orchestrateur** (`bail.py`) : le démon le prend au démarrage (sinon il refuse de démarrer et dit qui le
  tient), le renouvelle à chaque tour (120 s), le rend à l'arrêt (Ctrl+C ou SIGTERM). Repris si expiré ou si le
  titulaire est mort sur ce poste ; numéro incrémenté à chaque prise : un démon qui perd le bail s'arrête.
- **Exécutants déclarés** (`jarvis executant liste|declarer|retirer`) : « local » mesuré par le démon chaque minute
  (cœurs, mémoire, agents au maximum) ; d'autres déclarables à la main. L'admission n'utilise que le poste local.
- Limites : SQLite ne se partage pas par le réseau ; bail et exécutants protègent un poste. Plusieurs machines =
  base partagée (PostgreSQL ou service) + exécutants distants qui reçoivent du travail : conçu.

## Tests

`tests/test_vague3.py` : 14 tests (skills épinglées, quarantaine et approbation, empreinte modifiée, fichier non
géré jamais écrasé, signature ; optimiseur sans écriture et cas protégés cachés, surapprentissage et goldens
modifiés ; règles et en-tête du brief, canari/retrait/promotion, hebdomadaire ; bail, démon refusé et bail perdu,
migration sans perte et retour, exécutants). Suite complète : voir `tests.md`.

## Ce qui reste

- Sur ton PC : `jarvis skill auditer`, une installation de skill approuvée depuis Telegram, une signature avec ta
  clé SSH, `python3 outils/optimiser_prompts.py --role backend --mode abonnement --confirmer` (sans `--appliquer`
  d'abord), `jarvis stockage migrer` démon arrêté puis une journée normale.
- Plusieurs machines (base partagée, exécutants distants), GEPA/DSPy : à décider plus tard.
