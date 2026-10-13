"""Rôles spécialisés de l'usine : un fichier roles/<nom>.md par métier.

Chaque fichier commence par un en-tête « clé: valeur » entre deux lignes « --- », suivi du brief
transmis à l'agent. Un fichier du même nom dans ~/.config/jarvis/roles/ remplace celui du dépôt,
et tu peux y ajouter tes propres rôles.
"""

from __future__ import annotations

from pathlib import Path

from . import config

ROLES_DIR = config.JARVIS_HOME / "roles"
ROLES_PERSO = config.CONFIG_DIR / "roles"
DEFAUT = "generaliste"
EQUIPES = ("Conception", "Fabrication", "Exploitation", "Qualité", "Studio", "Veille")
FOURNISSEURS = ("claude", "codex", "auto")

_cache: tuple[tuple, dict[str, dict]] | None = None


def _parse(path: Path) -> dict | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    meta: dict = {}
    corps = text
    if text.startswith("---"):
        head, sep, rest = text[3:].partition("\n---")
        if sep:
            corps = rest.lstrip("\n")
            for line in head.splitlines():
                key, colon, val = line.partition(":")
                if colon and key.strip():
                    meta[key.strip()] = val.strip()
    nom = path.stem.lower()
    try:
        niveau = max(1, min(4, int(meta.get("niveau", 2))))
    except ValueError:
        niveau = 2
    fournisseur = meta.get("fournisseur", "auto")
    return {
        "nom": nom,
        "titre": meta.get("titre") or nom.capitalize(),
        "court": meta.get("court") or meta.get("titre") or nom.capitalize(),
        "equipe": meta.get("equipe") or "Fabrication",
        "sigle": (meta.get("sigle") or nom[:3]).upper()[:3],
        "emoji": meta.get("emoji") or "•",
        "couleur": meta.get("couleur") or "white",
        "fournisseur": fournisseur if fournisseur in FOURNISSEURS else "auto",
        "niveau": niveau,
        "revue": meta.get("revue") or "croisee",
        "livrable": meta.get("livrable") or "pr",
        "resume": meta.get("resume") or "",
        "corps": corps.strip(),
        "source": str(path),
    }


def _signature() -> tuple:
    sig = []
    for d in (ROLES_DIR, ROLES_PERSO):
        try:
            sig += sorted((p.name, p.stat().st_mtime_ns) for p in d.glob("*.md"))
        except OSError:
            continue
    return tuple(sig)


def tous() -> dict[str, dict]:
    """Tous les rôles connus, {nom: rôle}. Relu seulement quand un fichier change."""
    global _cache
    sig = _signature()
    if _cache and _cache[0] == sig:
        return _cache[1]
    out: dict[str, dict] = {}
    for d in (ROLES_DIR, ROLES_PERSO):  # les rôles personnels remplacent ceux du dépôt
        if not d.is_dir():
            continue
        for path in sorted(d.glob("*.md")):
            role = _parse(path)
            if role:
                out[role["nom"]] = role
    _cache = (sig, out)
    return out


def get(nom: str | None) -> dict | None:
    return tous().get((nom or "").strip().lower())


def ou_defaut(nom: str | None) -> dict:
    """Le rôle demandé, sinon le généraliste (un agent a toujours un rôle affichable)."""
    return get(nom) or get(DEFAUT) or {
        "nom": DEFAUT, "titre": "Développeur polyvalent", "court": "Polyvalent", "equipe": "Fabrication", "sigle": "DEV", "emoji": "•",
        "couleur": "white", "fournisseur": "auto", "niveau": 2, "revue": "croisee", "livrable": "pr",
        "resume": "", "corps": "", "source": "",
    }


def par_equipe() -> list[tuple[str, list[dict]]]:
    """[(équipe, [rôles])] dans l'ordre d'affichage de l'usine."""
    roles = tous()
    equipes = list(EQUIPES) + sorted({r["equipe"] for r in roles.values()} - set(EQUIPES))
    out = []
    for eq in equipes:
        membres = sorted((r for r in roles.values() if r["equipe"] == eq), key=lambda r: r["nom"])
        if membres:
            out.append((eq, membres))
    return out


def texte() -> str:
    """Liste lisible par le chef : quel rôle pour quelle tâche."""
    lines = []
    for eq, membres in par_equipe():
        lines.append(eq.upper())
        for r in membres:
            pref = {"claude": "Claude de préférence", "codex": "Codex de préférence", "auto": "selon les jetons"}
            lines.append(f"  {r['nom']:<12} {r['titre']} — {r['resume']} [niveau {r['niveau']}, {pref[r['fournisseur']]}]")
    return "\n".join(lines) or "Aucun rôle défini."
