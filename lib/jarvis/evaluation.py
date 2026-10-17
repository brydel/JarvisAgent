"""Harnais d'évaluation des rôles : des cas fixes (tests/goldens/) jugés par des scripts, jamais par un LLM.

Deux usages :
1. **Contrôle gratuit** (`jarvis eval verifier`, et les tests du dépôt) : pour chaque cas, la vérification doit
   refuser le projet de départ et accepter la solution de référence ; le brief du rôle doit contenir ses
   exigences. Une modification de prompt qui retire une règle importante casse ce contrôle.
2. **Exécution réelle** (`jarvis eval lancer <rôle>/<cas> --confirmer`) : un vrai agent (Claude Code ou Codex,
   en mode non interactif) travaille sur une copie du départ, avec le brief de son rôle et la consigne du cas ;
   la vérification cachée juge le résultat. Consomme le quota de l'abonnement : manuel, soumis à l'admission
   (pauses, capacité, jetons), résultat enregistré dans evaluations.jsonl avec l'empreinte du brief.

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

from . import config, store

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
                           env={k: v for k, v in os.environ.items() if not k.startswith("JARVIS_")})
    except subprocess.TimeoutExpired:
        return False, f"vérification interrompue après {timeout} s"
    sortie = (r.stdout + r.stderr).strip()
    ok = r.returncode == 0 and f"VERDICT: OK {jeton}" in r.stdout.splitlines()
    return ok, sortie.replace(jeton, "<jeton>")[-2000:]


def exigences_manquantes(c: dict) -> list[str]:
    from . import roles
    r = roles.get(c["role"])
    if not r:
        return [f"rôle {c['role']} introuvable"]
    return [e for e in c.get("exigences_brief", []) if not re.search(e, r["corps"], re.I)]


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


def consigne_complete(c: dict) -> str:
    from . import roles
    r = roles.ou_defaut(c["role"])
    return (f"# Ton rôle : {r['titre']}\n\n{r['corps']}\n\n# Ta tâche\n\n{c['consigne'].strip()}\n\n"
            "Travaille uniquement dans le dossier courant. Quand tu as fini, arrête-toi : une vérification "
            "automatique jugera le résultat.")


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
           commande: list[str] | None = None) -> dict:
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
        cmd = commande or commande_agent(agent, (m or {}).get("id", ""), consigne_complete(c))
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
    sortie_agent = sortie_agent[-1500:]
    res = {"ts": time.time(), "cas": nom, "role": c["role"], "agent": agent, "modele": modele or f"{agent}-defaut",
           "brief": empreinte_brief(c["role"]), "ok": ok, "duree_s": round(time.time() - debut, 1),
           "detail": detail[-500:], "sortie_agent": sortie_agent[-300:], "suspect": suspect}
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
