# Matrice de compatibilité des fournisseurs

Code : `lib/jarvis/adaptateurs.py` (interface `Adaptateur` : `disponible()`, `executer(enveloppe)`). Le moteur de
missions ne connaît aucun format propre à un fournisseur. Vérifié sur l'ASUS (WSL2 Ubuntu) le 21 octobre 2026.

| Capacité | Claude Code (`claude -p`) | Codex (`codex exec`) | Factice |
| --- | --- | --- | --- |
| Version observée | 2.1.307 (`~/.local/bin/claude`) | 0.162.1 (`~/.npm-global/bin/codex`, connexion ChatGPT) | — |
| Binaire Windows (`/mnt/…`) ignoré | VERIFIED (`binaire_linux`) | VERIFIED (`binaire_linux`) | sans objet |
| Analyse de document sans outils | **VERIFIED en réel** (`--tools ""`, dossier vide, sans MCP ni hooks) | **VERIFIED en réel** le 21/10/2026, 18,7 s (`--sandbox read-only`, `--ignore-user-config`, `--disable hooks`, `--ephemeral`, dossier vide) | VERIFIED |
| Aucun effet de bord | sessions non enregistrées | VERIFIED : 0 session Codex ajoutée, 0 agent workmux créé (le hook `SessionStart` de l'utilisateur ferait `workmux register-agent`) | sans objet |
| Clés payantes retirées en mode abonnement | VERIFIED (faux CLI) | VERIFIED (faux CLI) | sans objet |
| Quota / indisponibilité normalisés | VERIFIED (faux CLI : « usage limit » → `fournisseur_indisponible`) | IMPLEMENTED (même règle), non provoqué en réel | VERIFIED |
| Annulation | par fin du bail (le sous-processus va au bout de son délai) | idem | idem |
| Reprise de session | non utilisée (CURRENT : `workmux open --continue` pour les agents de code) | non utilisée | non |
| Flux d'événements en direct | non utilisé en M1 (`stream-json` possible) | app-server (M4) | non |
| Outils (édition de code) | via workmux + `bin/jarvis-claude` (CURRENT), pas via missions | via `bin/jarvis-codex` (CURRENT) | non |

Leçon de la vérification réelle : avec `--permission-mode plan` et aucun outil, Claude imitait un appel d'écriture
de plan (balises `<invoke>`). Option retirée, et la revue déterministe refuse désormais tout texte qui imite un
appel d'outil (test `test_revue_refuse_une_forme_invalide_puis_nouvel_essai`).

Vérifier soi-même : `python3 outils/verifier_mission_reelle.py` (Claude) ou `--fournisseur codex`.
