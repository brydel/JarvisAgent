"""Code déterministe : décisions du DAG dans Temporal, I/O dans les activités."""

from __future__ import annotations

import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError

from .contrat import groupes, operation, valider


@workflow.defn(name="jarvis.projet.prototype.v1")
class ProjetWorkflow:
    def __init__(self):
        self.pause = False
        self.annule = False
        self.etapes = {}
        self.actives = []

    @workflow.signal
    def suspendre(self):
        """La pause empêche les départs suivants, sans prétendre annuler un effet déjà parti."""
        self.pause = True

    @workflow.signal
    def reprendre(self):
        self.pause = False

    @workflow.signal
    def annuler(self):
        self.annule = True
        for appel in self.actives:
            appel.cancel()

    @workflow.query
    def etat(self) -> dict:
        return {"pause": self.pause, "annule": self.annule, "etapes": dict(self.etapes)}

    @workflow.run
    async def run(self, demande: dict) -> dict:
        try:
            spec = valider(demande)
        except ValueError as exc:
            raise ApplicationError(str(exc), type="ProjetInvalide", non_retryable=True) from None
        self.etapes = {s["id"]: "planned" for s in spec["steps"]}
        resultats = {}
        # Trois départs maximum par vague, même si le DAG contient 32 racines indépendantes.
        vagues = [groupe[i:i + 3] for groupe in groupes(spec["steps"]) for i in range(0, len(groupe), 3)]
        for vague in vagues:
            await workflow.wait_condition(lambda: not self.pause or self.annule)
            if self.annule:
                raise ApplicationError("Projet annulé ; les effets déjà partis restent à rapprocher.",
                                       type="ProjetAnnule", non_retryable=True)
            self.actives = []
            for step in vague:
                self.etapes[step["id"]] = "running"
                self.actives.append(workflow.start_activity(
                    "jarvis.appeler_passerelle.v1", operation(spec, step),
                    activity_id=step["id"],
                    start_to_close_timeout=timedelta(seconds=step["timeout_s"]),
                    schedule_to_close_timeout=timedelta(seconds=step["timeout_s"] * 3 + 10),
                    heartbeat_timeout=timedelta(seconds=min(step["timeout_s"], 35)),
                    cancellation_type=workflow.ActivityCancellationType.WAIT_CANCELLATION_COMPLETED,
                    retry_policy=RetryPolicy(initial_interval=timedelta(seconds=1), maximum_interval=timedelta(seconds=5),
                                             maximum_attempts=3),
                ))
            try:
                sorties = await asyncio.gather(*self.actives, return_exceptions=True)
                erreur = False
                for step, sortie in zip(vague, sorties):
                    if isinstance(sortie, BaseException):
                        self.etapes[step["id"]] = "cancelled" if self.annule else "blocked"
                        erreur = True
                    else:
                        self.etapes[step["id"]] = "succeeded"
                        resultats[step["id"]] = sortie
                if erreur or self.annule:
                    raise ApplicationError("Projet bloqué ou annulé ; aucune étape dépendante démarrée.",
                                           type="ProjetAnnule" if self.annule else "EtapeBloquee", non_retryable=True)
            finally:
                for appel in self.actives:
                    if not appel.done():
                        appel.cancel()
                self.actives = []
        return {"status": "succeeded", "project": spec["project"], "steps": resultats}
