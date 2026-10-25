"""Variante corrigée pour vérifier que la règle ne signale plus shell=True."""
import subprocess


def diagnostic():
    return subprocess.run(["uname", "-a"], shell=False, check=True)
