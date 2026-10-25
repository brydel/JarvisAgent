"""Inventaire RedTeam en lecture seule, exécutable aussi avec Python 3.10 sur JetPack.

Aucun téléchargement, inférence, sudo ou changement de configuration. La sortie ne
contient ni environnement, ni nom d'utilisateur, ni adresse réseau, ni jeton.
"""
from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def commande(argv: list[str]) -> dict:
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=10)
        # stderr peut contenir une adresse de registre ou un chemin personnel.
        return {"code": result.returncode, "sortie": result.stdout[:20_000] if result.returncode == 0 else ""}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"code": None, "erreur": type(exc).__name__}


def texte(path: str) -> str:
    try:
        return Path(path).read_text().strip("\x00\n")
    except OSError:
        return ""


def ollama(endpoint: str, payload: dict | None = None) -> dict:
    class SansRedirection(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), SansRedirection())
    request = urllib.request.Request(
        "http://127.0.0.1:11434/api/" + endpoint,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json"})
    with opener.open(request, timeout=10) as response:
        data = response.read(1_000_001)
    if len(data) > 1_000_000:
        raise ValueError("Réponse Ollama trop volumineuse.")
    result = json.loads(data)
    if not isinstance(result, dict):
        raise ValueError("Objet Ollama attendu.")
    return result


def inventaire() -> dict:
    memory = {}
    for line in texte("/proc/meminfo").splitlines():
        key, _, value = line.partition(":")
        if key in {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}:
            memory[key + "_kio"] = int(value.split()[0])
    disk = shutil.disk_usage("/")
    docker = commande(["docker", "info", "--format",
                        '{{json .Architecture}} {{json .ServerVersion}}'])
    report = {
        "version": 1, "date_utc": datetime.now(timezone.utc).isoformat(),
        "modele": texte("/proc/device-tree/model"), "architecture": platform.machine(),
        "python": platform.python_version(), "l4t": texte("/etc/nv_tegra_release"),
        "jetpack": commande(["dpkg-query", "-W", "-f=${Version}", "nvidia-jetpack"]),
        "cuda": commande(["/usr/local/cuda/bin/nvcc", "--version"]),
        "memoire": memory, "disque": {"total_octets": disk.total, "libre_octets": disk.free},
        "docker": docker,
        "service_actif": commande(["systemctl", "--user", "is-active", "jarvis-noeud"]),
        "gpu_memoire_mesuree": False,
        "aptitude_scan_distant": "à vérifier" if docker["code"] == 0 else "bloquée : accès Docker indisponible",
    }
    try:
        models = []
        report["ollama_version"] = ollama("version").get("version")
        for model in ollama("tags").get("models", []):
            # Ne détaille que le catalogue RedTeam, sans exposer d'autres noms privés.
            if model.get("name") not in {"gemma3:4b", "qwen3:4b"}:
                continue
            detail = ollama("show", {"model": model["name"]})
            license_text = detail.get("license", "")
            models.append({"nom": model["name"], "digest": model.get("digest"),
                           "octets": model.get("size"), "details": detail.get("details"),
                           "capacites": detail.get("capabilities"),
                           "licence_sha256": hashlib.sha256(license_text.encode()).hexdigest(),
                           "licence_presente": bool(license_text)})
        report["modeles"] = models
    except (OSError, ValueError, KeyError, TypeError) as exc:
        report["ollama_erreur"] = type(exc).__name__
    return report


if __name__ == "__main__":
    print(json.dumps(inventaire(), ensure_ascii=False, indent=2))
