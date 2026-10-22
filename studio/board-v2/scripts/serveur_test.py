"""Serveur Studio ISOLÉ pour Playwright : état et configuration temporaires, port 7720, exécutant factice.

Le jeton de session est écrit dans <état>/jeton-test (lu par les tests). Rien ne touche ton installation.
Variables : JARVIS_TEST_PORT (7720), JARVIS_TEST_EXECUTANT=1 pour faire tourner un exécutant factice (missions).
"""
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

base = Path(os.environ.get("JARVIS_TEST_ETAT") or tempfile.mkdtemp(prefix="jarvis-playwright-"))
os.environ["JARVIS_STATE_DIR"] = str(base / "etat")
os.environ["JARVIS_CONFIG_DIR"] = str(base / "config")
os.environ["JARVIS_DATA_DIR"] = str(base / "data")
os.environ.pop("JARVIS_MISSIONS_PG", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

from jarvis import adaptateurs, coureur, missions, studio_api  # noqa: E402

port = int(os.environ.get("JARVIS_TEST_PORT", "7720"))
org = missions.tenant_local()
missions.declarer_connexion(org, "factice", "factice")
httpd = studio_api.serveur(port)
httpd.intervalle_flux = 0.2
jeton = studio_api.jeton(nouveau=True)
(base / "jeton-test").write_text(jeton)
Path(os.environ.get("JARVIS_TEST_JETON_FICHIER", "/tmp/jarvis-board-v2-jeton")).write_text(jeton)

if os.environ.get("JARVIS_TEST_EXECUTANT") == "1":
    rid, secret = missions.enroler_executant(org, "executant-test", capacites=["analyse"], fournisseurs=["factice"])

    def boucle():
        cr = coureur.Coureur(coureur.TransportLocal(rid, secret), {"factice": adaptateurs.Factice()})
        while True:
            missions.recuperer()
            cr.tour()
            time.sleep(1)

    threading.Thread(target=boucle, daemon=True).start()

print(f"PRET http://localhost:{port}/v2/ etat={base}", flush=True)
httpd.serve_forever()
