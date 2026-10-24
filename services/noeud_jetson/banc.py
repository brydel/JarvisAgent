"""Banc d'essai des moteurs et modèles audio sur le noeud (à lancer SUR la Jetson, avec le venv du service).

    ~/.local/share/jarvis-noeud/venv/bin/python banc.py memo.m4a small turbo faster-whisper:small

Chaque essai s'écrit `moteur:modèle` (moteur whisper ou faster-whisper) ; un nom seul vaut `whisper:nom`.
Pour chacun : temps de chargement, temps de transcription, facteur temps réel (traitement / durée de l'audio,
plus petit = mieux), appareil réellement utilisé, mémoire GPU maximale (PyTorch seulement), mémoire libre et
températures en fin d'essai. Arrête le service pendant le banc (systemctl --user stop jarvis-noeud) : deux
modèles en mémoire ne tiennent pas dans 8 Go.
"""
from __future__ import annotations

import gc
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from service import FasterWhisper, duree_audio, mesures  # noqa: E402


def essai_whisper(nom: str, audio: Path, langue: str) -> dict:
    import torch
    import whisper
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    t0 = time.monotonic()
    modele = whisper.load_model(nom, device="cuda")
    charge = time.monotonic() - t0
    t1 = time.monotonic()
    r = modele.transcribe(str(audio), language=langue, fp16=True, condition_on_previous_text=False)
    traite = time.monotonic() - t1
    sortie = {"chargement_s": round(charge, 1), "transcription_s": round(traite, 1), "appareil": "cuda",
              "gpu_max_mo": torch.cuda.max_memory_allocated() // (1024 * 1024), **mesures(),
              "extrait": " ".join(str(r.get("text", "")).split())[:160]}
    del modele
    gc.collect()
    torch.cuda.empty_cache()
    return sortie


def essai_faster(nom: str, audio: Path, langue: str) -> dict:
    moteur = FasterWhisper(nom)
    t0 = time.monotonic()
    r = moteur.transcrire(audio, langue)  # le premier appel charge le modèle : on le mesure à part ci-dessous
    premier = time.monotonic() - t0
    t1 = time.monotonic()
    r = moteur.transcrire(audio, langue)
    traite = time.monotonic() - t1
    sortie = {"chargement_s": round(max(premier - traite, 0.0), 1), "transcription_s": round(traite, 1),
              "appareil": moteur.appareil, "gpu_max_mo": "?", **mesures(), "extrait": " ".join(r["texte"].split())[:160]}
    moteur.decharger()
    return sortie


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    audio, essais = Path(sys.argv[1]), sys.argv[2:]
    duree = duree_audio(audio)
    print(f"Audio : {audio.name}, {duree:.1f} s" if duree else f"Audio : {audio.name}, durée inconnue")
    for spec in essais:
        moteur, _, nom = spec.rpartition(":")
        moteur = moteur or "whisper"
        if moteur not in ("whisper", "faster-whisper"):
            print(f"\n== {spec} : moteur inconnu (whisper ou faster-whisper)")
            continue
        try:
            r = (essai_faster if moteur == "faster-whisper" else essai_whisper)(nom, audio, "fr")
        except Exception as exc:  # noqa: BLE001 — un moteur absent ne doit pas arrêter les autres essais
            print(f"\n== {moteur}:{nom} : échec ({type(exc).__name__}: {str(exc)[:160]})")
            continue
        rtf = f"{r['transcription_s'] / duree:.2f}" if duree else "?"
        print(f"\n== {moteur}:{nom} ({r['appareil']}) : chargement {r['chargement_s']} s · transcription "
              f"{r['transcription_s']} s (facteur temps réel {rtf}) · GPU max {r['gpu_max_mo']} Mo · "
              f"mémoire libre {r.get('memoire_dispo_mo', '?')} Mo · GPU {r.get('gpu_c', '?')} °C · "
              f"CPU {r.get('cpu_c', '?')} °C")
        print(f"   « {r['extrait']} »")
    return 0


if __name__ == "__main__":
    sys.exit(main())
