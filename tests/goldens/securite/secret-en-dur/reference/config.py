import os


def cle_paiement():
    cle = os.environ.get("PAIEMENT_CLE")
    if not cle:
        raise RuntimeError("variable d'environnement PAIEMENT_CLE absente")
    return cle
