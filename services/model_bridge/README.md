# Passerelle de modele local (facultative)

**Preparee, desactivee et non branchee au routeur.** Claude Code et Codex restent les seuls fournisseurs par defaut. Ce service ne telecharge rien, ne lance aucun modele et ne consomme aucune API commerciale.

## Contrat

`GET /health` expose la configuration, pas la disponibilite du modele : `upstream_verified: false`.

`POST /v1/generate` recoit `{"prompt":"...", "max_tokens":512}` avec un jeton Bearer prive. Il transmet une seule requete non-streaming a `http://127.0.0.1:<JARVIS_MODEL_PORT>/v1/chat/completions`. Le modele est impose par l'administrateur, pas par le client. La reponse est `{text, model, provider, tool_calls_executed:false}`.

Destination fixe loopback, aucun proxy d'environnement, aucune redirection, aucun appel d'outil, un seul traitement simultane. Entrees et sorties bornees ; delai amont limite. L'inference echouee n'est jamais rejouee automatiquement. Les prompts et jetons ne sont pas journalises.

## Lancement sans activation

```bash
python3 services/model_bridge/server.py
```

Les demandes d'inference recoivent 503. Le service ecoute uniquement sur 127.0.0.1:7731.

## Activation future, volontaire

Un administrateur doit d'abord choisir un modele, verifier la licence des poids et du moteur, ses besoins materiels, puis configurer un serveur local compatible. Aucun modele specifique n'est fourni ni presume installe.

Variables requises : `JARVIS_MODEL_ENABLED=1`, `JARVIS_MODEL_BRIDGE_TOKEN` (secret aleatoire d'au moins 32 caracteres), `JARVIS_MODEL_ID` (identifiant exact). Options : `JARVIS_MODEL_PORT` (11434 par defaut), `JARVIS_MODEL_UPSTREAM_TOKEN`. Ne pas versionner les secrets ni les transmettre au navigateur.

Pour devenir un fournisseur Jarvis, il reste a developper l'adaptateur du runner, son consentement explicite, ses tests d'evaluation et ses politiques de budget/permissions. Cette livraison ne pretend pas que cette integration est deja faite.

## Limites

Service personnel local, pas un endpoint SaaS multi-tenant. Ne pas l'exposer avec un tunnel public. Pour des runners distants : identites distinctes, TLS, isolation par organisation et autorisation du plan de controle seront necessaires. La sortie du modele reste une donnee non fiable ; ne jamais l'executer comme du code.

## Verification sans modele

```bash
python3 -m unittest discover -s services/model_bridge/tests -v
```

Les tests utilisent un serveur factice local, pas un fournisseur IA.
