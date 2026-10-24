"""RedTeam dans Jarvis : transport existant sous mandat, rapports et demande de revue durable."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

from . import config, store

FILE = "redteam.json"


def retain(result: dict, *, node: str, project: str) -> dict:
    """Conserve le rapport reçu comme donnée non fiable, sans promotion de ses conclusions."""
    from . import communaute, missions
    if (not isinstance(result, dict) or result.get("status") != "reported"
            or not isinstance(result.get("delegation"), dict)):
        raise ValueError("Rapport RedTeam incomplet.")
    ident = result.get("mission_id")
    delegation = result["delegation"]
    if (not isinstance(ident, str) or not re.fullmatch(r"RT-[a-zA-Z0-9_-]{1,64}", ident)
            or delegation.get("mission_id") != ident
            or delegation.get("authorization_scope") != {"tools": [], "network_targets": [], "merge": False}
            or delegation.get("requested_capability") != "security.independent_review"
            or (result.get("verification") or {}).get("impact_confirmed") is not False
            or not isinstance(result.get("evidence_sha256"), str)
            or not re.fullmatch(r"[a-f0-9]{64}", result["evidence_sha256"])):
        raise ValueError("Rapport ou délégation hors contrat ; aucune permission héritée.")
    # Une opération de publication idempotente survit à un arrêt entre publication et sauvegarde.
    content = json.dumps(result["delegation"], ensure_ascii=False, sort_keys=True)
    message = communaute.publier(project, content, auteur="redteam", type="question", salon="securite",
        titre="Revue indépendante RedTeam " + ident, preuves=result["delegation"]["evidence_references"],
        operation_id="redteam:" + node + ":" + ident, tenant_id=missions.tenant_local())
    record = {"node": node, "project": project, "report": result, "review_thread": message["fil_id"],
              "delivery": "published", "review_status": "pending"}
    store.update_json(FILE, {}, lambda data: data.update({node + ":" + ident: record}))
    store.feed_add("note", f"RedTeam {ident} : rapport reçu ; revue indépendante publiée.", projet=project)
    return record


def local(request: dict, *, project: str) -> dict:
    entry = config.JARVIS_HOME / "services/noeud_jetson/redteam_cli.py"
    process = subprocess.run([sys.executable, str(entry)], input=json.dumps(request), capture_output=True,
                             text=True, timeout=35)
    data = json.loads(process.stdout)
    if process.returncode or data.get("erreur"):
        raise ValueError(data.get("erreur", "Moteur local en échec."))
    return retain(data, node="local-redteam", project=project)


def remote(request: dict, *, project: str, mandate: str) -> dict:
    """Mandat RedTeam distinct : le mandat audio du Board ne donne aucun droit de sécurité."""
    from . import noeud, outils, executants
    if (not isinstance(request, dict) or set(request) != {"mission_id", "deadline"}
            or not isinstance(request["mission_id"], str)
            or not re.fullmatch(r"RT-[a-zA-Z0-9_-]{1,64}", request["mission_id"])):
        raise ValueError("Mission distante hors contrat.")
    r = noeud.reglages()
    if not r.get("actif") or not r.get("connexion"):
        raise ValueError("Nœud distant non configuré.")
    op = outils.executer({"operation_id": "redteam:" + request["mission_id"], "mandat_id": mandate,
        "project": project, "tool": f"mcp.{r['connexion']}.redteam_auditer", "arguments": request,
        "cost_cents": 0}, par="jarvis:redteam")
    data = (op.get("resultat") or {}).get("structuredContent")
    if (op.get("status") != "succeeded" or not isinstance(data, dict) or data.get("erreur")
            or data.get("mission_id") != request["mission_id"]):
        raise ValueError("Audit distant refusé, échoué ou incertain ; consulter le journal d'opérations.")
    record = retain(data, node=r["connexion"], project=project)
    # Observation d'un appel abouti, sans inventer de mesures RAM/GPU.
    executants.declarer("redteam-jetson", hote="noeud-ssh", capacite={"security.sast": True}, par="redteam")
    return record



def authorize(connection: str, project: str) -> dict:
    """Autorisation explicite, distincte de celle de l'audio, bornée à dix appels et une heure."""
    from . import connexions, mandats
    observed = connexions.decouvrir(connection)
    allowed = list(observed["outils_autorises"])
    if "redteam_auditer" not in allowed:
        connexions.configurer_outils(connection, allowed + ["redteam_auditer"], par="humain:redteam")
    mandate = mandats.creer({"version": 1, "owner": "humain", "project": project,
        "tools": [f"mcp.{connection}.redteam_auditer"], "destinations": [f"mcp:{connection}"],
        "expires_at": time.time() + 3600, "max_cost_cents": 0, "max_actions": 10}, par="humain:redteam")
    return {"mandat": mandate["id"], "expires_at": mandate["expires_at"], "max_actions": 10}


def overview() -> list[dict]:
    return list(store.read_json(FILE, {}).values())[-50:]


def reviews(key: str) -> dict:
    from . import communaute, missions
    record = store.read_json(FILE, {}).get(key)
    if not record:
        raise ValueError("Rapport inconnu.")
    return communaute.fil(record["project"], record["review_thread"], tenant_id=missions.tenant_local())


def add_parser(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser("redteam", help="audits autorisés et revues indépendantes")
    actions = parser.add_subparsers(dest="redteam_action", required=True)
    actions.add_parser("liste").set_defaults(fn=command)
    setup = actions.add_parser("autoriser", help="autoriser explicitement un outil RedTeam découvert (propriétaire)")
    setup.add_argument("--connexion", required=True)
    setup.add_argument("--projet", required=True)
    setup.set_defaults(fn=command)
    review = actions.add_parser("revue")
    review.add_argument("cle", help="nœud:RT-identifiant")
    review.set_defaults(fn=command)
    for action in ("local", "distant"):
        scan = actions.add_parser(action)
        scan.add_argument("demande", help="JSON {mission_id, deadline}")
        scan.add_argument("--projet", required=True)
        if action == "distant":
            scan.add_argument("--mandat", required=True)
        scan.set_defaults(fn=command)


def command(args: argparse.Namespace) -> int:
    try:
        if args.redteam_action == "autoriser":
            from .cli import _human_only
            refused = _human_only("autoriser RedTeam sur un noeud")
            if refused is not None:
                return refused
            result = authorize(args.connexion, args.projet)
        elif args.redteam_action == "liste":
            result = overview()
        elif args.redteam_action == "revue":
            result = reviews(args.cle)
        else:
            path = Path(args.demande)
            if path.stat().st_size > 4096:
                raise ValueError("Demande trop longue.")
            request = json.loads(path.read_text())
            if args.redteam_action == "local":
                result = local(request, project=args.projet)
            else:
                result = remote(request, project=args.projet, mandate=args.mandat)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f"RedTeam : {exc}", file=sys.stderr)
        return 1
