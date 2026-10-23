"""Annulation locale d'une tentative et sous-processus possédés par cette tentative.

Le jeton reste en mémoire : il ne vient jamais d'un document ou du modèle. Une expiration de bail est
convertie en échéance monotone, renouvelable uniquement tant que l'annulation n'a pas eu lieu.
"""

from __future__ import annotations

import math
import os
import signal
import subprocess
import threading
import time
from typing import Callable

POLL_S = 0.1
GRACE_S = 1.0


class ExecutionAnnulee(RuntimeError):
    """La tentative n'a plus l'autorité nécessaire pour continuer son travail."""


class ControleExecution:
    def __init__(self, *, expire: float | None = None, interruption: Callable[[], str] | None = None):
        self._verrou = threading.RLock()
        self._signal = threading.Event()
        self._raison = ""
        self._echeance: float | None = None
        self._interruption = interruption
        if expire is not None:
            self.renouveler(expire)

    def renouveler(self, expire: float) -> None:
        if isinstance(expire, bool) or not isinstance(expire, (int, float)) or not math.isfinite(expire):
            raise ValueError("expiration de bail invalide")
        with self._verrou:
            self._actualiser()
            if not self._signal.is_set():
                self._echeance = time.monotonic() + max(0, expire - time.time())

    def _actualiser(self) -> None:
        if self._signal.is_set():
            return
        if self._echeance is not None and time.monotonic() >= self._echeance:
            self.annuler("bail expiré localement sans renouvellement")
        elif self._interruption:
            raison = self._interruption()
            if raison:
                self.annuler(raison)

    def annuler(self, raison: str = "exécution annulée") -> None:
        with self._verrou:
            if not self._signal.is_set():
                self._raison = raison
                self._signal.set()

    @property
    def raison(self) -> str:
        with self._verrou:
            self._actualiser()
            return self._raison

    def verifier(self) -> None:
        with self._verrou:
            self._actualiser()
            if self._signal.is_set():
                raise ExecutionAnnulee(self._raison)

    def demarrer(self, fonction: Callable):
        """Le contrôle et la création du processus sont indivisibles par rapport à annuler()."""
        with self._verrou:
            self.verifier()
            return fonction()


def controle(env: dict) -> ControleExecution | None:
    valeur = env.get("_annulation")
    return valeur if isinstance(valeur, ControleExecution) else None


def verifier(env: dict) -> None:
    jeton = controle(env)
    if jeton is not None:
        jeton.verifier()


def _signaler(proc: subprocess.Popen, sig: signal.Signals) -> None:
    try:
        if os.name == "posix":
            os.killpg(proc.pid, sig)
        elif proc.poll() is None:
            proc.terminate() if sig == signal.SIGTERM else proc.kill()
    except ProcessLookupError:
        pass


def _arreter(proc: subprocess.Popen) -> None:
    # Même si le parent est sorti, ses descendants peuvent encore tenir les pipes ou continuer un outil.
    _signaler(proc, signal.SIGTERM)
    try:
        proc.communicate(timeout=GRACE_S)
    except subprocess.TimeoutExpired:
        pass
    finally:
        _signaler(proc, signal.SIGKILL)
    try:
        proc.communicate(timeout=GRACE_S)
    except subprocess.TimeoutExpired:
        # Un descendant qui a volontairement changé de session sort du contrat de groupe POSIX.
        # Aucun communicate() illimité : le runner doit pouvoir rendre la main.
        for pipe in (proc.stdout, proc.stderr):
            if pipe:
                pipe.close()
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=GRACE_S)


def executer_processus(cmd: list[str], *, timeout: float, annulation: ControleExecution | None = None,
                       cwd=None, env=None) -> subprocess.CompletedProcess:
    """Processus isolé, stdin fermé, sortie capturée ; TERM puis KILL du groupe à l'arrêt.

    Le jeton est vérifié au plus toutes les 100 ms. Après détection, les descendants du groupe sont arrêtés
    sous deux secondes. Un appelant externe doit transmettre le même jeton à chacun de ses outils.
    """
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("délai d'exécution invalide")
    debut = time.monotonic()

    def lancer():
        return subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, start_new_session=os.name == "posix")

    proc = annulation.demarrer(lancer) if annulation else lancer()
    termine = False
    try:
        while True:
            if annulation:
                annulation.verifier()
            restant = timeout - (time.monotonic() - debut)
            if restant <= 0:
                raise subprocess.TimeoutExpired(cmd, timeout)
            try:
                stdout, stderr = proc.communicate(timeout=min(POLL_S, restant))
            except subprocess.TimeoutExpired:
                continue
            if annulation:
                annulation.verifier()
            termine = True
            return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
    finally:
        # Le CLI terminé ne conserve pas de processus d'outil en arrière-plan.
        if not termine or os.name == "posix":
            _arreter(proc)
