"""Capacités observées du poste et limites des voies d'exécution Jarvis.

Le diagnostic ne lance aucune inférence. Un binaire présent ou une déclaration MCP ne prouve ni
l'authentification ni l'exécution d'un outil. ``available`` vaut seulement pour l'opération décrite
dans ``scope`` et effectivement vérifiée pendant la collecte. Par exemple ``provider.codex.cli``
vérifie ``--version`` ; il ne vérifie pas la capacité de produire une réponse avec un modèle.

Les configurations MCP sont lues comme métadonnées : ni arguments de commande, ni en-têtes,
ni variables/secrets, ni URL complète ne sont renvoyés. La sonde réseau est facultative, HTTPS
vérifié, sans redirection, vers un seul hôte public fixe ; elle ne valide pas « tout Internet ».
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import config

VERSION = 1
ETATS = ("absent", "configure", "authentifie", "verifie", "inconnu", "degrade")
DELAI_COMMANDE = 1.5
DELAI_RESEAU = 3.0
URL_SONDE = "https://pypi.org/"
VARIABLES = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY", "CODEX_API_KEY",
             "GH_TOKEN", "GITHUB_TOKEN", "LINEAR_API_KEY", "JARVIS_MISSIONS_PG")
_VERSION = re.compile(r"(?<![\w./-])v?(\d{1,3}\.\d{1,3}(?:\.\d{1,3})?[a-z]?)(?![\w/])")
_NOM_MCP = re.compile(r"[A-Za-z0-9_.-]{1,64}\Z")
_HOTE = re.compile(r"[A-Za-z0-9.-]{1,253}\Z")


def _preuve(ident: str, etat: str, scope: str, preuve: str, **extra) -> dict:
    return {"id": ident, "etat": etat, "available": etat == "verifie", "scope": scope,
            "preuve": preuve, **extra}


def _commande(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(args, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              timeout=DELAI_COMMANDE, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None


def _binaire(nom: str, ident: str, option: str = "--version") -> dict:
    scope = f"démarrage du CLI {nom} et lecture de sa version, sans inférence"
    chemin = shutil.which(nom)
    if not chemin or chemin.startswith("/mnt/"):
        return _preuve(ident, "absent", scope, "Aucun exécutable Linux utilisable détecté.")
    r = _commande([chemin, option])
    if r is None or r.returncode:
        return _preuve(ident, "degrade", scope, "Exécutable présent ; lecture de version échouée ou délai dépassé.")
    version = _VERSION.search(r.stdout)
    if not version:
        return _preuve(ident, "configure", scope, "Exécutable présent ; format de version non reconnu.")
    return _preuve(ident, "verifie", scope, "Le CLI a répondu à la commande de version.", version=version[1])


def _git_local() -> dict:
    scope = "lecture des métadonnées du checkout Jarvis local ; aucun accès Git distant testé"
    chemin = shutil.which("git")
    if not chemin or chemin.startswith("/mnt/"):
        return _preuve("git.read", "absent", scope, "Git introuvable.")
    r = _commande([chemin, "rev-parse", "--is-inside-work-tree"], cwd=config.JARVIS_HOME)
    if r is None or r.returncode or r.stdout.strip() != "true":
        return _preuve("git.read", "degrade", scope, "La lecture du checkout local n'a pas été vérifiée.")
    return _preuve("git.read", "verifie", scope, "Git reconnaît le checkout local.")


def _workmux_status() -> dict:
    scope = "lecture de workmux status --all --json dans le contexte local"
    chemin = shutil.which("workmux")
    if not chemin or chemin.startswith("/mnt/"):
        return _preuve("workmux.status", "absent", scope, "Workmux Linux introuvable.")
    r = _commande([chemin, "status", "--all", "--json"])
    if r is None or r.returncode:
        return _preuve("workmux.status", "degrade", scope, "Workmux n'a pas fourni un état exploitable.")
    try:
        data = json.loads(r.stdout)
    except (json.JSONDecodeError, TypeError):
        data = None
    if (not isinstance(data, dict) or not isinstance(data.get("agents"), list)
            or not all(isinstance(a, dict) for a in data["agents"])):
        return _preuve("workmux.status", "degrade", scope, "Le statut reçu ne respecte pas le format JSON attendu.")
    if data.get("target_errors") or data.get("state_files_invalid"):
        return _preuve("workmux.status", "degrade", scope, "Workmux signale des erreurs ou des états invalides.")
    return _preuve("workmux.status", "verifie", scope, "État JSON lu sans erreur de cible.",
                   sessions_observees=len(data["agents"]))


def _hote(url: object) -> str | None:
    if not isinstance(url, str):
        return None
    try:
        hote = urllib.parse.urlsplit(url).hostname
        return hote.lower() if hote and _HOTE.fullmatch(hote) else None
    except ValueError:
        return None


def _serveurs_mcp(source: str, data: object, *, projet: bool = False) -> list[dict]:
    if not isinstance(data, dict):
        return []
    resultat = []
    for nom, serveur in sorted(data.items()):
        # Une entrée malformée ne doit pas devenir un texte arbitraire affiché par le diagnostic.
        if not isinstance(nom, str) or not _NOM_MCP.fullmatch(nom) or not isinstance(serveur, dict):
            continue
        hote = _hote(serveur.get("url"))
        transport = "http" if hote else ("stdio" if isinstance(serveur.get("command"), str) else "inconnu")
        resultat.append({"nom": nom, "source": source, "perimetre": "projet" if projet else "utilisateur",
                         "transport": transport, "hote": hote, "etat": "configure", "available": False,
                         "active": serveur.get("enabled") is not False,
                         "auth_declaree": bool(serveur.get("bearer_token_env_var") or serveur.get("env")
                                               or serveur.get("headers") or serveur.get("http_headers")
                                               or serveur.get("env_http_headers")),
                         "preuve": "Métadonnées de configuration lues ; aucune connexion ni outil MCP testé."})
    return resultat


def _mcp() -> dict:
    """Ne jamais renvoyer les données source, les chemins ni les exceptions de parsing."""
    codex = Path(os.environ.get("CODEX_HOME") or config.HOME / ".codex") / "config.toml"
    claude_root = os.environ.get("CLAUDE_CONFIG_DIR")
    claude = (Path(claude_root) / ".claude.json") if claude_root else config.HOME / ".claude.json"
    entrees = (("codex", codex, "toml", False), ("claude", claude, "json", False),
               ("projet", config.JARVIS_HOME / ".mcp.json", "json", True))
    serveurs, diagnostics = [], []
    for source, chemin, format_, projet in entrees:
        try:
            with chemin.open("rb") as f:
                brut = f.read(1_048_577)
            if len(brut) > 1_048_576:
                raise ValueError("taille")
            data = tomllib.loads(brut.decode("utf-8")) if format_ == "toml" else json.loads(brut)
            if not isinstance(data, dict):
                raise ValueError("forme")
            cle = "mcp_servers" if format_ == "toml" else "mcpServers"
            serveurs.extend(_serveurs_mcp(source, data.get(cle), projet=projet))
            diagnostics.append({"source": source, "etat": "configure", "preuve": "Configuration lue sans exécuter ses commandes."})
        except FileNotFoundError:
            diagnostics.append({"source": source, "etat": "absent", "preuve": "Aucun fichier de configuration détecté à cet emplacement."})
        except (OSError, ValueError, UnicodeError):
            diagnostics.append({"source": source, "etat": "degrade", "preuve": "Configuration illisible ou malformée ; aucun contenu divulgué."})
    return {"serveurs": serveurs, "diagnostics": diagnostics}


class _SansRedirection(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _reseau(sonder: bool) -> dict:
    scope = "requête HEAD HTTPS vers pypi.org uniquement ; ne valide ni recherche web ni accès général à Internet"
    if not sonder:
        return _preuve("web.https", "inconnu", scope, "Sonde réseau non demandée ; aucune requête effectuée.")
    try:
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ssl.create_default_context()),
                                             _SansRedirection())
        requete = urllib.request.Request(URL_SONDE, method="HEAD", headers={"User-Agent": "Jarvis-capacites/1"})
        with opener.open(requete, timeout=DELAI_RESEAU) as r:
            statut = r.status
        if 200 <= statut < 300:
            return _preuve("web.https", "verifie", scope, "Réponse HTTPS reçue avec vérification TLS et sans redirection.",
                           hote="pypi.org", methode="HEAD", statut_http=statut)
    except (OSError, urllib.error.URLError, ValueError):
        pass
    return _preuve("web.https", "degrade", scope, "La sonde HTTPS fixe a échoué ; la cause détaillée et les URL ne sont pas divulguées.")


def _voies(capacites: list[dict]) -> dict:
    par_id = {c["id"]: c for c in capacites}
    chef_cli = par_id["provider.claude.cli"]["available"]
    code_cli = any(par_id[f"provider.{p}.cli"]["available"] for p in ("claude", "codex"))
    return {
        "board_documentaire": {
            "profile": "documentaire", "etat": "configure", "available": False,
            "outils": False, "mcp": False, "web_general": False, "session_persistante": False,
            "capacites_declarees": ["analyse"],
            "preuve": "Les adaptateurs documentaires désactivent les outils/MCP et la persistance. La copie d'une pièce peut être lue ; l'analyse par modèle n'est pas testée ici.",
        },
        "chef_cli": {
            "profile": "outille", "etat": "configure" if chef_cli else "absent", "available": False,
            "outils_declares": ["web.search", "web.fetch", "mcp.linear"],
            "outils_verifies": [],
            "preuve": "Web et Linear sont autorisés dans les instructions du chef ; ni sa session, ni leur authentification et leur exécution ne sont vérifiées par ce diagnostic.",
        },
        "code": {
            "profile": "code", "etat": "configure" if code_cli else "absent", "available": False,
            "outils_declares": ["shell", "git", "mcp.configures"], "outils_verifies": [],
            "reseau_declare": True,
            "preuve": "Les lanceurs de code prévoient outils et réseau ; cette déclaration ne prouve ni une session active ni l'accès à un service externe.",
        },
    }


def collecter(*, sonder_reseau: bool = False) -> dict:
    """Diagnostic sans inférence ni effet externe par défaut, borné par commande.

    Les observations CLI indépendantes se font sur quatre fils, avec un délai de 1,5 s par commande.
    La sonde opt-in ajoute au plus 3 s. Aucun résultat brut de commande ou configuration n'est renvoyé.
    Une vérification par modèle/authentification sera une opération distincte, explicitement autorisée.
    """
    if not isinstance(sonder_reseau, bool):
        raise ValueError("sonder_reseau doit être un booléen")
    verifications = [
        lambda: _binaire("git", "git.cli"),
        lambda: _binaire("tmux", "tmux.runtime", "-V"),
        lambda: _binaire("workmux", "workmux.cli"),
        lambda: _binaire("node", "node.runtime"),
        lambda: _binaire("claude", "provider.claude.cli"),
        lambda: _binaire("codex", "provider.codex.cli"),
        _git_local, _workmux_status,
    ]
    caps = [_preuve("python.runtime", "verifie" if sys.version_info >= (3, 11) else "degrade",
                    "interpréteur Python du processus courant", "Version de l'interpréteur observée localement.",
                    version=".".join(map(str, sys.version_info[:3])))]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        caps.extend(pool.map(lambda f: f(), verifications))
    for p in ("claude", "codex"):
        caps.append(_preuve(f"provider.{p}.auth", "inconnu", "authentification d'une inférence avec le fournisseur",
                             "Aucune inférence ni lecture de jeton effectuée ; un CLI présent ne prouve pas une connexion valide."))
        caps.append(_preuve(f"provider.{p}.modeles", "inconnu", "modèles accessibles avec le compte courant",
                             "Aucun modèle interrogé ; le catalogue déclaré ne prouve pas l'accès effectif."))
        caps.append(_preuve(f"provider.{p}.inference", "inconnu", "inférence réelle dans le profil et le modèle demandés",
                             "Aucun appel de modèle effectué ; authentification et disponibilité restent à vérifier."))
    caps.append(_reseau(sonder_reseau))
    return {"version": VERSION, "ts": time.time(), "capacites": caps, "voies": _voies(caps), "mcp": _mcp(),
            "variables": [{"nom": nom, "presente": bool(os.environ.get(nom))} for nom in VARIABLES],
            "note": "Une preuve locale ne vaut que pour son périmètre ; aucune connexion externe ni inférence n'est supposée disponible."}
