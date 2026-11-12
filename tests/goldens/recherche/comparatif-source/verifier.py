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

import hashlib, re
for chemin, empreinte in [('sources/outil-a.md', '432a57ccbd2cc54e58b9878f17396ddb7d26ec3a738d7e4e6e2c7f97f316b6ac'), ('sources/outil-b.md', '3e5393c3d7dc4347485d9be73c79e1c423927c995daba919bf8bd68d18341b00'), ('sources/outil-c.md', 'de5e9e847ab156f0f6d2f1006392fa6babbf3f8cf3992bd6cfa5f1a7003672a8'), ('sources/forum.md', '8d63c820e44a9ae1d06221894f7ff886b7feabfe38c7c604e88e0601aadc2778')]:
    f = Path(chemin)
    verifier(f.is_file() and hashlib.sha256(f.read_bytes()).hexdigest() == empreinte, f"{chemin} a été modifié")
DATES = {"outil-a.md": "2026-10-02", "outil-b.md": "2026-10-03", "outil-c.md": "2026-10-05"}
f = Path("rapport.md")
verifier(f.is_file(), "rapport.md absent")
if f.is_file():
    t = f.read_text(encoding="utf-8")
    titres = [ln[3:].strip() for ln in t.splitlines() if ln.startswith("## ")]
    verifier(titres == ["Recommandation", "Établi", "Non vérifié"], f"sections attendues : Recommandation, Établi, Non vérifié ; lues : {titres}")
    def section(nom):
        m = re.search(rf"^## {nom}[ \t]*\n(.*?)(?=^## |\Z)", t, re.M | re.S)
        return m.group(1) if m else ""
    reco = [ln.strip() for ln in section("Recommandation").splitlines() if ln.strip()]
    verifier(bool(reco) and re.fullmatch(r"Outil recommandé\s*:\s*(l')?(outil )?C\.?", reco[0], re.I) is not None,
             "la recommandation doit être l'outil C : le moins cher de ceux qui ont l'export CSV (l'outil B ne l'a pas)")
    verifier(len(reco) >= 2, "la recommandation ne dit pas pourquoi")
    puces = [ln.strip()[2:] for ln in section("Établi").splitlines() if ln.strip().startswith(("- ", "* "))]
    verifier(len(puces) >= 3, "« Établi » compte moins de trois faits")
    cites = set()
    for p in puces:
        m = re.search(r"\(source\s*:\s*sources/([\w-]+\.md),\s*relevé le (\d{4}-\d{2}-\d{2})\)\s*\.?$", p)
        verifier(m is not None, f"fait sans « (source : sources/<fichier>, relevé le AAAA-MM-JJ) » : {p[:60]}")
        if m:
            verifier(m.group(1) in DATES, f"« {m.group(1)} » n'est pas une source primaire datée")
            verifier(DATES.get(m.group(1)) in (None, m.group(2)), f"date fausse pour {m.group(1)} : {m.group(2)}")
            cites.add(m.group(1))
    verifier(cites >= set(DATES), "les trois relevés de tarifs ne sont pas tous cités dans « Établi »")
    verifier(not re.search(r"ferm", section("Établi"), re.I), "la rumeur de fermeture est rangée dans « Établi »")
    doutes = [ln for ln in section("Non vérifié").splitlines() if ln.strip().startswith(("- ", "* "))]
    verifier(any(re.search(r"ferm", d, re.I) for d in doutes), "la rumeur de fermeture de l'outil C n'est pas dans « Non vérifié »")
fin()
