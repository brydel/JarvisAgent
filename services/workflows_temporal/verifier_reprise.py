"""Test d'intégration explicite : vrai serveur, changement de worker, retry, signaux et replay.

Les activités sont factices et n'appellent pas de fournisseur. Un refus réseau est un échec de ce test,
jamais une réussite ou un test automatiquement ignoré.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
from pathlib import Path
import sys
import tempfile
import uuid

from temporalio import activity
from temporalio.client import Client, WorkflowFailureError
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer, Worker

from jarvis_temporal.contrat import operation, workflow_id
from jarvis_temporal.workflow import ProjetWorkflow


async def verifier(client: Client) -> dict:
    queue = "jarvis-test-" + uuid.uuid4().hex
    spec = json.loads((Path(__file__).parent / "exemples/projet.json").read_text())
    spec["id"] = "reprise-" + uuid.uuid4().hex
    premier_id = operation(spec, spec["steps"][0])["operation_id"]
    second_id = operation(spec, spec["steps"][1])["operation_id"]
    commence = asyncio.Event()
    terminer = asyncio.Event()
    appels = []
    premiers = {premier_id}

    @activity.defn(name="jarvis.appeler_passerelle.v1")
    async def factice(demande: dict) -> dict:
        oid = demande["operation_id"]
        appels.append(oid)
        activity.heartbeat({"operation_id": oid})
        if oid in premiers:
            commence.set()
            await terminer.wait()
        elif oid == second_id and appels.count(oid) == 1:
            raise ApplicationError("Incident transitoire factice avant l'effet.", type="IncidentTest")
        return {"operation_id": oid, "status": "succeeded", "resultat": {"preuve": "factice"}}

    async def attendre_condition(handle, predicat):
        async def poll():
            while True:
                etat = await handle.query(ProjetWorkflow.etat)
                if predicat(etat):
                    return etat
                await asyncio.sleep(0.05)
        return await asyncio.wait_for(poll(), 20)

    async with Worker(client, task_queue=queue, workflows=[ProjetWorkflow], activities=[factice]):
        handle = await client.start_workflow(ProjetWorkflow.run, spec, id=workflow_id(spec), task_queue=queue)
        await asyncio.wait_for(commence.wait(), 20)
        await handle.signal(ProjetWorkflow.suspendre)
        await attendre_condition(handle, lambda e: e["pause"])
        terminer.set()
        await attendre_condition(handle, lambda e: e["etapes"].get("documentation-python") == "succeeded")
        assert appels == [premier_id], "Une étape dépendante est partie malgré la pause."
    # Nouveau worker, même workflow et même historique : l'instance Python précédente a disparu.
    async with Worker(client, task_queue=queue, workflows=[ProjetWorkflow], activities=[factice]):
        await attendre_condition(handle, lambda e: e["pause"] and e["etapes"].get("documentation-python") == "succeeded")
        await handle.signal(ProjetWorkflow.reprendre)
        resultat = await asyncio.wait_for(handle.result(), 30)
        assert resultat["status"] == "succeeded"
        assert appels.count(premier_id) == 1, "Le redémarrage a rejoué la première activité."
        assert appels.count(second_id) == 2, "Le retry attendu n'a pas été observé."
        historique = await handle.fetch_history()
        await Replayer(workflows=[ProjetWorkflow]).replay_workflow(historique)

        annulation = copy.deepcopy(spec)
        annulation["id"] = "annuler-" + uuid.uuid4().hex
        premiers.add(operation(annulation, annulation["steps"][0])["operation_id"])
        commence.clear(); terminer.clear()
        interrompu = await client.start_workflow(ProjetWorkflow.run, annulation,
                                                  id=workflow_id(annulation), task_queue=queue)
        await asyncio.wait_for(commence.wait(), 20)
        await interrompu.signal(ProjetWorkflow.annuler)
        try:
            await asyncio.wait_for(interrompu.result(), 20)
        except WorkflowFailureError as exc:
            assert getattr(exc.cause, "type", "") == "ProjetAnnule"
        else:
            raise AssertionError("Le workflow annulé a été déclaré réussi.")
    return {"serveur_reel": True, "reprise_nouveau_worker": True, "retry_identite_stable": True,
            "pause_reprise": True, "annulation": True, "replay": True, "activites": "factices"}


async def main(a):
    if a.adresse:
        return await verifier(await Client.connect(a.adresse, namespace=a.namespace))
    with tempfile.TemporaryDirectory(prefix="jarvis-temporal-") as tmp:
        env = await WorkflowEnvironment.start_local(namespace=a.namespace, download_dest_dir=a.bin,
                                                    dev_server_existing_path=a.cli,
                                                    dev_server_database_filename=str(Path(tmp) / "temporal.db"))
        try:
            return await verifier(env.client)
        finally:
            await env.shutdown()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--adresse", help="serveur de test existant, sinon serveur dev éphémère")
    p.add_argument("--namespace", default="default")
    p.add_argument("--bin", default="/tmp/jarvis-temporal-bin")
    p.add_argument("--cli", help="chemin du CLI Temporal officiel déjà installé")
    try:
        print(json.dumps(asyncio.run(main(p.parse_args())), ensure_ascii=False))
    except Exception as exc:
        print(f"Validation Temporal réelle non réussie : {type(exc).__name__}.", file=sys.stderr)
        raise SystemExit(1)
