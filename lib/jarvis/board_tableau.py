"""Objets de tableau blanc du Board V2 : note adhésive, texte libre, forme, trait à main levée, cadre, flèche libre.

Leur apparence vit dans `meta`. Ce module la BORNE : couleurs = noms de jetons (jamais une couleur CSS libre, le
client choisit la teinte selon le thème), un trait = une liste de nombres de taille limitée (jamais un chemin SVG
libre), une flèche = deux extrémités normalisées sur sa boîte et, au besoin, deux ancres normalisées sur les objets
visés (elles survivent au redimensionnement). Tout texte reste du texte : rien ici n'est interprété comme du HTML.

Sans dépendance (ni aux missions, ni à la base) : `verifier` rend un message d'erreur en français, ou None.
"""

from __future__ import annotations

import math
import re

TYPES = ("adhesif", "texte_libre", "forme", "trait", "cadre", "fleche")
COULEURS = ("", "neutre", "indigo", "violet", "rose", "orange", "jaune", "vert", "cyan", "gris")
FORMES = ("rectangle", "ellipse", "losange")
OUTILS_TRAIT = ("crayon", "surligneur")
POINTES = ("fin", "deux", "aucune")
POINTS_MAX = 1_500        # points (x, y, pression) par trait : au-delà, le client simplifie avant d'envoyer
COORDONNEE_MAX = 100_000  # même borne que la géométrie des objets (board.GEOMETRIE_MAX)
EPAISSEUR_MAX = 64
LIBELLE_MAX = 200
_ID_OBJET = re.compile(r"BO-[0-9a-f]{12}")


def _nombre(v: object, mini: float, maxi: float) -> bool:
    """Nombre fini dans [mini, maxi]. Booléens et texte refusés : jamais de conversion silencieuse."""
    return not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v) and mini <= v <= maxi


def _trait(meta: dict) -> str | None:
    points = meta.get("points")
    if not isinstance(points, list) or len(points) % 3 or not 6 <= len(points) <= 3 * POINTS_MAX:
        return f"trait : de 2 à {POINTS_MAX} points (x, y, pression) attendus"
    if not all(_nombre(v, -COORDONNEE_MAX, COORDONNEE_MAX) for v in points):
        return "trait : chaque coordonnée doit être un nombre fini et borné"
    if meta.get("outil", "crayon") not in OUTILS_TRAIT:
        return f"outil de dessin inconnu : {str(meta.get('outil'))[:40]}"
    boite = meta.get("boite")
    if not isinstance(boite, list) or len(boite) != 2 or not all(_nombre(v, 1, COORDONNEE_MAX) for v in boite):
        return "trait : boîte d'origine [largeur, hauteur] attendue"
    return None


def _fleche(meta: dict) -> str | None:
    points = meta.get("points")
    if not isinstance(points, list) or len(points) != 4 or not all(_nombre(v, 0, 1) for v in points):
        return "flèche : deux extrémités normalisées [x1, y1, x2, y2] attendues (entre 0 et 1)"
    if meta.get("pointes", "fin") not in POINTES:
        return f"pointes de flèche inconnues : {str(meta.get('pointes'))[:40]}"
    ancres = meta.get("ancres", {})
    if not isinstance(ancres, dict) or set(ancres) - {"de", "vers"}:
        return "flèche : ancres « de » et « vers » seulement"
    for a in ancres.values():
        if (not isinstance(a, dict) or set(a) != {"id", "nx", "ny"} or not isinstance(a["id"], str)
                or not _ID_OBJET.fullmatch(a["id"]) or not _nombre(a["nx"], 0, 1) or not _nombre(a["ny"], 0, 1)):
            return "flèche : ancre invalide (id, nx, ny entre 0 et 1)"
    return None


def verifier(type_: str, meta: dict | None) -> str | None:
    """Message d'erreur si `meta` sort des bornes pour ce type d'objet ; None si tout va bien ou si le type n'est
    pas un objet de tableau blanc (les cartes existantes ne sont pas concernées)."""
    if type_ not in TYPES:
        return None
    meta = meta or {}
    for cle in ("couleur", "fond", "trait"):
        if cle in meta and (not isinstance(meta[cle], str) or meta[cle] not in COULEURS):
            return f"{cle} inconnue : {str(meta[cle])[:40]}"
    if "epaisseur" in meta and not _nombre(meta["epaisseur"], 0, EPAISSEUR_MAX):
        return f"épaisseur : nombre entre 0 et {EPAISSEUR_MAX} attendu"
    if "taille_police" in meta and not _nombre(meta["taille_police"], 8, 400):
        return "taille de police : nombre entre 8 et 400 attendu"
    if "libelle" in meta and (not isinstance(meta["libelle"], str) or len(meta["libelle"]) > LIBELLE_MAX):
        return f"libellé : texte de {LIBELLE_MAX} caractères au plus"
    if type_ == "forme" and meta.get("forme") not in FORMES:
        return f"forme inconnue : {str(meta.get('forme'))[:40]}"
    if type_ == "trait":
        return _trait(meta)
    if type_ == "fleche":
        return _fleche(meta)
    return None
