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

sys.path.insert(0, os.environ.get("GOLDENS_LIB") or str(Path(__file__).resolve().parents[4] / "lib"))
from jarvis import comptes_rendus

etat = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], capture_output=True, text=True, timeout=30)
verifier(etat.returncode == 0, "git status impossible dans le dossier évalué")
autres = [ln[3:] for ln in etat.stdout.splitlines()
          if ln[3:] != "verdict.md" and "__pycache__" not in ln and not ln.endswith(".pyc")]
verifier(not autres, f"une relecture ne modifie aucun autre fichier : {autres[:5]}")
f = Path("verdict.md")
verifier(f.is_file(), "verdict.md absent")
if f.is_file():
    a = comptes_rendus.analyser_verdict(f.read_text(encoding="utf-8"))
    verifier(a["verdict"] == "corrections", "le travail ne satisfait pas l'issue : « VERDICT : CORRECTIONS » attendu")
    for anomalie in a["anomalies"]:
        verifier(False, "format du verdict : " + anomalie)
    bloquantes = [c for c in a["corrections"] if c["severite"] == "bloquant" and c["fichier"] == "app/remise.py"
                  and c["ligne"] and 4 <= c["ligne"] <= 8]
    verifier(bool(bloquantes), "aucune correction [bloquant] ne désigne la fonction fautive (app/remise.py:4 à 8)")
    verifier(len(a["corrections"]) >= 2, "une seule correction : il manque le refus au-dessus de 100, l'arrondi ou les tests")
    verifier(all(len(c["texte"].split()) >= 5 for c in a["corrections"]), "correction trop vague pour être appliquée")
    verifier(any(v["commande"] and v["resultat"] for v in a["verifications"]),
             "aucune vérification lancée (commande → résultat) : une relecture qui ne lance rien n'est qu'une lecture")
fin()
