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

from html.parser import HTMLParser

class P(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inputs, self.labels, self.boutons = {}, set(), []
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "input":
            self.inputs[a.get("id")] = a
        elif tag == "label" and a.get("for"):
            self.labels.add(a["for"])
        elif tag == "button":
            self.boutons.append(a)

p = P()
p.feed(Path("index.html").read_text(encoding="utf-8"))
for ident in ("email", "mdp"):
    verifier(ident in p.inputs, f"champ {ident} disparu")
    verifier(ident in p.labels, f"champ {ident} sans libellé associé")
    verifier("required" in p.inputs.get(ident, {}), f"champ {ident} non obligatoire")
verifier(p.inputs.get("mdp", {}).get("aria-describedby") == "erreur-mdp", "erreur non reliée au champ mot de passe")
verifier(any(b.get("type") == "submit" for b in p.boutons), "pas de vrai bouton d'envoi")
fin()
