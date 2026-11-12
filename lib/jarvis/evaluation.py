"""Harnais d'évaluation des rôles : des cas fixes (tests/goldens/) jugés par des scripts, jamais par un LLM.

Deux usages :
1. **Contrôle gratuit** (`jarvis eval verifier`, et les tests du dépôt) : pour chaque cas, la vérification doit
   refuser le projet de départ et accepter la solution de référence ; le brief du rôle doit garder ses
   exigences. Deux sortes : `exigences_brief` (règles métier, des expressions cherchées dans le brief) et
   `exigences_compte_rendu` (contrôles exécutés : l'exemple et le contre-exemple de compte rendu du brief sont
   relus par l'analyseur de comptes_rendus). Une modification de prompt qui retire une règle importante, ou qui
   abîme son exemple de compte rendu, casse ce contrôle.
2. **Exécution réelle** (`jarvis eval lancer <rôle>/<cas> --confirmer`) : un vrai agent (Claude Code ou Codex,
   en mode non interactif) travaille sur une copie du départ, avec le brief de son rôle et la consigne du cas ;
   la vérification cachée juge le résultat. Consomme le quota de l'abonnement : manuel, soumis à l'admission
   (pauses, capacité, jetons), résultat enregistré dans evaluations.jsonl avec l'empreinte du brief et l'analyse
   du compte rendu rendu par l'agent (`compte_rendu` : type, conformité, anomalies). Cette analyse est une
   mesure à part : « ok » reste le seul verdict de la vérification cachée.

La vérification vit hors du dossier donné à l'agent : il ne peut ni la lire ni l'adapter.
"""

from __future__ import annotations

import hashlib
import secrets
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import zlib
from pathlib import Path

from . import comptes_rendus, config, store

RACINE = config.JARVIS_HOME / "tests" / "goldens"
RESULTATS = "evaluations.jsonl"


class EvalError(ValueError):
    pass


def cas_tous(role: str | None = None) -> list[dict]:
    out = []
    for f in sorted(RACINE.glob("*/*/cas.toml")) if RACINE.is_dir() else []:
        with f.open("rb") as fh:
            c = tomllib.load(fh)
        d = f.parent
        c.update(nom=f"{d.parent.name}/{d.name}", dossier=d, role=c.get("role") or d.parent.name)
        if role and c["role"] != role:
            continue
        out.append(c)
    return out


def cas(nom: str) -> dict:
    trouve = next((c for c in cas_tous() if c["nom"] == nom), None)
    if not trouve:
        raise EvalError(f"cas inconnu « {nom} » (jarvis eval liste)")
    return trouve


def preparer(c: dict, dossier: Path, avec_reference: bool = False) -> Path:
    """Copie le départ (et la référence par-dessus si demandé) dans `dossier`, en dépôt git propre."""
    dossier.mkdir(parents=True, exist_ok=True)
    shutil.copytree(c["dossier"] / "depart", dossier, dirs_exist_ok=True)
    if avec_reference:
        shutil.copytree(c["dossier"] / "reference", dossier, dirs_exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=dossier, check=True)
    subprocess.run(["git", "-c", "user.name=jarvis", "-c", "user.email=jarvis@localhost", "add", "-A"], cwd=dossier, check=True)
    subprocess.run(["git", "-c", "user.name=jarvis", "-c", "user.email=jarvis@localhost", "commit", "-q", "-m", "départ"],
                   cwd=dossier, check=True)
    return dossier


def verifier(c: dict, dossier: Path, timeout: int = 180) -> tuple[bool, str]:
    """Lance la vérification cachée du cas dans `dossier`. (réussi, sortie).

    Réussi = code 0 ET la ligne « VERDICT: OK <jeton> » avec le jeton aléatoire passé sur l'entrée standard :
    un code évalué qui imprime « VERDICT: OK » et quitte au chargement ne suffit pas."""
    jeton = secrets.token_hex(12)
    try:
        r = subprocess.run([sys.executable, "-I", str(c["dossier"] / "verifier.py")], cwd=dossier, capture_output=True,
                           input=jeton + "\n", text=True, timeout=timeout,
                           # GOLDENS_LIB : où trouver l'analyseur de comptes rendus (« -I » ignore PYTHONPATH).
                           env={**{k: v for k, v in os.environ.items() if not k.startswith("JARVIS_")},
                                "GOLDENS_LIB": str(Path(__file__).resolve().parents[1])})
    except subprocess.TimeoutExpired:
        return False, f"vérification interrompue après {timeout} s"
    sortie = (r.stdout + r.stderr).strip()
    ok = r.returncode == 0 and f"VERDICT: OK {jeton}" in r.stdout.splitlines()
    return ok, sortie.replace(jeton, "<jeton>")[-2000:]


# --- Contrôles exécutables sur le brief : son exemple et son contre-exemple de compte rendu --------------------------

_BLOC = re.compile(r"^\*\*(Exemple de bon compte rendu|Contre-exemple)[^\n]*\*\*[^\n]*\n```[^\n]*\n(.*?)\n```", re.M | re.S)
_TEST = re.compile(r"\btests?\b|test_|\.test\.|_test\.", re.I)


def blocs_brief(corps: str) -> dict:
    """{"exemple": texte | None, "contre_exemple": texte | None} : les deux blocs de code qu'un brief place sous
    « **Exemple de bon compte rendu …** » et « **Contre-exemple …** » (le premier de chaque sorte)."""
    out: dict = {"exemple": None, "contre_exemple": None}
    for titre, texte in _BLOC.findall(corps or ""):
        cle = "exemple" if titre.startswith("Exemple") else "contre_exemple"
        if out[cle] is None:
            out[cle] = texte
    return out


def analyser_extrait(texte: str) -> dict:
    """Relit un compte rendu, complet ou en extrait, avec comptes_rendus.

    Un verdict de relecture est jugé en entier. Un extrait de fin de tâche est jugé sur ce qu'il montre : au moins
    un critère et une vérification, chaque critère avec sa preuve, chaque vérification avec son résultat (les
    rubriques qu'un extrait ne recopie pas — résumé, fichiers, branche — ne lui sont pas reprochées).
    Renvoie {"type": "verdict" | "termine", "anomalies": [...], "analyse": {...}}."""
    v = comptes_rendus.analyser_verdict(texte)
    if v["verdict"]:
        return {"type": "verdict", "anomalies": list(v["anomalies"]), "analyse": v}
    a = comptes_rendus.analyser_termine(texte)
    anomalies = [x for x in a["anomalies"] if x.startswith(("critère ", "vérification "))]
    if not a["criteres"]:
        anomalies.append("aucun critère")
    if not a["verifications"]:
        anomalies.append("aucune vérification")
    return {"type": "termine", "anomalies": anomalies, "analyse": a}


def _c_exemple(corps: str) -> str:
    texte = blocs_brief(corps)["exemple"]
    if texte is None:
        return "exemple de bon compte rendu absent"
    anomalies = analyser_extrait(texte)["anomalies"]
    return "exemple de compte rendu non conforme (" + " ; ".join(anomalies) + ")" if anomalies else ""


def _c_contre_exemple(corps: str) -> str:
    texte = blocs_brief(corps)["contre_exemple"]
    if texte is None:
        return "contre-exemple absent"
    return "" if analyser_extrait(texte)["anomalies"] else "contre-exemple que l'analyseur accepterait : il ne montre rien à éviter"


def _c_preuve_par_test(corps: str) -> str:
    texte = blocs_brief(corps)["exemple"]
    a = analyser_extrait(texte) if texte is not None else None
    if a and a["type"] == "termine" and any(_TEST.search(c["preuve"]) for c in a["analyse"]["criteres"]):
        return ""
    return "aucun critère de l'exemple n'est prouvé par un test"


def _c_ecart_declare(corps: str) -> str:
    texte = blocs_brief(corps)["exemple"]
    a = analyser_extrait(texte) if texte is not None else None
    if a and a["type"] == "termine" and (a["analyse"]["hypotheses"] or a["analyse"]["risques"]):
        return ""
    return "l'exemple ne montre ni hypothèse ni risque déclaré"


# Nom du contrôle (clé `exigences_compte_rendu` d'un cas.toml) → fonction(brief) → anomalie, ou "" si tout va bien.
CONTROLES_COMPTE_RENDU = {
    "exemple": _c_exemple,                    # l'exemple est relu sans anomalie par l'analyseur
    "contre_exemple": _c_contre_exemple,      # le contre-exemple existe et l'analyseur le refuse
    "preuve_par_test": _c_preuve_par_test,    # l'exemple prouve au moins un critère par un test
    "ecart_declare": _c_ecart_declare,        # l'exemple déclare une hypothèse ou un risque
}


def structure_brief(corps: str) -> list[str]:
    """Écarts d'un brief au gabarit commun : procédure numérotée, 3 à 5 interdits, « fini » défini, exemple de
    compte rendu relu sans anomalie, contre-exemple refusé par l'analyseur. Liste vide = conforme."""
    lignes = (corps or "").splitlines()

    def rubrique(titre: str, motif: str) -> int:
        """Nombre d'éléments (lignes reconnues par `motif`) sous l'intitulé, jusqu'à la première ligne vide."""
        try:
            i = next(n for n, ln in enumerate(lignes) if ln.strip() == titre)
        except StopIteration:
            return -1
        total = 0
        for ln in lignes[i + 1:]:
            if not ln.strip():
                break
            total += bool(re.match(motif, ln))
        return total

    out = []
    etapes = rubrique("**Procédure**", r"\d+\. ")
    if etapes < 3:
        out.append("« **Procédure** » absente" if etapes < 0 else f"procédure de {etapes} étape(s) : 3 au moins")
    interdits = rubrique("**À ne pas faire**", r"- ")
    if not 3 <= interdits <= 5:
        out.append("« **À ne pas faire** » absent" if interdits < 0 else f"{interdits} interdit(s) : 3 à 5 attendus")
    if "**Fini quand :**" not in (corps or ""):
        out.append("« **Fini quand :** » absent")
    return out + [x for x in (_c_exemple(corps), _c_contre_exemple(corps)) if x]


def analyser_sortie(sortie: str) -> dict:
    """Compte rendu rendu par un agent évalué : {"type", "conforme", "anomalies"}.

    La sortie d'un CLI peut recopier le prompt, donc le gabarit : on relit le DERNIER bloc « ✅ TERMINÉ », et un
    bloc qui porte encore les « <…> » du gabarit ne compte pas comme un compte rendu."""
    lignes = str(sortie or "").splitlines()
    debuts = [i for i, ln in enumerate(lignes) if "✅" in ln and re.search(r"TERMIN[ÉE]", ln, re.I)]
    texte = "\n".join(lignes[debuts[-1]:]) if debuts else str(sortie or "")
    if debuts and "<ton rôle>" in texte:
        return {"type": "inconnu", "conforme": False, "anomalies": ["seul le gabarit du prompt a été recopié"]}
    a = comptes_rendus.analyser(texte)
    return {"type": a["type"], "conforme": bool(a["conforme"]), "anomalies": list(a["anomalies"])[:8]}


def exigences_manquantes(c: dict, corps: str | None = None) -> list[str]:
    """Exigences du cas que le brief ne tient pas (`corps` : un brief candidat, sinon celui du rôle) : expressions
    de `exigences_brief` absentes, puis contrôles de `exigences_compte_rendu` en échec."""
    if corps is None:
        from . import roles
        r = roles.get(c["role"])
        if not r:
            return [f"rôle {c['role']} introuvable"]
        corps = r["corps"]
    out = [e for e in c.get("exigences_brief", []) if not re.search(e, corps, re.I)]
    for nom in c.get("exigences_compte_rendu", []):
        controle_cr = CONTROLES_COMPTE_RENDU.get(nom)
        anomalie = controle_cr(corps) if controle_cr else f"contrôle inconnu « {nom} »"
        if anomalie:
            out.append(anomalie)
    return out


def controle(role: str | None = None) -> list[dict]:
    """Contrôle gratuit de chaque cas : départ refusé, référence acceptée, exigences du brief présentes."""
    out = []
    for c in cas_tous(role):
        with tempfile.TemporaryDirectory(prefix="jarvis-eval-") as d:
            ok_depart, _ = verifier(c, preparer(c, Path(d) / "depart"))
            ok_ref, sortie_ref = verifier(c, preparer(c, Path(d) / "ref", avec_reference=True))
        manquantes = exigences_manquantes(c)
        out.append({"cas": c["nom"], "depart_refuse": not ok_depart, "reference_acceptee": ok_ref,
                    "exigences_manquantes": manquantes, "detail": "" if ok_ref else sortie_ref,
                    "ok": (not ok_depart) and ok_ref and not manquantes})
    return out


def empreinte_brief(role: str) -> str:
    from . import roles
    r = roles.get(role) or {}
    return hashlib.sha256((r.get("corps") or "").encode("utf-8")).hexdigest()[:12]


def consigne_complete(c: dict, brief: str | None = None) -> str:
    """Consigne donnée à l'agent évalué. `brief` : un brief candidat à mesurer à la place de celui du rôle.

    C'est le vrai prompt de l'usine (prompt_agent) : même brief, même protocole d'incertitude, même définition de
    « fini » et même format de compte rendu qu'une tâche réelle — sans Linear ni PR, et sans contexte local
    (mémoire, registre), pour que deux exécutions du même cas restent comparables."""
    from . import prompt_agent, roles
    return prompt_agent.pour_evaluation(roles.ou_defaut(c["role"]), c["consigne"], brief)


def commande_agent(agent: str, modele_id: str, consigne: str) -> list[str]:
    if agent == "claude":
        # Les cas (références et vérifications) ne doivent pas être lus par l'agent évalué.
        cache = str(RACINE)
        refus = [f"{outil}({cache}/**)" for outil in ("Read", "Grep", "Glob", "Edit", "Write")]
        cmd = ["claude", "-p", consigne, "--permission-mode", "acceptEdits",
               "--settings", json.dumps({"disableAllHooks": True, "permissions": {"deny": refus}})]
        return cmd + (["--model", modele_id] if modele_id else [])
    if agent == "codex":
        cmd = ["codex", "exec", "--sandbox", "workspace-write", "--skip-git-repo-check"]
        return cmd + (["-m", modele_id] if modele_id else []) + [consigne]
    raise EvalError(f"agent inconnu « {agent} » (claude ou codex)")


def lancer(nom: str, agent: str, modele: str = "", acteur: str = "humain", garder: bool = False,
           commande: list[str] | None = None, brief: str | None = None) -> dict:
    """Exécution réelle d'un cas par un agent. Passe par l'admission ; enregistre le résultat."""
    from . import admission, modeles
    c = cas(nom)
    m = modeles.catalogue().get(modele) if modele else None
    if modele and not m:
        raise EvalError(f"modèle inconnu « {modele} » (jarvis modele liste)")
    adm = admission.demander(origine="cli", projet="jarvis-eval", issue=f"EVAL-{zlib.crc32(nom.encode()) % 10000}",
                             agent=agent, role=c["role"], worktree=f"eval-{nom.replace('/', '-')}", acteur=acteur)
    duree_max = 60 * int(c.get("duree_max_min", 20))
    d = None
    debut = time.time()
    try:
        # L'agent évalué n'apparaît jamais dans workmux : sans prolongation, le démon expirerait la réservation
        # (et rendrait la place) au bout de admission.reservation_min, en plein essai.
        admission.prolonger(adm["reservation"], duree_max + 600)
        d = Path(tempfile.mkdtemp(prefix="jarvis-eval-"))
        try:
            preparer(c, d / "projet")
        except (OSError, subprocess.CalledProcessError) as exc:
            raise EvalError(f"préparation du cas impossible : {exc}") from exc
        cmd = commande or commande_agent(agent, (m or {}).get("id", ""), consigne_complete(c, brief))
        try:
            r = subprocess.run(cmd, cwd=d / "projet", capture_output=True, text=True, timeout=duree_max)
            sortie_agent = r.stdout + r.stderr
        except subprocess.TimeoutExpired:
            sortie_agent = "agent interrompu : durée maximale dépassée"
        except FileNotFoundError as exc:
            raise EvalError(f"{cmd[0]} introuvable : {exc}") from exc
        ok, detail = verifier(c, d / "projet")
    finally:
        admission.liberer(adm["reservation"], "évaluation terminée", acteur=acteur)
        if d is not None and not garder:
            shutil.rmtree(d, ignore_errors=True)
    # Indice de triche : l'agent a cherché les cas eux-mêmes (références, vérifications) au lieu de travailler.
    suspect = bool(re.search(r"tests/goldens|verifier\.py|/reference/", sortie_agent))
    compte_rendu = analyser_sortie(sortie_agent)
    sortie_agent = sortie_agent[-1500:]
    res = {"ts": time.time(), "cas": nom, "role": c["role"], "agent": agent, "modele": modele or f"{agent}-defaut",
           "brief": (hashlib.sha256(brief.encode("utf-8")).hexdigest()[:12] if brief is not None
                     else empreinte_brief(c["role"])), "candidat": brief is not None, "ok": ok, "duree_s": round(time.time() - debut, 1),
           "detail": detail[-500:], "sortie_agent": sortie_agent[-300:], "suspect": suspect,
           "compte_rendu": compte_rendu}
    with store.locked(RESULTATS):
        with store.state_path(RESULTATS).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(res, ensure_ascii=False) + "\n")
    try:
        from . import journal
        journal.ecrire("systeme", acteur=acteur, objet=f"eval:{nom}", decision="reussi" if ok else "echoue",
                       raison=f"{agent}/{modele or 'défaut'} brief {res['brief']}")
    except Exception:  # noqa: BLE001
        pass
    if garder:
        res["dossier"] = str(d / "projet")
    return res


def resultats(n: int = 30) -> list[dict]:
    try:
        lignes = store.state_path(RESULTATS).read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    out = []
    for ln in lignes[-n:]:
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out


def promptfoo_config() -> str:
    """Configuration promptfoo (outil facultatif, non installé par Jarvis) : chaque cas devient un test dont le
    « fournisseur » est notre exécuteur (vrai agent + vérification cachée). JSON valide = YAML valide."""
    tests = [{"description": c["nom"], "vars": {"cas": c["nom"]},
              "assert": [{"type": "contains", "value": "VERDICT: OK"}]} for c in cas_tous()]
    conf = {
        "description": "Rôles JarvisAgent — cas fixes jugés par scripts (tests/goldens)",
        "prompts": ["{{cas}}"],
        # Chemin relatif : lancer « npx promptfoo eval -c outils/promptfoo/promptfooconfig.yaml » depuis le dépôt.
        "providers": [{"id": "exec: ./bin/jarvis eval lancer --sortie-brute --confirmer", "label": "jarvis-eval"}],
        "tests": tests,
    }
    return json.dumps(conf, ensure_ascii=False, indent=2)
