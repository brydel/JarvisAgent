#!/usr/bin/env python3
"""verifier.py — contrôle technique d'une vidéo, d'une image ou d'un document du studio.

    python3 verifier.py sortie.mp4 [--duree-min 15] [--duree-max 60] [--json]

Écrit aussi une planche-contact (sortie.planche.png) : 12 vignettes réparties sur la vidéo.
Regarde-la toujours avant de dire qu'une vidéo est prête. Code de sortie 0 = PRÊT, 1 = À CORRIGER.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "..", "lib"))

from jarvis import cli  # noqa: E402

if __name__ == "__main__":
    sys.exit(cli.main(["studio", "verifier", *sys.argv[1:]]))
