"""Adaptateurs fournisseurs : capacités DÉCLARÉES et VÉRIFIÉES de Claude Code et Codex, extensibles.

Pour chaque fournisseur : CLI présent et version, modèles du catalogue et leur état de vérification (un
modèle n'est utilisable qu'après un essai réussi avec l'abonnement), authentification observable, outils
disponibles, quotas tels que le fournisseur les publie (fenêtres, source, date, fraîcheur), santé et
possibilité de reprise de conversation. Rien n'est supposé : une donnée absente est « inconnu ».

Ce module ne contourne rien : il lit ce que les CLI exposent déjà. Il ne distingue pas à ta place
abonnement de développement et inférence vendue aux clients : les SaaS produits par l'usine ne doivent
pas consommer ces abonnements (voir docs/autonomy/fournisseurs.md).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

from . import config

ADAPTATEURS: dict[str, dict] = {
    "claude": {
        "titre": "Claude Code", "cli": "claude", "config": Path.home() / ".claude",
        "outils": ["Read", "Edit", "Bash", "Glob", "Grep", "WebFetch", "MCP (Linear)", "skills"],
        "reprise": "oui (workmux open --continue : reprise de la conversation du worktree)",
        "quotas_format": "fenêtres publiées par le CLI (five_hour / seven_day) ; lues depuis sa barre d'état",
        "authentification": "session du CLI (connexion dans le terminal) ; aucun jeton n'est lu ni copié par Jarvis",
        "modes": {"permission": "jarvis-claude passe --permission-mode auto aux agents ; le chef garde ses règles deny"},
    },
    "codex": {
        "titre": "Codex", "cli": "codex", "config": Path.home() / ".codex",
        "outils": ["shell (bac à sable)", "apply_patch", "MCP (Linear)", "skills ($HOME/.agents/skills)"],
        "reprise": "oui (workmux open --continue)",
        "quotas_format": "RateLimitSnapshot des sessions (used_percent, window_minutes, resets_at) ; la durée des fenêtres vient du fournisseur",
        "authentification": "connexion du CLI ; aucun jeton n'est lu ni copié par Jarvis",
        "modes": {"bac_a_sable": "codex.mode = bac-a-sable : écriture limitée au worktree et aux livrables"},
    },
}


def _version(cli: str) -> str:
    path = shutil.which(cli)
    if not path:
        return ""
    try:
        res = subprocess.run([cli, "--version"], capture_output=True, text=True, timeout=15)
        return (res.stdout or res.stderr).strip().splitlines()[0][:60] if res.returncode == 0 else "présent (version illisible)"
    except (subprocess.TimeoutExpired, OSError):
        return "présent (version illisible)"


def _connecte(nom: str, dossier: Path) -> str:
    """Indice d'authentification observable sans lire aucun secret : présence d'un dossier de configuration récent."""
    if not dossier.is_dir():
        return "inconnu (dossier de configuration absent : lance le CLI une fois)"
    try:
        age = time.time() - max((f.stat().st_mtime for f in dossier.iterdir()), default=0)
    except OSError:
        return "inconnu"
    return "probable (activité récente du CLI)" if age < 7 * 86400 else f"douteux (aucune activité depuis {int(age / 86400)} j)"


def capacites(now: float | None = None) -> dict:
    """{fournisseur: {cli, version, auth, modeles: [...], quotas: {...}, sante, reprise, outils}}."""
    now = now or time.time()
    from . import modeles, usage
    try:
        resume = usage.summary(now)
    except Exception:  # noqa: BLE001
        resume = {}
    cat = modeles.catalogue()
    out = {}
    for nom, a in ADAPTATEURS.items():
        u = resume.get(nom) or {}
        version = _version(a["cli"])
        mods = []
        for m_nom, m in cat.items():
            if m.get("fournisseur") != nom:
                continue
            mods.append({"nom": m_nom, "id": m.get("id", ""), "utilisable": modeles.utilisable(m),
                         "niveau": m.get("niveau"), "cout": m.get("cout")})
        quotas = {}
        for k in ("5h", "semaine"):
            if u.get(k):
                quotas[k] = {"utilise_pct": u[k]["used"], "remise_a_zero": usage.fmt_reset(u[k].get("resets_at"))}
        out[nom] = {
            "titre": a["titre"], "cli": a["cli"], "present": bool(version), "version": version or "absent",
            "authentification": _connecte(nom, a["config"]) if version else "sans objet (CLI absent)",
            "modeles": mods, "outils": a["outils"], "reprise": a["reprise"], "modes": a["modes"],
            "quotas": {"fenetres": quotas, "source": u.get("source", "inconnu"), "format": a["quotas_format"],
                       "mesure": time.strftime("%d/%m %H:%M", time.localtime(u["maj"])) if u.get("maj") else "jamais",
                       "age_s": u.get("age_s"), "perime": bool(u.get("perime")), "niveau": u.get("niveau", "inconnu"),
                       "prevision": u.get("prevision")},
            "sante": ("indisponible (CLI absent)" if not version else
                      "épuisé" if u.get("niveau") == "epuise" else
                      "prudence (mesure périmée)" if u.get("perime") else
                      "inconnu (aucune mesure)" if u.get("niveau") == "inconnu" else "ok"),
            "note": a.get("note", ""),
        }
    return out


def texte(caps: dict | None = None) -> str:
    caps = caps or capacites()
    out = ["FOURNISSEURS — capacités déclarées et vérifiées (rien n'est supposé illimité)"]
    for nom, c in caps.items():
        out.append("")
        out.append(f"{c['titre']} ({c['cli']}) : {c['version']} · authentification : {c['authentification']} · santé : {c['sante']}")
        q = c["quotas"]
        fen = ", ".join(f"{k} {v['utilise_pct']:.0f} % (remise à zéro {v['remise_a_zero']})" for k, v in q["fenetres"].items()) or "aucune fenêtre lue"
        age = f"{q['age_s'] // 60} min" if q.get("age_s") is not None else "—"
        out.append(f"  quotas : {fen} · source : {q['source']} · mesure du {q['mesure']} (âge {age}"
                   + (", PÉRIMÉE : prudence" if q["perime"] else "") + ")")
        out.append(f"  format des quotas : {q['format']}")
        verif = [m["nom"] for m in c["modeles"] if m["utilisable"]]
        non = [m["nom"] for m in c["modeles"] if not m["utilisable"]]
        out.append(f"  modèles vérifiés : {', '.join(verif) or 'aucun'}" + (f" · non vérifiés : {', '.join(non)}" if non else ""))
        out.append(f"  outils : {', '.join(c['outils'])} · reprise : {c['reprise']}")
        for k, v in c["modes"].items():
            out.append(f"  {k} : {v}")
    out.append("")
    out.append("Les abonnements ci-dessus financent le développement ; un SaaS vendu aux clients a besoin de sa propre "
               "inférence (API payante ou autre), désactivée tant qu'aucun budget ne la couvre.")
    return "\n".join(out)
