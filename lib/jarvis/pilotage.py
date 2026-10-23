"""Contrôleur du runtime : configuration propriétaire, modèle figé par run et workers bornés."""
from __future__ import annotations

import atexit
import json
import threading
import time

from . import annulation, connexions, contrats, modeles_runtime, store

_verrou = threading.RLock()
_workers: dict[str, tuple[threading.Thread, annulation.ControleExecution]] = {}
MAX_WORKERS = 2


def _db():
    c = connexions._base()
    c.execute("CREATE TABLE IF NOT EXISTS runtime_configuration (id INTEGER PRIMARY KEY CHECK(id=1), "
              "revision INTEGER NOT NULL,spec TEXT NOT NULL,verification TEXT,maj REAL NOT NULL,acteur TEXT NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS runtime_modeles (run_id TEXT PRIMARY KEY,spec TEXT NOT NULL,empreinte TEXT NOT NULL)")
    return c


def _configuration():
    row = _db().execute("SELECT revision,spec,verification FROM runtime_configuration WHERE id=1").fetchone()
    if row is None:
        return None, None, None
    try:
        spec = modeles_runtime.valider_configuration(json.loads(row[1]))
        verification = json.loads(row[2]) if row[2] else None
    except (ValueError, TypeError) as exc:
        raise ValueError("Configuration du modèle illisible ; aucun modèle lancé.") from exc
    return row[0], spec, verification


def modele():
    _, spec, verification = _configuration()
    return {"configuration": modeles_runtime.public_configuration(spec) if spec else None, "verification": verification}


def configurer_modele(spec: dict, *, par: str):
    spec = modeles_runtime.valider_configuration(spec)
    _db()
    with store.transaction() as c:
        c.execute("INSERT INTO runtime_configuration(id,revision,spec,verification,maj,acteur) VALUES(1,1,?,NULL,?,?) "
                  "ON CONFLICT(id) DO UPDATE SET revision=revision+1,spec=excluded.spec,verification=NULL,maj=excluded.maj,acteur=excluded.acteur",
                  (json.dumps(spec, allow_nan=False), time.time(), par))
    return modele()


def verifier_modele(*, annulation=None):
    revision, spec, _ = _configuration()
    if spec is None:
        raise ValueError("Configurer un modèle et sa référence d'authentification avant vérification.")
    resultat = modeles_runtime.verifier(spec, annulation=annulation)
    with store.transaction() as c:
        c.execute("UPDATE runtime_configuration SET verification=? WHERE id=1 AND revision=?",
                  (json.dumps(resultat, allow_nan=False), revision))
    return resultat


def creer_run(corps: dict, *, par: str, source="board"):
    from . import agent_runtime
    permis = {"agent", "tache", "configuration_modele", "max_tours", "reserve_model_cents", "max_model_output_tokens", "operation_id"}
    if not isinstance(corps, dict) or set(corps) - permis or not {"agent", "tache"} <= set(corps):
        raise ValueError("Contrats d'agent et de tâche attendus, sans champ d'autorité supplémentaire.")
    revision, spec, _ = _configuration()
    if spec is None:
        raise ValueError("Aucun modèle configuré par le propriétaire.")
    demande = modeles_runtime.valider_configuration(corps.get("configuration_modele", spec))
    if demande != spec:
        raise ValueError("La configuration demandée diffère de celle enregistrée par le propriétaire.")
    agent, tache = contrats.valider_agent(corps["agent"]), contrats.valider_tache(corps["tache"])
    if agent["provider"] != spec["provider"] or agent["model"] != spec["model"]:
        raise ValueError("Le contrat de l'agent doit nommer le fournisseur et le modèle configurés.")
    max_tours = corps.get("max_tours", min(8, spec["max_turns"]))
    max_output = corps.get("max_model_output_tokens", spec["max_output_tokens"])
    if type(max_tours) is not int or max_tours > spec["max_turns"] or type(max_output) is not int or max_output > spec["max_output_tokens"]:
        raise ValueError("Les limites du run dépassent la configuration du modèle.")
    _db()
    agent_runtime._db()
    # Création et liaison atomiques dans la même base ; aucun réseau dans cette transaction.
    with store.transaction() as c:
        if _configuration()[0] != revision:
            raise ValueError("La configuration a changé ; relire les paramètres avant de créer la mission.")
        run = agent_runtime.creer(agent, tache, par=par, max_tours=max_tours,
            reserve_model_cents=corps.get("reserve_model_cents", 1), max_model_output_tokens=max_output,
            source=source, operation_id=corps.get("operation_id", "creation:" + tache["id"]))
        ancien = c.execute("SELECT empreinte FROM runtime_modeles WHERE run_id=?", (run["id"],)).fetchone()
        empreinte = contrats.empreinte(spec)
        if ancien and ancien[0] != empreinte:
            raise ValueError("Cette création existe déjà avec une autre configuration de modèle.")
        c.execute("INSERT INTO runtime_modeles VALUES(?,?,?) ON CONFLICT(run_id) DO NOTHING",
                  (run["id"], json.dumps(spec, allow_nan=False), empreinte))
    return run


def _modele_du_run(ident):
    row = _db().execute("SELECT spec,empreinte FROM runtime_modeles WHERE run_id=?", (ident,)).fetchone()
    if row is None:
        raise ValueError("Liaison du modèle absente ; aucun modèle lancé.")
    spec = modeles_runtime.valider_configuration(json.loads(row[0]))
    if contrats.empreinte(spec) != row[1]:
        raise ValueError("Liaison du modèle invalide ; aucun modèle lancé.")
    return spec


def _fabrique_modele(configuration):
    return modeles_runtime.OpenAIResponses(configuration)


def lancer(ident: str, *, par: str, stop=None):
    from . import agent_runtime
    if stop is not None and stop.is_set():
        raise ValueError("Le service s'arrête ; aucun nouveau run lancé.")
    run = agent_runtime.voir(ident)
    if run["status"] not in ("planned", "running"):
        return run
    spec = _modele_du_run(ident)
    if not modeles_runtime.public_configuration(spec)["auth"]["configuree"]:
        raise ValueError("La variable d'authentification du modèle est absente ; aucun appel lancé.")
    with _verrou:
        if ident in _workers and _workers[ident][0].is_alive():
            return agent_runtime.voir(ident)
        if sum(f.is_alive() for f, _ in _workers.values()) >= MAX_WORKERS:
            raise ValueError("Deux missions outillées sont déjà en cours ; attendre une place.")
        controle = annulation.ControleExecution(interruption=(lambda: "arrêt du service" if stop.is_set() else "") if stop is not None else None)

        def travailler():
            try:
                modele = _fabrique_modele(spec)
                for _ in range(run["max_tours"] + 1):
                    controle.verifier()
                    r = agent_runtime.executer_tour(ident, modele, par=par, annulation=controle)
                    if r["status"] not in ("planned", "running"):
                        break
            except annulation.ExecutionAnnulee:
                pass
            except Exception as exc:  # noqa: BLE001 — aucun prompt ni credential dans le journal
                store.feed_add("erreur", f"mission outillée {ident} : {type(exc).__name__}")
            finally:
                with _verrou:
                    if _workers.get(ident, (None,))[0] is threading.current_thread():
                        _workers.pop(ident, None)
                c = getattr(store._local, "conn", None)
                if c is not None:
                    c.close()
                    store._local.conn = None

        fil = threading.Thread(target=travailler, name="runtime-" + ident, daemon=False)
        _workers[ident] = (fil, controle)
        fil.start()
    return agent_runtime.voir(ident)


def commander(ident: str, action: str, *, par: str, stop=None):
    from . import agent_runtime
    if action == "executer":
        return lancer(ident, par=par, stop=stop)
    if action == "reprendre":
        agent_runtime.reprendre(ident, par=par)
        return lancer(ident, par=par, stop=stop)
    if action not in ("pause", "annuler"):
        raise ValueError("Commande de mission inconnue.")
    resultat = (agent_runtime.pauser if action == "pause" else agent_runtime.annuler)(ident, par=par)
    with _verrou:
        worker = _workers.get(ident)
        if worker:
            worker[1].annuler("pause demandée" if action == "pause" else "annulation demandée")
    return resultat


def arreter():
    """Arrêt du service : annuler les appels et joindre les workers avant de fermer le serveur."""
    with _verrou:
        travailleurs = list(_workers.values())
        for _, controle in travailleurs:
            controle.annuler("arrêt du service")
    for fil, _ in travailleurs:
        if fil is not threading.current_thread():
            fil.join()


def attendre(ident):
    with _verrou:
        worker = _workers.get(ident)
    if worker:
        while worker[0].is_alive():
            worker[0].join(timeout=0.2)


atexit.register(arreter)
