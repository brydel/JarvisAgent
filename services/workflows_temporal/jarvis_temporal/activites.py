"""Une activité bornée appelle la passerelle, propriétaire des droits et effets."""

from __future__ import annotations

import asyncio

from temporalio import activity
from temporalio.exceptions import ApplicationError

from .controleur import Controleur, ErreurControleur


class Activites:
    def __init__(self, controleur: Controleur):
        self.controleur = controleur

    @activity.defn(name="jarvis.appeler_passerelle.v1")
    def executer(self, demande: dict) -> dict:
        def verifier():
            if activity.is_cancelled():
                raise asyncio.CancelledError()
        verifier()
        activity.heartbeat({"operation_id": demande["operation_id"], "etat": "avant_appel"})
        try:
            resultat = self.controleur.executer(demande, verifier_annulation=verifier)
        except ErreurControleur as exc:
            raise ApplicationError(str(exc), type="ControleurRefuse" if exc.definitive else "ControleurIndisponible",
                                   non_retryable=exc.definitive) from None
        verifier()
        statut = resultat.get("status")
        if statut == "succeeded":
            return resultat
        if statut in {"prepared", "in_progress"}:
            raise ApplicationError("Opération de passerelle en cours ; interrogation avec la même identité.",
                                   type="OperationEnCours")
        if statut == "unknown":
            raise ApplicationError("Résultat externe incertain ; rapprochement requis avant poursuite.",
                                   type="EffetIncertain", non_retryable=True)
        raise ApplicationError("La passerelle a refusé ou échoué l'opération.", type="OperationRefusee", non_retryable=True)
