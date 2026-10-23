"""Contrats communs des voies historiques, sans leur accorder de nouveaux outils.

Une projection décrit le profil réellement lancé ; elle n'est pas un mandat ni une preuve de connexion.
Les inconnues de coût/modèle restent explicites. Le protocole du runner contrôle ces contrats côté réception.
"""

from __future__ import annotations

import hashlib
import re

from . import contrats

ROLES_DOCUMENTAIRES = {"contextualiser": "recherche", "preparer": "redaction", "analyse_document": "recherche"}


def pour_mission(env: dict) -> dict:
    """Profil documentaire des adaptateurs actuels, construit hors du document transmis au modèle."""
    travail = env["travail"]
    role = ROLES_DOCUMENTAIRES.get(travail.get("type"), "generaliste")
    provider = env["fournisseur"]
    provider_id = provider if re.fullmatch(r"[a-z0-9_.-]{1,64}", provider) else hashlib.sha256(provider.encode()).hexdigest()[:24]
    agent_id = f"agent-documentaire-{provider_id}-{role}"
    agent = contrats.valider_agent({
        "version": 1, "id": agent_id, "role": role, "profile": "documentaire", "provider": provider,
        "tools": [], "required_capabilities": [],
        "budget": {"max_tokens": None, "max_cost_cents": None, "max_duration_s": env["delai_s"]},
    })
    objectif = env.get("objectif") or f"Traiter une tâche de type {travail.get('type', 'analyse')}"
    # Les champs d'exécution réservés ne viennent jamais du document ni d'un AgentSpec soumis par le modèle.
    tache = contrats.valider_tache({
        "version": 1, "id": env["tache_id"], "agent_id": agent_id, "objective": objectif,
        "project": str(travail.get("espace") or "")[:200],
        "inputs": [f"mission:{env['mission_id']}"],
        "acceptance": ["Rendre le livrable de la tâche et satisfaire la revue du moteur de missions."],
        "required_tools": [], "mandate_id": None, "execution_engine": "local",
        "max_attempts": env.get("essais_max", 1),
    })
    source = "board" if str(env.get("mission_source", "")).startswith("board") else "cli"
    run = contrats.valider_run({
        "version": 1, "id": env["tentative_id"], "agent_id": agent_id, "task_id": env["tache_id"],
        "status": "planned", "source": source, "session_ref": None, "evidence": [],
    })
    return {"agent": agent, "tache": tache, "run": run}


def pour_workmux(a: dict) -> dict:
    """Même schéma pour une session code observée ; les outils sont ceux du profil, pas des connexions prouvées."""
    identite = "\0".join(str(a.get(k) or "") for k in ("project", "worktree", "session", "window"))
    cle = hashlib.sha256(identite.encode()).hexdigest()[:24]
    role = a.get("role_id") or (a.get("tache") or {}).get("role") or "non-identifie"
    provider = a.get("kind", "").lower()
    provider = provider if provider in ("claude", "codex") else "auto"
    agent_id = f"agent-code-{cle}"
    agent = contrats.valider_agent({
        "version": 1, "id": agent_id, "role": role, "profile": "code", "provider": provider,
        "model": a.get("modele_id") or (a.get("tache") or {}).get("modele_id") or "",
        "tools": ["code.shell", "code.workspace"], "required_capabilities": [],
        "budget": {"max_tokens": None, "max_cost_cents": None, "max_duration_s": None},
    })
    tache = contrats.valider_tache({
        "version": 1, "id": f"task-{cle}", "agent_id": agent_id,
        "objective": (a.get("title") or f"Travail {a.get('worktree') or 'observé'}")[:2000],
        "project": str(a.get("project") or "")[:200],
        "acceptance": ["Vérifier le livrable contre les critères de la tâche sur sa version exacte."],
        "inputs": [f"worktree:{a.get('worktree') or ''}"], "required_tools": [],
    })
    etat = {"working": "running", "waiting": "blocked", "untracked": "blocked", "silent": "blocked",
            "idle": "blocked", "done": "blocked"}.get(a.get("status"), "planned")
    run = contrats.valider_run({
        "version": 1, "id": f"run-{cle}", "agent_id": agent_id, "task_id": tache["id"],
        "status": etat, "source": "workmux",
        "session_ref": f"{a['session']}:{a['window']}" if a.get("session") and a.get("window") else None,
    })
    return {"agent": agent, "tache": tache, "run": run}


def pour_prompt(*, role: str, projet: str, issue: str, branche: str) -> dict:
    return pour_workmux({"role_id": role, "project": projet, "worktree": branche,
                        "title": f"Traiter l'issue {issue}", "status": "planned"})


def preflight(agent_spec: dict, task_spec: dict, diagnostic: dict, *, destination: str = "", cost_cents: int = 0) -> dict:
    """Vérifie les prérequis déclarés sans lancer de modèle, réserver de budget ni accorder un outil."""
    agent = contrats.valider_agent(agent_spec)
    tache = contrats.valider_tache(task_spec)
    if type(cost_cents) is not int or cost_cents < 0:
        raise contrats.ContratError("Le coût prévu doit être un nombre entier de centimes positif ou nul.")
    if tache["agent_id"] != agent["id"]:
        raise contrats.ContratError("La tâche ne référence pas cet agent.")
    preuves = {c["id"]: c for c in diagnostic.get("capacites", [])}
    manquantes = [c for c in agent["required_capabilities"] if not preuves.get(c, {}).get("available")]
    outils = [o for o in tache["required_tools"] if o not in agent["tools"]]
    raisons = [f"Capacité non vérifiée : {c}" for c in manquantes] + [f"Outil absent du profil : {o}" for o in outils]
    decisions = []
    if tache["required_tools"]:
        if not tache["mandate_id"]:
            raisons.append("Un mandat est requis pour les outils de cette tâche.")
        else:
            from . import mandats
            for outil in tache["required_tools"]:
                demande = {"project": tache["project"], "tool": outil, "cost_cents": cost_cents}
                if destination:
                    demande["destination"] = destination
                decision = mandats.autoriser(tache["mandate_id"], demande)
                decisions.append({"tool": outil, **decision})
                if not decision["admis"]:
                    raisons.append(f"{outil} : {decision['raison']}")
    # Un appel --version n'atteste ni une authentification ni une inférence sur le modèle demandé.
    provider = agent["provider"]
    inference = preuves.get(f"provider.{provider}.inference", {})
    if provider == "auto" or not inference.get("available"):
        raisons.append("Inférence et modèle non vérifiés pour ce profil ; aucun appel facturable effectué.")
    return {"version": 1, "admis": not raisons, "raisons": raisons, "capacites_non_verifiees": manquantes,
            "outils_absents": outils, "autorisations": decisions, "budget_reserve": False,
            "note": "Préflight uniquement : aucune exécution ni extension des politiques historiques."}
