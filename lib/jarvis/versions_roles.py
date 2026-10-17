"""Versions des briefs de rôles : proposition, essai progressif (canari), retrait automatique, promotion humaine.

Le brief d'un rôle (`roles/<rôle>.md`) façonne tout ce que fait un agent : le changer est une décision de niveau 3
(politique « protection »), jamais automatique.

1. `proposer` : un brief candidat (de l'optimiseur `outils/optimiser_prompts.py`, du chef ou de toi) est enregistré
   avec ses scores. Refusé s'il perd une règle exigée par les cas d'évaluation du rôle (tests/goldens) ou s'il
   touche à l'en-tête du rôle (fournisseur, niveau…) : seul le texte du brief peut changer. Telegram : boutons.
2. `decider(ok)` (ton clic, ou `jarvis role approuver`) : le candidat part en **canari** — un pourcentage des
   unités de travail du rôle (10 % par défaut, `optimisation.canari_pct`), choisies de façon déterministe par
   (projet, issue, rôle) : une relance garde la même version. La fiche de tâche note la version reçue (`brief`).
3. `surveiller` (démon, toutes les heures) : si le taux d'échec du candidat dépasse celui de la version stable
   de 25 points sur au moins 3 tâches finies, **retour automatique à la version stable** (c'est revenir à ce que
   tu as déjà approuvé). Si le brief stable change pendant l'essai, le candidat est périmé.
4. `promouvoir` (toi seulement) : le candidat devient le brief du rôle, écrit dans ~/.config/jarvis/roles/
   (le dépôt n'est pas modifié ; l'ancien fichier personnel est sauvegardé).
"""

from __future__ import annotations

import difflib
import hashlib
import time
import zlib
from pathlib import Path

from . import config, roles, store

FILE = "roles_versions.json"
EN_COURS = ("proposee", "canari")
MIN_TACHES = 3
ECART_RETRAIT = 0.25


class VersionError(ValueError):
    pass


def _vide() -> dict:
    return {"seq": 0, "propositions": []}


def empreinte(corps: str) -> str:
    return hashlib.sha256(corps.strip().encode("utf-8")).hexdigest()[:12]


def candidats_dir() -> Path:
    return config.DATA_DIR / "roles-candidats"


def toutes() -> list[dict]:
    return store.read_json(FILE, _vide())["propositions"]


def get(prop_id: str) -> dict | None:
    return next((p for p in toutes() if p["id"] == prop_id.upper()), None)


def corps_candidat(p: dict) -> str:
    return Path(p["fichier"]).read_text(encoding="utf-8")


def _corps_seul(texte: str) -> tuple[str, str]:
    """(en-tête « --- … --- » ou "", corps) d'un fichier de rôle complet ou d'un simple brief."""
    if texte.startswith("---"):
        head, sep, rest = texte[3:].partition("\n---")
        if sep:
            return head.strip(), rest.lstrip("\n").strip()
    return "", texte.strip()


def _entete_stable(role: dict) -> str:
    try:
        return _corps_seul(Path(role["source"]).read_text(encoding="utf-8"))[0]
    except OSError:
        return ""


def controler(role_nom: str, corps: str) -> list[str]:
    """Raisons de refus d'un brief candidat (liste vide = acceptable)."""
    from . import evaluation
    raisons = []
    if len(corps.strip()) < 80:
        raisons.append("brief vide ou presque")
    for c in evaluation.cas_tous(role_nom):
        manquantes = evaluation.exigences_manquantes(c, corps=corps)
        if manquantes:
            raisons.append(f"perd des règles exigées par {c['nom']} : {', '.join(manquantes)}")
    return raisons


def proposer(role_nom: str, texte: str, pourquoi: str, *, scores: dict | None = None, par: str = "chef",
             source: str = "") -> dict:
    role = roles.get(role_nom)
    if not role:
        raise VersionError(f"rôle inconnu « {role_nom} »")
    entete, corps = _corps_seul(texte)
    if entete and entete != _entete_stable(role):
        raise VersionError("l'en-tête du rôle (fournisseur, niveau, équipe…) ne change pas ici : seul le brief peut changer")
    if empreinte(corps) == empreinte(role["corps"]):
        raise VersionError("le candidat est identique au brief actuel")
    raisons = controler(role["nom"], corps)
    if raisons:
        raise VersionError("candidat refusé : " + " ; ".join(raisons))
    if not pourquoi.strip():
        raise VersionError("--pourquoi est obligatoire : ton humain doit savoir ce que le candidat améliore")

    def _add(data):
        if any(p["role"] == role["nom"] and p["statut"] in EN_COURS for p in data["propositions"]):
            raise VersionError(f"un candidat pour {role['nom']} est déjà en attente ou en essai (jarvis role candidats)")
        data["seq"] += 1
        pid = f"RB-{data['seq']:04d}"
        fichier = candidats_dir() / f"{pid}-{role['nom']}.md"
        fichier.parent.mkdir(parents=True, exist_ok=True)
        fichier.write_text(corps + "\n", encoding="utf-8")
        p = {"id": pid, "role": role["nom"], "statut": "proposee", "ts": time.time(), "par": par, "source": source,
             "pourquoi": pourquoi.strip()[:800], "scores": scores or {}, "base": empreinte(role["corps"]),
             "empreinte": empreinte(corps), "fichier": str(fichier), "pct": 0}
        data["propositions"].append(p)
        data["propositions"] = data["propositions"][-200:]
        return dict(p)

    p = store.update_json(FILE, _vide(), _add)
    _journal(par, p, "propose", pourquoi)
    from . import notify
    notify.telegram(texte_proposition(p, role["corps"], corps), notify.role_buttons(p["id"]))
    return p


def texte_proposition(p: dict, ancien: str, nouveau: str, max_lignes: int = 40) -> str:
    diff = list(difflib.unified_diff(ancien.splitlines(), nouveau.splitlines(), "actuel", "candidat", lineterm="", n=1))
    coupe = diff[:max_lignes] + ([f"… ({len(diff) - max_lignes} lignes de plus : jarvis role candidats {p['id']})"]
                                 if len(diff) > max_lignes else [])
    s = p.get("scores") or {}
    scores = (f"\nScores (cas réussis) : stable {s.get('stable_entrainement', '?')} → candidat "
              f"{s.get('candidat_entrainement', '?')} ; cas protégés : stable {s.get('stable_protege', '?')} → candidat "
              f"{s.get('candidat_protege', '?')}") if s else "\nAucun score d'évaluation fourni."
    return (f"🧠 Brief candidat {p['id']} pour le rôle {p['role']} (par {p['par']})\nPourquoi : {p['pourquoi']}{scores}\n"
            f"Si tu approuves : essai sur {_pct()} % des tâches {p['role']}, retour automatique au brief actuel en cas "
            f"de régression.\n\n" + "\n".join(coupe))


def _pct() -> int:
    try:
        return max(1, min(50, int(config.settings().get("optimisation", {}).get("canari_pct", 10))))
    except (TypeError, ValueError):
        return 10


def _maj(prop_id: str, attendu: tuple, **champs) -> dict:
    def _set(data):
        for p in data["propositions"]:
            if p["id"] == prop_id.upper():
                if p["statut"] not in attendu:
                    raise VersionError(f"{p['id']} est « {p['statut']} » : action impossible")
                p.update(champs)
                return dict(p)
        raise VersionError(f"proposition {prop_id} introuvable")
    return store.update_json(FILE, _vide(), _set)


def decider(prop_id: str, ok: bool, par: str) -> dict:
    if ok:
        p = get(prop_id)
        role = roles.get(p["role"]) if p else None
        if p and role and empreinte(role["corps"]) != p["base"]:
            _maj(prop_id, ("proposee",), statut="perimee", fin=time.time())
            raise VersionError("le brief du rôle a changé depuis la proposition : candidat périmé")
        p = _maj(prop_id, ("proposee",), statut="canari", pct=_pct(), debut_canari=time.time(), decide_par=par)
    else:
        p = _maj(prop_id, ("proposee",), statut="refusee", fin=time.time(), decide_par=par)
    _journal(par, p, "canari" if ok else "refuse")
    return p


def retirer(prop_id: str, par: str, raison: str = "") -> dict:
    p = _maj(prop_id, EN_COURS, statut="retiree", fin=time.time(), retire_par=par, raison_retrait=raison[:300])
    _journal(par, p, "retire", raison)
    return p


def promouvoir(prop_id: str, par: str) -> dict:
    """Le candidat devient le brief du rôle (fichier personnel ~/.config/jarvis/roles/<rôle>.md)."""
    p = get(prop_id)
    if not p or p["statut"] != "canari":
        raise VersionError("seul un candidat en essai (canari) peut être promu")
    role = roles.get(p["role"])
    if empreinte(role["corps"]) != p["base"]:
        raise VersionError("le brief du rôle a changé pendant l'essai : candidat périmé, rien n'est écrit")
    entete = _entete_stable(role)
    cible = roles.ROLES_PERSO / f"{role['nom']}.md"
    cible.parent.mkdir(parents=True, exist_ok=True)
    if cible.exists():
        cible.rename(cible.with_name(f"{cible.name}.bak.{time.strftime('%Y%m%d-%H%M%S')}"))
    cible.write_text((f"---\n{entete}\n---\n\n" if entete else "") + corps_candidat(p).strip() + "\n", encoding="utf-8")
    p = _maj(prop_id, ("canari",), statut="promue", fin=time.time(), promu_par=par, ecrit=str(cible))
    _journal(par, p, "promu", str(cible))
    return p


def actif(role_nom: str) -> dict | None:
    """Le candidat en canari du rôle, s'il est toujours bâti sur le brief stable actuel."""
    role = roles.get(role_nom)
    if not role:
        return None
    for p in toutes():
        if p["role"] == role["nom"] and p["statut"] == "canari" and p["base"] == empreinte(role["corps"]):
            return p
    return None


def choisir(role_nom: str, projet: str, issue: str) -> tuple[str, str | None]:
    """("stable", None) ou ("candidat:RB-0001", corps). Déterministe par unité de travail."""
    p = actif(role_nom)
    if not p:
        return "stable", None
    tirage = zlib.crc32(f"{projet}:{issue.upper()}:{p['role']}".encode("utf-8")) % 100
    if tirage >= int(p.get("pct") or 0):
        return "stable", None
    try:
        return f"candidat:{p['id']}", corps_candidat(p).strip()
    except OSError:
        return "stable", None


def bilan(p: dict) -> dict:
    """Tâches du rôle finies depuis le début de l'essai : {stable: (n, échecs), candidat: (n, échecs)}."""
    from . import taches
    out = {"stable": [0, 0], "candidat": [0, 0]}
    for t in taches.toutes():
        if t.get("role") != p["role"] or t["cree"] < p.get("debut_canari", 1e18) or t["statut"] not in ("terminee", "perdue"):
            continue
        if t.get("jamais_demarre") or (t.get("echec") or {}).get("classe") == "quota":
            continue  # abonnement vidé ou lancement avorté : le brief n'y est pour rien
        cote = "candidat" if t.get("brief") == f"candidat:{p['id']}" else "stable"
        out[cote][0] += 1
        out[cote][1] += int(taches.echoue(t))
    return out


def surveiller(now: float | None = None) -> list[dict]:
    """Retire les candidats qui régressent ou dont la base a changé. Renvoie les retraits."""
    retraits = []
    for p in toutes():
        if p["statut"] != "canari":
            continue
        role = roles.get(p["role"])
        if not role or empreinte(role["corps"]) != p["base"]:
            retraits.append(_maj(p["id"], ("canari",), statut="perimee", fin=time.time()))
            continue
        b = bilan(p)
        (n_c, e_c), (n_s, e_s) = b["candidat"], b["stable"]
        if n_c < MIN_TACHES:
            continue
        taux_c, taux_s = e_c / n_c, (e_s / n_s if n_s else 0.0)
        if taux_c - taux_s >= ECART_RETRAIT:
            retraits.append(retirer(p["id"], par="demon", raison=f"régression : {e_c}/{n_c} échecs contre {e_s}/{n_s} "
                                                                  "avec le brief stable"))
    if retraits:
        from . import notify
        notify.alert("erreur", "Brief candidat retiré, retour au brief stable : "
                     + ", ".join(f"{p['id']} ({p['role']}, {p['statut']})" for p in retraits))
    return retraits


def _journal(acteur: str, p: dict, decision: str, raison: str = "") -> None:
    try:
        from . import journal
        journal.ecrire("politique", acteur=acteur, objet=f"role:{p['role']}:{p['id']}", decision=decision,
                       raison=raison[:300], action="protection")
    except Exception:  # noqa: BLE001
        pass


def texte(liste: list[dict] | None = None) -> str:
    liste = toutes() if liste is None else liste
    if not liste:
        return "Aucun brief candidat."
    out = []
    for p in reversed(liste[-20:]):
        ligne = (f"{p['id']}  {p['role']:<12} {p['statut']:<9} {time.strftime('%d/%m', time.localtime(p['ts']))}"
                 f"  par {p['par']} — {p['pourquoi'][:70]}")
        if p["statut"] == "canari":
            b = bilan(p)
            ligne += (f"\n        essai {p['pct']} % : candidat {b['candidat'][1]}/{b['candidat'][0]} échecs, "
                      f"stable {b['stable'][1]}/{b['stable'][0]}")
        out.append(ligne)
    return "\n".join(out)
