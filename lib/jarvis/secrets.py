"""Secrets minimaux par tâche : chaque rôle ne reçoit que les variables dont il a besoin.

Deux fichiers par projet, hors de tout dépôt, sous ~/.config/jarvis/secrets/ :

    <projet>.toml   QUI reçoit QUOI (des noms, jamais de valeurs) — peut être relu sans risque
        [role.backend]
        vars = ["STRIPE_KEY", "DATABASE_URL"]
        [role."*"]                       # facultatif : pour tous les rôles
        vars = ["SENTRY_DSN"]

    <projet>.env    les VALEURS (NOM=valeur, une par ligne), permissions 600 obligatoires

Les lanceurs (bin/jarvis-claude, bin/jarvis-codex) injectent seulement les variables autorisées pour le rôle
de la tâche, dans l'environnement de l'agent. Jamais dans le prompt, les journaux, le journal d'audit ni les
fichiers d'état : seuls les NOMS y apparaissent.

Limite à connaître : un agent voit les variables qu'il reçoit (il peut les afficher). Ce mécanisme réduit ce
qui peut fuiter d'une tâche ; il n'isole pas un agent de ses propres secrets, et il n'empêche pas un .env que
tu aurais copié toi-même dans un worktree.
"""

from __future__ import annotations

import os
import re
import stat
import tomllib
from pathlib import Path

from . import config

NOM_RE = re.compile(r"^[A-Z_][A-Z0-9_]{0,63}$")
# Variables qui changeraient le comportement du système ou de Jarvis : jamais injectées comme « secret ».
INTERDITES = {"PATH", "HOME", "SHELL", "USER", "LOGNAME", "PWD", "TERM", "TMUX", "LANG", "LD_PRELOAD",
              "LD_LIBRARY_PATH", "PYTHONPATH", "NODE_OPTIONS", "BASH_ENV", "ENV", "PROMPT_COMMAND",
              "GIT_DIR", "GIT_WORK_TREE", "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "CODEX_HOME", "CLAUDE_CONFIG_DIR",
              "IFS", "PS1", "PS2", "PS3", "PS4", "CDPATH", "GLOBIGNORE", "SHELLOPTS", "BASHOPTS"}
# Aussi les variables des fournisseurs d'IA : une clé d'API injectée pour le produit ferait facturer Claude Code
# ou Codex à l'API au lieu de l'abonnement, et une URL de base détournerait leur trafic.
PREFIXES_INTERDITS = ("JARVIS_", "LD_", "DYLD_", "GIT_CONFIG", "BASH_", "ANTHROPIC_", "CLAUDE_", "OPENAI_", "CODEX_")


class SecretsError(ValueError):
    pass


def dossier() -> Path:
    return config.CONFIG_DIR / "secrets"


def _projet_valide(projet: str) -> str:
    if not re.fullmatch(r"[\w.-]+", projet or "") or projet in (".", ".."):
        raise SecretsError(f"nom de projet invalide « {projet} »")
    return projet


def autorisations(projet: str) -> dict[str, list[str]]:
    """{rôle: [noms]} d'après <projet>.toml (rôle « * » = tous). Fichier absent : aucun secret."""
    path = dossier() / f"{_projet_valide(projet)}.toml"
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except FileNotFoundError:
        return {}
    except tomllib.TOMLDecodeError as exc:
        raise SecretsError(f"{path} illisible : {exc}") from exc
    out: dict[str, list[str]] = {}
    for role, bloc in (data.get("role") or {}).items():
        noms = (bloc or {}).get("vars") if isinstance(bloc, dict) else None
        if not isinstance(noms, list):
            continue
        valides = []
        for n in noms:
            n = str(n)
            if not NOM_RE.match(n):
                raise SecretsError(f"{path} : nom de variable invalide « {n} » (majuscules, chiffres, _)")
            if n in INTERDITES or n.startswith(PREFIXES_INTERDITS):
                raise SecretsError(f"{path} : « {n} » ne peut pas être injecté comme secret (variable système ou de Jarvis)")
            valides.append(n)
        out[str(role)] = sorted(set(valides))
    return out


def noms_pour(projet: str, role: str) -> list[str]:
    a = autorisations(projet)
    return sorted(set(a.get(role, [])) | set(a.get("*", [])))


def _valeurs(projet: str) -> dict[str, str]:
    path = dossier() / f"{_projet_valide(projet)}.env"
    try:
        st = path.stat()
    except FileNotFoundError:
        return {}
    if st.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise SecretsError(f"{path} est lisible par d'autres utilisateurs : chmod 600 {path} (aucun secret injecté d'ici là)")
    out: dict[str, str] = {}
    for ligne in path.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        nom, _, valeur = ligne.partition("=")
        nom = nom.strip().removeprefix("export ").strip()
        valeur = valeur.strip()
        if len(valeur) >= 2 and valeur[0] == valeur[-1] and valeur[0] in "\"'":
            valeur = valeur[1:-1]
        if NOM_RE.match(nom):
            out[nom] = valeur
    return out


def pour_tache(projet: str, role: str) -> dict[str, str]:
    """Variables à injecter pour (projet, rôle) : seulement les noms autorisés ET définis. Lève SecretsError
    si un fichier est illisible ou trop ouvert (dans ce cas rien n'est injecté)."""
    noms = noms_pour(projet, role)
    if not noms:
        return {}
    valeurs = _valeurs(projet)
    out = {}
    for n in noms:
        if n not in valeurs:
            continue
        v = valeurs[n]
        if "\n" in v or "\r" in v or "\t" in v:
            raise SecretsError(f"la valeur de {n} contient un retour à la ligne ou une tabulation : non injectée")
        out[n] = v
    return out


def verifier(projet: str) -> list[str]:
    """Rapport lisible : pour chaque rôle, les noms qui seraient injectés et s'ils sont définis. Jamais de valeur."""
    lignes = [f"Secrets du projet {projet} (noms seulement)"]
    toml = dossier() / f"{_projet_valide(projet)}.toml"
    env = dossier() / f"{projet}.env"
    if not toml.exists():
        return lignes + [f"  aucun fichier {toml} : aucun secret n'est injecté (c'est le défaut)"]
    a = autorisations(projet)
    try:
        valeurs = _valeurs(projet)
        etat_env = f"{env} : {len(valeurs)} variable(s), permissions correctes" if env.exists() else f"{env} absent"
    except SecretsError as exc:
        valeurs, etat_env = {}, f"⚠ {exc}"
    lignes.append(f"  {etat_env}")
    communs = a.get("*", [])
    for role in sorted(r for r in a if r != "*") + (["*"] if communs else []):
        noms = sorted(set(a.get(role, [])) | (set(communs) if role != "*" else set()))
        detail = ", ".join(f"{n} ({'défini' if n in valeurs else 'ABSENT'})" for n in noms) or "rien"
        lignes.append(f"  {role if role != '*' else 'tous les rôles'} : {detail}")
    lignes.append("  Les autres rôles ne reçoivent rien.")
    return lignes


def exclusions_codex(autorises: list[str], env: dict | None = None, existantes: list[str] | None = None) -> list[str]:
    """Pour Codex : son filtre par défaut retire des sous-processus toute variable dont le nom contient KEY,
    SECRET ou TOKEN. Pour laisser passer les secrets autorisés SANS élargir le reste, on désactive ce filtre
    et on exclut nommément les autres variables sensibles présentes, en gardant les exclusions déjà écrites
    par l'utilisateur dans sa configuration Codex. Renvoie motifs et noms (jamais de valeurs)."""
    env = os.environ if env is None else env
    motif = re.compile(r"KEY|SECRET|TOKEN|PASSWORD|PASSWD|CREDENTIAL", re.I)
    noms = {n for n in env if motif.search(n) and n not in set(autorises)}
    return sorted(noms | {str(x) for x in (existantes or [])})


def exclusions_codex_utilisateur() -> list[str]:
    """Motifs « shell_environment_policy.exclude » de ~/.codex/config.toml (ou $CODEX_HOME)."""
    base = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "config.toml"
    try:
        with base.open("rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return []
    excl = (data.get("shell_environment_policy") or {}).get("exclude") or []
    return [str(x) for x in excl if isinstance(x, str)]


def valeurs_connues() -> list[str]:
    """Toutes les valeurs des fichiers <projet>.env (pour les expurger d'un texte). Jamais affichées."""
    out = []
    d = dossier()
    for f in d.glob("*.env") if d.is_dir() else []:
        try:
            out += [v for v in _valeurs(f.stem).values() if len(v) >= 6]
        except SecretsError:
            continue
    return out
