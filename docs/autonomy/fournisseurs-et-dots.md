# Fournisseurs (Claude, Codex), quotas, ChatGPT Dots et Codex cloud

## Adaptateurs fournisseurs (`lib/jarvis/fournisseurs.py`, `jarvis fournisseurs`)

Pour Claude Code et Codex : CLI présent et version (`--version`), indice d'authentification observable
sans lire de secret (activité récente du dossier de configuration), modèles du catalogue et leur état de
vérification (un modèle sert seulement après un essai réussi : `jarvis modele verifier`), outils, reprise
(`workmux open --continue`), quotas **tels que publiés par le fournisseur** avec source, date de mesure,
âge et péremption. Une mesure plus vieille que `jetons.peremption_h` (6 h) vaut « alerte » : le routeur
réserve alors les modèles coûteux ; une mesure absente vaut « inconnu » (prudence), jamais « illimité ».

Statut : implémenté/testé (péremption) ; implémenté/non vérifié sur ton PC (versions, authentification :
le conteneur n'a pas Codex). Les formats de quota viennent des CLI : Claude publie `five_hour`/`seven_day`
dans sa barre d'état ; Codex publie `window_minutes` et `resets_at` dans ses sessions (déjà exploités).
Jarvis **ne lit ni ne copie aucun jeton** et ne contourne aucune limite : quand un fournisseur est épuisé,
ses agents reçoivent l'ordre de committer et de s'arrêter, le secours (autre fournisseur, validé dans le
plan) prend le relais, ou la pause `quota` se pose.

Abonnement ≠ inférence vendue : les SaaS produits par l'usine n'utilisent pas ces abonnements. Toute
inférence pour des clients passe par une API payante, désactivée tant qu'aucune enveloppe `services` ou
`infrastructure` ne la couvre (`jarvis budget`).

## ChatGPT Dots — ce qui est officiellement disponible (vérifié le 14 octobre 2026)

Sources consultées : page d'aide OpenAI « Getting started with your dot », FAQ « Dots privacy, security, and
safety », article « Developer mode and MCP apps in ChatGPT », et deux synthèses tierces (DataCamp, Flavio
Copes) qui renvoient à `openai.com/index/introducing-dots/`, `learn.chatgpt.com/docs/dots` et au
système card GPT-6 Astra. Rien ci-dessous n'est inventé ; ce qui n'est pas documenté est dit tel quel.

| Point | Constat | Conséquence pour Jarvis |
| --- | --- | --- |
| API Dots | **Aucune API publique annoncée.** Les dots s'utilisent via ChatGPT, Slack, Teams | Jarvis n'appelle pas un dot ; le dot vient à Jarvis par une application autorisée |
| Plans | Pro (hors EEE/Suisse/UK), Business Premium ; Enterprise/Edu en bêta sur activation admin ; pas Free/Go/Plus | À vérifier sur **ton** espace : sans dot actif, tout ceci reste une conception |
| Applications | Le dot réutilise les plugins/apps **que tu as déjà connectés** à ChatGPT (ex. GitHub, Gmail, Drive, Slack), avec leurs permissions ; « Custom rules don't grant app or computer access » | La **file partagée** passe par une app que tu autorises : GitHub (issues) est le candidat naturel, déjà utilisé par Jarvis via `gh` |
| Règles et Auto-review | Quatre comportements par action ; Auto-review non désactivable ; les actions sensibles exigent ta reprise en main | Rien dans Jarvis ne cherche à contourner ces confirmations |
| Recherche proactive | lit les sources connectées et prend des notes ; **ne peut pas** envoyer de messages, modifier du contenu via plugins ni piloter un ordinateur | Cohérent avec « le dot propose, Jarvis décide » |
| Accès local | optionnel, **désactivé par défaut** ; nécessite l'app ChatGPT ouverte sur le PC | **Gardé désactivé** dans le premier prototype, comme demandé |
| Codex | le dot peut créer des tâches Codex cloud **si l'environnement existe déjà** dans Codex | Chaque tâche cloud doit être inscrite dans la file (`jarvis proposition confier W-… codex-cloud <id>`) pour éviter le doublon avec un agent local |
| MCP personnalisé | « Developer mode » : serveurs MCP **distants** (tunnel sécurisé pour une machine privée) ; **Pro : lecture/fetch seulement** ; écriture (« full MCP ») en bêta Business/Enterprise/Edu ; l'article ne dit pas si un dot peut utiliser une app personnalisée (« Agent mode cannot use custom apps ») | Un connecteur MCP Jarvis **écrivant** depuis un dot n'est pas démontré possible aujourd'hui : conçu, non réalisable sans vérification sur ton espace |
| Mémoire | le dot garde ses propres notes, non éditables individuellement | Ne pas lui confier de secrets ni de données clients sensibles |

### Premier prototype retenu : file partagée via GitHub (sans API Dots)

1. Tu crées (ou désignes) un dépôt GitHub privé, par exemple `brydel/jarvis-propositions`, et tu
   l'autorises dans l'app GitHub de ChatGPT (permissions issues seulement).
2. Ton dot reçoit la consigne de la **revue quotidienne autorisée d'un seul produit** : lire les sources
   que tu lui as connectées (retours clients, analytics…) et ouvrir **une** issue étiquetée
   `jarvis-proposition` contenant un bilan et **au plus trois** propositions, avec en tête
   `type: bilan|opportunite|retours_clients|brief_produit|marketing` et `projet: <nom>`.
3. Sur ton PC : `jarvis regler propositions.github_depot brydel/jarvis-propositions`, puis le chef (ou toi)
   lance `jarvis proposition importer` ; chaque issue devient un travail `W-xxxxx` (déduplication par
   empreinte et par URL d'issue, contenu borné, traité comme donnée).
4. Le chef accepte au plus trois propositions par source et par jour (`jarvis proposition accepter`),
   les planifie comme toute tâche (plan → admission), confie à **un** exécutant, et clôt avec une preuve
   vérifiée par un autre (`jarvis proposition terminer`).
5. Rien n'est dépensé, publié ni lancé automatiquement par une proposition : la politique l'interdit et
   les tests le vérifient. Jarvis fonctionne sans le dot : la file est juste vide.

Statut : côté Jarvis **implémenté/testé** (`travaux.py`, import GitHub simulé) ; **non vérifié sur ton
PC** (`gh issue list` réel) ; côté dot **nécessite ton action** (plan éligible, app GitHub autorisée,
consigne du dot). Import automatique périodique par le démon : conçu (volontairement manuel d'abord).

### Connecteur MCP Jarvis minimal (conçu)

Trois outils en lecture : `etat_lire` (sortie de `jarvis etat --json` expurgée), `bilans_lire` (bilan
quotidien, `jarvis bilan --json`), `propositions_lire` ; un outil en écriture : `proposition_soumettre`
(équivalent de `jarvis proposition soumettre`, même déduplication, même plafond). Serveur HTTPS distant
ou tunnel, authentification OAuth, **lecture seule tant que ton plan n'offre pas l'écriture MCP** ; dans ce
cas la soumission continue par GitHub. Avant de coder : vérifier sur ton espace qu'un dot peut utiliser une
app en mode développeur. Jamais d'outil qui approuve, délègue, lève une pause ou dépense.

## Codex cloud (évaluation)

Constats (aide OpenAI « Using Codex cloud » et synthèse Flavio Copes) : environnements créés et publiés
depuis ChatGPT web/desktop (dépôts GitHub, script d'installation, internet désactivé par défaut) ; tâches
lancées depuis web, desktop, mobile, et un sous-commande CLI **expérimentale** `codex cloud exec --env ID
"<prompt>"` avec `codex cloud list|status|diff|apply` ; **la consommation est prise sur la même
allocation que Codex local**, une tâche cloud pouvant coûter plus qu'un message local ; VM 4 vCPU/16 Go
pour Pro ; pas de navigateur dans la VM ; résultats par PR ou diff.

Décision : utilisable pour des tâches **compatibles** (code en branche, tests sans service local, revue),
comptabilisées dans la file (`executant = codex-cloud`) et dans le registre quand une PR revient.
**Aucun gain de ressources locales n'est annoncé** avant mesure : un `jarvis diagnostic` avant/après une
journée avec N tâches cloud dira ce que le portable a économisé. Lancement cloud automatique par le chef :
non activé (le CLI est expérimental et non vérifié ici ; un lancement reste un départ soumis à l'admission
pour la place « réservée » au suivi, et à la politique pour les jetons). Statut : conçu, procédure manuelle.
