"""Chemins, réglages (settings.toml) et registre des projets (projects.toml)."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

HOME = Path.home()
JARVIS_HOME = Path(__file__).resolve().parents[2]
CONFIG_DIR = Path(os.environ.get("JARVIS_CONFIG_DIR") or Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config")) / "jarvis")
STATE_DIR = Path(os.environ.get("JARVIS_STATE_DIR") or Path(os.environ.get("XDG_STATE_HOME", HOME / ".local/state")) / "jarvis")
DATA_DIR = Path(os.environ.get("JARVIS_DATA_DIR") or Path(os.environ.get("XDG_DATA_HOME", HOME / ".local/share")) / "jarvis")
SESSION = os.environ.get("JARVIS_SESSION", "jarvis")
CHEF_WINDOW = "chef"

SETTINGS_FILE = CONFIG_DIR / "settings.toml"
PROJECTS_FILE = CONFIG_DIR / "projects.toml"

DEFAULTS: dict = {
    "general": {
        "workspace": str(HOME / "projets"),
        "max_agents": 3,
        "poll_seconds": 20,
        "owner": "",
        # Lance le chef avec --remote-control : tu peux aussi lui parler depuis l'app Claude (téléphone).
        "chef_remote_control": False,
        # Mode de permission du chef (auto = un classifieur valide les actions sûres, utile la nuit).
        # Ses règles deny (pas de code, pas de fusion, pas de push) restent prioritaires.
        "chef_permission_mode": "auto",
        # Battement de cœur : si rien ne s'est passé depuis N minutes et qu'il reste de la place,
        # le démon réveille le chef pour qu'il cherche du travail utile (0 = désactivé).
        "battement_min": 30,
        # Ferme la fenêtre d'un agent terminé depuis N minutes ; worktree et branche restent (0 = jamais).
        "fermeture_auto_min": 60,
        # Après un redémarrage du PC : relancer seuls les agents qui travaillaient et le chef.
        "reprise_auto": True,
        # Si le chef s'arrête alors qu'il reste du travail (agents occupés, plan en cours), le relancer.
        "chef_relance_auto": True,
        # Prévenir le chef quand un agent « travaille » sans rien afficher depuis N minutes (0 = jamais).
        "blocage_min": 45,
        # Prévenir le chef quand une tâche dure depuis plus de N minutes (0 = jamais).
        "duree_max_min": 240,
    },
    "codex": {
        # "bac-a-sable" : Codex écrit seulement dans son worktree et dans le dépôt git du projet.
        # "complet" : aucun bac à sable (dernier recours si Codex ne peut toujours pas committer).
        "mode": "bac-a-sable",
        # Serveurs MCP (séparés par des virgules) dont les outils sont approuvés d'avance pour Codex.
        "mcp_approuves": "linear",
    },
    "sante": {
        # Alertes sur l'état du PC (mémoire, disque, Docker, batterie, redémarrage Windows en attente).
        "active": True,
        "disque_min_go": 10,
        "memoire_min_pct": 10,
        # Capacité adaptée au PC : moins d'agents quand la mémoire manque, aucun lancement sur batterie
        # faible, disque plein ou processeur saturé. max_agents reste le plafond.
        "capacite_auto": True,
        "memoire_par_agent_mo": 1200,
        "batterie_min_pct": 30,
        # Sur batterie sous ce niveau : les agents committent leur travail et Jarvis se met en pause.
        "batterie_arret_pct": 12,
    },
    "notifications": {
        "windows": True,
    },
    "jetons": {
        # Pourcentage d'une fenêtre (5 h ou semaine) à partir duquel on prévient / on arrête.
        "alerte": 80,
        "arret": 95,
        # À l'arrêt : demander aux agents concernés de committer leur travail et de s'arrêter.
        "arret_agents": True,
        # Si les deux abonnements sont épuisés : pause automatique, levée à la remise à zéro.
        "pause_auto": True,
        # Au-delà de ce pourcentage de la fenêtre semaine, les modèles les plus coûteux sont réservés
        # aux grosses tâches (taille L).
        "semaine_prudence": 70,
    },
    "modeles": {
        # Un modèle du catalogue n'est utilisé qu'après un essai réussi avec ton abonnement
        # (jarvis modele verifier, relancé seul par le démon tous les N jours).
        "verification": True,
        "verification_jours": 7,
    },
    "studio": {
        # Taille maximale d'un livrable envoyé sur Telegram (limite de l'API Bot : 50 Mo).
        "taille_max_mo": 49,
    },
    "web": {
        # Tableau de bord dans le navigateur (lecture seule), servi par le démon sur ce PC uniquement.
        "actif": True,
        "port": 7717,
    },
    "veille": {
        # Veille concurrentielle par projet tous les N jours (0 = désactivée).
        "jours": 7,
        # Veille des modèles (nouveautés Claude et Codex) tous les N jours (0 = désactivée).
        "modeles_jours": 14,
    },
    "plans": {
        # "humain" : chaque plan attend ta validation. "auto" : approuvé aussitôt (tu es prévenu),
        # dans les limites de capacité, de jetons et de pause.
        "validation": "humain",
    },
    "telegram": {
        "token": "",
        "chat_id": "",
    },
}


def _merge(base: dict, extra: dict) -> dict:
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base.items()}
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def _read_toml(path: Path) -> dict:
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except FileNotFoundError:
        return {}


def settings() -> dict:
    return _merge(DEFAULTS, _read_toml(SETTINGS_FILE))


def _toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    s = str(v).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def dump_toml(data: dict) -> str:
    """Écrit un TOML à deux niveaux (tables de valeurs simples)."""
    lines: list[str] = []
    for table, values in data.items():
        if not isinstance(values, dict):
            continue
        lines.append(f"[{table}]")
        for k, v in values.items():
            if isinstance(v, dict):
                continue
            lines.append(f"{k} = {_toml_value(v)}")
        lines.append("")
    return "\n".join(lines)


def save_settings(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_FILE.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    # Créé directement en 600 : le jeton Telegram n'est jamais lisible par d'autres, même un instant.
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write("# Réglages JarvisAgent — contient des secrets, ne pas partager\n" + dump_toml(data))
    tmp.replace(SETTINGS_FILE)


# --- Registre des projets ----------------------------------------------------

def projects() -> dict[str, dict]:
    """{"repriceo": {"chemin": "...", "linear": "...", "description": "...", "priorite": 1}}"""
    raw = _read_toml(PROJECTS_FILE).get("projets", {})
    out: dict[str, dict] = {}
    for name, p in raw.items():
        if not isinstance(p, dict):
            continue
        p = dict(p)
        p["chemin"] = str(Path(os.path.expanduser(p.get("chemin", ""))))
        p.setdefault("priorite", 3)
        p.setdefault("linear", "")
        p.setdefault("description", "")
        p.setdefault("actif", True)
        out[name] = p
    return out


def save_projects(projs: dict[str, dict]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Registre des projets pilotés par Jarvis.",
        "# priorite : 1 = le plus important. actif = false pour mettre un projet en pause.",
        "",
    ]
    for name, p in projs.items():
        lines.append(f"[projets.{name}]")
        for key in ("chemin", "linear", "description", "verification", "priorite", "actif"):
            if key in p and p[key] != "":
                lines.append(f"{key} = {_toml_value(p[key])}")
        lines.append("")
    tmp = PROJECTS_FILE.with_suffix(".tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    tmp.replace(PROJECTS_FILE)


def project_for_path(path: str | os.PathLike) -> str | None:
    """Nom du projet dont le dossier contient `path` (worktrees inclus)."""
    target = Path(path).resolve()
    best: tuple[int, str] | None = None
    for name, p in projects().items():
        root = Path(p["chemin"]).resolve()
        candidates = [root, root.parent / f"{root.name}__worktrees"]
        for c in candidates:
            try:
                target.relative_to(c)
            except ValueError:
                continue
            depth = len(c.parts)
            if best is None or depth > best[0]:
                best = (depth, name)
    return best[1] if best else None
