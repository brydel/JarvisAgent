"""Politique de délégation : ce que l'usine fait seule, ce qu'elle fait après délégation, ce qu'elle demande.

Source : config/politique.toml (versionnée dans le dépôt), complétée par ~/.config/jarvis/politique.toml
qui ne peut que RESTREINDRE (monter un niveau, retirer une action). Les délégations de niveau 2 sont des
enveloppes posées par l'humain (plafond, échéance, périmètre) dans l'état local ; une proposition venue
d'un agent ou d'un outil externe n'en crée jamais.

`autoriser(action, …)` répond admis / refuse / approbation, journalise, et empile les refus dans la
file d'exceptions (exceptions.json) que l'humain lit groupées (« jarvis politique exceptions »).

Limite honnête : fichiers et état sont écrits par le même utilisateur Linux que le chef. La protection
est applicative (commandes réservées à l'humain, journal à empreintes), pas une barrière système.
"""

from __future__ import annotations

import time
import tomllib

from . import config, store

FICHIER_DEPOT = config.JARVIS_HOME / "config" / "politique.toml"
FICHIER_PERSO = config.CONFIG_DIR / "politique.toml"
DELEGATIONS = "delegations.json"
EXCEPTIONS = "exceptions.json"
NIVEAUX = {1: "automatique", 2: "délégué", 3: "approbation"}


class PolitiqueError(ValueError):
    pass


def _lire(path) -> dict:
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except FileNotFoundError:
        return {}
    except tomllib.TOMLDecodeError as exc:
        raise PolitiqueError(f"{path} illisible : {exc}") from exc


def charger() -> dict:
    """Politique effective : dépôt, puis restrictions personnelles (jamais d'assouplissement)."""
    base = _lire(FICHIER_DEPOT)
    actions = {k: dict(v) for k, v in (base.get("actions") or {}).items() if isinstance(v, dict)}
    for a in actions.values():
        a.setdefault("niveau", 3)
    ignorees: list[str] = []
    perso = _lire(FICHIER_PERSO)
    for nom, v in (perso.get("actions") or {}).items():
        if not isinstance(v, dict):
            continue
        if nom not in actions:
            actions[nom] = {**v, "niveau": max(int(v.get("niveau", 3)), 1)}
            continue
        niveau = int(v.get("niveau", actions[nom]["niveau"]))
        if niveau < int(actions[nom]["niveau"]):
            ignorees.append(f"{nom} : niveau {niveau} refusé (la copie personnelle ne peut que restreindre)")
            niveau = int(actions[nom]["niveau"])
        actions[nom] = {**actions[nom], **v, "niveau": niveau}
    meta = base.get("politique") or {}
    return {"version": int(meta.get("version", 0)), "devise": meta.get("devise", "EUR"), "actions": actions,
            "ignorees": ignorees}


def niveau(action: str, pol: dict | None = None) -> int:
    pol = pol or charger()
    a = pol["actions"].get(action)
    return int(a["niveau"]) if a else 3


# --- Délégations (niveau 2) ---------------------------------------------------------------------

def _vide() -> dict:
    return {"seq": 0, "delegations": []}


def deleguer(action: str, *, perimetre: str, plafond: float = 0.0, jours: int = 7, projet: str = "",
             par: str = "humain") -> dict:
    """L'humain délègue une action de niveau 2 : enveloppe datée, plafonnée, à périmètre nommé."""
    pol = charger()
    n = niveau(action, pol)
    if n != 2:
        raise PolitiqueError(f"« {action} » est de niveau {n} ({NIVEAUX[n]}) : seule une action de niveau 2 se délègue")
    if not perimetre.strip():
        raise PolitiqueError("une délégation nomme son périmètre (canal, environnement, projet…)")

    def _add(data):
        data["seq"] += 1
        d = {"id": f"D-{data['seq']:04d}", "action": action, "perimetre": perimetre.strip()[:200],
             "plafond": float(max(0.0, plafond)), "consomme": 0.0, "projet": projet, "par": par,
             "cree": time.time(), "expire": time.time() + 86400 * max(1, int(jours)), "active": True}
        data["delegations"].append(d)
        return dict(d)

    d = store.update_json(DELEGATIONS, _vide(), _add)
    from . import journal
    journal.ecrire("politique", acteur=par, objet=action, decision="deleguee",
                   raison=f"{d['id']} {perimetre} plafond {plafond:g} {pol['devise']} jusqu'au "
                          f"{time.strftime('%d/%m', time.localtime(d['expire']))}")
    return d


def revoquer(deleg_id: str, par: str = "humain") -> bool:
    def _set(data):
        for d in data["delegations"]:
            if d["id"] == deleg_id.upper() and d["active"]:
                d["active"], d["revoquee"] = False, time.time()
                return True
        return False

    ok = store.update_json(DELEGATIONS, _vide(), _set)
    if ok:
        from . import journal
        journal.ecrire("politique", acteur=par, objet=deleg_id.upper(), decision="revoquee")
    return ok


def delegations(now: float | None = None) -> list[dict]:
    now = now or time.time()
    return [d for d in store.read_json(DELEGATIONS, _vide())["delegations"] if d["active"] and now < d["expire"]]


def _delegation_pour(action: str, projet: str, montant: float, now: float) -> dict | None:
    for d in delegations(now):
        if d["action"] != action:
            continue
        if d.get("projet") and projet and d["projet"] != projet:
            continue
        if montant > 0 and d["consomme"] + montant > d["plafond"] + 1e-9:
            continue
        return d
    return None


# --- Décision ----------------------------------------------------------------------------------

def autoriser(action: str, *, acteur: str, projet: str = "", montant: float = 0.0, detail: str = "",
              now: float | None = None) -> dict:
    """{"decision": "admis"|"refuse"|"approbation", "niveau", "raison", "delegation"}.

    Niveau 1 : admis (si pas de montant : une dépense n'est jamais de niveau 1). Niveau 2 : admis s'il
    existe une délégation active couvrant action, projet et montant ; sinon « approbation » et mise en
    file d'exceptions. Niveau 3 ou action inconnue : « approbation ». Toute dépense passe aussi par
    budgets.verifier : une enveloppe non renseignée vaut zéro.
    """
    now = now or time.time()
    pol = charger()
    n = niveau(action, pol)
    connue = action in pol["actions"]
    delegation = None
    if montant and montant > 0:
        from . import budgets
        ok_b, raison_b = budgets.verifier("depense", montant, projet=projet, now=now)
        if not ok_b:
            decision, raison = "refuse", raison_b
            _journaliser(action, acteur, decision, raison, projet, montant)
            _exception(action, acteur, projet, montant, detail, raison)
            return {"decision": decision, "niveau": n, "raison": raison, "delegation": None}
    if not connue:
        decision, raison = "approbation", f"action « {action} » absente de la politique : approbation explicite requise"
    elif n == 1 and not montant:
        decision, raison = "admis", f"niveau 1 ({pol['actions'][action].get('perimetre', '')})"
    elif n == 1:
        decision, raison = "approbation", "une dépense n'est jamais automatique, même pour une action de niveau 1"
    elif n == 2:
        delegation = _delegation_pour(action, projet, montant, now)
        if delegation:
            decision, raison = "admis", f"délégation {delegation['id']} ({delegation['perimetre']})"
        else:
            decision, raison = "approbation", (f"niveau 2 sans délégation active couvrant {projet or 'ce projet'}"
                                              + (f" et {montant:g} {pol['devise']}" if montant else "")
                                              + " : jarvis politique deleguer " + action + " …")
    else:
        decision, raison = "approbation", f"niveau 3 : {pol['actions'][action].get('perimetre', '')}"
    if decision == "admis" and delegation and montant:
        _consommer(delegation["id"], montant)
    _journaliser(action, acteur, decision, raison, projet, montant)
    if decision != "admis":
        _exception(action, acteur, projet, montant, detail, raison)
    return {"decision": decision, "niveau": n, "raison": raison, "delegation": delegation}


def _consommer(deleg_id: str, montant: float) -> None:
    def _set(data):
        for d in data["delegations"]:
            if d["id"] == deleg_id:
                d["consomme"] = float(d.get("consomme", 0)) + montant

    store.update_json(DELEGATIONS, _vide(), _set)


def _journaliser(action, acteur, decision, raison, projet, montant) -> None:
    try:
        from . import journal
        journal.ecrire("politique", acteur=acteur, objet=action, decision=decision, raison=raison,
                       projet=projet or None, montant=montant or None)
    except Exception:  # noqa: BLE001
        pass


def _exception(action, acteur, projet, montant, detail, raison) -> None:
    """File d'exceptions : les demandes non automatiques, groupées pour l'humain, sans bloquer le reste."""

    def _add(data):
        for e in data["exceptions"]:
            if (e["action"], e["projet"], e.get("detail", "")) == (action, projet, detail[:200]) and e["statut"] == "ouverte":
                e["nb"] = e.get("nb", 1) + 1
                e["derniere"] = time.time()
                return
        data["seq"] += 1
        data["exceptions"].append({"id": f"E-{data['seq']:04d}", "ts": time.time(), "derniere": time.time(), "nb": 1,
                                   "action": action, "acteur": acteur, "projet": projet, "montant": montant,
                                   "detail": detail[:200], "raison": raison, "statut": "ouverte"})
        data["exceptions"] = data["exceptions"][-300:]

    store.update_json(EXCEPTIONS, {"seq": 0, "exceptions": []}, _add)


def exceptions(ouvertes: bool = True) -> list[dict]:
    items = store.read_json(EXCEPTIONS, {"seq": 0, "exceptions": []})["exceptions"]
    return [e for e in items if e["statut"] == "ouverte"] if ouvertes else items


def clore_exception(exc_id: str, decision: str, par: str = "humain") -> bool:
    if decision not in ("accordee", "refusee"):
        raise PolitiqueError("décision : accordee ou refusee")

    def _set(data):
        for e in data["exceptions"]:
            if e["id"] == exc_id.upper() and e["statut"] == "ouverte":
                e["statut"], e["decidee"], e["par"] = decision, time.time(), par
                return True
        return False

    ok = store.update_json(EXCEPTIONS, {"seq": 0, "exceptions": []}, _set)
    if ok:
        from . import journal
        journal.ecrire("politique", acteur=par, objet=exc_id.upper(), decision=decision)
    return ok


# --- Affichage --------------------------------------------------------------------------------

def texte(pol: dict | None = None) -> str:
    pol = pol or charger()
    out = [f"Politique de délégation v{pol['version']} ({pol['devise']}) — niveaux : 1 automatique, 2 délégué, 3 approbation"]
    for n in (1, 2, 3):
        noms = sorted(k for k, v in pol["actions"].items() if int(v["niveau"]) == n)
        out.append(f"  {n} {NIVEAUX[n]:<12} {', '.join(noms) or '—'}")
    deleg = delegations()
    out.append("Délégations actives : " + (", ".join(
        f"{d['id']} {d['action']} ({d['perimetre']}, {d['consomme']:g}/{d['plafond']:g} {pol['devise']}, "
        f"jusqu'au {time.strftime('%d/%m', time.localtime(d['expire']))})" for d in deleg) or "aucune"))
    exc = exceptions()
    out.append(f"Exceptions en attente : {len(exc)}" + (" (jarvis politique exceptions)" if exc else ""))
    for i in pol["ignorees"]:
        out.append(f"  ⚠ copie personnelle ignorée : {i}")
    return "\n".join(out)


def texte_exceptions() -> str:
    exc = exceptions()
    if not exc:
        return "Aucune exception en attente : tout ce qui a été demandé était autorisé."
    out = ["EXCEPTIONS EN ATTENTE DE TA DÉCISION (groupées, rien d'autre n'est bloqué)"]
    for e in exc:
        quand = time.strftime("%d/%m %H:%M", time.localtime(e["derniere"]))
        out.append(f"  {e['id']} {e['action']} ×{e['nb']} [{e['acteur']}{', ' + e['projet'] if e['projet'] else ''}"
                   f"{', ' + format(e['montant'], 'g') + ' €' if e.get('montant') else ''}] {quand}")
        out.append(f"      {e['detail'] or '(sans détail)'} — {e['raison']}")
    out.append("Décider : jarvis politique exception <E-xxxx> accordee|refusee  ·  déléguer : jarvis politique deleguer <action> --perimetre … --plafond N --jours N")
    return "\n".join(out)
