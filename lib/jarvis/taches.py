"""Registre des tâches : qui fait quoi, avec quel rôle et quel modèle, pour quel résultat.

Chaque lancement (`jarvis task`) crée une fiche. Le démon la tient à jour à partir de l'état des
agents (début, attente, fin, jetons consommés). Le cockpit s'en sert pour afficher le rôle et le
modèle de chaque agent, les lanceurs pour retrouver le modèle d'un worktree, et le bilan pour
mesurer ce que l'usine produit.
"""

from __future__ import annotations

import time
from pathlib import Path

from . import roles, store

FILE = "taches.json"
MAX = 600
OUVERTS = ("lancee", "en_cours", "attente", "silencieuse", "inconnue")
STATUTS = {"lancee": "lancée", "en_cours": "en cours", "attente": "attend", "silencieuse": "silencieuse",
           "inconnue": "état inconnu", "terminee": "terminée", "perdue": "interrompue"}
VERDICTS = {"pret": "prêt", "corrections": "corrections demandées"}
DEMARRAGE_MAX = 15 * 60  # une fiche « lancée » jamais vue par workmux après ce délai est perdue
ABSENCE_MAX = 120         # secondes sans voir la fenêtre d'un agent au travail avant de le dire interrompu


def _vide() -> dict:
    return {"seq": 0, "taches": []}


def toutes() -> list[dict]:
    return store.read_json(FILE, _vide())["taches"]


def enregistrer(*, projet: str, issue: str, agent: str, worktree: str, chemin: str = "", role: str = "",
                modele: str = "", modele_id: str = "", effort: str = "", repli: str = "", taille: str = "M",
                plan: str = "", revue: str = "", raison: str = "", secours: bool = False, classe: str = "",
                reservation: str = "") -> dict:
    """Crée la fiche d'un lancement. `chemin` : dossier du worktree (clé des lanceurs)."""
    chemin = str(Path(chemin).resolve()) if chemin else ""

    def _add(data):
        data["seq"] += 1
        fiche = {
            "id": f"T-{data['seq']:05d}", "projet": projet, "issue": issue.upper(), "agent": agent,
            "role": roles.ou_defaut(role)["nom"], "modele": modele, "modele_id": modele_id, "effort": effort,
            "repli": repli, "taille": taille, "plan": plan, "revue": str(revue or ""), "raison": raison,
            "secours": bool(secours), "worktree": worktree, "chemin": chemin, "statut": "lancee",
            "classe": classe, "reservation": reservation,
            "cree": time.time(), "debut": None, "fin": None, "jetons": None, "verdict": "", "verdict_note": "",
        }
        data["taches"].append(fiche)
        data["taches"] = data["taches"][-MAX:]
        return dict(fiche)

    return store.update_json(FILE, _vide(), _add)


def par_chemin(chemin: str) -> dict | None:
    """Fiche la plus récente du worktree `chemin` (ou d'un de ses sous-dossiers)."""
    try:
        cible = Path(chemin).resolve()
    except OSError:
        return None
    for t in reversed(toutes()):
        if not t.get("chemin"):
            continue
        racine = Path(t["chemin"])
        if cible == racine or racine in cible.parents:
            return t
    return None


def pour_agent(projet: str, worktree: str, liste: list[dict] | None = None, chemin: str = "") -> dict | None:
    """Fiche la plus récente d'un agent : par dossier de worktree, sinon par projet + worktree."""
    liste = toutes() if liste is None else liste
    if chemin:
        chemin = str(Path(chemin))
        for t in reversed(liste):
            if t.get("chemin") == chemin:
                return t
    for t in reversed(liste):
        if t["worktree"] == worktree and (t["projet"] == projet or projet in ("", "?", None)):
            return t
    return None


def annuler(tache_id: str) -> None:
    """Retire la fiche d'un lancement qui a échoué techniquement (workmux add)."""
    store.update_json(FILE, _vide(),
                      lambda data: data.__setitem__("taches", [t for t in data["taches"] if t["id"] != tache_id]))


def dernier_auteur(projet: str, issue: str) -> str:
    """Fournisseur qui a produit le dernier travail (hors relecture) sur cette issue, ou ''."""
    for t in reversed(toutes()):
        if t["projet"] == projet and t["issue"] == issue.upper() and not t.get("revue") and t["role"] != "revue":
            return t["agent"]
    return ""


def noter_verdict(projet: str, issue: str, verdict: str, note: str = "") -> dict | None:
    """Enregistre le verdict de la contre-relecture sur la dernière tâche de production de l'issue."""
    if verdict not in VERDICTS:
        raise ValueError(f"verdict inconnu (valeurs : {', '.join(VERDICTS)})")

    def _set(data):
        for t in reversed(data["taches"]):
            if t["projet"] == projet and t["issue"] == issue.upper() and not t.get("revue") and t["role"] != "revue":
                t["verdict"], t["verdict_note"], t["verdict_ts"] = verdict, note.strip()[:500], time.time()
                return dict(t)
        return None

    return store.update_json(FILE, _vide(), _set)


def _trouver(t: dict, par_chemin: dict, par_cle: dict, par_nom: dict) -> dict | None:
    """Agent visible qui correspond à la fiche : par dossier, puis par projet + worktree, puis par worktree seul."""
    a = par_chemin.get(t.get("chemin") or "") or par_cle.get((t["projet"], t["worktree"]))
    if a is None and t["statut"] in OUVERTS:
        # workmux nomme parfois le projet autrement que le registre de Jarvis : pour une tâche en
        # cours, le nom du worktree, s'il est unique à l'écran, suffit à reconnaître l'agent.
        candidats = par_nom.get(t["worktree"], [])
        a = candidats[0] if len(candidats) == 1 else None
    return a


def synchroniser(agents: list[dict], jetons_fn=None, now: float | None = None) -> list[dict]:
    """Aligne les fiches sur l'état réel des agents. Renvoie les fiches qui viennent de se fermer.

    Une fiche fermée porte "jamais_demarre": True quand son agent n'est jamais apparu (lancement
    interrompu). `jetons_fn(fiche) -> dict | None` mesure la consommation d'une tâche terminée.
    """
    now = now or time.time()
    par_chemin = {str(Path(a["workdir"])): a for a in agents if a.get("workdir")}
    par_cle = {(a["project"], a["worktree"]): a for a in agents}
    par_nom: dict[str, list[dict]] = {}
    for a in agents:
        par_nom.setdefault(a["worktree"], []).append(a)
    finies: list[dict] = []

    def _sync(data):
        # Une seule fiche vivante par worktree : la plus récente. Les plus anciennes encore ouvertes
        # (relance dans le même worktree) sont closes.
        derniere: dict[tuple, dict] = {}
        for t in data["taches"]:
            derniere[(t["projet"], t["worktree"])] = t
        for t in data["taches"]:
            if t is not derniere[(t["projet"], t["worktree"])]:
                if t["statut"] in OUVERTS:
                    t["statut"], t["fin"] = "perdue", now
                continue
            a = _trouver(t, par_chemin, par_cle, par_nom)
            if a is None:
                if t["statut"] == "lancee":
                    if now - t["cree"] > DEMARRAGE_MAX:
                        t["statut"], t["fin"] = "perdue", now
                        finies.append({**t, "jamais_demarre": True})
                elif t["statut"] in OUVERTS:
                    # La fenêtre a disparu pendant le travail : fermée à la main, plantée ou PC redémarré.
                    # Une absence passagère (workmux qui répond à moitié) ne suffit pas à conclure.
                    t["absent"] = t.get("absent") or now
                    if now - t["absent"] >= ABSENCE_MAX:
                        t["statut"], t["fin"] = "perdue", now
                        t.pop("absent", None)
                        finies.append(dict(t))
                continue
            t.pop("absent", None)
            st = a["status"]
            if st in ("working", "untracked", "waiting", "silent"):
                # Un agent qui reprend après une consigne corrective (ou un redémarrage) rouvre sa
                # fiche : sa durée et ses jetons couvrent tout son travail, pas seulement le premier tour.
                # « silent » : programme vivant sans sortie depuis longtemps — ouvert, jamais terminé d'office.
                t["statut"] = {"waiting": "attente", "silent": "silencieuse"}.get(st, "en_cours")
                t["debut"] = t["debut"] or now
                t["fin"] = None
            elif st in ("done", "idle") and t["statut"] in OUVERTS:
                t["debut"] = t["debut"] or t["cree"]
                t["statut"], t["fin"] = "terminee", now
                finies.append(dict(t))

    store.update_json(FILE, _vide(), _sync)
    a_mesurer = [t for t in finies if not t.get("jamais_demarre")]
    if jetons_fn and a_mesurer:
        mesures = {}
        for t in a_mesurer:
            try:
                mesures[t["id"]] = jetons_fn(t)
            except Exception:  # noqa: BLE001 — la mesure est un plus, jamais un blocage
                mesures[t["id"]] = None

        def _jetons(data):
            for t in data["taches"]:
                if mesures.get(t["id"]):
                    t["jetons"] = mesures[t["id"]]

        store.update_json(FILE, _vide(), _jetons)
        for t in finies:
            t["jetons"] = mesures.get(t["id"])
    return finies


def reouvrir(projet: str, worktree: str) -> None:
    """Après un redémarrage du PC : la fiche de l'agent repris redevient ouverte."""

    def _open(data):
        for t in reversed(data["taches"]):
            if t["projet"] == projet and t["worktree"] == worktree:
                if t["statut"] == "perdue":
                    t["statut"], t["fin"] = "en_cours", None
                return

    store.update_json(FILE, _vide(), _open)


# --- Bilan ----------------------------------------------------------------------------------

def _total(j: dict | None) -> int:
    return int((j or {}).get("total") or 0)


def bilan(jours: float = 7, now: float | None = None) -> dict:
    """Ce que l'usine a produit sur la période : par fournisseur, par rôle et par modèle."""
    now = now or time.time()
    debut = now - jours * 86400
    fiches = [t for t in toutes() if t["cree"] >= debut]

    def _groupe(cle) -> dict:
        out: dict[str, dict] = {}
        for t in fiches:
            g = out.setdefault(cle(t) or "?", {"taches": 0, "terminees": 0, "perdues": 0, "minutes": 0.0,
                                               "jetons": 0, "pretes": 0, "corrections": 0})
            g["taches"] += 1
            if t["statut"] == "terminee":
                g["terminees"] += 1
                if t.get("debut") and t.get("fin"):
                    g["minutes"] += max(0.0, t["fin"] - t["debut"]) / 60
            elif t["statut"] == "perdue":
                g["perdues"] += 1
            g["jetons"] += _total(t.get("jetons"))
            if t.get("verdict") == "pret":
                g["pretes"] += 1
            elif t.get("verdict") == "corrections":
                g["corrections"] += 1
        return out

    a_relire = [t for t in fiches if t["statut"] == "terminee" and not t.get("revue") and t["role"] != "revue"
                and roles.ou_defaut(t["role"])["revue"] == "croisee" and not t.get("verdict")]
    return {
        "jours": jours, "total": len(fiches),
        "fournisseurs": _groupe(lambda t: t["agent"]),
        "roles": _groupe(lambda t: t["role"]),
        "modeles": _groupe(lambda t: t["modele"] or f"{t['agent']}-defaut"),
        "a_relire": a_relire,
    }


def fmt_jetons(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f} M"
    if n >= 1000:
        return f"{n / 1000:.0f} k"
    return str(n)


def texte_bilan(b: dict | None = None) -> str:
    b = b or bilan()
    if not b["total"]:
        return f"Aucune tâche lancée sur les {b['jours']:g} derniers jours."
    lines = [f"Bilan des {b['jours']:g} derniers jours : {b['total']} tâche(s) lancée(s)"]
    for titre, cle in (("PAR FOURNISSEUR", "fournisseurs"), ("PAR RÔLE", "roles"), ("PAR MODÈLE", "modeles")):
        lines += ["", titre]
        for nom, g in sorted(b[cle].items(), key=lambda kv: -kv[1]["taches"]):
            moy = f"{g['minutes'] / g['terminees']:.0f} min en moyenne" if g["terminees"] else "—"
            ligne = (f"  {nom:<14} {g['terminees']}/{g['taches']} terminée(s) · {moy} · "
                     f"{fmt_jetons(g['jetons'])} jetons")
            if g["perdues"]:
                ligne += f" · {g['perdues']} interrompue(s)"
            if g["pretes"] or g["corrections"]:
                ligne += f" · relecture : {g['pretes']} prête(s), {g['corrections']} à corriger"
            lines.append(ligne)
    if b["a_relire"]:
        lines += ["", "SANS CONTRE-RELECTURE"]
        for t in b["a_relire"][-10:]:
            lines.append(f"  {t['projet']} {t['issue']} ({t['agent']}, {t['role']})")
    return "\n".join(lines)
