"""Vérification cachée : lancée depuis le dossier du projet évalué. Code 0 = réussi."""
import importlib.util, os, subprocess, sys
from pathlib import Path

ECHECS = []
# Jeton aléatoire transmis par le harnais sur l'entrée standard, lu AVANT de charger le code évalué : un code qui
# imprime lui-même « VERDICT: OK » puis quitte ne le connaît pas, et le harnais exige le jeton.
JETON = "" if sys.stdin is None or sys.stdin.isatty() else sys.stdin.readline().strip()

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
    print(f"VERDICT: OK {JETON}".rstrip())
    sys.exit(0)

import re, tempfile
script = Path("scripts/preparer.sh")
verifier(script.is_file(), "scripts/preparer.sh absent")
if not ECHECS:
    texte = script.read_text(encoding="utf-8")
    verifier(re.search(r"^set -euo pipefail\s*$", texte, re.M) is not None, "« set -euo pipefail » absent")
    verifier(subprocess.run(["bash", "-n", str(script)], capture_output=True).returncode == 0, "erreur de syntaxe bash")
    def lancer(*args):
        return subprocess.run(["bash", str(script.resolve()), *args], capture_output=True, text=True, timeout=30)
    r = lancer()
    verifier(r.returncode == 2 and r.stderr.strip(), f"sans argument : code 2 et message sur stderr attendus (code {r.returncode})")
    def etat(racine):
        out = []
        for f in sorted(racine.rglob("*")):
            rel = str(f.relative_to(racine))
            if f.is_symlink():
                out.append((rel, "lien", os.path.realpath(f)))
            elif f.is_dir():
                out.append((rel, "dossier", ""))
            else:
                out.append((rel, "fichier", f.read_text(encoding="utf-8")))
        return out
    with tempfile.TemporaryDirectory() as d:
        cible = Path(d).resolve() / "dossier cible" / "app"
        un = lancer(str(cible))
        verifier(un.returncode == 0, "première exécution en échec : " + un.stderr.strip()[-200:])
        premier = etat(cible) if cible.is_dir() else []
        deux = lancer(str(cible))
        verifier(deux.returncode == 0, "deuxième exécution en échec : " + deux.stderr.strip()[-200:])
        second = etat(cible) if cible.is_dir() else []
        verifier(premier == second and bool(premier), "l'état change entre la première et la deuxième exécution")
        config = cible / "partage" / "config.env"
        verifier(config.is_file() and config.read_text(encoding="utf-8").splitlines() == ["APP_ENV=production", "APP_PORT=8080"],
                 "partage/config.env ne contient pas exactement ses deux lignes")
        verifier((cible / "releases").is_dir(), "releases/ absent")
        lien = cible / "config.env"
        verifier(lien.is_symlink() and os.path.realpath(lien) == os.path.realpath(config), "config.env n'est pas un lien vers partage/config.env")
fin()
