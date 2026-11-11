"""Routes de la Bibliothèque de références, derrière la session du Studio (aiguillées par studio_api.py).

Même sécurité que le reste du Studio, appliquée AVANT d'arriver ici : hôte local, session, et pour les écritures
l'en-tête X-Jarvis-Studio et une Origin locale. Ce module ne lit que des paramètres bornés et ne renvoie que du
JSON ; les captures d'écran sont servies par la route de fichiers existante (/api/v2/fichiers/AS-…).

Lecture
  GET  /api/v2/references[?collection=&etiquette=&q=&corbeille=1]   liste + facettes + état du moteur
  GET  /api/v2/references/recherche?q=…[&collection=&etiquette=&n=] passages classés, avec citation complète
  GET  /api/v2/references/RF-…                                      fiche (et état de la capture)
  GET  /api/v2/references/fragments/FR-…                            un fragment entier
Écriture
  POST /api/v2/references                 {url | texte | objet_id, titre?, collection?, etiquettes?}  → 202 ou 201
  POST /api/v2/references/reindexer       {}                         toutes les références prêtes
  POST /api/v2/references/RF-…            {titre?, collection?, etiquettes?}
  POST /api/v2/references/RF-…/supprimer  {restaurer?}               suppression douce
  POST /api/v2/references/RF-…/reindexer  {recapturer?}              ré-indexe, ou relance la capture (202)
  POST /api/v2/references/RF-…/poser      {espace?, x?, y?}          crée la carte du Board reliée
"""

from __future__ import annotations

import re

_REF = r"(RF-[0-9a-f]{12})"


def _champs(corps: dict, permis: set[str]) -> None:
    if set(corps) - permis:
        raise ValueError("Champs inconnus dans la demande.")


def _un(query: dict, cle: str, defaut: str | None = None, maxi: int = 500) -> str | None:
    valeurs = query.get(cle)
    return valeurs[0][:maxi] if valeurs else defaut


def lire(route: str, query: dict, tenant: str):
    """Retourne (code HTTP, JSON), ou None si la route appartient à un autre module."""
    if not route.startswith("/api/v2/references"):
        return None
    from . import references
    if route == "/api/v2/references":
        return 200, {**references.lister(tenant, collection=_un(query, "collection", None, 80),
                                         etiquette=_un(query, "etiquette", None, 40), q=_un(query, "q", "", 200) or "",
                                         supprimees=_un(query, "corbeille") == "1"),
                     "moteur": references.etat_moteur(tenant)}
    if route == "/api/v2/references/recherche":
        return 200, references.chercher(tenant, _un(query, "q", "") or "", collection=_un(query, "collection", None, 80),
                                        etiquette=_un(query, "etiquette", None, 40), n=int(_un(query, "n", "8", 4) or 8))
    if m := re.fullmatch(r"/api/v2/references/fragments/(FR-[0-9a-f]{12})", route):
        return 200, references.fragment(tenant, m.group(1))
    if m := re.fullmatch(rf"/api/v2/references/{_REF}", route):
        return 200, references.voir(tenant, m.group(1), supprimees=True)
    return 404, {"erreur": "Route inconnue."}


def ecrire(route: str, corps: dict, tenant: str, *, serveur=None):
    """L'auteur provient de la session propriétaire, jamais du contenu publié. `serveur` : options de test du
    serveur Studio (`references_prives`, `references_exceptions`, `references_pilote`), absentes en service."""
    if not route.startswith("/api/v2/references"):
        return None
    from . import references
    options = {"autoriser_prives": bool(getattr(serveur, "references_prives", False)),
               "exceptions": getattr(serveur, "references_exceptions", ()),
               "pilote": getattr(serveur, "references_pilote", None)}
    if route == "/api/v2/references":
        _champs(corps, {"url", "texte", "objet_id", "titre", "collection", "etiquettes"})
        for cle in ("url", "texte", "objet_id", "titre", "collection"):
            if not isinstance(corps.get(cle, ""), str):
                raise ValueError(cle)
        ref = references.ajouter(tenant, url=corps.get("url", ""), texte=corps.get("texte", ""),
                                 objet_id=corps.get("objet_id", ""), titre=corps.get("titre", ""),
                                 collection=corps.get("collection", ""), etiquettes=corps.get("etiquettes") or (),
                                 auteur="studio:humain")
        if ref["type"] == "site" and ref["statut"] == "en_attente" and not ref.get("deja"):
            references.planifier(tenant, ref["id"], **options)  # hors du fil de la requête
            return 202, ref
        return (200 if ref.get("deja") else 201), ref
    if route == "/api/v2/references/reindexer":
        _champs(corps, set())
        return 200, references.reindexer(tenant)
    if m := re.fullmatch(rf"/api/v2/references/{_REF}", route):
        _champs(corps, {"titre", "collection", "etiquettes"})
        return 200, references.modifier(tenant, m.group(1), titre=corps.get("titre"), collection=corps.get("collection"),
                                        etiquettes=corps.get("etiquettes"))
    if m := re.fullmatch(rf"/api/v2/references/{_REF}/supprimer", route):
        _champs(corps, {"restaurer"})
        return 200, references.supprimer(tenant, m.group(1), restaurer=corps.get("restaurer") is True, par="studio:humain")
    if m := re.fullmatch(rf"/api/v2/references/{_REF}/reindexer", route):
        _champs(corps, {"recapturer"})
        if corps.get("recapturer") is True:
            ref = references.recapturer(tenant, m.group(1))
            references.planifier(tenant, m.group(1), **options)
            return 202, ref
        return 200, references.reindexer(tenant, m.group(1))
    if m := re.fullmatch(rf"/api/v2/references/{_REF}/poser", route):
        _champs(corps, {"espace", "x", "y"})
        return 201, references.poser_sur_board(tenant, m.group(1), espace=corps.get("espace") or "accueil",
                                               x=float(corps.get("x") or 0), y=float(corps.get("y") or 0),
                                               auteur="studio")
    return 404, {"erreur": "Route inconnue."}
