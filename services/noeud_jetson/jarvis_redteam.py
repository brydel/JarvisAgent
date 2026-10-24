"""Extension MCP optionnelle : conserve le point d'entrée GPU déjà installé.

La clé SSH reste limitée à mcp/depot/sante par le répartiteur existant. Le mandat
RedTeam est contrôlé par Jarvis ; la politique de cible reste sur le nœud.
Compatible avec le Python 3.10 livré par JetPack.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

OUTIL = {
    "name": "redteam_auditer",
    "description": "Audit statique Python sur la cible fixée par le propriétaire. Aucun test réseau.",
    "inputSchema": {"type": "object", "additionalProperties": False,
                    "required": ["mission_id", "deadline"],
                    "properties": {"mission_id": {"type": "string", "minLength": 4, "maxLength": 67},
                                   "deadline": {"type": "number"}}},
}


def politique():
    from redteam_engine import Policy
    path = Path(os.environ.get("JARVIS_REDTEAM_CONF") or Path.home() / ".config/jarvis-noeud/redteam.env")
    values = {}
    for line in path.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    required = ("JARVIS_REDTEAM_ROOT", "JARVIS_REDTEAM_STATE", "JARVIS_REDTEAM_IMAGE")
    if not all(values.get(key) for key in required):
        raise ValueError("Politique RedTeam incomplète ; Docker et cible propriétaire requis.")
    return Policy(Path(values[required[0]]), Path(values[required[1]]),
                  sandbox_image=values[required[2]])


def activer(noeud) -> None:
    if getattr(noeud, "_extension_redteam", False):
        return
    if any(tool.get("name") == OUTIL["name"] for tool in noeud.OUTILS):
        raise ValueError("Un outil RedTeam existe déjà ; comparaison manuelle requise.")
    original = noeud.appeler_outil

    def appeler(nom: str, arguments: dict, reglages: dict) -> dict:
        if nom != OUTIL["name"]:
            return original(nom, arguments, reglages)
        from redteam_engine import Engine
        try:
            return Engine(politique()).run(arguments)
        except (RuntimeError, subprocess.SubprocessError) as exc:
            # Le serveur installé ne capture pas forcément les erreurs de scan.
            raise noeud.ErreurNoeud("Audit RedTeam échoué : " + type(exc).__name__) from None

    noeud.OUTILS = [*noeud.OUTILS, OUTIL]
    noeud.appeler_outil = appeler
    noeud._extension_redteam = True


if __name__ == "__main__":
    import jarvis_noeud
    activer(jarvis_noeud)
    sys.exit(jarvis_noeud.principal(sys.argv[1:]))
