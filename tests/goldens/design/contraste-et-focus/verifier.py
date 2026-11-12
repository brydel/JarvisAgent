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

import re
f = Path("styles/jetons.css")
verifier(f.is_file(), "styles/jetons.css absent")
if f.is_file():
    css = re.sub(r"/\*.*?\*/", "", f.read_text(encoding="utf-8"), flags=re.S)
    m = re.search(r":root\s*\{(.*?)\}", css, re.S)
    verifier(m is not None, "bloc :root absent")
    racine = m.group(1) if m else ""
    jetons = {k: v.strip() for k, v in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", racine)}
    def luminance(hexa):
        h = hexa.lstrip("#")
        h = "".join(c * 2 for c in h) if len(h) == 3 else h
        canaux = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canaux]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    def contraste(a, b):
        la, lb = sorted((luminance(a), luminance(b)), reverse=True)
        return (la + 0.05) / (lb + 0.05)
    verifier(jetons.get("--couleur-marque", "").lower() == "#1f6feb" and jetons.get("--couleur-fond", "").lower() == "#ffffff",
             "--couleur-marque et --couleur-fond ne devaient pas changer")
    for nom in ("--couleur-texte", "--couleur-texte-discret"):
        valeur = jetons.get(nom, "")
        if not re.fullmatch(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})", valeur):
            verifier(False, f"{nom} doit être une couleur hexadécimale (lu : {valeur!r})")
            continue
        rapport = contraste(valeur, "#ffffff")
        verifier(rapport >= 4.5, f"{nom} : contraste de {rapport:.2f}:1 sur le fond, 4,5:1 au moins")
    taille = re.fullmatch(r"(\d+(?:\.\d+)?)px", jetons.get("--taille-texte", ""))
    verifier(taille is not None and float(taille.group(1)) >= 16, "--taille-texte doit valoir au moins 16px")
    reste = css.replace(m.group(0), "") if m else css
    verifier(re.search(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(", reste) is None, "couleur en dur en dehors de :root")
    verifier(re.search(r"outline\s*:\s*(none|0)\b", css) is None, "« outline: none » encore présent")
    focus = re.search(r"\.bouton:focus-visible\s*\{(.*?)\}", css, re.S)
    epaisseur = re.search(r"outline\s*:[^;]*?(\d+(?:\.\d+)?)px", focus.group(1)) if focus else None
    verifier(epaisseur is not None and float(epaisseur.group(1)) >= 2, "règle .bouton:focus-visible avec un outline d'au moins 2px absente")
    for largeur in re.findall(r"(?<![\w-])(?:min-)?width\s*:\s*(\d+(?:\.\d+)?)px", reste):
        verifier(float(largeur) <= 360, f"largeur fixe de {largeur}px : déborde d'un écran de 360 px")
    for regle in ("body", ".aide", ".bouton"):
        verifier(re.search(rf"(^|\}})\s*{re.escape(regle)}\s*\{{", css) is not None, f"règle {regle} supprimée")
fin()
