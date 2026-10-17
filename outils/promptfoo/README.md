# promptfoo (facultatif, non installé par Jarvis)

`promptfooconfig.yaml` est généré par `jarvis eval promptfoo` (JSON, donc YAML valide). Chaque cas de
`tests/goldens/` devient un test dont le fournisseur est `jarvis eval lancer` : un **vrai agent** travaille sur une
copie du cas et la vérification cachée (script, pas de LLM) le juge.

```bash
./bin/jarvis eval promptfoo > outils/promptfoo/promptfooconfig.yaml   # régénérer après ajout d'un cas
npx promptfoo@latest eval -c outils/promptfoo/promptfooconfig.yaml    # consomme ton quota : 15 agents
```

Statut : configuration fournie, **non exécutée** dans le dépôt (chaque exécution consomme le quota de ton
abonnement). Le contrôle gratuit et déterministe des cas est `jarvis eval verifier` (lancé aussi par les tests).
