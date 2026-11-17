"""Projection commune du relevé structuré, de la mémoire documentaire et du graphe."""
from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import urlsplit, urlunsplit

from . import memoire, rag


MESURES = {
    "largeur": "Largeur observée (px)", "hauteur": "Hauteur observée (px)",
    "elements_observes": "Éléments DOM observés", "conteneurs_grid": "Conteneurs CSS grid",
    "conteneurs_flex": "Conteneurs CSS flex", "controles_sans_libelle_apparent": "Contrôles sans libellé apparent",
    "canvas": "Canvas", "videos": "Vidéos",
}
STRUCTURE = {
    "entete": "En-tête", "navigation": "Zones de navigation", "principal": "Contenu principal", "pied": "Pied de page",
    "images": "Images", "boutons": "Boutons", "formulaires": "Formulaires", "hauteur_page": "Hauteur de page (px)",
}
FAMILLES_TOKENS = {
    "espacement": ("mesure", "Espacements récurrents"),
    "rayon": ("mesure", "Rayons récurrents"),
    "typographie": ("typographie", "Styles typographiques récurrents"),
    "couleur": ("palette", "Couleurs CSS récurrentes"),
}
MAX_OBSERVATIONS = 200  # couvre les champs bornés du pilote, y compris les preuves des deux écrans
_SEPARATEUR = "\n\x00\n"
_COURRIEL = re.compile(r"(?<![\w.+-])[a-z0-9._+%'-]+@[a-z0-9.-]+\.[a-z]{2,}(?![\w.-])", re.I)


def expurger(texte: str) -> str:
    """Texte destiné à une preuve ou une synthèse, sans secrets ni adresses de courriel."""
    return memoire.expurger(_COURRIEL.sub("[adresse expurgée]", texte))


def _objet(valeur) -> dict:
    return valeur if isinstance(valeur, dict) else {}


def _liste(valeur, limite: int) -> list:
    return valeur[:limite] if isinstance(valeur, list) else []


def _valeur(valeur) -> str:
    if isinstance(valeur, bool):
        return "observé" if valeur else "absent"
    if isinstance(valeur, (str, int, float)):
        return " ".join(str(valeur).replace("\x00", "").split())[:280]
    return ""


def _faits(donnees: dict, champs: dict) -> str:
    return "\n".join(f"{libelle} : {valeur}" for cle, libelle in champs.items() if (valeur := _valeur(donnees.get(cle))))


def adresse(valeur) -> str:
    """Le RAG conserve l’itinéraire observé, sans paramètres URL ni identifiants de connexion."""
    if not isinstance(valeur, str):
        return ""
    try:
        p = urlsplit(valeur)
        if p.scheme in ("http", "https") and p.hostname and not (p.username or p.password):
            return urlunsplit((p.scheme, p.netloc, p.path or "/", "", ""))
    except ValueError:
        pass
    return ""


def _justificatif(fichiers: dict, ecran: str | None, role: str | None) -> dict:
    if role:
        return _objet(fichiers.get(role))
    ecran = ecran or "bureau"
    return _objet(fichiers.get(f"{ecran}_page") or fichiers.get(f"{ecran}_vue") or fichiers.get("original"))


def _releves(meta: dict, ajouter) -> None:
    releves = _objet(meta.get("releve"))
    for ecran in ("bureau", "mobile"):
        releve = _objet(releves.get(ecran))
        mesures = _objet(releve.get("mesures"))
        for cle, titre in MESURES.items():
            if cle in mesures:
                ajouter("mesure", titre, _faits(mesures, {cle: titre}), ecran=ecran)
        for element in _liste(releve.get("elements"), 24):
            e = _objet(element)
            titre = " · ".join(filter(None, (_valeur(e.get("role")), _valeur(e.get("nom")))))
            ajouter("element", titre or "Élément du DOM", _faits(e, {
                "role": "Rôle", "nom": "Libellé", "largeur": "Largeur (px)", "hauteur": "Hauteur (px)",
                "affichage": "Affichage CSS", "espacement": "Espacement CSS", "rayon": "Rayon CSS",
                "police": "Police", "taille": "Taille du texte", "alignement": "Alignement",
                "colonnes": "Colonnes de grille", "selecteur": "Sélecteur CSS",
                "parent_selecteur": "Conteneur parent", "position": "Position CSS", "couleur": "Couleur du texte",
                "fond": "Couleur de fond", "padding": "Espacement intérieur", "interligne": "Interligne",
                "graisse": "Graisse",
            }), ecran=ecran, zone=e, element=e)
        for mouvement in _liste(releve.get("mouvements"), 16):
            m = _objet(mouvement)
            titre = " · ".join(filter(None, (_valeur(m.get("nature")), _valeur(m.get("propriete")))))
            ajouter("mouvement", titre or "Mouvement observé", _faits(m, {
                "nature": "Nature", "duree": "Durée", "courbe": "Courbe", "propriete": "Propriété ou animation",
            }), ecran=ecran)
        tokens = _objet(releve.get("tokens"))
        for famille, (type_, titre) in FAMILLES_TOKENS.items():
            lignes = []
            for token in _liste(tokens.get(famille), 8):
                token = _objet(token)
                valeur, occurrences = _valeur(token.get("valeur")), token.get("occurrences")
                if valeur and type(occurrences) is int and 0 < occurrences <= 450:
                    lignes.append(f"{valeur} · {occurrences} éléments observés")
            if lignes:
                ajouter(type_, titre, "\n".join(lignes), ecran=ecran)
    bureau, mobile = (_objet(_objet(releves.get(ecran)).get("mesures")) for ecran in ("bureau", "mobile"))
    ecarts = []
    if bureau and mobile:
        for cle, titre in MESURES.items():
            a, b = bureau.get(cle), mobile.get(cle)
            if type(a) is int and type(b) is int and a != b:
                ecarts.append(f"{titre} : {a} sur ordinateur, {b} sur mobile.")
    elements_bureau = {e.get("selecteur"): e for e in _liste(_objet(releves.get("bureau")).get("elements"), 24)
                       if isinstance(e, dict) and e.get("selecteur")}
    elements_mobile = {e.get("selecteur"): e for e in _liste(_objet(releves.get("mobile")).get("elements"), 24)
                       if isinstance(e, dict) and e.get("selecteur")}
    for selecteur in sorted(elements_bureau.keys() & elements_mobile.keys()):
        a, b = elements_bureau[selecteur], elements_mobile[selecteur]
        changements = [f"{libelle} de {_valeur(a.get(cle))} à {_valeur(b.get(cle))}"
                       for cle, libelle in (("affichage", "affichage"), ("colonnes", "colonnes"),
                                           ("taille", "taille du texte"), ("espacement", "espacement"))
                       if a.get(cle) and b.get(cle) and a[cle] != b[cle]]
        if changements:
            nom = _valeur(a.get("nom")) or _valeur(a.get("role")) or "Élément"
            ecarts.append(nom + " · " + " · ".join(changements))
        if len(ecarts) >= len(MESURES) + 6:
            break
    if ecarts:
        ajouter("comparaison", "Écarts entre ordinateur et mobile", "\n".join(ecarts))


def projeter(reference_id: str, meta: dict, fichiers: dict, *, capture_le: float | None,
             source: str = "") -> list[dict]:
    """Observe seulement les champs attendus. Chaque unité porte sa source et un ID indépendant de l’index."""
    recueillies: list[tuple[str, str, str, str | None, dict, dict]] = []

    def ajouter(type_: str, titre: str, texte: str, *, ecran: str | None = None, role: str | None = None,
                zone: dict | None = None, element: dict | None = None) -> None:
        if not texte:
            return
        fichier = _justificatif(fichiers, ecran, role)
        preuve = {"reference_id": reference_id, "capture_le": capture_le}
        if fichier:
            preuve.update({"asset_id": fichier["asset_id"], "capture_url": fichier["url"]})
        if zone and fichier and type(y := zone.get("y")) is int and type(h := zone.get("hauteur")) is int:
            if 0 <= y < fichier["hauteur"] and h > 0:
                preuve["zone"] = {"y": y, "hauteur": min(h, fichier["hauteur"] - y), "largeur": fichier["largeur"]}
        geometrie = {}
        if element and all(type(element.get(k)) is int for k in ("x", "y", "largeur", "hauteur")):
            geometrie = {k: element[k] for k in ("x", "y", "largeur", "hauteur")}
            for cle in ("selecteur", "parent_selecteur"):
                valeur = element.get(cle)
                if isinstance(valeur, str) and len(valeur) <= 512 and re.fullmatch(
                        r"[a-z][a-z0-9-]*:nth-of-type\([1-9][0-9]{0,5}\)(?: > [a-z][a-z0-9-]*:nth-of-type\([1-9][0-9]{0,5}\)){0,23}",
                        valeur):
                    geometrie[cle] = valeur
            if preuve.get("zone"):
                preuve["zone"].update({"x": max(0, element["x"]), "largeur_element": element["largeur"]})
        recueillies.append((type_, titre, texte, ecran, preuve, geometrie))

    if source:
        contexte = _faits(meta, {"langue": "Langue", "statut_http": "Statut HTTP", "tronquee": "Capture tronquée",
                                 "bac_a_sable": "Bac à sable", "selecteur": "Sélecteur CSS ciblé"})
        perimetre = _faits(_objet(meta.get("perimetre")), {"type": "Périmètre", "mobile_erreur": "Limite du relevé mobile"})
        ajouter("capture", "Contexte de la capture", "\n".join(filter(None, (adresse(source), contexte, perimetre))))
        reseau = _objet(meta.get("reseau"))
        charge = _faits(reseau, {"connexions": "Connexions", "octets": "Octets de la capture"})
        if charge:
            refus = len(_liste(reseau.get("refus"), 20))
            ajouter("capture", "Charge observée de la capture", f"{charge}\nRefus consignés par le garde : {refus}")
    structure = _objet(meta.get("structure"))
    ajouter("structure", "Organisation de la page", _faits(structure, STRUCTURE))
    ajouter("structure", "Section d’ouverture", _faits(_objet(structure.get("heros")), {
        "titre": "Titre", "appel_action": "Appel à l’action", "visible_d_emblee": "Visible d’emblée",
    }))
    for item in _liste(meta.get("palette"), 8):
        palette = _objet(item)
        hex_ = _valeur(palette.get("hex"))
        if hex_:
            ajouter("palette", f"Couleur dominante {hex_}", _faits(palette, {"hex": "Couleur", "part": "Part de pixels"}))
    for role, libelle in (("fond", "Fond"), ("texte", "Texte"), ("accent", "Accent"), ("lien", "Lien")):
        couleur = _valeur(_objet(meta.get("couleurs_css")).get(role))
        if couleur:
            ajouter("palette", f"Couleur CSS · {libelle}", f"{libelle} : {couleur}")
    polices = _objet(meta.get("polices"))
    for cle, titre in (("corps", "Corps"), ("titre", "Titre"), ("sous_titre", "Sous-titre"), ("bouton", "Bouton"), ("code", "Code")):
        nom = _valeur(_objet(polices.get("roles")).get(cle))
        if nom:
            ajouter("typographie", f"Police · {titre}", f"{titre} : {nom}")
    for police in _liste(polices.get("declarees"), 20):
        if nom := _valeur(police):
            ajouter("typographie", f"Police déclarée · {nom}", f"Police déclarée : {nom}")
    for item in _liste(meta.get("liens"), 40):
        lien = _objet(item)
        if url := adresse(lien.get("url")):
            nom = _valeur(lien.get("texte")) or url
            zone = {"entete": "En-tête", "pied": "Pied de page", "corps": "Corps"}.get(lien.get("zone"), "")
            portee = "externe" if lien.get("externe") is True else "interne"
            ajouter("lien", nom, "\n".join(filter(None, (nom, url, f"Lien {portee}", zone))))
    _releves(meta, ajouter)

    ajouter("media", "Propriétés du média", _faits(_objet(meta.get("media")), {
        "nom": "Nom", "mime": "MIME", "taille": "Taille (octets)", "largeur": "Largeur (px)", "hauteur": "Hauteur (px)",
        "duree": "Durée (s)", "codec_video": "Codec vidéo", "codec_audio": "Codec audio",
    }), role="original")
    storyboard = _objet(meta.get("storyboard"))
    for role, fichier in sorted(fichiers.items()):
        if role in storyboard:
            ajouter("media", f"Storyboard · {_valeur(storyboard[role])} s", f"Image à {_valeur(storyboard[role])} secondes", role=role)
        elif libelle := {"bureau_vue": "Vue bureau", "bureau_page": "Page bureau", "mobile_vue": "Vue mobile",
                         "mobile_page": "Page mobile", "original": "Fichier original"}.get(role):
            format_ = _faits(fichier, {"largeur": "Largeur (px)", "hauteur": "Hauteur (px)", "sha256": "Empreinte SHA-256"})
            ajouter("preuve", libelle, f"{libelle}\n{format_}".strip(), role=role)

    retenues = recueillies[:MAX_OBSERVATIONS]
    if not retenues:
        return []
    # Expurger le lot en une fois, y compris les secrets connus du poste. Le séparateur ne peut pas venir de la source.
    brut = _SEPARATEUR.join(champ.replace("\x00", "") for _, titre, texte, _, _, _ in retenues for champ in (titre, texte))
    nettoye = expurger(brut).split(_SEPARATEUR)
    observations: dict[str, dict] = {}
    groupes_tokens = set(FAMILLES_TOKENS.values())
    for (type_, _, _, ecran, preuve, element), titre, texte in zip(retenues, nettoye[::2], nettoye[1::2]):
        titre, texte = titre.strip()[:200], texte.strip()
        morceaux = [texte[:rag.FRAGMENT_MAX]]
        if (type_, titre) in groupes_tokens:
            # Chaque valeur doit rester entière dans une preuve et son fragment RAG, après expurgation.
            morceaux, courant = [], ""
            for ligne in texte.splitlines():
                if courant and len(courant) + len(ligne) + 1 > rag.FRAGMENT_MAX:
                    morceaux.append(courant)
                    courant = ""
                courant = courant + "\n" + ligne if courant else ligne
            if courant:
                morceaux.append(courant)
        for texte in morceaux:
            empreinte = json.dumps((reference_id, type_, ecran, titre, texte), ensure_ascii=False).encode()
            id_ = "OB-" + hashlib.sha256(empreinte).hexdigest()[:12]
            observations.setdefault(id_, {"id": id_, "type": type_, "titre": titre, "texte": texte,
                                          **({"ecran": ecran} if ecran else {}), **({"element": element} if element else {}),
                                          "preuve": preuve, "nature": "donnee_non_fiable"})
            if len(observations) >= MAX_OBSERVATIONS:
                return list(observations.values())
    return list(observations.values())
