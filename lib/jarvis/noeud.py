"""Noeud GPU (Jetson) : une extension de Jarvis, pas un second Jarvis.

La Jetson n'a ni base, ni Board, ni chef, ni agent : elle expose des outils GPU (transcription…) par un serveur
MCP stdio joint en SSH, avec une clé dédiée limitée à une commande forcée (services/noeud_jetson). Jarvis l'appelle
comme toute connexion MCP : par la passerelle d'outils, sous mandat, avec un identifiant d'opération stable et une
trace au journal. Les fichiers lourds (audio du Board) sont déposés à part, désignés ensuite par leur empreinte :
une session MCP stdio est bornée à 30 s et ses messages à 1 Mo.

Désactivé par défaut : `jarvis noeud config <utilisateur@hote>` le branche, `jarvis regler noeud.actif false`
le coupe. Une panne du noeud n'arrête rien : l'appelant retombe sur ce qu'il faisait sans lui.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import subprocess
import time
from pathlib import Path

from . import config

OUTILS_BOARD = ("audio_transcrire", "audio_resultat")
OUTILS = OUTILS_BOARD + ("noeud_sante",)
PROJET_BOARD = "jarvis-board"
ATTENTE_S = 15
TEXTE_MAX = 200_000


class NoeudError(RuntimeError):
    pass


def reglages() -> dict:
    return dict(config.settings().get("noeud") or {})


def active(r: dict | None = None) -> tuple[bool, str]:
    r = r or reglages()
    if not r.get("actif"):
        return False, "noeud GPU désactivé (jarvis noeud config)"
    if not r.get("cible") or not r.get("mandat_board"):
        return False, "noeud GPU incomplet : relance jarvis noeud config"
    return True, ""


def cle(r: dict | None = None) -> Path:
    r = r or reglages()
    return Path(r.get("cle") or Path.home() / ".ssh" / "jarvis_noeud_ed25519")


def commande_ssh(r: dict, *distant: str, hote_connu: bool = True) -> list[str]:
    """Commande complète vers le noeud ; `distant` est validé par la commande forcée côté Jetson."""
    return [r.get("commande") or "/usr/bin/ssh", "-T", "-i", str(cle(r)), "-o", "IdentitiesOnly=yes",
            "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=15",
            "-o", "StrictHostKeyChecking=" + ("yes" if hote_connu else "accept-new"), "--", r["cible"], *distant]


def _json(sortie: str) -> dict:
    try:
        data = json.loads(sortie.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise NoeudError("réponse du noeud illisible") from None
    if not isinstance(data, dict):
        raise NoeudError("réponse du noeud inattendue")
    if data.get("erreur"):
        raise NoeudError(f"noeud : {str(data['erreur'])[:200]}")
    return data


def sante(r: dict | None = None, *, hote_connu: bool = True) -> dict:
    r = r or reglages()
    try:
        p = subprocess.run(commande_ssh(r, "sante", hote_connu=hote_connu), capture_output=True, text=True,
                           timeout=30, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise NoeudError(f"noeud injoignable ({type(exc).__name__})") from None
    if p.returncode == 255:
        raise NoeudError("connexion SSH refusée ou noeud injoignable (clé autorisée ? noeud allumé ?)")
    return _json(p.stdout)


def deposer(chemin: Path, *, delai: float, r: dict | None = None) -> str:
    """Envoie un fichier dans la file d'entrée du noeud ; renvoie son empreinte, vérifiée côté noeud."""
    r = r or reglages()
    h = hashlib.sha256()
    with chemin.open("rb") as fh:
        for bloc in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(bloc)
    sha, taille = h.hexdigest(), chemin.stat().st_size
    try:
        with chemin.open("rb") as fh:
            p = subprocess.run(commande_ssh(r, "depot", sha, str(taille)), stdin=fh, capture_output=True,
                               timeout=max(30.0, delai))
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise NoeudError(f"envoi du fichier au noeud impossible ({type(exc).__name__})") from None
    if p.returncode == 255:
        raise NoeudError("connexion SSH refusée ou noeud injoignable")
    _json(p.stdout.decode("utf-8", "replace"))
    return sha


def appeler(outil: str, arguments: dict, *, operation_id: str, r: dict | None = None) -> dict:
    """Un appel d'outil du noeud par la passerelle, sous le mandat du Board. Lève NoeudError."""
    from . import outils
    r = r or reglages()
    try:
        op = outils.executer({"operation_id": operation_id, "mandat_id": r["mandat_board"], "project": PROJET_BOARD,
                              "tool": f"mcp.{r['connexion']}.{outil}", "arguments": arguments, "cost_cents": 0},
                             par="jarvis:noeud")
    except ValueError as exc:
        raise NoeudError(str(exc)[:200]) from None
    resultat = op.get("resultat") or {}
    data = resultat.get("structuredContent") if isinstance(resultat, dict) else None
    if not isinstance(data, dict):
        try:
            data = json.loads(resultat["content"][0]["text"])
        except (KeyError, IndexError, TypeError, ValueError):
            data = {}
    if op.get("status") != "succeeded":
        raise NoeudError(str(data.get("erreur") or op.get("erreur") or "appel du noeud refusé ou incertain")[:200])
    return data


def transcrire(chemin: Path, *, cle_operation: str, verifier=None, r: dict | None = None) -> dict:
    """Audio → {texte, langue, duree_audio_s, duree_traitement_s, modele}. `verifier()` lève si la tâche est annulée."""
    r = r or reglages()
    ok, raison = active(r)
    if not ok:
        raise NoeudError(raison)
    echeance = time.monotonic() + float(r.get("delai_s") or 900)
    sha = deposer(chemin, delai=echeance - time.monotonic(), r=r)
    travail = appeler("audio_transcrire", {"fichier": sha, "langue": str(r.get("langue") or "fr")},
                      operation_id=f"{cle_operation}:soumettre", r=r)
    ident = travail.get("id")
    if not isinstance(ident, str):
        raise NoeudError("le noeud n'a pas rendu d'identifiant de travail")
    for n in range(1, 10_000):
        if verifier:
            verifier()
        etat = travail if travail.get("statut") in ("termine", "echec") else appeler(
            "audio_resultat", {"travail": ident, "attente_s": ATTENTE_S}, operation_id=f"{cle_operation}:resultat:{n}", r=r)
        if etat.get("statut") == "termine":
            res = etat.get("resultat") or {}
            nombre = lambda v: v if isinstance(v, (int, float)) and not isinstance(v, bool) else None  # noqa: E731
            return {"texte": str(res.get("texte") or "").strip()[:TEXTE_MAX], "langue": str(res.get("langue") or "")[:8],
                    "duree_audio_s": nombre(res.get("duree_audio_s")), "modele": str(res.get("modele") or "")[:40],
                    "duree_traitement_s": nombre(res.get("duree_traitement_s"))}
        if etat.get("statut") == "echec":
            raise NoeudError(f"transcription refusée par le noeud : {str(etat.get('erreur') or '')[:160]}")
        if time.monotonic() > echeance:
            raise NoeudError("délai de transcription dépassé")
        travail = {}
    raise NoeudError("délai de transcription dépassé")


# --- branchement (terminal du propriétaire) -----------------------------------------------------

def creer_cle(r: dict) -> str:
    """Clé ed25519 dédiée au noeud (sans phrase de passe : le démon l'utilise seul). Renvoie la clé publique."""
    k = cle(r)
    if not k.exists():
        k.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "jarvis-noeud", "-f", str(k)],
                       check=True, stdin=subprocess.DEVNULL)
    return Path(str(k) + ".pub").read_text(encoding="utf-8").strip()


def brancher(cible: str, *, par: str) -> dict:
    """Enregistre la connexion MCP du noeud, découvre ses outils, autorise ceux du noeud et crée le mandat du
    Board. Le noeud doit déjà répondre (clé autorisée par installer_noeud.sh --cle-jarvis)."""
    from . import connexions, mandats
    data = config.settings()
    r = {**data["noeud"], "cible": cible}
    sante(r, hote_connu=False)  # premier contact : enregistre l'empreinte de l'hôte (réseau privé)
    ident = r.get("connexion") or "jetson"
    ssh = commande_ssh(r, "mcp")
    try:
        existante = connexions.get(ident)
    except connexions.ConnexionError:
        existante = None
    if existante:
        if existante["active"]:
            connexions.revoquer(ident, par=par)  # une connexion est immuable : nouvelle cible = nouvel identifiant
        ident = f"jetson-{secrets.token_hex(4)}"
    ancien = data["noeud"].get("mandat_board")
    if ancien and (mandats.get(ancien) or {}).get("revoked_at") is None and mandats.get(ancien):
        mandats.revoquer(ancien, par=par)
    connexions.enregistrer({"id": ident, "nom": "Noeud GPU Jetson", "type": "mcp_stdio", "command": ssh[0],
                            "args": ssh[1:], "env_allowlist": [], "outils_autorises": []}, par=par)
    connexions.decouvrir(ident)
    connexions.configurer_outils(ident, list(OUTILS), par=par)
    mandat = mandats.creer({"version": 1, "owner": par, "project": PROJET_BOARD,
                            "tools": [f"mcp.{ident}.{o}" for o in OUTILS_BOARD], "destinations": [f"mcp:{ident}"],
                            "expires_at": time.time() + 365 * 86400, "max_cost_cents": 0, "max_actions": 50_000},
                           par=par)
    data["noeud"].update(actif=True, cible=cible, connexion=ident, mandat_board=mandat["id"], cle=str(cle(r)))
    config.save_settings(data)
    return {"connexion": ident, "mandat": mandat["id"]}
