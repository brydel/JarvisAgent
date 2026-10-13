"""Contrôle technique des livrables du studio : vidéos, images et documents.

Ce contrôle est objectif et rapide (ffprobe + ffmpeg). Il ne remplace pas le regard : il produit
aussi une planche-contact (une image qui montre la vidéo en 12 vignettes) que l'agent, le
relecteur et le chef regardent avant toute livraison.
"""

from __future__ import annotations

import json
import re
import shutil
import struct
import subprocess
from pathlib import Path

VIDEOS = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
IMAGES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
DOCUMENTS = {".pdf", ".md", ".txt", ".html", ".csv", ".json", ".zip", ".docx", ".pptx", ".xlsx", ".srt", ".vtt"}

DEFAUTS = {
    # fps_min 23,5 : le 23,976 images/s du cinéma est légitime.
    "duree_min": 5.0, "duree_max": 180.0, "cote_min": 720, "fps_min": 23.5, "taille_max_mo": 49.0,
    "noir_max_pct": 8.0, "noir_bord_max": 1.5, "fige_max": 8.0, "fige_max_pct": 60.0,
}


class StudioError(RuntimeError):
    pass


def genre(path: Path) -> str:
    ext = path.suffix.lower()
    return "video" if ext in VIDEOS else "image" if ext in IMAGES else "document" if ext in DOCUMENTS else ""


def outils_presents() -> bool:
    return bool(shutil.which("ffprobe") and shutil.which("ffmpeg"))


def sonder(path: Path) -> dict:
    """Métadonnées du fichier (ffprobe). Lève StudioError s'il est illisible."""
    if not shutil.which("ffprobe"):
        raise StudioError("ffprobe introuvable : installe ffmpeg (sudo apt install ffmpeg)")
    try:
        res = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams",
                              str(path)], capture_output=True, text=True, timeout=60)
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise StudioError(f"ffprobe : {exc}") from exc
    if res.returncode != 0:
        raise StudioError((res.stderr.strip().splitlines() or ["fichier illisible"])[-1])
    try:
        data = json.loads(res.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise StudioError("réponse illisible de ffprobe") from exc
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    if not video:
        raise StudioError("aucune piste vidéo ou image dans ce fichier")

    def _ratio(v) -> float:
        try:
            a, _, b = str(v).partition("/")
            return float(a) / float(b or 1)
        except (ValueError, ZeroDivisionError):
            return 0.0

    def _float(v) -> float:
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    return {
        "duree": _float(data.get("format", {}).get("duration")) or _float(video.get("duration")),
        "largeur": int(video.get("width") or 0), "hauteur": int(video.get("height") or 0),
        "fps": _ratio(video.get("avg_frame_rate")) or _ratio(video.get("r_frame_rate")),
        "codec": video.get("codec_name") or "", "pix_fmt": video.get("pix_fmt") or "",
        "audio": (audio or {}).get("codec_name") or "",
        "octets": int(_float(data.get("format", {}).get("size"))) or path.stat().st_size,
    }


_BLACK = re.compile(r"black_start:(?P<s>[\d.]+)\s+black_end:(?P<e>[\d.]+)")
_FREEZE_S = re.compile(r"freeze_start:\s*(?P<s>[\d.]+)")
_FREEZE_E = re.compile(r"freeze_end:\s*(?P<e>[\d.]+)")
_SILENCE = re.compile(r"silence_duration:\s*(?P<d>[\d.]+)")
_FRAME = re.compile(r"^frame=\s*(\d+)", re.MULTILINE)
_ERREUR_DECODAGE = re.compile(r"Invalid data found|Error while decoding|error reading|partial file|"
                              r"moov atom not found|Invalid NAL|corrupt", re.IGNORECASE)


def detecter(path: Path, duree: float, avec_audio: bool = False) -> dict:
    """Écrans noirs, images figées, silence, et ce que ffmpeg a réellement pu décoder.

    Renvoie des listes d'intervalles (début, fin) en secondes, le nombre d'images décodées et les
    erreurs de décodage : l'en-tête d'un fichier tronqué annonce une durée qu'il ne contient plus.
    """
    # Noir : presque toute l'image sous 3 % de luminosité. Un écran sombre (thème nuit, #0B0D12) avec
    # un peu de texte n'est pas un écran noir.
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-progress", "pipe:1", "-i", str(path),
           "-vf", "blackdetect=d=0.4:pic_th=0.995:pix_th=0.03,freezedetect=n=-55dB:d=2"]
    cmd += ["-af", "silencedetect=n=-50dB:d=1"] if avec_audio else ["-an"]
    cmd += ["-f", "null", "-"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=max(120, int(duree * 6) + 60))
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise StudioError(f"analyse ffmpeg : {exc}") from exc
    log = res.stderr
    noirs = [(float(m["s"]), float(m["e"])) for m in _BLACK.finditer(log)]
    debuts = [float(m["s"]) for m in _FREEZE_S.finditer(log)]
    fins = [float(m["e"]) for m in _FREEZE_E.finditer(log)]
    figes = [(s, fins[i] if i < len(fins) else duree) for i, s in enumerate(debuts)]
    silence = sum(float(m["d"]) for m in _SILENCE.finditer(log))
    images = [int(x) for x in _FRAME.findall(res.stdout or "")]
    erreurs = [re.sub(r"^\[[^\]]*\]\s*", "", ln.strip()) for ln in log.splitlines() if _ERREUR_DECODAGE.search(ln)]
    return {"noirs": noirs, "figes": figes, "silence": silence, "images": images[-1] if images else None,
            "erreurs": erreurs, "code": res.returncode}


def faststart(path: Path) -> bool | None:
    """Vrai si l'index du MP4 (moov) précède les données (mdat) : lecture immédiate en ligne."""
    if path.suffix.lower() not in (".mp4", ".m4v", ".mov"):
        return None
    try:
        with path.open("rb") as fh:
            pos, size = 0, path.stat().st_size
            while pos + 8 <= size:
                fh.seek(pos)
                head = fh.read(16)
                if len(head) < 8:
                    break
                length, kind = struct.unpack(">I4s", head[:8])
                if length == 1 and len(head) >= 16:
                    length = struct.unpack(">Q", head[8:16])[0]
                if kind == b"moov":
                    return True
                if kind == b"mdat":
                    return False
                if length < 8:
                    break
                pos += length
    except OSError:
        return None
    return None


def planche(path: Path, dest: Path | None = None, colonnes: int = 4, lignes: int = 3,
            duree: float | None = None) -> Path:
    """Planche-contact : colonnes × lignes vignettes réparties sur toute la vidéo."""
    dest = dest or path.with_name(path.stem + ".planche.png")
    duree = duree if duree is not None else sonder(path)["duree"]
    n = colonnes * lignes
    pas = max(duree / n, 0.04)
    vf = (f"fps=1/{pas:.4f},scale=480:-2:force_original_aspect_ratio=decrease,"
          f"tile={colonnes}x{lignes}:padding=6:margin=6:color=0x202020")
    try:
        res = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(path), "-vf", vf,
                              "-frames:v", "1", "-update", "1", str(dest)], capture_output=True, text=True, timeout=180)
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise StudioError(f"planche-contact : {exc}") from exc
    if res.returncode != 0 or not dest.exists():
        raise StudioError("planche-contact : " + ((res.stderr.strip().splitlines() or ["échec"])[-1]))
    return dest


def verifier(path, **reglages) -> dict:
    """Contrôle un livrable. Renvoie {"verdict": "PRÊT" | "À CORRIGER", "points": [...], "infos": {...}}.

    Chaque point : {"nom", "ok", "detail", "bloquant"}. Seuls les points bloquants décident du verdict.
    """
    path = Path(path)
    r = {**DEFAUTS, **{k: v for k, v in reglages.items() if v is not None}}
    points: list[dict] = []

    def point(nom: str, ok: bool, detail: str, bloquant: bool = True) -> None:
        points.append({"nom": nom, "ok": bool(ok), "detail": detail, "bloquant": bloquant})

    def conclure(infos: dict, planche_path: str = "") -> dict:
        pret = all(p["ok"] for p in points if p["bloquant"])
        return {"fichier": str(path), "genre": genre(path), "verdict": "PRÊT" if pret else "À CORRIGER",
                "points": points, "infos": infos, "planche": planche_path}

    if not path.is_file():
        point("fichier", False, "fichier introuvable")
        return conclure({})
    taille_mo = path.stat().st_size / 1e6
    point("taille", 0 < taille_mo <= r["taille_max_mo"],
          f"{taille_mo:.2f} Mo (maximum {r['taille_max_mo']:.0f} Mo pour Telegram)" if taille_mo else "fichier vide")
    g = genre(path)
    if not g:
        point("format", False, f"extension {path.suffix or '(aucune)'} non prise en charge")
        return conclure({})
    if g == "document":
        return conclure({"octets": path.stat().st_size})
    try:
        infos = sonder(path)
    except StudioError as exc:
        point("lecture", False, str(exc))
        return conclure({})
    cote = min(infos["largeur"], infos["hauteur"])
    if g == "image":
        # Une capture mobile ou une bannière sont étroites par nature : la taille n'est qu'un avertissement.
        point("définition", cote >= 320, f"{infos['largeur']}×{infos['hauteur']} px (petit côté ≥ 320)")
        point("définition conseillée", cote >= 600, "600 px ou plus sur le petit côté", bloquant=False)
        return conclure(infos)

    d = infos["duree"]
    point("durée", r["duree_min"] <= d <= r["duree_max"],
          f"{d:.1f} s (attendu entre {r['duree_min']:.0f} et {r['duree_max']:.0f} s)")
    point("définition", cote >= r["cote_min"], f"{infos['largeur']}×{infos['hauteur']} px (petit côté ≥ {r['cote_min']})")
    point("définition conseillée", cote >= 1080, "1080 px ou plus sur le petit côté", bloquant=False)
    point("fluidité", infos["fps"] >= r["fps_min"], f"{infos['fps']:.0f} images/s (minimum {r['fps_min']:.0f})")
    compatible = infos["codec"] == "h264" and infos["pix_fmt"] in ("yuv420p", "yuvj420p")
    point("compatibilité", compatible, f"{infos['codec']} / {infos['pix_fmt']} (attendu h264 / yuv420p : lisible partout)")
    fs = faststart(path)
    if fs is not None:
        point("lecture immédiate", fs, "index en tête du fichier (-movflags +faststart)", bloquant=False)
    point("piste audio", bool(infos["audio"]), infos["audio"] or "aucune (ajoute au moins une piste silencieuse)",
          bloquant=False)
    planche_path = ""
    if d > 0:
        try:
            det = detecter(path, d, avec_audio=bool(infos["audio"]))
            # Intégrité : toutes les images annoncées doivent se décoder, sans erreur.
            attendues = d * infos["fps"] if infos["fps"] else 0
            if det["erreurs"] or det["code"] != 0:
                point("intégrité", False, "fichier abîmé ou tronqué : " + (det["erreurs"] or ["ffmpeg a échoué"])[0][:120])
            elif det["images"] is not None and attendues and det["images"] < attendues * 0.9:
                point("intégrité", False, f"l'image s'arrête à {det['images'] / infos['fps']:.1f} s sur {d:.1f} s "
                                          "(fichier tronqué, ou piste vidéo plus courte que le son)")
            else:
                point("intégrité", True, "toutes les images se lisent")
            noir = sum(e - s for s, e in det["noirs"])
            # Un fondu d'ouverture ou de fermeture est normal : seul le noir prolongé compte.
            bords = [e - s for s, e in det["noirs"] if s < 0.2 or e > d - 0.2]
            milieu = noir - sum(bords)
            ok_noir = milieu <= d * r["noir_max_pct"] / 100 and all(b <= r["noir_bord_max"] for b in bords)
            point("écran noir", ok_noir, f"{noir:.1f} s de noir, dont {milieu:.1f} s en cours de vidéo")
            fige = sum(e - s for s, e in det["figes"])
            plus_long = max((e - s for s, e in det["figes"]), default=0.0)
            ok_fige = plus_long <= r["fige_max"] and fige <= d * r["fige_max_pct"] / 100
            detail = f"{fige:.1f} s sans mouvement, plus long arrêt {plus_long:.1f} s"
            if not ok_fige and det["figes"]:
                s0, e0 = max(det["figes"], key=lambda x: x[1] - x[0])
                detail += f" (de {s0:.1f} à {e0:.1f} s)"
            point("image figée", ok_fige, detail)
            if infos["audio"]:
                point("son", True, "piste silencieuse (aucune musique ni voix)" if det["silence"] >= d * 0.95
                      else "son présent", bloquant=False)
            infos["noir"], infos["fige"] = round(noir, 2), round(fige, 2)
        except StudioError as exc:
            point("analyse", False, str(exc))
        try:
            planche_path = str(planche(path, duree=d))
        except StudioError as exc:
            point("planche-contact", False, str(exc), bloquant=False)
    return conclure(infos, planche_path)


def texte(rapport: dict) -> str:
    lines = [f"{'✅' if rapport['verdict'] == 'PRÊT' else '❌'} {rapport['verdict']} — {Path(rapport['fichier']).name}"]
    for p in rapport["points"]:
        mark = "✓" if p["ok"] else ("✗" if p["bloquant"] else "!")
        lines.append(f"  {mark} {p['nom']} : {p['detail']}")
    if rapport.get("planche"):
        lines.append(f"  Planche-contact à regarder : {rapport['planche']}")
    return "\n".join(lines)
