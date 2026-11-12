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

import ast, shutil, tempfile
ORIGINAL = '"""Petits outils de texte."""\n\n\ndef tronquer(texte, longueur):\n    """Coupe `texte` à `longueur` caractères au plus. Un texte coupé se termine par « … », compté dans la longueur."""\n    if len(texte) > longueur:\n        return texte[:longueur] + "…"\n    return texte\n\n\ndef slug(titre):\n    r = ""\n    for c in titre.lower():\n        if c.isalnum(): r += c\n        elif r and r[-1] != "-": r += "-"\n    return r.strip("-")\n'
SLUG = 'def slug(titre):\n    r = ""\n    for c in titre.lower():\n        if c.isalnum(): r += c\n        elif r and r[-1] != "-": r += "-"\n    return r.strip("-")'
source = Path("texte.py").read_text(encoding="utf-8")
m = charger("texte.py", "texte_evalue")
verifier(m.tronquer("abcdefghij", 5) == "abcd…", "tronquer('abcdefghij', 5) doit rendre « abcd… »")
verifier(m.tronquer("abc", 5) == "abc" and m.tronquer("abcde", 5) == "abcde", "un texte assez court doit rester tel quel")
verifier(m.tronquer("abcdef", 1) == "…", "tronquer('abcdef', 1) doit rendre « … »")
for n in (0, -3):
    try:
        m.tronquer("abc", n)
        verifier(False, f"longueur {n} acceptée à tort")
    except ValueError:
        pass
actuel = next((ast.get_source_segment(source, n) for n in ast.parse(source).body
               if isinstance(n, ast.FunctionDef) and n.name == "slug"), None)
verifier(actuel == SLUG, "la fonction slug a été modifiée : elle était hors périmètre")
tests = Path("tests/test_texte.py")
verifier(tests.is_file() and "test_slug" in tests.read_text(encoding="utf-8")
         and "test_texte_court_inchange" in tests.read_text(encoding="utf-8"), "tests existants retirés")
def lancer(src):
    with tempfile.TemporaryDirectory() as d:
        shutil.copytree("tests", Path(d) / "tests")
        Path(d, "texte.py").write_text(src, encoding="utf-8")
        r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."], cwd=d,
                           capture_output=True, text=True, timeout=60)
        return r.returncode, r.stderr
if not ECHECS:
    rc, err = lancer(ORIGINAL)
    verifier(rc != 0, "aucun test ne reproduit le bug : la suite passe sur le code d'origine")
    verifier("test_slug" not in "".join(l for l in err.splitlines() if l.startswith(("FAIL:", "ERROR:"))),
             "le test de slug échoue sur le code d'origine : il ne devait pas changer")
    rc, err = lancer(source)
    verifier(rc == 0, "la suite échoue sur le code corrigé : " + err.strip()[-200:])
fin()
