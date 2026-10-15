"""Budgets : enveloppes de dépense par catégorie, projet et période. Non renseigné = zéro.

Les abonnements Claude et Codex sont suivis en jetons (usage.py). Ici on parle d'argent : services tiers,
acquisition, infrastructure, remboursements… Une dépense n'est admise que si une enveloppe la couvre
ENTIÈREMENT, réserve pour incidents déduite. Les enveloppes sont posées par l'humain (jarvis budget definir),
les dépenses engagées sont enregistrées (jarvis budget engager) pour comparer estimé et réel.

Rien ici ne paie quoi que ce soit : c'est une comptabilité d'autorisation. Les montants réellement
encaissés (revenus) ont leur propre enregistrement pour ne jamais confondre marge brute et bénéfice net.
"""

from __future__ import annotations

import time

from . import store

FILE = "budgets.json"
CATEGORIES = ("depense", "infrastructure", "services", "acquisition", "remboursement", "abonnement", "humain")
PERIODES = {"mois": 30 * 86400, "semaine": 7 * 86400, "jour": 86400, "unique": None}
RESERVE_INCIDENT_PCT = 10  # part de chaque enveloppe gardée pour les imprévus


def _vide() -> dict:
    return {"seq": 0, "enveloppes": [], "mouvements": []}


def definir(categorie: str, plafond: float, *, periode: str = "mois", projet: str = "", par: str = "humain",
            note: str = "") -> dict:
    if categorie not in CATEGORIES:
        raise ValueError(f"catégorie inconnue « {categorie} » (valeurs : {', '.join(CATEGORIES)})")
    if periode not in PERIODES:
        raise ValueError(f"période inconnue « {periode} » (valeurs : {', '.join(PERIODES)})")
    if plafond < 0:
        raise ValueError("le plafond est positif ou nul")

    def _set(data):
        for e in data["enveloppes"]:
            if (e["categorie"], e["projet"], e["periode"]) == (categorie, projet, periode):
                e.update(plafond=float(plafond), maj=time.time(), par=par, note=note[:200])
                return dict(e)
        data["seq"] += 1
        e = {"id": f"B-{data['seq']:04d}", "categorie": categorie, "projet": projet, "periode": periode,
             "plafond": float(plafond), "cree": time.time(), "maj": time.time(), "par": par, "note": note[:200]}
        data["enveloppes"].append(e)
        return dict(e)

    e = store.update_json(FILE, _vide(), _set)
    from . import journal
    journal.ecrire("budget", acteur=par, objet=f"{categorie}/{projet or '*'}/{periode}", decision="definie",
                   raison=f"plafond {plafond:g}" + (f" — {note}" if note else ""))
    return e


def _consomme(data: dict, e: dict, now: float) -> float:
    """Dépenses de la période imputées à l'enveloppe : celles de son projet ; pour l'enveloppe globale
    (projet vide), celles de tous les projets qui n'ont pas d'enveloppe propre dans cette catégorie."""
    duree = PERIODES[e["periode"]]
    debut = now - duree if duree else 0
    avec_propre = {x["projet"] for x in data["enveloppes"] if x["categorie"] == e["categorie"] and x["projet"]}

    def _imputee(m) -> bool:
        if e["projet"]:
            return m["projet"] == e["projet"]
        return m["projet"] not in avec_propre

    return sum(m["montant"] for m in data["mouvements"]
               if m["type"] == "depense" and m["categorie"] == e["categorie"] and m["ts"] >= debut and _imputee(m))


def verifier(categorie: str, montant: float, *, projet: str = "", now: float | None = None) -> tuple[bool, str]:
    """(admis, raison). L'enveloppe la plus précise (projet) prime ; sans enveloppe, zéro : refus."""
    now = now or time.time()
    if montant <= 0:
        return True, "aucune dépense"
    data = store.read_json(FILE, _vide())
    candidats = [e for e in data["enveloppes"] if e["categorie"] == categorie and e["projet"] in (projet, "")]
    candidats.sort(key=lambda e: e["projet"] != projet)  # enveloppe du projet d'abord
    if not candidats:
        return False, f"aucune enveloppe « {categorie} »{' pour ' + projet if projet else ''} : budget non renseigné = 0"
    e = candidats[0]
    deja = _consomme(data, e, now)
    disponible = e["plafond"] * (1 - RESERVE_INCIDENT_PCT / 100) - deja
    if montant > disponible + 1e-9:
        return False, (f"enveloppe {e['id']} {categorie}/{e['projet'] or '*'} : {montant:g} demandé, "
                       f"{max(0.0, disponible):g} disponible (plafond {e['plafond']:g} par {e['periode']}, "
                       f"{deja:g} engagé, réserve incidents {RESERVE_INCIDENT_PCT} %)")
    return True, f"enveloppe {e['id']} : {deja + montant:g}/{e['plafond']:g} après cette dépense"


def engager(categorie: str, montant: float, *, projet: str = "", libelle: str = "", par: str = "chef",
            estime: bool = False) -> dict:
    """Enregistre une dépense engagée (ou estimée : comparée plus tard au réel). Ne vérifie pas l'enveloppe :
    c'est politique.autoriser qui refuse AVANT ; ici on tient les comptes de ce qui a été fait."""
    if categorie not in CATEGORIES:
        raise ValueError(f"catégorie inconnue « {categorie} »")

    def _add(data):
        m = {"ts": time.time(), "type": "depense", "categorie": categorie, "projet": projet, "montant": float(montant),
             "libelle": libelle[:200], "par": par, "estime": bool(estime)}
        data["mouvements"].append(m)
        data["mouvements"] = data["mouvements"][-5000:]
        return m

    m = store.update_json(FILE, _vide(), _add)
    from . import journal
    journal.ecrire("budget", acteur=par, objet=f"{categorie}/{projet or '*'}", decision="estimee" if estime else "engagee",
                   raison=f"{montant:g} {libelle}".strip())
    return m


def encaisser(montant: float, *, projet: str, libelle: str = "", par: str = "humain") -> dict:
    """Revenu réellement encaissé (jamais une estimation)."""

    def _add(data):
        m = {"ts": time.time(), "type": "revenu", "categorie": "revenu", "projet": projet, "montant": float(montant),
             "libelle": libelle[:200], "par": par, "estime": False}
        data["mouvements"].append(m)
        return m

    m = store.update_json(FILE, _vide(), _add)
    from . import journal
    journal.ecrire("budget", acteur=par, objet=f"revenu/{projet}", decision="encaisse", raison=f"{montant:g} {libelle}".strip())
    return m


def bilan(jours: float = 30, now: float | None = None) -> dict:
    """Encaissé réel, dépensé réel, estimé, par projet. La « marge » affichée omet ce qui n'est pas saisi : dit tel quel."""
    now = now or time.time()
    data = store.read_json(FILE, _vide())
    debut = now - jours * 86400
    par_projet: dict[str, dict] = {}
    for m in data["mouvements"]:
        if m["ts"] < debut:
            continue
        p = par_projet.setdefault(m["projet"] or "*", {"revenus": 0.0, "depenses": 0.0, "estimations": 0.0})
        if m["type"] == "revenu":
            p["revenus"] += m["montant"]
        elif m.get("estime"):
            p["estimations"] += m["montant"]
        else:
            p["depenses"] += m["montant"]
    return {"jours": jours, "projets": par_projet, "enveloppes": data["enveloppes"],
            "avertissement": "marge = encaissé − dépenses saisies ; abonnements, temps humain et frais non saisis ne sont pas déduits"}


def texte(now: float | None = None) -> str:
    now = now or time.time()
    data = store.read_json(FILE, _vide())
    out = ["BUDGETS (une enveloppe non renseignée vaut zéro : toute dépense est alors refusée)"]
    if not data["enveloppes"]:
        out.append("  aucune enveloppe : jarvis budget definir <catégorie> <plafond> [--projet P] [--periode mois|semaine|jour|unique]")
    for e in data["enveloppes"]:
        deja = _consomme(data, e, now)
        out.append(f"  {e['id']} {e['categorie']:<14} {e['projet'] or '*':<12} {deja:>8.2f} / {e['plafond']:>8.2f} par {e['periode']}"
                   + (f"  — {e['note']}" if e.get("note") else ""))
    b = bilan(30, now)
    if b["projets"]:
        out.append("30 derniers jours :")
        for p, v in sorted(b["projets"].items()):
            out.append(f"  {p:<14} encaissé {v['revenus']:.2f} · dépensé {v['depenses']:.2f} · estimé {v['estimations']:.2f}"
                       f" · marge brute saisie {v['revenus'] - v['depenses']:.2f}")
        out.append("  " + b["avertissement"])
    return "\n".join(out)
