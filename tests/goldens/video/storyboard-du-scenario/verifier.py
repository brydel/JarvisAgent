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
f = Path("storyboard.json")
verifier(f.is_file(), "storyboard.json absent")
s = None
if f.is_file():
    try:
        s = json.loads(f.read_text(encoding="utf-8"))
    except ValueError as exc:
        verifier(False, f"storyboard.json n'est pas du JSON valide : {exc}")
if isinstance(s, dict):
    scenes = s.get("scenes") if isinstance(s.get("scenes"), list) else []
    verifier(len(scenes) >= 4 and all(isinstance(x, dict) for x in scenes), "« scenes » doit être une liste d'au moins 4 scènes")
    scenes = [x for x in scenes if isinstance(x, dict)]
    marque = s.get("marque") if isinstance(s.get("marque"), dict) else {}
    verifier(marque.get("nom") == "Carnet" and str(marque.get("accent", "")).upper() == "#1F6FEB",
             "la marque doit reprendre le nom et la couleur d'accent du scénario")
    verifier(s.get("format", "16:9") in ("16:9", "9:16", "1:1", "4:5"), "format inconnu")
    durees = [x.get("duree") for x in scenes]
    nombres = all(isinstance(d, (int, float)) and not isinstance(d, bool) and d >= 0.8 for d in durees)
    verifier(nombres, "chaque scène a une « duree » d'au moins 0,8 seconde")
    if nombres and scenes:
        verifier(20 <= sum(durees) <= 45, f"durée totale de {sum(durees)} s : 20 à 45 attendues")
    for x in scenes:
        verifier(x.get("type") in ("titre", "capture", "points", "fin"),
                 f"type de scène refusé : {x.get('type')!r} (« chiffre » : le scénario ne donne aucun chiffre)")
        titre = x.get("titre")
        verifier(isinstance(titre, str) and 1 <= len(titre.split()) <= 6, f"titre absent ou de plus de 6 mots : {titre!r}")
    if scenes:
        un, fin_ = scenes[0], scenes[-1]
        verifier(un.get("type") == "titre" and isinstance(un.get("duree"), (int, float)) and un["duree"] <= 3,
                 "la première scène est un « titre » de 3 secondes au plus")
        verifier("facture" in str(un.get("titre", "")).lower() + str(un.get("sous_titre", "")).lower()
                 and "minute" in str(un.get("titre", "")).lower() + str(un.get("sous_titre", "")).lower(),
                 "la première scène ne porte pas le bénéfice du scénario (les factures, en deux minutes)")
        verifier(fin_.get("type") == "fin" and all(isinstance(fin_.get(k), str) and fin_.get(k) for k in ("titre", "bouton", "url")),
                 "la dernière scène est une « fin » avec titre, bouton et url")
    captures = [x for x in scenes if x.get("type") == "capture"]
    verifier(len(captures) >= 2, "au moins deux scènes « capture »")
    for x in captures:
        image = x.get("image")
        verifier(isinstance(image, str) and not Path(image).is_absolute() and Path(image).is_file(),
                 f"image de capture introuvable à côté du storyboard : {image!r}")
    verifier("@" not in json.dumps(s, ensure_ascii=False), "une adresse de courriel apparaît dans le storyboard")
elif f.is_file() and not ECHECS:
    verifier(False, "storyboard.json doit être un objet JSON")
fin()
