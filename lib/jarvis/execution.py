"""Backends d'exécution : où tourne un agent. L'agent, lui, ne sait pas sur quel backend il est.

Interface commune (`ExecBackend`) : `lancer`, `statut`, `capturer`, `fermer`.

- `WorkmuxBackend` (défaut) : le fonctionnement historique — worktree git + fenêtre tmux, via workmux, sur ce PC.
  Aucune différence de comportement avec les versions précédentes.
- `E2BBackend` (facultatif, désactivé) : bac à sable distant E2B, choisi par projet (`execution = "e2b"` dans
  projects.toml). C'est un **service payant** : refusé tant qu'une enveloppe de budget « infrastructure » ne
  couvre pas le projet, que le SDK (`pip install e2b-code-interpreter`) et la clé E2B_API_KEY manquent. Les
  identifiants de tes abonnements Claude/Codex ne sont jamais copiés dans le bac à sable : un agent distant
  s'authentifie avec une clé d'API dédiée, fournie par les secrets du rôle (et facturée à l'API).
  Statut : interface et garde-fous implémentés et testés avec un double ; appels réels au SDK non vérifiés.
"""

from __future__ import annotations

import os
import subprocess
from typing import Protocol

from . import agents as ag
from . import config


class NonDisponible(RuntimeError):
    """Backend indisponible ou refusé, avec la raison à afficher."""


class ExecBackend(Protocol):
    nom: str

    def lancer(self, *, projet: str, chemin: str, branche: str, profil: str, prompt: str) -> dict: ...

    def statut(self) -> tuple[list[dict] | None, str]: ...

    def capturer(self, cible: str, lignes: int = 60) -> str: ...

    def fermer(self, agent: dict) -> tuple[bool, str]: ...


class WorkmuxBackend:
    """Worktree + fenêtre tmux via workmux, sur ce poste (comportement historique)."""

    nom = "workmux"

    def lancer(self, *, projet: str, chemin: str, branche: str, profil: str, prompt: str) -> dict:
        res = subprocess.run(["workmux", "add", branche, "-a", profil, "-b", "-P", prompt], cwd=chemin)
        if res.returncode != 0:
            raise NonDisponible("workmux add a échoué")
        return {"backend": self.nom, "cible": f"{projet}:{branche}"}

    def statut(self):
        return ag.status_all()

    def capturer(self, cible: str, lignes: int = 60) -> str:
        return ag.capture(cible, lignes)

    def fermer(self, agent: dict):
        return ag.close(agent)


class E2BBackend:
    """Bac à sable distant E2B (facultatif). `sdk` : module e2b_code_interpreter, ou un double pour les tests."""

    nom = "e2b"
    # Dépense estimée engagée à chaque lancement (dollars) : un bac à sable pour une tâche de quelques heures.
    # Réglable par projet (`e2b_cout_estime` dans projects.toml). Comparée au réel quand la facture arrive.
    COUT_ESTIME = 1.0

    def __init__(self, sdk=None):
        self._sdk = sdk

    def _charger_sdk(self):
        if self._sdk is not None:
            return self._sdk
        try:
            import e2b_code_interpreter as sdk  # noqa: PLC0415 — dépendance facultative, jamais requise
        except ImportError:
            return None
        return sdk

    def _cout(self, projet: str) -> float:
        try:
            return float((config.projects().get(projet) or {}).get("e2b_cout_estime") or self.COUT_ESTIME)
        except (TypeError, ValueError):
            return self.COUT_ESTIME

    def _verifier(self, projet: str):
        raisons = []
        sdk = self._charger_sdk()
        if sdk is None:
            raisons.append("SDK absent (pip install e2b-code-interpreter)")
        if not os.environ.get("E2B_API_KEY"):
            raisons.append("clé E2B_API_KEY absente (à fournir par les secrets du rôle)")
        from . import budgets
        ok, pourquoi = budgets.verifier("infrastructure", self._cout(projet), projet=projet)
        if not ok:
            raisons.append(f"aucun budget « infrastructure » pour {projet} ({pourquoi})")
        if raisons:
            raise NonDisponible("exécution E2B refusée : " + " ; ".join(raisons))
        return sdk

    def lancer(self, *, projet: str, chemin: str, branche: str, profil: str, prompt: str) -> dict:
        sdk = self._verifier(projet)
        with open(prompt, encoding="utf-8") as fh:
            consigne = fh.read()
        from . import budgets, store
        # La dépense est comptée AVANT la création : l'enveloppe baisse, et finit par refuser.
        budgets.engager("infrastructure", self._cout(projet), projet=projet, libelle=f"bac à sable E2B {branche}",
                        par="jarvis", estime=True)
        sandbox = sdk.Sandbox.create(metadata={"jarvis_projet": projet, "jarvis_branche": branche})
        ident = getattr(sandbox, "sandbox_id", "") or getattr(sandbox, "id", "")
        try:
            sandbox.files.write("/home/user/jarvis-prompt.md", consigne)
            commande = "claude -p \"$(cat /home/user/jarvis-prompt.md)\"" if profil == "cc" else \
                "codex exec \"$(cat /home/user/jarvis-prompt.md)\""
            sandbox.commands.run(commande, background=True)
        except Exception as exc:  # noqa: BLE001 — un bac à sable créé ne doit jamais continuer de coûter seul
            try:
                sdk.Sandbox.kill(ident)
            except Exception:  # noqa: BLE001
                store.feed_add("erreur", f"E2B : bac à sable {ident} peut-être encore actif, à arrêter à la main")
            raise NonDisponible(f"lancement E2B échoué, bac à sable arrêté : {exc}") from exc
        store.feed_add("task", f"{projet} {branche} lancé dans E2B ({ident})")
        return {"backend": self.nom, "cible": ident}

    def statut(self):
        return [], ""  # suivi des bacs à sable distants : à brancher avec le premier usage réel

    def capturer(self, cible: str, lignes: int = 60) -> str:
        return "(aperçu indisponible pour un agent E2B dans cette version)"

    def fermer(self, agent: dict):
        # Arrêter n'exige ni budget ni clé de plus : on doit toujours pouvoir stopper ce qui coûte.
        sdk = self._charger_sdk()
        if sdk is None:
            return False, "SDK E2B absent : arrête le bac à sable depuis la console E2B"
        sdk.Sandbox.kill(agent.get("worktree", ""))
        return True, "bac à sable arrêté"


BACKENDS = {"workmux": WorkmuxBackend, "e2b": E2BBackend}


def pour_projet(projet: str) -> ExecBackend:
    nom = str((config.projects().get(projet) or {}).get("execution") or "workmux")
    if nom not in BACKENDS:
        raise NonDisponible(f"backend d'exécution inconnu « {nom} » pour {projet} (valeurs : {', '.join(BACKENDS)})")
    return BACKENDS[nom]()
