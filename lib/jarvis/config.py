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
    "admission": {
        # Profil appliqué (jarvis profil appliquer laptop-conservative) : information, les valeurs font foi.
        "profil": "",
        # Opérations lourdes simultanées (compilation, tests, navigateur, vidéo) déclarées via « jarvis lourd ».
        "operations_lourdes_max": 1,
        # Une réservation d'admission non confirmée par l'apparition de l'agent expire après N minutes.
        "reservation_min": 15,
        # Au-delà de cette charge moyenne par cœur (1 min), aucun nouveau départ.
        "charge_max_par_coeur": 2.5,
        # Mémoire gardée pour Windows, le navigateur, Docker et le chef (Mo).
        "memoire_reserve_mo": 1500,
        # Pression mémoire soutenue (PSI « some », 60 s, en %) au-delà de laquelle le démon pose la pause
        # « ressources » ; elle se lève seule quand la pression retombe sous la moitié pendant hysterese_min.
        "pression_memoire_pct": 25,
        "hysterese_min": 5,
    },
    "budget_jetons": {
        # Plafond de jetons par unité de travail (projet, issue, rôle), relances comprises :
        # multiplicateur × estimation. L'estimation devient la médiane des tâches terminées de même rôle et
        # taille dès qu'il y en a 5 ; avant, ces valeurs par défaut. Un plan peut imposer « %2M ».
        "actif": True,
        "multiplicateur": 3.0,
        "estimation_s": 300_000,
        "estimation_m": 800_000,
        "estimation_l": 2_000_000,
        # Le démon relit la consommation des tâches ouvertes toutes les N minutes.
        "verification_min": 5,
    },
    "couts": {
        # « jarvis cout » : équivalent API, jamais une dépense. Tarifs en dollars US (config/modeles.toml) ;
        # taux = unités de la devise pour 1 dollar US (0 = non réglé : affichage en dollars US).
        "devise": "EUR",
        "taux": 0.0,
    },
    "observabilite": {
        # Point d'entrée OTLP/HTTP (ex. http://localhost:4318) pour « jarvis traces envoyer ». Vide = rien ne sort.
        "otlp_endpoint": "",
    },
    "optimisation": {
        # Optimisation hebdomadaire des briefs de rôles (outils/optimiser_prompts.py, sur tes abonnements) :
        # désactivée par défaut. Rôles séparés par des virgules, traités un par semaine à tour de rôle.
        "hebdo": False,
        "roles": "backend,frontend,qa,securite,redaction",
        "jour": 7,          # 1 = lundi … 7 = dimanche
        "heure": "02:00",
        "canari_pct": 10,   # part des tâches d'un rôle qui essaient un brief candidat approuvé
    },
    "stockage": {
        # json (défaut) ou sqlite (après « jarvis stockage migrer »). Le journal d'audit reste un fichier.
        "backend": "json",
    },
    "bilan": {
        # Bilan quotidien envoyé sur Telegram par le démon, une fois par jour à cette heure (HH:MM, heure locale).
        "actif": True,
        "heure": "08:00",
    },
    "propositions": {
        # File de travaux partagée : au plus N propositions acceptées par source et par jour.
        "max_par_jour": 3,
        # Dépôt GitHub (owner/nom) dont les issues « jarvis-proposition » sont importées (vide = désactivé).
        "github_depot": "",
    },
    "noeud": {
        # Noeud GPU (Jetson, services/noeud_jetson) joint en SSH par une clé à commande forcée. Il étend Jarvis
        # d'outils GPU appelés par la passerelle sous mandat ; désactivé = l'audio du Board garde ses métadonnées.
        # Branché par « jarvis noeud config utilisateur@hote » (cible, clé, connexion et mandat).
        "actif": False,
        "cible": "",
        "cle": "",
        "connexion": "jetson",
        "mandat_board": "",
        "commande": "/usr/bin/ssh",
        "langue": "fr",
        "delai_s": 900,
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


# Bornes des réglages qui gouvernent l'admission : hors bornes, l'admission refuse (fail closed).
_BORNES: dict[tuple[str, str], tuple[type, float, float]] = {
    ("general", "max_agents"): (int, 0, 64),
    ("general", "poll_seconds"): (int, 5, 600),
    ("admission", "operations_lourdes_max"): (int, 0, 16),
    ("admission", "reservation_min"): (int, 1, 120),
    ("admission", "charge_max_par_coeur"): (float, 0.5, 16),
    ("admission", "memoire_reserve_mo"): (int, 0, 65536),
    ("admission", "pression_memoire_pct"): (int, 1, 100),
    ("admission", "hysterese_min"): (int, 1, 120),
    ("sante", "memoire_par_agent_mo"): (int, 200, 65536),
    ("sante", "batterie_min_pct"): (int, 0, 100),
    ("sante", "batterie_arret_pct"): (int, 0, 100),
    ("jetons", "alerte"): (int, 1, 100),
    ("jetons", "arret"): (int, 1, 100),
    ("budget_jetons", "multiplicateur"): (float, 1, 20),
    ("budget_jetons", "estimation_s"): (int, 10_000, 100_000_000),
    ("budget_jetons", "estimation_m"): (int, 10_000, 100_000_000),
    ("budget_jetons", "estimation_l"): (int, 10_000, 100_000_000),
    ("budget_jetons", "verification_min"): (int, 1, 120),
    ("couts", "taux"): (float, 0, 1000),
    ("noeud", "delai_s"): (int, 30, 3600),
}
# Langues acceptées par le noeud GPU (services/noeud_jetson, LANGUES).
LANGUES_NOEUD = ("auto", "fr", "en", "es", "de", "it", "pt", "nl", "ar")


def valider(s: dict | None = None) -> list[str]:
    """Erreurs de configuration (liste vide = valide). Une valeur absurde ne doit jamais ouvrir les vannes."""
    s = settings() if s is None else s
    erreurs = []
    for (table, cle), (typ, mini, maxi) in _BORNES.items():
        v = (s.get(table) or {}).get(cle)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            erreurs.append(f"{table}.{cle} doit être un nombre (lu : {v!r})")
            continue
        if typ is int and int(v) != v:
            erreurs.append(f"{table}.{cle} doit être un entier (lu : {v!r})")
        elif not mini <= v <= maxi:
            erreurs.append(f"{table}.{cle} = {v} hors bornes [{mini:g}, {maxi:g}]")
    if (s.get("plans") or {}).get("validation") not in ("humain", "auto"):
        erreurs.append("plans.validation doit valoir « humain » ou « auto »")
    if (s.get("noeud") or {}).get("langue") not in LANGUES_NOEUD:
        erreurs.append("noeud.langue doit valoir : " + ", ".join(LANGUES_NOEUD))
    import re as _re
    if not _re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", str((s.get("bilan") or {}).get("heure", ""))):
        erreurs.append("bilan.heure doit être une heure HH:MM (ex. 08:00)")
    j = s.get("jetons") or {}
    if isinstance(j.get("alerte"), int) and isinstance(j.get("arret"), int) and j["alerte"] > j["arret"]:
        erreurs.append("jetons.alerte doit être inférieur ou égal à jetons.arret")
    return erreurs


# --- Profils de poste --------------------------------------------------------------------------

PROFILS_DIR = JARVIS_HOME / "config" / "profils"


def profils() -> dict[str, dict]:
    """{nom: {"description", "reglages": {table: {cle: valeur}}}} lus dans config/profils/*.toml."""
    out: dict[str, dict] = {}
    for f in sorted(PROFILS_DIR.glob("*.toml")) if PROFILS_DIR.is_dir() else []:
        data = _read_toml(f)
        meta = data.pop("profil", {}) if isinstance(data.get("profil"), dict) else {}
        out[f.stem] = {"description": str(meta.get("description", "")), "mesure": bool(meta.get("mesure", False)),
                       "reglages": {t: dict(v) for t, v in data.items() if isinstance(v, dict)}}
    return out


def appliquer_profil(nom: str) -> tuple[dict, Path | None]:
    """Fusionne un profil dans settings.toml (sauvegarde d'abord). Renvoie (réglages appliqués, sauvegarde)."""
    p = profils().get(nom)
    if not p:
        raise ValueError(f"profil inconnu « {nom} » (disponibles : {', '.join(profils()) or 'aucun'})")
    courant = _read_toml(SETTINGS_FILE)
    nouveau = _merge(courant, p["reglages"])
    nouveau.setdefault("admission", {})["profil"] = nom
    erreurs = valider(_merge(DEFAULTS, nouveau))
    if erreurs:
        raise ValueError("profil refusé : " + " ; ".join(erreurs))
    sauvegarde = None
    if SETTINGS_FILE.exists():
        import shutil
        import time
        sauvegarde = SETTINGS_FILE.with_name(f"settings.toml.avant-{nom}-{time.strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(SETTINGS_FILE, sauvegarde)
    save_settings(nouveau)
    return p["reglages"], sauvegarde


def _toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v) if isinstance(v, float) else str(v)
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
        for key in ("chemin", "linear", "description", "verification", "priorite", "actif", "execution"):
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
