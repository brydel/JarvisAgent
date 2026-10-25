"""Entrée locale du moteur, autorisation fournie par la configuration du propriétaire."""
import json
import sys
import subprocess
from redteam_engine import Engine, Policy

if __name__ == "__main__":
    try:
        raw = sys.stdin.read(4097)
        if len(raw) > 4096:
            raise ValueError("Demande trop longue.")
        result = Engine(Policy.environment()).run(json.loads(raw))
        print(json.dumps(result, ensure_ascii=False))
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({"erreur": str(exc)[:300]}))
        sys.exit(1)
