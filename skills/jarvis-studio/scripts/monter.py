#!/usr/bin/env python3
"""monter.py — assemble des séquences en une vidéo finale prête à diffuser.

    python3 monter.py montage.json sortie.mp4

Montage (JSON) :
    {
      "format": "16:9",                       (16:9, 9:16, 1:1 ou 4:5 ; défaut 16:9)
      "ips": 30,
      "transition": 0.4,                      (fondu entre séquences, en secondes ; 0 = coupe franche)
      "segments": [
        {"fichier": "intro.mp4"},
        {"fichier": "parcours.webm", "debut": 1.2, "fin": 9.0, "vitesse": 1.25},
        {"fichier": "fin.mp4"}
      ],
      "musique": {"fichier": "musique.mp3", "volume": 0.25}     (facultatif)
    }

- Les chemins partent du dossier de montage.json ; « $JARVIS_LIVRABLES/… » et « ~/… » sont acceptés.
- Chaque séquence est remise au format de sortie. Si ses proportions diffèrent, elle est centrée
  sur un fond flouté tiré de l'image elle-même : jamais de bandes noires, jamais de déformation.
- Un film issu d'enregistrer.cjs est rogné tout seul à sa partie utile (fichier .json voisin),
  sauf si « debut » est donné.
- Le son des séquences n'est pas repris : la bande-son est la musique fournie, ou le silence.
- Sortie : H.264 / yuv420p / AAC, index en tête du fichier, lisible partout (Telegram, réseaux).
  Si le fichier dépasse 49 Mo, il est réencodé jusqu'à tenir sous la limite (ou le script échoue).
- N'utilise une musique que si ton humain l'a fournie ou si sa licence permet l'usage commercial.

Bibliothèque standard uniquement ; ffmpeg et ffprobe doivent être installés.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

FORMATS = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080), "4:5": (1080, 1350)}
TAILLE_MAX = 49 * 1000 * 1000


def stop(msg: str, code: int = 2):
    print(f"Erreur : {msg}", file=sys.stderr)
    sys.exit(code)


def run(cmd: list[str], quoi: str) -> None:
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        tail = (res.stderr.strip().splitlines() or ["échec"])[-1]
        stop(f"{quoi} : {tail}", 1)


def chemin(base: Path, f) -> Path:
    """Chemin cité dans le montage : « $JARVIS_LIVRABLES/… » et « ~/… » développés, sinon relatif au montage."""
    if not isinstance(f, str) or not f.strip():
        stop("chaque séquence doit avoir un champ « fichier » (chemin du clip)")
    if f.startswith("$JARVIS_LIVRABLES"):
        racine = os.environ.get("JARVIS_LIVRABLES")
        if not racine:
            stop("la variable JARVIS_LIVRABLES n'est pas définie : écris le chemin complet du fichier")
        f = racine + f[len("$JARVIS_LIVRABLES"):]
    return (base / os.path.expanduser(f)).resolve()


def nombre(valeur, nom: str, defaut: float | None = None) -> float | None:
    if valeur is None:
        return defaut
    try:
        return float(valeur)
    except (TypeError, ValueError):
        stop(f"« {nom} » doit être un nombre (reçu : {valeur!r})")
        return defaut


def duree(path: Path) -> float:
    res = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True)
    try:
        return float(res.stdout.strip())
    except ValueError:
        stop(f"impossible de lire la durée de {path.name}", 1)
        return 0.0


def normaliser(seg: dict, base: Path, dest: Path, w: int, h: int, ips: int) -> float:
    """Remet une séquence au format de sortie (taille, cadence, rognage, vitesse). Renvoie sa durée."""
    if not isinstance(seg, dict):
        stop("une séquence est un objet {\"fichier\": …}")
    src = chemin(base, seg.get("fichier"))
    if not src.is_file():
        stop(f"séquence introuvable : {seg['fichier']} (cherchée ici : {src})")
    debut = nombre(seg.get("debut"), "debut")
    side = Path(str(src) + ".json")
    if debut is None and side.is_file():
        try:
            debut = float(json.loads(side.read_text(encoding="utf-8")).get("debut_utile") or 0)
        except (ValueError, OSError):
            debut = 0
    debut = max(0.0, float(debut or 0))
    fin = nombre(seg.get("fin"), "fin")
    vitesse = nombre(seg.get("vitesse"), "vitesse", 1.0) or 1.0
    if not 0.25 <= vitesse <= 4:
        stop(f"vitesse hors limites pour {seg['fichier']} (entre 0.25 et 4)")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    if debut > 0:
        cmd += ["-ss", f"{debut:.3f}"]
    if fin is not None:
        if float(fin) <= debut:
            stop(f"« fin » doit dépasser « debut » pour {seg['fichier']}")
        cmd += ["-t", f"{float(fin) - debut:.3f}"]
    # Fond : la même image agrandie et floutée. Devant : l'image entière, sans déformation.
    vf = (f"[0:v]setpts=PTS/{vitesse},fps={ips},split=2[a][b];"
          f"[a]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},boxblur=28:4,eq=brightness=-0.12[fond];"
          f"[b]scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos[avant];"
          f"[fond][avant]overlay=(W-w)/2:(H-h)/2,setsar=1,format=yuv420p[v]")
    cmd += ["-i", str(src), "-filter_complex", vf, "-map", "[v]", "-an",
            "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-r", str(ips), str(dest)]
    run(cmd, f"préparation de {seg['fichier']}")
    return duree(dest)


def assembler(parts: list[Path], durees: list[float], transition: float, dest: Path, ips: int) -> float:
    """Enchaîne les séquences, avec un fondu de `transition` secondes entre elles. Renvoie la durée totale."""
    if len(parts) == 1:
        shutil.copyfile(parts[0], dest)
        return durees[0]
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    for p in parts:
        cmd += ["-i", str(p)]
    transition = max(0.0, min(transition, min(durees) / 2.5))
    if transition < 0.05:
        graphe = "".join(f"[{i}:v]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=1:a=0[v]"
        total = sum(durees)
    else:
        graphe, precedent, cumul = "", "[0:v]", durees[0]
        for i in range(1, len(parts)):
            sortie = "[v]" if i == len(parts) - 1 else f"[x{i}]"
            graphe += f"{precedent}[{i}:v]xfade=transition=fade:duration={transition:.3f}:offset={cumul - transition:.3f}{sortie};"
            precedent = sortie
            cumul += durees[i] - transition
        graphe = graphe.rstrip(";")
        total = cumul
    cmd += ["-filter_complex", graphe, "-map", "[v]", "-c:v", "libx264", "-preset", "medium", "-crf", "16",
            "-pix_fmt", "yuv420p", "-r", str(ips), str(dest)]
    run(cmd, "assemblage")
    return total


def finaliser(video: Path, total: float, musique: dict | None, base: Path, dest: Path, crf: int = 19,
              debit: int | None = None) -> None:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video)]
    if musique and musique.get("fichier"):
        src = chemin(base, musique["fichier"])
        if not src.is_file():
            stop(f"musique introuvable : {musique['fichier']}")
        vol = max(0.0, min(1.5, nombre(musique.get("volume"), "volume", 0.3)))
        cmd += ["-stream_loop", "-1", "-i", str(src), "-filter_complex",
                f"[1:a]volume={vol},afade=t=in:d=0.6,afade=t=out:st={max(0.0, total - 1.2):.2f}:d=1.2[a]",
                "-map", "0:v", "-map", "[a]"]
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000", "-map", "0:v", "-map", "1:a"]
    cmd += ["-c:v", "libx264", "-preset", "slow", "-pix_fmt", "yuv420p"]
    cmd += ["-b:v", str(debit), "-maxrate", str(int(debit * 1.3)), "-bufsize", str(debit * 2)] if debit else ["-crf", str(crf)]
    cmd += ["-c:a", "aac", "-b:a", "160k", "-t", f"{total:.3f}", "-movflags", "+faststart", str(dest)]
    run(cmd, "encodage final")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        stop("ffmpeg introuvable : sudo apt install ffmpeg", 3)
    fichier, dest = Path(argv[0]).resolve(), Path(argv[1]).resolve()
    try:
        m = json.loads(fichier.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        stop(f"{fichier} illisible : {exc}")
    if not isinstance(m, dict):
        stop("le montage est un objet JSON { \"segments\": [ … ] }")
    if m.get("format", "16:9") not in FORMATS:
        stop(f"format inconnu (valeurs : {', '.join(FORMATS)})")
    w, h = FORMATS[m.get("format", "16:9")]
    if dest.suffix.lower() != ".mp4":
        stop("la vidéo de sortie doit se terminer par .mp4")
    ips = int(max(12, min(60, nombre(m.get("ips"), "ips", 30) or 30)))
    segments = m.get("segments") or []
    if not isinstance(segments, list) or not segments:
        stop("le montage doit contenir une liste « segments » non vide")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="jarvis-montage-") as tmp:
        tmp = Path(tmp)
        parts, durees = [], []
        for i, seg in enumerate(segments):
            part = tmp / f"seq{i:02d}.mp4"
            d = normaliser(seg, fichier.parent, part, w, h, ips)
            if d < 0.3:
                stop(f"séquence trop courte après rognage : {seg['fichier']}")
            parts.append(part)
            durees.append(d)
            print(f"  séquence {i + 1}/{len(segments)} : {seg['fichier']} ({d:.1f} s)")
        brut = tmp / "assemble.mp4"
        total = assembler(parts, durees, nombre(m.get("transition"), "transition", 0.4) or 0.0, brut, ips)
        musique = m.get("musique") if isinstance(m.get("musique"), dict) else None
        finaliser(brut, total, musique, fichier.parent, dest)
        marge = 0.90
        for _essai in range(3):
            if dest.stat().st_size <= TAILLE_MAX:
                break
            # Trop lourd pour Telegram : débit calculé pour tenir sous la limite, avec une marge qui
            # grandit à chaque essai (l'encodeur dépasse parfois le débit demandé sur une image agitée).
            debit = max(300_000, int(TAILLE_MAX * 8 * marge / total) - 160_000)
            print(f"  fichier de {dest.stat().st_size / 1e6:.1f} Mo : réencodage à {debit // 1000} kb/s")
            finaliser(brut, total, musique, fichier.parent, dest, debit=debit)
            marge -= 0.12
        if dest.stat().st_size > TAILLE_MAX:
            stop(f"la vidéo pèse encore {dest.stat().st_size / 1e6:.1f} Mo (limite 49 Mo) : raccourcis-la ou baisse le format", 1)
    print(f"Vidéo écrite : {dest} ({total:.1f} s, {w}×{h}, {dest.stat().st_size / 1e6:.1f} Mo)")
    print(f"Contrôle-la maintenant : python3 {Path(__file__).with_name('verifier.py')} {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
