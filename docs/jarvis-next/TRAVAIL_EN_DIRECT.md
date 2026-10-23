# Travail en direct sur le Board

Base examinée : `feat/jarvis-board-v2`, commit `81a875a`. Le code de cette branche est plus récent que `main`.

## Défauts corrigés

- Telegram `/etat` réunissait les sessions workmux et les missions du moteur. Le Board ne rendait des agents
  que dans les cartes liées à une mission : une session de code indépendante était invisible.
- Deux fenêtres du même nom, dans des sessions tmux différentes, pouvaient se masquer. Le rapprochement et
  la détection du fournisseur distinguent maintenant la session et la fenêtre.
- Le repli de `jarvis voir projet:worktree` pouvait capturer le projet homonyme. Il filtre maintenant le projet,
  cible l'identifiant tmux et refuse une cible ambiguë.
- Un flux constant d'événements pouvait repousser sans fin le rafraîchissement par debounce. Le délai est
  maintenant borné. Une relecture périodique couvre les coupures du SSE et les changements non notifiés.
- Une réponse de chargement ancienne pouvait écraser une réponse plus récente. Seule la dernière demande
  peut mettre à jour le Board et ses approbations.
- La carte d'équipe pouvait privilégier quatre anciennes tentatives terminées et cacher un agent actif.
  Les tentatives actives passent en premier ; les entrées supplémentaires sont signalées.
- Un échec de `tmux send-keys` pouvait être traité comme un message remis au chef. Les codes de retour
  sont vérifiés et un échec reste en file. Ce mécanisme n'est pas une garantie de remise exactement une fois.

## Lecture et limites

Le panneau « Travail en direct » observe les sessions locales et les tâches non terminales du moteur.
Il comprend les missions attachées à une note, les attentes de validation, de fournisseur et de nouvel essai.
Le Board d'accueil observe tous les projets ; les autres Boards filtrent leur espace. Les sessions du poste
ne sont jamais offertes à un autre tenant. L'API utilise la session authentifiée du Studio, ne retourne aucun
secret d'exécutant ni jeton de bail et ne permet ni lancement ni commande terminal arbitraire.

L'aperçu est une capture de sortie du terminal sélectionné, bornée à 16 000 caractères et relue toutes les
cinq secondes après la réponse précédente. Une erreur est affichée, pas transformée en équipe vide.
Les missions exécutées sans terminal montrent l'état durable du moteur et l'expiration du bail, pas des
tokens de modèle inventés. Un bail valide n'est pas la preuve d'un progrès sémantique. Pour ces missions,
le contenu et les outils déclarés restent disponibles à la remise du résultat.

## Vérification et utilisation

```bash
python3 -m unittest discover -s tests
cd studio/board-v2
npm ci
npm run build
npx playwright test activite.spec.ts product.spec.ts
```

Chromium système est utilisable avec `JARVIS_TEST_BROWSER_EXECUTABLE=/chemin/vers/chromium` ; sans cette
variable, Playwright utilise son navigateur habituel. Les parcours couvrent les sessions sans carte, la
capture, les changements d'état sans événement de mission, l'affichage mobile et l'arrivée d'une carte
après coupure du SSE. Les tests serveur couvrent les projets homonymes, les tenants, l'authentification,
les baux expirés et les messages conservés après échec tmux.

Validation dans l'environnement cloud : 383 tests Python exécutés, 282 réussis et 101 ignorés ; neuf
parcours Chromium réussis (activité et navigation produit), puis trois parcours activité revérifiés après
ajustement mobile. TypeScript, build de production, syntaxe Bash et aide CLI passent. ShellCheck retourne
1 sur les avertissements préexistants des scripts shell, qui n'ont pas été modifiés.

Après installation du code et du build sur le poste utilisateur, redémarrer le serveur Studio qui sert
`jarvis mission studio`, puis recharger le Board réel. Les changements du module de surveillance nécessitent
aussi de redémarrer le démon de ce poste. La validation locale ne modifie pas un Jarvis déjà lancé ailleurs.

Cette correction porte sur l'observabilité et la synchronisation. Elle ne prétend pas valider toutes les
décisions autonomes, la qualité des réponses de Claude/Codex ou les connexions réelles Telegram/Linear.
