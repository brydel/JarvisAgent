"""Board V2 : objets spatiaux (géométrie, priorité, métadonnées), relations, fichiers multimédias, commentaires.

S'appuie sur le moteur de missions (mêmes transactions, mêmes backends SQLite / PostgreSQL, même journal
d'événements, contrôle du tenant à chaque requête). Règles :
- validation serveur de chaque champ (types, bornes, priorité P1–P3) ; versions pour détecter les conflits ;
- suppression douce (`supprime`) : annuler une suppression restaure l'objet et ses relations ;
- un fichier n'est accepté qu'après reconnaissance de son type par ses premiers octets (jamais par son nom), dans
  la limite de taille de sa famille ; stocké sous l'état de Jarvis, servi seulement par l'API authentifiée ;
- les événements ne contiennent ni contenu ni média (identifiants et champs modifiés seulement).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import subprocess
import tempfile
import time
from pathlib import Path

from . import config
from .missions import MissionError, PRIORITES, _evenement, _id, transaction, _connecter

ESPACE_MAX = 80
MO = 1024 * 1024
LIMITES = {"image": 25 * MO, "audio": 150 * MO, "video": 500 * MO, "pdf": 60 * MO}
GEOMETRIE_MAX = 100_000.0
TAILLE_MIN, TAILLE_MAX = 40.0, 4000.0
CHAMPS_MAJ = ("x", "y", "largeur", "hauteur", "z", "priorite", "meta", "contenu", "verrouille", "parent_id")
STYLES_LIEN = ("defaut", "inspire", "alimente", "utilise", "depend")
CLES_CHEF = ("jarvis_resume", "propositions", "jarvis_mission")  # écrites par le moteur seul


# --- Reconnaissance du type par les octets ---------------------------------------------------------------

def reconnaitre(entete: bytes) -> tuple[str, str, str] | None:
    """(famille, mime, extension) d'après les premiers octets, ou None. Le nom de fichier n'est jamais cru."""
    e = entete
    if e.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image", "image/png", "png"
    if e[:3] == b"\xff\xd8\xff":
        return "image", "image/jpeg", "jpg"
    if e[:6] in (b"GIF87a", b"GIF89a"):
        return "image", "image/gif", "gif"
    if e[:4] == b"RIFF" and e[8:12] == b"WEBP":
        return "image", "image/webp", "webp"
    if e[:4] == b"\x00\x00\x01\x00":
        return "image", "image/x-icon", "ico"  # favicons ; le SVG est refusé exprès (il peut contenir du script)
    if e[:4] == b"RIFF" and e[8:12] == b"WAVE":
        return "audio", "audio/wav", "wav"
    if e[:3] == b"ID3" or (len(e) > 1 and e[0] == 0xFF and (e[1] & 0xE0) == 0xE0):
        return "audio", "audio/mpeg", "mp3"
    if e[:4] == b"OggS":
        return ("video", "video/ogg", "ogv") if b"theora" in e[:200] else ("audio", "audio/ogg", "ogg")
    if e[:4] == b"fLaC":
        return "audio", "audio/flac", "flac"
    if e[:4] == b"\x1aE\xdf\xa3":
        return "video", "video/webm", "webm"
    if e[4:8] == b"ftyp":
        marque = e[8:12]
        if marque in (b"M4A ", b"M4B "):
            return "audio", "audio/mp4", "m4a"
        if marque[:2] == b"qt":
            return "video", "video/quicktime", "mov"
        return "video", "video/mp4", "mp4"
    if e.startswith(b"%PDF-"):
        return "pdf", "application/pdf", "pdf"
    return None


def _dimensions_image(chemin: Path, mime: str) -> dict:
    """Largeur et hauteur lues dans l'en-tête (PNG, GIF, WebP, JPEG), sans décoder l'image."""
    try:
        with chemin.open("rb") as fh:
            d = fh.read(512 * 1024)
        if mime == "image/png":
            l, h = struct.unpack(">II", d[16:24])
        elif mime == "image/gif":
            l, h = struct.unpack("<HH", d[6:10])
        elif mime == "image/webp":
            if d[12:16] == b"VP8X":
                l = 1 + int.from_bytes(d[24:27], "little")
                h = 1 + int.from_bytes(d[27:30], "little")
            elif d[12:16] == b"VP8 ":
                l, h = (v & 0x3FFF for v in struct.unpack("<HH", d[26:30]))
            else:  # VP8L
                b = int.from_bytes(d[21:25], "little")
                l, h = (b & 0x3FFF) + 1, ((b >> 14) & 0x3FFF) + 1
        else:  # JPEG : premier marqueur SOFn
            i = 2
            while i < len(d) - 9:
                if d[i] != 0xFF:
                    i += 1
                    continue
                m = d[i + 1]
                if m in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    h, l = struct.unpack(">HH", d[i + 5:i + 9])
                    break
                i += 2 + struct.unpack(">H", d[i + 2:i + 4])[0]
            else:
                return {}
        return {"largeur": int(l), "hauteur": int(h)} if 0 < l < 100_000 and 0 < h < 100_000 else {}
    except (OSError, struct.error, ValueError, IndexError):
        return {}


def _sonder_media(chemin: Path) -> dict:
    """Durée et dimensions par ffprobe (si présent), borné à 20 s. Fichier non fiable : aucune option du fichier n'est
    interprétée, aucune sortie n'est exécutée."""
    if not shutil.which("ffprobe"):
        return {}
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams",
                            str(chemin)], capture_output=True, text=True, timeout=20)
        info = json.loads(r.stdout or "{}")
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return {}
    meta = {}
    try:
        meta["duree"] = round(float(info.get("format", {}).get("duration", 0)), 2)
    except (TypeError, ValueError):
        pass
    for s in info.get("streams", []):
        if s.get("codec_type") == "video" and s.get("width"):
            meta.update(largeur=int(s["width"]), hauteur=int(s["height"]), codec_video=str(s.get("codec_name", ""))[:20])
        if s.get("codec_type") == "audio":
            meta["codec_audio"] = str(s.get("codec_name", ""))[:20]
    return meta


def _vignette_video(chemin: Path, sortie: Path) -> bool:
    if not shutil.which("ffmpeg"):
        return False
    try:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1", "-i", str(chemin), "-frames:v", "1",
                        "-vf", "scale=640:-2", "-q:v", "4", str(sortie)], capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return sortie.exists() and sortie.stat().st_size > 0


def dossier_assets(tenant_id: str) -> Path:
    d = config.STATE_DIR / "board_assets" / hashlib.sha256(tenant_id.encode()).hexdigest()[:16]
    d.mkdir(parents=True, exist_ok=True)
    return d


def enregistrer_fichier(tenant_id: str, source: Path, nom: str, *, auteur: str, now: float | None = None) -> dict:
    """Range un fichier téléversé (déjà écrit dans un fichier temporaire par l'API). Le source est consommé."""
    now = now or time.time()
    with source.open("rb") as fh:
        entete = fh.read(4096)
    sorte = reconnaitre(entete)
    if sorte is None:
        source.unlink(missing_ok=True)
        raise MissionError("fichier", "type de fichier non pris en charge (image, audio, vidéo ou PDF reconnus par "
                                      "leur contenu)")
    famille, mime, ext = sorte
    taille = source.stat().st_size
    if taille > LIMITES[famille]:
        source.unlink(missing_ok=True)
        raise MissionError("fichier", f"fichier trop volumineux pour un {famille} ({taille // MO} Mo, "
                                      f"{LIMITES[famille] // MO} Mo au plus)")
    h = hashlib.sha256()
    with source.open("rb") as fh:
        for bloc in iter(lambda: fh.read(MO), b""):
            h.update(bloc)
    sha = h.hexdigest()
    nom = "".join(ch for ch in os.path.basename(nom or "") if ch.isprintable())[:160] or f"fichier.{ext}"
    with transaction(tenant_id) as c:
        existant = c.execute("SELECT * FROM board_assets WHERE tenant_id=? AND sha256=?", (tenant_id, sha)).fetchone()
    if existant:  # même contenu déjà stocké : rien de dupliqué
        source.unlink(missing_ok=True)
        return _asset_public(dict(existant))
    dossier = dossier_assets(tenant_id)
    fichier = dossier / f"{sha}.{ext}"
    shutil.move(str(source), fichier)
    os.chmod(fichier, 0o600)
    meta = {"famille": famille}
    if famille == "image":
        meta.update(_dimensions_image(fichier, mime))
    elif famille in ("audio", "video"):
        meta.update(_sonder_media(fichier))
    vignette_id = None
    if famille == "video":
        vig = dossier / f"{sha}.vignette.jpg"
        if _vignette_video(fichier, vig):
            os.chmod(vig, 0o600)
            vignette_id = _id("AS")
            with transaction(tenant_id) as c:
                c.execute("INSERT INTO board_assets (id, tenant_id, sha256, mime, taille, nom, fichier, meta, cree) "
                          "VALUES (?,?,?,?,?,?,?,?,?)",
                          (vignette_id, tenant_id, hashlib.sha256(vig.read_bytes()).hexdigest(), "image/jpeg",
                           vig.stat().st_size, f"vignette de {nom}", vig.name,
                           json.dumps({"famille": "image", **_dimensions_image(vig, "image/jpeg")}), now))
    aid = _id("AS")
    with transaction(tenant_id) as c:
        c.execute("INSERT INTO board_assets (id, tenant_id, sha256, mime, taille, nom, fichier, meta, vignette_id, cree) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (aid, tenant_id, sha, mime, taille, nom, fichier.name, json.dumps(meta), vignette_id, now))
        _evenement(c, tenant_id, "board_fichier", now=now, asset_id=aid, famille=famille, taille=taille, par=auteur)
        row = c.execute("SELECT * FROM board_assets WHERE id=?", (aid,)).fetchone()
    return _asset_public(dict(row))


def _asset_public(a: dict) -> dict:
    meta = json.loads(a.get("meta") or "{}")
    return {"id": a["id"], "mime": a["mime"], "taille": a["taille"], "nom": a["nom"], "famille": meta.get("famille"),
            "meta": meta, "vignette_id": a.get("vignette_id"), "url": f"/api/v2/fichiers/{a['id']}",
            "vignette_url": f"/api/v2/fichiers/{a['vignette_id']}" if a.get("vignette_id") else None}


def fichier(tenant_id: str, asset_id: str) -> tuple[Path, dict]:
    """Chemin et description d'un fichier du tenant. Le nom sur disque vient de la base, jamais de la requête."""
    c = _connecter(tenant_id)
    try:
        a = c.execute("SELECT * FROM board_assets WHERE id=? AND tenant_id=?", (asset_id, tenant_id)).fetchone()
    finally:
        c.close()
    if a is None:
        raise MissionError("inconnue", "fichier inconnu")
    chemin = dossier_assets(tenant_id) / a["fichier"]
    if not chemin.is_file():
        raise MissionError("inconnue", "fichier absent du stockage")
    return chemin, _asset_public(dict(a))


# --- Objets ------------------------------------------------------------------------------------------------

def _valider_maj(champs: dict) -> dict:
    propres = {}
    for k, v in champs.items():
        if k not in CHAMPS_MAJ:
            raise MissionError("board", f"champ non modifiable : {k}")
        if k in ("x", "y"):
            propres[k] = max(-GEOMETRIE_MAX, min(GEOMETRIE_MAX, float(v)))
        elif k in ("largeur", "hauteur"):
            propres[k] = max(TAILLE_MIN, min(TAILLE_MAX, float(v)))
        elif k == "z":
            propres[k] = max(-1_000_000, min(1_000_000, int(v)))
        elif k == "priorite":
            if v not in PRIORITES:
                raise MissionError("board", f"priorité inconnue : {v}")
            propres[k] = v
        elif k == "meta":
            if not isinstance(v, dict):
                raise MissionError("board", "meta doit être un objet")
            texte = json.dumps(v, ensure_ascii=False)
            if len(texte) > 20_000:
                raise MissionError("board", "métadonnées trop volumineuses")
            propres[k] = texte
        elif k == "contenu":
            if not isinstance(v, str) or len(v) > 50_000:
                raise MissionError("board", "contenu invalide (texte de 50 000 caractères au plus)")
            propres[k] = v
        elif k == "verrouille":
            propres[k] = 1 if v else 0
        elif k == "parent_id":
            propres[k] = v or None
    return propres


def mettre_a_jour(tenant_id: str, objet_id: str, champs: dict, *, version: int | None = None, par: str,
                  now: float | None = None) -> dict:
    """Modifie un objet. `version` : si fournie et différente de la version en base, conflit (code `conflit`)."""
    now = now or time.time()
    propres = _valider_maj(champs)
    if not propres:
        raise MissionError("board", "rien à modifier")
    with transaction(tenant_id) as c:
        o = c.execute("SELECT * FROM board_objets WHERE id=? AND tenant_id=? AND supprime=0",
                      (objet_id, tenant_id)).fetchone()
        if o is None:
            raise MissionError("inconnue", f"objet inconnu : {objet_id}")
        if version is not None and int(version) != o["version"]:
            raise MissionError("conflit", f"l'objet a été modifié ailleurs (version {o['version']}, reçue {version})")
        if o["verrouille"] and set(propres) & {"x", "y", "largeur", "hauteur"} and "verrouille" not in propres:
            raise MissionError("verrouille", "objet verrouillé : déverrouille-le avant de le déplacer")
        if propres.get("parent_id"):
            if propres["parent_id"] == objet_id or not c.execute(
                    "SELECT 1 FROM board_objets WHERE id=? AND tenant_id=? AND type='dossier' AND supprime=0",
                    (propres["parent_id"], tenant_id)).fetchone():
                raise MissionError("board", "dossier parent inconnu")
        if "meta" in propres:  # résumé et propositions appartiennent au chef : un client (même périmé) ne les efface pas
            ancienne = json.loads(o["meta"] or "{}")
            nouvelle = json.loads(propres["meta"])
            nouvelle.update({k: ancienne[k] for k in CLES_CHEF if k in ancienne})
            propres["meta"] = json.dumps(nouvelle, ensure_ascii=False)
        sets = ", ".join(f"{k}=?" for k in propres)
        c.execute(f"UPDATE board_objets SET {sets}, version=version+1, maj=? WHERE id=? AND tenant_id=?",
                  (*propres.values(), now, objet_id, tenant_id))
        _evenement(c, tenant_id, "board_maj", now=now, objet_id=objet_id, champs=sorted(propres), par=par)
        a_contextualiser = ("contenu" in propres and o["type"] in ("note", "texte") and not o["mission_id"]
                            and propres["contenu"].strip() not in ("", "Nouvelle note"))
    if a_contextualiser:  # première vraie écriture d'une note créée vide : le chef la lit
        from . import missions
        missions.lancer_contextualisation(tenant_id, objet_id, auteur=par, now=now)
    return {"version": o["version"] + 1}


def mettre_a_jour_lot(tenant_id: str, modifications: list[dict], *, par: str) -> list[dict]:
    """Plusieurs objets (déplacement d'une sélection) : une transaction par objet, échecs signalés un par un."""
    if len(modifications) > 500:
        raise MissionError("board", "500 modifications au plus par lot")
    sorties = []
    for m in modifications:
        try:
            v = mettre_a_jour(tenant_id, str(m.get("id")), m.get("champs") or {}, version=m.get("version"), par=par)
            sorties.append({"id": m.get("id"), "ok": True, **v})
        except (MissionError, TypeError, ValueError) as exc:
            sorties.append({"id": m.get("id"), "ok": False, "erreur": str(exc)})
    return sorties


def supprimer(tenant_id: str, ids: list[str], *, par: str, restaurer: bool = False, now: float | None = None) -> int:
    """Suppression douce (ou restauration) d'objets et des relations qui les touchent."""
    now = now or time.time()
    if not ids or len(ids) > 500:
        raise MissionError("board", "1 à 500 objets")
    etat = 0 if restaurer else 1
    with transaction(tenant_id) as c:
        n = 0
        for oid in ids:
            n += c.execute("UPDATE board_objets SET supprime=?, version=version+1, maj=? WHERE id=? AND tenant_id=?",
                           (etat, now, oid, tenant_id)).rowcount
            c.execute("UPDATE board_liens SET supprime=?, maj=? WHERE tenant_id=? AND (source_id=? OR cible_id=?)",
                      (etat, now, tenant_id, oid, oid))
        _evenement(c, tenant_id, "board_restaure" if restaurer else "board_supprime", now=now, objets=ids[:50], par=par)
        return n


def _mission_resume(c, tenant_id: str, mission_id: str) -> dict | None:
    m = c.execute("SELECT id, objectif, statut, cree FROM missions WHERE id=? AND tenant_id=?",
                  (mission_id, tenant_id)).fetchone()
    if m is None:
        return None
    taches = [dict(t) for t in c.execute(
        "SELECT id, type, niveau, statut, fournisseur_choisi, fournisseur, essais, raison FROM taches "
        "WHERE mission_id=? AND tenant_id=? ORDER BY cree, id", (mission_id, tenant_id))]
    faites = sum(1 for t in taches if t["statut"] == "SUCCEEDED")
    agents = [dict(a) for a in c.execute(
        "SELECT a.id, a.tache_id, a.fournisseur, a.issue, a.debut, a.fin, e.nom AS executant, t.type AS role, "
        "t.statut AS statut_tache FROM tentatives a JOIN taches t ON t.id=a.tache_id "
        "LEFT JOIN executants e ON e.id=a.executant_id WHERE a.tenant_id=? AND t.mission_id=? "
        "ORDER BY a.debut DESC", (tenant_id, mission_id))]
    attente = c.execute("SELECT COUNT(*) AS n FROM approbations WHERE tenant_id=? AND statut='en_attente' AND tache_id IN "
                        "(SELECT id FROM taches WHERE mission_id=?)", (tenant_id, mission_id)).fetchone()["n"]
    return {**dict(m), "taches": taches, "faites": faites, "total": len(taches),
            "progression": round(100 * faites / len(taches)) if taches else 0, "agents": agents,
            "approbations_en_attente": attente}


def objets(tenant_id: str, espace: str) -> dict:
    """Tout le Board d'un espace : objets (avec fichier et résumé de mission réels), relations, compteurs."""
    c = _connecter(tenant_id)
    try:
        objs = []
        for o in c.execute("SELECT * FROM board_objets WHERE tenant_id=? AND espace=? AND supprime=0 ORDER BY z, cree",
                           (tenant_id, espace)):
            d = dict(o)
            d["meta"] = json.loads(d.get("meta") or "{}")
            if d.get("asset_id"):
                a = c.execute("SELECT * FROM board_assets WHERE id=? AND tenant_id=?",
                              (d["asset_id"], tenant_id)).fetchone()
                d["asset"] = _asset_public(dict(a)) if a else None
            if d.get("mission_id"):
                d["mission"] = _mission_resume(c, tenant_id, d["mission_id"])
                arts = c.execute("SELECT id, fournisseur, factice, revue, contenu FROM artefacts WHERE mission_id=? "
                                 "AND tenant_id=? ORDER BY cree", (d["mission_id"], tenant_id)).fetchall()
                d["artefacts"] = [dict(a) for a in arts]
            d["commentaires"] = c.execute("SELECT COUNT(*) AS n FROM board_commentaires WHERE tenant_id=? AND objet_id=?",
                                          (tenant_id, d["id"])).fetchone()["n"]
            objs.append(d)
        liens = [dict(l) for l in c.execute(
            "SELECT * FROM board_liens WHERE tenant_id=? AND espace=? AND supprime=0 ORDER BY cree",
            (tenant_id, espace))]
        return {"espace": espace, "objets": objs, "liens": liens}
    finally:
        c.close()


# --- Relations ---------------------------------------------------------------------------------------------

def lier(tenant_id: str, espace: str, source_id: str, cible_id: str, *, libelle: str = "", style: str = "defaut",
         par: str, now: float | None = None) -> str:
    now = now or time.time()
    if source_id == cible_id:
        raise MissionError("board", "une relation relie deux objets différents")
    if style not in STYLES_LIEN:
        raise MissionError("board", f"style de relation inconnu : {style}")
    with transaction(tenant_id) as c:
        for oid in (source_id, cible_id):
            if not c.execute("SELECT 1 FROM board_objets WHERE id=? AND tenant_id=? AND espace=? AND supprime=0",
                             (oid, tenant_id, espace)).fetchone():
                raise MissionError("inconnue", f"objet inconnu : {oid}")
        existant = c.execute("SELECT id FROM board_liens WHERE tenant_id=? AND source_id=? AND cible_id=? AND supprime=0",
                             (tenant_id, source_id, cible_id)).fetchone()
        if existant:
            return existant["id"]
        lid = _id("BL")
        c.execute("INSERT INTO board_liens (id, tenant_id, espace, source_id, cible_id, libelle, style, cree, maj) "
                  "VALUES (?,?,?,?,?,?,?,?,?)", (lid, tenant_id, espace, source_id, cible_id, libelle[:60], style, now, now))
        _evenement(c, tenant_id, "board_lien", now=now, lien_id=lid, source_id=source_id, cible_id=cible_id, par=par)
        return lid


def modifier_lien(tenant_id: str, lien_id: str, *, libelle: str | None = None, style: str | None = None,
                  supprime: bool | None = None, par: str, now: float | None = None) -> None:
    now = now or time.time()
    if style is not None and style not in STYLES_LIEN:
        raise MissionError("board", f"style de relation inconnu : {style}")
    with transaction(tenant_id) as c:
        l = c.execute("SELECT * FROM board_liens WHERE id=? AND tenant_id=?", (lien_id, tenant_id)).fetchone()
        if l is None:
            raise MissionError("inconnue", "relation inconnue")
        c.execute("UPDATE board_liens SET libelle=?, style=?, supprime=?, maj=? WHERE id=? AND tenant_id=?",
                  ((libelle if libelle is not None else l["libelle"])[:60], style or l["style"],
                   int(supprime) if supprime is not None else l["supprime"], now, lien_id, tenant_id))
        _evenement(c, tenant_id, "board_lien_maj", now=now, lien_id=lien_id, par=par)


# --- Commentaires ------------------------------------------------------------------------------------------

def commenter(tenant_id: str, objet_id: str, texte: str, *, auteur: str, now: float | None = None) -> str:
    now = now or time.time()
    texte = texte.strip()
    if not texte or len(texte) > 4000:
        raise MissionError("board", "commentaire vide ou trop long (4 000 caractères au plus)")
    with transaction(tenant_id) as c:
        if not c.execute("SELECT 1 FROM board_objets WHERE id=? AND tenant_id=? AND supprime=0",
                         (objet_id, tenant_id)).fetchone():
            raise MissionError("inconnue", f"objet inconnu : {objet_id}")
        cid = _id("CM")
        c.execute("INSERT INTO board_commentaires VALUES (?,?,?,?,?,?)", (cid, tenant_id, objet_id, auteur, texte, now))
        _evenement(c, tenant_id, "board_commentaire", now=now, objet_id=objet_id, commentaire_id=cid, par=auteur)
        return cid


def commentaires(tenant_id: str, objet_id: str) -> list[dict]:
    c = _connecter(tenant_id)
    try:
        return [dict(r) for r in c.execute("SELECT * FROM board_commentaires WHERE tenant_id=? AND objet_id=? "
                                           "ORDER BY cree", (tenant_id, objet_id))]
    finally:
        c.close()


def fichier_temporaire() -> Path:
    d = config.STATE_DIR / "board_assets" / "televersements"
    d.mkdir(parents=True, exist_ok=True)
    fd, nom = tempfile.mkstemp(dir=d)
    os.close(fd)
    return Path(nom)


def nettoyer_orphelins(tenant_id: str, *, age_s: float = 86_400, now: float | None = None) -> int:
    """Supprime les fichiers du tenant qu'aucun objet (même supprimé) ne référence depuis plus d'un jour, et les
    téléversements interrompus. Les objets supprimés gardent leurs fichiers : l'annulation doit les retrouver."""
    now = now or time.time()
    n = 0
    c = _connecter(tenant_id)
    try:
        utilises = {r["asset_id"] for r in c.execute("SELECT asset_id FROM board_objets WHERE tenant_id=? "
                                                     "AND asset_id IS NOT NULL", (tenant_id,))}
        vignettes = {r["vignette_id"] for r in c.execute("SELECT vignette_id FROM board_assets WHERE tenant_id=? "
                                                         "AND vignette_id IS NOT NULL", (tenant_id,))}
        orphelins = [dict(a) for a in c.execute("SELECT * FROM board_assets WHERE tenant_id=? AND cree < ?",
                                                (tenant_id, now - age_s))
                     if a["id"] not in utilises and a["id"] not in vignettes]
    finally:
        c.close()
    for a in orphelins:
        (dossier_assets(tenant_id) / a["fichier"]).unlink(missing_ok=True)
        n += 1
    if orphelins:
        with transaction(tenant_id) as c:
            for a in orphelins:
                c.execute("UPDATE board_assets SET fichier=? WHERE id=? AND tenant_id=?",
                          (f"supprime-{a['id']}", a["id"], tenant_id))
    tmp = config.STATE_DIR / "board_assets" / "televersements"
    if tmp.is_dir():
        for f in tmp.iterdir():
            if f.is_file() and f.stat().st_mtime < now - 3600:
                f.unlink(missing_ok=True)
    return n
