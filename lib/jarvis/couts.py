"""Coût des tâches et plafonds de jetons.

1. **Équivalent API.** Tes agents tournent sur tes abonnements Claude et Codex : une tâche ne te coûte
   pas d'argent en plus, elle consomme du quota. Le montant affiché ici est ce qu'elle aurait coûté au
   tarif API public (champs prix_* de config/modeles.toml, avec leur source et leur date). C'est une mesure
   de poids, utile pour comparer et repérer les tâches qui dérapent ; ce n'est jamais une dépense. Les vraies
   dépenses restent dans budgets.py.
2. **Plafond de jetons par unité de travail** (projet, issue, rôle) : estimation × multiplicateur, ou valeur
   imposée dans le plan. Vérifié par l'admission avant chaque (re)lancement, et par le démon pendant le travail.

Les jetons d'une tâche se lisent dans les journaux des CLI (usage.task_tokens), sans rien envoyer nulle part.
"""

from __future__ import annotations

import statistics
import time

from . import config

REFERENCE = {"claude": "sonnet", "codex": "sol"}   # tarif utilisé quand le modèle d'une tâche est inconnu
CACHE_LECTURE = 0.1                                 # × prix d'entrée, quand le tarif du cache est inconnu
CACHE_ECRITURE = 1.25
TAILLES = ("S", "M", "L")


# --- Tarifs ------------------------------------------------------------------------------------

def tarif(agent: str, modele: str) -> dict:
    """Tarif applicable à une tâche : {"prix_in", "prix_out", "prix_cache_lecture", "prix_cache_ecriture",
    "estimation": bool, "modele": nom utilisé, "raison": pourquoi c'est une estimation}."""
    from . import modeles
    cat = modeles.catalogue()
    m = cat.get(modele or "")
    raisons = []
    if not m or m.get("prix_in") is None or m.get("prix_out") is None:
        ref = cat.get(REFERENCE.get(agent, ""))
        raisons.append(f"tarif de {modele or 'modèle par défaut'} inconnu : tarif de {REFERENCE.get(agent, '?')} utilisé")
        m = ref
    if not m or m.get("prix_in") is None or m.get("prix_out") is None:
        return {"prix_in": None, "prix_out": None, "prix_cache_lecture": None, "prix_cache_ecriture": None,
                "estimation": True, "modele": modele, "raison": "aucun tarif connu"}
    out = {"prix_in": m["prix_in"], "prix_out": m["prix_out"], "modele": m["nom"]}
    for cle, mult in (("prix_cache_lecture", CACHE_LECTURE), ("prix_cache_ecriture", CACHE_ECRITURE)):
        if m.get(cle) is None:
            out[cle] = m["prix_in"] * mult
            raisons.append(f"{cle.replace('prix_', '').replace('_', ' ')} estimé")
        else:
            out[cle] = m[cle]
    out["estimation"] = bool(raisons)
    out["raison"] = " ; ".join(raisons)
    return out


def cout_jetons(jetons: dict | None, agent: str, modele: str) -> dict:
    """{"usd": float | None, "estimation": bool, "raison": str} pour un relevé de jetons."""
    if not jetons:
        return {"usd": None, "estimation": True, "raison": "jetons inconnus"}
    t = tarif(agent, modele)
    if t["prix_in"] is None:
        return {"usd": None, "estimation": True, "raison": t["raison"]}
    usd = (int(jetons.get("entree") or 0) * t["prix_in"] + int(jetons.get("sortie") or 0) * t["prix_out"]
           + int(jetons.get("cache_lecture") or 0) * t["prix_cache_lecture"]
           + int(jetons.get("cache_ecriture") or 0) * t["prix_cache_ecriture"]) / 1_000_000
    return {"usd": usd, "estimation": t["estimation"], "raison": t["raison"]}


def jetons_fiche(fiche: dict, mesurer: bool = True) -> dict | None:
    """Jetons d'une fiche : relevé enregistré à la fin, sinon mesure en direct si `mesurer`."""
    if fiche.get("jetons"):
        return fiche["jetons"]
    if not mesurer:
        return None
    from . import usage
    try:
        return usage.task_tokens(fiche)
    except Exception:  # noqa: BLE001 — une mesure illisible n'empêche rien
        return None


def cout_fiche(fiche: dict, mesurer: bool = True) -> dict:
    j = jetons_fiche(fiche, mesurer)
    c = cout_jetons(j, fiche.get("agent", ""), fiche.get("modele", ""))
    c["jetons"] = int((j or {}).get("total") or 0)
    return c


# --- Monnaie -----------------------------------------------------------------------------------

def monnaie(usd: float | None) -> str:
    """« 3,42 € » si un taux est réglé (couts.devise, couts.taux), sinon « 3.42 $ US »."""
    if usd is None:
        return "—"
    cfg = config.settings().get("couts", {})
    devise, taux = str(cfg.get("devise") or "EUR").upper(), float(cfg.get("taux") or 0)
    if devise != "USD" and taux > 0:
        symbole = {"EUR": "€", "CAD": "$ CA", "GBP": "£"}.get(devise, devise)
        return f"{usd * taux:,.2f} {symbole}".replace(",", " ").replace(".", ",")
    return f"{usd:,.2f} $ US".replace(",", " ")


def note_monnaie() -> str:
    cfg = config.settings().get("couts", {})
    devise, taux = str(cfg.get("devise") or "EUR").upper(), float(cfg.get("taux") or 0)
    if devise != "USD" and taux <= 0:
        return f"Montants en dollars US : aucun taux {devise} réglé (jarvis regler couts.taux 0.86, par exemple)."
    return ""


# --- Agrégats ----------------------------------------------------------------------------------

def _periode(texte: str) -> float:
    """« 7j », « 24h », « 30j » → secondes."""
    t = (texte or "7j").strip().lower()
    try:
        if t.endswith("h"):
            return float(t[:-1]) * 3600
        return float(t.rstrip("j").rstrip("d")) * 86400
    except ValueError:
        raise ValueError(f"période illisible « {texte} » (ex. 24h, 7j, 30j)") from None


def tableau(fiches: list[dict], mesurer_ouvertes: bool = True) -> list[dict]:
    from . import taches
    out = []
    for t in fiches:
        ouverte = t["statut"] in taches.OUVERTS
        c = cout_fiche(t, mesurer=mesurer_ouvertes and ouverte)
        out.append({"id": t["id"], "projet": t["projet"], "issue": t["issue"], "role": t.get("role", ""),
                    "agent": t["agent"], "modele": t.get("modele") or f"{t['agent']}-defaut", "statut": t["statut"],
                    "cree": t["cree"], **c})
    return out


def par_projet(projet: str, periode: str = "7j", now: float | None = None) -> dict:
    from . import taches
    now = now or time.time()
    debut = now - _periode(periode)
    lignes = tableau([t for t in taches.toutes() if t["projet"] == projet and t["cree"] >= debut])
    total = sum(x["usd"] or 0 for x in lignes)
    return {"projet": projet, "periode": periode, "lignes": lignes, "usd": total,
            "jetons": sum(x["jetons"] for x in lignes),
            "estimation": any(x["estimation"] for x in lignes), "inconnus": sum(1 for x in lignes if x["usd"] is None)}


def semaine(n: int = 10, now: float | None = None) -> dict:
    from . import taches
    now = now or time.time()
    lignes = tableau([t for t in taches.toutes() if t["cree"] >= now - 7 * 86400])
    projets: dict[str, float] = {}
    for x in lignes:
        projets[x["projet"]] = projets.get(x["projet"], 0.0) + (x["usd"] or 0)
    return {"lignes": sorted(lignes, key=lambda x: -(x["usd"] or 0))[:n], "usd": sum(x["usd"] or 0 for x in lignes),
            "jetons": sum(x["jetons"] for x in lignes), "projets": projets,
            "estimation": any(x["estimation"] for x in lignes)}


# --- Plafonds de jetons ------------------------------------------------------------------------

def _cfg_jetons() -> dict:
    return config.settings().get("budget_jetons", {})


def estimation(role: str, taille: str, now: float | None = None) -> tuple[int, str]:
    """(jetons estimés pour une tâche, d'où vient l'estimation).

    Médiane des tâches terminées de même rôle et taille sur 60 jours s'il y en a au moins 5 ; sinon la valeur
    par défaut du réglage budget_jetons.estimation_<taille>.
    """
    from . import roles, taches
    now = now or time.time()
    taille = (taille or "M").upper()
    role = roles.ou_defaut(role)["nom"]
    totaux = [int(t["jetons"]["total"]) for t in taches.toutes()
              if t.get("role") == role and (t.get("taille") or "M") == taille and t["statut"] == "terminee"
              and (t.get("jetons") or {}).get("total") and now - t["cree"] < 60 * 86400]
    if len(totaux) >= 5:
        return int(statistics.median(totaux)), f"médiane de {len(totaux)} tâches {role}/{taille} terminées"
    defaut = int(_cfg_jetons().get(f"estimation_{taille.lower()}", 800_000))
    return defaut, f"valeur par défaut pour la taille {taille}"


def plafond_defaut(role: str, taille: str, now: float | None = None) -> tuple[int, str]:
    est, source = estimation(role, taille, now)
    mult = float(_cfg_jetons().get("multiplicateur", 3))
    return int(est * mult), f"{mult:g} × {est:,} ({source})".replace(",", " ")


def compteur_unite(projet: str, issue: str, role: str, mesurer: bool = True) -> int:
    """Jetons déjà consommés par l'unité de travail (projet, issue, rôle), toutes relances comprises."""
    from . import taches
    return sum(int((jetons_fiche(t, mesurer=mesurer and t["statut"] in taches.OUVERTS) or {}).get("total") or 0)
               for t in taches.unite(projet, issue, role))


def fmt_jetons(n: int) -> str:
    from . import taches
    return taches.fmt_jetons(int(n or 0))
