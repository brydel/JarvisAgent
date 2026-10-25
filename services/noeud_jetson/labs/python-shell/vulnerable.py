"""Fixture SAST synthétique : ne jamais lancer cette fonction avec une entrée réelle."""
import subprocess


def diagnostic(user_input: str):
    return subprocess.run(user_input, shell=True)
