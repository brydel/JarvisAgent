"""Résumé d'un texte par un modèle."""
import json


def resumer(texte, fournisseur):
    """`fournisseur(texte)` renvoie une chaîne JSON {"resume": "..."}."""
    return json.loads(fournisseur(texte))["resume"]
