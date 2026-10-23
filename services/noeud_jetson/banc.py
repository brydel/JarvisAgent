"""Banc d'essai des modèles Whisper sur le noeud (à lancer SUR la Jetson, avec le venv du service).

    ~/.local/share/jarvis-noeud/venv/bin/python banc.py memo.m4a small turbo

Pour chaque modèle : temps de chargement, temps de transcription, facteur temps réel (traitement / durée de
l'audio, plus petit = mieux), mémoire GPU maximale et températures en fin d'essai. Arrête le service pendant le
banc (systemctl --user stop jarvis-noeud) : deux modèles en mémoire ne tiennent pas dans 8 Go.
"""
from __future__ import annotations

import gc
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from service import duree_audio, mesures  # noqa: E402


def essai(nom: str, audio: Path, langue: str) -> dict:
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
    sortie = {"modele": nom, "chargement_s": round(charge, 1), "transcription_s": round(traite, 1),
              "gpu_max_mo": torch.cuda.max_memory_allocated() // (1024 * 1024), **mesures(),
              "extrait": " ".join(str(r.get("text", "")).split())[:160]}
    del modele
    gc.collect()
    torch.cuda.empty_cache()
    return sortie


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    audio, modeles = Path(sys.argv[1]), sys.argv[2:]
    duree = duree_audio(audio)
    print(f"Audio : {audio.name}, {duree:.1f} s" if duree else f"Audio : {audio.name}, durée inconnue")
    for nom in modeles:
        r = essai(nom, audio, "fr")
        rtf = f"{r['transcription_s'] / duree:.2f}" if duree else "?"
        print(f"\n== {nom} : chargement {r['chargement_s']} s · transcription {r['transcription_s']} s "
              f"(facteur temps réel {rtf}) · GPU max {r['gpu_max_mo']} Mo · "
              f"mémoire libre {r.get('memoire_dispo_mo', '?')} Mo · GPU {r.get('gpu_c', '?')} °C · "
              f"CPU {r.get('cpu_c', '?')} °C")
        print(f"   « {r['extrait']} »")
    return 0


if __name__ == "__main__":
    sys.exit(main())
