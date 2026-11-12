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

import json
TEXTE = "  Le cours a gagné 4 % cette semaine. Le volume reste faible.  "
REPLI = {"resume": "Le cours a gagné 4 % cette semaine.", "source": "repli"}
BON = json.dumps({"resume": "Hausse de 4 %."})

class Simule:
    def __init__(self, *reponses):
        self.reponses, self.appels = list(reponses), 0
    def __call__(self, texte):
        self.appels += 1
        r = self.reponses.pop(0) if self.reponses else RuntimeError("fournisseur épuisé")
        if isinstance(r, Exception):
            raise r
        return r

def essai(nom, fournisseur, attendu, appels=None, **kw):
    try:
        res = M.resumer(TEXTE, fournisseur, **kw)
    except Exception as exc:  # noqa: BLE001
        verifier(False, f"{nom} : exception {type(exc).__name__} au lieu d'un repli")
        return
    verifier(res == attendu, f"{nom} : obtenu {res!r}")
    if appels is not None:
        verifier(fournisseur.appels == appels, f"{nom} : {fournisseur.appels} appel(s) au fournisseur, {appels} attendu(s)")

os.environ.pop("RESUME_IA", None)
M = charger("resume.py", "resume_evalue")
IA = {"resume": "Hausse de 4 %.", "source": "ia"}
essai("drapeau absent", Simule(BON), REPLI, appels=0)
os.environ["RESUME_IA"] = "0"
essai("RESUME_IA=0", Simule(BON), REPLI, appels=0)
os.environ["RESUME_IA"] = "1"
essai("RESUME_IA=1", Simule(BON), IA, appels=1)
essai("actif=False l'emporte sur l'environnement", Simule(BON), REPLI, appels=0, actif=False)
os.environ.pop("RESUME_IA", None)
essai("actif=True", Simule(BON), IA, appels=1, actif=True)
essai("deux pannes", Simule(TimeoutError(), ConnectionError()), REPLI, appels=2, actif=True)
essai("une panne puis une réponse", Simule(OSError(), BON), IA, appels=2, actif=True)
for mauvaise in ("pas du json", "[]", json.dumps({"resume": ""}), json.dumps({"resume": 3}), json.dumps({"autre": "x"}),
                 json.dumps({"resume": "x" * 500})):
    essai(f"sortie hors schéma {mauvaise[:20]!r}", Simule(mauvaise, mauvaise), REPLI, actif=True)
try:
    verifier(M.resumer(" Stable ", Simule(), actif=False) == {"resume": "Stable", "source": "repli"}, "repli d'un texte sans point")
except Exception as exc:  # noqa: BLE001
    verifier(False, f"texte sans point : exception {type(exc).__name__}")
verifier(Path("tests/test_resume.py").is_file(), "tests/test_resume.py absent")
if Path("tests/test_resume.py").is_file():
    verifier(not any(mot in Path("tests/test_resume.py").read_text(encoding="utf-8") for mot in ("urllib", "requests", "http.client", "socket")),
             "les tests ne doivent faire aucun appel réseau")
    r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."], capture_output=True,
                       text=True, timeout=60, env={k: v for k, v in os.environ.items() if k != "RESUME_IA"})
    verifier(r.returncode == 0, "tests en échec : " + r.stderr.strip()[-200:])
    verifier("Ran 0 tests" not in r.stderr, "aucun test exécuté")
fin()
