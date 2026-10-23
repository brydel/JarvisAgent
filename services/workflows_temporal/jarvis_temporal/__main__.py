"""Lancement explicite du prototype ; aucune mission locale n'est migrée implicitement."""

from __future__ import annotations

import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
import os
from pathlib import Path
import signal
import sys

from temporalio.client import Client, WorkflowHistory
from temporalio.common import WorkflowIDReusePolicy
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer, Worker

from .activites import Activites
from .contrat import valider, workflow_id
from .controleur import Controleur
from .workflow import ProjetWorkflow

QUEUE = "jarvis-prototype-v1"


def _lire(chemin: str) -> dict:
    path = Path(chemin)
    if path.stat().st_size > 48_000:
        raise ValueError("Projet trop volumineux.")
    return valider(json.loads(path.read_text()))


async def _worker(client: Client) -> None:
    config = Path(os.environ.get("JARVIS_CONFIG_DIR") or Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "jarvis")
    controleur = Controleur(os.environ.get("JARVIS_STUDIO_URL", "http://127.0.0.1:7717"),
                            os.environ.get("JARVIS_STUDIO_TOKEN_FILE", str(config / "studio_jeton")))
    arret = asyncio.Event()
    for nom in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(nom, arret.set)
    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="passerelle-temporal") as executor:
        async with Worker(client, task_queue=QUEUE, workflows=[ProjetWorkflow],
                          activities=[Activites(controleur).executer], activity_executor=executor,
                          max_concurrent_activities=3, graceful_shutdown_timeout=timedelta(seconds=35)):
            print("Worker Temporal prêt : file jarvis-prototype-v1 ; trois activités maximum.", flush=True)
            await arret.wait()


async def _main(a) -> None:
    if a.action == "valider":
        spec = _lire(a.fichier)
        print(json.dumps({"valide": True, "workflow_id": workflow_id(spec)}, ensure_ascii=False))
        return
    if a.action == "replay":
        history_path = Path(a.fichier)
        if history_path.stat().st_size > 16_000_000:
            raise ValueError("Historique trop volumineux.")
        history = WorkflowHistory.from_json(a.id, history_path.read_text())
        await Replayer(workflows=[ProjetWorkflow]).replay_workflow(history)
        print("Historique rejoué sans divergence.")
        return
    if a.action == "dev":
        etat = Path(os.environ.get("JARVIS_STATE_DIR", str(Path.home() / ".local/state/jarvis"))) / "temporal-prototype"
        etat.mkdir(parents=True, exist_ok=True)
        serveur = await WorkflowEnvironment.start_local(
            port=a.port, namespace=a.namespace, download_dest_dir=str(etat / "bin"),
            dev_server_database_filename=str(etat / "temporal.db"),
            dev_server_existing_path=os.environ.get("JARVIS_TEMPORAL_CLI") or None,
        )
        try:
            await _worker(serveur.client)
        finally:
            await serveur.shutdown()
        return
    client = await Client.connect(a.adresse, namespace=a.namespace)
    if a.action == "worker":
        await _worker(client)
    elif a.action == "lancer":
        spec = _lire(a.fichier)
        handle = await client.start_workflow(ProjetWorkflow.run, spec, id=workflow_id(spec), task_queue=QUEUE,
                                             id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE)
        print(json.dumps({"workflow_id": handle.id, "execution_engine": "temporal_prototype"}))
    elif a.action == "etat":
        handle = client.get_workflow_handle(a.id)
        description = await handle.describe()
        print(json.dumps({"workflow_id": a.id, "temporal_status": description.status.name,
                          "progression": await handle.query(ProjetWorkflow.etat)}, ensure_ascii=False))
    elif a.action == "signal":
        handle = client.get_workflow_handle(a.id)
        await handle.signal(a.signal)
        print("Signal transmis.")
    elif a.action == "historique":
        history = await client.get_workflow_handle(a.id).fetch_history()
        # Création exclusive : ne jamais écraser un historique existant.
        with Path(a.fichier).open("x") as fh:
            fh.write(history.to_json())
        print("Historique enregistré ; les arguments et résultats d'outils font partie de ce fichier.")


def main() -> int:
    p = argparse.ArgumentParser(description="Prototype Temporal Jarvis, séparé des missions locales.")
    p.add_argument("--adresse", default=os.environ.get("TEMPORAL_ADDRESS", "127.0.0.1:7233"))
    p.add_argument("--namespace", default=os.environ.get("TEMPORAL_NAMESPACE", "default"))
    sub = p.add_subparsers(dest="action", required=True)
    sub.add_parser("worker")
    a = sub.add_parser("dev"); a.add_argument("--port", type=int, default=7233)
    a = sub.add_parser("valider"); a.add_argument("fichier")
    a = sub.add_parser("lancer"); a.add_argument("fichier")
    a = sub.add_parser("etat"); a.add_argument("id")
    a = sub.add_parser("signal"); a.add_argument("id"); a.add_argument("signal", choices=("suspendre", "reprendre", "annuler"))
    a = sub.add_parser("historique"); a.add_argument("id"); a.add_argument("fichier")
    a = sub.add_parser("replay"); a.add_argument("id"); a.add_argument("fichier")
    args = p.parse_args()
    try:
        asyncio.run(_main(args))
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        # Les causes HTTP peuvent contenir des détails de transport ; l'historique ne doit pas recevoir de secret.
        print(f"Prototype Temporal interrompu : {type(exc).__name__}. Vérifie serveur, réseau et configuration.",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
