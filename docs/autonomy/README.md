# Autonomie de JarvisAgent — synthèse, état des lots et index

Mission : faire évoluer JarvisAgent vers une usine à SaaS autonome, par lots utiles, sur le portable actuel
d'abord. Cette documentation regroupe ce qui a été **réellement livré**, ce qui est **conçu**, et ce qui
**manque**. Chaque fonction porte un statut honnête :

- **implémenté/testé** — code dans la branche, tests déterministes verts ;
- **implémenté/non vérifié sur ton PC** — code et tests dans un conteneur Linux (2 cœurs, 8 Go, sans WSL,
  sans workmux ni Codex) : le comportement sur l'ASUS reste à constater ;
- **conçu** — décrit ici, pas codé ;
- **bloqué** / **nécessite une autorisation** — hors de portée de cette session, et pourquoi.

> Important : l'agent qui a produit ce lot **n'a pas exécuté ses outils sur ton PC**. Toutes les mesures
> matérielles citées viennent d'un conteneur distant et ne valent pas pour ton ASUS. `jarvis diagnostic`
> est là pour mesurer chez toi.

## Synthèse de l'existant (avant ce lot, branche `claude/usine-roles-modeles-studio`, b8296b7)

Effectif : chef d'orchestre (Claude Code) qui propose des plans validés par l'humain (Telegram, cockpit,
terminal) ; agents Claude/Codex lancés par workmux dans des worktrees ; démon de surveillance (événements,
jetons, prévision, chiens de garde chef/démon/blocage, santé du poste, batterie, reprise après redémarrage) ;
rôles spécialisés et routeur de modèles avec vérification ; registre des tâches et bilan ; studio vidéo et
livrables ; cockpit curses et tableau de bord web en lecture seule ; Telegram bidirectionnel.

Limites constatées à la lecture du code (voir `audit.md`) : une seule pause ambiguë partagée par
l'humain, la batterie et le quota ; capacité vérifiée au lancement par plan mais pas pour un lancement
manuel, ni pour la reprise après redémarrage ; aucune réservation entre deux lancements simultanés ;
un agent muet depuis vingt minutes devenait « terminé » ; pas de notion d'opération lourde ; pas de
politique de délégation, de budget monétaire, ni de journal d'audit ; quota périmé traité comme valide.

## État des lots

| Lot | Contenu | Statut |
| --- | --- | --- |
| 0 | État réel du dépôt, baseline de tests (84 → 108 verts), diagnostic du poste, profils, audit priorisé | implémenté/testé (diagnostic : implémenté/non vérifié sur ton PC) |
| 1 | Admission commune, réservations expirables, concurrence prudente (agents + opérations lourdes), pauses à causes indépendantes, reprise via admission, agents silencieux, visibilité cockpit/web/Telegram, tests §16 | implémenté/testé ; plafonnement système des processus : **bloqué** (voir `securite.md`) |
| 2 | Politique de délégation versionnée, file d'exceptions, budgets (non renseigné = 0), journal d'audit à empreintes, adaptateurs fournisseurs avec fraîcheur des quotas, file de travaux partagée (dot/GitHub), états de tâches | fondations implémentées/testées ; états avancés d'échec (classification, reprise bornée par tâche) : conçu |
| 3 | Parcours commercial complet d'un produit, en simulation | conçu (`feuille-de-route.md`) |
| 4 | Exploitation, amélioration mesurée des agents, migration vers la station | conçu (`feuille-de-route.md`, `exploitation.md`) |

## Index

- `audit.md` — audit priorisé des pistes du mandat, chacune vérifiée dans le code, avec statut.
- `architecture.md` — la cible (stratégie, orchestration, exécution, contrôle, évaluation) et son implémentation légère.
- `admission-et-pauses.md` — point d'admission, réservations, opérations lourdes, pauses, états d'agents.
- `politique-budgets-audit.md` — politique de délégation, délégations, exceptions, budgets, journal.
- `securite.md` — ce que l'isolation sous un même utilisateur garantit, et ce qu'elle ne garantit pas.
- `fournisseurs-et-dots.md` — adaptateurs Claude/Codex, quotas, ChatGPT Dots (sources officielles), Codex cloud.
- `exploitation.md` — installation, diagnostic, profils, **relance propre**, retour arrière, migration.
- `tests.md` — ce que couvrent les tests, unitaires / intégration simulée / vérifications réelles.
- `feuille-de-route.md` — lots 3 et 4, prochaines actions.
- `vague-1.md` — plafonds de jetons, coûts (équivalent API), mémoire du chef, bilan quotidien, échecs bornés, secrets par rôle.
- `vague-2.md` — harnais d'évaluation (goldens), backend d'exécution, replay, proxy LiteLLM des produits, traces OpenTelemetry, rollback assisté.
- `vague-3.md` — registre de skills avec confiance, briefs de rôles auto-améliorés (canari), stockage SQLite facultatif, bail d'orchestrateur, exécutants.
- `handoff.md` — reprise de session en une page.
- `../jarvis-next/README.md` — **Jarvis Next** : architecture hybride (Studio Cloud + exécutants) et jalon M1 (missions durables).
