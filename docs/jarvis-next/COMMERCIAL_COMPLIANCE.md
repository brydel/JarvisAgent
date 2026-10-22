# Conformité commerciale des fournisseurs

Sources officielles consultées le **21 octobre 2026**. Ce document ne vaut pas avis juridique ; aucune conformité
à un cadre légal (Loi 25 du Québec, LPRPDE, RGPD…) n'est revendiquée sans évaluation réelle.

## Claude (Anthropic)

Source : `https://code.claude.com/docs/en/agent-sdk/overview` (redirigée depuis docs.claude.com).

- L'Agent SDK exécute le binaire Claude Code ; en Python et TypeScript ; sinon `claude -p --output-format json`.
- Citation : « Unless previously approved, Anthropic does not allow third party developers to offer claude.ai
  login or rate limits for their products » — les produits tiers doivent utiliser l'authentification par **clé
  d'API**.
- L'usage du SDK pour des produits offerts à ses clients relève des **Commercial Terms of Service** d'Anthropic.
- Marque : « Claude Agent » ou « {Nom} Powered by Claude » autorisés ; « Claude Code » / « Claude Code Agent » et
  tout visuel imitant Claude Code **interdits** ; le produit garde sa propre marque.

## Codex (OpenAI)

Sources : `https://learn.chatgpt.com/docs/codex-sdk` (redirigée depuis developers.openai.com/codex/sdk) et les
pages d'authentification Codex (`developers.openai.com/codex/auth`, `…/auth/ci-cd-auth`) via recherche.

- SDK TypeScript (`@openai/codex-sdk`, Node ≥ 18) et Python (`openai-codex`, ≥ 3.10, stable, pilote l'app-server
  en JSON-RPC) ; l'app-server est recommandé pour les clients personnalisés (auth, historique, approbations,
  flux). `codex mcp-server` a été retiré.
- Deux modes : connexion ChatGPT (accès par l'abonnement) ou clé d'API (facturée au tarif API). La documentation
  recommande la **clé d'API pour l'automatisation et la CI** ; réutiliser un fichier d'authentification ChatGPT
  sur un exécutant est un cas avancé « seulement pour exécuter en tant que ton compte », fichier à traiter comme un
  mot de passe. Des jetons d'accès existent pour les espaces ChatGPT Enterprise.
- La page SDK ne dit **rien** de l'usage d'un abonnement ChatGPT dans un produit tiers commercial : non vérifié,
  donc traité comme **non autorisé**.

## Règles appliquées par le code (VERIFIED dans `missions.ELIGIBILITE` et les tests)

| Profil | Abonnement (Claude / ChatGPT) | Clé d'API | Factice |
| --- | --- | --- | --- |
| `PERSONAL_LOCAL` — ta machine, tes sessions | **oui** (ton CLI officiel, ta session, ta machine) | oui si budget > 0 | oui |
| `CUSTOMER_OWNED_RUNNER` — machine du client | oui **uniquement** avec la session du client sur sa machine, jamais la tienne | oui si budget du client > 0 | oui |
| `COMMERCIAL_HOSTED` — exécution hébergée par Jarvis | **non** (refusé par le routeur, test `test_abonnement_refuse_en_hebergement_commercial`) | oui si budget > 0 et conditions commerciales acceptées | oui |

Et toujours :
- Jarvis ne lit, ne copie, ne relaie aucun jeton de session ; aucun relais OAuth ; une connexion ne stocke **aucun
  identifiant** (seulement fournisseur, mode, payant ou non).
- En mode abonnement, les variables `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `OPENAI_API_KEY`, `CODEX_API_KEY`
  sont retirées de l'environnement du CLI : pas de bascule silencieuse vers l'API payante (test
  `test_claude_sans_outils_sans_cle_payante`).
- Aucune rotation de comptes ou d'identités pour contourner une limite.

## Permissions non résolues pour un usage commercial (BLOCKED)

1. Offre hébergée avec Claude : contrat API Anthropic et acceptation des Commercial Terms par le fondateur.
2. Offre hébergée avec Codex : clé d'API OpenAI et conditions applicables ; usage d'abonnements ChatGPT dans un
   produit tiers à confirmer **par écrit** auprès d'OpenAI avant toute conception qui en dépend.
3. Nom commercial et marque conformes aux règles de marque d'Anthropic.
4. Évaluation de confidentialité et de résidence des données (Canada) avant tout client réel.
