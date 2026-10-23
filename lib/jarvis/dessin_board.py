"""Le chef dessine le Board : poser une carte dans le format voulu, la déplacer, la redimensionner, la colorer,
la rendre compacte, ranger tout un Board (grille, colonnes par type, flux suivant les liens) et grouper en dossier.

Tout passe par les mêmes fonctions que le Studio (board.mettre_a_jour, missions.board_ajouter) : versions, verrous
et événements sont respectés, et le Studio ouvert se met à jour en direct. Une carte verrouillée n'est jamais
déplacée ; rien n'est supprimé ici (le rangement ne retire rien : voir `jarvis board retirer`).
"""

from __future__ import annotations

from pathlib import Path

from . import board, missions

COULEURS = ("indigo", "violet", "rose", "orange", "jaune", "vert", "cyan", "gris")
FORMATS = ("note", "texte", "lien", "dossier", "image", "pdf", "audio", "video", "document")
TAILLES = {"note": (408, 320), "texte": (408, 240), "lien": (434, 356), "dossier": (378, 152), "image": (491, 309),
           "pdf": (348, 318), "audio": (462, 178), "video": (378, 178), "document": (348, 240)}
COMPACTE = (240, 96)
DISPOSITIONS = ("grille", "colonnes", "flux", "ligne")
ORDRE_TYPES = ("plan", "mission", "tache", "agents", "note", "texte", "lien", "image", "capture", "pdf", "document",
               "audio", "video", "dossier")


def _meta_options(*, titre=None, couleur=None, compact=None, tags=None) -> dict:
    meta = {}
    if titre is not None:
        meta["titre"] = str(titre)[:120]
    if couleur is not None:
        if couleur not in COULEURS + ("",):
            raise missions.MissionError("board", f"couleur inconnue : {couleur} (au choix : {', '.join(COULEURS)})")
        meta["couleur"] = couleur
    if compact is not None:
        meta["compact"] = bool(compact)
    if tags is not None:
        meta["tags"] = [t.strip().lstrip("#")[:30] for t in tags if t.strip()][:12]
    return meta


def poser(tenant: str, espace: str, *, format_: str = "note", contenu: str = "", titre: str = "", fichier: str = "",
          x: float | None = None, y: float | None = None, largeur: float | None = None, hauteur: float | None = None,
          couleur: str | None = None, compact: bool = False, tags: list[str] | None = None, priorite: str = "",
          dans: str = "", par: str, analyser: bool = False) -> dict:
    """Une carte dans le format voulu. Un fichier (image, PDF, audio, vidéo) est COPIÉ dans le Board."""
    from . import synchro
    if format_ not in FORMATS:
        raise missions.MissionError("board", f"format inconnu : {format_} (au choix : {', '.join(FORMATS)})")
    asset_id = None
    if fichier:
        source = Path(fichier).expanduser()
        if not source.is_file():
            raise missions.MissionError("inconnue", f"fichier introuvable : {fichier}")
        copie = board.fichier_temporaire()
        copie.write_bytes(source.read_bytes())  # enregistrer_fichier consomme sa source : on garde l'original
        a = board.enregistrer_fichier(tenant, copie, source.name, auteur=par)
        asset_id, format_ = a["id"], a["famille"] or "document"
        titre = titre or Path(source.name).stem
    l0, h0 = COMPACTE if compact else TAILLES.get(format_, (408, 320))
    l, h = float(largeur or l0), float(hauteur or h0)
    if x is None or y is None:
        x, y = synchro.position_libre(tenant, espace, l, h)
    meta = {"source": par if par in ("chef", "humain") else "chef",
            **_meta_options(titre=titre or (contenu.split("\n")[0][:80] if contenu else format_), couleur=couleur,
                            compact=compact or None, tags=tags)}
    o = missions.board_ajouter(tenant, espace, format_, contenu, auteur=par, x=float(x), y=float(y), largeur=l, hauteur=h,
                               priorite=priorite, meta=meta, asset_id=asset_id, analyser=False, contextualiser=analyser)
    if dans:
        board.mettre_a_jour(tenant, o["objet_id"], {"parent_id": dans}, par=par)
    return o


def modifier(tenant: str, objet_id: str, *, par: str, x=None, y=None, largeur=None, hauteur=None, contenu=None,
             titre=None, couleur=None, compact=None, tags=None, priorite=None, verrouille=None) -> dict:
    """Déplace, redimensionne, recolore, compacte ou réécrit une carte (les clés du chef sont préservées)."""
    o = _objet(tenant, objet_id)
    champs = {k: v for k, v in (("x", x), ("y", y), ("largeur", largeur), ("hauteur", hauteur), ("contenu", contenu),
                                ("priorite", priorite), ("verrouille", verrouille)) if v is not None}
    options = _meta_options(titre=titre, couleur=couleur, compact=compact, tags=tags)
    if options:
        champs["meta"] = {**o["meta"], **options}
    if compact is True and largeur is None and hauteur is None:
        champs.setdefault("largeur", COMPACTE[0])
        champs.setdefault("hauteur", COMPACTE[1])
    if not champs:
        raise missions.MissionError("board", "rien à modifier")
    return board.mettre_a_jour(tenant, objet_id, champs, par=par)


def _objet(tenant: str, objet_id: str) -> dict:
    from . import synchro
    o = synchro._objet(tenant, objet_id)
    if o is None or o["supprime"]:
        raise missions.MissionError("inconnue", f"carte inconnue : {objet_id}")
    return o


def _cibles(tenant: str, espace: str, ids: list[str] | None, types: list[str] | None) -> list[dict]:
    objs = [o for o in board.objets(tenant, espace)["objets"] if not o.get("parent_id")]
    if ids:
        absents = set(ids) - {o["id"] for o in objs}
        if absents:
            raise missions.MissionError("inconnue", f"carte(s) absente(s) du Board {espace} : {', '.join(sorted(absents)[:5])}")
        objs = [o for o in objs if o["id"] in ids]
    if types:
        objs = [o for o in objs if o["type"] in types]
    return objs


def ranger(tenant: str, espace: str, *, disposition: str = "grille", ids: list[str] | None = None,
           types: list[str] | None = None, x0: float = 0, y0: float = 0, espacement: float = 60,
           colonnes: int | None = None, par: str) -> dict:
    """Range des cartes sans rien retirer :
    - grille : en lignes, du plus important au moins important (plan, mission, tâche, équipe, puis le reste) ;
    - colonnes : une colonne par type de carte ;
    - flux : de gauche à droite en suivant les liens (une source avant ce qu'elle alimente) ;
    - ligne : toutes sur une ligne."""
    if disposition not in DISPOSITIONS:
        raise missions.MissionError("board", f"disposition inconnue : {disposition} ({', '.join(DISPOSITIONS)})")
    objs = [o for o in _cibles(tenant, espace, ids, types) if not o.get("verrouille")]
    if not objs:
        return {"deplacees": 0, "ignorees": 0}
    rang = {t: i for i, t in enumerate(ORDRE_TYPES)}
    objs.sort(key=lambda o: (rang.get(o["type"], 99), o["cree"]))
    positions: dict[str, tuple[float, float]] = {}
    if disposition in ("grille", "ligne"):
        n = len(objs) if disposition == "ligne" else (colonnes or max(1, round(len(objs) ** 0.5 + 0.49)))
        x, y, haut_ligne = x0, y0, 0.0
        for i, o in enumerate(objs):
            if i and i % n == 0:
                x, y, haut_ligne = x0, y + haut_ligne + espacement, 0.0
            positions[o["id"]] = (x, y)
            x += (o["largeur"] or 400) + espacement
            haut_ligne = max(haut_ligne, o["hauteur"] or 300)
    elif disposition == "colonnes":
        x = x0
        for t in sorted({o["type"] for o in objs}, key=lambda t: rang.get(t, 99)):
            y, large = y0, 0.0
            for o in [o for o in objs if o["type"] == t]:
                positions[o["id"]] = (x, y)
                y += (o["hauteur"] or 300) + espacement
                large = max(large, o["largeur"] or 400)
            x += large + espacement * 2
    else:  # flux : niveau = plus long chemin depuis une source, dans le graphe des liens du Board
        liens = board.objets(tenant, espace)["liens"]
        ids_set = {o["id"] for o in objs}
        succ: dict[str, list[str]] = {i: [] for i in ids_set}
        entrants = {i: 0 for i in ids_set}
        for l in liens:
            if l["source_id"] in ids_set and l["cible_id"] in ids_set and l["source_id"] != l["cible_id"]:
                succ[l["source_id"]].append(l["cible_id"])
                entrants[l["cible_id"]] += 1
        niveau = {i: 0 for i in ids_set}
        file = [i for i in ids_set if entrants[i] == 0] or [objs[0]["id"]]
        vus = 0
        while file and vus < 10 * len(ids_set):  # borne : un cycle ne fait pas tourner en rond
            i = file.pop(0)
            vus += 1
            for j in succ[i]:
                if niveau[j] < niveau[i] + 1:
                    niveau[j] = niveau[i] + 1
                    file.append(j)
        x = x0
        for n in sorted(set(niveau.values())):
            y, large = y0, 0.0
            for o in [o for o in objs if niveau[o["id"]] == n]:
                positions[o["id"]] = (x, y)
                y += (o["hauteur"] or 300) + espacement
                large = max(large, o["largeur"] or 400)
            x += large + espacement * 2
    mods = [{"id": i, "champs": {"x": round(px), "y": round(py)}} for i, (px, py) in positions.items()]
    resultats = board.mettre_a_jour_lot(tenant, mods, par=par)
    return {"deplacees": sum(1 for r in resultats if r["ok"]), "ignorees": sum(1 for r in resultats if not r["ok"]),
            "disposition": disposition}


def reduire(tenant: str, espace: str, *, echelle: float = 0.6, ids: list[str] | None = None,
            types: list[str] | None = None, compact: bool = False, par: str) -> dict:
    """Réduit (ou agrandit, échelle > 1) des cartes ; `compact` les passe en vignette (titre et icône seulement)."""
    if not 0.1 <= echelle <= 3:
        raise missions.MissionError("board", "échelle entre 0.1 et 3")
    n = 0
    for o in _cibles(tenant, espace, ids, types):
        if o.get("verrouille"):
            continue
        champs = {"largeur": max(board.TAILLE_MIN, round((o["largeur"] or 400) * echelle)),
                  "hauteur": max(board.TAILLE_MIN, round((o["hauteur"] or 300) * echelle))}
        if compact:
            champs.update(largeur=COMPACTE[0], hauteur=COMPACTE[1], meta={**o["meta"], "compact": True})
        board.mettre_a_jour(tenant, o["id"], champs, par=par)
        n += 1
    return {"modifiees": n}


def grouper(tenant: str, espace: str, ids: list[str], *, titre: str, par: str, couleur: str | None = None) -> dict:
    """Range des cartes dans un dossier (nouveau), posé à l'endroit de la première."""
    objs = _cibles(tenant, espace, ids, None)
    if not objs:
        raise missions.MissionError("board", "aucune carte à grouper")
    d = missions.board_ajouter(tenant, espace, "dossier", "", auteur=par, x=min(o["x"] for o in objs),
                               y=min(o["y"] for o in objs), largeur=378, hauteur=152,
                               meta={"titre": titre[:120], "source": "chef", **_meta_options(couleur=couleur)},
                               analyser=False, contextualiser=False)
    for o in objs:
        board.mettre_a_jour(tenant, o["id"], {"parent_id": d["objet_id"]}, par=par)
    return {"dossier_id": d["objet_id"], "cartes": len(objs)}
