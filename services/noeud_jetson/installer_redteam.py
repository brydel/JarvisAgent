"""Installation RedTeam ciblée, sans remplacer ni redémarrer le service GPU.

À exécuter sur le nœud. Les droits Docker et l'image doivent déjà exister.
Chaque fichier modifié est sauvegardé ; une réexécution identique ne le réécrit pas.
"""
from __future__ import annotations

import argparse
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path


def publier(path: Path, content: bytes, mode: int) -> None:
    if path.is_symlink():
        raise ValueError("Lien symbolique refusé pour un fichier à installer.")
    if path.exists() and path.read_bytes() == content:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = Path(tempfile.mkdtemp(prefix=path.name + ".avant-redteam-", dir=path.parent)) / path.name
        shutil.copy2(path, backup)
    fd, name = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
            os.fchmod(stream.fileno(), mode)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def raccorder(content: str, public_key: str, directory: Path) -> str:
    fields = public_key.split()
    if len(fields) < 2 or fields[0] != "ssh-ed25519" or not re.fullmatch(r"[A-Za-z0-9+/=]+", fields[1]):
        raise ValueError("Clé publique ed25519 requise.")
    suffix = " ssh-ed25519 " + fields[1]
    matches = [line for line in content.splitlines() if suffix in line and
               (line.split(suffix, 1)[1] == "" or line.split(suffix, 1)[1].startswith(" "))]
    if len(matches) != 1:
        raise ValueError("Une unique clé Jarvis déjà installée est requise.")
    line = matches[0]
    match = re.fullmatch(r'command="([^"\\]*)",restrict( ssh-ed25519 .*)', line)
    if not match:
        raise ValueError("Restrictions SSH personnalisées : comparaison manuelle requise.")
    old = ["/usr/bin/python3", str(directory / "jarvis_noeud.py"), "ssh"]
    new = ["/usr/bin/python3", str(directory / "jarvis_redteam.py"), "ssh"]
    if shlex.split(match[1]) not in (old, new):
        raise ValueError("Commande forcée différente : activation refusée.")
    command = shlex.join(new)
    if '"' in command or "\\" in command:
        raise ValueError("Chemin incompatible avec la commande forcée.")
    replacement = 'command="' + command + '",restrict' + match[2]
    return "".join(replacement + ("\n" if row.endswith("\n") else "")
                   if row.rstrip("\n") == line else row for row in content.splitlines(keepends=True))


def principal() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--racine", type=Path, required=True)
    parser.add_argument("--etat", type=Path, required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--cle-jarvis", type=Path, help="Active la commande forcée pour cette clé publique existante.")
    args = parser.parse_args()
    values = {"JARVIS_REDTEAM_ROOT": str(args.racine), "JARVIS_REDTEAM_STATE": str(args.etat),
              "JARVIS_REDTEAM_IMAGE": args.image}
    if any("\n" in value or "\r" in value for value in values.values()):
        raise ValueError("Valeur de configuration multiligne refusée.")
    from redteam_engine import Policy
    Policy(args.racine, args.etat, sandbox_image=args.image).validate()
    image = subprocess.run(["docker", "image", "inspect", args.image, "--format", "{{.Id}}"],
                           capture_output=True, text=True, timeout=10)
    if image.returncode or not re.fullmatch(r"sha256:[0-9a-f]{64}\s*", image.stdout):
        raise ValueError("Image Docker locale inaccessible ; aucun fichier installé.")
    directory = Path.home() / ".local/share/jarvis-noeud"
    if not (directory / "jarvis_noeud.py").is_file():
        raise ValueError("Point d'entrée GPU existant requis.")
    ssh = Path.home() / ".ssh/authorized_keys"
    keys = raccorder(ssh.read_text(), args.cle_jarvis.read_text(), directory) if args.cle_jarvis else None
    source = Path(__file__).resolve().parent
    # Charger le point d'entrée sans lancer son serveur pour vérifier la compatibilité.
    import importlib.util
    spec = importlib.util.spec_from_file_location("_noeud_installe", directory / "jarvis_noeud.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "principal", None)) or not callable(getattr(module, "appeler_outil", None)):
        raise ValueError("Interface du point d'entrée existant incompatible.")
    from jarvis_redteam import activer
    activer(module)
    for filename in ("redteam_engine.py", "redteam_models.py", "redteam_cli.py", "jarvis_redteam.py"):
        publier(directory / filename, (source / filename).read_bytes(), 0o644)
    conf = Path.home() / ".config/jarvis-noeud/redteam.env"
    publier(conf, "".join(key + "=" + value + "\n" for key, value in values.items()).encode(), 0o600)
    if keys is not None:
        publier(ssh, keys.encode(), 0o600)
    print("Extension RedTeam installée ; service GPU conservé sans redémarrage.")
    print("Commande forcée " + ("activée pour la clé Jarvis." if keys is not None else "inchangée (préparation seule)."))


if __name__ == "__main__":
    principal()
