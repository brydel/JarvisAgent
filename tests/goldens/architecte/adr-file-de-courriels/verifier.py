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
ROLES = {"architecte", "backend", "data", "design", "devops", "frontend", "generaliste", "ia-produit", "marketing",
         "qa", "recherche", "redaction", "revue", "securite", "video"}
for chemin, empreinte in (("app/notifications.py", "e2bcc5d34151199018230c96de569e340595e494485c26ccd3b5c01179a92371"),
                          ("app/commandes.py", "8b0fd0a1961145c874e8033bef2e083fcc29ca9fc1bb33c9678bb2a7851452f5")):
    f = Path(chemin)
    verifier(f.is_file() and hashlib.sha256(f.read_bytes()).hexdigest() == empreinte, f"{chemin} a été modifié")
adrs = sorted(Path("docs/adr").glob("0002-*.md"))
verifier(len(adrs) == 1, "il faut exactement un fichier docs/adr/0002-<titre>.md")
if len(adrs) == 1:
    t = adrs[0].read_text(encoding="utf-8")
    lignes = t.splitlines()
    verifier(bool(lignes) and lignes[0].startswith("# ADR-0002"), "première ligne : « # ADR-0002 : … »")
    verifier(re.search(r"^Statut\s*:\s*proposé", t, re.M) is not None, "ligne « Statut : proposé » absente")
    titres = [ln[3:].strip() for ln in lignes if ln.startswith("## ")]
    attendus = ["Contexte", "Options", "Décision", "Conséquences", "Découpage"]
    verifier([x.split(" ")[0] for x in titres] == attendus, f"sections attendues, dans l'ordre : {attendus} ; lues : {titres}")
    def section(nom):
        m = re.search(rf"^## {nom}[^\n]*\n(.*?)(?=^## |\Z)", t, re.M | re.S)
        return m.group(1) if m else ""
    options = [o for o in re.split(r"^### ", section("Options"), flags=re.M)[1:]]
    verifier(len(options) >= 2, "au moins deux options sous des titres « ### Option … »")
    for o in options:
        for champ in ("Coût", "Bloque", "Retour arrière"):
            verifier(re.search(rf"^{champ}\s*:\s*\S", o, re.M) is not None,
                     f"option « {o.splitlines()[0][:40]} » sans ligne « {champ} : »")
    cites = re.findall(r"(app/[\w/]+\.py):(\d+)", section("Contexte"))
    verifier(bool(cites), "le contexte ne cite aucun fichier:ligne de app/")
    for chemin, n in cites:
        f = Path(chemin)
        verifier(f.is_file() and 1 <= int(n) <= len(f.read_text(encoding="utf-8").splitlines()),
                 f"renvoi {chemin}:{n} inexistant")
    verifier(len(section("Décision").split()) >= 15, "décision trop courte pour dire ce qui tranche")
    verifier(len(section("Conséquences").split()) >= 8, "conséquences absentes")
    rangs = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in section("Découpage").splitlines()
             if ln.strip().startswith("|")]
    rangs = [r for r in rangs if not all(set(c) <= set("-: ") for c in r)][1:]   # sans l'en-tête ni le séparateur
    verifier(len(rangs) >= 2, "le découpage compte moins de deux tâches")
    vus = {}
    for r in rangs:
        if len(r) < 4:
            verifier(False, f"ligne de découpage incomplète : {r}")
            continue
        verifier(r[1].strip("` ").lower() in ROLES, f"rôle inconnu dans le découpage : « {r[1]} »")
        verifier(len(r[3]) >= 8, f"tâche « {r[0]} » sans critère vérifiable")
        fichiers = [x.strip("` ") for x in re.split(r"[,;]|<br>", r[2]) if x.strip("` ")]
        verifier(bool(fichiers), f"tâche « {r[0]} » sans fichier")
        for x in fichiers:
            verifier(x not in vus, f"{x} apparaît dans deux tâches (« {vus.get(x)} » et « {r[0]} »)")
            vus[x] = r[0]
fin()
