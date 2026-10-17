"""Vérification cachée : lancée depuis le dossier du projet évalué. Code 0 = réussi."""
import importlib.util, os, subprocess, sys
from pathlib import Path

ECHECS = []

def verifier(cond, msg):
    if not cond:
        ECHECS.append(msg)

def charger(chemin, nom="m"):
    spec = importlib.util.spec_from_file_location(nom, Path(chemin).resolve())
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def fin():
    if ECHECS:
        print("ÉCHEC :\n- " + "\n- ".join(ECHECS))
        sys.exit(1)
    print("VERDICT: OK")
    sys.exit(0)

import json, shutil
if not shutil.which("node"):
    print("node introuvable : vérification impossible")
    sys.exit(2)
def rendre(elements):
    code = "const {rendreListe}=require(process.argv[1]);process.stdout.write(rendreListe(JSON.parse(process.argv[2])))"
    r = subprocess.run(["node", "-e", code, str(Path("liste.js").resolve()), json.dumps(elements)],
                       capture_output=True, text=True, timeout=20)
    verifier(r.returncode == 0, "liste.js ne s'exécute pas : " + r.stderr.strip()[:200])
    return r.stdout
vide = rendre([])
verifier("class=\"action\"" in vide and "Créer une alerte" in vide, "état vide sans action")
verifier(len(vide.replace("<", " <").split()) > 6, "état vide sans texte utile")
html = rendre([{"nom": "<script>alert(1)</script>"}, {"nom": "BTC > 60k"}])
verifier("<script>" not in html, "nom non échappé (XSS)")
verifier("&lt;script&gt;" in html, "nom échappé absent")
verifier("<li>" in html, "liste non rendue")
fin()
