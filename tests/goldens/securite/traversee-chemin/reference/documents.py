from pathlib import Path


def lire_document(base, nom):
    racine = Path(base).resolve()
    cible = (racine / nom).resolve()
    if cible != racine and racine not in cible.parents:
        raise PermissionError("document hors du dossier autorisé")
    return cible.read_text(encoding="utf-8")
