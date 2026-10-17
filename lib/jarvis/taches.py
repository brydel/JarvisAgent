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

# Classes d'échec d'un essai. « quota » et « bloque » se constatent seuls (démon) ; les trois autres se
# déclarent (chef, relecteur, humain) : les deviner dans la sortie d'un agent ne serait pas fiable.
CLASSES_ECHEC = {
    "bloque": "attend l'humain",
    "erreur_outil": "outil ou environnement en échec",
    "hors_perimetre": "sorti du périmètre de l'issue",
    "quota": "jetons du fournisseur épuisés",
    "regression": "a cassé ce qui marchait",
}
CLASSES_AUTO = ("bloque", "quota")
# Après l'un de ces échecs, le 2e essai doit changer d'approche (modèle, fournisseur ou consignes).
CHANGER_APRES = ("erreur_outil", "hors_perimetre", "regression")
ESSAIS_AUTO = 2          # au-delà : escalade, un humain débloque un essai de plus
ESCALADES = "escalades.json"


def _vide() -> dict:
    return {"seq": 0, "taches": []}


def toutes() -> list[dict]:
    return store.read_json(FILE, _vide())["taches"]


def enregistrer(*, projet: str, issue: str, agent: str, worktree: str, chemin: str = "", role: str = "",
                modele: str = "", modele_id: str = "", effort: str = "", repli: str = "", taille: str = "M",
                plan: str = "", revue: str = "", raison: str = "", secours: bool = False, classe: str = "",
                reservation: str = "", jetons_max: int = 0, consignes_empreinte: str = "") -> dict:
    """Crée la fiche d'un lancement. `chemin` : dossier du worktree (clé des lanceurs).

    `jetons_max` : plafond de jetons de l'unité de travail (projet, issue, rôle), toutes relances comprises.
    `consignes_empreinte` : empreinte du fichier de consignes, pour savoir si un nouvel essai change d'approche.
    """
    chemin = str(Path(chemin).resolve()) if chemin else ""
    role_nom = roles.ou_defaut(role)["nom"]

    def _add(data):
        data["seq"] += 1
        precedents = _essais_comptes([t for t in data["taches"] if _cle(t) == (projet, issue.upper(), role_nom)])
        fiche = {
            "id": f"T-{data['seq']:05d}", "projet": projet, "issue": issue.upper(), "agent": agent,
            "role": roles.ou_defaut(role)["nom"], "modele": modele, "modele_id": modele_id, "effort": effort,
            "repli": repli, "taille": taille, "plan": plan, "revue": str(revue or ""), "raison": raison,
            "secours": bool(secours), "worktree": worktree, "chemin": chemin, "statut": "lancee",
            "classe": classe, "reservation": reservation, "jetons_max": int(jetons_max or 0),
            "consignes_empreinte": consignes_empreinte, "essai": len(precedents) + 1, "echec": None,
            "cree": time.time(), "debut": None, "fin": None, "jetons": None, "verdict": "", "verdict_note": "",
        }
        data["taches"].append(fiche)
        data["taches"] = data["taches"][-MAX:]
        return dict(fiche)

    fiche = store.update_json(FILE, _vide(), _add)
    from . import evenements
    evenements.sans_echec(fiche["id"], "lance", ts=fiche["cree"], projet=projet, issue=fiche["issue"], role=fiche["role"],
                          agent=agent, modele=modele, plan=plan, essai=fiche["essai"], jetons_max=fiche["jetons_max"] or None)
    return fiche


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

    t = store.update_json(FILE, _vide(), _set)
    if t:
        from . import evenements
        evenements.sans_echec(t["id"], "verdict", verdict=verdict, note=note.strip()[:120] or None)
    return t


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
    transitions: list[tuple] = []

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
                    finies.append(dict(t))  # remplacée par une relance : ses jetons sont mesurés quand même
                continue
            a = _trouver(t, par_chemin, par_cle, par_nom)
            if a is None:
                if t["statut"] == "lancee":
                    if now - t["cree"] > DEMARRAGE_MAX:
                        t["statut"], t["fin"], t["jamais_demarre"] = "perdue", now, True
                        finies.append(dict(t))
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
            avant = t["statut"]
            if st in ("working", "untracked", "waiting", "silent"):
                # Un agent qui reprend après une consigne corrective (ou un redémarrage) rouvre sa
                # fiche : sa durée et ses jetons couvrent tout son travail, pas seulement le premier tour.
                # « silent » : programme vivant sans sortie depuis longtemps — ouvert, jamais terminé d'office.
                t["statut"] = {"waiting": "attente", "silent": "silencieuse"}.get(st, "en_cours")
                t["debut"] = t["debut"] or now
                t["fin"] = None
                # L'agent est reparti : une classe constatée par le démon (bloqué, quota) n'est plus d'actualité.
                if st != "waiting" and (t.get("echec") or {}).get("source") == "auto":
                    t["echec"] = None
            elif st in ("done", "idle") and t["statut"] in OUVERTS:
                t["debut"] = t["debut"] or t["cree"]
                t["statut"], t["fin"] = "terminee", now
                finies.append(dict(t))
            if t["statut"] != avant:
                transitions.append((t["id"], avant, t["statut"]))

    store.update_json(FILE, _vide(), _sync)
    from . import evenements
    for tid, avant, apres in transitions:
        if apres == "attente":
            evenements.sans_echec(tid, "tour_agent", ts=now, etat="attend une réponse")
        elif apres == "terminee":
            evenements.sans_echec(tid, "tour_agent", ts=now, etat="a fini son tour")
        elif apres in ("en_cours", "silencieuse") and avant in ("attente", "perdue", "terminee"):
            evenements.sans_echec(tid, "reprise", ts=now, depuis=avant)
    for t in finies:
        evenements.sans_echec(t["id"], "termine" if t["statut"] == "terminee" else "perdue", ts=now,
                              jamais_demarre=True if t.get("jamais_demarre") else None)
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


# --- Unités de travail, essais, échecs -------------------------------------------------------

def _cle(t: dict) -> tuple:
    """Unité de travail : même projet, même issue, même rôle. Une relance continue la même unité."""
    return (t["projet"], t["issue"], t.get("role") or "generaliste")


def unite(projet: str, issue: str, role: str, liste: list[dict] | None = None) -> list[dict]:
    """Fiches de l'unité (projet, issue, rôle), de la plus ancienne à la plus récente."""
    liste = toutes() if liste is None else liste
    cle = (projet, issue.upper(), roles.ou_defaut(role)["nom"])
    return [t for t in liste if _cle(t) == cle]


def echoue(t: dict) -> bool:
    """Essai sans succès : interrompu, échec déclaré, ou corrections demandées par la relecture."""
    e = t.get("echec") or {}
    return (t["statut"] == "perdue" or (e and e.get("source") == "declare") or t.get("verdict") == "corrections")


def _essais_comptes(fiches: list[dict]) -> list[dict]:
    """Essais qui comptent pour la borne : ceux en cours et ceux qui n'ont pas abouti. Ne comptent pas :
    les lancements jamais démarrés, les arrêts pour quota (c'est l'abonnement qui s'est vidé, pas l'agent qui
    a échoué) et les essais terminés sans échec (une nouvelle demande sur la même issue n'est pas une reprise)."""
    out = []
    for t in fiches:
        if t.get("jamais_demarre") or (t.get("echec") or {}).get("classe") == "quota":
            continue
        if t["statut"] in OUVERTS or echoue(t):
            out.append(t)
    return out


def en_vol(projet: str, issue: str, role: str, liste: list[dict] | None = None) -> dict | None:
    """Essai de cette unité encore ouvert (un seul à la fois par unité de travail)."""
    return next((t for t in unite(projet, issue, role, liste) if t["statut"] in OUVERTS), None)


def autorisations(projet: str, issue: str, role: str) -> int:
    cle = f"{projet}:{issue.upper()}:{roles.ou_defaut(role)['nom']}"
    return int((store.read_json(ESCALADES, {}).get(cle) or {}).get("autorise", 0))


def autoriser_essai(projet: str, issue: str, role: str, par: str, note: str = "") -> int:
    """Un humain débloque UN essai de plus après une escalade. Renvoie le nombre d'essais autorisés au total."""
    cle = f"{projet}:{issue.upper()}:{roles.ou_defaut(role)['nom']}"

    def _maj(data):
        e = data.setdefault(cle, {"autorise": 0, "historique": []})
        e["autorise"] = int(e.get("autorise", 0)) + 1
        e["historique"] = (e.get("historique") or [])[-20:] + [{"ts": time.time(), "par": par, "note": note[:200]}]
        return ESSAIS_AUTO + e["autorise"]

    total = store.update_json(ESCALADES, {}, _maj)
    try:
        from . import journal
        journal.ecrire("relance", acteur=par, objet=cle, decision="essai_autorise", raison=note or f"{total} essais autorisés")
    except Exception:  # noqa: BLE001
        pass
    return total


def verifier_reprise(projet: str, issue: str, role: str, *, agent: str = "", modele: str = "",
                     consignes_empreinte: str = "", liste: list[dict] | None = None) -> tuple[str, str] | None:
    """Borne de reprise d'une unité de travail. None si le lancement peut partir, sinon (code, raison).

    - 3e essai (ou au-delà des essais débloqués par un humain) : « escalade » ;
    - 2e essai après un échec d'outil, de périmètre ou une régression, avec la même approche (même
      fournisseur, même modèle, mêmes consignes) : « meme_approche ». Vérifié seulement quand le modèle est
      connu (lancement par plan) ; un humain qui lance à la main décide lui-même.
    """
    fiches = unite(projet, issue, role, liste)
    comptes = _essais_comptes(fiches)
    maxi = ESSAIS_AUTO + autorisations(projet, issue, role)
    if len(comptes) >= maxi:
        resume = ", ".join(f"{t['id']} ({(t.get('echec') or {}).get('classe') or STATUTS.get(t['statut'], t['statut'])})"
                           for t in comptes[-3:])
        return ("escalade", f"{projet} {issue} [{roles.ou_defaut(role)['nom']}] : {len(comptes)} essai(s) déjà faits "
                            f"({resume}). Pas d'essai automatique de plus : le chef expose le problème à ton humain, "
                            f"qui peut débloquer un essai (jarvis tache relancer {comptes[-1]['id']} --autoriser).")
    if len(comptes) >= 1 and modele:
        dernier = comptes[-1]
        classe = (dernier.get("echec") or {}).get("classe")
        if classe in CHANGER_APRES and (dernier.get("agent"), dernier.get("modele") or "",
                                        dernier.get("consignes_empreinte") or "") == (agent, modele, consignes_empreinte):
            return ("meme_approche", f"{dernier['id']} a échoué ({CLASSES_ECHEC[classe]}) avec {agent}/{modele} et les "
                                     "mêmes consignes : change de modèle, de fournisseur ou de consignes avant un 2e essai.")
    return None


def classer(tache_id: str, classe: str, *, source: str = "declare", par: str = "", note: str = "",
            remplacer: bool = True) -> dict | None:
    """Classe l'échec d'un essai. Une classe déclarée remplace une classe automatique, jamais l'inverse."""
    if classe not in CLASSES_ECHEC:
        raise ValueError(f"classe inconnue « {classe} » (valeurs : {', '.join(CLASSES_ECHEC)})")
    if source != "auto" and classe in CLASSES_AUTO:
        # Sinon déclarer « quota » sur deux échecs suffirait à contourner la borne des essais.
        raise ValueError(f"« {classe} » est constaté par le démon, il ne se déclare pas "
                         f"(classes déclarables : {', '.join(c for c in CLASSES_ECHEC if c not in CLASSES_AUTO)})")

    def _set(data):
        for t in data["taches"]:
            if t["id"] != tache_id.upper():
                continue
            actuel = t.get("echec") or {}
            if actuel and (not remplacer or (source == "auto" and actuel.get("source") == "declare")):
                return None
            t["echec"] = {"classe": classe, "source": source, "par": par, "note": note.strip()[:300], "ts": time.time()}
            return dict(t)
        raise ValueError(f"tâche {tache_id} introuvable")

    t = store.update_json(FILE, _vide(), _set)
    if t:
        from . import evenements
        evenements.sans_echec(t["id"], "echec", classe=classe, source=source, par=par or None, note=note[:120] or None)
        store.feed_add("erreur" if classe != "bloque" else "question",
                       f"{t['projet']} {t['issue']} ({t['id']}) : {CLASSES_ECHEC[classe]}" + (f" — {note}" if note else ""))
    return t


def get(tache_id: str) -> dict | None:
    return next((t for t in toutes() if t["id"] == tache_id.upper()), None)


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
