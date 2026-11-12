"""Bloc « Outils de cette session » du prompt d'un agent : ce que le lanceur a constaté, jamais ce qu'il suppose.

Chaque ligne vient d'un fait lu au lancement, sur ce poste : un réglage de Jarvis, un fichier de configuration du
moteur, la présence d'un fichier ou d'une commande dans le PATH. Rien n'est connecté, aucun outil n'est appelé,
aucun serveur MCP n'est démarré : « configuré » ne veut pas dire « en état de marche », et le bloc le dit.

Trois réponses possibles par ligne : le fait constaté, son absence constatée, ou « inconnu » quand la source est
illisible, absente ou hors de portée du lanceur. Une ligne inconnue est écrite comme telle : un agent qui croit
avoir un outil qu'il n'a pas perd sa tâche, un agent qui sait qu'il doit vérifier perd une minute.

Seuls des noms sortent d'ici (serveurs, skills, classes) : jamais une valeur de configuration, une URL, une
variable d'environnement ni un chemin personnel.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

from . import config

DELAI_AIDE_S = 5          # « codex --help » : une aide locale, pas un appel de modèle
TAILLE_CONFIG_MAX = 2_000_000
NOMS_MAX = 12             # serveurs ou skills listés ; au-delà, le nombre restant est indiqué
_NOM = re.compile(r"[A-Za-z0-9_.-]{1,64}\Z")
_SKILL_CITEE = re.compile(r"skills/([a-z0-9][a-z0-9._-]{0,39})/")
MOTEURS = {"claude": "Claude Code", "codex": "Codex"}
INCONNU = "inconnu"


def _home() -> Path:
    return Path(os.environ.get("HOME") or Path.home())


def _lire(chemin: Path, format_: str):
    """Contenu d'un fichier de configuration : dict, None s'il n'existe pas ; lève ValueError s'il est illisible."""
    try:
        with chemin.open("rb") as fh:
            brut = fh.read(TAILLE_CONFIG_MAX + 1)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ValueError("illisible") from exc
    if len(brut) > TAILLE_CONFIG_MAX:
        raise ValueError("trop gros")
    try:
        data = tomllib.loads(brut.decode("utf-8")) if format_ == "toml" else json.loads(brut)
    except (ValueError, UnicodeError) as exc:
        raise ValueError("malformé") from exc
    if not isinstance(data, dict):
        raise ValueError("forme inattendue")
    return data


def _noms(liste: list[str]) -> str:
    return ", ".join(liste[:NOMS_MAX]) + (f" (et {len(liste) - NOMS_MAX} de plus)" if len(liste) > NOMS_MAX else "")


def _vrai(valeur) -> bool:
    return str(valeur).strip().lower() not in ("false", "non", "0", "no", "off", "")


def racine_projet(projet: str) -> Path | None:
    """Dossier du projet d'après le registre de Jarvis, ou None s'il n'y est pas."""
    try:
        chemin = (config.projects().get(projet) or {}).get("chemin") or ""
        p = Path(chemin) if chemin else None
        return p if p and p.is_dir() else None
    except Exception:  # noqa: BLE001
        return None


# --- Recherche web -------------------------------------------------------------------------------------------------

def recherche_web_codex() -> str:
    """Même décision que bin/jarvis-codex : --search si le réglage ne le coupe pas ET si ce Codex connaît l'option."""
    try:
        reglage = config.settings().get("codex", {}).get("recherche_web", True)
    except Exception:  # noqa: BLE001
        return f"{INCONNU} — réglage `codex.recherche_web` illisible ; essaie, et dis-le si elle manque"
    if not _vrai(reglage):
        return "non — coupée par le réglage `codex.recherche_web` ; n'invente aucune source, dis ce que tu n'as pas pu vérifier"
    if not shutil.which("codex"):
        return f"{INCONNU} — la commande `codex` n'est pas dans le PATH du lanceur"
    try:
        r = subprocess.run(["codex", "--help"], capture_output=True, text=True, timeout=DELAI_AIDE_S,
                           stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return f"{INCONNU} — `codex --help` n'a pas répondu ; essaie, et dis-le si elle manque"
    if "--search" in (r.stdout or ""):
        return "oui — `--search` est passé à Codex (réglage actif, option connue de la version installée)"
    return ("non — la version installée de Codex ne propose pas `--search` ; n'invente aucune source, dis ce que "
            "tu n'as pas pu vérifier")


def _reglages_claude(racine: Path | None) -> list[Path]:
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    fichiers = [(Path(base) if base else _home() / ".claude") / "settings.json"]
    if racine:
        fichiers += [racine / ".claude" / "settings.json", racine / ".claude" / "settings.local.json"]
    return fichiers


def recherche_web_claude(racine: Path | None) -> str:
    """WebSearch est un outil intégré de Claude Code : le seul fait vérifiable ici est qu'aucun réglage lu ne le refuse."""
    lus, illisibles = 0, 0
    for f in _reglages_claude(racine):
        try:
            data = _lire(f, "json")
        except ValueError:
            illisibles += 1
            continue
        if data is None:
            continue
        lus += 1
        perms = data.get("permissions") if isinstance(data.get("permissions"), dict) else {}
        refus = [x for x in (perms.get("deny") or []) if isinstance(x, str)]
        if any(x == "WebSearch" or x.startswith("WebSearch(") for x in refus):
            return ("non — l'outil WebSearch est refusé par les réglages de Claude Code ; n'invente aucune source, "
                    "dis ce que tu n'as pas pu vérifier")
    if illisibles:
        return f"{INCONNU} — un fichier de réglages de Claude Code est illisible ; essaie WebSearch, et dis-le s'il manque"
    return ("outil WebSearch intégré à Claude Code, sans refus dans les réglages lus "
            f"({lus} fichier(s)) ; non testé au lancement : s'il échoue, dis-le")


# --- Serveurs MCP --------------------------------------------------------------------------------------------------

def _serveurs(data, cle: str) -> list[tuple[str, bool]]:
    bloc = data.get(cle) if isinstance(data, dict) else None
    if not isinstance(bloc, dict):
        return []
    return [(nom, s.get("enabled") is not False) for nom, s in sorted(bloc.items())
            if isinstance(nom, str) and _NOM.fullmatch(nom) and isinstance(s, dict)]


def mcp_codex() -> tuple[str, list[str]]:
    """(ligne, noms) : serveurs déclarés dans la configuration de Codex et approbation d'avance de leurs outils."""
    chemin = Path(os.environ.get("CODEX_HOME") or _home() / ".codex") / "config.toml"
    try:
        data = _lire(chemin, "toml")
    except ValueError:
        return f"{INCONNU} — configuration de Codex illisible", []
    if data is None:
        return "aucun — pas de fichier de configuration de Codex sur ce poste", []
    serveurs = _serveurs(data, "mcp_servers")
    if not serveurs:
        return "aucun dans la configuration de Codex", []
    try:
        reglages = config.settings().get("codex", {})
        approuves = {x.strip() for x in str(reglages.get("mcp_approuves", "")).split(",") if x.strip()}
        complet = reglages.get("mode") == "complet"
    except Exception:  # noqa: BLE001
        approuves, complet = None, False
    actifs = [n for n, actif in serveurs if actif]
    if complet or approuves is None:
        detail = _noms(actifs) + ("" if complet else f" (approbation d'avance : {INCONNU})")
    else:
        ok, refuses = [n for n in actifs if n in approuves], [n for n in actifs if n not in approuves]
        morceaux = []
        if ok:
            morceaux.append(f"{_noms(ok)} (outils approuvés d'avance)")
        if refuses:
            morceaux.append(f"{_noms(refuses)} (déclaré, mais non approuvé d'avance : ses appels seront refusés)")
        detail = " ; ".join(morceaux)
    coupes = [n for n, actif in serveurs if not actif]
    if coupes:
        detail = (detail + " ; " if detail else "") + f"{_noms(coupes)} (désactivé dans la configuration)"
    return detail, actifs


def mcp_claude(racine: Path | None) -> tuple[str, list[str]]:
    """(ligne, noms) : serveurs de portée utilisateur, puis ceux que le projet déclare dans son `.mcp.json`."""
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    chemin = (Path(base) / ".claude.json") if base else _home() / ".claude.json"
    morceaux, noms, inconnu = [], [], False
    try:
        data = _lire(chemin, "json")
        utilisateur = [n for n, actif in _serveurs(data or {}, "mcpServers") if actif]
        if utilisateur:
            morceaux.append(f"{_noms(utilisateur)} (portée utilisateur)")
            noms += utilisateur
    except ValueError:
        inconnu = True
    if racine:
        try:
            projet = [n for n, actif in _serveurs(_lire(racine / ".mcp.json", "json") or {}, "mcpServers") if actif]
            if projet:
                morceaux.append(f"{_noms(projet)} (déclaré par `.mcp.json` du projet ; activation non vérifiée)")
                noms += projet
        except ValueError:
            inconnu = True
    reste = ("Les connecteurs du compte et les serveurs apportés par un plugin ne sont pas visibles du lanceur : "
             f"pour eux, {INCONNU}.")
    if inconnu and not morceaux:
        return f"{INCONNU} — configuration de Claude Code illisible. {reste}", noms
    if not morceaux:
        return f"aucun dans les fichiers lus. {reste}", noms
    return " ; ".join(morceaux) + (f" ; une configuration est illisible ({INCONNU} pour elle)" if inconnu else "") + f". {reste}", noms


# --- Playwright ----------------------------------------------------------------------------------------------------

def playwright(racine: Path | None, serveurs_mcp: list[str]) -> str:
    """Où Playwright a été trouvé, sans rien lancer (pas de `npx`, qui téléchargerait)."""
    trouve = []
    if shutil.which("playwright"):
        trouve.append("commande `playwright` dans le PATH")
    if racine:
        if any((racine / "node_modules" / p).exists() for p in (".bin/playwright", "playwright", "@playwright/test")):
            trouve.append("installé dans `node_modules` du dépôt principal du projet (ton worktree est une copie "
                          "neuve : installe ses dépendances avant de t'en servir)")
        else:
            try:
                paquet = _lire(racine / "package.json", "json") or {}
                deps = {**(paquet.get("dependencies") or {}), **(paquet.get("devDependencies") or {})}
                if any(n in deps for n in ("playwright", "@playwright/test", "playwright-core")):
                    trouve.append("déclaré dans `package.json` du projet, mais pas installé dans le dépôt principal")
            except (ValueError, TypeError):
                pass
    try:
        if importlib.util.find_spec("playwright") is not None:
            trouve.append("module Python `playwright` importable par le Python du lanceur")
    except (ImportError, ValueError):
        pass
    mcp = [n for n in serveurs_mcp if "playwright" in n.lower()]
    if mcp:
        trouve.append(f"serveur MCP `{mcp[0]}` configuré")
    navigateurs = (_home() / ".cache" / "ms-playwright").is_dir()
    if trouve:
        return ("présent — " + " ; ".join(trouve) + ". Navigateurs téléchargés (`~/.cache/ms-playwright`) : "
                + ("oui" if navigateurs else "non trouvés, `playwright install chromium` sera nécessaire") + ".")
    cherche = "PATH, " + ("`node_modules` et `package.json` du projet, " if racine else "") + "module Python, serveurs MCP"
    return (f"non trouvé ({cherche})" + ("" if racine else f" ; dossier du projet {INCONNU} du lanceur : son `node_modules` n'a pas été regardé")
            + ". Ne suppose pas qu'il est installé : vérifie, et si tu ne peux pas piloter de navigateur, dis-le "
              "dans ton compte rendu au lieu de valider à la lecture du code.")


# --- Skills et opérations lourdes ----------------------------------------------------------------------------------

def skills_du_role(brief: str, moteur: str) -> str:
    """Skills que le brief du rôle cite, avec ce qui a été constaté sur disque pour chacune."""
    cites = list(dict.fromkeys(_SKILL_CITEE.findall(brief or "")))
    if not cites:
        return ""
    lien = {"claude": _home() / ".claude" / "skills", "codex": _home() / ".agents" / "skills"}.get(moteur)
    morceaux = []
    for nom in cites[:NOMS_MAX]:
        present = (config.JARVIS_HOME / "skills" / nom / "SKILL.md").is_file()
        etat = f"`$JARVIS_HOME/skills/{nom}/SKILL.md` " + ("présent" if present else "ABSENT de ce poste : dis-le dans ton compte rendu")
        if present and lien is not None:
            etat += ", lié pour ton moteur" if (lien / nom / "SKILL.md").is_file() else ", non lié pour ton moteur (lis le fichier directement)"
        morceaux.append(f"{nom} ({etat})")
    return " ; ".join(morceaux)


def classes_lourdes() -> str:
    try:
        from . import admission
        classes = [c for c, lourde in admission.CLASSES.items() if lourde]
        maxi = int(config.settings().get("admission", {}).get("operations_lourdes_max", 1))
    except Exception:  # noqa: BLE001
        return f"{INCONNU} — réglages d'admission illisibles"
    if maxi <= 0:
        return (f"classes {', '.join(classes)}, mais le réglage `admission.operations_lourdes_max` vaut 0 : aucune "
                "opération lourde ne sera admise ; dis-le si ta tâche en demande une")
    combien = "une seule opération lourde" if maxi == 1 else f"{maxi} opérations lourdes"
    texte = f"classes {', '.join(classes)} ; {combien} à la fois sur ce poste (la commande attend son tour)"
    if not shutil.which("jarvis"):
        texte += f". La commande `jarvis` n'est pas dans le PATH du lanceur ({INCONNU} dans ta session) : sinon, `$JARVIS_HOME/bin/jarvis`"
    return texte


# --- Assemblage ----------------------------------------------------------------------------------------------------

def bloc(*, agent: str, projet: str, brief: str = "") -> list[str]:
    """Section « Outils de cette session ». Ne lève jamais : une ligne dont la source tombe en panne vaut « inconnu »."""
    moteur = (agent or "").strip().lower()
    racine = racine_projet(projet)

    def sur(fn, *args):
        try:
            return fn(*args)
        except Exception:  # noqa: BLE001 — un constat en panne ne bloque pas le prompt
            return None

    out = ["## Outils de cette session", "",
           "Constaté au lancement sur ce poste (réglages, fichiers de configuration, PATH), sans rien connecter. "
           f"« {INCONNU} » veut dire non vérifié : teste avant de compter dessus. Un outil annoncé qui ne répond pas "
           "se signale dans ton compte rendu."]
    serveurs: list[str] = []
    if moteur == "codex":
        out.append("- Moteur : Codex (lancé par `jarvis-codex`).")
        out.append("- Recherche web : " + (sur(recherche_web_codex) or INCONNU) + ".")
        mcp = sur(mcp_codex)
        etiquette = "Serveurs MCP configurés pour Codex"
    elif moteur == "claude":
        out.append("- Moteur : Claude Code (lancé par `jarvis-claude`).")
        out.append("- Recherche web : " + (sur(recherche_web_claude, racine) or INCONNU) + ".")
        mcp = sur(mcp_claude, racine)
        etiquette = "Serveurs MCP configurés pour Claude Code"
    else:
        out.append(f"- Moteur : {INCONNU} (lancement hors routeur) ; recherche web et serveurs MCP : {INCONNU}.")
        mcp, etiquette = None, ""
    if etiquette:
        ligne, serveurs = mcp if mcp else (INCONNU, [])
        ligne = ligne.rstrip(".")
        out.append(f"- {etiquette} (déclarés, pas testés) : {ligne}.")
    out.append("- Playwright : " + (sur(playwright, racine, serveurs) or f"{INCONNU}."))
    skills = sur(skills_du_role, brief, moteur)
    if skills:
        out.append(f"- Skills citées par ton rôle : {skills}.")
    out.append("- `jarvis lourd exec <classe> -- <commande>` : " + (sur(classes_lourdes) or INCONNU) + ".")
    return out
